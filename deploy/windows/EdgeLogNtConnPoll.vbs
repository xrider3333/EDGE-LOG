' EDGELOG NT8 connection poller - launches hidden at logon (same pattern as EdgeLogRunner.vbs / EdgeLogGate.vbs).
' Re-dials the Live / Simulation NinjaTrader connections when they drop (owner 2026-11-06). Source of truth:
' tools/nt_conn_poll.ps1 in the repo, deployed to C:\EdgeLog\nt_conn_poll.ps1. A second copy exits at once (mutex).
' Install: copy this file to %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\EdgeLogNtConnPoll.vbs
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\EdgeLog\nt_conn_poll.ps1""", 0, False
