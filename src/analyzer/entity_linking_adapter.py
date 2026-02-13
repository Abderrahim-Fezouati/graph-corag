from __future__ import annotations
from typing import List, Dict, Optional, Any

from analyzer.sapbert_linker_v2 import SapBERTLinkerV2


# ============================================================
# Surface normalization
# ============================================================

def normalize_surface(text: str) -> str:
    """
    Normalize surface strings consistently across NER, SapBERT, and KG.
    """
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


# ============================================================
# Relation → expected entity types
# ============================================================

REL_TYPES = {
    "INTERACTS_WITH":      (["drug", "protein"], ["drug", "protein"]),
    "ADVERSE_EFFECT":      (["drug"], ["disease"]),
    "CONTRAINDICATED_FOR": (["drug"], ["disease"]),
    "MECHANISM_OF_ACTION": (["drug"], ["protein", "gene"]),
}


def get_allowed_types(relation: str, slot: str) -> List[str]:
    """
    Return allowed entity types given (relation, slot).
    """
    rel = (relation or "").upper()
    head_allowed, tail_allowed = REL_TYPES.get(
        rel,
        (["drug", "disease", "protein", "gene", "chemical"],) * 2
    )
    return head_allowed if slot == "head" else tail_allowed


# ============================================================
# Entity Linking Adapter
# ============================================================

class ELAdapter:
    """
    Unified entity-linking adapter.

    Architecture:
      - SapBERTLinkerV2 is the PRIMARY and AUTHORITATIVE linker
      - No legacy linker is required
      - No crashes on recall failure
      - No hallucination

    Guarantees:
      - Deterministic
      - Offline-safe
      - Publication-grade
    """

    def __init__(
        self,
        linker: Optional[Any] = None,
        reranker: Optional[Any] = None,
        default_topk: int = 8
    ):
        # Legacy linker is OPTIONAL and deprecated
        self.linker = linker
        self.reranker = reranker
        self.default_topk = default_topk

        # Primary SapBERT v2 linker
        self.sapbert_v2 = SapBERTLinkerV2()

    # --------------------------------------------------------
    # SapBERT v2 linking (primary path)
    # --------------------------------------------------------

    def _sapbert_v2_link(
        self,
        mention_text: str,
        relation: str,
        slot: str
    ) -> List[Dict[str, Any]]:
        """
        Try SapBERT v2 using allowed entity types.
        Returns at most ONE candidate (wrapped in list).
        """

        allowed_types = get_allowed_types(relation, slot)

        for etype in allowed_types:
            result = self.sapbert_v2.link(mention_text, etype)

            if result.get("kg_id") is not None:
                return [{
                    "kg_id": result["kg_id"],
                    "name": result["kg_id"],
                    "canonical_id": result["kg_id"],
                    "entity_type": etype,
                    "score": float(result["score"]),
                    "ctx_score": 0.0,
                    "linker": "sapbert_v2",
                }]

        return []

    # --------------------------------------------------------
    # Routed linking (SapBERT v2 → optional legacy)
    # --------------------------------------------------------

    def _routed_link(
        self,
        mention_text: str,
        relation: str,
        slot: str,
        topk: Optional[int] = None
    ) -> List[Dict[str, Any]]:

        # 1️⃣ Primary SapBERT v2
        cands = self._sapbert_v2_link(mention_text, relation, slot)
        if cands:
            return cands

        # 2️⃣ Optional legacy linker (if provided)
        if self.linker is None:
            return []

        types = get_allowed_types(relation, slot)
        k = topk or self.default_topk

        if hasattr(self.linker, "link"):
            try:
                return self.linker.link(
                    mention_text,
                    expected_types=types,
                    topk=k
                )
            except TypeError:
                return self.linker.link(mention_text, topk=k)

        if hasattr(self.linker, "link_text"):
            try:
                return self.linker.link_text(
                    mention_text,
                    expected_types=types,
                    topk=k
                )
            except TypeError:
                return self.linker.link_text(mention_text, topk=k)

        if hasattr(self.linker, "link_mentions"):
            try:
                return self.linker.link_mentions(
                    [mention_text],
                    expected_types=types,
                    topk=k
                )[0]
            except TypeError:
                return self.linker.link_mentions(
                    [mention_text],
                    topk=k
                )[0]

        # 🔒 SAFE FALLBACK — NO CRASH
        return []

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def link_mentions(
        self,
        question: str,
        mentions: List[str],
        relation: str,
        slot: str,
        topk: Optional[int] = None
    ) -> List[List[Dict[str, Any]]]:

        results: List[List[Dict[str, Any]]] = []

        for m in mentions:
            cands = self._routed_link(m, relation, slot, topk=topk)
            cands = self._normalize_candidates(cands)

            # annotate surface
            for c in cands:
                c["surface"] = m

            if self.reranker:
                cands = self.reranker.rerank(
                    question,
                    cands,
                    topk=topk or self.default_topk
                )

            cands = _apply_type_priority(
                cands,
                get_allowed_types(relation, slot)
            )

            results.append(cands[: (topk or self.default_topk)])

        return results

    def pick_best_cuis(
        self,
        question: str,
        mentions: List[str],
        relation: str,
        slot: str,
        topk: Optional[int] = None
    ) -> List[str]:

        linked = self.link_mentions(
            question,
            mentions,
            relation,
            slot,
            topk=topk
        )

        out: List[str] = []
        for cands in linked:
            if cands:
                out.append(cands[0]["kg_id"])

        return out

    # --------------------------------------------------------
    # Utilities
    # --------------------------------------------------------

    def _normalize_candidates(
        self,
        cands: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:

        out: List[Dict[str, Any]] = []

        for c in cands or []:
            out.append({
                "kg_id": c.get("kg_id"),
                "name": c.get("name") or "",
                "canonical_id": c.get("canonical_id"),
                "entity_type": c.get("entity_type"),
                "score": float(c.get("score", 0.0)),
                "ctx_score": float(c.get("ctx_score", 0.0)),
                "linker": c.get("linker", "unknown"),
            })

        out.sort(
            key=lambda x: (x["ctx_score"], x["score"]),
            reverse=True
        )
        return out


# ============================================================
# Type priority helper
# ============================================================

def _apply_type_priority(
    cands: List[Dict[str, Any]],
    expected_types: List[str]
) -> List[Dict[str, Any]]:

    exp = set(expected_types or [])
    good, rest = [], []

    for c in cands:
        if c.get("entity_type") in exp:
            good.append(c)
        else:
            rest.append(c)

    return good + rest
