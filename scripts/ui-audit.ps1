<#
.SYNOPSIS
  Runs the UI action audit (frontend/e2e/ui-audit.spec.ts) against the demo organization with a
  temporary owner that is removed afterwards. Needs the dev stack, backend :8000, frontend :3000.
#>
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
$pwFile = Join-Path $env:TEMP 'replyline-audit-owner.txt'
$email = 'ui.audit@example.com'
[IO.File]::WriteAllText($pwFile, 'Ua-' + [guid]::NewGuid().ToString('N') + '-Aa1')
Push-Location $backend
& $py -m app.cli create-owner harbor-web $email $pwFile | Out-Null
Pop-Location
try {
    $env:E2E_OWNER_EMAIL = $email; $env:E2E_PASSWORD_FILE = $pwFile
    Push-Location (Join-Path $root 'frontend')
    npx playwright test e2e/ui-audit.spec.ts --reporter=line
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    Remove-Item Env:E2E_OWNER_EMAIL, Env:E2E_PASSWORD_FILE -ErrorAction SilentlyContinue
    Remove-Item $pwFile -ErrorAction SilentlyContinue
    Push-Location $backend
    & $py -c "from sqlalchemy import delete;from app.core.db import get_session_factory as f;from app.models import User`nwith f()() as db: db.execute(delete(User).where(User.email=='$email')); db.commit()"
    Pop-Location
    Write-Host 'Temporary audit owner removed.'
}
exit $code
