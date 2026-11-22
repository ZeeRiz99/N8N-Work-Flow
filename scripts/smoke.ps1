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
    $lead = (Invoke-RestMethod "$Api/api/v1/leads").items | Where-Object { $_.email -eq $email }
    if ($lead -and $lead.ai_status -eq 'done') { break }
    Start-Sleep 1
}
$secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
Check 'lead analyzed by W1' ($lead.ai_status -eq 'done') "($secs s, score $($lead.score), $($lead.priority), $($lead.score_source))"
Check 'priority is high' ($lead.priority -eq 'high')
Start-Sleep 3
$runs = Sql "select string_agg(status || ':' || coalesce(request_id,''), ',') from workflow_executions where lead_id='$($lead.id)'"
Check 'W1 run logged with request id' ($runs -eq "success:$rid") "($runs)"
$mail1 = (Invoke-RestMethod "$Mailpit/api/v1/messages").total
Check 'one alert email' (($mail1 - $mail0) -eq 1)

$ev = Sql "select id from outbox_events where payload->'data'->>'lead_id'='$($lead.id)'"
Sql "update outbox_events set status='pending', next_attempt_at=now() where id='$ev'" | Out-Null
for ($i = 0; $i -lt 20; $i++) { if ((Sql "select status from outbox_events where id='$ev'") -eq 'delivered') { break }; Start-Sleep 1 }
Start-Sleep 4
$runs2 = Sql "select string_agg(status, ',' order by created_at) from workflow_executions where lead_id='$($lead.id)'"
Check 'redelivery logged as skipped' ($runs2 -eq 'success,skipped') "($runs2)"
Check 'no second alert email' (((Invoke-RestMethod "$Mailpit/api/v1/messages").total - $mail1) -eq 0)
Check 'still one lead and one inquiry' ((Sql "select count(*) from lead_inquiries where lead_id='$($lead.id)'") -eq '1')

if ($failed) { Write-Host "$failed check(s) failed."; exit 1 }
Write-Host 'All smoke checks passed.'
