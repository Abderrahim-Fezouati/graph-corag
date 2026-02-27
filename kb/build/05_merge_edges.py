from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:
    from .common import ensure_files, write_json
except ImportError:
    from kb.build.common import ensure_files, write_json


def _read_edges(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        alias = {h.lower(): h for h in (r.fieldnames or [])}
        hcol = alias.get("h") or alias.get("head")
        rcol = alias.get("r") or alias.get("relation")
        tcol = alias.get("t") or alias.get("tail")
        scol = alias.get("source")
        pcol = alias.get("score")
        ecol = alias.get("evidence")
        for row in r:
            h = (row.get(hcol) or "").strip()
            rel = (row.get(rcol) or "").strip()
            t = (row.get(tcol) or "").strip()
            if not (h and rel and t):
                continue
            src = (row.get(scol) or "").strip() if scol else ""
            score_raw = (row.get(pcol) or "").strip() if pcol else ""
            try:
                score = float(score_raw)
            except Exception:
                score = 1.0
            ev = (row.get(ecol) or "").strip() if ecol else ""
            yield h, rel, t, src, score, ev


def build(raw_root: Path, out_dir: Path, version: str, progress_every: int = 0) -> dict:
    _ = raw_root
    p1 = out_dir / "kg_edges.umls.csv"
    p2 = out_dir / "kg_edges.sider.csv"
    p3 = out_dir / "kg_edges.ctd.csv"
    ensure_files([p1, p2, p3])

    out_path = out_dir / "kg_edges.merged.csv"
    out_plus = out_dir / "kg_edges.merged.plus.csv"
    report_path = out_dir / "stage_05_report.json"

    merged: dict[tuple[str, str, str], dict] = {}
    seen_rows = 0
    for p in (p1, p2, p3):
        for h, rel, t, src, score, ev in _read_edges(p):
            seen_rows += 1
            key = (h, rel, t)
            if key not in merged:
                merged[key] = {
                    "h": h,
                    "r": rel,
                    "t": t,
                    "source": set([src]) if src else set(),
                    "score": score,
                    "evidence": set([ev]) if ev else set(),
                }
            else:
                merged[key]["source"].add(src)
                merged[key]["evidence"].add(ev)
                if score > merged[key]["score"]:
                    merged[key]["score"] = score

    rows = []
    for key in sorted(merged):
        row = merged[key]
        rows.append(
            {
                "h": row["h"],
                "r": row["r"],
                "t": row["t"],
                "source": "|".join(sorted(x for x in row["source"] if x)),
                "score": f"{row['score']:.4f}",
                "evidence": "|".join(sorted(x for x in row["evidence"] if x)),
            }
        )

    for out in (out_path, out_plus):
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "head",
                    "relation",
                    "tail",
                    "source",
                    "score",
                    "evidence",
                ],
            )
            w.writeheader()
            for row in rows:
                w.writerow(
                    {
                        "head": row["h"],
                        "relation": row["r"],
                        "tail": row["t"],
                        "source": row["source"],
                        "score": row["score"],
                        "evidence": row["evidence"],
                    }
                )

    report = {
        "stage": "05_merge_edges",
        "version": version,
        "inputs": {
            "umls": str(p1),
            "sider": str(p2),
            "ctd": str(p3),
        },
        "counts": {"rows_seen": seen_rows, "rows_written": len(rows)},
        "outputs": {
            "kg_edges_merged": str(out_path),
            "kg_edges_merged_plus": str(out_plus),
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
        f"[05] wrote {report['outputs']['kg_edges_merged']} "
        f"({report['counts']['rows_written']} edges)"
    )


if __name__ == "__main__":
    main()
