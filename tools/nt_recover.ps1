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
# ENGU-Q ADDED 2026-08-17: the old exclusion (ImmediatelySubmit rejecting its sync order
# outside market hours, proven 2026-08-14) no longer applies -- it now runs WaitUntilFlat
# on the 24h ETH session (#226 config), so enabling it is safe around the clock. After it
# reaches Realtime, check /orders: its warm-up replay can leave a REAL orphan stop (EQx)
# guarding a position that exists only in the replay.
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

# ── SYNC CHECK ─────────────────────────────────────────────────────────────────────
# "Realtime" is not the same as "working". ENGU-Q sat Realtime for a full day holding a
# position the account never had -- inherited from replayed history -- and therefore
# placed no orders at all. Nothing alerted, because every check only asked whether the
# strategy was running. Strategies now start flat by design, so a strategy claiming a
# position the account does not hold means they have drifted apart: either it inherited
# a ghost again, or a real fill went unrecorded. Both are real-money problems, and both
# are invisible unless something explicitly compares the two sides.
function SyncProblems {
  # THE INVARIANT: for each instrument, the strategies positions must ADD UP to what the
  # account holds. The first version compared each strategy against the account on its own,
  # which is only right while one strategy trades an instrument. ENGU-Q and ORB230 both
  # trade NQ on this account, so the account shows their NET -- ENGU-Q long 1 while ORB230
  # is short 1 nets to flat, and the old check would have called both of them broken.
  # Summing catches the real fault (a strategy holding something the account never got, or
  # a fill nobody recorded) without inventing one every time two strategies disagree.
  $out = @()
  try {
    $acctJson = (Invoke-WebRequest -Uri "$bridge/positions" -TimeoutSec 8 -UseBasicParsing).Content | ConvertFrom-Json
    $acct = @{}
    foreach ($p in @($acctJson.positions)) {
      $q = [int]$p.qty; if ("$($p.side)" -match "Short") { $q = -$q }
      $acct["$($p.instrument)"] = ([int]$acct["$($p.instrument)"]) + $q
    }
    $strat = @{}
    foreach ($st in (Roster)) {
      $pos = "$($st.position)"; $inst = "$($st.instrument)"
      if (-not $inst) { continue }
      $q = 0
      if ($pos -match "^(Long|Short)\s+(\d+)") {
        $q = [int]$Matches[2]; if ($Matches[1] -eq "Short") { $q = -$q }
      }
      $strat[$inst] = ([int]$strat[$inst]) + $q
    }
    foreach ($inst in @($strat.Keys + $acct.Keys | Select-Object -Unique)) {
      $sSum = [int]$strat[$inst]; $aSum = [int]$acct[$inst]
      if ($sSum -ne $aSum) {
        $out += "$inst : strategies add up to $sSum but the account holds $aSum"
      }
    }
  } catch { }
  return $out
}
# Top-level window titles belonging to the NinjaTrader process, read from OUTSIDE the app.
# Needed because a modal raised during startup blocks the very UI thread the bridge would
# have to use to report it -- so the app cannot describe its own blockage.
Add-Type @"
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
public class NtWin {
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr h, out int pid);
  delegate bool EnumProc(IntPtr h, IntPtr l);
  public static List<string> Titles(int wantPid) {
    var outp = new List<string>();
    EnumWindows((h, l) => {
      int pid; GetWindowThreadProcessId(h, out pid);
      if (pid == wantPid && IsWindowVisible(h)) {
        var sb = new StringBuilder(512); GetWindowText(h, sb, 512);
        var t = sb.ToString().Trim();
        if (t.Length > 0) outp.Add(t);
      }
      return true;
    }, IntPtr.Zero);
    return outp;
  }
}
"@ -ErrorAction SilentlyContinue

function NtWindowTitles {
  try {
    $p = @(Get-Process NinjaTrader -ErrorAction SilentlyContinue)
    if ($p.Count -eq 0) { return @() }
    return @([NtWin]::Titles($p[0].Id))
  } catch { return @() }
}
Log "=== recover start (WhatIf=$WhatIf) ==="

# ── 1. already healthy? ────────────────────────────────────────────────────────────
if (BridgeUp) {
  $live = @(RealtimeNames)
  $missing = @($expected | Where-Object { $live -notcontains $_ })
  if ($missing.Count -eq 0) {
    $sync = @(SyncProblems)
    if ($sync.Count -gt 0) {
      Log "OUT OF SYNC - running, but not trading what you think:"
      foreach ($m in $sync) { Log "  $m" }
      Log "A strategy holding a position the account does not have will not open new trades."
      exit 4
    }
    Log "healthy: bridge up, all expected strategies Realtime ($($expected -join ', ')), in sync with the account"
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

  # WEDGED, not down. "Bridge unreachable" was assumed to mean NinjaTrader had exited or
  # was sitting at its login window -- so this went straight to the login script, which
  # waits for a login window that a RUNNING NinjaTrader never shows. On 2026-08-18 a
  # Tradovate drop left the app alive but unresponsive (UI thread pegged, 3.4 GB), and
  # this loop then relaunched the login every 10 minutes for an hour: no recovery, a pile
  # of stranded processes, and a popup each time. If the process EXISTS but the bridge is
  # dead, the app is hung -- give it one grace period to finish whatever it is doing, then
  # end it so the launch path below starts a clean one.
  $ntProc = @(Get-Process NinjaTrader -ErrorAction SilentlyContinue)
  if ($ntProc.Count -gt 0) {
    Log "NinjaTrader is RUNNING but the bridge is dead - it is hung, not down. Waiting 60s..."
    Start-Sleep -Seconds 60
    if (BridgeUp) {
      Log "bridge answered during the grace period - it was only busy, carrying on"
    } else {
      Log "still hung after 60s - ending the process so a clean instance can start"
      foreach ($p in $ntProc) { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {} }
      Start-Sleep -Seconds 8
    }
  }

  if (BridgeUp) { Log "bridge is up - no login needed" } else {
  Log "running unattended login..."
  & powershell -ExecutionPolicy Bypass -File $loginPs1 2>&1 | ForEach-Object { Log "  [login] $_" }
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Date) -lt $deadline -and -not (BridgeUp)) { Start-Sleep -Seconds 5 }
  if (-not (BridgeUp)) { Log "FATAL: bridge still unreachable after login attempt"; exit 2 }
  Log "bridge is up"
  }
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
# RETRY, because a freshly-launched NinjaTrader is not ready the moment the bridge
# answers. The strategies live on CHARTS, and the charts take another minute or two to
# load their history; until they exist the bridge correctly reports "no reachable
# instance". On 2026-08-19 this ran ~20s after login, got three 404s, declared
# INCOMPLETE and gave up -- leaving everything down until the next 10-minute pass, in
# the middle of the session. Keep trying for a few minutes instead of failing once.
$deadline4 = (Get-Date).AddMinutes(4)
do {
  $pending = @($expected | Where-Object { @(RealtimeNames) -notcontains $_ })
  if ($pending.Count -eq 0) { break }
  foreach ($s in $pending) {
    Log "enabling $s..."
    & $py $cli strategy enable --name $s --yes 2>&1 | ForEach-Object { Log "  [enable] $_" }
    Start-Sleep -Seconds 4
  }
  $pending = @($expected | Where-Object { @(RealtimeNames) -notcontains $_ })
  if ($pending.Count -gt 0) {
    # A MODAL DIALOG blocks the workspace from loading, so the charts never appear and
    # every enable answers "no reachable instance" forever. On 2026-08-19 a monitor-layout
    # prompt ("windows outside the viewable range, reposition to the primary monitor?")
    # held everything up while this logged the same 404 over and over.
    # The bridge cannot see such a dialog -- it is raised before NinjaTraders UI is up,
    # so the in-process window walk returns nothing. Enumerate NinjaTraders top-level
    # windows from OUTSIDE the app instead, and say what is on screen: only a person can
    # answer a dialog, and they need to be told rather than left guessing.
    $titles = @(NtWindowTitles)
    $blocking = @($titles | Where-Object { $_ -and $_ -notmatch "^(Control Center|Chart|NinjaScript Editor|Strategy Analyzer)" })
    if ($blocking.Count -gt 0) {
      Log "A DIALOG IS BLOCKING NINJATRADER - nobody can recover this without a click:"
      foreach ($t in $blocking) { Log "  window: $t" }
      Log "Answer it on screen, then this will recover on its next pass."
      exit 5
    }
    Log "still waiting on: $($pending -join ', ') - charts may still be loading, retrying in 20s"
    Start-Sleep -Seconds 20
  }
} while ((Get-Date) -lt $deadline4)
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
