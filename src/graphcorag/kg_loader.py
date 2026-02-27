# -*- coding: utf-8 -*-
"""
hybridkg.kg_loader
Clean KG CSV loader with normalization, has_edge(), neighbors().
"""
from __future__ import annotations
import csv, io, json, os
from typing import Dict, Iterable, List, Optional, Set, Tuple


def _norm_cui(x: Optional[str]) -> str:
    return "" if x is None else str(x).strip().lower()


def _norm_rel(x: Optional[str]) -> str:
    return "" if x is None else str(x).strip().upper()


class KG:
    def __init__(
        self,
        kg_csv_path: str,
        dict_path: Optional[str] = None,
        overlay_path: Optional[str] = None,
    ):
        self.edge_set: Set[Tuple[str, str, str]] = set()
        self.out: Dict[Tuple[str, str], Set[str]] = {}

        # Load edges
        with io.open(kg_csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("KG CSV has no header.")
            # Tolerant header aliases
            alias = {h.lower(): h for h in reader.fieldnames}
            hcol = alias.get("head") or alias.get("h") or "head"
            rcol = alias.get("relation") or alias.get("rel") or "relation"
            tcol = alias.get("tail") or alias.get("t") or "tail"
            for row in reader:
                h = _norm_cui(row.get(hcol))
                r = _norm_rel(row.get(rcol))
                t = _norm_cui(row.get(tcol))
                if not (h and r and t):
                    continue
                self.edge_set.add((h, r, t))
                self.out.setdefault((h, r), set()).add(t)

        print(
            f"[KG] Loaded {len(self.edge_set)} edges from: {os.path.basename(kg_csv_path)}. Total unique now: {len(self.edge_set)}"
        )

        # Optional dictionary (JSON: CUI -> [surfaces])
        self.surface_dict: Dict[str, List[str]] = {}
        if dict_path and os.path.exists(dict_path):
            try:
                with io.open(dict_path, "r", encoding="utf-8-sig") as f:
                    self.surface_dict = json.load(f)
            except Exception:
                self.surface_dict = {}
        print(f"[KG] Loaded dictionary entries: {len(self.surface_dict)}")

        # Optional overlay
        self.overlay = None
        if overlay_path and os.path.exists(overlay_path):
            try:
                with io.open(overlay_path, "r", encoding="utf-8-sig") as f:
                    self.overlay = json.load(f)
            except Exception:
                self.overlay = None

    def has_edge(self, head_cui: str, relation: str, tail_cui: str) -> bool:
        return (
            _norm_cui(head_cui),
            _norm_rel(relation),
            _norm_cui(tail_cui),
        ) in self.edge_set

    def neighbors(self, head_cui: str, relation: str) -> List[str]:
        """Return sorted list of tails T with (head, relation, T) in KG."""
        h = _norm_cui(head_cui)
        r = _norm_rel(relation)
        return sorted(self.out.get((h, r), []))

    # Convenience for quick checks
    def surface_to_cui(self, surface: str) -> Optional[str]:
        s = (surface or "").strip().lower()
        for cui, forms in self.surface_dict.items():
            for form in forms:
                if (form or "").lower() == s:
                    return cui
        return None


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--kg", required=True)
    ap.add_argument("--dict", default=None)
    ap.add_argument("--overlay", default=None)
    ap.add_argument("--check", default=None, help="HEAD,REL,TAIL")
    ap.add_argument("--surface", default=None)
    args = ap.parse_args()

    kg = KG(args.kg, dict_path=args.dict, overlay_path=args.overlay)

    if args.surface:
        print(f"surface_to_cui('{args.surface}') -> {kg.surface_to_cui(args.surface)}")

    if args.check:
        parts = [p.strip() for p in args.check.split(",")]
        if len(parts) != 3:
            print("Invalid --check (expected HEAD,REL,TAIL)")
            raise SystemExit(2)
        h, r, t = parts
        print("has_edge:", kg.has_edge(h, r, t))
