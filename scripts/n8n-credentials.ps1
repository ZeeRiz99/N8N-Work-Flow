<#
.SYNOPSIS
  Creates (or updates) Replyline's named n8n credentials from .env. Never prints a secret.
.DESCRIPTION
  RL Backend Service Key  (Header Auth, X-Service-Key)    n8n -> backend /api/v1/internal/*
  RL Webhook Secret       (Header Auth, X-Webhook-Secret)  backend -> n8n webhooks
  RL SMTP                 (SMTP, mailpit:1025)             dev email
  RL Telegram Bot         (Telegram API)                   only when TELEGRAM_BOT_TOKEN is set
  Secrets go to n8n through a pipe, not a file on disk; n8n encrypts them with N8N_ENCRYPTION_KEY.
.EXAMPLE
  .\scripts\n8n-credentials.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
$container = 'n8n-work-flow-n8n-1'

$envMap = @{}
foreach ($line in [System.IO.File]::ReadAllLines($envFile)) {
    if ($line -match '^([A-Z0-9_]+)=(\S*)') { $envMap[$Matches[1]] = $Matches[2] }
}
function Get-EnvValue([string]$name) {
    $v = $envMap[$name]
    if ([string]::IsNullOrWhiteSpace($v) -or $v.StartsWith('#')) { return '' }
    return $v
}

$creds = @(
    @{ id = 'rlCredSvcKey0001'; name = 'RL Backend Service Key'; type = 'httpHeaderAuth'
       data = @{ name = 'X-Service-Key'; value = (Get-EnvValue 'SERVICE_API_KEY') } },
    @{ id = 'rlCredWebhook001'; name = 'RL Webhook Secret'; type = 'httpHeaderAuth'
       data = @{ name = 'X-Webhook-Secret'; value = (Get-EnvValue 'N8N_WEBHOOK_SECRET') } },
    @{ id = 'rlCredSmtp000001'; name = 'RL SMTP'; type = 'smtp'
       data = @{ host = (Get-EnvValue 'SMTP_HOST'); port = [int](Get-EnvValue 'SMTP_PORT');
                 user = (Get-EnvValue 'SMTP_USER'); password = (Get-EnvValue 'SMTP_PASSWORD'); secure = $false } }
)
$tg = Get-EnvValue 'TELEGRAM_BOT_TOKEN'
if ($tg) {
    $creds += @{ id = 'rlCredTelegram01'; name = 'RL Telegram Bot'; type = 'telegramApi'; data = @{ accessToken = $tg } }
}

foreach ($c in $creds) {
    if ($c.type -eq 'httpHeaderAuth' -and -not $c.data.value) {
        Write-Host ("Skipped {0}: its value is missing in .env" -f $c.name); continue
    }
}
$creds = $creds | Where-Object { $_.type -ne 'httpHeaderAuth' -or $_.data.value }

$json = ConvertTo-Json -InputObject @($creds) -Depth 5 -Compress
# Windows PowerShell 5.1 would prefix piped text with a BOM; send plain UTF-8 instead.
$OutputEncoding = New-Object System.Text.UTF8Encoding($false)
# The in-container steps live in a script file (no secrets in it) to avoid Windows quoting problems.
# n8n's own output can echo the input, so the script never shows it.
$helper = Join-Path $root 'infra\n8n\import-credentials.sh'
docker cp $helper "${container}:/tmp/rl-import-credentials.sh" | Out-Null
$json | docker exec -i $container sh /tmp/rl-import-credentials.sh
$code = $LASTEXITCODE
docker exec -u root $container rm -f /tmp/rl-import-credentials.sh | Out-Null
$json = $null
if ($code -ne 0) { Write-Host 'Import failed. n8n output is hidden because it can contain the input; nothing secret was printed.'; exit $code }
Write-Host ('Credentials in n8n: ' + (($creds | ForEach-Object { $_.name }) -join ', '))
if (-not $tg) { Write-Host 'RL Telegram Bot: skipped until TELEGRAM_BOT_TOKEN is set (task 13).' }
