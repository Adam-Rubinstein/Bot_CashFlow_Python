' Launcher for the persistent split-tunnel guardian.
' Runs hidden so Task Scheduler does not flash a console window.
Option Explicit
Dim sh, fso, ps1, cmd
Set sh = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "keep_split_tunnel_alive.ps1")
cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
' 0 = hidden; True = wait until the guardian exits (which is normally never).
sh.Run cmd, 0, True
