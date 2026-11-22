<#
.SYNOPSIS
  Saves one secret into .env with hidden input. The value is never shown or printed.
.EXAMPLE
  .\scripts\set-secret.ps1 OPENAI_API_KEY
  .\scripts\set-secret.ps1 GEMINI_API_KEY
  .\scripts\set-secret.ps1 TELEGRAM_BOT_TOKEN
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN')]
    [string]$Name
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Write-Host '.env is missing. Create it first:  .\scripts\new-env.ps1'
    exit 1
}

$secure = Read-Host -Prompt "Paste $Name (input is hidden), then press Enter" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $value = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim()
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if (-not $value) {
    Write-Host 'Nothing entered. .env not changed.'
    exit 1
}
if ($value -match '\s') {
    Write-Host 'The value contains spaces or line breaks, which a key never has. .env not changed.'
    exit 1
}

$lines = [System.Collections.Generic.List[string]]::new()
$found = $false
foreach ($line in [System.IO.File]::ReadAllLines($envFile)) {
    if ($line -match "^$Name=") {
        $lines.Add("$Name=$value")
        $found = $true
    } else {
        $lines.Add($line)
    }
}
if (-not $found) { $lines.Add("$Name=$value") }

$enc = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envFile, (($lines -join "`n") + "`n"), $enc)
$length = $value.Length
$value = $null
Write-Host ("Saved {0} to .env (length {1}). The value was not shown." -f $Name, $length)
