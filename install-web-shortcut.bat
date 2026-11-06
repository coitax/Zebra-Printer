@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$target = Join-Path '%CD%' 'run.bat';" ^
  "$work = '%CD%';" ^
  "$icon = Join-Path '%CD%' 'assets\app.ico';" ^
  "$s = $ws.CreateShortcut((Join-Path $desktop 'GK420D Web Printer.lnk'));" ^
  "$s.TargetPath = $target;" ^
  "$s.WorkingDirectory = $work;" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Open GK420D sticker printer in your browser';" ^
  "if (Test-Path -LiteralPath $icon) { $s.IconLocation = \"$icon,0\" };" ^
  "$s.Save();"

echo Created "GK420D Web Printer" shortcut on your Desktop.
echo Double-click it anytime to open http://127.0.0.1:8765
pause
