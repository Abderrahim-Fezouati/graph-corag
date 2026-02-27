from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

try:
    from .common import (
        ensure_files,
        iter_tsv,
        normalize_surface,
        read_entity_catalog,
        write_edges_csv,
        write_json,
    )
except ImportError:
    from kb.build.common import (
        ensure_files,
        iter_tsv,
        normalize_surface,
        read_entity_catalog,
        write_edges_csv,
        write_json,
    )


def _resolve_file(preferred: Path, fallback: Path) -> Path:
    return preferred if preferred.exists() else fallback


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 500000) -> dict:
    drug_names = raw_root / "SIDER" / "drug_names.tsv"
    meddra = _resolve_file(
        raw_root / "SIDER" / "meddra_all_se.tsv",
        raw_root / "SIDER" / "meddra_all_se.tsv" / "meddra_all_se.tsv",
    )
    entity_catalog = out_dir / "entity_catalog.jsonl"
    ensure_files([drug_names, meddra, entity_catalog])

    out_path = out_dir / "kg_edges.sider.csv"
    report_path = out_dir / "stage_03_report.json"

    rows = read_entity_catalog(entity_catalog)
    drug_idx: dict[str, set[str]] = defaultdict(set)
    disease_idx: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        et = row.get("entity_type")
        for s in row.get("synonyms", []):
            n = normalize_surface(s)
            if et in {"drug", "chemical"}:
                drug_idx[n].add(row["kg_id"])
            elif et in {"disease"}:
                disease_idx[n].add(row["kg_id"])

    stitch_to_names: dict[str, str] = {}
    dn_rows = 0
    for fields in iter_tsv(drug_names, progress_every=progress_every):
        dn_rows += 1
        if len(fields) < 2:
            continue
        stitch_to_names[fields[0].strip()] = fields[1].strip()

    counts = {
        "drug_names_rows": dn_rows,
        "meddra_rows": 0,
        "unmapped_drug": 0,
        "unmapped_effect": 0,
        "written": 0,
    }

    seen = set()
    out_rows = []
    for fields in iter_tsv(meddra, progress_every=progress_every):
        counts["meddra_rows"] += 1
        if len(fields) < 6:
            continue
        stitch = fields[0].strip() or fields[1].strip()
        effect = fields[-1].strip()
        drug_name = stitch_to_names.get(stitch, "")
        if not (drug_name and effect):
            continue
        d_hits = drug_idx.get(normalize_surface(drug_name), set())
        e_hits = disease_idx.get(normalize_surface(effect), set())
        if not d_hits:
            counts["unmapped_drug"] += 1
            continue
        if not e_hits:
            counts["unmapped_effect"] += 1
            continue
        for d in sorted(d_hits):
            for e in sorted(e_hits):
                key = (d, "ADVERSE_EFFECT", e)
                if key in seen:
                    continue
                seen.add(key)
                out_rows.append(
                    {
                        "h": d,
                        "r": "ADVERSE_EFFECT",
                        "t": e,
                        "source": "SIDER",
                        "score": 0.9,
                        "evidence": f"{drug_name} -> {effect}",
                    }
                )

    counts["written"] = write_edges_csv(out_path, out_rows)
    report = {
        "stage": "03_build_edges_sider",
        "version": version,
        "inputs": {
            "drug_names": str(drug_names),
            "meddra_all_se": str(meddra),
            "entity_catalog": str(entity_catalog),
        },
        "counts": counts,
        "outputs": {"kg_edges_sider": str(out_path)},
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
        f"[03] wrote {report['outputs']['kg_edges_sider']} "
        f"({report['counts']['written']} edges)"
    )


if __name__ == "__main__":
    main()
