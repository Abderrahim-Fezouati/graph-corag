# -*- coding: utf-8 -*-
"""
hybridkg.text_retriever (enhanced)
- BM25 baseline
- Optional chunking for long docs
- Dict-driven query expansion (surfaces sharing the same CUI)
- Phrase boost for multiword matches
- RM3 PRF rerank (lexical; dependency-free)

API: TextRetriever(...).retrieve(query, topk)
Also exposes a CLI for smoke tests.
"""
import json, math, os, re, sys
from typing import Dict, List, Tuple, Optional

_WORD_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)
_STOP = set(
    """
a an and are as at be but by for from has have if in into is it its of on or that the their there these this to was were which with
""".split()
)


def _tok(s: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(s or "")]


def _phrase_spans(s: str) -> List[str]:
    toks = [t for t in re.split(r"\s+", (s or "").strip()) if t]
    phrases = []
    for i in range(len(toks) - 1):
        ph = (toks[i] + " " + toks[i + 1]).strip()
        if len(ph) >= 5:
            phrases.append(ph.lower())
    # dedup, stable
    return list(dict.fromkeys(phrases))


class TextRetriever:
    def __init__(
        self,
        corpus_path: str,
        chunk_size: int = 0,
        chunk_stride: Optional[int] = None,
        dict_path: Optional[str] = None,
        overlay_path: Optional[str] = None,
        dict_expansion_weight: float = 0.7,
        phrase_boost: float = 0.2,
        use_rm3: bool = False,
        rm3_fb_docs: int = 10,
        rm3_fb_terms: int = 10,
        rm3_orig_weight: float = 0.6,
    ):
        """
        Args:
          chunk_size: if >0, index documents in sliding windows of token length
          chunk_stride: step for sliding windows (default = chunk_size)
          dict_path: surface->CUI JSON (enables synonym expansion via CUI reverse map)
        """
        self.docs: Dict[str, str] = {}  # doc_id -> raw lowercased text (chunk or full)
        self.doc_len: Dict[str, int] = {}  # doc_id -> token count
        self.inverted: Dict[str, Dict[str, int]] = {}  # term -> {doc_id: tf}
        self.N = 0
        self.avgdl = 0.0

        # --- legacy positional args compatibility ---
        # Old runner calls: TextRetriever(corpus_path, dict_path, overlay_path)
        # so our 'chunk_size' param may actually be a string dict_path.
        if isinstance(chunk_size, str):
            if dict_path is None and len(chunk_size) > 0:
                dict_path = chunk_size
            chunk_size = 0
        # ---------------------------------------------------------------------

        self.chunk_size = max(0, int(chunk_size))
        if isinstance(chunk_stride, str):
            # legacy 3rd positional arg is an overlay path
            if overlay_path is None and len(chunk_stride) > 0:
                overlay_path = chunk_stride
            chunk_stride = None
        self.chunk_stride = int(chunk_stride) if chunk_stride is not None else None
        self.chunk_stride = (
            self.chunk_stride
            if self.chunk_stride and self.chunk_stride > 0
            else self.chunk_size
        )

        self.dict_path = dict_path
        self.overlay_path = overlay_path
        self.dict: Dict[str, str] = {}
        self.cui2surfaces: Dict[str, List[str]] = {}
        self.dict_expansion_weight = float(dict_expansion_weight)
        self.phrase_boost = float(phrase_boost)

        self.use_rm3 = bool(use_rm3)
        self.rm3_fb_docs = int(rm3_fb_docs)
        self.rm3_fb_terms = int(rm3_fb_terms)
        self.rm3_orig_weight = float(rm3_orig_weight)

        if self.dict_path:
            self._load_dict(self.dict_path, self.overlay_path)

        self._load_corpus(corpus_path)

    # ------------------------------ loaders ------------------------------
    def _load_dict(self, path: str, overlay_path: Optional[str] = None) -> None:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Dictionary JSON must be an object: {path}")

        # Preferred contract: kg_id -> list[str] surfaces.
        if raw and all(isinstance(v, list) for v in raw.values()):
            merged: Dict[str, List[str]] = {}
            for kg_id, surfs in raw.items():
                if not isinstance(kg_id, str):
                    continue
                vals: List[str] = []
                seen = set()
                for s in surfs:
                    if not isinstance(s, str):
                        continue
                    t = s.strip()
                    if not t:
                        continue
                    key = t.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    vals.append(t)
                if vals:
                    merged[kg_id.strip().upper()] = vals

            if overlay_path and os.path.exists(overlay_path):
                with open(overlay_path, "r", encoding="utf-8-sig") as f:
                    overlay_raw = json.load(f)
                if not isinstance(overlay_raw, dict):
                    raise ValueError(f"Overlay JSON must be an object: {overlay_path}")
                for kg_id, surfs in overlay_raw.items():
                    if not isinstance(kg_id, str) or not isinstance(surfs, list):
                        continue
                    cui = kg_id.strip().upper()
                    base = merged.setdefault(cui, [])
                    seen = {x.lower() for x in base}
                    for s in surfs:
                        if not isinstance(s, str):
                            continue
                        t = s.strip()
                        if not t:
                            continue
                        key = t.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        base.append(t)

            for cui, surfs in merged.items():
                self.cui2surfaces[cui] = list(surfs)
                for s in surfs:
                    sl = s.lower()
                    if sl not in self.dict:
                        self.dict[sl] = cui
        else:
            # Legacy contract: surface -> CUI.
            self.dict = {
                str(k).strip().lower(): str(v).strip().upper() for k, v in raw.items()
            }
            for s, cui in self.dict.items():
                self.cui2surfaces.setdefault(cui, []).append(s)

        for cui in self.cui2surfaces:
            self.cui2surfaces[cui].sort(key=len, reverse=True)
        print(
            f"[TextRetriever] Loaded dict surfaces: {len(self.dict)} (CUIs: {len(self.cui2surfaces)})",
            file=sys.stderr,
        )

    def _add_postings(self, doc_id: str, text: str) -> None:
        text_lc = text.lower()
        toks = _tok(text_lc)
        if not toks:
            return
        self.docs[doc_id] = text_lc
        self.doc_len[doc_id] = len(toks)
        counts: Dict[str, int] = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        for t, tf in counts.items():
            posting = self.inverted.get(t)
            if posting is None:
                posting = {}
                self.inverted[t] = posting
            posting[doc_id] = tf

    def _load_corpus(self, path: str) -> None:
        seen_missing = False
        with open(path, "r", encoding="utf-8-sig") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception as e:
                    print(
                        f"[WARN] Skipping malformed JSONL line {i}: {e}",
                        file=sys.stderr,
                    )
                    continue
                doc_id = obj.get("id") or obj.get("doc_id") or f"doc_{i}"
                text = obj.get("text") or obj.get("body") or obj.get("content")
                if not text:
                    if not seen_missing:
                        print(
                            "[WARN] Some documents lack {text|body|content}. They will be skipped.",
                            file=sys.stderr,
                        )
                        seen_missing = True
                    continue

                if self.chunk_size > 0:
                    toks = _tok(text)
                    if not toks:
                        continue
                    stride = self.chunk_stride or self.chunk_size
                    idx = 0
                    chunk_id = 0
                    while idx < len(toks):
                        chunk_tokens = toks[idx : idx + self.chunk_size]
                        if not chunk_tokens:
                            break
                        chunk_text = " ".join(chunk_tokens)
                        self._add_postings(f"{doc_id}#c{chunk_id}", chunk_text)
                        chunk_id += 1
                        idx += stride
                else:
                    self._add_postings(doc_id, text)

        self.N = len(self.docs)
        self.avgdl = (sum(self.doc_len.values()) / self.N) if self.N > 0 else 0.0
        print(
            f"[TextRetriever] Loaded {self.N} docs. avgdl={self.avgdl:.2f}",
            file=sys.stderr,
        )

    # ------------------------------ scoring ------------------------------
    def _idf(self, term: str) -> float:
        df = len(self.inverted.get(term, {}))
        if df == 0 or self.N == 0:
            return 0.0
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    # ------------------------------ query expansion ------------------------------
    def _expand_query_from_dict(self, query_raw: str) -> Dict[str, float]:
        q_lower = (query_raw or "").lower()
        base_terms = _tok(q_lower)
        weights: Dict[str, float] = {}
        for t in base_terms:
            weights[t] = max(weights.get(t, 0.0), 1.0)

        if not self.cui2surfaces or not self.dict:
            return weights

        present_cuis = set()
        for surface, cui in self.dict.items():
            if surface in q_lower:
                present_cuis.add(cui)

        for cui in present_cuis:
            for s in self.cui2surfaces.get(cui, []):
                for t in _tok(s):
                    if t in _STOP:
                        continue
                    if weights.get(t, 0.0) < 1.0:
                        weights[t] = max(
                            weights.get(t, 0.0), self.dict_expansion_weight
                        )
        return weights

    # ------------------------------ RM3 PRF ------------------------------
    def _rm3_terms(
        self, scores_sorted: List[Tuple[str, float]], fb_docs: int, fb_terms: int
    ) -> Dict[str, float]:
        term_counts: Dict[str, int] = {}
        take = min(fb_docs, len(scores_sorted))
        for doc_id, _ in scores_sorted[:take]:
            for t in _tok(self.docs.get(doc_id, "")):
                if t in _STOP:
                    continue
                term_counts[t] = term_counts.get(t, 0) + 1
        if not term_counts:
            return {}
        scored = [(t, term_counts[t] * self._idf(t)) for t in term_counts]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[: max(0, fb_terms)]
        total = sum(w for _, w in top) or 1.0
        return {t: (w / total) for t, w in top}

    # ------------------------------ retrieve ------------------------------
    def retrieve(
        self, query: str, topk: int = 50, k1: float = 1.5, b: float = 0.75
    ) -> List[Tuple[str, float]]:
        if self.N == 0:
            return []

        if self.cui2surfaces:
            term_w = self._expand_query_from_dict(query)
        else:
            term_w = {t: 1.0 for t in _tok(query)}

        scores: Dict[str, float] = {}
        for qt, w in term_w.items():
            posting = self.inverted.get(qt)
            if not posting:
                continue
            idf = self._idf(qt)
            for doc_id, tf in posting.items():
                dl = self.doc_len.get(doc_id, 0)
                contrib = idf * (
                    (tf * (k1 + 1.0))
                    / (tf + k1 * (1.0 - b + b * (dl / (self.avgdl + 1e-9))) + 1e-9)
                )
                scores[doc_id] = scores.get(doc_id, 0.0) + (w * contrib)

        # Phrase boost (exact substring of multiword phrases)
        if self.phrase_boost > 0.0:
            phrases = _phrase_spans(query)
            if self.cui2surfaces:
                for cui, ss in self.cui2surfaces.items():
                    for s in ss:
                        if " " in s and s in (query or "").lower():
                            phrases.append(s.lower())
            phrases = list(dict.fromkeys([p for p in phrases if len(p) >= 5]))
            if phrases:
                for doc_id in list(scores.keys()):
                    text = self.docs.get(doc_id, "")
                    add = 0.0
                    for p in phrases:
                        if p in text:
                            add += self.phrase_boost
                    if add:
                        scores[doc_id] += add

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        if not self.use_rm3 or not ranked:
            return ranked[: max(0, int(topk))]

        # RM3 second pass
        prf = self._rm3_terms(ranked, self.rm3_fb_docs, self.rm3_fb_terms)
        if prf:
            base_sum = sum(term_w.values()) or 1.0
            base_norm = {t: term_w[t] / base_sum for t in term_w}
            combined: Dict[str, float] = {}
            for t, w in base_norm.items():
                combined[t] = combined.get(t, 0.0) + self.rm3_orig_weight * w
            for t, w in prf.items():
                combined[t] = combined.get(t, 0.0) + (1.0 - self.rm3_orig_weight) * w

            scores2: Dict[str, float] = {}
            for qt, w in combined.items():
                posting = self.inverted.get(qt)
                if not posting:
                    continue
                idf = self._idf(qt)
                for doc_id, tf in posting.items():
                    dl = self.doc_len.get(doc_id, 0)
                    contrib = idf * (
                        (tf * (k1 + 1.0))
                        / (tf + k1 * (1.0 - b + b * (dl / (self.avgdl + 1e-9))) + 1e-9)
                    )
                    scores2[doc_id] = scores2.get(doc_id, 0.0) + (w * contrib)
            ranked = sorted(scores2.items(), key=lambda kv: kv[1], reverse=True)

        return ranked[: max(0, int(topk))]


# ---------------- Backward-compat alias ----------------
try:
    BM25Retriever = TextRetriever
except NameError:
    pass

# ---------------- CLI for smoke testing ----------------
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Enhanced BM25 retriever")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--topk", type=int, default=20)
    ap.add_argument("--chunk_size", type=int, default=0)
    ap.add_argument("--chunk_stride", type=int, default=0)
    ap.add_argument("--dict", dest="dict_path", default=None)
    ap.add_argument("--dict_expansion_weight", type=float, default=0.7)
    ap.add_argument("--phrase_boost", type=float, default=0.2)
    ap.add_argument("--rm3", action="store_true")
    ap.add_argument("--rm3_fb_docs", type=int, default=10)
    ap.add_argument("--rm3_fb_terms", type=int, default=10)
    ap.add_argument("--rm3_orig_weight", type=float, default=0.6)
    args = ap.parse_args()

    tr = TextRetriever(
        corpus_path=args.corpus,
        chunk_size=args.chunk_size,
        chunk_stride=(args.chunk_stride if args.chunk_stride > 0 else None),
        dict_path=args.dict_path,
        dict_expansion_weight=args.dict_expansion_weight,
        phrase_boost=args.phrase_boost,
        use_rm3=args.rm3,
        rm3_fb_docs=args.rm3_fb_docs,
        rm3_fb_terms=args.rm3_fb_terms,
        rm3_orig_weight=args.rm3_orig_weight,
    )
    res = tr.retrieve(args.query, topk=args.topk)
    print(f"results: {len(res)}")
    if res:
        top_id, top_sc = res[0]
        print(f"top1: ({top_id}, {top_sc:.3f})")
        print("topk sample:", res[:5])


# --- compatibility alias (added by setup) ---
try:
    if not hasattr(TextRetriever, "search"):

        def _search(self, query, topk=100):
            return self.retrieve(query, topk=topk)

        TextRetriever.search = _search
except Exception:
    pass
