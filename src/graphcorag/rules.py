# -*- coding: utf-8 -*-
"""
hybridkg.rules
Rule-based candidate generator + small heuristics to fill common surfaces (e.g., pregnancy).
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple, Iterable, Set

_WORD_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


def _tok_lc(s: str) -> str:
    return (s or "").lower()


def _guess_type(cui: str) -> str:
    p = (cui or "").upper()
    for t in ("DRUG_", "CLASS_", "DISEASE_", "SYMPTOM_", "COND_"):
        if p.startswith(t):
            return t[:-1]
    return "UNKNOWN"


def extract_surfaces(surface2cui: Dict[str, str], text: str) -> List[Tuple[str, str]]:
    q = _tok_lc(text)
    keys = sorted(surface2cui.keys(), key=len, reverse=True)
    found: List[Tuple[str, str]] = []
    used_spans: List[Tuple[int, int]] = []
    for k in keys:
        start = 0
        while True:
            idx = q.find(k, start)
            if idx < 0:
                break
            span = (idx, idx + len(k))
            if any(not (span[1] <= s or span[0] >= e) for s, e in used_spans):
                start = idx + 1
                continue
            found.append((k, surface2cui[k]))
            used_spans.append(span)
            start = idx + len(k)
    found.sort(key=lambda kv: q.find(kv[0]))
    return found


# ── Updated keywords (added pregnancy-oriented cues) ───────────────────────────
_REL_KW = {
    "ADVERSE_EFFECT": [
        "adverse effect",
        "side effect",
        "associated with",
        "induces",
        "causes",
        "cough",
        "nausea",
        "toxicity",
    ],
    "CONTRAINDICATED_FOR": [
        "contraindicated",
        "avoid in",
        "not recommended for",
        "pregnancy",
        "pregnant",
        "teratogen",
        "teratogenic",
        "embryotoxic",
        "fetal",
        "safe in pregnancy",  # phrased as a question still triggers relation generation
    ],
    "TREATS": [
        "treat",
        "treats",
        "used for",
        "indication",
        "manage",
        "management of",
        "effective for",
    ],
    "FIRST_LINE": ["first line", "first-line"],
    "EFFECTIVE_IN": ["effective in", "efficacy in"],
    "REQUIRES_MONITORING": ["monitoring", "requires monitoring", "monitor"],
    "INTERACTS_WITH": ["interacts with", "interaction", "drug interaction"],
    "HAS_MEMBER": ["has member", "includes"],
    "MEMBER_OF": ["member of", "class of", "belongs to"],
}


def detect_relations(
    query_text: str, available: Iterable[str], surfaces: List[Tuple[str, str]]
) -> List[str]:
    q = _tok_lc(query_text)
    avail = {str(r).upper() for r in available}
    chosen: List[str] = []
    for rel, kws in _REL_KW.items():
        if rel not in avail:
            continue
        if any(kw in q for kw in kws):
            chosen.append(rel)

    types = {_cui: _guess_type(_cui) for (_, _cui) in surfaces}
    has_drug_or_class = any(t in ("DRUG", "CLASS") for t in types.values())
    has_symptom = any(t == "SYMPTOM" for t in types.values())
    has_disease = any(t == "DISEASE" for t in types.values())
    has_drug = any(t == "DRUG" for t in types.values())
    has_class = any(t == "CLASS" for t in types.values())

    def _add(rel):
        if rel in avail and rel not in chosen:
            chosen.append(rel)

    # Heuristic fallbacks
    if not chosen:
        if has_drug_or_class and has_symptom:
            _add("ADVERSE_EFFECT")
        if has_drug_or_class and has_disease:
            _add("TREATS")

    # If the text mentions pregnancy and a drug/class is present, suggest CONTRAINDICATED_FOR
    if ("pregnan" in q) and has_drug_or_class:
        _add("CONTRAINDICATED_FOR")

    if has_class and has_drug:
        _add("MEMBER_OF")
        _add("HAS_MEMBER")

    return chosen


def generate_candidates(
    surfaces: List[Tuple[str, str]], rels: List[str]
) -> List[Tuple[str, str, str]]:
    triples: List[Tuple[str, str, str]] = []
    by_type = {cui: _guess_type(cui) for (_, cui) in surfaces}
    for rel in rels:
        for i, (_, ci) in enumerate(surfaces):
            for j, (_, cj) in enumerate(surfaces):
                if i == j:
                    continue
                ti, tj = by_type[ci], by_type[cj]
                if rel == "TREATS":
                    if ti in ("DRUG", "CLASS") and tj == "DISEASE":
                        triples.append((ci, rel, cj))
                elif rel == "ADVERSE_EFFECT":
                    if ti in ("DRUG", "CLASS") and tj == "SYMPTOM":
                        triples.append((ci, rel, cj))
                elif rel == "CONTRAINDICATED_FOR":
                    if ti in ("DRUG", "CLASS") and tj in ("DISEASE", "COND"):
                        triples.append((ci, rel, cj))
                elif rel in ("FIRST_LINE", "EFFECTIVE_IN", "REQUIRES_MONITORING"):
                    if ti in ("DRUG", "CLASS") and tj in ("DISEASE", "COND", "SYMPTOM"):
                        triples.append((ci, rel, cj))
                elif rel == "INTERACTS_WITH":
                    if ti in ("DRUG", "CLASS") and tj in ("DRUG", "CLASS"):
                        triples.append((ci, rel, cj))
                elif rel == "MEMBER_OF":
                    if ti == "DRUG" and tj == "CLASS":
                        triples.append((ci, rel, cj))
                elif rel == "HAS_MEMBER":
                    if ti == "CLASS" and tj == "DRUG":
                        triples.append((ci, rel, cj))
    # Dedup
    seen: Set[Tuple[str, str, str]] = set()
    uniq: List[Tuple[str, str, str]] = []
    for tr in triples:
        if tr not in seen:
            seen.add(tr)
            uniq.append(tr)
    return uniq


def augment_surfaces(
    query_text: str, surfaces: List[Tuple[str, str]]
) -> List[Tuple[str, str]]:
    """
    Add common surfaces when the dict misses them (without touching data files).
    Currently: pregnancy → COND_PREGNANCY (runner will resolve to KG label 'PREGNANCY').
    """
    q = _tok_lc(query_text)
    have = {s for (s, _) in surfaces}
    extras: List[Tuple[str, str]] = []
    if ("pregnan" in q) and ("pregnancy" not in have):
        extras.append(("pregnancy", "COND_PREGNANCY"))
    return surfaces + extras


# CLI (optional) unchanged…
if __name__ == "__main__":
    import argparse, json, sys
    from hybridkg.kg_loader import KG

    ap = argparse.ArgumentParser(description="rules smoke test")
    ap.add_argument("--kg", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--query", required=True)
    args = ap.parse_args()

    kg = KG(args.kg, dict_path=args.dict)
    surfaces = extract_surfaces(kg.surface2cui, args.query)
    surfaces = augment_surfaces(args.query, surfaces)
    avail_rels = {r for _, r, _ in kg.edge_set}
    rels = detect_relations(args.query, avail_rels, surfaces)
    cands = generate_candidates(surfaces, rels)
    print("surfaces:", surfaces)
    print("rels:", rels)
    print("candidates:", cands[:25], ("..." if len(cands) > 25 else ""))
