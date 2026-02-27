param(
  [switch]$WhatIf
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $root)

$destRoot = "artifacts\\root_generated"

function New-Dir {
  param([Parameter(Mandatory=$true)][string[]]$Paths)
  if ($WhatIf) {
    New-Item -ItemType Directory -Force -Path $Paths -WhatIf | Out-Null
  } else {
    New-Item -ItemType Directory -Force -Path $Paths | Out-Null
  }
}

function Move-NoOverwrite {
  param(
    [Parameter(Mandatory=$true)][string]$Src,
    [Parameter(Mandatory=$true)][string]$DestDir,
    [Parameter(Mandatory=$true)][string]$LogPath
  )
  $name = Split-Path $Src -Leaf
  $dest = Join-Path $DestDir $name
  if (Test-Path $dest) {
    $base = [IO.Path]::GetFileNameWithoutExtension($name)
    $ext = [IO.Path]::GetExtension($name)
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $dest = Join-Path $DestDir ("{0}_{1}{2}" -f $base, $stamp, $ext)
    if (Test-Path $dest) {
      throw "Collision: $dest already exists."
    }
  }
  $entry = "MOVE $Src -> $dest"
  if ($WhatIf) {
    $entry = "DRYRUN $entry"
    Move-Item -Path $Src -Destination $dest -WhatIf
  } else {
    Add-Content -Path $LogPath -Value $entry
    Move-Item -Path $Src -Destination $dest
  }
}

# Root-generated reports to quarantine
$targets = @(
  "env_conda_list.txt",
  "env_full_report.txt",
  "env_pip_freeze.txt",
  "project_folder_structure.txt",
  "project_structure_clean.txt",
  "project_tree.txt",
  "project_tree_after_cleanup.txt",
  "project_tree_current.txt"
)

$logDir = "artifacts"
$logPath = Join-Path $logDir "root_generated_move_log.txt"

if ($WhatIf) {
  New-Dir -Paths @($destRoot, $logDir)
} else {
  New-Dir -Paths @($destRoot, $logDir)
  if (-not (Test-Path $destRoot)) {
    throw "Destination root missing: $destRoot"
  }
  if (-not (Test-Path $logDir)) {
    throw "Log directory missing: $logDir"
  }
}

foreach ($t in $targets) {
  if (Test-Path $t) {
    Move-NoOverwrite -Src (Join-Path (Get-Location) $t) -DestDir $destRoot -LogPath $logPath
  }
}

if ($WhatIf) {
  Write-Host "DryRun complete; no files moved. Log: $logPath"
} else {
  Write-Host "Quarantine complete. Log: $logPath"
}
