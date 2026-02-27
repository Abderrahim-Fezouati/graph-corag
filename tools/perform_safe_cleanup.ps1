# Safe cleanup script
# Moves large folders out of repo to a timestamped backup folder, removes them from git index, and commits .gitignore

# Compute repo root as parent of this script's folder
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

# .gitignore content
$gi = @'
# Large models / checkpoints
/models/
**/checkpoint-*/
*.safetensors
*.pt
*.pth

# Generated indices and search artifacts
/artifacts/
/indices/

# Run outputs, caches, logs, temp
/out/
/temp/
/tmp/
/cache/
/logs/

# Local env dumps
/env/
venv/
/.venv/
pip_freeze.txt
conda_list.txt

# Big data files (optional)
#/data/corpus.jsonl
#/data/kg_edges.*

# Python artifacts
__pycache__/
*.pyc

# Editor / OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Tool outputs
/tools/*.log
'@

Set-Content -Path (Join-Path $Root '.gitignore') -Value $gi -Encoding UTF8
Write-Host "Wrote .gitignore to $Root\.gitignore"

# Create timestamped backup folder
$BACKUP = Join-Path $Root ("large_backups_" + (Get-Date -Format yyyyMMdd_HHmmss))
New-Item -ItemType Directory -Force -Path $BACKUP | Out-Null
Write-Host "Backup folder: $BACKUP"

$toMove = @('models','artifacts','indices','out','env','temp','tmp','cache','logs')
$actuallyMoved = @()
foreach ($p in $toMove) {
    $full = Join-Path $Root $p
    if (Test-Path $full) {
        try {
            Move-Item -Path $full -Destination $BACKUP -Force
            Write-Host "Moved: $full -> $BACKUP"
            $actuallyMoved += $p
        } catch {
            Write-Warning "Failed to move $full : $($_.Exception.Message)"
        }
    } else {
        Write-Host "Not found, skipped: $full"
    }
}

if ($actuallyMoved.Count -gt 0) {
    # Remove from git index
    $args = @('rm','-r','--cached') + $actuallyMoved
    Write-Host "Running: git $($args -join ' ')"
    git @args 2>&1 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "No candidate folders were moved; skipping git rm --cached"
}

# Stage .gitignore and all changes
git add .gitignore
git add -A

$staged = (git diff --cached --name-only)
if ($staged) {
    git commit -m "chore: remove large artifacts and ignore them (moved to backup: $BACKUP)" 2>&1 | ForEach-Object { Write-Host $_ }
    Write-Host "Committed cleanup. Staged files:`n$staged"
} else {
    Write-Host "Nothing to commit (no staged changes)."
}

Write-Host "\nGit status (short):"
git status --short | ForEach-Object { Write-Host $_ }

Write-Host "\nBackup contents (top files):"
Get-ChildItem -Path $BACKUP -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object FullName,@{Name='MB';Expression={[math]::Round($_.Length/1MB,2)}} -First 50 | Format-Table -AutoSize | Out-String | Write-Host

Write-Host "\nSAFE CLEANUP COMPLETE. Files moved to: $BACKUP"
