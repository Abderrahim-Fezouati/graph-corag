# -*- coding: utf-8 -*-
"""
Pre-analyze raw queries (qid,text) -> enrich with surfaces, relations, and KG candidates.
Safe to run even if advanced rules aren't present: falls back to text-only.
"""
import json, argparse
from typing import List, Dict, Any


def load_jsonl(p: str) -> List[Dict[str, Any]]:
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def write_jsonl(p: str, rows: List[Dict[str, Any]]) -> None:
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def try_import_rules():
    try:
        from graphcorag.rules import (
            extract_surfaces,
            augment_surfaces,
            detect_relations,
            generate_candidates,
        )

        return extract_surfaces, augment_surfaces, detect_relations, generate_candidates
    except Exception:
        return None, None, None, None


def try_load_kg(kg_path: str):
    try:
        from graphcorag.kg_loader import KG

        return KG(kg_path)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_raw", required=True)
    ap.add_argument("--out_enriched", required=True)
    ap.add_argument("--dict", required=True)
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--kg", required=True)
    ap.add_argument("--schema", required=True)
    args = ap.parse_args()

    rows = load_jsonl(args.in_raw)
    extract_surfaces, augment_surfaces, detect_relations, generate_candidates = (
        try_import_rules()
    )
    kg = try_load_kg(args.kg)

    # relation schema (optional)
    try:
        with open(args.schema, "r", encoding="utf-8") as f:
            relation_schema = json.load(f)
    except Exception:
        relation_schema = {}

    enriched = []
    for ex in rows:
        qtext = ex.get("text") or ex.get("question") or ""
        out = dict(ex)  # keep qid,text
        out["extracted_surfaces"] = []
        out["detected_relations"] = []
        out["candidates"] = []

        if all(
            [extract_surfaces, augment_surfaces, detect_relations, generate_candidates]
        ):
            try:
                surfaces = extract_surfaces(args.dict, args.overlay, qtext)
                surfaces = augment_surfaces(surfaces, qtext)
                out["extracted_surfaces"] = surfaces

                rels = detect_relations(qtext, relation_schema, surfaces) or []
                out["detected_relations"] = rels

                cand = generate_candidates(surfaces, rels) or []
                out["candidates"] = cand

                if kg and cand:
                    verdicts, hit = [], 0
                    for h, r, t in cand:
                        present = bool(kg.has_edge(h, r, t))
                        verdicts.append({"edge": [h, r, t], "present": present})
                        hit += int(present)
                    out["kg_verdicts_preview"] = verdicts
                    out["coverage_preview"] = hit / max(1, len(cand))
            except Exception:
                pass

        enriched.append(out)

    write_jsonl(args.out_enriched, enriched)


if __name__ == "__main__":
    main()
