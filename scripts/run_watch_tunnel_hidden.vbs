' Launcher for Task Scheduler: no console flash (WshShell.Run window style 0 = hidden).
' See docs/WINDOWS_SSH_TUNNEL.md — prefer this /TR instead of bare powershell.exe if the window still blinks.
Option Explicit
Dim sh, fso, ps1, cmd
Set sh = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ps1 = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "watch_split_tunnel.ps1")
cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & ps1 & """"
' 0 = hidden; True = wait until script exits (avoid overlapping runs)
sh.Run cmd, 0, True
