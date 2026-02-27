

param(
    [string]$Root = (Get-Location).Path,
    [string]$CondaEnv = "gcorag-lite-cu118",
    [string]$Bm25Path = "",
    [string]$DensePath = "",
    [switch]$SkipCondaActivate,
    [switch]$SkipCoverage
)

Set-StrictMode -Version Latest

function AbortIfNot([bool]$cond, [string]$message) {
    if (-not $cond) {
        Write-Error $message
        exit 1
    }
}

Write-Host "Using project root: $Root"

# 0) Activate conda env (optional)
if (-not $SkipCondaActivate) {
    Write-Host "Activating conda env: $CondaEnv"
    try {
        & conda activate $CondaEnv
    } catch {
        Write-Warning "Could not run 'conda activate $CondaEnv' in this session. If conda isn't initialized for PowerShell, please activate manually before running the script. Continuing..."
    }
} else {
    Write-Host "Skipping conda activation (SkipCondaActivate set)."
}

# 1) Define all important paths (based on tree)
$RAW     = Join-Path $Root "data\queries.raw.40.jsonl"
$DICT    = Join-Path $Root "config\umls_dict.txt"
$OVERLAY = Join-Path $Root "config\umls_dict.overlay.json"
$KG      = Join-Path $Root "data\kg_edges.merged.plus.csv"
$SCHEMA  = Join-Path $Root "config\relation_schema.json"
$CORPUS  = Join-Path $Root "data\corpus.jsonl"

Write-Host "Paths set:" -ForegroundColor Cyan
Write-Host " RAW     : $RAW"
Write-Host " DICT    : $DICT"
Write-Host " OVERLAY : $OVERLAY"
Write-Host " KG      : $KG"
Write-Host " SCHEMA  : $SCHEMA"
Write-Host " CORPUS  : $CORPUS"

# quick sanity checks for required files
AbortIfNot (Test-Path $RAW) "Raw queries missing: $RAW"
AbortIfNot (Test-Path $DICT) "Dictionary missing: $DICT"
AbortIfNot (Test-Path $KG) "KG edges missing: $KG"
AbortIfNot (Test-Path $SCHEMA) "Relation schema missing: $SCHEMA"

# 1b) BM25 & dense index auto-detect (best-effort)
$indicesDir = Join-Path $Root "indices"
$BM25 = $null; $DENSE = $null
if (Test-Path $indicesDir) {
    Write-Host "Auto-detecting indices under $indicesDir"
    $bm25File = Get-ChildItem -Path $indicesDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'bm25' } | Select-Object -First 1
    if ($bm25File) { $BM25 = $bm25File.FullName }

    $denseFile = Get-ChildItem -Path $indicesDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'sapbert|dense|dpr' } | Select-Object -First 1
    if ($denseFile) { $DENSE = $denseFile.FullName }
}

if ($BM25) { Write-Host "BM25 index detected: $BM25" } else { Write-Warning 'BM25 index NOT detected automatically. You can set variable manually inside this script or run: $BM25 = ''F:\your\path''' }
if ($DENSE) { Write-Host "Dense index detected: $DENSE" } else { Write-Warning 'Dense/SapBERT index NOT detected automatically. You can set variable manually inside this script or run: $DENSE = ''F:\your\path''' }

# Allow CLI overrides for BM25 / DENSE paths
if ($Bm25Path -ne "") { $BM25 = $Bm25Path; Write-Host "BM25 overridden by CLI: $BM25" }
if ($DensePath -ne "") { $DENSE = $DensePath; Write-Host "Dense overridden by CLI: $DENSE" }

# If either index is missing, still continue but warn — run_hybrid.py may accept missing depending on mode.

# 2) Create a fresh run folder
$STAMP = Get-Date -Format "yyyyMMdd_HHmm"
$RUN   = Join-Path $Root ("out\run_from_raw_$STAMP")
New-Item -ItemType Directory -Force -Path $RUN | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RUN "cache") | Out-Null
Write-Host "Run folder: $RUN"

# 3) STEP 1 – Pre-structure & enrich raw queries
$preScript = Join-Path $Root "scripts\pre_analyze_raw.py"
AbortIfNot (Test-Path $preScript) "Pre-analyze script not found: $preScript"
$out_enriched = Join-Path $RUN "queries.structured.jsonl"

Write-Host "Running pre_analyze_raw.py -> $out_enriched"
& python $preScript `
    --in_raw $RAW `
    --out_enriched $out_enriched `
    --dict $DICT `
    --overlay $OVERLAY `
    --kg $KG `
    --schema $SCHEMA

AbortIfNot (Test-Path $out_enriched) "Step 1 FAILED: $out_enriched missing."
Write-Host "Step 1 complete." -ForegroundColor Green

# 4) STEP 2 – Intent detection + optional SapBERT EL (type-aware)
# New wrapper script: it will try to use SapBERT/index when available, but falls back
# to a fast dict-based linking so the pipeline can run on lightweight machines.
$analyzeScript = Join-Path $Root "scripts\analyze_with_el_and_intent.py"
AbortIfNot (Test-Path $analyzeScript) "Analyzer wrapper script not found: $analyzeScript"
$out_analyzed = Join-Path $RUN "queries.analyzed.jsonl"

# Auto-detect SapBERT index dir (common backup/artifacts paths)
$SAPBERT_DIR = $null
$cand1 = Join-Path $Root "large_backups_20251117_132909\artifacts\sapbert"
if (Test-Path $cand1) { $SAPBERT_DIR = $cand1 }
$cand2 = Join-Path $Root "indices\sapbert"
if (-not $SAPBERT_DIR -and Test-Path $cand2) { $SAPBERT_DIR = $cand2 }

# Auto-detect an intent classifier under models/
$INTENT_MODEL = $null
if (Test-Path (Join-Path $Root 'models')) {
    $m = Get-ChildItem -Path (Join-Path $Root 'models') -Directory | Where-Object { $_.Name -match 'intent' } | Sort-Object Name -Descending | Select-Object -First 1
    if ($m) { $INTENT_MODEL = $m.FullName }
}

Write-Host "Running analyze_with_el_and_intent.py -> $out_analyzed (will use SapBERT index if found)"
$anArgs = @('--dict', $DICT, '--input', $out_enriched, '--out', $out_analyzed)
if ($SAPBERT_DIR) { $anArgs += @('--index_dir', $SAPBERT_DIR) } else { $anArgs += @('--use_dict') }
if ($INTENT_MODEL) { $anArgs += @('--intent_model_dir', $INTENT_MODEL); Write-Host "Intent model detected: $INTENT_MODEL" }

& python $analyzeScript @anArgs

AbortIfNot (Test-Path $out_analyzed) "Step 2 FAILED: $out_analyzed missing."
Write-Host "Step 2 complete." -ForegroundColor Green

# 5) STEP 3 – Hybrid retrieval + KG validation
$hybridScript = Join-Path $Root "scripts\run_hybrid.py"
AbortIfNot (Test-Path $hybridScript) "Hybrid script not found: $hybridScript"

Write-Host "Running run_hybrid.py -> output folder: $RUN"

# Require BM25 and Dense paths (either auto-detected or passed via CLI)
if (($null -eq $BM25) -or ($BM25 -eq "") -or ($null -eq $DENSE) -or ($DENSE -eq "")) {
    Write-Error "BM25 and Dense index paths are required for run_hybrid.\nProvide them with -Bm25Path and -DensePath when invoking this script, or place suitable files under $indicesDir for auto-detection.\nExample: & .\tools\run_pipeline.ps1 -Bm25Path 'F:\path\to\bm25' -DensePath 'F:\path\to\dense' -SkipCondaActivate"
    exit 2
}

$bm25Arg = $BM25
$denseArg = $DENSE

$hybridArgs = @(
    '--proj', $Root,
    '--corpus', $CORPUS,
    '--kg', $KG,
    '--dict', $DICT,
    '--overlay', $OVERLAY,
    '--schema', $SCHEMA,
    '--queries', $out_analyzed,
    '--out', $RUN,
    '--topk', '80',
    '--mode', 'both'
)
if ($bm25Arg -ne '') { $hybridArgs += @('--bm25_mod_path', $bm25Arg) }
if ($denseArg -ne '') { $hybridArgs += @('--dense_mod_path', $denseArg) }

# Run hybrid and capture logs
$hybridLog = Join-Path $RUN "run_hybrid.stdout.log"
Write-Host "Running run_hybrid.py (logging to $hybridLog)"
try {
    & python $hybridScript @hybridArgs > $hybridLog 2>&1
} catch {
    Write-Warning "run_hybrid.py exited with a non-zero status; see $hybridLog for details."
}

# Basic post-checks (look for typical outputs)
$expectedHybridOut = Join-Path $RUN "hybrid.outputs.jsonl"
AbortIfNot (Test-Path $expectedHybridOut) "Step 3 may have failed: expected $expectedHybridOut not found. Check $RUN for logs."
Write-Host "Step 3 complete." -ForegroundColor Green

# 6) Optional – Text coverage metrics
if (-not $SkipCoverage) {
    $coverageScript = Join-Path $Root "scripts\evaluation\text_coverage_metrics.py"
    if (Test-Path $coverageScript) {
        Write-Host "Running optional text coverage metrics"
        $cache = Join-Path $RUN "cache\retrieval.cache.jsonl"
        # If cache not present, try to generate it automatically using our helper
        if (-not (Test-Path $cache)) {
            $genScript = Join-Path $Root "tools\generate_retrieval_cache.py"
            if (Test-Path $genScript) {
                Write-Host "Cache not found. Generating retrieval cache using $genScript"
                & python $genScript `
                    --queries $out_analyzed `
                    --bm25 $BM25 `
                    --dense $DENSE `
                    --out $cache `
                    --topk 80
                if (-not (Test-Path $cache)) {
                    Write-Warning "Cache generation attempted but $cache still missing. Coverage will be skipped."
                }
            } else {
                Write-Warning "Cache not found and generator script missing ($genScript). Skipping coverage."
            }
        }

        if (Test-Path $cache) {
            & python $coverageScript `
                --queries $expectedHybridOut `
                --corpus $CORPUS `
                --cache $cache `
                --out_per_query (Join-Path $RUN "coverage.per_query.jsonl") `
                --out_summary (Join-Path $RUN "coverage.summary.json") `
                --ks 10 20 50 80

            if (Test-Path (Join-Path $RUN "coverage.summary.json")) {
                Write-Host "Coverage summary written to: $(Join-Path $RUN "coverage.summary.json")"
            } else {
                Write-Warning "Coverage script ran but summary file not found or queries=0 (this can be normal for queries without required entities)."
            }
        }
    } else {
        Write-Warning "Coverage script not found at $coverageScript. Skipping coverage step."
    }
} else {
    Write-Host "Skipping coverage step (SkipCoverage set)."
}

Write-Host "\n--- Run complete ---" -ForegroundColor Cyan
Write-Host "Run folder: $RUN"
Get-ChildItem -Path $RUN -Depth 1 | ForEach-Object { Write-Host $_.Name }

Write-Host "If any step fails, paste the failing step's stderr/stdout or the script-specific log (if present) and I'll help debug it."