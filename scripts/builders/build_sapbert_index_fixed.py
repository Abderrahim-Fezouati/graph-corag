# -*- coding: utf-8 -*-
"""
Professional Type-Aware SapBERT Index Builder
Compatible with:
  - SapBERTLinker (combined index)
  - TypeAwareLinker (per-type FAISS indexes)

Enterprise-grade, safe, validated.
"""

import os
import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
import faiss


# -------------------------------------------------------
# 1. Utilities
# -------------------------------------------------------


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(s: str):
    """Simple lowercase/strip normalization."""
    return " ".join((s or "").lower().strip().split())


# -------------------------------------------------------
# 2. Arguments
# -------------------------------------------------------

ap = argparse.ArgumentParser()
ap.add_argument("--kg", required=True, help="KG triples (h,rel,t) CSV file")
ap.add_argument(
    "--dict", required=True, help="umls_dict.txt (CUI → [surfaces]) JSON format"
)
ap.add_argument(
    "--overlay", required=True, help="overlay JSON dictionary of extra synonyms"
)
ap.add_argument("--out_dir", required=True, help="Target directory for SapBERT indices")
ap.add_argument(
    "--model",
    default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
    help="SapBERT model",
)
ap.add_argument("--batch", type=int, default=512)
args = ap.parse_args()

os.makedirs(args.out_dir, exist_ok=True)


# -------------------------------------------------------
# 3. Load KG nodes and infer types (Drug, Disease)
# -------------------------------------------------------

kg_types = {}  # kg_id → type ("Drug" or "Disease")
kg_nodes = set()

with open(args.kg, "r", encoding="utf-8", newline="") as f:
    r = csv.reader(f)
    rows = list(r)

    # Skip header if present
    if rows and rows[0] and rows[0][0].lower() in ("h", "head", "source"):
        rows = rows[1:]

    for h, rel, t in rows:
        h = h.strip()
        t = t.strip()
        if h:
            kg_nodes.add(h)
        if t:
            kg_nodes.add(t)

# Infer type from prefix: "drug_xxx" -> Drug, "disease_xxx" -> Disease
for cui in kg_nodes:
    if cui.lower().startswith("drug_"):
        kg_types[cui] = "Drug"
    elif cui.lower().startswith("disease_"):
        kg_types[cui] = "Disease"

# Filter to known types only
typed_nodes = {cui: tp for cui, tp in kg_types.items() if tp in ("Drug", "Disease")}

if not typed_nodes:
    raise SystemExit("No typed KG nodes detected. Check KG formatting.")


# -------------------------------------------------------
# 4. Load dictionary + overlay
# -------------------------------------------------------

base_dict = load_json(args.dict)
overlay = load_json(args.overlay)

# Merge overlay synonyms into base_dict
for cui, syns in overlay.items():
    base = base_dict.setdefault(cui, [])
    seen_norm = {normalize_text(s) for s in base}
    for s in syns:
        ns = normalize_text(s)
        if ns and ns not in seen_norm:
            base.append(s)
            seen_norm.add(ns)


# -------------------------------------------------------
# 5. Build (kg_id → unique normalized surfaces)
# -------------------------------------------------------

node2surfs = {}
for cui, tp in typed_nodes.items():
    surfs = base_dict.get(cui, [])
    clean = []

    for s in surfs:
        ns = normalize_text(s)
        if ns and len(ns) >= 3:
            clean.append(ns)

    if clean:
        node2surfs[cui] = sorted(set(clean))


# -------------------------------------------------------
# 6. Flatten surfaces for encoding
# -------------------------------------------------------

pairs = []  # (kg_id, surface, type)
texts = []  # surfaces to encode

for cui, surfs in node2surfs.items():
    t = kg_types[cui]
    for s in surfs:
        pairs.append((cui, s, t))
        texts.append(s)

if not texts:
    raise SystemExit("No surfaces found to encode. Check dictionary coverage.")


# -------------------------------------------------------
# 7. Load SapBERT and encode
# -------------------------------------------------------

device = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(args.model, use_fast=True)
mdl = AutoModel.from_pretrained(args.model).to(device).eval()


def encode_batch(batch_texts):
    """Encode a batch of texts into L2-normalized SapBERT embeddings."""
    with torch.no_grad():
        x = tok(
            batch_texts,
            padding=True,
            truncation=True,
            max_length=64,
            return_tensors="pt",
        ).to(device)
        out = mdl(**x).last_hidden_state  # [B, L, H]
        mask = x["attention_mask"].unsqueeze(-1)  # [B, L, 1]
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return pooled.cpu().numpy().astype("float32")


embs_list = []
for i in range(0, len(texts), args.batch):
    batch = texts[i : i + args.batch]
    emb = encode_batch(batch)
    embs_list.append(emb)

embs = np.vstack(embs_list).astype("float32")

if embs.shape[0] != len(pairs):
    raise SystemExit("Embedding count mismatch.")


# -------------------------------------------------------
# 8. Build combined FAISS index
# -------------------------------------------------------

dim = embs.shape[1]
index_combined = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
index_combined.hnsw.efConstruction = 40
index_combined.add(embs)

# Write combined index + metadata
faiss.write_index(index_combined, str(Path(args.out_dir, "index.faiss")))
np.save(str(Path(args.out_dir, "vectors.npy")), embs)

cui_map = [{"cui": cui, "name": surface} for (cui, surface, _) in pairs]
with open(Path(args.out_dir, "cui_map.json"), "w", encoding="utf-8") as f:
    json.dump(cui_map, f, ensure_ascii=False, indent=2)


# -------------------------------------------------------
# 9. Build per-type FAISS indexes (Drug, Disease)
# -------------------------------------------------------

per_type = defaultdict(list)
for (cui, surface, tp), vec in zip(pairs, embs):
    per_type[tp].append((cui, surface, vec))

for tp, entries in per_type.items():
    tp_dir = Path(args.out_dir, tp)
    tp_dir.mkdir(parents=True, exist_ok=True)

    # Build FAISS for this type
    vecs = np.vstack([v for (_, _, v) in entries])
    idx = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
    idx.hnsw.efConstruction = 40
    idx.add(vecs)

    faiss.write_index(idx, str(tp_dir / "index.faiss"))

    # Write rows.jsonl
    with open(tp_dir / "rows.jsonl", "w", encoding="utf-8") as f:
        for cui, surface, _ in entries:
            json.dump({"kg_id": cui, "text": surface}, f, ensure_ascii=False)
            f.write("\n")


# -------------------------------------------------------
# 10. Final Summary
# -------------------------------------------------------

print("\n[SUCCESS] Type-Aware SapBERT Index Built")
print(f"  Total surfaces encoded: {len(pairs)}")
print(f"  Output directory: {args.out_dir}")

for tp, entries in per_type.items():
    print(f"  {tp}: {len(entries)} entries")
