' "NinjaTrader OFF tonight" - the owner's desktop switch (owner 2026-10-07: "wheres the switch to turn
' off the nt8 trader"). Runs tools\nt_night.py off with NO console window: the end-of-day checks
' (backup, one 10-second repair pass, fills, the safety check), then NinjaTrader closes and night mode
' keeps the watchdog from relaunching it until the morning start (05:45 Arizona on the next trading day).
' Same safety rules as the automatic close: never with your real account open, never strips a stop.
' The answer is shown in a small message that closes itself (SHOW_SECONDS).
'
' Deployed copy: C:\EdgeLog\nt_night_off.vbs (repo: deploy\windows\nt_night_off.vbs).
' Desktop shortcut target: C:\Windows\System32\wscript.exe "C:\EdgeLog\nt_night_off.vbs"
Option Explicit
Const PY = "C:\Users\xride\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\pythonw.exe"
Const REPO = "C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
Const LAST = "C:\EdgeLog\nt_night_mode_last.txt"
Const TITLE = "NinjaTrader OFF tonight"
Const SHOW_SECONDS = 20
Dim sh, fso, msg, f
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
If fso.FileExists(LAST) Then fso.DeleteFile LAST, True
sh.Popup "Final checks first, then NinjaTrader closes for the night." & vbCrLf & _
         "This can take a few minutes - a message follows.", 5, TITLE, 64
sh.CurrentDirectory = REPO
sh.Run """" & PY & """ tools\nt_night.py off", 0, True
msg = "Finished, but no answer was written - see C:\EdgeLog\nt_night_mode.log."
If fso.FileExists(LAST) Then
  Set f = fso.OpenTextFile(LAST, 1)
  If Not f.AtEndOfStream Then msg = f.ReadAll
  f.Close
End If
sh.Popup msg, SHOW_SECONDS, TITLE, 64
