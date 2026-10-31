Option Explicit
Dim shell, fs, base, command, result
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
base = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base
command = "pyw -3 " & Chr(34) & fs.BuildPath(base, "bootstrap.py") & Chr(34)
On Error Resume Next
result = shell.Run(command, 0, False)
If Err.Number <> 0 Then
    MsgBox "Instal Python 3.12 untuk Windows beserta Python Launcher dari python.org, lalu buka Auto Upload lagi.", 48, "Auto Upload"
End If
