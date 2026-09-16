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

".venv\Scripts\python.exe" -m pip install -q -r requirements.txt

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
