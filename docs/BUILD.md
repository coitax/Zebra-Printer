# Build the standalone Windows app

The browser version does not need this. Use these steps only when you want a fresh `GK420D Sticker Printer.exe`.

## What you need

- Windows 10 or 11
- Python 3.12+ on PATH (`py -3 --version`)
- The Zebra printer already installed in Windows (ZDesigner queue)

## Build

From the repo root:

```bat
build.bat
```

That will:

1. Create `.venv` if it is missing
2. Install [requirements.txt](../requirements.txt) plus PyInstaller
3. Package `desktop.py`, the FastAPI app, and `static/` into an onedir build

Output:

```
dist\GK420D Sticker Printer\GK420D Sticker Printer.exe
```

The `_internal` folder next to the exe is required. Copy the whole `GK420D Sticker Printer` directory, not the exe alone.

## Run the build

- Double-click the exe, or
- `start-exe.bat` from the repo (only works after a local build)

Closing the window stops the local server.

## Rebuild after code changes

Run `build.bat` again. `--clean` is already on, so the previous `dist` folder is replaced.

## Browser version (no build)

```bat
run.bat
```

Then open http://127.0.0.1:8765 and leave the console open.

`run-app.bat` is the same UI in a desktop window, still using your local Python venv. It does not produce an exe.
