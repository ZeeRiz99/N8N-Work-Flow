<#
.SYNOPSIS
  Saves one secret into .env. The value is never shown or printed.
.DESCRIPTION
  Default: reads the key from the clipboard (copy it first), saves it, then clears the clipboard.
  -Type: asks for it with hidden input instead (some terminals paste only one character there).
.EXAMPLE
  .\scripts\set-secret.ps1 OPENAI_API_KEY          # copy the key first
  .\scripts\set-secret.ps1 GEMINI_API_KEY
  .\scripts\set-secret.ps1 TELEGRAM_BOT_TOKEN -Type
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('GEMINI_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN')]
    [string]$Name,
    [switch]$Type
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    Write-Host '.env is missing. Create it first:  .\scripts\new-env.ps1'
    exit 1
}

if ($Type) {
    $secure = Read-Host -Prompt "Paste $Name (input is hidden), then press Enter" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $value = ([Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)).Trim()
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
} else {
    Write-Host ''
    Write-Host "Now go to your browser and copy the $Name (select it, Ctrl+C)."
    $null = Read-Host 'Then come back here and press Enter'
    $value = ((Get-Clipboard -Raw) | Out-String).Trim()
}
if (-not $value) {
    Write-Host 'Nothing found. Copy the key first (Ctrl+C), then run this again. .env not changed.'
    exit 1
}
if ($value -match '\s') {
    Write-Host 'The copied text contains spaces or line breaks, which a key never has. .env not changed.'
    exit 1
}
if ($value.Length -lt 20) {
    Write-Host ("Only {0} characters: that is too short for a real key, so it looks cut off. .env not changed." -f $value.Length)
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
if (-not $Type) { Set-Clipboard -Value ' ' }
Write-Host ("Saved {0} to .env (length {1}). The value was not shown, and the clipboard was cleared." -f $Name, $length)
