@echo off
setlocal
cd /d "%~dp0"
set EXE=%~dp0dist\GK420D Sticker Printer\GK420D Sticker Printer.exe
if not exist "%EXE%" (
  echo The standalone app has not been built yet.
  echo Run build.bat first.
  pause
  exit /b 1
)
start "" "%EXE%"
