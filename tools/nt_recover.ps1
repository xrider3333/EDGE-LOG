# EdgeLog NT8 AUTO-RECOVER — bring NinjaTrader all the way back, unattended.
#
# WHY (2026-08-16): every piece of this already existed and nothing chained them. Twice in
# one session NinjaTrader was found sitting at its login screen with the bridge unreachable
# and the board correctly showing DOWN — and each time recovery was three manual steps:
# run the login script, dial Simulation, re-enable the strategies. That is exactly the
# "something goes wrong and I am not around" case the whole bridge project exists for.
#
# WHAT IT DOES, in order, and only as far as it needs to:
#   1. If the bridge already answers AND the expected strategies are Realtime -> exit 0,
#      touch nothing. Safe to run on a timer.
#   2. Launch + log in via nt_login.ps1 if NinjaTrader is down or stuck at the login window.
#   3. Dial the Simulation connection.
#   4. Re-enable each expected strategy that is not already Realtime.
#   5. Print a real vs sim account readout and verify the roster; exit non-zero if the
#      end state is still wrong, so a scheduler/monitor can tell success from noise.
#
# IT NEVER TOUCHES THE LIVE ACCOUNT. Every mutation goes through the bridge, which hard-
# refuses account 1810769 in its own compiled code (L1) regardless of what this asks for.
#
# Usage:  powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_recover.ps1
#         -WhatIf   report what it WOULD do and exit, changing nothing.

param([switch]$WhatIf)

$ErrorActionPreference = 'Stop'
$bridge   = 'http://127.0.0.1:8391'
$py       = 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe'
$cli      = 'C:\Users\xride\AppData\Local\EdgeLog-worktrees\paper\tools\nt_bridge.py'
$loginPs1 = 'C:\EdgeLog\nt_login.ps1'
$logPath  = 'C:\EdgeLog\nt_recover.log'
# The roster this box is supposed to be running.
# ENGU-Q ADDED 2026-08-17: it runs the 24h ETH session (#226 config), so enabling it
# is safe around the clock. As of 2026-08-18 it REFUSES to open positions on replayed
# history, so it starts FLAT and in sync instead of inheriting a ghost trade -- which
# previously either armed a real orphan stop or blocked it from trading for days.
# EdgeLogORBV2 REMOVED 2026-08-16: it still ran the retired look-ahead-era params
# while the engine's ORB crown moved to run #230, so its fills measured a dead
# config. EdgeLogORB230 ADDED 2026-08-17 (owner's call): the honest #230 port,
# created offline via nt_reconfig --add-orb230 and live on ORBV2's NQ 5-min chart.
# Its fills still owe a reconcile against the engine's blotter -- forward, as they land.
$expected = @('EdgeLogNOISE', 'EdgeLogENGUQ1m', 'EdgeLogORB230')
$connName = 'Simulation'

function Log($m){
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Write-Host $line
  try { Add-Content -Path $logPath -Value $line -Encoding utf8 } catch {}
}

function BridgeUp {
  try { $r = Invoke-WebRequest -Uri "$bridge/health" -TimeoutSec 4 -UseBasicParsing; return $r.StatusCode -eq 200 }
  catch { return $false }
}

function Roster {
  try {
    $d = (Invoke-WebRequest -Uri "$bridge/strategies" -TimeoutSec 6 -UseBasicParsing).Content | ConvertFrom-Json
    return @($d.strategies)
  } catch { return @() }
}

function RealtimeNames { (Roster | Where-Object { $_.state -eq 'Realtime' } | ForEach-Object { $_.name }) }

Log "=== recover start (WhatIf=$WhatIf) ==="

# ── 1. already healthy? ────────────────────────────────────────────────────────────
if (BridgeUp) {
  $live = @(RealtimeNames)
  $missing = @($expected | Where-Object { $live -notcontains $_ })
  if ($missing.Count -eq 0) {
    Log "healthy: bridge up and all expected strategies Realtime ($($expected -join ', ')) - nothing to do"
    exit 0
  }
  Log "bridge up but not Realtime: $($missing -join ', ')"
} else {
  Log "bridge unreachable - NinjaTrader is down or sitting at the login window"
}

if ($WhatIf) { Log "WhatIf: stopping before any action"; exit 0 }

# ── 2. log in / launch if needed ───────────────────────────────────────────────────
if (-not (BridgeUp)) {
  if (-not (Test-Path $loginPs1)) { Log "FATAL: $loginPs1 missing"; exit 2 }
  Log "running unattended login..."
  & powershell -ExecutionPolicy Bypass -File $loginPs1 2>&1 | ForEach-Object { Log "  [login] $_" }
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Date) -lt $deadline -and -not (BridgeUp)) { Start-Sleep -Seconds 5 }
  if (-not (BridgeUp)) { Log "FATAL: bridge still unreachable after login attempt"; exit 2 }
  Log "bridge is up"
}

# ── 3. dial the demo connection ────────────────────────────────────────────────────
Log "connecting '$connName'..."
& $py $cli connect --name $connName 2>&1 | ForEach-Object { Log "  [connect] $_" }
Start-Sleep -Seconds 20

# ── 3b. REAL-MONEY GATE: never auto-enable into an out-of-sync account ─────────────
# A strategy that starts flat while the ACCOUNT holds a real position leaves that
# position unmanaged -- no trail, no stop maintenance, nobody watching it. Strategies
# start flat by design (they refuse to open positions on replayed history), so an open
# position here means a restart caught a live trade. That is a human-judgment moment:
# report it loudly and stop rather than quietly enabling into a mismatch.
$posJson = ""
try { $posJson = (Invoke-WebRequest -Uri "$bridge/positions" -TimeoutSec 8 -UseBasicParsing).Content } catch {}
if ($posJson -and $posJson -notmatch '"positions"\s*:\s*\[\s*\]') {
  Log "STOP: the account is holding a position while strategies are down:"
  Log "  $posJson"
  Log "Not enabling anything -- a strategy starting flat would leave this position unmanaged."
  Log "Decide by hand: flatten it, or enable the strategy knowing it will not manage this trade."
  exit 3
}

# ── 4. enable whatever is not already Realtime ─────────────────────────────────────
foreach ($s in $expected) {
  $live = @(RealtimeNames)
  if ($live -contains $s) { Log "$s already Realtime"; continue }
  Log "enabling $s..."
  & $py $cli strategy enable --name $s --yes 2>&1 | ForEach-Object { Log "  [enable] $_" }
  Start-Sleep -Seconds 4
}
Start-Sleep -Seconds 5

# ── 5. verify + report ─────────────────────────────────────────────────────────────
& $py $cli accounts 2>&1 | ForEach-Object { Log "  [accounts] $_" }
$live = @(RealtimeNames)
$missing = @($expected | Where-Object { $live -notcontains $_ })
if ($missing.Count -gt 0) {
  Log "INCOMPLETE: still not Realtime -> $($missing -join ', ')"
  exit 1
}
Log "RECOVERED: $($expected -join ', ') are Realtime"
exit 0
