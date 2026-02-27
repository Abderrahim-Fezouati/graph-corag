## .git
Purpose: Git metadata and history.
Primary Responsibilities: store objects, refs, and index for version control.
Key Files (if any): config, objects/, refs/.
Inputs: git commands.
Outputs: commit history, branch state.
Dependencies: git.
Notes / Risks: manual edits can corrupt the repository.

## .tmp
Purpose: transient scratch and run artifacts.
Primary Responsibilities: keep intermediate JSONL outputs and ad-hoc run data.
Key Files (if any): pipeline_eval_100/, Q###.passage_ner.jsonl, queries_eval_100.analyzed.jsonl.
Inputs: outputs from `scripts/` and `src/passage_processing`.
Outputs: intermediate JSONL used for eval/debug.
Dependencies: produced by pipeline scripts.
Notes / Risks: large and stale; retention is unclear.

## .vscode
Purpose: editor workspace configuration.
Primary Responsibilities: store VS Code settings for this repo.
Key Files (if any): settings.json.
Inputs: developer/editor preferences.
Outputs: editor behavior.
Dependencies: VS Code.
Notes / Risks: not part of runtime.

## archives
Purpose: historical backups and old run artifacts.
Primary Responsibilities: preserve past outputs, indexes, and .bak copies.
Key Files (if any): exp_20251123_2239/, run_smoke/, large_backups_20251117_132909/, *.bak.
Inputs: copied data/models/outputs.
Outputs: archived artifacts only.
Dependencies: none at runtime.
Notes / Risks: very large; easy to confuse with current outputs.

## config
Purpose: configuration and vocab/alias resources for entity linking and KG schema.
Primary Responsibilities: provide UMLS dicts, overlays, relation schema, normalization rules, alias lists.
Key Files (if any): umls_dict.txt, umls_dict.overlay.json, relation_schema.json, name_normalization.yaml, surf2cui.json.
Inputs: curated dictionaries and schema definitions.
Outputs: consumed by scripts and `src` modules.
Dependencies: referenced by `scripts/`, `src/`, `kb/`.
Notes / Risks: schema/dict drift affects EL and KG validation.

## data
Purpose: primary datasets for corpus, KG edges, queries, and training sets.
Primary Responsibilities: hold raw KG/corpus, processed derivatives, and external source drops.
Key Files (if any): corpus.jsonl, kg_edges.merged.plus.csv, queries_eval_100.jsonl, processed/, intent classifier/, new data/.
Inputs: external datasets and script-generated derivatives.
Outputs: processed CSV/JSONL used by pipeline and indices.
Dependencies: consumed by `scripts/`, `src/`, `tests/`.
Notes / Risks: mixed raw/processed/legacy; version alignment required.

## indices
Purpose: prebuilt concept indexes for fast entity linking.
Primary Responsibilities: store FAISS index files and row metadata by entity type.
Key Files (if any): sapbert/Disease/index.faiss, sapbert/Drug/index.faiss, rows.jsonl.
Inputs: SapBERT embeddings and alias rows from config/data.
Outputs: index files used during retrieval/EL.
Dependencies: built by `kb/` or `scripts/`; used by `src/analyzer`.
Notes / Risks: must match model/version of alias data.

## kb
Purpose: KB indexing utilities.
Primary Responsibilities: build alias rows and FAISS indexes from overlays and aliases.
Key Files (if any): build_indices.py.
Inputs: config overlays and aliases; model name.
Outputs: index directories (typically under `indices/`).
Dependencies: numpy, torch, transformers, faiss.
Notes / Risks: compute-heavy; outputs are not validated here.

## models
Purpose: model artifacts and caches.
Primary Responsibilities: store pretrained weights, intent classifiers, HF cache, zip snapshots.
Key Files (if any): sapbert/model.safetensors, biobert-base-cased-v1.2/, intent_classifier_*.
Inputs: downloaded or trained model files.
Outputs: weights consumed by analyzers, retrievers, index builders.
Dependencies: transformers/torch runtime.
Notes / Risks: multiple versions can desync with indices.

## scripts
Purpose: executable pipeline, training, and evaluation entry points.
Primary Responsibilities: run hybrid retrieval; build indexes/catalogs; train intent classifier; evaluation utilities.
Key Files (if any): run_hybrid.py, pipeline/run_pipeline.py, build_* scripts, evaluation/*.py.
Inputs: config/, data/, models/, indices/.
Outputs: out directories, processed data, index builds, eval summaries.
Dependencies: `src` modules and their external libs.
Notes / Risks: Windows-specific scripts and .bak files can mislead.

## src
Purpose: core application library.
Primary Responsibilities: retrieval (text/dense/KG multihop), analysis (NER/EL/intent), passage processing, KG validation.
Key Files (if any): graphcorag/, analyzer/, passage_processing/, kg_validation/.
Inputs: config dictionaries, data corpus/KG, model weights, indices.
Outputs: in-memory results and JSONL outputs when invoked by scripts.
Dependencies: torch/transformers/faiss (observed in modules); standard libs.
Notes / Risks: .bak files indicate refactors; API changes impact scripts/tests.

## tests
Purpose: test suite and gold data.
Primary Responsibilities: validate pipeline components and KG multihop behavior.
Key Files (if any): test_run_pipeline.py, test_kg_multihop.py, gold.*.jsonl.
Inputs: `src` modules and sample datasets.
Outputs: test results via runner.
Dependencies: test runner not specified; runtime deps required.
Notes / Risks: tests likely require local models/data.

## tools
Purpose: auxiliary utilities and data preparation helpers.
Primary Responsibilities: dataset prep, dict building, cache generation, cleanup, PowerShell automation.
Key Files (if any): run_pipeline.ps1, generate_retrieval_cache.py, dict_builder/, datasets/, sample_data/.
Inputs: data/, config/, scripts/.
Outputs: patched datasets, sample inputs, cache files.
Dependencies: PowerShell and Python.
Notes / Risks: one-off tools; environment assumptions.

## utils
Purpose: small standalone helpers.
Primary Responsibilities: model conversion and metadata generation.
Key Files (if any): convert_biobert_to_safetensors.py, generate_type_metadata.py.
Inputs: model artifacts or type lists.
Outputs: converted model files or metadata.
Dependencies: Python libs referenced by scripts.
Notes / Risks: narrow usage; format compatibility matters.
