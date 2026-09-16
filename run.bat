@echo off
setlocal
cd /d "%~dp0"

echo Updating app from GitHub...
git pull --ff-only origin cursor/crop-and-paced-batches 2>nul
if errorlevel 1 (
  echo Could not pull latest ^(using local copy^). Check out branch cursor/crop-and-paced-batches in GitHub Desktop if needed.
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create a virtual environment. Is Python 3 installed?
    pause
    exit /b 1
  )
)

echo Installing dependencies if needed...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)

echo Stopping any old server on port 8765...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo Opening browser...
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8765"

echo Starting GK420D sticker app at http://127.0.0.1:8765
echo Look for build tag "4x6-adaptive-crop" under the title to confirm the update loaded.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
