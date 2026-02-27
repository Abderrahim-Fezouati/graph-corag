param(
  [Parameter(Mandatory=$true)][string]$Tag,
  [switch]$NoDryRun
)

$DryRun = -not $NoDryRun

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

$now = Get-Date
$stamp = $now.ToString("yyyyMMdd_HHmmss")
$dateFolder = $now.ToString("yyyy-MM-dd")

$runRoot = "runs\\$dateFolder"
$runDir = Join-Path $runRoot ("run_{0}_{1}" -f $stamp, $Tag)
$logsDir = Join-Path $runDir "logs"
$outputsDir = Join-Path $runDir "outputs"
$cmdDir = Join-Path $runDir "cmd"
$configDir = Join-Path $runDir "config_snapshot"

$latest = Get-ChildItem -Path ".tmp" -Directory -Filter "pipeline_*" -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if (-not $latest) {
  Write-Error "No .tmp/pipeline_* folder found."
  exit 1
}
$tmpPipeline = $latest.FullName

Write-Host "Repo root: $(Get-Location)"
Write-Host "Source folder: $tmpPipeline"
Write-Host "Destination: $runDir"
if (Test-Path $runDir) {
  Write-Error "Run directory already exists: $runDir. Choose a different -Tag."
  exit 1
}

function New-Dir {
  param([Parameter(Mandatory=$true)][string[]]$Paths)
  if ($DryRun) {
    New-Item -ItemType Directory -Force -Path $Paths -WhatIf | Out-Null
  } else {
    New-Item -ItemType Directory -Force -Path $Paths | Out-Null
  }
}

New-Dir -Paths @($runRoot, $runDir, $logsDir, $outputsDir, $cmdDir, $configDir)

function Copy-NoOverwrite {
  param(
    [Parameter(Mandatory=$true)][string]$Src,
    [Parameter(Mandatory=$true)][string]$DestDir
  )
  $name = Split-Path $Src -Leaf
  $dest = Join-Path $DestDir $name
  if (Test-Path $dest) {
    $base = [IO.Path]::GetFileNameWithoutExtension($name)
    $ext = [IO.Path]::GetExtension($name)
    $dest = Join-Path $DestDir ("{0}_{1}{2}" -f $base, $stamp, $ext)
    if (Test-Path $dest) {
      throw "Collision: $dest already exists."
    }
  }
  if ($DryRun) {
    Copy-Item -Path $Src -Destination $dest -WhatIf
  } else {
    Copy-Item -Path $Src -Destination $dest
  }
}

Get-ChildItem -Path $tmpPipeline -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in ".txt", ".log" } |
  ForEach-Object { Copy-NoOverwrite -Src $_.FullName -DestDir $logsDir }

Get-ChildItem -Path $tmpPipeline -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in ".jsonl", ".tsv" } |
  ForEach-Object { Copy-NoOverwrite -Src $_.FullName -DestDir $outputsDir }

Get-ChildItem -Path $tmpPipeline, ".tmp" -File -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -in @("analysis_command.txt","cmd.txt") } |
  ForEach-Object { Copy-NoOverwrite -Src $_.FullName -DestDir $cmdDir }

if ($DryRun) {
  Copy-Item -Path "config" -Destination $configDir -Recurse -WhatIf
} else {
  Copy-Item -Path "config" -Destination $configDir -Recurse
}

$inputs = @{
  kg = "data/kg_edges.merged.plus.csv"
  corpus = "data/corpus.jsonl"
  queries = "data/queries_kg_aligned.jsonl"
  tag = $Tag
  timestamp = $stamp
  source_folder = $tmpPipeline
}
$inputsPath = Join-Path $runDir "inputs.json"
if ($DryRun) {
  Write-Output (ConvertTo-Json $inputs -Depth 2) | Out-File -FilePath $inputsPath -Encoding utf8 -WhatIf
} else {
  Write-Output (ConvertTo-Json $inputs -Depth 2) | Out-File -FilePath $inputsPath -Encoding utf8
}

if ($DryRun) {
  Write-Host "DryRun complete; nothing created. Planned destination: $runDir"
} else {
  Write-Host "Run snapshot created at: $runDir"
}
