' EdgeLog runner launcher - the logon entry (Startup folder) and the manual double-click
' start. Since 2026-09-08 it does ONE thing: hand off to C:\EdgeLog\_restart_runner.bat,
' which is the single definition of the runner set (the primary plus its drain-only
' workers, the environment, the log). Before that this file carried its own copy of the
' python command line and had already drifted from the bat (no ntfy topic, no drawdown
' floor), and it started only the primary - so every logon or restart silently dropped
' the job queue back to ONE slot until somebody launched the workers by hand.
' A copy of this file lives at %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\
' EdgeLogRunner.vbs; keep the two identical.
' Window style 0 = a hidden console that belongs to nobody, so the runner survives
' whatever launched it (see _restart_runner_hidden.vbs for the 0xC0000142 story).
Set sh = CreateObject("WScript.Shell")
sh.Run "cmd /c """"C:\EdgeLog\_restart_runner.bat""""", 0, False
