from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .common import ensure_files, iter_rrf, write_json
except ImportError:
    from kb.build.common import ensure_files, iter_rrf, write_json


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 0) -> dict:
    entity_catalog = out_dir / "entity_catalog.jsonl"
    mrconso = raw_root / "UMLS" / "MRCONSO.RRF"
    ensure_files([entity_catalog])
    ensure_files([mrconso])

    dict_path = out_dir / "umls_dict.txt"
    overlay_path = out_dir / "umls_dict.overlay.json"
    report_path = out_dir / "stage_06_report.json"

    kg_to_cui: dict[str, str] = {}
    kg_to_catalog_syns: dict[str, set[str]] = {}
    kg_to_canonical: dict[str, str] = {}
    rows = 0
    with entity_catalog.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows += 1
            row = json.loads(line)
            kg_id = row["kg_id"]
            cui = (row.get("cui") or "").strip().upper()
            if not cui:
                continue
            syns = {
                s.strip()
                for s in row.get("synonyms", [])
                if isinstance(s, str) and s.strip()
            }
            canonical = (row.get("canonical_name") or "").strip()
            kg_to_cui[kg_id] = cui
            kg_to_catalog_syns[kg_id] = syns
            kg_to_canonical[kg_id] = canonical

    cui_to_kg: dict[str, str] = {cui: kg for kg, cui in kg_to_cui.items()}
    base_sets: dict[str, set[str]] = {kg: set() for kg in kg_to_cui}

    mrconso_rows = 0
    mrconso_english = 0
    for fields in iter_rrf(mrconso, progress_every=progress_every):
        mrconso_rows += 1
        if len(fields) < 15:
            continue
        cui = fields[0].strip().upper()
        lat = fields[1].strip().upper()
        text = fields[14].strip()
        if not cui or not text or lat != "ENG":
            continue
        kg_id = cui_to_kg.get(cui)
        if not kg_id:
            continue
        base_sets[kg_id].add(text)
        mrconso_english += 1

    for kg_id, canonical in kg_to_canonical.items():
        if canonical:
            base_sets.setdefault(kg_id, set()).add(canonical)

    base_dict: dict[str, list[str]] = {}
    overlay_dict: dict[str, list[str]] = {}
    total_base_synonyms = 0
    total_overlay_synonyms = 0

    for kg_id in sorted(base_sets):
        base_sorted = sorted(base_sets[kg_id], key=str.casefold)
        if base_sorted:
            base_dict[kg_id] = base_sorted
            total_base_synonyms += len(base_sorted)
        catalog_syns = kg_to_catalog_syns.get(kg_id, set())
        extra = sorted((catalog_syns - set(base_sorted)), key=str.casefold)
        if extra:
            overlay_dict[kg_id] = extra
            total_overlay_synonyms += len(extra)

    dict_path.write_text(json.dumps(base_dict, ensure_ascii=False, indent=2), encoding="utf-8")
    overlay_path.write_text(
        json.dumps(overlay_dict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = {
        "stage": "06_build_umls_dict_and_overlay",
        "version": version,
        "inputs": {"entity_catalog": str(entity_catalog), "mrconso": str(mrconso)},
        "counts": {
            "entities_rows_seen": rows,
            "entities_with_cui": len(kg_to_cui),
            "mrconso_rows_seen": mrconso_rows,
            "mrconso_english_rows_mapped": mrconso_english,
            "total_base_synonyms": total_base_synonyms,
            "total_overlay_synonyms": total_overlay_synonyms,
            "overlay_keys": len(overlay_dict),
        },
        "outputs": {
            "umls_dict": str(dict_path),
            "umls_dict_overlay": str(overlay_path),
        },
    }
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--progress_every", type=int, default=0)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    report = build(Path(args.raw_root), Path(args.out_dir), args.version, args.progress_every)
    print(
        f"[06] wrote {report['outputs']['umls_dict']} "
        f"({report['counts']['entities_with_cui']} entities)"
    )


if __name__ == "__main__":
    main()
