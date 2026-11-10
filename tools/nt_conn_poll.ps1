# EdgeLog NT8 CONNECTION POLLER - re-dial Live / Simulation when NinjaTrader drops them.
#
# WHY (2026-11-06, owner: "if NinjaTrader disconnects, have a runner/poller automatically
# reconnect to Live (and Simulation). The app does not need to be closed."). At 09:24:58 that
# morning both connections went ConnectionLost in a 20 s latency burst. The strategies kept
# running (KeepRunning/30 s), so the 3-minute watchdog (nt_recover.ps1) called the box healthy
# and nothing re-dialed Live for five minutes until a person did it by hand.
#
# WHAT IT DOES, every 20 s, and nothing else:
#   GET /connections on the bridge; for each of Live and Simulation whose status is
#   ConnectionLost or Disconnected, POST /connect (the same act as clicking the saved name in
#   NinjaTrader's Connections menu - NinjaTrader holds the credentials, none pass through here),
#   then poll up to 20 s for Connected.
#   Backoff: at most one attempt per name per 60 s; after 10 failed attempts in a row it posts
#   ALERT to the PAPER-NT8 inbox and stops trying that name until the bridge reports it
#   Connected again (a hand re-dial, or the watchdog's own step 0, resets the counter).
#   Opt-out: while C:\EdgeLog\NO_AUTO_RECONNECT_<NAME> exists (upper-case, e.g.
#   NO_AUTO_RECONNECT_LIVE) that name is left alone - so the owner can keep Live down on purpose.
#   Each successful reconnect posts one line to the PAPER-NT8 inbox (from NT-CONNPOLL).
# It never restarts NinjaTrader, never enables/disables a strategy, never touches orders or
# positions. A bridge that does not answer (NinjaTrader closed, night mode, weekend) is logged
# once per change of state and the loop just keeps waiting.
#
# Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File C:\EdgeLog\nt_conn_poll.ps1
#         -Once      one pass, then exit (for a hand check)
#         -WhatIf    report, never re-dial
# Deploy: copy from the repo (tools/nt_conn_poll.ps1) to C:\EdgeLog\nt_conn_poll.ps1, as nt_recover.ps1.
# Starts at logon from the Startup folder (deploy/windows/EdgeLogNtConnPoll.vbs, same hidden-launch
# pattern as EdgeLogRunner.vbs); a second copy exits at once (named mutex). Log: C:\EdgeLog\nt_conn_poll.log

param([switch]$Once, [switch]$WhatIf)

$ErrorActionPreference = 'Continue'
$bridge    = 'http://127.0.0.1:8391'
$py        = 'C:\Program Files\WindowsApps\PythonSoftwareFoundation.Python.3.13_3.13.3824.0_x64__qbz5n2kfra8p0\python3.13.exe'
$repo      = 'C:\Users\xride\OneDrive\Desktop\EDGE-LOG'
$cli       = "$repo\tools\nt_bridge.py"
$inboxPy   = "$repo\tools\chat_inbox.py"
$logPath   = 'C:\EdgeLog\nt_conn_poll.log'
$names     = @('Live', 'Simulation')
$lostStates = @('ConnectionLost', 'Disconnected')
$PollSec    = 20
$BackoffSec = 60
$MaxFails   = 10
$WaitSec    = 20

function Log($m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Write-Host $line
  try { Add-Content -Path $logPath -Value $line -Encoding utf8 } catch {}
}

function Post($text) {
  if ($WhatIf) { Log "[WhatIf] would post to PAPER-NT8: $text"; return }
  try { & $py $inboxPy post --from NT-CONNPOLL PAPER-NT8 $text 2>&1 | ForEach-Object { Log "  [inbox] $_" } }
  catch { Log "  [inbox] post failed: $($_.Exception.Message)" }
}

# Returns a hashtable name -> status, or $null when the bridge does not answer.
function Connections {
  try {
    $d = (Invoke-WebRequest -Uri "$bridge/connections" -TimeoutSec 6 -UseBasicParsing).Content | ConvertFrom-Json
    $h = @{}
    foreach ($c in @($d.connections)) { if ($names -contains $c.name) { $h[$c.name] = "$($c.status)" } }
    return $h
  } catch { return $null }
}

function Redial($n) {
  if ($WhatIf) { Log "[WhatIf] would re-dial '$n'"; return $false }
  try { & $py $cli connect --name $n 2>&1 | ForEach-Object { Log "  [connect $n] $_" } }
  catch { Log "  [connect $n] failed: $($_.Exception.Message)" }
  $t0 = Get-Date
  while (((Get-Date) - $t0).TotalSeconds -lt $WaitSec) {
    Start-Sleep -Seconds 2
    $h = Connections
    if ($h -and $h[$n] -eq 'Connected') { return $true }
  }
  return $false
}

# One copy at a time: the logon launcher and a detach.py hand launch must not both poll.
$script:pollMutex = New-Object System.Threading.Mutex($false, 'Global\EdgeLogNtConnPoll')
try { $gotMutex = $script:pollMutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $gotMutex = $true }
if (-not $gotMutex) { Log "another nt_conn_poll is already running (pid unknown) - this one exits"; exit 0 }

Log "=== nt_conn_poll start pid=$PID (Once=$Once WhatIf=$WhatIf) poll ${PollSec}s backoff ${BackoffSec}s max ${MaxFails} fails ==="
$lastTry  = @{}   # name -> DateTime of the last attempt
$fails    = @{}   # name -> consecutive failed attempts
$alerted  = @{}   # name -> $true once the 10-fail alert went out
$lastSeen = @{}   # name -> last status logged (log on change only)
$bridgeDown = $false

while ($true) {
  $h = Connections
  if ($null -eq $h) {
    if (-not $bridgeDown) { Log "bridge not answering (NinjaTrader closed, starting, or night mode) - waiting"; $bridgeDown = $true }
  } else {
    if ($bridgeDown) { Log "bridge answering again"; $bridgeDown = $false }
    foreach ($n in $names) {
      $st = $h[$n]
      if ($null -eq $st) { if ($lastSeen[$n] -ne 'MISSING') { Log "connection '$n' not in the bridge's list"; $lastSeen[$n] = 'MISSING' }; continue }
      if ($lastSeen[$n] -ne $st) { Log "connection '$n' is $st"; $lastSeen[$n] = $st }
      if ($st -eq 'Connected') {
        if ($fails[$n] -gt 0 -or $alerted[$n]) { Log "connection '$n' is Connected - fail counter reset" }
        $fails[$n] = 0; $alerted[$n] = $false
        continue
      }
      if ($lostStates -notcontains $st) { continue }   # Connecting etc.: let it finish
      $opt = "C:\EdgeLog\NO_AUTO_RECONNECT_$($n.ToUpper())"
      if (Test-Path $opt) { if ($lastSeen["$n.opt"] -ne 1) { Log "connection '$n' is $st but $opt exists - left alone on purpose"; $lastSeen["$n.opt"] = 1 }; continue }
      $lastSeen["$n.opt"] = 0
      if ($alerted[$n]) { continue }
      if ($lastTry[$n] -and (((Get-Date) - $lastTry[$n]).TotalSeconds -lt $BackoffSec)) { continue }
      $lastTry[$n] = Get-Date
      Log "connection '$n' is $st - re-dialing (attempt $($fails[$n] + 1) of $MaxFails)..."
      if (Redial $n) {
        $took = [int]((Get-Date) - $lastTry[$n]).TotalSeconds
        Log "connection '$n' is Connected again after ${took}s"
        Post "NT-CONNPOLL: NinjaTrader '$n' connection was $st at $($lastTry[$n].ToString('HH:mm:ss')) - re-dialed, Connected again after ${took}s (attempt $($fails[$n] + 1))"
        $fails[$n] = 0
      } else {
        $fails[$n] = [int]$fails[$n] + 1
        Log "connection '$n' still not Connected after attempt $($fails[$n]) of $MaxFails"
        if ($fails[$n] -ge $MaxFails) {
          $alerted[$n] = $true
          Log "ALERT: '$n' failed $MaxFails re-dials in a row - giving up until the bridge reports it Connected"
          Post "NT-CONNPOLL ALERT: NinjaTrader '$n' connection has been $st and $MaxFails automatic re-dials over ~$([int]($MaxFails * $BackoffSec / 60)) min did not bring it back - needs a look (NT is still open; nothing else was touched). Auto re-dial of '$n' paused until it shows Connected."
        }
      }
    }
  }
  # Stranded-position guard (owner GO 11-10): a demo position no running strategy owns -> phone within ~40 s,
  # flatten on a 100-pt adverse move or at 13:55 MST. tools/nt_stranded_guard.py holds the rules + tests.
  if ($null -ne $h) {
    $ga = @("$repo\tools\nt_stranded_guard.py", '--once'); if ($WhatIf) { $ga += '--whatif' }
    try { & $py @ga 2>&1 | Where-Object { $_ -match '^(PUSH|FLATTEN|  ->|push failed)' } | ForEach-Object { Log "  [stranded] $_" } }
    catch { Log "  [stranded] guard failed: $($_.Exception.Message)" }
  }
  if ($Once) { break }
  Start-Sleep -Seconds $PollSec
}
Log "=== nt_conn_poll end ==="
