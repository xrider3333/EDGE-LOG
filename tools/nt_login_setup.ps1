# EdgeLog NT8 auto-login -- SETUP (run once, interactively, BY THE ACCOUNT OWNER ONLY).
#
# Stores NinjaTrader 8 login credentials in Windows Credential Manager, encrypted by
# Windows itself (DPAPI, tied to this Windows user account) via the real CredWrite API --
# not the `cmdkey` command-line tool, whose /pass argument can briefly appear in the
# process list on this machine. The password is read via PowerShell's built-in masked
# Get-Credential prompt: it is never typed into this script's source, never written to
# any log or file, and never seen by anything outside this one process's memory, which
# is explicitly zeroed before the script exits.
#
# Written for EDGELOG's NT8 bridge project (2026-08-15). Companion script: nt_login.ps1
# reads this credential back and (once its UI-injection half is verified against the
# real NT8 login window) uses it for unattended relaunches.
#
# Run this from a PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File C:\EdgeLog\nt_login_setup.ps1

$ErrorActionPreference = 'Stop'
$target = 'EdgeLog_NT8'

Write-Host "This stores your NinjaTrader 8 login in Windows Credential Manager -- the same"
Write-Host "encrypted store Windows/Chrome use for saved passwords. It is NOT written to any"
Write-Host "file, log, or script. Only this Windows user account can ever decrypt it."
Write-Host ""

$cred = Get-Credential -Message "NinjaTrader 8 login (email + password)"

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class EdgeLogCredMan {
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
    public static extern bool CredWrite([In] ref CREDENTIAL userCredential, [In] uint flags);
}
"@

$bstr = $null
$blob = [IntPtr]::Zero
try {
    $bstr  = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $bytes = [Text.Encoding]::Unicode.GetBytes($plain)
    $blob  = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
    [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $blob, $bytes.Length)

    $c = New-Object EdgeLogCredMan+CREDENTIAL
    $c.Type              = 1   # CRED_TYPE_GENERIC
    $c.TargetName         = $target
    $c.Comment            = 'EDGELOG NT8 auto-login -- see C:\EdgeLog\nt_login.ps1'
    $c.CredentialBlobSize = $bytes.Length
    $c.CredentialBlob     = $blob
    $c.Persist            = 2   # CRED_PERSIST_LOCAL_MACHINE
    $c.UserName           = $cred.UserName

    $ok = [EdgeLogCredMan]::CredWrite([ref]$c, 0)
    if ($ok) {
        Write-Host ""
        Write-Host "Stored. Target='$target' UserName='$($cred.UserName)'." -ForegroundColor Green
        Write-Host "Verify any time with: cmdkey /list:$target   (shows the username only, never the password)"
    } else {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        Write-Host "CredWrite failed, Win32 error $err" -ForegroundColor Red
    }
}
finally {
    # Zero every copy of the plaintext this process ever made.
    if ($bstr -ne $null) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($blob -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::FreeHGlobal($blob) }
    Remove-Variable plain, bytes, cred -ErrorAction SilentlyContinue
    [GC]::Collect()
}
