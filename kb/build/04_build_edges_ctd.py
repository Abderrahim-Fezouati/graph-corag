from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

try:
    from .common import (
        ensure_files,
        normalize_surface,
        open_text_auto,
        read_entity_catalog,
        write_edges_csv,
        write_json,
    )
except ImportError:
    from kb.build.common import (
        ensure_files,
        normalize_surface,
        open_text_auto,
        read_entity_catalog,
        write_edges_csv,
        write_json,
    )


def _resolve_ctd(path_gz: Path) -> Path:
    if path_gz.exists():
        return path_gz
    alt = Path(str(path_gz).replace(".csv.gz", ".csv"))
    return alt


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 300000) -> dict:
    ctd = _resolve_ctd(raw_root / "CTD" / "CTD_chemicals_diseases.csv.gz")
    entity_catalog = out_dir / "entity_catalog.jsonl"
    ensure_files([ctd, entity_catalog])

    out_path = out_dir / "kg_edges.ctd.csv"
    report_path = out_dir / "stage_04_report.json"

    rows = read_entity_catalog(entity_catalog)
    chem_idx: dict[str, set[str]] = defaultdict(set)
    disease_idx: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        et = row.get("entity_type")
        for s in row.get("synonyms", []):
            n = normalize_surface(s)
            if et in {"drug", "chemical"}:
                chem_idx[n].add(row["kg_id"])
            elif et in {"disease"}:
                disease_idx[n].add(row["kg_id"])

    counts = {
        "ctd_rows": 0,
        "unmapped_chemical": 0,
        "unmapped_disease": 0,
        "written": 0,
    }

    seen = set()
    out_rows = []
    with open_text_auto(ctd) as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if progress_every and i % progress_every == 0:
                print(f"[{ctd.name}] read {i:,} lines")
            if not row:
                continue
            if row[0].startswith("#"):
                continue
            if len(row) < 6:
                continue
            if row[0] == "ChemicalName":
                continue

            counts["ctd_rows"] += 1
            chemical_name = row[0].strip()
            disease_name = row[3].strip()
            direct_evidence = row[4].strip().lower()
            inf_score = row[7].strip() if len(row) > 7 else ""

            chem_hits = chem_idx.get(normalize_surface(chemical_name), set())
            dis_hits = disease_idx.get(normalize_surface(disease_name), set())
            if not chem_hits:
                counts["unmapped_chemical"] += 1
                continue
            if not dis_hits:
                counts["unmapped_disease"] += 1
                continue

            rel = "TREATS" if "therapeutic" in direct_evidence else "ASSOCIATED_WITH"
            score = float(inf_score) if inf_score.replace(".", "", 1).isdigit() else 0.75
            for h in sorted(chem_hits):
                for t in sorted(dis_hits):
                    key = (h, rel, t)
                    if key in seen:
                        continue
                    seen.add(key)
                    out_rows.append(
                        {
                            "h": h,
                            "r": rel,
                            "t": t,
                            "source": "CTD",
                            "score": score,
                            "evidence": f"{chemical_name} -> {disease_name} ({direct_evidence})",
                        }
                    )

    counts["written"] = write_edges_csv(out_path, out_rows)
    report = {
        "stage": "04_build_edges_ctd",
        "version": version,
        "inputs": {"ctd_chemicals_diseases": str(ctd), "entity_catalog": str(entity_catalog)},
        "counts": counts,
        "outputs": {"kg_edges_ctd": str(out_path)},
    }
    write_json(report_path, report)
    return report


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True)
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--progress_every", type=int, default=300000)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    report = build(Path(args.raw_root), Path(args.out_dir), args.version, args.progress_every)
    print(
        f"[04] wrote {report['outputs']['kg_edges_ctd']} "
        f"({report['counts']['written']} edges)"
    )


if __name__ == "__main__":
    main()
