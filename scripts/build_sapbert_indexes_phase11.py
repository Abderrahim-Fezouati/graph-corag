# -*- coding: utf-8 -*-
"""
Phase 1.1 — Type-Aware SapBERT Index Construction

Builds FAISS indexes for KG-anchored entities using SapBERT.
Indexes are separated by entity type (drug / disease).
Each indexed row corresponds to a (kg_id, surface, sources) triple.

Design choices (FROZEN):
- SapBERT encoder (offline)
- [CLS] embedding from last hidden layer
- L2-normalized vectors
- FAISS IndexFlatIP (exact cosine similarity)
- Surface-level indexing (not entity-level)
"""

import os
import json
from collections import defaultdict

import numpy as np
import faiss
import torch
from transformers import AutoTokenizer, AutoModel

# ===============================
# Paths & config
# ===============================
ENTITY_CATALOG = "data/processed/entities/entity_catalog.cleaned.jsonl"
SAPHBERT_MODEL_PATH = "models/sapbert"  # adjust ONLY if your model is elsewhere
OUTPUT_ROOT = "indices/sapbert"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH_SIZE = 64
MAX_LENGTH = 64  # Surface forms are short biomedical names; 64 is sufficient

# ===============================
# Load SapBERT (offline only)
# ===============================
tokenizer = AutoTokenizer.from_pretrained(SAPHBERT_MODEL_PATH, local_files_only=True)

model = AutoModel.from_pretrained(SAPHBERT_MODEL_PATH, local_files_only=True).to(DEVICE)

model.eval()

# ===============================
# Load entity catalog & prepare rows
# ===============================
type_to_rows = {"drug": [], "disease": []}

seen_keys = set()  # (entity_type, kg_id, surface)

with open(ENTITY_CATALOG, encoding="utf-8") as f:
    for line in f:
        entry = json.loads(line)

        entity_type = entry["entity_type"].lower()
        if entity_type not in type_to_rows:
            continue

        kg_id = entry["kg_id"]
        canonical = entry["canonical_name"]
        external_sources = entry.get("sources", [])

        for surface in entry["synonyms"]:
            key = (entity_type, kg_id, surface)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            if surface == canonical:
                sources = ["canonical"]
            else:
                # Preserve real provenance (RxNorm / DrugBank / MeSH)
                sources = external_sources if external_sources else []

            type_to_rows[entity_type].append(
                {"kg_id": kg_id, "surface": surface, "sources": sources}
            )

# ===============================
# Report pre-index statistics
# ===============================
print("\n=== SapBERT Index Preparation Stats ===")
for etype, rows in type_to_rows.items():
    kg_ids = {r["kg_id"] for r in rows}
    surfaces = {r["surface"] for r in rows}
    print(f"{etype.upper()}:")
    print(f"  Entities: {len(kg_ids)}")
    print(f"  Unique surfaces: {len(surfaces)}")
    print(f"  Total rows: {len(rows)}")


# ===============================
# Embedding function ([CLS] + L2)
# ===============================
def embed_surfaces(surface_list):
    vectors = []

    with torch.no_grad():
        for i in range(0, len(surface_list), BATCH_SIZE):
            batch = surface_list[i : i + BATCH_SIZE]

            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )

            encoded = {k: v.to(DEVICE) for k, v in encoded.items()}
            outputs = model(**encoded)

            cls_vecs = outputs.last_hidden_state[:, 0, :]
            cls_vecs = torch.nn.functional.normalize(cls_vecs, p=2, dim=1)

            vectors.append(cls_vecs.cpu().numpy())

    return np.vstack(vectors)


# ===============================
# Build FAISS indexes (per type)
# ===============================
for entity_type, rows in type_to_rows.items():
    if not rows:
        continue

    print(f"\nIndexing {entity_type} surfaces...")

    surfaces = [r["surface"] for r in rows]
    embeddings = embed_surfaces(surfaces)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    out_dir = os.path.join(OUTPUT_ROOT, entity_type.capitalize())
    os.makedirs(out_dir, exist_ok=True)

    faiss.write_index(index, os.path.join(out_dir, "index.faiss"))

    with open(os.path.join(out_dir, "rows.jsonl"), "w", encoding="utf-8") as f_out:
        for r in rows:
            f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"  Saved index with {index.ntotal} vectors to {out_dir}")

print("\nSapBERT type-aware indexes built successfully.")
