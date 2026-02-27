param(
  [string]$Proj    = "F:\graph-corag-clean",
  [string]$KgRel   = "data\kg_edges.merged.plus.csv",
  [string]$OutRaw  = "data\queries.raw.100.txt"
)

$ErrorActionPreference = "Stop"
$KG = Join-Path $Proj $KgRel
$OUT= Join-Path $Proj $OutRaw
if (!(Test-Path $KG)) { throw "KG not found: $KG" }

$lines = Get-Content $KG -Encoding UTF8

# Parse edges "head","REL","tail"
$ae = New-Object System.Collections.Generic.List[Object]
$ddi= New-Object System.Collections.Generic.List[Object]
foreach ($ln in $lines) {
  if ($ln -match '^"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\s*$') {
    $h=$Matches[1]; $r=$Matches[2]; $t=$Matches[3]
    if ($r -eq 'ADVERSE_EFFECT' -and $h -like 'drug_*' -and $t -like 'disease_*') {
      $ae.Add(@($h,$t))
    } elseif ($r -eq 'INTERACTS_WITH' -and $h -like 'drug_*' -and $t -like 'drug_*') {
      $ddi.Add(@($h,$t))
    }
  }
}

# Helper to prettify node ids -> surface strings
function Pretty([string]$id) {
  ($id -replace '^(drug|disease)_','') -replace '_',' '
}

# Build questions:
$qs = New-Object System.Collections.Generic.List[string]

# 1) 45 AE (factoid)
$ae | Select-Object -First 45 | ForEach-Object {
  $drug = Pretty $_[0]; $dis = Pretty $_[1]
  $qs.Add( ("What adverse effects are associated with {0}?" -f $drug) )
}

# 2) 25 DDI (yes/no)
$ddi | Select-Object -First 25 | ForEach-Object {
  $d1 = Pretty $_[0]; $d2 = Pretty $_[1]
  $qs.Add( ("Does {0} interact with {1}?" -f $d1, $d2) )
}

# 3) 30 Multihop AE via DDI bridge: drugA --(INTERACTS_WITH)--> drugB and drugB --(AE)--> diseaseC
#    Build an index from drugB -> diseases
$aeByDrug = @{}
foreach ($pair in $ae) {
  $h=$pair[0]; $t=$pair[1]
  if (-not $aeByDrug.ContainsKey($h)) { $aeByDrug[$h] = New-Object System.Collections.Generic.HashSet[string] }
  $null = $aeByDrug[$h].Add($t)
}
$added = 0
foreach ($pair in $ddi) {
  if ($added -ge 30) { break }
  $a=$pair[0]; $b=$pair[1]
  if ($aeByDrug.ContainsKey($b)) {
    foreach ($dz in $aeByDrug[$b]) {
      $qa = ("If {0} interacts with {1}, and {1} is associated with {2}, is {0} linked to {2} as an adverse effect?" `
              -f (Pretty $a),(Pretty $b),(Pretty $dz))
      $qs.Add($qa); $added++
      if ($added -ge 30) { break }
    }
  }
}

# Trim to 100, write
$qs = $qs | Select-Object -First 100
$qs | Set-Content -Encoding UTF8 (Join-Path $Proj $OutRaw)

"Built $($qs.Count) queries -> $OutRaw"
