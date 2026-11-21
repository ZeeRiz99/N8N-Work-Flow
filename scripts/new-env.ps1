<#
.SYNOPSIS
  Creates .env from .env.example and fills every "generate" value with a random secret.
.DESCRIPTION
  Never prints a secret. Refuses to overwrite an existing .env (use -Force to replace it,
  which also replaces N8N_ENCRYPTION_KEY: only do that before n8n has stored credentials).
  You add GEMINI_API_KEY and TELEGRAM_BOT_TOKEN yourself afterwards.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\new-env.ps1
#>
[CmdletBinding()]
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$example = Join-Path $root '.env.example'
$target = Join-Path $root '.env'

if ((Test-Path $target) -and -not $Force) {
    Write-Host '.env already exists. Nothing changed. (Use -Force only before n8n has stored credentials.)'
    exit 0
}

function New-Secret {
    param([int]$Bytes = 48)
    $buf = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($buf)
    $rng.Dispose()
    # URL-safe, no quotes or symbols that would need escaping in SQL, YAML or URLs
    return ([Convert]::ToBase64String($buf) -replace '[+/=]', '').Substring(0, 40)
}

$count = 0
$lines = Get-Content -Path $example -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=generate(\s.*)?$') {
        $count++
        '{0}={1}' -f $Matches[1], (New-Secret)
    } else {
        $_
    }
}

$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($target, (($lines -join "`n") + "`n"), $enc)
Write-Host ('.env created with {0} generated secrets (values not shown).' -f $count)
Write-Host 'Next: open .env yourself and fill GEMINI_API_KEY (and TELEGRAM_BOT_TOKEN in task 13).'
