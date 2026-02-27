#!/usr/bin/env python3
"""Generate a simple retrieval cache JSONL for text_coverage_metrics.

Writes lines of the form {"qid": <qid>, "hits": [doc_id, ...]}

Usage:
  python tools/generate_retrieval_cache.py --queries <queries.analyzed.jsonl> \
      --bm25 <path/to/text_retriever.py> --dense <path/to/dense_retriever.py> \
      --out <out/cache/retrieval.cache.jsonl> --topk 80
"""
import argparse, json, importlib.util, sys
from typing import Any, Dict, List


def _import_from_path(py_path: str, obj_name: str):
    spec = importlib.util.spec_from_file_location("mod_" + obj_name, py_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {obj_name} from {py_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, obj_name)


def load_queries(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--bm25", required=True)
    ap.add_argument("--dense", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--topk", type=int, default=80)
    args = ap.parse_args()

    TextRetriever = _import_from_path(args.bm25, "TextRetriever")
    DenseRetriever = _import_from_path(args.dense, "DenseRetriever")

    queries = load_queries(args.queries)
    # build retrievers (they expect corpus path as first arg)
    # we infer corpus path from environment by asking user to keep retrievers using dataset files
    # For compatibility we inspect constructor signature: assume first arg is corpus_path
    # We'll try to read 'corpus' value from queries file if present, else raise if retriever init fails.

    # Try to locate a corpus path passed inside queries (not guaranteed)
    corpus_path = None
    # If queries contained a top-level 'corpus' key (unlikely), use it. Otherwise, require user set env var or rely on retriever defaults.
    for q in queries:
        if q.get("corpus"):
            corpus_path = q.get("corpus")
            break

    if corpus_path is None:
        # fallback: ask user to ensure retriever constructors accept no path (DenseRetriever in repo requires corpus path), so we try to infer common path
        # We'll attempt common location: data/corpus.jsonl
        import os

        cand = os.path.join(os.getcwd(), "data", "corpus.jsonl")
        if os.path.exists(cand):
            corpus_path = cand
        else:
            print(
                "ERROR: cannot infer corpus path. Please ensure data/corpus.jsonl exists or modify this script."
            )
            sys.exit(2)

    print(f"Using corpus: {corpus_path}")
    bm25 = TextRetriever(corpus_path)
    dense = DenseRetriever(corpus_path)

    with open(args.out, "w", encoding="utf-8") as fout:
        for q in queries:
            qid = q.get("qid") or q.get("_qid") or q.get("id")
            qtext = q.get("text") or q.get("question") or q.get("query") or ""
            # perform retrievals
            bm = bm25.search(qtext, topk=args.topk)
            de = dense.search(qtext, topk=args.topk)
            # normalize bm to list of (doc_id, score)
            scores = {}
            for doc_id, score in bm:
                scores[doc_id] = max(scores.get(doc_id, 0.0), float(score))
            for _hit in de:
                if isinstance(_hit, dict):
                    doc_id = _hit.get("id") or _hit.get("doc_id")
                    score = float(_hit.get("score", 0.0))
                elif isinstance(_hit, (list, tuple)) and len(_hit) >= 2:
                    a, b = _hit[0], _hit[1]
                    if isinstance(a, (int, float)) and not isinstance(b, (int, float)):
                        doc_id, score = b, float(a)
                    else:
                        doc_id, score = a, float(b)
                else:
                    continue
                if doc_id is None:
                    continue
                scores[doc_id] = max(scores.get(doc_id, 0.0), float(score))

            top_sorted = [
                did
                for did, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[
                    : args.topk
                ]
            ]
            fout.write(
                json.dumps({"qid": qid, "hits": top_sorted}, ensure_ascii=False) + "\n"
            )

    print(f"Wrote cache to {args.out}")


if __name__ == "__main__":
    main()
