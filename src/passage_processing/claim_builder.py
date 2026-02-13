# -*- coding: utf-8 -*-
"""
Build candidate KG claims from passages.

Design principles:
- Transparent
- Deterministic
- Epistemically aware (hypothesis vs fact)
- Backward compatible
"""

from typing import List, Dict, Optional

# ---------------------------------------------------------------------
# Lexical predicate triggers (review-safe, deterministic)
# ---------------------------------------------------------------------
PREDICATE_TRIGGERS = {
    "CAUSES": ["cause", "causes", "induce", "induces", "lead to"],
    "ADVERSE_EFFECT": ["adverse", "side effect", "toxicity"],
    "ASSOCIATED_WITH": ["associated", "linked", "correlated"],
    "INTERACTS_WITH": ["interact", "interacts", "binding"],
}


def infer_predicate(text: str) -> Optional[str]:
    """Infer predicate from raw passage text (lexical, conservative)."""
    t = text.lower()
    for pred, kws in PREDICATE_TRIGGERS.items():
        for kw in kws:
            if kw in t:
                return pred
    return None


# ---------------------------------------------------------------------
# Canonical API (USED BY PIPELINE)
# ---------------------------------------------------------------------
def build_claims(
    passages: List[Dict],
    head_cui: str,
    relation: Optional[str] = None,
) -> List[Dict]:
    """
    Build epistemically-aware KG claims from passage objects.

    Each passage must contain:
      - text
      - linked_entities: [{kg_id, ...}]

    Returns claims:
    {
        head_cui,
        predicate,
        tail_cui,
        evidence_text,
        claim_strength,
        claim_source
    }
    """
    claims = []

    for p in passages:
        text = p.get("text", "")
        linked_entities = p.get("linked_entities", [])

        predicate = relation or infer_predicate(text)
        if not predicate:
            continue

        for e in linked_entities:
            tail = e.get("kg_id")
            if not tail or tail == head_cui:
                continue

            claims.append({
                "head_cui": head_cui,
                "predicate": predicate,
                "tail_cui": tail,
                "evidence_text": text,
                # --- epistemics ---
                "claim_strength": "HYPOTHESIS",
                "claim_source": "PASSAGE",
            })

    return claims


# ---------------------------------------------------------------------
# Backward compatibility (OLD CALL SITES)
# ---------------------------------------------------------------------
def build_claims_from_passages(
    head_cui: str,
    passage_text: str,
    linked_entities: List[Dict],
    **kwargs,
) -> List[Dict]:
    """
    Legacy wrapper — preserved for older pipelines.
    """
    return build_claims(
        passages=[{
            "text": passage_text,
            "linked_entities": linked_entities,
        }],
        head_cui=head_cui,
        relation=None,
    )
