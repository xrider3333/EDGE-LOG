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
Dim sh, fso
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

sh.CurrentDirectory = "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"

' NTFY_TOPIC / NTFY_TOKEN so the adapter's own alerts (breaker, kill file, end of day)
' reach the phone instead of falling back to log-only. Used to be a literal topic right
' here -- this repo is public, so anyone who cloned it could read (and post to) it
' (WEBULL_GO_LIVE.md 1.10). Both now come from an UNTRACKED local file instead:
'   C:\EdgeLog\secrets\ntfy.env
' one KEY=VALUE per line, '#' comments and blank lines ignored, e.g.:
'   # ntfy push topic/token -- see WEBULL_GO_LIVE.md 1.10
'   NTFY_TOPIC=edgelog-xxxxxxxxxxxxxxxxxxxx
'   NTFY_TOKEN=tk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
' NTFY_TOKEN is optional (a private topic's access token, sent as an Authorization
' header once the runner side is switched to api/ntfy_push.py). A missing file, or a
' missing key inside it, just leaves that piece unset -- same "push skipped, log only"
' fallback as an unset env var always had.
' FILE FORMAT, exactly: create the C:\EdgeLog\secrets\ folder first (it does not exist
' by default), then save this file as plain ASCII or UTF-8 WITHOUT a byte-order mark
' (BOM) -- a BOM on the first line makes THIS parser's first `If ntfyLine ... <> "#"`
' check fail to match NTFY_TOPIC on that line, so it stays unset with no error at all
' (tools/_restart_runner.bat.example's `for /f` loop is more forgiving of a BOM here,
' but do not rely on that). What NEITHER parser can read at all is UTF-16: Windows
' PowerShell 5.1's `Out-File`/`Set-Content`/`>` all default to UTF-16LE, not UTF-8 --
' write this file with
'   [IO.File]::WriteAllText('C:\EdgeLog\secrets\ntfy.env', "# ...`r`nNTFY_TOPIC=...`r`n",
'     (New-Object Text.UTF8Encoding $false))
' instead. Starting the file with a '#' comment line (as in the example above) means a
' stray BOM can only ever land on a line this parser already ignores.
Dim ntfyTopic, ntfyToken, ntfyEnvPath, ntfyLine, ntfyParts, ntfyFile
ntfyTopic = ""
ntfyToken = ""
ntfyEnvPath = "C:\EdgeLog\secrets\ntfy.env"
If fso.FileExists(ntfyEnvPath) Then
    Set ntfyFile = fso.OpenTextFile(ntfyEnvPath, 1)
    Do While Not ntfyFile.AtEndOfStream
        ntfyLine = Trim(ntfyFile.ReadLine)
        If Len(ntfyLine) > 0 And Left(ntfyLine, 1) <> "#" And InStr(ntfyLine, "=") > 0 Then
            ntfyParts = Split(ntfyLine, "=", 2)
            If UCase(Trim(ntfyParts(0))) = "NTFY_TOPIC" Then ntfyTopic = Trim(ntfyParts(1))
            If UCase(Trim(ntfyParts(0))) = "NTFY_TOKEN" Then ntfyToken = Trim(ntfyParts(1))
        End If
    Loop
    ntfyFile.Close
End If

' Set these on the VBS process's OWN environment rather than splicing
' `set NTFY_TOPIC=<val> && ...` into the cmd command line below: the command line of
' every process is visible to any other local process (`tasklist /v`, Process Explorer,
' etc.), so the old form put the token in plain sight the same way the topic used to be
' hardcoded in this file. sh.Run's child cmd.exe inherits this process's environment,
' so nothing here needs to pass NTFY_TOPIC/NTFY_TOKEN through the command line at all --
' and there is no `set X=val ` trailing space to strip, either.
sh.Environment("Process")("NTFY_TOPIC") = ntfyTopic
If ntfyToken <> "" Then sh.Environment("Process")("NTFY_TOKEN") = ntfyToken

' 0 = hidden window, False = do not wait: this must outlive whatever launched it.
sh.Run "cmd /c """ & _
       "python -u -m api.qqq_exec --serve --uid IO0K35JpLIcH9YK4C0pMNYUzZOM2 " & _
       "--cred serviceAccount.json " & _
       ">> C:\EdgeLog\qqq_exec_serve.log 2>&1""", 0, False
