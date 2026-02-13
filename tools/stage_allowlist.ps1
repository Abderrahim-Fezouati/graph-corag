param(
  [switch]$NoDryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path "pyproject.toml")) {
  throw "Run this script from repo root (pyproject.toml not found)."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is not available in this shell."
}

$dryRun = -not $NoDryRun

# Explicit, code-only allowlist staging paths.
$allowlist = @(
  ".gitignore",
  "pyproject.toml",
  "run_pipeline.ps1",
  "scripts/analyze_with_el_and_intent.py",
  "scripts/pipeline/run_pipeline.py",
  "scripts/run_hybrid.py",
  "scripts/run_ner_offline.py",
  "src/graphcorag",
  "src/analyzer",
  "src/kg_validation",
  "src/passage_processing",
  "config/umls_dict.txt",
  "config/umls_dict.overlay.json",
  "config/relation_schema.json",
  "docs/pipeline_docs_2026-01-27/PIPELINE_EXECUTION.md",
  "tools/smoke_test_pipeline.ps1",
  "tools/stage_allowlist.ps1"
)

# Explicit deny patterns inside allowlisted directories.
$denyPathPatterns = @(
  '\\old_sapbert_scripts\\',
  '\\archives\\'
)
$denyNamePatterns = @(
  '*.bak*',
  '*.backup.py',
  '*~'
)

Write-Host "[INFO] Verifying allowlist paths..."
foreach ($p in $allowlist) {
  if (-not (Test-Path $p)) {
    throw "Allowlist path missing: $p"
  }
}

# Expand allowlist into concrete files and apply deny filters.
$filesToStage = New-Object System.Collections.Generic.List[string]
foreach ($p in $allowlist) {
  $item = Get-Item -LiteralPath $p
  if ($item.PSIsContainer) {
    $candidates = Get-ChildItem -LiteralPath $p -Recurse -File
  } else {
    $candidates = @($item)
  }

  foreach ($f in $candidates) {
    $full = $f.FullName
    $denyByPath = $false
    foreach ($pat in $denyPathPatterns) {
      if ($full -match $pat) {
        $denyByPath = $true
        break
      }
    }
    if ($denyByPath) { continue }

    $denyByName = $false
    foreach ($namePat in $denyNamePatterns) {
      if ($f.Name -like $namePat) {
        $denyByName = $true
        break
      }
    }
    if ($denyByName) { continue }

    $filesToStage.Add($f.FullName)
  }
}

$filesToStage = $filesToStage | Sort-Object -Unique
if (-not $filesToStage -or $filesToStage.Count -eq 0) {
  throw "No files left to stage after deny filters."
}

# Safety check: block unexpectedly large files.
$maxBytes = 50MB
$large = Get-Item -LiteralPath $filesToStage | Where-Object { $_.Length -gt $maxBytes }
if ($large) {
  Write-Host "[FAIL] Files larger than 50MB found in allowlist:"
  $large | ForEach-Object { Write-Host "  $($_.FullName) ($($_.Length) bytes)" }
  throw "Refusing to stage due to oversized files."
}

if ($dryRun) {
  Write-Host "[DRY-RUN] Would run:"
  foreach ($f in $filesToStage) {
    Write-Host "  git add -- `"$f`""
  }
  Write-Host "[DRY-RUN] Current git status:"
  git status --short
  exit 0
}

Write-Host "[INFO] Staging allowlist..."
foreach ($f in $filesToStage) {
  git add -- "$f"
}

Write-Host "[INFO] Staged files:"
git diff --cached --name-only
Write-Host "[PASS] Allowlist staging complete."
