import torch
from transformers import AutoTokenizer, AutoModel


class ContextReranker:
    def __init__(self, model_name: str = None, device: str = None, tok=None, mdl=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        if tok is not None and mdl is not None:
            # reuse same model/tokenizer (SapBERT)
            self.tok, self.mdl = tok, mdl
        else:
            self.model_name = (
                model_name or "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
            )
            self.tok = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)
            self.mdl = AutoModel.from_pretrained(self.model_name).to(self.device).eval()

    @torch.no_grad()
    def _enc(self, texts, max_len=128):
        x = self.tok(
            texts,
            padding=True,
            truncation=True,
            max_length=max_len,
            return_tensors="pt",
        ).to(self.device)
        out = self.mdl(**x).last_hidden_state
        mask = x["attention_mask"].unsqueeze(-1)
        pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return torch.nn.functional.normalize(pooled, p=2, dim=1)

    def rerank(self, question: str, candidates: list[dict], topk: int = 8):
        if not candidates:
            return []
        qv = self._enc([question])
        cv = self._enc([c["name"] for c in candidates])
        sims = (qv @ cv.T).cpu().numpy().flatten()
        ranked = sorted(
            [dict(c, ctx_score=float(s)) for c, s in zip(candidates, sims)],
            key=lambda x: (x.get("ctx_score", 0.0), x.get("score", 0.0)),
            reverse=True,
        )
        return ranked[:topk]
