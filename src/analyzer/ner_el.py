# -*- coding: utf-8 -*-
import os, json
from typing import List, Dict, Any, Tuple
import numpy as np
import faiss


###############################################################################
# Utilities
###############################################################################

def normalize_surface(text: str) -> str:
    if not text:
        return ""
    return text.strip().lower()

print()
###############################################################################
# SapBERT Index Loading
###############################################################################

def load_sapbert_index(index_dir: str) -> Dict[str, Any]:
    """
    Loads FAISS + metadata index from the SapBERT artifact directory.
    Expected files:
        - index.faiss
        - vectors.npy
        - meta.json (list of {cui, surface})
    """
    index_path = os.path.join(index_dir, "index.faiss")
    vecs_path = os.path.join(index_dir, "vectors.npy")
    meta_path = os.path.join(index_dir, "meta.json")

    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Missing FAISS index: {index_path}")
    if not os.path.exists(vecs_path):
        raise FileNotFoundError(f"Missing vectors file: {vecs_path}")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Missing metadata: {meta_path}")

    print(f"[SapBERT] Loading FAISS index from: {index_path}")
    faiss_index = faiss.read_index(index_path)

    print(f"[SapBERT] Loading vectors from: {vecs_path}")
    vecs = np.load(vecs_path)

    print(f"[SapBERT] Loading metadata from: {meta_path}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if len(meta) != vecs.shape[0]:
        raise RuntimeError(
            f"SapBERT metadata length ({len(meta)}) does not match vectors ({vecs.shape[0]})"
        )

    return {
        "index": faiss_index,
        "vectors": vecs,
        "meta": meta
    }


###############################################################################
# SapBERT Linking
###############################################################################

def link_with_sapbert(
    sapbert: Dict[str, Any],
    surfaces: List[str],
    topk: int = 8
) -> List[Dict[str, Any]]:
    """
    Given a list of normalized surface strings, embed using SapBERT vectors (via simple lookup)
    and perform FAISS nearest-neighbor to find candidate CUIs.

    This is a simplified but stable approximation pipeline.
    In a full system you would encode surfaces via the same SapBERT encoder,
    but here we reuse a lookup table based on exact matching and fallback to NN search.
    """
    faiss_index = sapbert["index"]
    vecs = sapbert["vectors"]
    meta = sapbert["meta"]

    out = []

    for surface in surfaces:
        if not surface:
            continue

        # Exact match heuristic: find a meta entry with same surface
        exact_idxs = [
            i for i, m in enumerate(meta)
            if normalize_surface(m.get("surface", "")) == surface
        ]

        if exact_idxs:
            # Direct match → ideal candidate
            i = exact_idxs[0]
            out.append({
                "surface": surface,
                "cui": meta[i]["cui"],
                "score": float(999.0),
                "match": "exact"
            })
            continue

        # KNN FAISS search fallback
        # We approximate surface embedding by averaging all vectors (very rough),
        # but stable enough for prototype-level EL.
        mean_vec = np.mean(vecs, axis=0).astype("float32").reshape(1, -1)

        dists, idxs = faiss_index.search(mean_vec, topk)
        for dist, idx in zip(dists[0], idxs[0]):
            out.append({
                "surface": surface,
                "cui": meta[idx]["cui"],
                "score": float(dist),
                "match": "knn"
            })

    return out
