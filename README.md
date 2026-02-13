# Graph-CORAG

Graph-CORAG is a biomedical claim-validation pipeline that combines NER/EL, relation intent inference, hybrid retrieval, and KG reasoning.

## Motivation

Graph-CORAG is designed for evidence-grounded claim validation rather than free-form answer generation. It takes biomedical query claims, grounds entities to KG-compatible identifiers, retrieves text and graph evidence, and outputs validation signals with traceable artifacts.

## Directory Structure

```text
.
├─ scripts/                  # Executable pipeline stages and utilities
│  ├─ analyze_with_el_and_intent.py
│  ├─ run_hybrid.py
│  └─ pipeline/run_pipeline.py
├─ src/                      # Core library modules
│  ├─ analyzer/
│  ├─ graphcorag/
│  ├─ kg_validation/
│  └─ passage_processing/
├─ config/                   # Required schema and dictionary configs
├─ tools/                    # Operational scripts (smoke test, staging, utilities)
├─ docs/                     # Pipeline docs and operational notes
├─ data/                     # Local input data (not committed)
└─ run_pipeline.ps1          # PowerShell orchestrator
```

## Installation

### 1) Create and activate environment (Conda, Python 3.10)

```powershell
conda create -n gcorag-lite-cu118 python=3.10 -y
conda activate gcorag-lite-cu118
```

### 2) Install dependencies

```powershell
python -m pip install -e .
```

### 3) Optional: verify spaCy/scispaCy model availability

```powershell
python -m spacy validate
python -c "import spacy; spacy.load('en_core_sci_md'); print('ok en_core_sci_md')"
python -c "import spacy; spacy.load('en_ner_bc5cdr_md'); print('ok en_ner_bc5cdr_md')"
python -c "import spacy; spacy.load('en_ner_jnlpba_md'); print('ok en_ner_jnlpba_md')"
```

## Small Data Example and Smoke Test

Use the PowerShell smoke test script to validate pipeline wiring and NER behavior.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_test_pipeline.ps1 -PY "path\to\python.exe"
```

This script performs single/ensemble NER checks, validates output schema fields, builds an adapter JSONL, and runs pipeline output checks.

## Full Pipeline Example

### Stage 1: Analyze queries

```powershell
$PY = "path\to\python.exe"

& $PY scripts\analyze_with_el_and_intent.py `
  --queries data\queries_kg_aligned.jsonl `
  --corpus data\corpus.jsonl `
  --kg data\kg_edges.merged.plus.csv `
  --kg_version kg_edges.merged.plus.csv `
  --retrieval_topk 10 `
  --query_ner_mode ensemble3 `
  --ner_python $PY `
  --out .tmp\pipeline_eval_kg_aligned\queries.analyzed.jsonl
```

### Stage 2: Run pipeline orchestrator (uses analyzed JSONL directly)

`scripts/pipeline/run_pipeline.py` expects analyzed rows from Stage 1 via `--query_jsonl` and internally writes `queries.for_hybrid.jsonl` before launching `scripts/run_hybrid.py`.

Minimum analyzed-row fields expected by the orchestrator:
- `qid`
- `text`
- `candidates` (for head CUI selection)
- `head` (optional)

```powershell
& $PY scripts\pipeline\run_pipeline.py `
  --query_jsonl .tmp\pipeline_eval_kg_aligned\queries.analyzed.jsonl `
  --corpus data\corpus.jsonl `
  --kg data\kg_edges.merged.plus.csv `
  --dict config\umls_dict.txt `
  --overlay config\umls_dict.overlay.json `
  --schema config\relation_schema.json `
  --dense_mod_path src\graphcorag\dense_retriever.py `
  --out_dir .tmp\pipeline_eval_kg_aligned\out
```

### Optional Stage 2b: Adapter transform (only if your upstream schema differs)

If your Stage 1 output does not include `candidates`, create an adapter file first:

```python
import json
from pathlib import Path

src = Path(".tmp/pipeline_eval_kg_aligned/queries.analyzed.jsonl")
dst = Path(".tmp/pipeline_eval_kg_aligned/queries.adapter.jsonl")

rows = []
for line in src.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    ex = json.loads(line)
    rows.append(
        {
            "qid": ex.get("qid"),
            "text": ex.get("text"),
            "head": ex.get("head") or ex.get("head_text"),
            "candidates": ex.get("candidates", []),
        }
    )

with dst.open("w", encoding="utf-8", newline="\n") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```

### Alternate wrapper orchestrator

```powershell
.\run_pipeline.ps1
```

## Data Provisioning Notes

Graph-CORAG expects externally provisioned biomedical resources and derived files. Typical sources include:

- UMLS (terminology and concept linking)
- SIDER (adverse effect relation signals)
- Hetionet and other KG sources for drug-disease interactions

Recommended practice:

- Keep raw downloads and large generated artifacts out of Git.
- Store working corpora/KG files under `data/` locally.
- Maintain reproducible build scripts for derived dictionaries and overlays.

## Running on a Server

1. Clone repository and create the environment.
2. Install project and dependencies.
3. Provision data files to server-local paths.
4. Set interpreter explicitly for reproducibility.
5. Run smoke test before full pipeline runs.

Example:

```bash
git clone https://github.com/Abderrahim-Fezouati/graph-corag.git
cd graph-corag
conda create -n gcorag-lite-cu118 python=3.10 -y
conda activate gcorag-lite-cu118
python -m pip install -e .
```

Then run equivalent pipeline commands with server data paths.

## Supported vs Legacy Scripts

Supported production path for end-to-end runs:
- `scripts/analyze_with_el_and_intent.py`
- `scripts/pipeline/run_pipeline.py`
- `scripts/run_hybrid.py`
- `scripts/run_ner_offline.py`

Legacy/experimental content exists in the repository (for example under `archives/` and `src/analyzer/old_sapbert_scripts/`) and is not part of the supported pipeline path.

## Contact

- Author: Abderrahim Fezouati
- Repository: https://github.com/Abderrahim-Fezouati/graph-corag
