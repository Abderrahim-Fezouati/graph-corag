import os, json, torch
from sentence_transformers import SentenceTransformer
import numpy as np

PROJ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ALIASES = os.path.join(PROJ, "out", "kg_catalog.aliases.json")
OUT = os.path.join(PROJ, "out", "kg_catalog.sbert.npz")

model_name = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer(model_name, device=device)

with open(ALIASES, "r", encoding="utf-8") as f:
    aliases = json.load(f)

rows = []
keys = []
for cui, names in aliases.items():
    for s in names:
        keys.append((cui, s))
        rows.append(s)

print(f"[embed] encoding {len(rows)} alias strings with SapBERT on {device}…")
emb = model.encode(
    rows,
    convert_to_numpy=True,
    normalize_embeddings=True,
    batch_size=128,
    show_progress_bar=True,
)

np.savez_compressed(OUT, emb=emb, keys=np.array(keys, dtype=object))
print(f"[embed] wrote {OUT} | shape={emb.shape}")
