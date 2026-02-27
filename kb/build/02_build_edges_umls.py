from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .common import (
        ensure_files,
        iter_rrf,
        load_type_map_from_catalog,
        write_edges_csv,
        write_json,
    )
except ImportError:
    from kb.build.common import (
        ensure_files,
        iter_rrf,
        load_type_map_from_catalog,
        write_edges_csv,
        write_json,
    )


def _is_drug_like(t: str) -> bool:
    return t in {"drug", "chemical"}


def _is_disease_like(t: str) -> bool:
    return t in {"disease"}


def map_relation(rel: str, rela: str) -> str | None:
    r = (rela or rel or "").strip().lower()
    if r in {"may_treat", "treats", "treated_by", "treatment_of"}:
        return "TREATS"
    if r in {"causes", "induces", "adverse_effect_of"}:
        return "ADVERSE_EFFECT"
    if r in {"contraindicated_with_disease", "contraindicated_with"}:
        return "CONTRAINDICATED_FOR"
    if r in {"interacts_with", "ddi", "drug_interaction"}:
        return "INTERACTS_WITH"
    if (rel or "").strip().upper() in {"RO", "RQ"}:
        return "ASSOCIATED_WITH"
    return None


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 500000) -> dict:
    mrrel = raw_root / "UMLS" / "MRREL.RRF"
    entity_catalog = out_dir / "entity_catalog.jsonl"
    ensure_files([mrrel, entity_catalog])

    out_path = out_dir / "kg_edges.umls.csv"
    report_path = out_dir / "stage_02_report.json"

    cui_to_kg, kg_to_type = load_type_map_from_catalog(entity_catalog)
    counts = {
        "mrrel_rows": 0,
        "mapped_relation": 0,
        "filtered_relation": 0,
        "unmapped_cui": 0,
        "filtered_semantic_type": 0,
        "written": 0,
    }

    seen = set()
    rows = []
    for fields in iter_rrf(mrrel, progress_every=progress_every):
        counts["mrrel_rows"] += 1
        if len(fields) < 11:
            continue
        cui1 = fields[0].strip().upper()
        rel = fields[3].strip().upper()
        cui2 = fields[4].strip().upper()
        rela = fields[7].strip()
        sab = fields[10].strip()

        mapped = map_relation(rel, rela)
        if not mapped:
            counts["filtered_relation"] += 1
            continue
        counts["mapped_relation"] += 1

        h = cui_to_kg.get(cui1)
        t = cui_to_kg.get(cui2)
        if not (h and t):
            counts["unmapped_cui"] += 1
            continue

        ht = kg_to_type.get(h, "entity")
        tt = kg_to_type.get(t, "entity")
        if mapped in {"TREATS", "ADVERSE_EFFECT", "CONTRAINDICATED_FOR"}:
            if not (_is_drug_like(ht) and _is_disease_like(tt)):
                counts["filtered_semantic_type"] += 1
                continue
        if mapped == "INTERACTS_WITH":
            if not (_is_drug_like(ht) and _is_drug_like(tt)):
                counts["filtered_semantic_type"] += 1
                continue

        key = (h, mapped, t)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "h": h,
                "r": mapped,
                "t": t,
                "source": "UMLS",
                "score": 1.0,
                "evidence": f"{sab}:{rela or rel}",
            }
        )

    counts["written"] = write_edges_csv(out_path, rows)
    report = {
        "stage": "02_build_edges_umls",
        "version": version,
        "inputs": {"MRREL": str(mrrel), "entity_catalog": str(entity_catalog)},
        "counts": counts,
        "outputs": {"kg_edges_umls": str(out_path)},
    }
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--progress_every", type=int, default=500000)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    report = build(Path(args.raw_root), Path(args.out_dir), args.version, args.progress_every)
    print(
        f"[02] wrote {report['outputs']['kg_edges_umls']} "
        f"({report['counts']['written']} edges)"
    )


if __name__ == "__main__":
    main()
