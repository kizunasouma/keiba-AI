' デスクトップに競馬AI予測のショートカットを作成する
Set WshShell = WScript.CreateObject("WScript.Shell")
strDesktop = WshShell.SpecialFolders("Desktop")

Set oShortcut = WshShell.CreateShortcut(strDesktop & "\競馬AI予測.lnk")
oShortcut.TargetPath = "C:\code\keiba-AI\keiba-ai.bat"
oShortcut.WorkingDirectory = "C:\code\keiba-AI"
oShortcut.WindowStyle = 7  ' 最小化で実行（バッチ画面を目立たせない）
oShortcut.Description = "競馬AI予測デスクトップアプリ"

' アイコンがあればそれを使う、なければ既定のアイコン
oShortcut.IconLocation = "C:\code\keiba-AI\assets\icon.ico,0"

oShortcut.Save
WScript.Echo "デスクトップにショートカットを作成しました。"
