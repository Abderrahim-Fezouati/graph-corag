# ============================
# Run GCORAG-LITE Full Pipeline
# ============================

param(
  [string]$RunDir = "",
  [string]$WorkDir = ""
)

$PY = "C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe"
if (-not (Test-Path $PY)) { throw "Python not found: $PY" }

if ($RunDir) {
  if (-not (Test-Path $RunDir)) {
    throw "RunDir not found: $RunDir"
  }
  if (-not (Test-Path (Join-Path $RunDir "inputs.json"))) {
    throw "inputs.json not found in RunDir: $RunDir"
  }
  $OUTDIR = Join-Path $RunDir "outputs"
  New-Item -ItemType Directory -Force -Path $OUTDIR | Out-Null
} else {
  $OUTDIR = ".tmp\pipeline_eval_kg_aligned\out"
}

# ========== 1. Analyze (Query + Passage NER via internal calls) ==========
# ensure correct Python import path
$env:PYTHONPATH = (Join-Path (Get-Location) "src")

& $PY scripts\analyze_with_el_and_intent.py `
  --queries data\queries_kg_aligned.jsonl `
  --corpus data\corpus.jsonl `
  --kg data\kg_edges.merged.plus.csv `
  --kg_version kg_edges.merged.plus.csv `
  --retrieval_topk 10 `
  --out .tmp\pipeline_eval_kg_aligned\queries.analyzed.jsonl


# ========== 3. Run Hybrid Retrieval + KG Reasoning ==========
& $PY scripts\run_hybrid.py `
  --proj "eval_kg_aligned" `
  --corpus data\corpus.jsonl `
  --kg data\kg_edges.merged.plus.csv `
  --dict config\umls_dict.txt `
  --overlay config\umls_dict.overlay.json `
  --schema config\relation_schema.json `
  --queries .tmp\pipeline_eval_kg_aligned\queries.for_hybrid.jsonl `
  --out $OUTDIR `
  --topk 80 `
  --bm25_mod_path "src\graphcorag\text_retriever.py" `
  --dense_mod_path "src\graphcorag\dense_retriever.py"

Write-Host "==============================="
Write-Host "Pipeline Completed Successfully!"
Write-Host "==============================="
