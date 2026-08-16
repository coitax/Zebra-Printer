@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$startup = [Environment]::GetFolderPath('Startup');" ^
  "$target = Join-Path '%CD%' 'run-app.bat';" ^
  "$work = '%CD%';" ^
  "foreach ($dir in @($desktop, $startup)) {" ^
  "  $s = $ws.CreateShortcut((Join-Path $dir 'GK420D Sticker Printer.lnk'));" ^
  "  $s.TargetPath = $target;" ^
  "  $s.WorkingDirectory = $work;" ^
  "  $s.WindowStyle = 7;" ^
  "  $s.Description = 'GK420D Sticker Printer';" ^
  "  $s.Save();" ^
  "}"

echo Created shortcuts on the Desktop and in the Startup folder.
echo The app will open after you sign in to Windows.
echo Delete the Startup shortcut if you do not want that.
pause
