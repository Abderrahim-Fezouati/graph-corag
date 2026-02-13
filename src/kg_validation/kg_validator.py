# -*- coding: utf-8 -*-
"""
Read-only KG claim validator with epistemic awareness.
"""

from typing import Dict, Any, Optional, Tuple, Set
from kg_validation.verdict_types import Verdict, VerdictReason
from kg_validation.predicate_schema import is_antagonistic


def _norm(x: Optional[str]) -> str:
    return "" if x is None else str(x).strip().lower()


def _norm_rel(x: Optional[str]) -> str:
    return "" if x is None else str(x).strip().upper()


RELAXED_PREDICATES = {
    "CAUSES": {"ASSOCIATED_WITH", "AFFECTS"},
}


class KGValidator:
    def __init__(self, kg, kg_version: str):
        self.kg = kg
        self.kg_version = kg_version

        self.edge_set = getattr(kg, "edge_set", set())
        self.ht_to_preds: Dict[Tuple[str, str], Set[str]] = {}

        for h, r, t in self.edge_set:
            h2, t2, r2 = _norm(h), _norm(t), _norm_rel(r)
            self.ht_to_preds.setdefault((h2, t2), set()).add(r2)

    def validate_claim(
        self,
        head_cui: str,
        predicate: str,
        tail_cui: str,
        claim_strength: str = "HYPOTHESIS",
    ) -> Dict[str, Any]:

        h, r, t = _norm(head_cui), _norm_rel(predicate), _norm(tail_cui)

        out = {
            "verdict": Verdict.UNSUPPORTED,
            "reason": VerdictReason.NO_EDGE,
            "support_edges": [],
            "conflict_edges": [],
            "kg_version": self.kg_version,
        }

        if not h or not t:
            out["verdict"] = Verdict.INVALID_ENTITY
            out["reason"] = VerdictReason.GROUNDING_FAILURE
            return out

        preds = self.ht_to_preds.get((h, t), set())
        if not preds:
            return out  # unsupported hypothesis

        # Exact match
        if (h, r, t) in self.edge_set:
            out["verdict"] = Verdict.SUPPORTED
            out["reason"] = VerdictReason.EXACT_MATCH
            out["support_edges"] = [(h, r, t)]
            return out

        # Relaxed predicate
        for relaxed in RELAXED_PREDICATES.get(r, []):
            if relaxed in preds:
                out["verdict"] = Verdict.WEAKLY_SUPPORTED
                out["reason"] = VerdictReason.RELAXED_PREDICATE_MATCH
                return out

        # Contradiction
        for pr in preds:
            if is_antagonistic(r, pr):
                out["verdict"] = Verdict.CONTRADICTED
                out["reason"] = VerdictReason.ANTAGONISTIC_PREDICATE
                out["conflict_edges"].append((h, pr, t))
                return out

        return out
