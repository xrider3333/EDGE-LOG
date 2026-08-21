# EdgeLog — check whether it is safe to switch the PC off, WITHOUT closing anything.
#
# WHY (2026-08-19): the owner shuts the machine down overnight. The first version of this
# script flattened any open position first. That was wrong twice over:
#
#   1. It invents an exit the strategy never chose. The whole point of the forward test is
#      to compare live trading against the engine's record; a forced close writes a trade
#      outcome into the live ledger that no strategy rule produced. That is not a shutdown
#      procedure, it is data corruption.
#   2. It then DISABLED the strategies. NinjaTrader cancels a strategy's working orders
#      when it is disabled -- so on any night the flatten had failed or been skipped, the
#      sequence would have stripped the protective stop off a live position and left it
#      naked overnight. That is the single worst thing this stack could do.
#
# What is actually true: the protective stops are GTC (verified in NinjaTrader's own
# strategy records, 2026-08-19), so they rest at the broker rather than inside NinjaTrader.
# A position left open overnight keeps its stop. What it loses is the TRAIL -- nothing
# moves the stop up, and the strategy cannot take its own exit -- until the machine is back.
#
# So this script no longer closes anything. It reports whether powering off is safe, and
# only stops the strategies when there is nothing open to protect.
#
# Usage:  powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_eod_safe.ps1
#         -WhatIf   report only, change nothing.

param([switch]$WhatIf)

$ErrorActionPreference = 'Stop'
$bridge  = 'http://127.0.0.1:8391'
$py      = 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe'
$cli     = 'C:\Users\xride\AppData\Local\EdgeLog-worktrees\paper\tools\nt_bridge.py'
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

Log "=== eod-safe check (WhatIf=$WhatIf) ==="

$pos = Get-Json "/positions"
if ($null -eq $pos) {
  Log "bridge is not answering - NinjaTrader is already down. Nothing to check."
  exit 0
}
$ord = Get-Json "/orders"
$hasPosition = $pos -notmatch '"positions"\s*:\s*\[\s*\]'
$hasOrders   = $ord -and ($ord -notmatch '"orders"\s*:\s*\[\s*\]')

if (-not $hasPosition) {
  Log "account is FLAT - nothing is exposed overnight"
  foreach ($s in $roster) {
    if ($WhatIf) { Log "WhatIf: would stop $s (safe: nothing open)"; continue }
    Log "stopping $s ..."
    & $py $cli strategy disable --name $s --yes 2>&1 | ForEach-Object { Log "  [disable] $_" }
    Start-Sleep -Seconds 3
  }
  Log "SAFE TO POWER OFF. The nightly shadow run still records what every leg would have done."
  exit 0
}

# --- something is open ---------------------------------------------------------------
Log "POSITION IS OPEN:"
Log "  $pos"
if ($hasOrders) {
  Log "protective order(s) resting at the broker (GTC - these survive NinjaTrader closing):"
  Log "  $ord"
} else {
  Log "WARNING: NO working protective order found next to this position."
  Log "Powering off now would leave it completely unprotected. Deal with it before shutdown."
  exit 1
}

Log ""
Log "NOT stopping the strategies: disabling one cancels its orders, which would strip the"
Log "stop off this position and leave it naked overnight."
Log "NOT closing the position either: the strategy did not choose that exit, and forcing it"
Log "would write a trade into the live record that no rule produced."
Log ""
Log "Powering off now is SURVIVABLE but not free:"
Log "  - the stop stays where it is; nothing will trail it up while the PC is off"
Log "  - the strategy cannot take its own exit until the machine is back"
Log "  - tomorrow, recover will refuse to start anything until this is resolved"
Log "Leaving the PC on until this trade closes is the clean option."
exit 2
