# EdgeLog — make it SAFE to switch the PC off.
#
# WHY (2026-08-19): the owner powers the machine down overnight, and the plan is to let the
# nightly SHADOW backfill cover the hours the PC is off (it re-runs every leg on 24-hour
# 1-minute bars, so the performance record stays complete). That works for measuring the
# strategy. It does NOT cover one thing: a REAL position left open on the broker.
#
# NOISE and ORB230 flatten themselves at the session close, so they are never exposed.
# ENGU-Q deliberately holds across sessions -- 6 of its last 11 trades were still open at
# the hour the PC goes off. A position left there is real at the broker: the resting stop
# survives, but nothing trails it, nothing takes its exit, and next morning the recover
# script (correctly) refuses to start anything into that mismatch.
#
# So before shutting down: flatten, then stop the strategies. The shadow leg still records
# what the strategy WOULD have done overnight, which is the number that matters.
#
# Usage:  powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_eod_safe.ps1
#         -WhatIf   report what it WOULD do and change nothing.

param([switch]$WhatIf)

$ErrorActionPreference = 'Stop'
$bridge  = 'http://127.0.0.1:8391'
$py      = 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe'
$cli     = 'C:\Users\xride\AppData\Local\EdgeLog-worktrees\paper\tools\nt_bridge.py'
$acct    = 'DEMO7240108'
$logPath = 'C:\EdgeLog\nt_recover.log'
$roster  = @('EdgeLogNOISE', 'EdgeLogENGUQ1m', 'EdgeLogORB230')

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Write-Host $line
  try { Add-Content -Path $logPath -Value $line -Encoding utf8 } catch {}
}

function Get-Json($path) {
  try { return (Invoke-WebRequest -Uri "$bridge$path" -TimeoutSec 8 -UseBasicParsing).Content }
  catch { return $null }
}

Log "=== eod-safe start (WhatIf=$WhatIf) ==="

$pos = Get-Json "/positions"
if ($null -eq $pos) {
  Log "bridge is not answering - NinjaTrader is already down. Nothing to do."
  exit 0
}

$hasPosition = $pos -notmatch '"positions"\s*:\s*\[\s*\]'
if ($hasPosition) {
  Log "OPEN POSITION on $acct - this must not be left overnight:"
  Log "  $pos"
  if ($WhatIf) {
    Log "WhatIf: would flatten $acct"
  } else {
    Log "flattening $acct ..."
    & $py $cli flatten --account $acct --yes 2>&1 | ForEach-Object { Log "  [flatten] $_" }
    Start-Sleep -Seconds 6
    $pos2 = Get-Json "/positions"
    if ($pos2 -notmatch '"positions"\s*:\s*\[\s*\]') {
      Log "STILL NOT FLAT after flatten - do NOT power off, check NinjaTrader by hand:"
      Log "  $pos2"
      exit 1
    }
    Log "account is flat"
  }
} else {
  Log "account is already flat - nothing to close"
}

# Stop the strategies so nothing half-fills as the machine goes down, and so tomorrow's
# recover starts from a known state rather than whatever a killed process left behind.
foreach ($s in $roster) {
  if ($WhatIf) { Log "WhatIf: would disable $s"; continue }
  Log "disabling $s ..."
  & $py $cli strategy disable --name $s --yes 2>&1 | ForEach-Object { Log "  [disable] $_" }
  Start-Sleep -Seconds 3
}

if (-not $WhatIf) {
  $ord = Get-Json "/orders"
  if ($ord -and $ord -notmatch '"orders"\s*:\s*\[\s*\]') {
    Log "WARNING: working orders remain after disabling - review before powering off:"
    Log "  $ord"
    exit 1
  }
}

Log "SAFE TO POWER OFF: no position, no working orders, strategies stopped."
Log "The nightly shadow run still records what every leg would have done overnight."
exit 0
