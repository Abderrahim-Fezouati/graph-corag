# -*- coding: utf-8 -*-
import os, json, csv, argparse, re
import numpy as np
from sentence_transformers import SentenceTransformer
import nmslib

ap = argparse.ArgumentParser()
ap.add_argument("--in_raw", required=True)
ap.add_argument("--out_enriched", required=True)
ap.add_argument("--kg", required=True)
ap.add_argument("--dict", required=True)  # CUI -> [surfaces]
ap.add_argument("--overlay", required=True)
ap.add_argument("--index_dir", required=True)
ap.add_argument("--model", default="cambridgeltl/SapBERT-from-PubMedBERT-fulltext")
ap.add_argument("--k", type=int, default=8)
args = ap.parse_args()

# --- load KG nodes ---
kg_heads = set()
kg_nodes = set()
with open(args.kg, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    rows = list(r)
    if rows and rows[0] and rows[0][0].lower() in ("h", "head", "source"):
        rows = rows[1:]
    for h, rel, t in rows:
        h = h.strip()
        t = t.strip()
        kg_heads.add(h)
        kg_nodes.update([h, t])

# --- intent rules ---
rx_interact = re.compile(
    r"\b(interact|interaction|co[- ]?administer|combination)\b", re.I
)
rx_ae = re.compile(
    r"\b(adverse|side effect|toxicit|risk|associated with|linked to)\b", re.I
)


def detect_relations(text):
    r = set()
    if rx_interact.search(text):
        r.add("INTERACTS_WITH")
    if rx_ae.search(text):
        r.add("ADVERSE_EFFECT")
    if not r:
        tl = text.lower().strip()
        if (
            tl.startswith(("does", "do", "is", "are", "can", "will"))
            and "interact" in tl
        ):
            r.add("INTERACTS_WITH")
        if tl.startswith(("what", "which")) and ("adverse" in tl or "side" in tl):
            r.add("ADVERSE_EFFECT")
    return sorted(r)


# --- mention candidates by dictionary substring (fast and robust) ---
def load_cui2surfs(p):
    return json.load(open(p, encoding="utf-8"))


cui2 = load_cui2surfs(args.dict)
ov = load_cui2surfs(args.overlay)
for k, v in ov.items():
    base = cui2.setdefault(k, [])
    seen = set(s.strip() for s in base)
    for s in v:
        s = (s or "").strip()
        if s and s not in seen:
            base.append(s)
            seen.add(s)

surfset = set()
for v in cui2.values():
    for s in v:
        s = (s or "").strip().lower()
        if len(s) >= 3:
            surfset.add(s)
surfaces = sorted(surfset)


def find_mentions(text):
    ql = text.lower()
    found = set()
    for s in surfaces:
        if len(s) >= 4 and s in ql:
            found.add(s)
    return sorted(found)


# --- load ANN index ---
pairs = json.load(open(os.path.join(args.index_dir, "ids.json"), encoding="utf-8"))[
    "pairs"
]
embs = np.load(os.path.join(args.index_dir, "vectors.npy"))
index = nmslib.init(method="hnsw", space="cosinesimil")
index.loadIndex(os.path.join(args.index_dir, "nmslib_index.bin"))

# reverse lookup: surface row -> node_id
row2node = [p[0] for p in pairs]

# model for mention encoding
model = SentenceTransformer(args.model)

BAN = {"disease_adverse_effects", "disease_side_effect"}


def nearest_nodes(surface_text, topk):
    v = model.encode(
        [surface_text], convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")
    idxs, dists = index.knnQuery(v[0], k=topk)
    nodes = [row2node[i] for i in idxs]
    return nodes, dists


def choose_head(candidates):
    # 1) prefer drug_* that are KG heads
    for c in candidates:
        if c.startswith("drug_") and c in kg_heads:
            return c
    # 2) any drug_* in KG
    for c in candidates:
        if c.startswith("drug_") and c in kg_nodes:
            return c
    # 3) any non-banned in KG
    for c in candidates:
        if c in kg_nodes and c not in BAN:
            return c
    return None


with open(args.out_enriched, "w", encoding="utf-8") as w, open(
    args.in_raw, encoding="utf-8"
) as r:
    for line in r:
        if not line.strip():
            continue
        ex = json.loads(line)
        qid, text = ex.get("qid"), ex.get("text", "")
        rels = detect_relations(text)
        ments = find_mentions(text)
        all_nodes = []
        # SapBERT over each mention, collect top-k nodes
        for m in ments:
            nodes, _ = nearest_nodes(m, args.k)
            all_nodes.extend(nodes)
        # keep stable order but unique
        seen = set()
        uniq = []
        for c in all_nodes:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        head = choose_head(uniq)
        out = {
            "qid": qid,
            "text": text,
            "relations": rels,
            "head_cui": head,
            "extracted_surfaces": ments,
            "candidates": uniq[: args.k],
        }
        w.write(json.dumps(out, ensure_ascii=False) + "\n")

print("Wrote", args.out_enriched)
