@echo off
setlocal
cd /d "%~dp0"

set "ICON=%CD%\assets\app.ico"
if not exist "%ICON%" set "ICON=%CD%\dist\GK420D Sticker Printer\GK420D Sticker Printer.exe"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$target = Join-Path '%CD%' 'run-app.bat';" ^
  "$work = '%CD%';" ^
  "$icon = '%ICON%';" ^
  "$s = $ws.CreateShortcut((Join-Path $desktop 'GK420D Sticker Printer.lnk'));" ^
  "$s.TargetPath = $target;" ^
  "$s.WorkingDirectory = $work;" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'GK420D Sticker Printer';" ^
  "if (Test-Path -LiteralPath $icon) { $s.IconLocation = \"$icon,0\" };" ^
  "$s.Save();"

echo Created Desktop shortcut with sticker icon (Startup not modified).
echo Rebuild with build.bat to update the .exe icon too.
pause
