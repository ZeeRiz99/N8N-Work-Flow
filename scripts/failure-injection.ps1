<#
.SYNOPSIS
  Failure-injection checks from master prompt §9.4 that need real containers stopped.
.DESCRIPTION
  A. n8n stopped while a lead arrives: the backend keeps the event in the outbox, retries,
     and the lead is analyzed and drafted once n8n is back. Nothing is lost.
  B. SMTP refusing (Mailpit stopped) when a draft is approved: W4b marks the draft failed,
     logs the failure, and does not send it again when the mail server returns.
  Other §9.4 checks live elsewhere: duplicate delivery (smoke.ps1), Gemini down (pytest
  test_ai_faults.py + retry worker), Telegram failure (pytest test_approvals.py; the n8n
  branch needs the bot, backlog #17).
  Needs: dev stack up, backend on :8000, W1/W4b/W9 active, demo org seeded. Synthetic data.
#>
[CmdletBinding()]
param([string]$Api = 'http://127.0.0.1:8000', [string]$Mailpit = 'http://127.0.0.1:8025')

$ErrorActionPreference = 'Stop'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path
$failed = 0
function Check([string]$name, [bool]$ok, [string]$detail = '') {
    if ($ok) { Write-Host "PASS  $name $detail" } else { Write-Host "FAIL  $name $detail"; $script:failed++ }
}
function Sql([string]$q) { (docker exec n8n-work-flow-postgres-1 psql -U replyline_app -d replyline -tAc $q | Out-String).Trim() }
function WaitFor([scriptblock]$cond, [int]$seconds) {
    for ($i = 0; $i -lt $seconds; $i++) { if (& $cond) { return $true }; Start-Sleep 1 }
    return $false
}
function WaitHttp([string]$url, [int]$seconds) {
    WaitFor { try { (Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { $false } } $seconds
}

$cfg = Invoke-RestMethod "$Api/api/v1/public/forms/harbor-web"
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$email = "fault.$stamp@example.com"

# ---------------- A. n8n down
Write-Host '--- A: n8n stopped while a lead arrives'
docker stop n8n-work-flow-n8n-1 | Out-Null
try {
    $body = @{ full_name = 'Fault Test Lead'; email = $email; company = 'Example Cafe'; consent = $true
               message = 'We need a website with online ordering. Budget about $2,000, within a month. Quote please.' } | ConvertTo-Json
    Invoke-RestMethod "$Api/api/v1/public/leads" -Method Post -Body $body -ContentType 'application/json' -Headers @{ 'X-Form-Key' = $cfg.form_key } | Out-Null
    $lead = ''
    WaitFor { $script:lead = Sql "select id from leads where email_normalized='$email'"; [bool]$script:lead } 10 | Out-Null
    Check 'lead stored while n8n is down' ([bool]$lead)
    $retried = WaitFor { [int](Sql "select coalesce(max(attempts),0) from outbox_events where payload->'data'->>'lead_id'='$lead'") -ge 1 } 20
    Check 'delivery attempted and kept for retry' $retried "(status: $(Sql "select status from outbox_events where payload->'data'->>'lead_id'='$lead'"))"
} finally {
    docker start n8n-work-flow-n8n-1 | Out-Null
}
Check 'n8n back up' (WaitHttp 'http://127.0.0.1:5678/healthz' 90)
Start-Sleep 5
# Skip the backoff wait (the sweeper W9b does this on a schedule from P8).
Sql "update outbox_events set status='pending', next_attempt_at=now() where payload->'data'->>'lead_id'='$lead' and status <> 'delivered'" | Out-Null
$done = WaitFor { (Sql "select ai_status from leads where id='$lead'") -in @('done', 'failed') } 120
Check 'lead processed after recovery' $done "(ai: $(Sql "select ai_status from leads where id='$lead'"))"
$draft = ''
WaitFor { $script:draft = Sql "select id from communication_drafts where lead_id='$lead' and status='pending_approval'"; [bool]$script:draft } 60 | Out-Null
Check 'draft written after recovery' ([bool]$draft)
Check 'exactly one draft' ((Sql "select count(*) from communication_drafts where lead_id='$lead'") -eq '1')

# ---------------- B. SMTP refusing
Write-Host '--- B: mail server down when a draft is approved'
$backend = Join-Path (Split-Path $PSScriptRoot -Parent) 'backend'
$py = Join-Path $backend '.venv/Scripts/python.exe'
docker stop n8n-work-flow-mailpit-1 | Out-Null
try {
    $code = "import uuid;from app.core.db import get_session_factory as f;from app.models import CommunicationDraft as D;from app.services import approvals as a`n" +
            "with f()() as db:`n d=db.get(D,uuid.UUID('$draft'));a.approve(db,d,None);db.commit();print(d.status)"
    Push-Location $backend; $st = (& $py -c $code | Out-String).Trim(); Pop-Location
    Check 'draft approved' ($st -eq 'approved')
    $isFailed = WaitFor { (Sql "select status from communication_drafts where id='$draft'") -eq 'failed' } 90
    Check 'draft marked failed (SMTP refused)' $isFailed "($(Sql "select status || ' | ' || coalesce(send_error,'') from communication_drafts where id='$draft'"))"
    Check 'failure logged' ((Sql "select count(*) from communication_logs where draft_id='$draft' and status='failed'") -eq '1')
} finally {
    docker start n8n-work-flow-mailpit-1 | Out-Null
}
Check 'mail server back up' (WaitHttp "$Mailpit/api/v1/info" 60)
Start-Sleep 8
Check 'no second send attempt' ((Sql "select status from communication_drafts where id='$draft'") -eq 'failed')
$hits = (Invoke-RestMethod "$Mailpit/api/v1/search?query=to:$email").messages_count
Check 'nothing delivered later by itself' ($hits -eq 0) "($hits)"
Check 'lead untouched by the failure' ((Sql "select count(*) from leads where id='$lead' and archived_at is null") -eq '1')

if ($failed) { Write-Host "$failed check(s) failed."; exit 1 }
Write-Host 'All failure-injection checks passed.'
