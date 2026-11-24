<#
.SYNOPSIS
  Restore drill (P10): takes a fresh backup, restores the app database into a scratch database,
  compares row counts table by table with the live database, then drops the scratch copy.
  Your live databases are only read.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$root = Split-Path $PSScriptRoot -Parent
$pg = 'n8n-work-flow-postgres-1'
$su = (docker exec $pg printenv POSTGRES_USER | Out-String).Trim()
$appDb = 'replyline'
foreach ($line in [IO.File]::ReadAllLines((Join-Path $root '.env'))) {
    if ($line -match '^\s*APP_DB_NAME\s*=\s*([^#\s]+)') { $appDb = $Matches[1] }
}
$scratch = "${appDb}_restore_drill"
$failed = 0

$t0 = Get-Date
& (Join-Path $PSScriptRoot 'backup.ps1') | Write-Host
$dump = Get-ChildItem (Join-Path $root 'backups') -Filter "$appDb-*.dump" | Sort-Object LastWriteTime | Select-Object -Last 1
Write-Host "Restoring $($dump.Name) into $scratch ..."
docker cp $dump.FullName "${pg}:/tmp/drill.dump" | Out-Null
docker exec $pg psql -q -U $su -d postgres -c "DROP DATABASE IF EXISTS $scratch WITH (FORCE)" 2>&1 | Out-Null
docker exec $pg psql -q -U $su -d postgres -c "CREATE DATABASE $scratch OWNER replyline_app" 2>&1 | Out-Null
docker exec $pg pg_restore -U $su -d $scratch --no-owner --role=replyline_app /tmp/drill.dump 2>&1 | Out-Null
$restoreCode = $LASTEXITCODE
docker exec $pg rm -f /tmp/drill.dump
Write-Host ("pg_restore exit code {0}" -f $restoreCode)

$tables = (docker exec $pg psql -U $su -d $appDb -tAc "select tablename from pg_tables where schemaname='public' order by 1" | Out-String).Trim() -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }
$rows = @()
foreach ($t in $tables) {
    $live = (docker exec $pg psql -U $su -d $appDb -tAc "select count(*) from public.""$t""" | Out-String).Trim()
    $back = (docker exec $pg psql -U $su -d $scratch -tAc "select count(*) from public.""$t""" | Out-String).Trim()
    $rows += [pscustomobject]@{ Table = $t; Live = $live; Restored = $back; Same = ($live -eq $back) }
}
$rows | Format-Table -AutoSize | Out-String | Write-Host
$diff = @($rows | Where-Object { -not $_.Same })
$version = (docker exec $pg psql -U $su -d $scratch -tAc "select version_num from alembic_version" | Out-String).Trim()
docker exec $pg psql -q -U $su -d postgres -c "DROP DATABASE IF EXISTS $scratch WITH (FORCE)" 2>&1 | Out-Null
$mins = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Write-Host "Tables: $($rows.Count), differing: $($diff.Count), schema version: $version, took $mins s."
if ($diff.Count -gt 0) { Write-Host 'FAIL  restore drill (counts differ; a write may have happened during the backup)'; exit 1 }
Write-Host 'PASS  restore drill: every table restored with the same row count.'
