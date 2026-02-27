"""
sapbert_linker_v2.py

Type-aware SapBERT entity linker.
Read-only, deterministic, offline, publication-safe.

Authoritative indexes:
  indices/sapbert/Drug/index.faiss
  indices/sapbert/Disease/index.faiss

Design guarantees:
- No legacy code modification
- No silent failures
- Explicit confidence score
- Type-safe routing
"""

import os
import json
from typing import Optional, Dict, Any, List

import numpy as np
import torch
import faiss
from transformers import AutoTokenizer, AutoModel


# ============================================================
# CONFIG (LOCKED)
# ============================================================

SAPBERT_MODEL_PATH = "models/sapbert"
SAPBERT_INDEX_ROOT = "indices/sapbert"

TOP_K = 5
MIN_SCORE = 0.65
MAX_LENGTH = 64

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# Helper: L2 normalize numpy vectors
# ============================================================


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec, axis=1, keepdims=True)
    return vec / np.clip(norm, a_min=1e-12, a_max=None)


# ============================================================
# SapBERT Linker V2
# ============================================================


class SapBERTLinkerV2:
    def __init__(self):
        # Load model (offline only)
        self.tokenizer = AutoTokenizer.from_pretrained(
            SAPBERT_MODEL_PATH, local_files_only=True
        )
        self.model = AutoModel.from_pretrained(
            SAPBERT_MODEL_PATH, local_files_only=True
        ).to(DEVICE)
        self.model.eval()

        # Load FAISS indexes and row metadata
        self.index_by_type = {}
        self.rows_by_type = {}

        for etype in ["Drug", "Disease"]:
            index_path = os.path.join(SAPBERT_INDEX_ROOT, etype, "index.faiss")
            rows_path = os.path.join(SAPBERT_INDEX_ROOT, etype, "rows.jsonl")

            if not os.path.exists(index_path):
                raise FileNotFoundError(f"Missing FAISS index: {index_path}")
            if not os.path.exists(rows_path):
                raise FileNotFoundError(f"Missing rows file: {rows_path}")

            index = faiss.read_index(index_path)

            rows = []
            with open(rows_path, encoding="utf-8") as f:
                for line in f:
                    rows.append(json.loads(line))

            self.index_by_type[etype.lower()] = index
            self.rows_by_type[etype.lower()] = rows

    # --------------------------------------------------------
    # Embed a single surface string
    # --------------------------------------------------------

    def _embed(self, surface: str) -> np.ndarray:
        with torch.no_grad():
            encoded = self.tokenizer(
                surface,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )
            encoded = {k: v.to(DEVICE) for k, v in encoded.items()}

            outputs = self.model(**encoded)
            cls_vec = outputs.last_hidden_state[:, 0, :]
            cls_vec = torch.nn.functional.normalize(cls_vec, p=2, dim=1)

        return cls_vec.cpu().numpy()

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def link(self, surface: str, entity_type: str) -> Dict[str, Any]:
        """
        Link a surface string to a KG entity.

        Returns:
            {
              "surface": str,
              "entity_type": str,
              "kg_id": Optional[str],
              "score": float,
              "source": str
            }
        """

        entity_type = entity_type.lower()

        if entity_type not in self.index_by_type:
            return {
                "surface": surface,
                "entity_type": entity_type,
                "kg_id": None,
                "score": 0.0,
                "source": "sapbert_invalid_type",
            }

        # Embed query
        query_vec = self._embed(surface)

        # Search FAISS
        index = self.index_by_type[entity_type]
        rows = self.rows_by_type[entity_type]

        scores, indices = index.search(query_vec, TOP_K)

        scores = scores[0]
        indices = indices[0]

        if len(indices) == 0:
            return {
                "surface": surface,
                "entity_type": entity_type,
                "kg_id": None,
                "score": 0.0,
                "source": "sapbert_no_result",
            }

        best_idx = int(indices[0])
        best_score = float(scores[0])

        if best_score < MIN_SCORE:
            return {
                "surface": surface,
                "entity_type": entity_type,
                "kg_id": None,
                "score": best_score,
                "source": "sapbert_low_conf",
            }

        best_row = rows[best_idx]

        return {
            "surface": surface,
            "entity_type": entity_type,
            "kg_id": best_row["kg_id"],
            "score": best_score,
            "source": "sapbert",
        }
