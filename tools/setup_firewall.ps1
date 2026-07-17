<#
.SYNOPSIS
    Allow phones/tablets on your network to reach HONE (LAN mode / QR codes).

.DESCRIPTION
    With `lan = true` the web and live servers bind 0.0.0.0, but Windows Firewall
    still drops inbound connections unless a rule allows them - the phone just
    hangs on a blank page. This script opens HONE's two ports for the local
    subnet only, and moves the active network off the Public profile (which
    blocks inbound by default, and which our Private-scoped rule never matches).

    Rules are keyed on the ports, not on python.exe: the launcher spawns whatever
    interpreter it was started with, so a program rule would break every time the
    virtualenv is recreated.

    Run it by hand (right-click -> "Run with PowerShell") to set things up, or
    with -Auto from HONE.bat, which checks first and only asks for elevation when
    something is actually missing.

.PARAMETER Auto
    Startup mode: do nothing unless LAN mode is on AND the firewall is not already
    set up. Never pauses, and never fails the caller - HONE must start even if the
    user dismisses the elevation prompt.

.PARAMETER Undo
    Remove the rule. Leaves the network profile as it is.
#>

[CmdletBinding()]
param(
    [switch]$Auto,
    [switch]$Undo
)

$ErrorActionPreference = 'Stop'
$RuleName = 'HONE (LAN)'

function Write-Step($msg, $colour = 'Gray') {
    # In -Auto we only speak up when we actually change something, so the normal
    # HONE.bat console stays clean.
    Write-Host $msg -ForegroundColor $colour
}

# --- settings from config.toml ---------------------------------------------
# Defaults mirror accoach.config (Config.lan, ServerCfg.port, WebCfg.port).
$lan = $false
$serverPort = 8777
$webPort = 8778
$configPath = Join-Path $env:USERPROFILE 'Documents\ACCoach\config.toml'
if (Test-Path $configPath) {
    # Tiny section-aware scan - enough for top-level `lan` and `[server]/[web] port`,
    # falling back to the defaults on anything unexpected rather than failing.
    $section = ''
    foreach ($line in Get-Content $configPath) {
        $trimmed = $line.Trim()
        if ($trimmed -match '^\[(.+)\]') { $section = $Matches[1]; continue }
        if ($section -eq '' -and $trimmed -match '^lan\s*=\s*(true|false)') {
            $lan = ($Matches[1] -eq 'true')
        }
        if ($trimmed -match '^port\s*=\s*(\d+)') {
            if ($section -eq 'server') { $serverPort = [int]$Matches[1] }
            if ($section -eq 'web') { $webPort = [int]$Matches[1] }
        }
    }
}
$ports = @($serverPort, $webPort) | Select-Object -Unique

# --- current state (readable without admin) --------------------------------
# The interface carrying the default route is the one a phone reaches us on -
# the same one accoach.netinfo.lan_ip() resolves by routing toward 8.8.8.8.
$route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
    Sort-Object RouteMetric | Select-Object -First 1
$netProfile = $null
$ip = $null
if ($route) {
    # Not $profile - that name shadows PowerShell's automatic $PROFILE variable.
    $netProfile = Get-NetConnectionProfile -InterfaceIndex $route.ifIndex -ErrorAction SilentlyContinue
    $ip = (Get-NetIPAddress -InterfaceIndex $route.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' } | Select-Object -First 1).IPAddress
}

function Test-RuleReady {
    # True when exactly one enabled Allow rule covers precisely our ports. Any
    # drift (ports changed in config.toml, rule disabled by hand) counts as
    # not-ready so the setup path rebuilds it.
    $rules = @(Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)
    if ($rules.Count -ne 1) { return $false }
    $rule = $rules[0]
    if ("$($rule.Enabled)" -ne 'True') { return $false }
    if ("$($rule.Action)" -ne 'Allow') { return $false }
    $have = @(($rule | Get-NetFirewallPortFilter).LocalPort) | Sort-Object
    $want = @($script:ports | ForEach-Object { "$_" }) | Sort-Object
    return -not (Compare-Object $have $want)
}

# A Private-scoped rule simply does not apply while the network is Public, so an
# unfixed Public profile means we are not reachable even with the rule in place.
$profilePublic = $netProfile -and $netProfile.NetworkCategory -eq 'Public'

# --- startup gate ----------------------------------------------------------
if ($Auto -and -not $Undo) {
    if (-not $lan) { exit 0 }            # local-only setup: nothing to open
    if (-not $route) { exit 0 }          # offline: no network to be reachable on
    if ((Test-RuleReady) -and -not $profilePublic) { exit 0 }   # already good
    Write-Step 'HONE: LAN mode is on but this PC is not reachable from other devices yet.' 'Yellow'
    Write-Step 'Asking for admin rights once to open the ports (see the UAC prompt).' 'Yellow'
}

# --- elevate ---------------------------------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    if (-not $Auto) { Write-Host 'Firewall changes need admin rights - asking Windows for elevation...' }
    $psArgs = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"")
    if ($Auto) { $psArgs += '-Auto' }
    if ($Undo) { $psArgs += '-Undo' }
    try {
        # -Wait so the rule exists before HONE's servers start accepting devices.
        Start-Process powershell.exe -Verb RunAs -ArgumentList $psArgs -Wait
    } catch {
        # Dismissed UAC. Say so, but never take HONE down over it.
        Write-Step 'Skipped: no admin rights, so phones/tablets will not be able to connect.' 'Yellow'
        Write-Step 'Run tools\setup_firewall.ps1 by hand when you want to fix that.' 'Yellow'
    }
    exit 0
}

# --- undo ------------------------------------------------------------------
if ($Undo) {
    $existing = @(Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)
    if ($existing.Count) {
        $existing | Remove-NetFirewallRule -Confirm:$false
        Write-Host "Removed the '$RuleName' firewall rule. Devices can no longer reach HONE." -ForegroundColor Green
    } else {
        Write-Host "No '$RuleName' rule found - nothing to remove."
    }
    if (-not $Auto) { Write-Host ''; Read-Host 'Press Enter to close' }
    exit 0
}

# --- report what we found --------------------------------------------------
if (-not $route) {
    Write-Host 'No default route - this machine is not on a network. Nothing to do.' -ForegroundColor Yellow
    if (-not $Auto) { Read-Host 'Press Enter to close' }
    exit 0
}
Write-Host ("Ports:   {0} (live coach)  {1} (analysis/engineer web app)" -f $serverPort, $webPort)
Write-Host ("Network: {0} on {1} - IP {2}" -f $netProfile.Name, $netProfile.InterfaceAlias, $ip)
Write-Host ''

# --- network profile -------------------------------------------------------
# Public blocks inbound by default and is meant for cafes/airports. A home or
# paddock network you trust enough to stream telemetry over should be Private.
if ($profilePublic) {
    Write-Host ("'{0}' is set to Public, which blocks incoming connections." -f $netProfile.Name) -ForegroundColor Yellow
    Write-Host 'Switching it to Private so trusted devices on this network can connect.'
    Set-NetConnectionProfile -InterfaceIndex $route.ifIndex -NetworkCategory Private
    Write-Host 'Network profile -> Private' -ForegroundColor Green
} elseif ($netProfile.NetworkCategory -eq 'DomainAuthenticated') {
    Write-Host 'Network is domain-joined; leaving its profile alone.'
} else {
    Write-Host ("Network profile is already {0} - no change needed." -f $netProfile.NetworkCategory)
}

# --- firewall rule ---------------------------------------------------------
# Recreate rather than patch: the port list may have changed in config.toml.
$existing = @(Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)
if ($existing.Count) {
    $existing | Remove-NetFirewallRule -Confirm:$false
    Write-Host "Replacing the existing '$RuleName' rule."
}
New-NetFirewallRule -DisplayName $RuleName `
    -Description 'Lets phones/tablets on your local network open the HONE report, engineer and test pages.' `
    -Direction Inbound -Protocol TCP -LocalPort $ports -Action Allow `
    -Profile Private, Domain -RemoteAddress LocalSubnet | Out-Null
Write-Host ("Firewall rule '{0}' created: TCP {1} inbound, local subnet only." -f $RuleName, ($ports -join ', ')) -ForegroundColor Green

# --- what to do next -------------------------------------------------------
Write-Host ''
if ($ip) {
    Write-Host 'Scan the QR codes in the Devices section, or open these on your phone:'
    Write-Host ("  http://{0}:{1}/          report" -f $ip, $webPort) -ForegroundColor Cyan
    Write-Host ("  http://{0}:{1}/engineer  setup engineer" -f $ip, $webPort) -ForegroundColor Cyan
    Write-Host ("  http://{0}:{1}/test      on-track test" -f $ip, $webPort) -ForegroundColor Cyan
}
Write-Host ''
Write-Host 'To undo later, run this script with -Undo.'
if ($Auto) {
    Start-Sleep -Seconds 4     # elevated window is its own console; let them read it
} else {
    Write-Host ''
    Read-Host 'Press Enter to close'
}
