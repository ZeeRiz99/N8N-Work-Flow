<#
.SYNOPSIS
  End-to-end smoke test of the walking skeleton. Needs: .\scripts\dev.ps1 up, the backend on :8000,
  W1 imported and active (.\scripts\import-workflows.ps1 -Activate), and the demo org seeded.
.DESCRIPTION
  1. Submits a high-intent lead through the public API.
  2. Waits for n8n W1 to analyze it (fake AI) and checks the score, the run log and the alert email.
  3. Redelivers the same outbox event and checks that nothing new happens (no second alert).
  Uses synthetic data (example.com). Prints PASS/FAIL per check and exits 1 on any failure.
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

$cfg = Invoke-RestMethod "$Api/api/v1/public/forms/harbor-web"
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$email = "smoke.$stamp@example.com"
$mail0 = (Invoke-RestMethod "$Mailpit/api/v1/messages").total
$body = @{
    full_name = 'Smoke Test Lead'; email = $email; company = 'Example Bakery'; service = 'Website Development'
    budget = '$1,500 to $5,000'; timeline = 'Within 1 month'; consent = $true
    message = 'We need a website with online ordering. Budget about $2,000, live within a month. Quote please.'
} | ConvertTo-Json
$rid = "smoke-$stamp"
$t0 = Get-Date
$resp = Invoke-RestMethod "$Api/api/v1/public/leads" -Method Post -Body $body -ContentType 'application/json' -Headers @{ 'X-Form-Key' = $cfg.form_key; 'X-Request-ID' = $rid }
Check 'lead accepted' ([bool]$resp.reference)

$lead = $null
for ($i = 0; $i -lt 30; $i++) {
    # The leads API needs a login since Phase 4, so read the row straight from the database.
    $row = Sql "select id || '|' || ai_status || '|' || coalesce(score::text,'') || '|' || priority || '|' || coalesce(score_source,'') from leads where email_normalized='$email'"
    if ($row) {
        $p = $row -split '\|'
        $lead = [pscustomobject]@{ id = $p[0]; ai_status = $p[1]; score = $p[2]; priority = $p[3]; score_source = $p[4] }
    }
    if ($lead -and ($lead.ai_status -eq 'done' -or $lead.ai_status -eq 'failed')) { break }
    Start-Sleep 1
}
$secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Check 'lead scored by W1' ([bool]$lead.score) "($secs s, score $($lead.score), $($lead.priority), $($lead.score_source), ai $($lead.ai_status))"
$isHigh = $lead.priority -eq 'high'
if ($lead.ai_status -eq 'done') { Check 'priority is high' $isHigh }
else { Write-Host "SKIP  priority check: AI unavailable (daily Gemini budget?), provisional score" }
# W1 logs its run at the end (after the alert and the draft). With Telegram configured but
# unreachable, the Telegram step waits for its timeout before the email fallback: wait for the log.
for ($i = 0; $i -lt 90; $i++) {
    $runs = Sql "select string_agg(status || ':' || coalesce(request_id,''), ',') from workflow_executions where lead_id='$($lead.id)'"
    if ($runs) { break }
    Start-Sleep 1
}
Check 'W1 run logged with request id' ($runs -eq "success:$rid") "($runs)"
$mail1 = (Invoke-RestMethod "$Mailpit/api/v1/messages").total
Check 'alert email only when high' (($mail1 - $mail0) -eq [int]$isHigh) "(high=$isHigh)"
$draft = Sql "select id || '|' || status || '|' || coalesce(to_address,'') from communication_drafts where lead_id='$($lead.id)'"
$d = $draft -split '\|'
Check 'W1 wrote one draft, pending approval, to the lead' ($d[1] -eq 'pending_approval' -and $d[2] -eq $email) "($($d[1]))"

$ev = Sql "select id from outbox_events where payload->'data'->>'lead_id'='$($lead.id)'"
Sql "update outbox_events set status='pending', next_attempt_at=now() where id='$ev'" | Out-Null
for ($i = 0; $i -lt 20; $i++) { if ((Sql "select status from outbox_events where id='$ev'") -eq 'delivered') { break }; Start-Sleep 1 }
Start-Sleep 4
$runs2 = Sql "select string_agg(status, ',' order by created_at) from workflow_executions where lead_id='$($lead.id)'"
Check 'redelivery logged as skipped' ($runs2 -eq 'success,skipped') "($runs2)"
Check 'no second alert email' (((Invoke-RestMethod "$Mailpit/api/v1/messages").total - $mail1) -eq 0)
Check 'still one lead and one inquiry' ((Sql "select count(*) from lead_inquiries where lead_id='$($lead.id)'") -eq '1')

Check 'redelivery made no second draft' ((Sql "select count(*) from communication_drafts where lead_id='$($lead.id)'") -eq '1')

# ---- P6: a person approves through the API (the same call as the Approvals button) -> W4b
# sends it. A temporary approver logs in; afterwards the smoke lead is erased and the approver
# removed, so the demo organization keeps no smoke data (backlog #37, #46).
$backend = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"
$py = Join-Path $backend ".venv/Scripts/python.exe"
$approver = 'smoke.approver@example.com'
$pwFile = Join-Path $env:TEMP 'replyline-smoke-approver.txt'
[IO.File]::WriteAllText($pwFile, 'Sm-' + [guid]::NewGuid().ToString('N') + '-Aa1')
Push-Location $backend; & $py -m app.cli create-owner harbor-web $approver $pwFile | Out-Null; Pop-Location
$h = @{ 'X-Requested-With' = 'replyline' }
try {
    $login = @{ email = $approver; password = [IO.File]::ReadAllText($pwFile) } | ConvertTo-Json
    Invoke-RestMethod "$Api/api/v1/auth/login" -Method Post -Body $login -ContentType 'application/json' -Headers $h -SessionVariable web | Out-Null
    $ap = Invoke-RestMethod "$Api/api/v1/drafts/$($d[0])/approve" -Method Post -Headers $h -WebSession $web
    Check 'draft approved through the API' ($ap.status -in @('approved', 'sending', 'sent')) "($($ap.status))"
    $mail2 = (Invoke-RestMethod "$Mailpit/api/v1/messages").total
    for ($i = 0; $i -lt 40; $i++) { if ((Sql "select status from communication_drafts where id='$($d[0])'") -eq 'sent') { break }; Start-Sleep 1 }
    Check 'W4b sent it (draft sent)' ((Sql "select status from communication_drafts where id='$($d[0])'") -eq 'sent')
    $msgs = Invoke-RestMethod "$Mailpit/api/v1/search?query=to:$email"
    Check 'email delivered to the lead (Mailpit)' ($msgs.messages_count -ge 1)
    Check 'sent logged with message id' ([bool](Sql "select provider_message_id from communication_logs where draft_id='$($d[0])' and status='sent'"))
    Check 'follow-up scheduled in 3 days' ((Sql "select count(*) from follow_ups where lead_id='$($lead.id)' and status='scheduled' and due_at > now() + interval '2 days'") -eq '1')
    $aev = Sql "select id from outbox_events where event_type='draft.approved' and payload->'data'->>'draft_id'='$($d[0])'"
    Sql "update outbox_events set status='pending', next_attempt_at=now() where id='$aev'" | Out-Null
    for ($i = 0; $i -lt 20; $i++) { if ((Sql "select status from outbox_events where id='$aev'") -eq 'delivered') { break }; Start-Sleep 1 }
    Start-Sleep 5
    Check 'approval redelivered: no second email' ((Invoke-RestMethod "$Mailpit/api/v1/search?query=to:$email").messages_count -eq $msgs.messages_count)
    $w4b = Sql "select string_agg(status, ',' order by created_at) from workflow_executions where workflow_key='W4b' and lead_id='$($lead.id)'"
    Check 'W4b runs logged: success then skipped' ($w4b -eq 'success,skipped') "($w4b)"
} finally {
    if ($web -and $runs) {
        try {
            Invoke-RestMethod "$Api/api/v1/leads/$($lead.id)" -Method Delete -Headers $h -WebSession $web | Out-Null
            Write-Host 'Smoke lead erased from the demo organization.'
        } catch { Write-Host "WARN  could not erase the smoke lead: $($_.Exception.Message)" }
    }
    Remove-Item $pwFile -ErrorAction SilentlyContinue
    Push-Location $backend
    & $py -c "from sqlalchemy import delete;from app.core.db import get_session_factory as f;from app.models import RefreshToken,OrganizationMember,User`nwith f()() as db:`n u=db.query(User).filter_by(email='$approver').first()`n if u:`n  db.execute(delete(RefreshToken).where(RefreshToken.user_id==u.id));db.execute(delete(OrganizationMember).where(OrganizationMember.user_id==u.id));db.delete(u);db.commit()"
    Pop-Location
    Write-Host 'Temporary approver removed.'
}

if ($failed) { Write-Host "$failed check(s) failed."; exit 1 }
Write-Host 'All smoke checks passed.'
