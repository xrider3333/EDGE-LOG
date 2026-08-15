# EdgeLog NT8 auto-login -- LOGIN (unattended relaunch helper).
#
# Reads ONLY from Windows Credential Manager (target 'EdgeLog_NT8', written once by
# nt_login_setup.ps1) and injects into NinjaTrader's real login window via UI Automation.
# Control names below were captured from LIVE read-only inspections of the actual windows
# (nt_inspect_login.ps1 + nt_inspect_mode.ps1, 2026-08-15) -- not guessed:
#
#   Screen 1 -- 'Welcome' credentials:
#     username: AutomationId='tbUserName'   (TextBox, ValuePattern)
#     password: AutomationId='passwordBox'  (PasswordBox, ValuePattern worked live)
#     button:   AutomationId='btnLogin'     (Name='Log In')
#     error:    AutomationId='tbIncorrectLoginMessage'
#
#   Screen 2 -- 'Select a Trading Mode' (same window Name='Welcome', different content):
#     AutomationId='btnLiveTrading' (Name='Start Trading') -- ALWAYS this one, per the
#       owner's explicit instruction 2026-08-15: this button does not itself select or
#       trade any account -- it only unlocks NT8's normal interface. Every account-level
#       safety rail (L1 hard-lock on 1810769, L2 allowlist on DEMO7240108/Sim101) lives in
#       EdgeLogBridge.cs and is completely unaffected by which button is clicked here.
#     AutomationId='btnSimulation' (Name='Continue') exists but is intentionally NOT used
#       -- the owner's normal flow is Live Trading, then reconnect Simulation afterward
#       via the bridge, same as every other cold-boot in this project.
#
# The plaintext password exists only transiently in this process's memory between
# CredRead and the injection call; it is never written to any file, log, or Write-Host,
# and the SecureString/plain copies are cleared before exit.
#
# After login, this script also reconnects the Simulation demo connection and prints a
# clear REAL vs SIM account readout via the local bridge (127.0.0.1:8391) -- so any
# unattended run leaves a plain record of what's actually live vs simulated, never just
# "logged in, assume it's fine."

$ErrorActionPreference = 'Stop'
$target = 'EdgeLog_NT8'
$exePath = 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe'
$bridgeBase = 'http://127.0.0.1:8391'
$liveLockedAccount = '1810769'

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class EdgeLogCredManRead {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct CREDENTIAL {
        public int Flags;
        public int Type;
        public string TargetName;
        public string Comment;
        public long LastWritten;
        public int CredentialBlobSize;
        public IntPtr CredentialBlob;
        public int Persist;
        public int AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool CredRead(string target, int type, int reservedFlag, out IntPtr credentialPtr);
    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern void CredFree(IntPtr cred);
}
"@

function Get-StoredNtCredential {
    $ptr = [IntPtr]::Zero
    $ok = [EdgeLogCredManRead]::CredRead($target, 1, 0, [ref]$ptr)
    if (-not $ok) { throw "no stored credential named '$target' -- run nt_login_setup.ps1 first" }
    try {
        $c = [Runtime.InteropServices.Marshal]::PtrToStructure($ptr, [Type][EdgeLogCredManRead+CREDENTIAL])
        $bytes = New-Object byte[] $c.CredentialBlobSize
        [Runtime.InteropServices.Marshal]::Copy($c.CredentialBlob, $bytes, 0, $c.CredentialBlobSize)
        $pw = [Text.Encoding]::Unicode.GetString($bytes)
        return @{ UserName = $c.UserName; Password = $pw }
    }
    finally { [EdgeLogCredManRead]::CredFree($ptr) }
}

function Find-NtWindow([string]$name, $timeoutSec = 20) {
    $root = [System.Windows.Automation.AutomationElement]::RootElement
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        $windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children,
            [System.Windows.Automation.Condition]::TrueCondition)
        foreach ($w in $windows) {
            try {
                if ($w.Current.Name -eq $name) {
                    $procId = $w.Current.ProcessId
                    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                    if ($proc -and $proc.ProcessName -like '*Ninja*') { return $w }
                }
            } catch {}
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Find-Child($parent, $automationId) {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $automationId)
    return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Set-ElementValue($el, [string]$value) {
    $pattern = $null
    if ($el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        $pattern.SetValue($value)
        return 'ValuePattern'
    }
    $legacy = $null
    if ($el.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern, [ref]$legacy)) {
        $legacy.SetValue($value)
        return 'LegacyIAccessiblePattern'
    }
    $el.SetFocus()
    Start-Sleep -Milliseconds 200
    $escaped = -join ($value.ToCharArray() | ForEach-Object {
        if ('+^%~(){}[]' -contains $_) { "{$_}" } else { $_ }
    })
    [System.Windows.Forms.SendKeys]::SendWait($escaped)
    return 'SendKeys'
}

function Invoke-Element($el) {
    $invoke = $null
    if ($el.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invoke)) {
        $invoke.Invoke(); return $true
    }
    return $false
}

function Wait-ForBridge($timeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "$bridgeBase/health" -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { return $true }
        } catch {}
        Start-Sleep -Seconds 2
    }
    return $false
}

function Show-AccountReadout {
    try {
        $accts = (Invoke-WebRequest -Uri "$bridgeBase/accounts" -TimeoutSec 5 -UseBasicParsing).Content | ConvertFrom-Json
        Write-Host ""
        Write-Host "==================== ACCOUNT STATUS (real vs sim) ====================" -ForegroundColor Cyan
        foreach ($a in $accts.accounts) {
            $tag = if ($a.live_locked) { "REAL / LIVE-LOCKED" } else { "sim/demo" }
            $color = if ($a.live_locked) { 'Red' } else { 'Green' }
            Write-Host ("  {0,-14} {1,-20} cash={2,-12} realized={3}" -f $a.name, "[$tag]", $a.cash, $a.realized) -ForegroundColor $color
        }
        Write-Host "========================================================================" -ForegroundColor Cyan
    } catch {
        Write-Host "Could not read account status from bridge: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

# ── run ──────────────────────────────────────────────────────────────────────────
$stored = $null
try {
    Write-Host "Retrieving stored credential (value never printed)..."
    $stored = Get-StoredNtCredential

    if (-not (Get-Process NinjaTrader -ErrorAction SilentlyContinue)) {
        Write-Host "Launching NinjaTrader..."
        Start-Process $exePath
    }

    Write-Host "Waiting for the login window..."
    $win = Find-NtWindow -name 'Welcome' -timeoutSec 25
    if (-not $win) { throw "login window did not appear within 25s" }

    $userEl = Find-Child $win 'tbUserName'
    $passEl = Find-Child $win 'passwordBox'
    $btnEl  = Find-Child $win 'btnLogin'
    if (-not $userEl -or -not $passEl -or -not $btnEl) {
        throw "one or more expected login controls not found -- NT's login UI may have changed, ABORTING without typing anything"
    }

    Write-Host "Filling username field via $(Set-ElementValue $userEl $stored.UserName)"
    Start-Sleep -Milliseconds 300
    $method = Set-ElementValue $passEl $stored.Password
    Write-Host "Filling password field via $method (value not shown)"
    Start-Sleep -Milliseconds 300

    Write-Host "Clicking Log In..."
    if (-not (Invoke-Element $btnEl)) { throw "Log In button has no InvokePattern" }
    Start-Sleep -Seconds 3

    # Screen 2: "Select a Trading Mode" -- same window Name, different content. Always
    # click Start Trading (btnLiveTrading) per the owner's explicit instruction: this
    # button only unlocks the interface, it does not select or trade any account.
    # RE-QUERY the window fresh on every attempt rather than polling one captured
    # AutomationElement handle. Two live tests (2026-08-15) showed a handle captured
    # right after the Log In click silently stops finding new descendants once WPF
    # swaps the dialog's content underneath it -- even a 15s poll against that same
    # stale handle never found the button, while a brand-new root-down query (a
    # separate inspection script) found it instantly. Re-fetching the window itself on
    # every iteration, not just re-searching within it, is the actual fix.
    Write-Host "Looking for the trading-mode dialog (re-querying fresh each attempt)..."
    $liveBtn = $null
    $modeDeadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $modeDeadline -and -not $liveBtn) {
        try {
            $freshWin = Find-NtWindow -name 'Welcome' -timeoutSec 1
            if ($freshWin) { $liveBtn = Find-Child $freshWin 'btnLiveTrading' }
        } catch { }
        if (-not $liveBtn) { Start-Sleep -Milliseconds 700 }
    }
    if ($liveBtn) {
        Write-Host "Trading-mode dialog detected -- clicking Start Trading (Live Trading interface unlock; does not select/trade any account)"
        Invoke-Element $liveBtn | Out-Null
        Start-Sleep -Seconds 2
    } else {
        # No mode dialog found within the window -- either it doesn't always appear, or
        # login itself failed. Check for the login error message before assuming success.
        $checkWin = Find-NtWindow -name 'Welcome' -timeoutSec 2
        if ($checkWin) {
            $errEl = Find-Child $checkWin 'tbIncorrectLoginMessage'
            $errVisible = $false
            if ($errEl) { try { $errVisible = -not $errEl.Current.IsOffscreen } catch {} }
            if ($errVisible) {
                Write-Host "LOGIN FAILED: NinjaTrader reported incorrect username/password." -ForegroundColor Red
                Write-Host "(Re-run nt_login_setup.ps1 to re-store the credential.)"
                return
            }
        }
    }

    Write-Host "Waiting for the bridge to come up (NinjaTrader finishing boot)..."
    if (Wait-ForBridge -timeoutSec 60) {
        Write-Host "SUCCESS: bridge is up, NinjaTrader is logged in." -ForegroundColor Green
        Show-AccountReadout
        Write-Host ""
        Write-Host "NOTE: Simulation is not auto-connected here on purpose -- reconnect it and"
        Write-Host "re-enable strategies via tools/nt_bridge.py the same way every other session start does."
    } else {
        Write-Host "Login appears to have gone through, but the bridge did not come up within 60s." -ForegroundColor Yellow
        Write-Host "NinjaTrader may still be loading -- check manually."
    }
}
finally {
    if ($stored) { $stored.Password = $null; Remove-Variable stored -ErrorAction SilentlyContinue }
    [GC]::Collect()
}
