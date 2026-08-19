' EDGELOG — lock the desktop shortly after an automatic logon.
'
' WHY: NinjaTrader is a desktop application. It cannot run when nobody is signed in --
' there is no desktop for it to exist on. So "keep the strategies running while I am not
' at the machine" really means "keep a Windows session alive without a human present",
' which is what Windows auto-logon does. The cost is that the machine boots to an OPEN
' desktop. This closes that hole: the session stays alive (so NinjaTrader, the gate
' service and the runner keep running) but the screen requires the password to touch.
'
' The delay lets the other Startup-folder items launch first.
' To disable, simply delete this file from the Startup folder.
Dim sh
Set sh = CreateObject("WScript.Shell")
WScript.Sleep 90000                       ' 90 seconds
sh.Run "rundll32.exe user32.dll,LockWorkStation", 0, False
