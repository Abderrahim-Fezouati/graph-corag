# KB Build From Raw Data

This document defines the reproducible raw-to-artifact build path for Graph-CORAG.

## Scope

The KB build writes versioned artifacts under:

`data_processed/graphcorag/<version>/`

Main outputs:

- `entity_catalog.jsonl`
- `kg_edges.umls.csv`
- `kg_edges.sider.csv`
- `kg_edges.ctd.csv`
- `kg_edges.merged.csv`
- `kg_edges.merged.plus.csv`
- `umls_dict.txt`
- `umls_dict.overlay.json`
- `sapbert_index/index.faiss`
- `sapbert_index/rows.jsonl`
- `sapbert_index/manifest.json`
- `build_manifest.json`

## Required Raw Inputs

Place these datasets under one root (example: `data/new data/necessary raw data/`):

- `UMLS/MRCONSO.RRF`
- `UMLS/MRREL.RRF`
- `UMLS/MRSTY.RRF`
- `RxNorm/RXNCONSO.RRF`
- `Mesh/desc2025.xml`
- `DrugBank/drugbank.xml`
- `SIDER/drug_names.tsv`
- `SIDER/meddra_all_se.tsv`
- `CTD/CTD_chemicals_diseases.csv.gz` (or `.csv`)

## Stage Scripts

- `kb/build/01_build_entity_catalog.py`
- `kb/build/02_build_edges_umls.py`
- `kb/build/03_build_edges_sider.py`
- `kb/build/04_build_edges_ctd.py`
- `kb/build/05_merge_edges.py`
- `kb/build/06_build_umls_dict_and_overlay.py`
- `kb/build/07_build_sapbert_index.py`
- `kb/build/build_all.py`

Each stage accepts:

- `--raw_root`
- `--out_dir`
- `--version`

Each stage writes a stage report:

- `stage_01_report.json` … `stage_07_report.json`

## One-Command Build

### Windows (PowerShell)

```powershell
python -m kb.build.build_all `
  --raw_root "data\new data\necessary raw data" `
  --out_root "data_processed\graphcorag" `
  --version "v1" `
  --model_name "models/sapbert" `
  --batch_size 64 `
  --local_files_only
```

### Linux (bash)

```bash
python -m kb.build.build_all \
  --raw_root "data/new data/necessary raw data" \
  --out_root "data_processed/graphcorag" \
  --version "v1" \
  --model_name "models/sapbert" \
  --batch_size 64 \
  --local_files_only
```

## Runtime Integration

The runtime path stays unchanged. Point runtime inputs to a chosen version directory:

- KG: `data_processed/graphcorag/<version>/kg_edges.merged.plus.csv`
- Dict: `data_processed/graphcorag/<version>/umls_dict.txt`
- Overlay: `data_processed/graphcorag/<version>/umls_dict.overlay.json`
- SapBERT index: `data_processed/graphcorag/<version>/sapbert_index/`

Current runtime scripts that consume these artifact formats:

- `scripts/run_hybrid.py`
- `scripts/pipeline/run_pipeline.py`
- `src/analyzer/sapbert_linker_v2.py`

## Design Notes

- Edge CSV is written with `h,r,t,source,score,evidence` to keep compatibility with current runtime loader logic.
- UMLS edge relations are filtered to a curated subset and type-checked using MRSTY-derived entity categories.
- SIDER and CTD edges are mapped through the built entity catalog using normalized surface matching.
- Build is deterministic:
  - stable sorted writes
  - stage reports with counts
  - `build_manifest.json` with file hashes and provenance

## License and Data Governance Warning

UMLS and some biomedical data sources are license-restricted.

- Do **not** publish raw UMLS files publicly.
- Do **not** publish restricted derived outputs publicly unless license terms permit redistribution.
- Keep raw data and restricted artifacts out of public repositories.

