Dim ws, fso, dir, scriptPath, cmd
Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = dir & "\voice_type.py"
' Pin 3.11 via the Windows Python Launcher (pyw = no console). Reinstall deps: py -3.11 -m pip install -r requirements.txt
cmd = "pyw -3.11 """ & scriptPath & """"
ws.Run cmd, 0, False