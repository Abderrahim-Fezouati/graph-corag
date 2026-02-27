# Pipeline Overview

## Purpose
Graph-CORAG is a research pipeline for validating biomedical claims against a knowledge graph (KG) and retrieved text evidence. It is explicitly a claim validation system, not an answer generation system.

## High-level flow
- Inputs are query JSONL files (qid + text).
- Analysis performs NER/EL, relation inference, and KG-aware checks.
- Retrieval collects candidate passages.
- KG validation checks whether predicted relations are supported by KG edges.
- Outputs are validation artifacts (hybrid.outputs.jsonl, rl_eval.tsv), not generated answers.

## End-to-end data flow
1) Analysis: `scripts/analyze_with_el_and_intent.py`
   - Query-level NER + entity linking
   - Relation prediction
   - KG relation checks and claim construction

2) Retrieval: `scripts/run_hybrid.py`
   - BM25 + Dense retrieval
   - Simple KG coverage check

3) KG validation and reasoning: `scripts/pipeline/run_pipeline.py`
   - Calls `scripts/run_hybrid.py`
   - Adds multihop KG reasoning via `graphcorag.kg_multihop.KGMultiHop`

## Diagram (text)
```
[Raw Queries JSONL]
        |
        v
[Analysis: scripts/analyze_with_el_and_intent.py]
        |
        v
[Analyzed Queries JSONL]
        |
        v
[Adapter (optional, data-only)]
        |
        v
[Pipeline Orchestrator: scripts/pipeline/run_pipeline.py]
        |
        +--> [Hybrid Retrieval: scripts/run_hybrid.py]
        |
        +--> [KG Multihop: graphcorag.kg_multihop.KGMultiHop]
        |
        v
[Outputs: hybrid.outputs.jsonl, rl_eval.tsv]
```
