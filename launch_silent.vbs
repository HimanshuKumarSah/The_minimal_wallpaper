Set WshShell = CreateObject("WScript.Shell")
strPath = WshShell.CurrentDirectory
If InStr(WScript.ScriptFullName, "\") > 0 Then
    strPath = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
End If
WshShell.CurrentDirectory = strPath

Set fso = CreateObject("Scripting.FileSystemObject")

' Launch silently (no console window): packaged exe first, then a real
' pythonw.exe. Microsoft Store app-execution aliases are skipped because they
' only open the Store page instead of running Python.
If fso.FileExists(strPath & "\YearProgress.exe") Then
    WshShell.Run """" & strPath & "\YearProgress.exe"" --minimized", 0, False
Else
    pythonw = FindPythonw()
    If pythonw <> "" Then
        WshShell.Run """" & pythonw & """ """ & strPath & "\main.py"" --minimized", 0, False
    Else
        MsgBox "Could not find a Python interpreter to start Year Progress Wallpaper." & vbCrLf & vbCrLf & _
               "Install Python 3, or place YearProgress.exe in:" & vbCrLf & strPath, _
               vbExclamation, "Year Progress Wallpaper"
    End If
End If

Function FindPythonw()
    Dim candidates, i, line, exec
    candidates = Array( _
        WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe"), _
        WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"), _
        WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"), _
        WshShell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"))
    For i = 0 To UBound(candidates)
        If fso.FileExists(candidates(i)) Then
            FindPythonw = candidates(i)
            Exit Function
        End If
    Next

    On Error Resume Next
    Set exec = WshShell.Exec("where pythonw.exe")
    If Err.Number = 0 Then
        Do While Not exec.StdOut.AtEndOfStream
            line = Trim(exec.StdOut.ReadLine())
            If line <> "" And fso.FileExists(line) Then
                If InStr(1, line, "WindowsApps", vbTextCompare) = 0 Then
                    FindPythonw = line
                    Exit Function
                End If
            End If
        Loop
    End If
    Err.Clear
    On Error GoTo 0

    FindPythonw = ""
End Function
