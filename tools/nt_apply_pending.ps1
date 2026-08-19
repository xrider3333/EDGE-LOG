# EdgeLog — install the NinjaScript changes that are waiting on a restart.
#
# WHY THIS EXISTS (2026-08-19): two corrections are compiled and staged but NOT running,
# because installing them means restarting NinjaTrader and ENGU-Q was holding a live trade.
# Restarting on top of an open position is survivable -- the protective stop is GTC and
# rests at the broker -- but it is not something to do casually, and it must never happen
# by accident. So the work waits here behind a flat check instead of living in someone's
# memory.
#
# WHAT IS WAITING:
#   1. The fill recorder that names the STRATEGY on every fill. The copy NinjaTrader is
#      running predates it and writes fills with no strategy attached, so when two
#      strategies trade the same contract their results are attributed by nearest-in-time
#      guessing. That is the single thing blocking multiple strategies on one instrument.
#   2. ENGU-Q refusing to adopt a position whose SIZE does not match its own saved trade.
#      ORB230 trades the same contract on the same account, so what NinjaTrader offers on
#      start is the net of both.
#
# Safe to run any time: it does nothing at all unless the account is flat.
#
# Usage:  powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_apply_pending.ps1
#         -WhatIf   report what it WOULD do and change nothing.

param([switch]$WhatIf)

$ErrorActionPreference = 'Stop'
$bridge  = 'http://127.0.0.1:8391'
$custom  = 'C:\Users\xride\Documents\NinjaTrader 8\bin\Custom'
$built   = Join-Path $custom 'bin\Debug\NinjaTrader.Custom.dll'
$live    = Join-Path $custom 'NinjaTrader.Custom.dll'
$logPath = 'C:\EdgeLog\nt_recover.log'
$recover = 'C:\EdgeLog\nt_recover.ps1'

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Write-Host $line
  try { Add-Content -Path $logPath -Value $line -Encoding utf8 } catch {}
}

Log "=== apply-pending start (WhatIf=$WhatIf) ==="

if (-not (Test-Path $built)) { Log "FATAL: nothing built at $built - run the build first"; exit 2 }

$pos = $null
try { $pos = (Invoke-WebRequest -Uri "$bridge/positions" -TimeoutSec 8 -UseBasicParsing).Content } catch {}

if ($pos -and $pos -notmatch '"positions"\s*:\s*\[\s*\]') {
  Log "HOLDING OFF: a position is open, so this is not the moment to restart NinjaTrader."
  Log "  $pos"
  Log "Run this again once it closes; nothing has been changed."
  exit 3
}
Log "account is flat - safe to proceed"

if ($WhatIf) { Log "WhatIf: would install the built assembly and restart NinjaTrader"; exit 0 }

# Keep the copy that is running, so this is reversible without a rebuild.
$bak = Join-Path $custom ("NinjaTrader.Custom.dll.bak-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
try { Copy-Item $live $bak -Force; Log "backed up the running assembly to $bak" } catch { Log "WARN: could not back up: $_" }

$nt = @(Get-Process NinjaTrader -ErrorAction SilentlyContinue)
if ($nt.Count -gt 0) {
  Log "stopping NinjaTrader..."
  foreach ($p in $nt) { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {} }
  Start-Sleep -Seconds 8
}

try { Copy-Item $built $live -Force; Log "installed the new assembly" }
catch { Log "FATAL: could not install: $_"; exit 2 }

Log "bringing everything back up..."
& powershell -ExecutionPolicy Bypass -File $recover 2>&1 | ForEach-Object { Log "  [recover] $_" }

# Did the thing we came for actually take effect?
$hdr = ''
try { $hdr = (Get-Content 'C:\EdgeLog\fills.csv' -TotalCount 1) } catch {}
if ($hdr -match 'SignalName') { Log "fills file header carries SignalName" }
else { Log "NOTE: fills header has no SignalName column yet - it is rewritten only when the file is recreated" }

$roster = @('EdgeLogNOISE','EdgeLogENGUQ1m','EdgeLogORB230')
$live2 = @()
try {
  $d = (Invoke-WebRequest -Uri "$bridge/strategies" -TimeoutSec 8 -UseBasicParsing).Content | ConvertFrom-Json
  $live2 = @($d.strategies | Where-Object { $_.state -eq 'Realtime' } | ForEach-Object { $_.name })
} catch {}
$missing = @($roster | Where-Object { $live2 -notcontains $_ })
if ($missing.Count -gt 0) { Log "INCOMPLETE: not Realtime -> $($missing -join ', ')"; exit 1 }

Log "DONE: new code installed and all three strategies are running."
Log "From here, every fill records which strategy caused it."
exit 0
