# -*- coding: utf-8 -*-
"""
Integrity checker for Type-Aware SapBERT index.
Validates:
  - FAISS index dimensions
  - Metadata rows.jsonl & cui_map.json
  - Combined vs per-type integrity
"""

import os
import json
import numpy as np
from pathlib import Path
import faiss
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--index_root", required=True)
args = ap.parse_args()

root = Path(args.index_root)


def check_file(path):
    if not path.exists():
        print(f"[ERROR] Missing: {path}")
        return False
    print(f"[OK] Found: {path}")
    return True


print("\n=== SapBERT Integrity Check ===\n")

# Check combined files
ok = True
ok &= check_file(root / "vectors.npy")
ok &= check_file(root / "cui_map.json")
ok &= check_file(root / "index.faiss")

if not ok:
    raise SystemExit("[FAIL] Missing combined index files.")

# Load vectors
vecs = np.load(root / "vectors.npy")
num_vecs, dim = vecs.shape
print(f"\n[OK] Loaded vectors.npy: {num_vecs} × {dim}")

# Load meta
meta = json.loads((root / "cui_map.json").read_text("utf-8"))
print(f"[OK] cui_map.json entries: {len(meta)}")

if len(meta) != num_vecs:
    raise SystemExit("[FAIL] cui_map.json length mismatch vectors.")

# Load combined FAISS
fa = faiss.read_index(str(root / "index.faiss"))
print(f"[OK] Loaded combined FAISS index (dim={fa.d})")

if fa.d != dim:
    raise SystemExit("[FAIL] Combined FAISS dimension mismatch.")

# Check per-type directories
for tdir in root.iterdir():
    if not tdir.is_dir():
        continue

    idx_path = tdir / "index.faiss"
    rows_path = tdir / "rows.jsonl"
    if not idx_path.exists():
        continue

    print(f"\n=== Checking type: {tdir.name} ===")
    check_file(idx_path)
    check_file(rows_path)

    # Load FAISS
    idx = faiss.read_index(str(idx_path))
    print(f"[OK] FAISS dim = {idx.d}")

    # Load rows
    rows = []
    with open(rows_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    print(f"[OK] rows.jsonl entries: {len(rows)}")

    if len(rows) != idx.ntotal:
        raise SystemExit("[FAIL] rows.jsonl entries do not match FAISS rows.")

print("\n[SUCCESS] SapBERT index integrity fully validated.\n")
