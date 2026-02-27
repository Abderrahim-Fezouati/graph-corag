from __future__ import annotations

import argparse
import importlib
from datetime import datetime, timezone
from pathlib import Path

try:
    from .common import sha256_file, write_json
except ImportError:
    from kb.build.common import sha256_file, write_json


STAGES = [
    "01_build_entity_catalog",
    "02_build_edges_umls",
    "03_build_edges_sider",
    "04_build_edges_ctd",
    "05_merge_edges",
    "06_build_umls_dict_and_overlay",
]


def _run_stage(mod_name: str, raw_root: Path, out_dir: Path, version: str, progress_every: int) -> dict:
    mod = importlib.import_module(f"kb.build.{mod_name}")
    return mod.build(raw_root=raw_root, out_dir=out_dir, version=version, progress_every=progress_every)


def build_all(
    raw_root: Path,
    out_root: Path,
    version: str,
    progress_every: int,
    model_name: str,
    batch_size: int,
    skip_sapbert: bool,
    local_files_only: bool,
) -> dict:
    version_dir = out_root / version
    version_dir.mkdir(parents=True, exist_ok=True)

    stage_reports = []
    for name in STAGES:
        print(f"[build_all] running {name}")
        stage_reports.append(_run_stage(name, raw_root, version_dir, version, progress_every))

    if not skip_sapbert:
        print("[build_all] running 07_build_sapbert_index")
        mod = importlib.import_module("kb.build.07_build_sapbert_index")
        stage_reports.append(
            mod.build(
                raw_root=raw_root,
                out_dir=version_dir,
                version=version,
                model_name=model_name,
                batch_size=batch_size,
                local_files_only=local_files_only,
            )
        )

    tracked_outputs = [
        version_dir / "entity_catalog.jsonl",
        version_dir / "kg_edges.umls.csv",
        version_dir / "kg_edges.sider.csv",
        version_dir / "kg_edges.ctd.csv",
        version_dir / "kg_edges.merged.csv",
        version_dir / "kg_edges.merged.plus.csv",
        version_dir / "umls_dict.txt",
        version_dir / "umls_dict.overlay.json",
    ]
    if not skip_sapbert:
        tracked_outputs.extend(
            [
                version_dir / "sapbert_index" / "index.faiss",
                version_dir / "sapbert_index" / "rows.jsonl",
                version_dir / "sapbert_index" / "manifest.json",
            ]
        )

    file_hashes = {}
    for p in tracked_outputs:
        if p.exists():
            file_hashes[str(p)] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}

    manifest = {
        "builder": "graphcorag_kb_build",
        "version": version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root),
        "output_dir": str(version_dir),
        "stages": stage_reports,
        "files": file_hashes,
    }
    write_json(version_dir / "build_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw_root", required=True, help="Root containing UMLS/ RxNorm/ Mesh/ DrugBank/ SIDER/ CTD")
    ap.add_argument(
        "--out_root",
        default="data_processed/graphcorag",
        help="Root output folder. Version folder is created under this path.",
    )
    ap.add_argument("--version", required=True, help="Build version label, e.g., v1")
    ap.add_argument("--progress_every", type=int, default=500000)
    ap.add_argument("--model_name", default="models/sapbert")
    ap.add_argument("--batch_size", type=int, default=64)
    ap.add_argument("--skip_sapbert", action="store_true")
    ap.add_argument("--local_files_only", action="store_true", default=False)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_all(
        raw_root=Path(args.raw_root),
        out_root=Path(args.out_root),
        version=args.version,
        progress_every=args.progress_every,
        model_name=args.model_name,
        batch_size=args.batch_size,
        skip_sapbert=args.skip_sapbert,
        local_files_only=args.local_files_only,
    )
    print(f"[build_all] done: {manifest['output_dir']}")
    print(f"[build_all] manifest: {Path(manifest['output_dir']) / 'build_manifest.json'}")


if __name__ == "__main__":
    main()
