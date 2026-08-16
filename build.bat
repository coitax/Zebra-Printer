@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)
echo Installing build dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

echo Building standalone Windows app...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --onedir --name "GK420D Sticker Printer" --add-data "static;static" --hidden-import app.main --hidden-import app.printer --hidden-import app.image_pipeline --hidden-import app.zpl --hidden-import app.calibration --hidden-import app.presets --hidden-import app.paths --hidden-import win32print --hidden-import win32api --hidden-import pywintypes --hidden-import pythoncom --hidden-import uvicorn.logging --hidden-import uvicorn.loops --hidden-import uvicorn.loops.auto --hidden-import uvicorn.protocols --hidden-import uvicorn.protocols.http --hidden-import uvicorn.protocols.http.auto --hidden-import uvicorn.protocols.websockets.auto --hidden-import uvicorn.lifespan --hidden-import uvicorn.lifespan.on --hidden-import multipart --collect-all webview --collect-all uvicorn desktop.py
if errorlevel 1 exit /b 1

echo.
echo Built: dist\GK420D Sticker Printer\GK420D Sticker Printer.exe
echo You can copy that whole folder anywhere and double-click the exe.
echo Do not move the exe out of its folder.
