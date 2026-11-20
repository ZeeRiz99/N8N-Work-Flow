<#
.SYNOPSIS
  AI LeadFlow - READ-ONLY environment audit for Windows.

.DESCRIPTION
  Inspects this machine and prints a report. It installs nothing, changes no settings
  and writes no files unless you pass -OutFile.
  It does NOT print environment-variable values, API keys, passwords, or your git
  user name / email. Your Windows user name is replaced with <user> unless -NoRedact is used.

.PARAMETER OutFile
  Optional. Also save the report to this text file.

.PARAMETER NoRedact
  Optional. Do not replace your Windows user name in the output.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\inspect-env.ps1
  (the ExecutionPolicy flag applies to this one run only and changes no system setting)

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\inspect-env.ps1 -OutFile .\env-report.txt
#>
[CmdletBinding()]
param(
    [string]$OutFile = '',
    [switch]$NoRedact
)

$ErrorActionPreference = 'Continue'
$script:Lines  = New-Object System.Collections.Generic.List[string]
$script:CountOk = 0
$script:CountWarn = 0
$script:CountMissing = 0
$startTime = Get-Date

# ---------------------------------------------------------------- helpers
function Out-Line {
    param([string]$Text = '')
    if ((-not $NoRedact) -and $env:USERNAME) {
        $Text = $Text -replace [regex]::Escape($env:USERNAME), '<user>'
    }
    Write-Host $Text
    [void]$script:Lines.Add($Text)
}
function Section {
    param([string]$Title)
    Out-Line ''
    Out-Line ('=' * 72)
    Out-Line ('== ' + $Title)
    Out-Line ('=' * 72)
}
function Ok   { param([string]$Message) $script:CountOk++;      Out-Line ('[OK]      ' + $Message) }
function Warn { param([string]$Message) $script:CountWarn++;    Out-Line ('[WARN]    ' + $Message) }
function Miss { param([string]$Message) $script:CountMissing++; Out-Line ('[MISSING] ' + $Message) }
function Info { param([string]$Message) Out-Line ('[INFO]    ' + $Message) }

function Get-FirstLine {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    return (($Text -split "`r?`n")[0]).Trim()
}

function Invoke-Timed {
    # Runs a script block in a background job; returns its text output, or $null on timeout.
    param([scriptblock]$Script, [int]$TimeoutSec = 15)
    $job = Start-Job -ScriptBlock $Script
    if (Wait-Job -Job $job -Timeout $TimeoutSec) {
        $out = Receive-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force
        return (($out | Out-String).Trim())
    }
    Stop-Job -Job $job
    Remove-Job -Job $job -Force
    return $null
}

function Test-Tool {
    # Reports whether a command exists on PATH and prints its first version line.
    param([string]$Name, [string[]]$VersionArgs = @('--version'), [string]$Hint = '')
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) {
        Miss (('{0,-10} not found on PATH {1}' -f $Name, $Hint).TrimEnd())
        return $false
    }
    $src = $cmd.Source
    if (-not $src) { $src = $cmd.Definition }
    if (($Name -eq 'python' -or $Name -eq 'python3') -and ($src -like '*\WindowsApps\*')) {
        Warn ('{0,-10} resolves to a Microsoft Store alias ({1}); this is NOT a real Python install' -f $Name, $src)
        return $false
    }
    $ver = ''
    try {
        $raw = & $Name @VersionArgs 2>&1 | Select-Object -First 1
        $ver = ($raw | Out-String).Trim()
    } catch {
        $ver = '(version check failed)'
    }
    Ok ('{0,-10} {1}   [{2}]' -f $Name, $ver, $src)
    return $true
}

function Test-Tcp {
    param([string]$HostName, [int]$Port = 443, [int]$TimeoutMs = 4000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $done = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
        if ($done -and $client.Connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-MajorMinor {
    param([string]$Text)
    if ($Text -match '(\d+)\.(\d+)') {
        return New-Object PSObject -Property @{ Major = [int]$Matches[1]; Minor = [int]$Matches[2] }
    }
    return $null
}

# ---------------------------------------------------------------- header
Out-Line 'AI LeadFlow - environment audit (read-only)'
Out-Line ('Run at: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz'))
Out-Line 'This script installs nothing and changes nothing.'

# ---------------------------------------------------------------- 1. system
Section '1. Windows, hardware, virtualization'
try {
    $os  = Get-CimInstance Win32_OperatingSystem
    $cs  = Get-CimInstance Win32_ComputerSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Info ('OS: {0} | version {1} | build {2} | {3}' -f $os.Caption, $os.Version, $os.BuildNumber, $os.OSArchitecture)
    if ([int]$os.BuildNumber -lt 19045) {
        Warn 'Windows build is older than 19045 (Windows 10 22H2). Docker Desktop may not support it - check before installing.'
    } else {
        Ok 'Windows build is recent enough for Docker Desktop (WSL2 backend).'
    }
    $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    $freeRamGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    Info ('CPU: {0} | cores {1} | logical processors {2}' -f $cpu.Name.Trim(), $cpu.NumberOfCores, $cpu.NumberOfLogicalProcessors)
    if ($ramGB -lt 8) {
        Warn ('RAM: {0} GB total ({1} GB free). Under 8 GB is tight for Docker + n8n + PostgreSQL + Node + Python together.' -f $ramGB, $freeRamGB)
    } else {
        Ok ('RAM: {0} GB total ({1} GB free right now)' -f $ramGB, $freeRamGB)
    }
    Info ('Virtualization enabled in firmware: {0} | Hypervisor present: {1}' -f $cpu.VirtualizationFirmwareEnabled, $cs.HypervisorPresent)
    Info '(If "Hypervisor present" is True, virtualization is effectively on even if the firmware flag shows False.)'
} catch {
    Warn ('Could not read system information: ' + $_.Exception.Message)
}

try {
    $tz = Get-TimeZone
    Info ('Time zone: {0} ({1})' -f $tz.Id, $tz.DisplayName)
} catch { }

try {
    $lp = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    if ($lp -eq 1) { Ok 'Windows long paths: enabled' } else { Info 'Windows long paths: disabled (keep the project path short)' }
} catch {
    Info 'Windows long paths: could not read the setting'
}

try {
    $av = Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop
    if ($av) { Info ('Antivirus products: ' + ((@($av) | ForEach-Object { $_.displayName }) -join ', ')) }
} catch {
    Info 'Antivirus products: could not be read'
}

# ---------------------------------------------------------------- 2. disk
Section '2. Disk space'
try {
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        $freeGB  = [math]::Round($_.FreeSpace / 1GB, 1)
        $totalGB = [math]::Round($_.Size / 1GB, 1)
        $msg = 'Drive {0} {1} GB free of {2} GB' -f $_.DeviceID, $freeGB, $totalGB
        if ($freeGB -lt 20) { Warn ($msg + ' - under 20 GB free; Docker images and node_modules need room') }
        else { Ok $msg }
    }
} catch {
    Warn ('Could not read disk information: ' + $_.Exception.Message)
}

# ---------------------------------------------------------------- 3. shell + project location
Section '3. PowerShell and project location'
Info ('PowerShell version: ' + $PSVersionTable.PSVersion.ToString() + ' (' + $PSVersionTable.PSEdition + ')')
try {
    $policies = Get-ExecutionPolicy -List | ForEach-Object { ('{0}={1}' -f $_.Scope, $_.ExecutionPolicy) }
    Info ('Execution policy: ' + ($policies -join ' | '))
} catch { }

$here = (Get-Location).Path
Info ('Current folder: ' + $here)
if ($here -match 'OneDrive')                { Warn 'The current folder is inside OneDrive. Sync conflicts break node_modules, .git and Docker mounts. Use a folder outside OneDrive, such as D:\Projects\N8N Work Flow.' }
if ($here -match '\s')                      { Info 'The current path contains a space (allowed for this project). Every script, command and compose file must quote paths.' }
if ($here -match '\\(Desktop|Documents)(\\|$)') { Warn 'Desktop and Documents are often synced or protected. Prefer a folder such as D:\Projects\N8N Work Flow.' }
if (Test-Path 'D:\Projects\N8N Work Flow') { Info 'D:\Projects\N8N Work Flow already exists' } else { Info 'D:\Projects\N8N Work Flow does not exist yet (fine; it will be created later with your approval)' }

# ---------------------------------------------------------------- 4. core tools
Section '4. Core development tools'
$gitOk = Test-Tool 'git'
if ($gitOk) {
    $n = (& git config --global --get user.name 2>$null)
    $e = (& git config --global --get user.email 2>$null)
    if ($n) { Ok 'git user.name is set' }  else { Warn 'git user.name is not set' }
    if ($e) { Ok 'git user.email is set' } else { Warn 'git user.email is not set' }
    $crlf = (& git config --global --get core.autocrlf 2>$null)
    if ($crlf) { Info ('git core.autocrlf = ' + $crlf + ' (the project will add .gitattributes to force LF)') } else { Info 'git core.autocrlf is not set globally' }
    $branch = (& git config --global --get init.defaultBranch 2>$null)
    if ($branch) { Info ('git init.defaultBranch = ' + $branch) } else { Info 'git init.defaultBranch is not set (default is master)' }
}
[void](Test-Tool 'gh' @('--version') '(GitHub CLI - optional)')

$nodeOk = Test-Tool 'node'
if ($nodeOk) {
    $nv = Get-MajorMinor ((& node --version 2>&1 | Out-String))
    if ($nv -and $nv.Major -lt 20) { Warn ('Node.js {0}.{1} is older than 20. Current Next.js needs a recent LTS - verify the required version.' -f $nv.Major, $nv.Minor) }
}
[void](Test-Tool 'npm')
[void](Test-Tool 'npx')
[void](Test-Tool 'pnpm' @('--version') '(optional)')
foreach ($vm in @('nvm', 'fnm', 'volta')) {
    if (Get-Command $vm -ErrorAction SilentlyContinue) { Info ('Node version manager present: ' + $vm) }
}

$pyOk = Test-Tool 'python'
if ($pyOk) {
    $pv = Get-MajorMinor ((& python --version 2>&1 | Out-String))
    if ($pv -and ($pv.Major -lt 3 -or ($pv.Major -eq 3 -and $pv.Minor -lt 11))) {
        Warn ('python {0}.{1} is older than 3.11 - the backend needs a newer Python.' -f $pv.Major, $pv.Minor)
    }
}
$pyLauncher = Test-Tool 'py' @('--version') '(Python launcher)'
if ($pyLauncher) {
    $list = (& py -0p 2>&1 | Out-String).Trim()
    if ($list) { Info 'Installed Pythons (py -0p):'; $list -split "`r?`n" | ForEach-Object { Out-Line ('           ' + $_.Trim()) } }
}
[void](Test-Tool 'pip' @('--version') '')
[void](Test-Tool 'uv'  @('--version') '(optional)')

[void](Test-Tool 'winget' @('--version') '(Windows package manager)')

# ---------------------------------------------------------------- 5. VS Code + Claude Code
Section '5. VS Code and Claude Code'
$codeOk = Test-Tool 'code' @('--version') '(add VS Code to PATH from its installer or Command Palette)'
if ($codeOk) {
    $ext = (& code --list-extensions 2>$null)
    if ($ext) {
        $extList = @($ext) | ForEach-Object { $_.ToLower() }
        Info ('VS Code extensions installed: ' + $extList.Count)
        $wanted = [ordered]@{
            'anthropic.claude-code'            = 'Claude Code'
            'ms-python.python'                 = 'Python'
            'charliermarsh.ruff'               = 'Ruff'
            'ms-azuretools.vscode-docker'      = 'Docker'
            'dbaeumer.vscode-eslint'           = 'ESLint'
            'esbenp.prettier-vscode'           = 'Prettier'
            'bradlc.vscode-tailwindcss'        = 'Tailwind CSS IntelliSense'
            'ms-vscode-remote.remote-wsl'      = 'WSL (optional)'
        }
        foreach ($k in $wanted.Keys) {
            if ($extList -contains $k) { Ok ('extension present: ' + $wanted[$k]) } else { Info ('extension not found: ' + $wanted[$k] + ' (' + $k + ')') }
        }
    }
}
[void](Test-Tool 'claude' @('--version') '(Claude Code CLI - optional if you use the VS Code extension)')

# ---------------------------------------------------------------- 6. Docker + WSL
Section '6. Docker and WSL'
$dockerOk = Test-Tool 'docker'
if ($dockerOk) {
    $compose = Invoke-Timed { docker compose version 2>&1 } 20
    if ($compose) { Ok ('docker compose: ' + (Get-FirstLine $compose)) } else { Warn 'docker compose did not answer in time or is unavailable' }
    $dinfo = Invoke-Timed { docker info --format '{{.ServerVersion}} | {{.OperatingSystem}} | cpus={{.NCPU}} | mem={{.MemTotal}}' 2>&1 } 25
    if ($null -eq $dinfo) {
        Warn 'The Docker daemon did not answer within 25 seconds (Docker Desktop is probably not running).'
    } elseif ($dinfo -match 'error|Cannot connect|failed|pipe') {
        Warn ('The Docker daemon is not reachable: ' + (Get-FirstLine $dinfo))
    } else {
        Ok ('Docker daemon: ' + $dinfo)
    }
}
if (Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue) { Ok 'Docker Desktop is running' } else { Info 'Docker Desktop process is not running' }

if (Get-Command wsl -ErrorAction SilentlyContinue) {
    $w = ((& wsl.exe -l -v 2>&1 | Out-String) -replace "`0", '').Trim()
    if ($w) {
        Info 'WSL distributions (wsl -l -v):'
        $w -split "`r?`n" | ForEach-Object { if ($_.Trim()) { Out-Line ('           ' + $_.Trim()) } }
    }
} else {
    Miss 'wsl.exe not found (WSL is not installed or not enabled)'
}
$wslCfg = Join-Path $env:USERPROFILE '.wslconfig'
if (Test-Path $wslCfg) {
    Info '.wslconfig exists:'
    Get-Content $wslCfg -ErrorAction SilentlyContinue | Select-Object -First 15 | ForEach-Object { Out-Line ('           ' + $_) }
} else {
    Info '.wslconfig not found (WSL memory defaults apply)'
}

# ---------------------------------------------------------------- 7. PostgreSQL
Section '7. PostgreSQL'
$pgServices = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue
if ($pgServices) {
    foreach ($s in $pgServices) { Warn ('PostgreSQL service found: {0} ({1}) - it may occupy port 5432' -f $s.Name, $s.Status) }
} else {
    Info 'No native PostgreSQL Windows service found (a Docker container will be used)'
}
[void](Test-Tool 'psql' @('--version') '(client tools - optional)')
if (Test-Path 'C:\Program Files\PostgreSQL') { Info 'C:\Program Files\PostgreSQL exists' }

# ---------------------------------------------------------------- 8. ports
Section '8. Ports the project plans to use'
$ports = @(1025, 3000, 5173, 5432, 5678, 8000, 8025)
foreach ($p in $ports) {
    $conn = Get-NetTCPConnection -State Listen -LocalPort $p -ErrorAction SilentlyContinue
    if ($conn) {
        $names = @()
        foreach ($c in $conn) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            if ($proc) { $names += $proc.ProcessName } else { $names += ('pid ' + $c.OwningProcess) }
        }
        Warn ('port {0} is already in use by: {1}' -f $p, (($names | Select-Object -Unique) -join ', '))
    } else {
        Ok ('port {0} is free' -f $p)
    }
}
Info 'Plan: 3000 dashboard | 8000 API | 5432 PostgreSQL | 5678 n8n | 8025 Mailpit UI | 1025 Mailpit SMTP'

# ---------------------------------------------------------------- 9. network
Section '9. Network reachability (TCP connect only, no data sent)'
$targets = @(
    @('github.com', 443),
    @('registry.npmjs.org', 443),
    @('pypi.org', 443),
    @('files.pythonhosted.org', 443),
    @('registry-1.docker.io', 443),
    @('docker.n8n.io', 443),
    @('generativelanguage.googleapis.com', 443),
    @('api.telegram.org', 443),
    @('smtp.gmail.com', 587)
)
foreach ($t in $targets) {
    if (Test-Tcp -HostName $t[0] -Port $t[1]) { Ok ('{0}:{1} reachable' -f $t[0], $t[1]) }
    else { Warn ('{0}:{1} NOT reachable (firewall, proxy, or DNS problem?)' -f $t[0], $t[1]) }
}

# ---------------------------------------------------------------- summary
Section 'SUMMARY'
$elapsed = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
Out-Line ('OK: {0}   WARN: {1}   MISSING: {2}   (took {3}s)' -f $script:CountOk, $script:CountWarn, $script:CountMissing, $elapsed)
Out-Line ''
Out-Line 'Nothing was installed or changed.'
Out-Line 'Next step: paste this ENTIRE output to Claude Code. Do not delete the WARN or MISSING lines.'
Out-Line 'Privacy: the report contains tool versions, install paths and which programs own which ports.'
Out-Line 'It contains no passwords, keys, environment-variable values or git identity.'

if ($OutFile) {
    try {
        $script:Lines | Set-Content -Path $OutFile -Encoding UTF8
        Write-Host ('Report also saved to: ' + $OutFile)
    } catch {
        Write-Host ('Could not save the report: ' + $_.Exception.Message)
    }
}
