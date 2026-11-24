<#
.SYNOPSIS
  Load smoke (P10): a burst of 100 leads plus 30 exact duplicates, sent concurrently. Expect
  100 leads, 100 inquiries, 100 intake events, and every lead processed by n8n W1. None lost,
  none duplicated.
.DESCRIPTION
  Runs on a freshly created <APP_DB_NAME>_e2e database (development data untouched) with the
  offline AI and the public-form rate limit raised for the test. Restores the normal backend
  afterwards. Needs the dev stack (PostgreSQL, n8n with W1 active, Mailpit).
#>
[CmdletBinding()]
param([int]$Leads = 100, [int]$Duplicates = 30)

$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
$pg = 'n8n-work-flow-postgres-1'
$appDb = 'replyline'
foreach ($line in [IO.File]::ReadAllLines((Join-Path $root '.env'))) {
    if ($line -match '^\s*APP_DB_NAME\s*=\s*([^#\s]+)') { $appDb = $Matches[1] }
}
$db = "${appDb}_e2e"
$su = (docker exec $pg printenv POSTGRES_USER | Out-String).Trim()
$failed = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    if ($ok) { Write-Host "PASS  $name $detail" } else { Write-Host "FAIL  $name $detail"; $script:failed++ }
}
function Sql([string]$q) { (docker exec $pg psql -U replyline_app -d $db -tAc $q | Out-String).Trim() }
function SuperSql([string]$d, [string]$q) { docker exec $pg psql -q -U $su -d $d -c $q 2>&1 | Out-Null }
function Stop-Backend {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*uvicorn app.main:app*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
}
function Start-Backend([hashtable]$vars) {
    $saved = @{}
    foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $vars[$k]) }
    Start-Process -FilePath $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--timeout-keep-alive', '65' `
        -WorkingDirectory $backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $env:TEMP 'rl-backend.log') -RedirectStandardError (Join-Path $env:TEMP 'rl-backend.err')
    foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    for ($i = 0; $i -lt 40; $i++) {
        try { if ((Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2).status -eq 'ok') { return } } catch {}
        Start-Sleep 1
    }
    throw 'Backend did not start.'
}

try {
    Stop-Backend
    SuperSql 'postgres' "DROP DATABASE IF EXISTS $db WITH (FORCE)"
    SuperSql 'postgres' "CREATE DATABASE $db OWNER replyline_app"
    SuperSql $db 'CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm; GRANT ALL ON SCHEMA public TO replyline_app'
    $env:APP_DB_NAME = $db
    Push-Location $backend
    & $py -m alembic upgrade head 2>&1 | Out-Null
    & $py -m app.cli seed-demo | Out-Null
    Pop-Location
    Remove-Item Env:APP_DB_NAME
    Start-Backend @{ APP_DB_NAME = $db; AI_PROVIDER = 'fake'; PUBLIC_FORM_RATE_LIMIT_PER_MINUTE = '100000' }

    $t0 = Get-Date
    $burst = @"
import concurrent.futures, random, httpx
cfg = httpx.get('http://127.0.0.1:8000/api/v1/public/forms/harbor-web').json()
def body(i):
    return {'full_name': f'Load Lead {i}', 'email': f'load.{i}@example.com', 'consent': True,
            'message': f'Load test inquiry {i}: we need a website, budget about 2,000 dollars.'}
jobs = [body(i) for i in range($Leads)] + [body(i) for i in range($Duplicates)]
random.shuffle(jobs)
def send(b):
    return httpx.post('http://127.0.0.1:8000/api/v1/public/leads', json=b, timeout=30,
                      headers={'X-Form-Key': cfg['form_key']}).status_code
with concurrent.futures.ThreadPoolExecutor(25) as pool:
    codes = list(pool.map(send, jobs))
print(','.join(f'{c}:{codes.count(c)}' for c in sorted(set(codes))))
"@
    $codes = (& $py -c $burst | Out-String).Trim()
    $secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    Check "burst of $($Leads + $Duplicates) requests accepted" ($codes -notmatch '5\d\d') "($codes in $secs s)"
    Check "exactly $Leads leads" ((Sql 'select count(*) from leads') -eq "$Leads")
    Check "exactly $Leads inquiries (duplicates deduplicated)" ((Sql 'select count(*) from lead_inquiries') -eq "$Leads")
    Check "exactly $Leads intake events" ((Sql "select count(*) from outbox_events where event_type='lead.created'") -eq "$Leads")
    $done = $false
    for ($i = 0; $i -lt 120; $i++) {
        $n = [int](Sql "select count(*) from leads where ai_status in ('done','skipped')")
        if ($n -ge $Leads) { $done = $true; break }
        Start-Sleep 5
    }
    $mins = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    Check 'every lead processed by n8n W1' $done "($(Sql "select count(*) from leads where ai_status in ('done','skipped')") of $Leads in $mins min)"
    Check 'every event delivered' ((Sql "select count(*) from outbox_events where status <> 'delivered'") -eq '0')
    Check 'no lead has two drafts' ((Sql 'select count(*) from (select lead_id from communication_drafts group by lead_id having count(*) > 1) x') -eq '0')
    Check 'W1 runs: one success per lead' ((Sql "select count(distinct lead_id) from workflow_executions where workflow_key='W1' and status='success'") -eq "$Leads")
} finally {
    Stop-Backend
    Start-Backend @{}
    Write-Host 'Backend restarted on the development database.'
}
if ($failed) { Write-Host "$failed check(s) failed."; exit 1 }
Write-Host 'Load smoke passed.'
