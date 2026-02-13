# -*- coding: utf-8 -*-
"""
kg_validation.kg_loader

Read-only biomedical KG loader for validation.
- CSV-based (reproducible, review-safe)
- BOM-safe (utf-8-sig)
- Normalized CUIs and predicates
- O(1) edge lookup
"""

from __future__ import annotations
import csv
import io
import os
from typing import Dict, List, Optional, Set, Tuple


# -----------------------------
# Normalization helpers
# -----------------------------

def _norm_cui(x: Optional[str]) -> str:
    return ("" if x is None else str(x).strip().lower())


def _norm_rel(x: Optional[str]) -> str:
    return ("" if x is None else str(x).strip().upper())


# -----------------------------
# KG Loader (Read-Only)
# -----------------------------

class KGLoader:
    """
    Read-only KG loader for validation purposes.

    Loads triples:
        (head_cui, predicate, tail_cui)

    Provides:
        - Exact edge existence checks
        - Fast neighborhood queries
        - Predicate inspection
    """

    def __init__(self, kg_csv_path: str):
        self.kg_csv_path = kg_csv_path

        # Core storage
        self.edge_set: Set[Tuple[str, str, str]] = set()
        self.hp_to_tails: Dict[Tuple[str, str], Set[str]] = {}
        self.ht_to_preds: Dict[Tuple[str, str], Set[str]] = {}
        self.h_to_edges: Dict[str, List[Tuple[str, str]]] = {}

        # Metadata
        self.nodes: Set[str] = set()
        self.edges: int = 0
        self.kg_version: str = os.path.basename(kg_csv_path)

        self._load()

    # -----------------------------
    # Load & index KG
    # -----------------------------

    def _load(self):
        with io.open(self.kg_csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("KG CSV has no header.")

            # Header aliasing (robust but explicit)
            alias = {h.lower(): h for h in reader.fieldnames}
            hcol = alias.get("head")
            rcol = alias.get("relation")
            tcol = alias.get("tail")

            if not (hcol and rcol and tcol):
                raise ValueError(
                    f"Unexpected KG schema: {reader.fieldnames}, expected head/relation/tail"
                )

            for row in reader:
                h = _norm_cui(row.get(hcol))
                r = _norm_rel(row.get(rcol))
                t = _norm_cui(row.get(tcol))

                if not (h and r and t):
                    continue

                self.edge_set.add((h, r, t))

                self.hp_to_tails.setdefault((h, r), set()).add(t)
                self.ht_to_preds.setdefault((h, t), set()).add(r)
                self.h_to_edges.setdefault(h, []).append((r, t))

                self.nodes.add(h)
                self.nodes.add(t)
                self.edges += 1

        print(
            f"[INFO] KG loaded: nodes={len(self.nodes)}, edges={self.edges}, "
            f"file={self.kg_version}"
        )

    # -----------------------------
    # Query helpers (read-only)
    # -----------------------------

    def has_edge(self, head: str, predicate: str, tail: str) -> bool:
        return (
            _norm_cui(head),
            _norm_rel(predicate),
            _norm_cui(tail),
        ) in self.edge_set

    def tails(self, head: str, predicate: str) -> List[str]:
        return sorted(
            self.hp_to_tails.get((_norm_cui(head), _norm_rel(predicate)), [])
        )

    def predicates_between(self, head: str, tail: str) -> List[str]:
        return sorted(
            self.ht_to_preds.get((_norm_cui(head), _norm_cui(tail)), [])
        )

    def outgoing(self, head: str) -> List[Tuple[str, str]]:
        return self.h_to_edges.get(_norm_cui(head), [])


# -----------------------------
# CLI sanity check
# -----------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--kg", required=True)
    ap.add_argument("--check", default=None, help="HEAD,REL,TAIL")
    args = ap.parse_args()

    kg = KGLoader(args.kg)

    if args.check:
        h, r, t = [x.strip() for x in args.check.split(",")]
        print("has_edge:", kg.has_edge(h, r, t))
