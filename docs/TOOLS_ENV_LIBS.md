# Tools, Environments, Libraries

## Tools
- Pipeline orchestrators: `scripts/pipeline/run_pipeline.py`, `scripts/run_hybrid.py`, `scripts/analyze_with_el_and_intent.py`.
- NER runner: `scripts/run_ner_offline.py`.
- PowerShell wrappers: `run_pipeline.ps1`, `tools/run_pipeline.ps1`.
- Index builders: `kb/build_indices.py`, `scripts/build_sapbert_index.py`, `scripts/build_umls_sapbert_index.py`, `scripts/build_sapbert_indexes_phase11.py`.
- Evaluation utilities: `scripts/evaluate_claims.py`, `scripts/summarize_pipeline_results.py`, `scripts/evaluation/*.py`.

## Environments
- Conda env `gcorag-lite-cu118` (used in `run_pipeline.ps1` and `tools/run_pipeline.ps1`).
- Conda env `ner-el-py310` (external NER in `scripts/analyze_with_el_and_intent.py`; default path `F:\conda-envs\ner-el-py310\python.exe`).
- Environment snapshots: `env_conda_list.txt`, `env_full_report.txt`, `env_pip_freeze.txt`.

## Libraries
- `torch`, `transformers`: `src/analyzer/relation_classifier.py`, `src/analyzer/sapbert_linker_v2.py`, `kb/build_indices.py`.
- `faiss`: `src/graphcorag/dense_retriever.py`, `kb/build_indices.py`, `src/analyzer/sapbert_linker_v2.py`.
- `sentence_transformers`: `src/graphcorag/dense_retriever.py`.
- `spacy` (model `en_ner_bc5cdr_md`): `scripts/run_ner_offline.py`.
- `numpy`: `src/graphcorag/dense_retriever.py`, `kb/build_indices.py`, `src/analyzer/sapbert_linker_v2.py`.
- `pandas`: `scripts/summarize_pipeline_results.py`.
