@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Failed to create a virtual environment. Is Python 3 installed?
    exit /b 1
  )
)

".venv\Scripts\python.exe" -c "import webview, fastapi, uvicorn, PIL" 2>nul
if errorlevel 1 (
  echo Installing dependencies...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

echo Starting GK420D Sticker Printer...
start "" ".venv\Scripts\pythonw.exe" "%~dp0desktop.py"
