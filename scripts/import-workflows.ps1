<#
.SYNOPSIS
  Imports Replyline's n8n workflows from n8n\workflows\*.json, filling URL placeholders from .env.
.DESCRIPTION
  Placeholders (D21): __BACKEND_URL__ (BACKEND_URL_FOR_N8N), __ALERT_EMAIL_TO__ (ALERT_EMAIL_TO),
  __ALERT_EMAIL_FROM__ (SMTP_FROM). Workflow files hold no secrets; secrets live in n8n credentials.
  -Activate publishes the workflows so their production webhooks answer, then restarts n8n.
.EXAMPLE
  .\scripts\import-workflows.ps1 -Activate
#>
[CmdletBinding()]
param(
    [string]$Only = '',
    [switch]$Activate
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$container = 'n8n-work-flow-n8n-1'
$envMap = @{}
foreach ($line in [System.IO.File]::ReadAllLines((Join-Path $root '.env'))) {
    if ($line -match '^([A-Z0-9_]+)=(\S*)') { $envMap[$Matches[1]] = $Matches[2] }
}
function Get-EnvValue([string]$name, [string]$default) {
    $v = $envMap[$name]
    if ([string]::IsNullOrWhiteSpace($v) -or $v.StartsWith('#')) { return $default }
    return $v
}
$values = @{
    '__BACKEND_URL__'      = (Get-EnvValue 'BACKEND_URL_FOR_N8N' 'http://host.docker.internal:8000').TrimEnd('/')
    '__ALERT_EMAIL_TO__'   = (Get-EnvValue 'ALERT_EMAIL_TO' 'team@harbor-web.example.com')
    '__ALERT_EMAIL_FROM__' = (Get-EnvValue 'SMTP_FROM' 'hello@harbor-web.example.com')
    '__FRONTEND_URL__'     = (Get-EnvValue 'FRONTEND_PUBLIC_URL' 'http://localhost:3000').TrimEnd('/')
}

$files = Get-ChildItem (Join-Path $root 'n8n\workflows') -Filter '*.json' |
    Where-Object { -not $Only -or $_.Name -like "*$Only*" }
$enc = New-Object System.Text.UTF8Encoding($false)
$ids = @()
foreach ($file in $files) {
    $text = [System.IO.File]::ReadAllText($file.FullName)
    foreach ($k in $values.Keys) { $text = $text.Replace($k, $values[$k]) }
    if ($text -match '__[A-Z_]+__') { throw "Unfilled placeholder in $($file.Name): $($Matches[0])" }
    $wf = $text | ConvertFrom-Json
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("rl-wf-" + $file.Name)
    [System.IO.File]::WriteAllText($tmp, $text, $enc)
    docker cp $tmp "${container}:/tmp/rl-wf.json" | Out-Null
    Remove-Item $tmp
    $out = docker exec $container n8n import:workflow --input=/tmp/rl-wf.json 2>&1 | Out-String
    docker exec -u root $container rm -f /tmp/rl-wf.json | Out-Null
    if ($out -notmatch 'Successfully imported') { throw "Import failed for $($file.Name)" }
    Write-Host ("Imported: {0}" -f $wf.name)
    $ids += $wf.id
}

if ($Activate) {
    foreach ($id in ($ids | Where-Object { $_ -notlike 'rlP2*' })) {
        $out = docker exec $container n8n publish:workflow --id=$id 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            $out = docker exec $container n8n update:workflow --id=$id --active=true 2>&1 | Out-String
        }
        Write-Host ("Activated: {0} ({1})" -f $id, (($out.Trim() -split "`n")[-1]))
    }
    docker restart $container | Out-Null
    Write-Host 'n8n restarted so the production webhooks load.'
}
