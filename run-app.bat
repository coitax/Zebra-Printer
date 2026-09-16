@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Python 3 is required. Install from python.org then run this again.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import webview, fastapi, uvicorn, PIL" 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

start "" ".venv\Scripts\pythonw.exe" "%~dp0desktop.py"
