import io, json
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

class DenseRetriever:
    def __init__(self, corpus_path, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        self.ids, self.texts = [], []
        with io.open(corpus_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                o = json.loads(line)
                if o.get("id") and o.get("text"):
                    self.ids.append(o["id"]); self.texts.append(o["text"])
        self.model = SentenceTransformer(model_name)
        X = self.model.encode(self.texts, convert_to_numpy=True, batch_size=256,
                              show_progress_bar=False, normalize_embeddings=True)
        self.index = faiss.IndexFlatIP(X.shape[1])
        self.index.add(X)

    def search(self, query, topk=100):
        q = self.model.encode([query], convert_to_numpy=True, normalize_embeddings=True)
        D, I = self.index.search(q, topk)
        out = []
        for score, idx in zip(D[0], I[0]):
            if idx == -1: break
            out.append({"id": self.ids[idx], "text": self.texts[idx], "score": float(score)})
        return out
