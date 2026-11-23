<#
.SYNOPSIS
  Demo data for the demo organization: about 150 fictional leads over 60 days (P7).
.DESCRIPTION
  Creates the demo organization and n8n service key if missing (seed-demo), then loads
  fictional sample leads: several industries, a realistic stage mix, reply history for leads
  past "Contacted", notes and two near-duplicates. Leads are flagged as sample data
  (custom_fields.sample) and scored by the offline AI, so no Gemini quota is used.
  -Fresh removes the previous sample leads first (your own leads are never touched).
.EXAMPLE
  .\scripts\seed.ps1 -Fresh
#>
[CmdletBinding()]
param([int]$Count = 150, [int]$Days = 60, [switch]$Fresh, [string]$Org = 'harbor-web')

$ErrorActionPreference = 'Stop'
$backend = Join-Path (Split-Path $PSScriptRoot -Parent) 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'
Push-Location $backend
try {
    & $py -m app.cli seed-demo
    if ($Fresh) { & $py -m app.cli sample-data --org $Org --clear }
    & $py -m app.cli sample-data --org $Org --count $Count --days $Days
} finally {
    Pop-Location
}
