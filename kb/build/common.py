from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Iterator


def ensure_files(paths: Iterable[Path]) -> None:
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required input files:\n" + "\n".join(missing))


def open_text_auto(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="ignore", newline="")
    return path.open("r", encoding="utf-8", errors="ignore", newline="")


def iter_rrf(path: Path, progress_every: int = 500000) -> Iterator[list[str]]:
    with open_text_auto(path) as f:
        for i, line in enumerate(f, start=1):
            if progress_every and i % progress_every == 0:
                print(f"[{path.name}] read {i:,} lines")
            yield line.rstrip("\n").split("|")


def iter_tsv(path: Path, progress_every: int = 500000) -> Iterator[list[str]]:
    with open_text_auto(path) as f:
        for i, line in enumerate(f, start=1):
            if progress_every and i % progress_every == 0:
                print(f"[{path.name}] read {i:,} lines")
            yield line.rstrip("\n").split("\t")


def slugify(text: str) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip().lower())
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def normalize_surface(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_entity_catalog(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_edges_csv(path: Path, rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["h", "r", "t", "source", "score", "evidence"]
        )
        w.writeheader()
        for row in rows:
            w.writerow(row)
            count += 1
    return count


def load_type_map_from_catalog(entity_catalog: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Returns (cui_to_kgid, kgid_to_type)."""
    cui_to_kgid: dict[str, str] = {}
    kgid_to_type: dict[str, str] = {}
    with entity_catalog.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            kgid = row["kg_id"]
            et = row.get("entity_type", "unknown")
            kgid_to_type[kgid] = et
            cui = (row.get("cui") or "").upper()
            if cui:
                cui_to_kgid[cui] = kgid
    return cui_to_kgid, kgid_to_type

