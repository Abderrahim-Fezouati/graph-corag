param(
    [string]$Root = 'F:\graph-corag-clean',
    [int]$N = 80
)

Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object Length -Descending |
    Select-Object FullName,Length -First $N |
    ForEach-Object { "$($_.FullName)`t$([math]::Round($_.Length/1MB,2))MB" }
