param(
  [string]$Proj    = "F:\graph-corag-clean",
  [string]$KgInRel = "data\kg_edges.merged.csv",
  [string]$PatchRel= "data\kg_edges.patch.ddi.csv",
  [string]$KgOutRel= "data\kg_edges.merged.plus.csv"
)

$ErrorActionPreference = "Stop"
$KG_IN  = Join-Path $Proj $KgInRel
$PATCH  = Join-Path $Proj $PatchRel
$KG_OUT = Join-Path $Proj $KgOutRel
if (!(Test-Path $KG_IN)) { throw "KG not found: $KG_IN" }

# Seed candidate pairs that match the naming style you’ve seen in your KG
$seedPairs = @(
  @("drug_adalimumab","drug_infliximab"),
  @("drug_adalimumab","drug_etanercept"),
  @("drug_pembrolizumab","drug_adalimumab"),
  @("drug_infliximab","drug_etanercept"),
  @("drug_tacrolimus","drug_cyclosporine"),
  @("drug_valproate","drug_carbamazepine"),
  @("drug_digoxin","drug_amiodarone")
)

"[*] Loading KG… $KG_IN"
$kgText = Get-Content $KG_IN -Raw -Encoding UTF8

function Test-NodeExists([string]$nodeId) {
  return ($kgText -match [regex]::Escape('"' + $nodeId + '"'))
}

$kept    = New-Object System.Collections.Generic.List[Object]
$skipped = New-Object System.Collections.Generic.List[Object]

"[*] Checking node existence for seed pairs…"
foreach ($pair in $seedPairs) {
  $h = $pair[0]; $t = $pair[1]
  $hOk = Test-NodeExists $h
  $tOk = Test-NodeExists $t
  if ($hOk -and $tOk) {
    $kept.Add(@($h,"INTERACTS_WITH",$t))
  } else {
    $skipped.Add([pscustomobject]@{ head=$h; tail=$t; head_ok=$hOk; tail_ok=$tOk })
  }
}

"[+] Valid pairs kept: $($kept.Count)"
if ($skipped.Count -gt 0) {
  "[-] Skipped pairs (missing nodes):"
  $skipped | Format-Table -Auto
}

if ($kept.Count -eq 0) { "No valid pairs to write. Exiting."; exit 0 }

# Write patch
$patchDir = Split-Path $PATCH
if (!(Test-Path $patchDir)) { New-Item -ItemType Directory -Path $patchDir | Out-Null }
"[*] Writing patch: $PATCH"
$kept | ForEach-Object {
  '"{0}","{1}","{2}"' -f $_[0], $_[1], $_[2]
} | Set-Content -Encoding UTF8 $PATCH

# Merge to out KG
"[*] Writing merged-plus KG: $KG_OUT"
Get-Content $KG_IN -Encoding UTF8 | Set-Content -Encoding UTF8 $KG_OUT
Add-Content -Encoding UTF8 -Path $KG_OUT -Value (Get-Content $PATCH -Encoding UTF8)

# Report counts
$ddiBefore = ([regex]::Matches($kgText, ',INTERACTS_WITH,')).Count
$kgTextPlus = Get-Content $KG_OUT -Raw -Encoding UTF8
$ddiAfter  = ([regex]::Matches($kgTextPlus, ',INTERACTS_WITH,')).Count
"[=] DDI edges before: $ddiBefore | after: $ddiAfter | added: $($ddiAfter - $ddiBefore)"

"`nAdded edges:"
Get-Content $PATCH -TotalCount 20
