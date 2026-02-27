import os
import json
from typing import List
import numpy as np
import torch
import faiss
from transformers import AutoTokenizer, AutoModel
from tqdm import tqdm

# ============================================================
# CONFIG (LOCKED)
# ============================================================

ENTITY_CATALOG = "data/processed/entities/entity_catalog.cleaned.jsonl"
SAPBERT_MODEL_PATH = "models/sapbert"
OUTPUT_ROOT = "indices/sapbert"

BATCH_SIZE = 64
MAX_LENGTH = 64

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ============================================================
# Load SapBERT (OFFLINE ONLY)
# ============================================================

tokenizer = AutoTokenizer.from_pretrained(SAPBERT_MODEL_PATH, local_files_only=True)

model = AutoModel.from_pretrained(SAPBERT_MODEL_PATH, local_files_only=True).to(DEVICE)

model.eval()

# ============================================================
# Load entity catalog and split by type
# ============================================================

rows_by_type = {"drug": [], "disease": []}

with open(ENTITY_CATALOG, encoding="utf-8") as f:
    for line in f:
        entry = json.loads(line)
        etype = entry["entity_type"].lower()
        if etype not in rows_by_type:
            continue

        kg_id = entry["kg_id"]
        canonical = entry["canonical_name"]

        for surface in entry["synonyms"]:
            rows_by_type[etype].append(
                {
                    "kg_id": kg_id,
                    "surface": surface,
                    "source": "canonical" if surface == canonical else "external",
                }
            )

# ============================================================
# Embedding function (SapBERT standard)
#   - [CLS] token
#   - L2 normalization
# ============================================================


def embed_surfaces(surfaces: List[str]) -> np.ndarray:
    all_embeddings = []

    with torch.no_grad():
        for i in range(0, len(surfaces), BATCH_SIZE):
            batch = surfaces[i : i + BATCH_SIZE]

            encoded = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )

            encoded = {k: v.to(DEVICE) for k, v in encoded.items()}

            outputs = model(**encoded)

            cls_embeddings = outputs.last_hidden_state[:, 0, :]
            cls_embeddings = torch.nn.functional.normalize(cls_embeddings, p=2, dim=1)

            all_embeddings.append(cls_embeddings.cpu().numpy())

    return np.vstack(all_embeddings)


# ============================================================
# Build FAISS indexes (type-aware)
# ============================================================

os.makedirs(OUTPUT_ROOT, exist_ok=True)

for entity_type, rows in rows_by_type.items():
    if not rows:
        continue

    print(f"\n[Phase 1.1] Indexing {entity_type} entities")
    print(f"Surfaces: {len(rows)}")

    surfaces = [r["surface"] for r in rows]

    embeddings = embed_surfaces(surfaces)
    dim = embeddings.shape[1]

    # FAISS IndexFlatIP
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    out_dir = os.path.join(OUTPUT_ROOT, entity_type.capitalize())
    os.makedirs(out_dir, exist_ok=True)

    # Save FAISS index
    faiss.write_index(index, os.path.join(out_dir, "index.faiss"))

    # Save row metadata
    with open(os.path.join(out_dir, "rows.jsonl"), "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Saved index to {out_dir}")

print("\n✅ Phase 1.1 complete — SapBERT indexes built successfully.")
