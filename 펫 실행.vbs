' 데스크탑 펫 - 콘솔 창 없이 조용히 실행
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.Run "pythonw pet.py", 0, False
