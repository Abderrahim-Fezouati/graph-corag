# Pipeline Execution

## Entrypoints (runnable scripts)
- `scripts/analyze_with_el_and_intent.py`
- `scripts/pipeline/run_pipeline.py`
- `scripts/run_hybrid.py`
- `scripts/run_ner_offline.py` (invoked by the analyzer; not typically run directly)

## Non-entrypoint modules (imported by scripts)
- `src/graphcorag/text_retriever.py`
- `src/graphcorag/dense_retriever.py`
- `src/graphcorag/kg_multihop.py`
- `src/kg_validation/kg_loader.py`
- `src/kg_validation/kg_validator.py`

## Stage-by-stage execution

### Stage 1: Analysis (query-level NER/EL + relation prediction)
Script: `scripts/analyze_with_el_and_intent.py`

Inputs:
- `--queries` JSONL (qid, text)
- `--corpus` JSONL (document corpus)
- `--kg` KG CSV
- `--kg_version` (usually filename of KG CSV)

Output:
- `--out` analyzed queries JSONL

### Stage 2: Adapter (data-only, when needed)
Purpose: produce pipeline-ready queries for `scripts/pipeline/run_pipeline.py`.

Inputs:
- analyzed queries JSONL (from Stage 1)

Output:
- adapter JSONL with `qid`, `text`, `relations`, `head`, and `candidates`

### Stage 3: Pipeline orchestration
Script: `scripts/pipeline/run_pipeline.py`

Inputs:
- `--query_jsonl` adapter JSONL
- `--corpus` JSONL
- `--kg_csv` KG CSV
- `--dict`, `--overlay`, `--schema`
- `--dense_mod_path` path to Python module: `src/graphcorag/dense_retriever.py`

Outputs:
- `<out_dir>/queries.for_hybrid.jsonl`
- `<out_dir>/hybrid.outputs.jsonl`
- `<out_dir>/rl_eval.tsv`

### Stage 4: Hybrid retrieval (standalone, optional)
Script: `scripts/run_hybrid.py`

Inputs:
- `--corpus`, `--kg`, `--dict`, `--overlay`, `--schema`
- `--queries` (queries.for_hybrid.jsonl)
- `--dense_mod_path` (Python module path)

Outputs:
- `hybrid.outputs.jsonl`, `rl_eval.tsv`

## Smoke test (1 query) - Windows cmd
```
cd /d D:\graph-corag-clean

:: Create 1-line query file
if not exist data\queries_kg_aligned.1.jsonl (
  powershell -NoProfile -Command "Get-Content -TotalCount 1 data\queries_kg_aligned.jsonl | Set-Content data\queries_kg_aligned.1.jsonl"
)

:: Stage 1: analysis
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe scripts\analyze_with_el_and_intent.py ^
  --queries data\queries_kg_aligned.1.jsonl ^
  --corpus data\corpus.jsonl ^
  --kg data\kg_edges.merged.plus.csv ^
  --kg_version kg_edges.merged.plus.csv ^
  --retrieval_topk 10 ^
  --out .tmp\pipeline_test_full\queries.analyzed.jsonl ^
  1> .tmp\pipeline_test_full\analyze.stdout.txt ^
  2> .tmp\pipeline_test_full\analyze.stderr.txt

:: Stage 1 (ensemble3 query NER, explicit ner python)
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe scripts\analyze_with_el_and_intent.py ^
  --queries data\queries_kg_aligned.1.jsonl ^
  --corpus data\corpus.jsonl ^
  --kg data\kg_edges.merged.plus.csv ^
  --kg_version kg_edges.merged.plus.csv ^
  --retrieval_topk 10 ^
  --query_ner_mode ensemble3 ^
  --query_ner_models en_core_sci_md,en_ner_bc5cdr_md,en_ner_jnlpba_md ^
  --ner_python C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe ^
  --out .tmp\pipeline_test_full\queries.analyzed.ensemble3.jsonl

:: Stage 2: adapter (data-only)
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe -c "import json; src=r'.tmp\\pipeline_test_full\\queries.analyzed.jsonl'; out=r'.tmp\\pipeline_test_full\\queries.adapter.jsonl';
import pathlib; f=open(src,'r',encoding='utf-8'); w=open(out,'w',encoding='utf-8');
for line in f:
  o=json.loads(line); row={'qid':o.get('qid'),'text':o.get('text'),'relations':['ADVERSE_EFFECT'],'head':o.get('head_cui'),'candidates':[{'cui':o.get('head_cui'),'score':o.get('head_score'),'source':o.get('head_source')}]};
  w.write(json.dumps(row)+'\n')"

:: Stage 3: pipeline
C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe scripts\pipeline\run_pipeline.py ^
  --query_jsonl .tmp\pipeline_test_full\queries.adapter.jsonl ^
  --out_dir .tmp\pipeline_test_full\run_pipeline_out ^
  --kg_csv data\kg_edges.merged.plus.csv ^
  --corpus data\corpus.jsonl ^
  --dict config\umls_dict.txt ^
  --overlay config\umls_dict.overlay.json ^
  --schema config\relation_schema.json ^
  --dense_mod_path src\graphcorag\dense_retriever.py
```

## Full pipeline (multi-query) - Windows cmd
```
cd /d D:\graph-corag-clean

C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe scripts\analyze_with_el_and_intent.py ^
  --queries data\queries_kg_aligned.jsonl ^
  --corpus data\corpus.jsonl ^
  --kg data\kg_edges.merged.plus.csv ^
  --kg_version kg_edges.merged.plus.csv ^
  --retrieval_topk 10 ^
  --out .tmp\pipeline_full\queries.analyzed.jsonl

C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe scripts\pipeline\run_pipeline.py ^
  --query_jsonl .tmp\pipeline_full\queries.adapter.jsonl ^
  --out_dir .tmp\pipeline_full\run_pipeline_out ^
  --kg_csv data\kg_edges.merged.plus.csv ^
  --corpus data\corpus.jsonl ^
  --dict config\umls_dict.txt ^
  --overlay config\umls_dict.overlay.json ^
  --schema config\relation_schema.json ^
  --dense_mod_path src\graphcorag\dense_retriever.py
```
