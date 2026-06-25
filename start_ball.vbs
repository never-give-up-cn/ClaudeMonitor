' Launch floating ball without any console window
Dim shell, fso, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetFile(WScript.ScriptFullName).ParentFolder.Path
Set shell = CreateObject("WScript.Shell")
shell.Run "pyw -3 """ & scriptDir & "\floating_ball.py""", 0, False
