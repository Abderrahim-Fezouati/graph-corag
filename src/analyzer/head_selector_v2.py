from __future__ import annotations
from typing import List, Dict, Optional
from collections import defaultdict


class HeadSelectorV2:
    """
    Confidence-aware, relation-aware head entity selector.

    Guarantees:
      - No forced selection
      - Deterministic behavior
      - Explicit abstention when uncertain
    """

    def __init__(
        self,
        min_score: float = 0.75,
        agreement_boost: float = 0.15,
        max_boost: float = 0.30
    ):
        """
        Args:
            min_score: minimum SapBERT score to accept a candidate
            agreement_boost: score bonus for multi-mention agreement
            max_boost: cap on agreement bonus
        """
        self.min_score = min_score
        self.agreement_boost = agreement_boost
        self.max_boost = max_boost

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def select_head(
        self,
        linked_mentions: List[List[Dict]],
        relation: str,
        slot: str
    ) -> Optional[str]:
        """
        Args:
            linked_mentions:
                Output of ELAdapter.link_mentions
                Shape: List[mentions] → List[candidates]
            relation:
                Predicted relation label
            slot:
                "head" or "tail"

        Returns:
            kg_id of selected head entity, or None (abstain)
        """

        if not linked_mentions:
            return None

        # Flatten candidates
        all_cands = []
        for cands in linked_mentions:
            if not cands:
                continue

            # --- Normalize candidate container ---
            if isinstance(cands, dict):
                # single candidate dict
                all_cands.append(cands)
            elif isinstance(cands, list):
                if len(cands) > 0:
                    all_cands.append(cands[0])
            else:
                continue

        if not all_cands:
            return None

        # Group by kg_id
        by_kg = defaultdict(list)
        for c in all_cands:
            if c.get("kg_id"):
                by_kg[c["kg_id"]].append(c)

        if not by_kg:
            return None

        # Score aggregation with agreement boost
        scored = []
        for kg_id, cands in by_kg.items():
            base_score = max(c["score"] for c in cands)
            agreement = len(cands) - 1
            boost = min(self.max_boost, agreement * self.agreement_boost)
            final_score = base_score + boost

            scored.append({
                "kg_id": kg_id,
                "base_score": base_score,
                "agreement": len(cands),
                "final_score": final_score,
                "entity_type": cands[0].get("entity_type"),
            })

        # Sort by final score
        scored.sort(key=lambda x: x["final_score"], reverse=True)

        best = scored[0]

        # Confidence gate
        if best["base_score"] < self.min_score:
            return None

        return best["kg_id"]
