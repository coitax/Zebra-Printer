@echo off
setlocal
cd /d "%~dp0"

echo Updating app from GitHub...
git pull --ff-only origin cursor/crop-and-paced-batches 2>nul

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create a virtual environment. Is Python 3 installed?
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import webview, fastapi, uvicorn, PIL" 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo Starting GK420D Sticker Printer ^(desktop window^)...
start "" ".venv\Scripts\pythonw.exe" "%~dp0desktop.py"
