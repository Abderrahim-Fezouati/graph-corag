# -*- coding: utf-8 -*-
import os, csv, json, argparse, numpy as np
from tqdm import tqdm
from collections import defaultdict
from sentence_transformers import SentenceTransformer
import nmslib

ap = argparse.ArgumentParser()
ap.add_argument("--kg", required=True)
ap.add_argument("--dict", required=True)  # umls_dict.txt (JSON: CUI -> [surfaces])
ap.add_argument("--overlay", required=True)  # overlay JSON
ap.add_argument("--out_dir", required=True)
ap.add_argument("--model", default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext")
ap.add_argument("--batch", type=int, default=64)
args = ap.parse_args()

os.makedirs(args.out_dir, exist_ok=True)

# 1) Load KG nodes
kg_nodes = set()
with open(args.kg, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    rows = list(r)
    if rows and rows[0] and rows[0][0].lower() in ("h", "head", "source"):
        rows = rows[1:]
    for h, rel, t in rows:
        kg_nodes.add(h.strip())
        kg_nodes.add(t.strip())


# 2) Load dict + overlay
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


cui2surfs = load_json(args.dict)
overlay = load_json(args.overlay)

# merge overlay
for cui, surfs in overlay.items():
    base = cui2surfs.setdefault(cui, [])
    seen = set(s.strip() for s in base)
    for s in surfs:
        s = (s or "").strip()
        if s and s not in seen:
            base.append(s)
            seen.add(s)

# filter to KG nodes only, build (node -> surfaces)
node2surfs = {}
for cui in kg_nodes:
    surfs = cui2surfs.get(cui, [])
    # keep unique, non-empty, >=3 chars
    surfs = sorted({s.strip() for s in surfs if s and len(s.strip()) >= 3})
    if surfs:
        node2surfs[cui] = surfs

if not node2surfs:
    raise SystemExit(
        "No surfaces found for KG nodes. Check your dict/overlay coverage."
    )

# 3) Flatten surfaces for encoding and remember which node each surface belongs to
pairs = []  # (node_id, surface)
for node, surfs in node2surfs.items():
    for s in surfs:
        pairs.append((node, s))

texts = [s for _, s in pairs]

# 4) Encode with SapBERT
model = SentenceTransformer(args.model)
embs = []
for i in tqdm(range(0, len(texts), args.batch), desc="Encoding"):
    batch = texts[i : i + args.batch]
    vecs = model.encode(
        batch,
        batch_size=args.batch,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    embs.append(vecs)
embs = np.vstack(embs).astype("float32")

# 5) Build an ANN index over surface vectors
index = nmslib.init(method="hnsw", space="cosinesimil")
index.addDataPointBatch(embs)
index.createIndex({"post": 2}, print_progress=True)

# 6) Persist
np.save(os.path.join(args.out_dir, "vectors.npy"), embs)
with open(os.path.join(args.out_dir, "ids.json"), "w", encoding="utf-8") as f:
    json.dump({"pairs": pairs}, f, ensure_ascii=False, indent=2)
index.saveIndex(os.path.join(args.out_dir, "nmslib_index.bin"))

print(f"Indexed {len(pairs)} surfaces for {len(node2surfs)} KG nodes → {args.out_dir}")
