<#
.SYNOPSIS
  Runs the UI action audit and accessibility scan (frontend/e2e/ui-audit.spec.ts, a11y.spec.ts) in a
  throwaway organization with sample leads and a temporary owner, all deleted afterwards, so the
  demo data is never changed (backlog #46). Needs the dev stack, backend :8000, frontend :3000.
#>
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
$pwFile = Join-Path $env:TEMP 'replyline-audit-owner.txt'
$email = 'ui.audit@example.com'
[IO.File]::WriteAllText($pwFile, 'Ua-' + [guid]::NewGuid().ToString('N') + '-Aa1')
$org = 'ui-audit-' + (Get-Date -Format 'yyyyMMddHHmmss')
Push-Location $backend
& $py -m app.cli create-test-org $org | Out-Null
& $py -m app.cli create-owner $org $email $pwFile | Out-Null
& $py -m app.cli sample-data --org $org --count 40 | Out-Null
Pop-Location
try {
    $env:E2E_OWNER_EMAIL = $email; $env:E2E_PASSWORD_FILE = $pwFile
    Push-Location (Join-Path $root 'frontend')
    New-Item -ItemType Directory -Force (Join-Path $root "frontend/test-results") | Out-Null
    npx playwright test e2e/ui-audit.spec.ts e2e/a11y.spec.ts --reporter=line
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    Remove-Item Env:E2E_OWNER_EMAIL, Env:E2E_PASSWORD_FILE -ErrorAction SilentlyContinue
    Remove-Item $pwFile -ErrorAction SilentlyContinue
    Push-Location $backend
    & $py -m app.cli delete-org $org | Out-Null
    Pop-Location
    Write-Host "Throwaway organization $org and its owner removed."
}
exit $code
