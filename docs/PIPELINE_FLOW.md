# Graph-CORAG Pipeline Flow

## Entry Points
- `scripts/pipeline/run_pipeline.py`: orchestrates analyzed queries -> `run_hybrid.py` -> KG multihop injection.
- `scripts/run_hybrid.py`: runs BM25 + dense retrieval over the corpus and a minimal KG neighbor check.
- `scripts/analyze_with_el_and_intent.py`: separate pipeline for passage-level NER, entity linking, claim building, and KG validation.
- `scripts/pre_analyze_raw.py`: optional preprocessing for raw query JSONL (rule-based enrichment).
- `tools/run_pipeline.ps1`: attempts to chain `pre_analyze_raw.py` -> `analyze_with_el_and_intent.py` -> `run_hybrid.py`, but its flags do not match the current Python scripts; execution is unclear.
- `run_pipeline.ps1` and `run.sh`: legacy wrappers that call `scripts/analyze_with_el_and_intent.py` with flags not present in the current script.

## Step-by-Step Execution
1. Pre-structure raw queries (optional)
   - What happens: loads raw query JSONL, extracts surface strings, detects relations, generates candidate triples, and optionally previews KG coverage.
   - Code location (script/module): `scripts/pre_analyze_raw.py`, `src/graphcorag/rules.py`, `src/graphcorag/kg_loader.py`.
   - Main inputs: raw queries JSONL, `config/umls_dict.txt`, `config/umls_dict.overlay.json`, KG CSV, `config/relation_schema.json`.
   - Main outputs: enriched `queries.structured.jsonl`.

2. Build hybrid input from analyzed queries
   - What happens: infers relations from query text, chooses the best head CUI from candidates, writes hybrid input JSONL.
   - Code location (script/module): `scripts/pipeline/run_pipeline.py`.
   - Main inputs: analyzed queries JSONL with `qid`, `text`, and `candidates`.
   - Main outputs: `queries.for_hybrid.jsonl` in `--out_dir`.

3. Hybrid retrieval and minimal KG check
   - What happens: loads corpus JSONL, builds BM25 and dense in-memory indexes, merges retrieval scores, loads KG CSV, checks 1-hop neighbors for `INTERACTS_WITH` and `ADVERSE_EFFECT`, and writes results.
   - Code location (script/module): `scripts/run_hybrid.py`, `src/graphcorag/text_retriever.py`, `src/graphcorag/dense_retriever.py`.
   - Main inputs: corpus JSONL, KG CSV, queries JSONL (with `relations` and `head_cui`), retriever module paths.
   - Main outputs: `hybrid.outputs.jsonl`, `rl_eval.tsv` in `--out`.

4. Inject KG multihop reasoning
   - What happens: loads `hybrid.outputs.jsonl`, runs BFS from `head_cui` with relation filtering, and injects `kg_paths`, `explanations`, and `support_score`.
   - Code location (script/module): `scripts/pipeline/run_pipeline.py`, `src/graphcorag/kg_multihop.py`.
   - Main inputs: `hybrid.outputs.jsonl`, KG CSV.
   - Main outputs: updated `hybrid.outputs.jsonl` (in place).

5. Passage-level claim validation pipeline (separate flow)
   - What happens: for each query, retrieves top-k passages, runs external NER on those passages, classifies relation, links tail entities with SapBERT, builds claims, validates claims against KG, writes per-query results.
   - Code location (script/module): `scripts/analyze_with_el_and_intent.py`, `scripts/run_ner_offline.py`, `src/analyzer/*`, `src/passage_processing/claim_builder.py`, `src/kg_validation/*`.
   - Main inputs: queries JSONL, corpus JSONL, KG CSV, KG version string, SapBERT model and FAISS indexes, external NER Python env.
   - Main outputs: analysis JSONL at `--out` containing `claims` and `kg_validation`.

6. Evaluate claim validation output (optional)
   - What happens: computes verdict distribution and precision@KG; optionally emits a JSON summary.
   - Code location (script/module): `scripts/evaluate_claims.py`.
   - Main inputs: output of `scripts/analyze_with_el_and_intent.py`.
   - Main outputs: stdout report and optional JSON file.

## Artifacts and Side Effects
- `scripts/pipeline/run_pipeline.py` writes `queries.for_hybrid.jsonl` and updates `hybrid.outputs.jsonl` in `--out_dir`.
- `scripts/run_hybrid.py` writes `hybrid.outputs.jsonl` and `rl_eval.tsv` to `--out`.
- `scripts/analyze_with_el_and_intent.py` writes per-query results to `--out` and creates `.tmp/<qid>.passage_ner.jsonl` plus `.tmp/tmp_passages.jsonl` during NER.
- `tools/run_pipeline.ps1` creates `out/run_from_raw_<timestamp>/` and may write `run_hybrid.stdout.log`, `coverage.per_query.jsonl`, and `coverage.summary.json` if those scripts run.
- Temporary outputs live under `.tmp/` or `out/`; no pipeline step writes back to `data/` or `config/`.

## Failure-Sensitive Stages
- External NER: `scripts/analyze_with_el_and_intent.py` calls `scripts/run_ner_offline.py` via a separate Python executable; missing spaCy model or env breaks the pipeline.
- SapBERT EL: `src/analyzer/sapbert_linker_v2.py` requires `models/sapbert` and `indices/sapbert/*`; missing files raise errors.
- KG schema mismatch: `src/kg_validation/kg_loader.py` expects CSV headers `head,relation,tail`; other schemas will raise `ValueError`.
- Retrieval memory cost: `src/graphcorag/dense_retriever.py` embeds the full corpus each run and stores a FAISS index in RAM.
- Script mismatch: `tools/run_pipeline.ps1`, `run_pipeline.ps1`, and `run.sh` pass flags that do not exist in the current Python scripts, so they are likely to fail without manual edits.

## Explicit Non-Goals
- No model training or fine-tuning during pipeline execution.
- No automatic index building; FAISS indexes and models are assumed to exist before execution.
- No answer generation or natural-language response synthesis; outputs are JSONL and TSV artifacts.
- No end-to-end integration between the passage-level claim pipeline and the hybrid retrieval pipeline.
- No comprehensive KG reasoning in `run_hybrid.py`; it only checks 1-hop neighbors for two hard-coded relations.
