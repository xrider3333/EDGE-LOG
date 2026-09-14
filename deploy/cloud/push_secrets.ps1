<#
.SYNOPSIS
  Copies EDGE-LOG's local secret FILES to the Oracle Cloud VM over scp. Run this BY
  HAND, from a PowerShell window on the owner's PC -- never automatically, never by a
  Claude session.

.DESCRIPTION
  Copies ONLY:
    - the Firebase service-account key (serviceAccount.json)
    - the existing LIVE Webull key file + its token directory's token.txt
    - the PAPER Webull key file, IF one already exists locally (skipped otherwise --
      this script never creates, edits, or checks the CONTENTS of paper credentials,
      only whether the file is present)
  Nothing else, and nothing beyond those exact files. This script NEVER prints, logs,
  or inspects the CONTENTS of any secret file -- only its name, byte size, and path --
  and it never places an order, never touches Firebase/Webull itself, and never runs
  as part of any automated step (install.sh does not call this; the owner runs it).

  Each copied file is chmod'd 600 on the VM (owner read/write only) right after the
  scp completes.

.PARAMETER VmIp
  Public IP address of the Oracle Cloud VM (README.md step (a)).

.PARAMETER KeyPath
  Path to the SSH private key downloaded when the VM was created (README.md step (a)).

.PARAMETER RemoteUser
  SSH user on the VM. Default: ubuntu (Oracle's Canonical Ubuntu image default).

.PARAMETER RemoteHome
  EDGELOG_HOME on the VM. Default: /home/<RemoteUser>/edgelog -- matches install.sh's
  own default of $HOME/edgelog when it was run as that same user.

.PARAMETER LocalRepo
  Path to the EDGE-LOG checkout on this PC (where serviceAccount.json lives).

.PARAMETER LocalEdgeLogHome
  Path to this PC's EdgeLog home (where webull_keys.json / webull_token / an existing
  webull_paper_keys.json live). Default: C:\EdgeLog.

.EXAMPLE
  .\push_secrets.ps1 -VmIp 123.45.67.89 -KeyPath C:\Users\xride\Downloads\oracle-vm-key.key

.NOTES
  Requires an `ssh`/`scp` client on PATH (Windows 10/11 ship OpenSSH client by
  default). Idempotent: safe to re-run any time a secret changes (e.g. a fresh Webull
  live token) -- it simply overwrites the remote file and re-applies chmod 600.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$VmIp,

    [Parameter(Mandatory = $true)]
    [string]$KeyPath,

    [string]$RemoteUser = "ubuntu",

    [string]$RemoteHome = "",

    [string]$LocalRepo = "C:\Users\xride\OneDrive\Desktop\EDGE-LOG",

    [string]$LocalEdgeLogHome = "C:\EdgeLog"
)

$ErrorActionPreference = "Stop"

if (-not $RemoteHome -or $RemoteHome -eq "") {
    $RemoteHome = "/home/$RemoteUser/edgelog"
}
$RemoteRepo = "$RemoteHome/EDGE-LOG"

if (-not (Test-Path -LiteralPath $KeyPath)) {
    Write-Error "SSH key not found at $KeyPath -- check the -KeyPath parameter."
    exit 1
}

function Copy-SecretFile {
    param(
        [string]$LocalPath,
        [string]$RemotePath,
        [string]$Label
    )
    if (-not (Test-Path -LiteralPath $LocalPath)) {
        Write-Host ("  [skip]    {0,-32} not found locally at {1}" -f $Label, $LocalPath) -ForegroundColor Yellow
        return $false
    }
    $sizeBytes = (Get-Item -LiteralPath $LocalPath).Length
    Write-Host ("  [copying] {0,-32} ({1} bytes) -> {2}@{3}:{4}" -f $Label, $sizeBytes, $RemoteUser, $VmIp, $RemotePath)

    # scp will not create a missing remote directory -- make sure it exists first.
    $remoteDir = $RemotePath.Substring(0, $RemotePath.LastIndexOf("/"))
    & ssh -i $KeyPath "$RemoteUser@$VmIp" "mkdir -p '$remoteDir'"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [FAILED]  {0,-32} could not create remote directory {1}" -f $Label, $remoteDir) -ForegroundColor Red
        return $false
    }

    & scp -i $KeyPath $LocalPath "${RemoteUser}@${VmIp}:$RemotePath"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [FAILED]  {0,-32} scp exited {1}" -f $Label, $LASTEXITCODE) -ForegroundColor Red
        return $false
    }

    & ssh -i $KeyPath "$RemoteUser@$VmIp" "chmod 600 '$RemotePath'"
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  [WARN]    {0,-32} copied but chmod 600 failed -- fix by hand" -f $Label) -ForegroundColor Yellow
        return $true
    }

    Write-Host ("  [ok]      {0,-32} copied, chmod 600 set" -f $Label) -ForegroundColor Green
    return $true
}

Write-Host "EDGE-LOG secret push -> $RemoteUser@${VmIp}:$RemoteHome" -ForegroundColor Cyan
Write-Host "This copies FILES ONLY. Their contents are never printed by this script." -ForegroundColor Cyan
Write-Host ""

$results = [ordered]@{}

$results["Firebase service account"] = Copy-SecretFile `
    -LocalPath (Join-Path $LocalRepo "serviceAccount.json") `
    -RemotePath "$RemoteRepo/serviceAccount.json" `
    -Label "Firebase service account"

$results["Webull LIVE keys"] = Copy-SecretFile `
    -LocalPath (Join-Path $LocalEdgeLogHome "webull_keys.json") `
    -RemotePath "$RemoteHome/webull_keys.json" `
    -Label "Webull LIVE keys"

$results["Webull LIVE token"] = Copy-SecretFile `
    -LocalPath (Join-Path $LocalEdgeLogHome "webull_token\token.txt") `
    -RemotePath "$RemoteHome/webull_token/token.txt" `
    -Label "Webull LIVE token"

$paperKeysPath = Join-Path $LocalEdgeLogHome "webull_paper_keys.json"
if (Test-Path -LiteralPath $paperKeysPath) {
    $results["Webull PAPER keys"] = Copy-SecretFile `
        -LocalPath $paperKeysPath `
        -RemotePath "$RemoteHome/webull_paper_keys.json" `
        -Label "Webull PAPER keys"
} else {
    Write-Host ("  [skip]    {0,-32} not found locally at {1} (see README.md `"Webull ORDER adapter`" -- normal until paper access is set up)" -f "Webull PAPER keys", $paperKeysPath) -ForegroundColor Yellow
    $results["Webull PAPER keys"] = $false
}

Write-Host ""
Write-Host "Checklist:" -ForegroundColor Cyan
foreach ($key in $results.Keys) {
    if ($results[$key]) {
        Write-Host ("  [x] {0}" -f $key) -ForegroundColor Green
    } else {
        Write-Host ("  [ ] {0} -- not copied" -f $key) -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host "Next: SSH in, edit ~/edgelog/edgelog.env, then start the services (README.md's numbered checklist)." -ForegroundColor Cyan
