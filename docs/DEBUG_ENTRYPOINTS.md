# Debug Entry Points

## Retrieval Issues
Symptoms:
- Empty or low-quality `hybrid.outputs.jsonl` results.
- Retrieval returns zero docs or unexpected IDs.
Relevant Files:
- `scripts/run_hybrid.py`
- `src/graphcorag/text_retriever.py`
- `src/graphcorag/dense_retriever.py`
Key Functions:
- `_load_jsonl`, `iter_kg_edges`, `main` in `scripts/run_hybrid.py`
- `TextRetriever.__init__`, `TextRetriever.search` in `src/graphcorag/text_retriever.py`
- `DenseRetriever.__init__`, `DenseRetriever.search` in `src/graphcorag/dense_retriever.py`
Notes:
- `scripts/run_hybrid.py` imports retrievers by file path; wrong paths silently change behavior or fail at import.

## Entity Linking / NER Issues
Symptoms:
- Missing or empty `claims` or `kg_validation` in analysis output.
- `passage_ner` JSONL empty or missing entities.
Relevant Files:
- `scripts/analyze_with_el_and_intent.py`
- `scripts/run_ner_offline.py`
- `src/analyzer/entity_linking_adapter.py`
- `src/analyzer/sapbert_linker_v2.py`
- `src/analyzer/relation_classifier.py`
- `src/passage_processing/claim_builder.py`
Key Functions:
- `run_passage_ner`, `main` in `scripts/analyze_with_el_and_intent.py`
- `main` in `scripts/run_ner_offline.py`
- `ELAdapter.link_mentions` in `src/analyzer/entity_linking_adapter.py`
- `SapBERTLinkerV2.link` in `src/analyzer/sapbert_linker_v2.py`
- `RelationClassifier.predict` in `src/analyzer/relation_classifier.py`
- `build_claims` in `src/passage_processing/claim_builder.py`
Notes:
- NER runs in an external Python environment specified by `--ner_python`; path is hard-coded by default.

## Index / Model Mismatch
Symptoms:
- FileNotFoundError for FAISS indexes or model weights.
- Entity linker returns no candidates due to low scores or missing index types.
Relevant Files:
- `src/analyzer/sapbert_linker_v2.py`
- `models/sapbert/`
- `indices/sapbert/`
- `kb/build_indices.py`
- `scripts/build_umls_sapbert_index.py`
Notes:
- `sapbert_linker_v2.py` expects `indices/sapbert/{Drug,Disease}/index.faiss` and `rows.jsonl` plus `models/sapbert`.

## KG Graph Construction
Symptoms:
- KG load errors or missing edges.
- All KG checks return unsupported/empty.
Relevant Files:
- `src/graphcorag/kg_loader.py`
- `src/kg_validation/kg_loader.py`
- `data/kg_edges.merged.plus.csv` (and other KG CSVs under `data/`)
Key Functions:
- `KG.__init__` in `src/graphcorag/kg_loader.py`
- `KGLoader._load` in `src/kg_validation/kg_loader.py`
Notes:
- `src/kg_validation/kg_loader.py` requires CSV headers `head,relation,tail`; other schemas will fail.

## KG Validation / Verdict Errors
Symptoms:
- Unexpected verdict distributions (all unsupported, many contradicted).
- `kg_validation` fields missing or invalid.
Relevant Files:
- `src/kg_validation/kg_validator.py`
- `src/kg_validation/verdict_types.py`
- `src/kg_validation/predicate_schema.py`
- `scripts/evaluate_claims.py`
Key Functions:
- `KGValidator.validate_claim` in `src/kg_validation/kg_validator.py`
- `is_antagonistic` in `src/kg_validation/predicate_schema.py`
Notes:
- Verdict logic depends on normalized predicates and a fixed relaxed predicate map.

## Evaluation / Testing Mismatches
Symptoms:
- Test failures or inconsistent pipeline outputs across runs.
- Summary TSV/JSON does not match expected structure.
Relevant Files:
- `tests/test_run_pipeline.py`
- `tests/test_kg_multihop.py`
- `scripts/pipeline/run_pipeline.py`
- `scripts/summarize_pipeline_results.py`
- `scripts/evaluate_claims.py`
Notes:
- Pipeline tests assume `scripts/pipeline/run_pipeline.py` writes `queries.for_hybrid.jsonl` and mutates `hybrid.outputs.jsonl` in place.
