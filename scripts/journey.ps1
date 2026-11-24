<#
.SYNOPSIS
  The MVP gate (master prompt §12.5, P7): the 16-step journey, N times in a row, each from a
  clean database.
.DESCRIPTION
  For each run:
   1. Recreate the separate database <APP_DB_NAME>_e2e (your development data is untouched),
      migrate it, seed the demo organization + n8n service key, and create an e2e owner.
   2. Restart the backend on :8000 against that database with the offline AI (the spec's
      "fake provider in CI"), so the run never depends on the Gemini quota.
   3. Clear Mailpit and run the Playwright journey (steps 1-15).
   4. Step 16: submit a lead, kill the backend immediately, restart it, and check the lead is
      analyzed and drafted (the outbox keeps the event).
  Afterwards the backend is restarted on the normal development database.
  Needs: dev stack up (PostgreSQL, n8n with W1/W4b/W9 active, Mailpit), frontend on :3000.
#>
[CmdletBinding()]
param([int]$Runs = 3, [string]$Mailpit = 'http://127.0.0.1:8025')

# Continue: PowerShell 5.1 turns any native stderr line (psql NOTICEs, alembic logs) into a
# terminating error under Stop; exit codes are checked explicitly instead.
$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
$pg = 'n8n-work-flow-postgres-1'
$appDb = 'replyline'
foreach ($line in [IO.File]::ReadAllLines((Join-Path $root '.env'))) {
    if ($line -match '^\s*APP_DB_NAME\s*=\s*([^#\s]+)') { $appDb = $Matches[1] }
}
$e2eDb = "${appDb}_e2e"
$owner = 'e2e.owner@example.com'
$pwFile = Join-Path $env:TEMP 'replyline-e2e-owner.txt'
$results = @()

function Stop-Backend {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*uvicorn app.main:app*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
}
function Start-Backend([hashtable]$envVars) {
    $saved = @{}
    foreach ($k in $envVars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $envVars[$k]) }
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
function Sql([string]$q) { (docker exec $pg psql -U replyline_app -d $e2eDb -tAc $q | Out-String).Trim() }
$su = (docker exec $pg printenv POSTGRES_USER | Out-String).Trim()
function SuperSql([string]$db, [string]$q) {
    docker exec $pg psql -q -v ON_ERROR_STOP=1 -U $su -d $db -c $q 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "SQL failed on ${db}: $q" }
}

$e2eEnv = @{ APP_DB_NAME = $e2eDb; AI_PROVIDER = 'fake' }
try {
    for ($run = 1; $run -le $Runs; $run++) {
        Write-Host "=== Run $run of $Runs ==="
        Stop-Backend
        # 1. A clean database.
        SuperSql 'postgres' "DROP DATABASE IF EXISTS $e2eDb WITH (FORCE)"
        SuperSql 'postgres' "CREATE DATABASE $e2eDb OWNER replyline_app"
        SuperSql $e2eDb 'CREATE EXTENSION IF NOT EXISTS citext; CREATE EXTENSION IF NOT EXISTS pg_trgm; GRANT ALL ON SCHEMA public TO replyline_app'
        $env:APP_DB_NAME = $e2eDb
        Push-Location $backend
        & $py -m alembic upgrade head 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Migration failed on $e2eDb" }
        & $py -m app.cli seed-demo | Out-Null
        [IO.File]::WriteAllText($pwFile, 'E2e-' + [guid]::NewGuid().ToString('N') + '-Aa1')
        & $py -m app.cli create-owner harbor-web $owner $pwFile | Out-Null
        Pop-Location
        Remove-Item Env:APP_DB_NAME
        # 2. Backend on the clean database with the offline AI.
        Start-Backend $e2eEnv
        Invoke-RestMethod "$Mailpit/api/v1/messages" -Method Delete | Out-Null
        # 3. Steps 1-15 in the browser.
        $env:E2E_OWNER_EMAIL = $owner; $env:E2E_PASSWORD_FILE = $pwFile
        Push-Location $frontend
        $out = (npx playwright test e2e/mvp-journey.spec.ts --reporter=line 2>&1 | Out-String)
        $browserOk = $LASTEXITCODE -eq 0
        Pop-Location
        if (-not $browserOk) { Write-Host $out }
        Write-Host ("{0}  steps 1-15 (browser)" -f ($(if ($browserOk) { 'PASS' } else { 'FAIL' })))
        # 4. Step 16: kill the backend mid-flow, restart, nothing lost.
        $cfg = Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/public/forms/harbor-web'
        $email = "kill.$(Get-Date -Format 'HHmmssfff')@example.com"
        $body = @{ full_name = 'Restart Test'; email = $email; company = 'Example Bakery'; consent = $true
                   message = 'We need a website with online ordering. Budget about $2,000, within a month. Quote please.' } | ConvertTo-Json
        Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/public/leads' -Method Post -Body $body -ContentType 'application/json' -Headers @{ 'X-Form-Key' = $cfg.form_key } | Out-Null
        Stop-Backend
        Start-Sleep 3
        Start-Backend $e2eEnv
        $ok16 = $false
        for ($i = 0; $i -lt 200; $i++) {  # up to 400 s: a run killed mid-analysis is requeued after 5 min
            $state = Sql "select l.ai_status || '|' || (select count(*) from communication_drafts d where d.lead_id = l.id) from leads l where l.email_normalized = '$email'"
            if ($state -eq 'done|1') { $ok16 = $true; break }
            Start-Sleep 2
        }
        Write-Host ("{0}  step 16 (backend killed mid-flow, nothing lost) ({1})" -f ($(if ($ok16) { 'PASS' } else { 'FAIL' })), $state)
        $results += [pscustomobject]@{ Run = $run; Browser = $browserOk; Restart = $ok16 }
    }
} finally {
    Remove-Item Env:E2E_OWNER_EMAIL, Env:E2E_PASSWORD_FILE -ErrorAction SilentlyContinue
    Remove-Item $pwFile -ErrorAction SilentlyContinue
    Stop-Backend
    Start-Backend @{}
    Write-Host 'Backend restarted on the development database.'
}
$results | Format-Table -AutoSize | Out-String | Write-Host
$passed = @($results | Where-Object { $_.Browser -and $_.Restart }).Count
Write-Host "$passed of $Runs runs passed every step."
if ($passed -ne $Runs) { exit 1 }
