param(
    [string]$PY = "C:\Users\Abdou\miniconda3\envs\gcorag-lite-cu118\python.exe"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
# Do not treat native stderr output as terminating PowerShell errors.
if ($null -ne (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue)) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Write-Info([string]$msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Pass([string]$msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }

function Invoke-PythonLogged {
    param(
        [string]$Label,
        [string[]]$CmdArgs,
        [string]$StdoutPath,
        [string]$StderrPath
    )
    $cmdDisplay = "$PY " + ($CmdArgs -join " ")
    Write-Info $Label
    Write-Host "  CMD: $cmdDisplay"
    Write-Host "  STDOUT: $StdoutPath"
    Write-Host "  STDERR: $StderrPath"

    $proc = Start-Process -FilePath $PY -ArgumentList $CmdArgs -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    if ($proc.ExitCode -ne 0) {
        throw "Command failed with exit code $($proc.ExitCode): $cmdDisplay`nSee logs: $StdoutPath , $StderrPath"
    }
}

function Assert-NonEmptyFile {
    param([string]$Path)
    if (-not (Test-Path $Path)) { throw "Missing file: $Path" }
    $item = Get-Item $Path
    if ($item.Length -le 0) { throw "File is empty: $Path" }
    Write-Pass "Non-empty file: $Path ($($item.Length) bytes)"
}

try {
    $repoRoot = (Get-Location).Path
    Write-Info "Repo root: $repoRoot"
    if (-not (Test-Path "pyproject.toml")) {
        throw "Not in repo root (pyproject.toml missing). Current dir: $repoRoot"
    }
    Write-Pass "Repo root verified (pyproject.toml found)."

    if (-not (Test-Path $PY)) { throw "Python interpreter not found: $PY" }
    $ResolvedPY = (Resolve-Path $PY).Path
    Write-Pass "Using Python: $ResolvedPY"

    $required = @(
        "scripts\analyze_with_el_and_intent.py",
        "scripts\pipeline\run_pipeline.py",
        "data\corpus.jsonl",
        "data\kg_edges.merged.plus.csv",
        "config\umls_dict.txt",
        "config\umls_dict.overlay.json",
        "config\relation_schema.json",
        "src\graphcorag\dense_retriever.py"
    )
    foreach ($p in $required) {
        if (-not (Test-Path $p)) { throw "Missing required file: $p" }
    }

    $queryOne = "data\queries_kg_aligned.1.jsonl"
    $queryFull = "data\queries_kg_aligned.jsonl"
    if (-not (Test-Path $queryOne)) {
        if (-not (Test-Path $queryFull)) { throw "Missing query file: $queryFull" }
        Get-Content -TotalCount 1 $queryFull | Set-Content $queryOne
        Write-Pass "Created $queryOne from first line of $queryFull"
    }
    New-Item -ItemType Directory -Force -Path ".tmp" | Out-Null
    $logDir = ".tmp\smoke_logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $queryNoHead = ".tmp\smoke_query_nohead.jsonl"
    & $PY -c "import json,sys
src=sys.argv[1]; out=sys.argv[2]
drop={'head','head_cui','head_text','head_score','head_source','candidates'}
rows=[]
for line in open(src,encoding='utf-8'):
 o=json.loads(line)
 for k in drop:
  o.pop(k,None)
 rows.append(o)
with open(out,'w',encoding='utf-8') as w:
 for o in rows:
  w.write(json.dumps(o)+'\n')
" $queryOne $queryNoHead
    if ($LASTEXITCODE -ne 0) { throw "Failed to create no-head smoke query input." }
    Assert-NonEmptyFile $queryNoHead

    $singleOut = ".tmp\test_single.jsonl"
    $ensembleOut = ".tmp\test_ensemble3.jsonl"
    $adapterOut = ".tmp\test_adapter.jsonl"
    $pipelineOut = ".tmp\test_pipeline_out"

    $singleStdout = Join-Path $logDir "stage1_single.stdout.log"
    $singleStderr = Join-Path $logDir "stage1_single.stderr.log"
    $ensStdout = Join-Path $logDir "stage1_ensemble3.stdout.log"
    $ensStderr = Join-Path $logDir "stage1_ensemble3.stderr.log"
    $pipeStdout = Join-Path $logDir "stage3_pipeline.stdout.log"
    $pipeStderr = Join-Path $logDir "stage3_pipeline.stderr.log"

    foreach ($f in @($singleOut, $ensembleOut, $adapterOut, $singleStdout, $singleStderr, $ensStdout, $ensStderr, $pipeStdout, $pipeStderr)) {
        if (Test-Path $f) { Remove-Item -Force $f }
    }
    if (Test-Path $pipelineOut) { Remove-Item -Recurse -Force $pipelineOut }
    New-Item -ItemType Directory -Force -Path $pipelineOut | Out-Null

    Invoke-PythonLogged -Label "Stage 1A: analyze (single)" -CmdArgs @(
        "scripts\analyze_with_el_and_intent.py",
        "--queries", $queryOne,
        "--corpus", "data\corpus.jsonl",
        "--kg", "data\kg_edges.merged.plus.csv",
        "--kg_version", "kg_edges.merged.plus.csv",
        "--retrieval_topk", "10",
        "--query_ner_mode", "single",
        "--ner_python", $ResolvedPY,
        "--out", $singleOut
    ) -StdoutPath $singleStdout -StderrPath $singleStderr
    Assert-NonEmptyFile $singleOut

    Invoke-PythonLogged -Label "Stage 1B: analyze (ensemble3)" -CmdArgs @(
        "scripts\analyze_with_el_and_intent.py",
        "--queries", $queryNoHead,
        "--corpus", "data\corpus.jsonl",
        "--kg", "data\kg_edges.merged.plus.csv",
        "--kg_version", "kg_edges.merged.plus.csv",
        "--retrieval_topk", "10",
        "--query_ner_mode", "ensemble3",
        "--query_ner_models", "en_core_sci_md,en_ner_bc5cdr_md,en_ner_jnlpba_md",
        "--ner_python", $ResolvedPY,
        "--out", $ensembleOut
    ) -StdoutPath $ensStdout -StderrPath $ensStderr
    Assert-NonEmptyFile $ensembleOut

    $firstLine = Get-Content $ensembleOut -TotalCount 1
    if (-not $firstLine) { throw "No JSONL rows in $ensembleOut" }
    $row = $firstLine | ConvertFrom-Json

    if (-not $row.PSObject.Properties.Name.Contains("query_ner_models")) {
        throw "Missing field 'query_ner_models' in $ensembleOut"
    }
    if (-not $row.PSObject.Properties.Name.Contains("mentions_by_model")) {
        throw "Missing field 'mentions_by_model' in $ensembleOut"
    }
    if (-not $row.PSObject.Properties.Name.Contains("ner_python")) {
        throw "Missing field 'ner_python' in $ensembleOut"
    }
    if (-not $row.PSObject.Properties.Name.Contains("mentions")) {
        throw "Missing field 'mentions' in $ensembleOut"
    }

    $models = @($row.query_ner_models)
    if ($models.Count -ne 3) {
        throw "Expected query_ner_models length=3, got $($models.Count)"
    }

    $mbm = $row.mentions_by_model
    if ($null -eq $mbm) { throw "mentions_by_model is null" }
    $mbmKeys = @($mbm.PSObject.Properties.Name)
    if ($mbmKeys.Count -ne 3) {
        throw "Expected mentions_by_model key count=3, got $($mbmKeys.Count)"
    }

    # ---- Validate merged mentions ----
    $mergedMentions = @($row.mentions)
    if ($mergedMentions.Count -le 0) {
        throw "Merged mentions list is empty; expected > 0 in ensemble3 output"
    }

    # ---- Validate per-model mentions (persisted row schema) ----
    # Expected structure:
    # mentions_by_model[model] = list[str]

    $atLeastOneModelHasMentions = $false

    foreach ($modelKey in $mbmKeys) {
        $modelMentions = @($mbm.$modelKey)
        if ($modelMentions.Count -gt 0) {
            $atLeastOneModelHasMentions = $true
            break
        }
    }

    if (-not $atLeastOneModelHasMentions) {
        throw "All per-model mention lists are empty in ensemble3 output"
    }

    $normalizePath = {
        param([string]$p)
        return ($p -replace '/', '\').ToLowerInvariant()
    }
    if ((& $normalizePath $row.ner_python) -ne (& $normalizePath $ResolvedPY)) {
        throw "ner_python mismatch. Expected '$ResolvedPY', got '$($row.ner_python)'"
    }

    Write-Pass "Ensemble3 content checks passed (models=3, per-model keys=3, mentions present, ner_python matches)"

    Write-Info "Stage 2: build adapter JSONL -> $adapterOut"
    Write-Host "  CMD: PowerShell adapter transform from $ensembleOut to $adapterOut"
    $adapterRows = @()
    foreach ($line in Get-Content $ensembleOut) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $o = $line | ConvertFrom-Json
        $adapterRows += [PSCustomObject]@{
            qid = $o.qid
            text = $o.text
            relations = @("ADVERSE_EFFECT")
            head = $o.head_cui
            candidates = @(
                [PSCustomObject]@{
                    cui = $o.head_cui
                    score = $o.head_score
                    source = $o.head_source
                }
            )
        }
    }
    if ($adapterRows.Count -eq 0) { throw "Adapter rows are empty" }
    $adapterRows | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 } | Set-Content $adapterOut
    Assert-NonEmptyFile $adapterOut

    Invoke-PythonLogged -Label "Stage 3: run pipeline" -CmdArgs @(
        "scripts\pipeline\run_pipeline.py",
        "--query_jsonl", $adapterOut,
        "--out_dir", $pipelineOut,
        "--kg_csv", "data\kg_edges.merged.plus.csv",
        "--corpus", "data\corpus.jsonl",
        "--dict", "config\umls_dict.txt",
        "--overlay", "config\umls_dict.overlay.json",
        "--schema", "config\relation_schema.json",
        "--dense_mod_path", "src\graphcorag\dense_retriever.py"
    ) -StdoutPath $pipeStdout -StderrPath $pipeStderr

    $expected = @(
        (Join-Path $pipelineOut "queries.for_hybrid.jsonl"),
        (Join-Path $pipelineOut "hybrid.outputs.jsonl"),
        (Join-Path $pipelineOut "rl_eval.tsv")
    )
    foreach ($f in $expected) {
        Assert-NonEmptyFile $f
    }

    Write-Host ""
    Write-Pass "SMOKE TEST PASSED"
    exit 0
}
catch {
    Write-Host ""
    Write-Fail $_.Exception.Message
    exit 1
}
