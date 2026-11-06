@echo off
setlocal
cd /d "%~dp0"

echo Building application (PyInstaller onedir)...
call build.bat
if errorlevel 1 exit /b 1

if not exist "dist\GK420D Sticker Printer\GK420D Sticker Printer.exe" (
  echo Expected exe not found after build.
  exit /b 1
)

where iscc >nul 2>&1
if errorlevel 1 (
  echo.
  echo Inno Setup 6 compiler ^(iscc.exe^) was not found on PATH.
  echo Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
  echo Then add its folder to PATH, or run:
  echo   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\installer.iss
  echo.
  echo Application build is ready in: dist\GK420D Sticker Printer\
  exit /b 0
)

echo Compiling Windows installer...
iscc "installer\installer.iss"
if errorlevel 1 exit /b 1

echo.
echo Installer: dist\installer\GK420D-Sticker-Printer-Setup.exe
exit /b 0
