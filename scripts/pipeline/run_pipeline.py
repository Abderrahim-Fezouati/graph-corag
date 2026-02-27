#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
End-to-end biomedical QA pipeline orchestrator with multihop KG reasoning.

Input:
  - Analyzed queries (NER + EL via SapBERT + dictionary)
  - BM25 + Dense retrieval modules
  - KG CSV: data/kg_edges.merged.plus.csv

Steps:
  1) Load queries with candidates and NER spans
  2) Infer intent/relation
  3) Select best head concept (CUI)
  4) Launch hybrid retrieval module
  5) Run KG multihop reasoning over retrieved results
  6) Write output with paths, support scores, explanations

Output:
  - hybrid.outputs.jsonl in --out_dir
  - rl_eval.tsv in --out_dir
  - Supports JSONL output with structured reasoning fields

Run in: gcorag-lite-cu118 environment
"""

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from graphcorag.kg_multihop import KGMultiHop


# -----------------------------
# Utility functions
# -----------------------------
def load_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_jsonl(path: str, rows: List[Dict[str, Any]]):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


# -----------------------------
# Core pipeline functions
# -----------------------------
def infer_relations(text: str) -> List[str]:
    t = (text or "").lower()
    rels = []
    if any(k in t for k in ["interact", "interaction", "drug-drug"]):
        rels.append("INTERACTS_WITH")
    if any(
        k in t for k in ["adverse effect", "toxicity", "side effect", "adverse event"]
    ):
        rels.append("ADVERSE_EFFECT")
    return list(dict.fromkeys(rels))  # dedup


def choose_best_cui(candidates: List[Dict[str, Any]]) -> Optional[str]:
    if not candidates:
        return None

    def sort_key(c):
        match_priority = {"sapbert_typeaware": 2, "sapbert_combined": 1}
        return (match_priority.get(c.get("match", ""), 0), float(c.get("score", 0.0)))

    return sorted(candidates, key=sort_key, reverse=True)[0].get("cui")


def build_hybrid_input(analyzed_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hybrid_input = []
    for ex in analyzed_rows:
        hybrid_input.append(
            {
                "qid": ex["qid"],
                "text": ex["text"],
                "relations": infer_relations(ex["text"]),
                "head": ex.get("head"),
                "head_cui": choose_best_cui(ex.get("candidates", [])),
            }
        )
    return hybrid_input


# -----------------------------
# Explainability: add KG reasoning results
# -----------------------------
def inject_reasoning(output_path: str, kg: KGMultiHop, max_hops: int = 3):
    rows = load_jsonl(output_path)
    enriched = []
    for row in rows:
        cui = row.get("head_cui")
        relations = set(row.get("relations", []))
        if not cui:
            row.update(
                {
                    "kg_paths": [],
                    "reasoning_hops": 0,
                    "explanations": [],
                    "support_score": 0.0,
                }
            )
            enriched.append(row)
            continue

        paths = kg.bfs_paths(start=cui, max_hops=max_hops, allowed_relations=relations)
        explanations = [
            " -> ".join(f"{src} -[{rel}]-> {tgt}" for src, rel, tgt in path)
            for path in paths
        ]
        score = min(len(paths), 5) / 5.0  # crude support proxy

        row.update(
            {
                "kg_paths": paths,
                "reasoning_hops": max(len(p) for p in paths) if paths else 0,
                "explanations": explanations,
                "support_score": score,
            }
        )
        enriched.append(row)

    save_jsonl(output_path, enriched)


# -----------------------------
# Main orchestrator
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query_jsonl", required=True)
    parser.add_argument("--out_dir", required=True)
    parser.add_argument("--kg_csv", default="data/kg_edges.merged.plus.csv")
    parser.add_argument("--run_tag", default="pipeline_run")

    parser.add_argument("--corpus", required=True)
    parser.add_argument("--dict", required=True)
    parser.add_argument("--overlay", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument(
        "--bm25_mod_path",
        required=False,
        default=None,
        help="Optional. If omitted, BM25 is built from --corpus at runtime.",
    )
    parser.add_argument("--dense_mod_path", required=True)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    print("[INFO] Loading analyzed queries...")
    analyzed = load_jsonl(args.query_jsonl)
    hybrid_rows = build_hybrid_input(analyzed)

    qpath = os.path.join(args.out_dir, "queries.for_hybrid.jsonl")
    save_jsonl(qpath, hybrid_rows)

    print("[INFO] Running hybrid retrieval...")
    import sys

    cmd = [
        sys.executable,
        "scripts/run_hybrid.py",
        "--corpus",
        args.corpus,
        "--kg",
        args.kg_csv,
        "--dict",
        args.dict,
        "--overlay",
        args.overlay,
        "--schema",
        args.schema,
        "--queries",
        qpath,
        "--out",
        args.out_dir,
        "--dense_mod_path",
        args.dense_mod_path,
    ]
    if args.bm25_mod_path:
        cmd.extend(["--bm25_mod_path", args.bm25_mod_path])
    subprocess.run(cmd, check=True)

    print("[INFO] Injecting KG multihop reasoning...")
    kg = KGMultiHop(args.kg_csv)
    out_path = os.path.join(args.out_dir, "hybrid.outputs.jsonl")
    inject_reasoning(out_path, kg)

    print("[DONE] Output written to:", out_path)


if __name__ == "__main__":
    main()
