' "NinjaTrader ON now" - the owner's desktop switch (owner 2026-10-07). Runs tools\nt_night.py on with
' NO console window: night mode ends at once and the watchdog pass that brings NinjaTrader up (login,
' Simulation, strategies - exactly as every morning) starts now. The answer is shown in a small
' message that closes itself (SHOW_SECONDS).
'
' Deployed copy: C:\EdgeLog\nt_night_on.vbs (repo: deploy\windows\nt_night_on.vbs).
' Desktop shortcut target: C:\Windows\System32\wscript.exe "C:\EdgeLog\nt_night_on.vbs"
Option Explicit
Const PY = "C:\Users\xride\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
Const REPO = "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
Const LAST = "C:\EdgeLog\nt_night_mode_last.txt"
Const TITLE = "NinjaTrader ON now"
Const SHOW_SECONDS = 15
Dim sh, fso, msg, f
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
If fso.FileExists(LAST) Then fso.DeleteFile LAST, True
sh.CurrentDirectory = REPO
sh.Run """" & PY & """ tools\nt_night.py on", 0, True
msg = "Finished, but no answer was written - see C:\EdgeLog\nt_night_mode.log."
If fso.FileExists(LAST) Then
  Set f = fso.OpenTextFile(LAST, 1)
  If Not f.AtEndOfStream Then msg = f.ReadAll
  f.Close
End If
sh.Popup msg, SHOW_SECONDS, TITLE, 64
