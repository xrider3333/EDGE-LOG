' EdgeLog QQQ SHADOW adapter - detached launcher.
'
' WHY A SEPARATE PROCESS (2026-09-09). The adapter used to be a thread inside the job
' runner, so its uptime was a property of the busiest process on this box: about thirty
' concurrent sessions restart the runner fleet all day to load code, and on 2026-09-09
' that booted the adapter EIGHT times before 14:00. The day recorded ~94 percent tick
' coverage against a 95 percent readiness bar, so the forward trial was being failed by
' deploys rather than by anything wrong with the adapter. api/runner.py now calls
' qqq_exec.ensure_standalone(), which leaves a live adapter alone and only launches this
' when none is serving - so a fleet restart is a no-op for the shadow book.
'
' WHY WSCRIPT. A process started from a session's console dies with that console and,
' worse, orphans into the powershell 0xC0000142 popup loop that cost a day on 2026-09-01.
' wscript with a hidden window owns no console, so nothing it spawns can inherit a dead one.
'
' Shape copied deliberately from _run_worker.vbs (plain "python" through cmd, output
' appended to its own log) so there is one launcher idiom on this box, not two.
'
' INSTALL: copy to C:\EdgeLog\_run_qqq_exec.vbs - the path in qqq_exec.QQQ_EXEC_VBS.
' The adapter is SHADOW ONLY: this starts no order path of any kind.
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")

sh.CurrentDirectory = "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"

' NTFY_TOPIC so the adapter's own alerts (breaker, kill file, end of day) reach the phone
' instead of falling back to log-only - the same value _restart_runner.bat sets.
' 0 = hidden window, False = do not wait: this must outlive whatever launched it.
sh.Run "cmd /c ""set NTFY_TOPIC=edgelog-ESmQqoq7tFF9PZVHs6azgDYI && " & _
       "python -u -m api.qqq_exec --serve --uid IO0K35JpLIcH9YK4C0pMNYUzZOM2 " & _
       "--cred serviceAccount.json " & _
       ">> C:\EdgeLog\qqq_exec_serve.log 2>&1""", 0, False
