<#
.SYNOPSIS
  Backs up the app database and the n8n database (custom-format pg_dump) into backups\.
.DESCRIPTION
  backups\ is git-ignored. The n8n dump holds its encrypted credentials and execution history;
  workflows themselves are also kept as JSON in the repo. Keep backups somewhere safe and
  off this machine for real data. Prints file names and sizes only.
#>
[CmdletBinding()]
param([string]$OutDir)

$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$root = Split-Path $PSScriptRoot -Parent
if (-not $OutDir) { $OutDir = Join-Path $root 'backups' }
New-Item -ItemType Directory -Force $OutDir | Out-Null
$pg = 'n8n-work-flow-postgres-1'
$su = (docker exec $pg printenv POSTGRES_USER | Out-String).Trim()
$appDb = 'replyline'; $n8nDb = 'n8n'
foreach ($line in [IO.File]::ReadAllLines((Join-Path $root '.env'))) {
    if ($line -match '^\s*APP_DB_NAME\s*=\s*([^#\s]+)') { $appDb = $Matches[1] }
    if ($line -match '^\s*N8N_DB_NAME\s*=\s*([^#\s]+)') { $n8nDb = $Matches[1] }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($db in @($appDb, $n8nDb)) {
    $inside = "/tmp/$db-$stamp.dump"
    docker exec $pg pg_dump -U $su -Fc -f $inside $db
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed for $db" }
    $file = Join-Path $OutDir "$db-$stamp.dump"
    docker cp "${pg}:$inside" $file | Out-Null
    docker exec $pg rm -f $inside
    "{0}  {1:n0} KB" -f (Split-Path $file -Leaf), ((Get-Item $file).Length / 1KB)
}
