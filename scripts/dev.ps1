<#
.SYNOPSIS
  Start, stop and inspect Replyline's development infrastructure (PostgreSQL, n8n, Mailpit).
.EXAMPLE
  .\scripts\dev.ps1 up          # start in the background
  .\scripts\dev.ps1 status      # containers and health
  .\scripts\dev.ps1 logs n8n    # follow one service's logs
  .\scripts\dev.ps1 down        # stop (keeps data)
  .\scripts\dev.ps1 reset -Yes  # stop and DELETE all data, including n8n credentials
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][ValidateSet('up', 'down', 'reset', 'status', 'logs')][string]$Command = 'status',
    [Parameter(Position = 1)][string]$Service = '',
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'infra\compose.dev.yml'
$envFile = Join-Path $root '.env'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Docker is not installed or not on PATH. Install Docker Desktop first (docs/INSTALLATION_PLAN.md).'
    exit 1
}
if (-not (Test-Path $envFile)) {
    Write-Host '.env is missing. Create it with:  .\scripts\new-env.ps1'
    exit 1
}

$base = @('compose', '-f', $composeFile, '--env-file', $envFile)

switch ($Command) {
    'up' {
        & docker @base up -d
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host ''
        Write-Host 'n8n:     http://localhost:5678'
        Write-Host 'Mailpit: http://localhost:8025'
        Write-Host 'Postgres: localhost:5432'
    }
    'down' { & docker @base down }
    'reset' {
        if (-not $Yes) {
            Write-Host 'reset deletes the PostgreSQL and n8n volumes, including stored n8n credentials.'
            Write-Host 'Run again with -Yes to confirm:  .\scripts\dev.ps1 reset -Yes'
            exit 1
        }
        & docker @base down -v
    }
    'status' { & docker @base ps }
    'logs' {
        if ($Service) { & docker @base logs -f --tail 200 $Service }
        else { & docker @base logs -f --tail 100 }
    }
}
exit $LASTEXITCODE
