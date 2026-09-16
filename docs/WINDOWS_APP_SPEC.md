# Windows Application Specification & Conversion Guide

**Project:** GK420D Sticker Printer  
**Audience:** Developers packaging or extending this repo as a native-feeling Windows app  
**Last updated:** 2026-09-16

This document is the complete specification and step-by-step instructions for turning the existing **FastAPI + static web UI** into a **Windows desktop application** — from a quick pywebview wrapper through a distributable `.exe`, installer, shortcuts, and production polish.

---

## Table of contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Current architecture](#2-current-architecture)
3. [Three run modes (today)](#3-three-run-modes-today)
4. [Recommended conversion strategy](#4-recommended-conversion-strategy)
5. [Phase A — Desktop window (pywebview)](#5-phase-a--desktop-window-pywebview)
6. [Phase B — Standalone executable (PyInstaller)](#6-phase-b--standalone-executable-pyinstaller)
7. [Phase C — Production Windows app polish](#7-phase-c--production-windows-app-polish)
8. [PyInstaller reference spec](#8-pyinstaller-reference-spec)
9. [Installer packaging (Inno Setup)](#9-installer-packaging-inno-setup)
10. [Icons, manifest, and Windows integration](#10-icons-manifest-and-windows-integration)
11. [Single-instance and lifecycle](#11-single-instance-and-lifecycle)
12. [File associations and drag-to-app](#12-file-associations-and-drag-to-app)
13. [Logging, crash reporting, and updates](#13-logging-crash-reporting-and-updates)
14. [Security model](#14-security-model)
15. [Testing matrix](#15-testing-matrix)
16. [Troubleshooting frozen builds](#16-troubleshooting-frozen-builds)
17. [Alternative stacks (when not to use pywebview)](#17-alternative-stacks-when-not-to-use-pywebview)
18. [Checklist: ship a Windows app](#18-checklist-ship-a-windows-app)

---

## 1. Goals and non-goals

### Goals

| Goal | Description |
| --- | --- |
| **Double-click launch** | User opens one shortcut; no browser tabs, no manual URL, no visible terminal |
| **Reuse existing UI** | Keep `static/index.html`, `app.js`, `styles.css` unchanged — the web UI *is* the app |
| **Keep Python backend** | FastAPI, Pillow, pypdfium2, win32print RAW pipeline stays as-is |
| **USB Zebra printing** | Continue using Windows spooler + `pywin32` RAW jobs to GK420D/GX420d |
| **Offline-first** | All processing local; server binds `127.0.0.1` only |
| **Optional portable exe** | Folder copy to USB or Desktop without Python installed |

### Non-goals (for this conversion path)

- Rewriting the UI in WPF, WinUI 3, or Electron (unnecessary — see [§17](#17-alternative-stacks-when-not-to-use-pywebview))
- macOS or Linux builds (printer integration is Windows-specific today)
- Cloud print queue or multi-user server deployment
- Replacing ZPL with Windows GDI printing (would reintroduce driver scaling bugs)

---

## 2. Current architecture

The app is already a **local web application**. Converting it to a “Windows app” means **hosting that same localhost server inside a native shell**, not rewriting business logic.

```
┌──────────────────────────────────────────────────────────────────────┐
│  Windows shell (choose one)                                          │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────┐ │
│  │ System browser  │  │ pywebview window │  │ PyInstaller onedir  │ │
│  │ (run.bat)       │  │ (run-app.bat)    │  │ (.exe + _internal)  │ │
│  └────────┬────────┘  └────────┬─────────┘  └──────────┬──────────┘ │
└───────────┼─────────────────────┼───────────────────────┼───────────┘
            │                     │                       │
            └─────────────────────┼───────────────────────┘
                                  │  http://127.0.0.1:8765
┌─────────────────────────────────▼────────────────────────────────────┐
│  uvicorn (FastAPI) — app/main.py                                     │
│  Serves static/ · REST API · multipart uploads · ZPL download        │
└──────┬───────────────────────┬───────────────────────┬───────────────┘
       │                       │                       │
┌──────▼──────┐        ┌───────▼────────┐      ┌───────▼───────┐
│ image_      │        │ zpl.py         │      │ printer.py    │
│ pipeline.py │        │ ^GFA encoding  │      │ win32print    │
└─────────────┘        └────────────────┘      └───────────────┘
```

**Key file:** `desktop.py` — entry point for the windowed app. It:

1. Starts uvicorn on `127.0.0.1:8765` in a **daemon thread** (unless port already open)
2. Waits until the port accepts connections
3. Opens a **pywebview** window pointed at the local URL
4. Blocks until the window closes; process exits and the daemon thread dies

**Key file:** `app/paths.py` — resolves `static/` for both dev and frozen exe:

```python
def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)  # PyInstaller onefile/onedir extract dir
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # repo root
```

FastAPI mounts static files from `resource_root() / "static"`. **No code changes are required** in the API layer for packaging if `static/` is bundled correctly.

---

## 3. Three run modes (today)

| Mode | Launcher | Python required? | UI | Server lifecycle |
| --- | --- | --- | --- | --- |
| **Web** | `run.bat` | Yes (auto venv) | Default browser | Console open = server running |
| **Desktop (dev)** | `run-app.bat` | Yes (auto venv) | pywebview window | `pythonw desktop.py`; no console |
| **Standalone exe** | `build.bat` → exe | No | pywebview in bundle | Window close = exit |

**User-facing quick launch (web):**

- `run.bat` — creates venv, installs deps, kills stale `:8765`, opens browser
- `web.bat` — alias to `run.bat`
- `install-web-shortcut.bat` — Desktop shortcut **GK420D Web Printer**

**User-facing desktop shortcut (dev):**

- `install-shortcut.bat` — Desktop + Startup shortcuts to `run-app.bat`

---

## 4. Recommended conversion strategy

Use a **phased approach**. Do not skip Phase A validation before investing in PyInstaller.

| Phase | Deliverable | Effort | User experience |
| --- | --- | --- | --- |
| **A** | pywebview + `run-app.bat` | Done | Desktop window; needs Python on machine |
| **B** | PyInstaller onedir exe | 1–2 hours first time | Portable folder; no Python |
| **C** | Installer + icon + single-instance | 1–2 days | Feels like a “real” app from Start menu |
| **D** (optional) | MSIX / auto-update / code signing | Days | Store-ready or enterprise deploy |

**Decision:** Stay on **pywebview + embedded uvicorn**. The UI is complex (cropper, PDF pages, live preview); rewriting would take weeks with no print benefit.

---

## 5. Phase A — Desktop window (pywebview)

### 5.1 What pywebview does

[pywebview](https://pywebview.flowrl.com/) creates a native window (Edge WebView2 on Windows 10/11) and loads a URL. It is **not** a full browser — no tabs, no extensions — which is ideal for a single-purpose tool.

**Dependency:** `pywebview>=5.3` (already in `requirements.txt`).

**Runtime requirement:** **Microsoft Edge WebView2 Runtime** — preinstalled on most Windows 11 systems; may need separate install on clean Windows 10.

### 5.2 How `desktop.py` works (line-by-line behavior)

| Step | Code behavior | Why it matters |
| --- | --- | --- |
| Port check | `_port_open()` connects to `:8765` | If user already ran `run.bat`, desktop reuses existing server |
| Server thread | `uvicorn.Server` with `log_level="warning"` | Keeps console quiet when run under `pythonw` |
| Wait loop | `_wait_for_server()` up to 8s | Webview must not load blank page before FastAPI is ready |
| Fallback | If `webview` import fails → `webbrowser.open` | Graceful degrade on broken venv |
| Window size | 1220×900, min 900×700 | Matches `.app { max-width: 1180px }` in CSS with margin |
| Exit | `webview.start()` blocks; window close ends process | No orphan uvicorn on port 8765 from *this* process |

### 5.3 Instructions — run as desktop app (developer / power user)

1. Install **Python 3.12+** from [python.org](https://www.python.org/downloads/) — check **“Add python.exe to PATH”**.
2. Clone or copy the repo to e.g. `C:\Users\<you>\Zebra-Printer`.
3. Double-click **`run-app.bat`**.
   - First run: creates `.venv`, installs `requirements.txt`.
   - Kills any process listening on port **8765**.
   - Launches `pythonw desktop.py` (no black console window).
4. A window titled **GK420D Sticker Printer** opens with the full UI.
5. Close the window to stop the app.

### 5.4 Instructions — Desktop shortcut (one-time)

1. Double-click **`install-shortcut.bat`**.
2. Creates **GK420D Sticker Printer.lnk** on Desktop and in Startup folder.
3. Delete the Startup shortcut if you do not want auto-launch on sign-in.

### 5.5 Phase A improvements (recommended before Phase B)

These are small edits to `desktop.py` that improve the “real app” feel:

#### A.1 Hide console entirely

Already done via `pythonw.exe` in `run-app.bat`. Do **not** use `python.exe` for desktop mode unless debugging.

#### A.2 Single-instance mutex (recommended)

Prevent two windows fighting over port 8765:

```python
# desktop.py — add at top of main()
import ctypes
mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "GK420D-Sticker-Printer-SingleInstance")
if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    ctypes.windll.user32.MessageBoxW(0, "GK420D Sticker Printer is already running.", "Already open", 0x40)
    return
```

If another instance is running, focus its window instead of showing an error (advanced: find HWND by title).

#### A.3 Custom application icon

pywebview 5.x supports `icon=` on some platforms. On Windows, set icon via PyInstaller `--icon=assets/app.ico` in Phase B, or embed in shortcut `.lnk`.

#### A.4 Disable external navigation

If a link ever opens in the webview, trap `webview` navigation events (pywebview API) to keep user on localhost.

---

## 6. Phase B — Standalone executable (PyInstaller)

### 6.1 What gets built

`build.bat` produces an **onedir** bundle:

```
dist\GK420D Sticker Printer\
├── GK420D Sticker Printer.exe    ← double-click this
├── _internal\                    ← required; do not delete
│   ├── static\                   ← bundled UI
│   ├── app\                      ← Python packages
│   ├── python312.dll
│   └── ... (dependencies)
```

**Why onedir, not onefile?**

| Format | Pros | Cons |
| --- | --- | --- |
| **onedir** | Faster startup; easier to debug missing files; pypdfium2/Pillow DLLs behave better | Whole folder must ship together |
| **onefile** | Single exe aesthetic | Slow cold start; temp extract dir; more AV false positives |

**Recommendation:** Ship **onedir** inside an installer (Phase C).

### 6.2 Prerequisites

- Windows 10/11 x64
- Python 3.12+ (`py -3 --version`)
- Repo cloned locally
- Zebra printer installed in Windows (for post-build smoke test)

### 6.3 Build instructions (step-by-step)

1. Open **Command Prompt** or PowerShell in the repo root (or double-click `build.bat`).
2. Run:

   ```bat
   build.bat
   ```

3. Wait for pip install + PyInstaller (first build: 3–10 minutes depending on network).
4. Confirm output:

   ```bat
   dir "dist\GK420D Sticker Printer\GK420D Sticker Printer.exe"
   ```

5. Test:

   ```bat
   start-exe.bat
   ```

   Or double-click the exe directly.

6. Verify in the app:
   - Size defaults to **4" × 6"**
   - Drop a PDF → preview loads
   - **Calibrate media** sends ZPL (requires printer)
   - Build tag visible under title (from `/api/presets`)

### 6.4 What `build.bat` does (annotated)

```bat
py -3 -m venv .venv                                    # local build venv
pip install -r requirements.txt pyinstaller
pyinstaller ^
  --noconfirm --clean ^
  --windowed              # no console (GUI app)
  --onedir                # folder bundle
  --name "GK420D Sticker Printer" ^
  --add-data "static;static"   # CRITICAL: UI assets → _MEIPASS/static
  --hidden-import ...     # modules PyInstaller misses heuristically
  --collect-all webview   # WebView2 loader + platform files
  --collect-all uvicorn   # uvicorn submodules for ASGI server
  desktop.py              # entry point (not app.main)
```

**Entry point is `desktop.py`**, not `uvicorn app.main:app`, because the exe must start both server thread and webview window.

### 6.5 Hidden imports — why each exists

| Hidden import | Reason |
| --- | --- |
| `app.main`, `app.printer`, … | FastAPI app package tree |
| `win32print`, `win32api`, `pywintypes`, `pythoncom` | pywin32 RAW printing |
| `uvicorn.logging`, `uvicorn.loops.auto`, … | uvicorn dynamic imports |
| `multipart` | FastAPI file uploads |
| `--collect-all webview` | Edge WebView2 bridge DLLs |
| `--collect-all uvicorn` | Protocol and lifespan handlers |

If a frozen exe crashes on import, run once from CMD with a debug build (omit `--windowed`) to see the traceback.

### 6.6 Bundling `static/` — common failure

**Symptom:** Window opens but UI is blank / 404 on `/`.

**Cause:** `--add-data "static;static"` missing or wrong separator.

- Windows PyInstaller uses **`;`** between source and dest in `--add-data`.
- Linux/Mac use `:` — do not copy this batch file verbatim to other OS builds.

**Verify:** After build, check `dist\GK420D Sticker Printer\_internal\static\index.html` exists.

### 6.7 Bundling pypdfium2 (PDF support)

pypdfium2 ships native PDFium binaries. PyInstaller usually picks them up via Pillow/pypdfium2 hooks. If PDF drop fails in exe but works in dev:

```bat
--collect-all pypdfium2
```

Add to `build.bat` if PDF `/api/source` returns 500 only in frozen build.

### 6.8 Rebuild after code changes

```bat
build.bat
```

`--clean` wipes prior `dist/` and `build/`. No need to delete manually.

**Important:** GitHub release v1.0.0 may predate PDF/auto-crop/4×6 default. Always rebuild from current `main` before distributing exe.

### 6.9 Distribution of the raw folder

Zip the **entire** `dist\GK420D Sticker Printer\` folder:

```
GK420D-Sticker-Printer-win64.zip
└── GK420D Sticker Printer\
    ├── GK420D Sticker Printer.exe
    └── _internal\
```

Tell users: **extract fully; do not move exe out of folder.**

---

## 7. Phase C — Production Windows app polish

Phase C turns a portable folder into something users install once and find in Start menu.

### 7.1 Deliverables

| Item | Purpose |
| --- | --- |
| **Setup.exe** (Inno Setup or WiX) | Install to `%ProgramFiles%`, Start menu, uninstall entry |
| **Application icon** | `.ico` multi-size (16, 32, 48, 256) |
| **Version resource** | Properties → Details tab in Explorer |
| **WebView2 bootstrapper** | Install runtime if missing on Win10 |
| **Code signing** | Reduce SmartScreen warnings |
| **User data directory** | Logs and settings outside Program Files |

### 7.2 Recommended install location

```
C:\Program Files\GK420D Sticker Printer\     ← app binaries (read-only)
%LOCALAPPDATA%\GK420D Sticker Printer\       ← logs, optional settings
```

Do not write logs next to exe in Program Files (UAC / permissions).

### 7.3 Start menu and Desktop

Installer should create:

- Start → **GK420D Sticker Printer**
- Optional: Desktop shortcut (unchecked by default)
- **Do not** add to Startup unless user opts in (contrast with `install-shortcut.bat` dev helper)

### 7.4 WebView2 runtime handling

**Check on first launch:**

```python
# Optional preflight in desktop.py
import subprocess
# WebView2 Evergreen Bootstrapper: https://developer.microsoft.com/microsoft-edge/webview2/
```

**Installer option:** Run `MicrosoftEdgeWebview2Setup.exe /silent /install` as prerequisite.

**Detection:** pywebview will fail or show blank window if runtime missing — catch and show MessageBox with download link.

### 7.5 Elevated vs non-elevated

**Do not require admin** for normal operation. Printing via spooler works as standard user.

**Installer** requires admin once; app runs as user.

Exception: if targeting a shared machine printer mapping — still usually non-elevated.

---

## 8. PyInstaller reference spec

Replace the long command line in `build.bat` with a `.spec` file for maintainability. Example **`gk420d.spec`**:

```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

webview_datas, webview_hidden, _ = collect_all("webview")
uvicorn_datas, uvicorn_hidden, _ = collect_all("uvicorn")
pdf_datas, pdf_hidden, _ = collect_all("pypdfium2")

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[("static", "static")] + webview_datas + uvicorn_datas + pdf_datas,
    hiddenimports=[
        "app.main",
        "app.printer",
        "app.image_pipeline",
        "app.zpl",
        "app.calibration",
        "app.presets",
        "app.paths",
        "win32print",
        "win32api",
        "pywintypes",
        "pythoncom",
        "multipart",
    ] + webview_hidden + uvicorn_hidden + pdf_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GK420D Sticker Printer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets\\app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GK420D Sticker Printer",
)
```

**Build with spec:**

```bat
.venv\Scripts\pyinstaller.exe --noconfirm --clean gk420d.spec
```

Add `assets/app.ico` to repo (not yet present — create from 256×256 PNG).

---

## 9. Installer packaging (Inno Setup)

### 9.1 Why Inno Setup

- Free, widely used for Windows desktop apps
- Single `Setup.exe` output
- Uninstaller, Start menu, version checks, WebView2 prereq script

### 9.2 Example `installer.iss` skeleton

```iss
#define MyAppName "GK420D Sticker Printer"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "coitax"
#define MyAppExeName "GK420D Sticker Printer.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputBaseFilename=GK420D-Sticker-Printer-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "dist\GK420D Sticker Printer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
```

### 9.3 Build installer workflow

1. `build.bat` — fresh PyInstaller output
2. Compile `installer.iss` with Inno Setup Compiler
3. Ship `Output\GK420D-Sticker-Printer-Setup.exe`
4. Tag Git release with version + attach Setup.exe + zip fallback

---

## 10. Icons, manifest, and Windows integration

### 10.1 Application icon

1. Create **256×256** PNG (printer + label motif).
2. Convert to `.ico` with multiple embedded sizes (use [icoconvert.com](https://icoconvert.com/) or ImageMagick).
3. Save as `assets/app.ico`.
4. Reference in PyInstaller `--icon=assets/app.ico` and Inno `[Setup] SetupIconFile`.

### 10.2 Version resource (optional, advanced)

Use `pyinstaller-versionfile` or a `.rc` file so Explorer shows:

- File version: `1.1.0.0`
- Product name: GK420D Sticker Printer
- Company: your name

### 10.3 DPI awareness

The web UI uses CSS pixels. WebView2 handles HiDPI scaling. No extra manifest required for basic use.

If crop overlay misaligns on 150% display scaling, test at 100% and 125% Windows scale — fix in JS (`devicePixelRatio`), not PyInstaller.

---

## 11. Single-instance and lifecycle

### 11.1 Problem

| Scenario | Bad behavior |
| --- | --- |
| User double-clicks exe twice | Two windows; port conflict or shared server confusion |
| User closes window | Server thread must stop; port 8765 freed |
| User runs exe + `run.bat` | Two UIs, one server — acceptable if port reuse is intentional |

### 11.2 Required behavior

1. **Second launch** → focus existing window OR show “Already running”.
2. **Window close** → exit process; daemon uvicorn thread dies with process.
3. **Optional tray icon** → “Open” / “Quit” instead of closing on X (advanced).

### 11.3 Port 8765 policy

**Option A (current):** Fixed port 8765 — simple, matches docs.

**Option B (advanced):** Dynamic port + pass URL to webview:

```python
sock = socket.socket()
sock.bind((HOST, 0))
port = sock.getsockname()[1]
```

Update README if port becomes dynamic.

### 11.4 Graceful shutdown

Enhance `desktop.py`:

```python
def on_closed():
    # signal uvicorn server shutdown if you keep a reference
    pass

window = webview.create_window(..., on_top=False)
webview.start(func=on_closed)
```

For uvicorn graceful stop, store `server: uvicorn.Server` and call `server.should_exit = True` in a shutdown hook.

---

## 12. File associations and drag-to-app

### 12.1 Open PDF with app (optional)

Register ProgId in installer:

```
HKCU\Software\Classes\.pdf\OpenWithList\GK420D Sticker Printer.exe
```

Or **Open with** context menu via Inno `[Registry]` section.

**App change:** Accept CLI file path:

```python
# desktop.py
import sys
if len(sys.argv) > 1:
    initial_file = sys.argv[1]
    # pass to webview via query string or localStorage injection on load
```

Frontend: on load, if `?file=` param present, POST to `/api/source`.

### 12.2 Drag PDF onto exe icon

Windows passes dropped file path as `sys.argv[1]` when user drops file on running exe — same CLI handling.

### 12.3 Window-wide drop

Already implemented in `static/app.js` for browser/webview — no Windows-specific code needed.

---

## 13. Logging, crash reporting, and updates

### 13.1 Log file location

```python
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", ".")) / "GK420D Sticker Printer" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
```

Log:

- Server start/stop
- Print job printer name, preset, dimensions, copy count
- win32print errors
- Uncaught exceptions

Use Python `logging` with `RotatingFileHandler` (5 × 1 MB).

### 13.2 Frozen exe debug mode

Ship **`GK420D Sticker Printer (Debug).bat`** beside exe:

```bat
@echo off
cd /d "%~dp0"
"GK420D Sticker Printer.exe" --debug
```

Run PyInstaller debug build with `console=True` for support sessions.

### 13.3 Auto-update (optional, Phase D)

| Approach | Complexity | Notes |
| --- | --- | --- |
| **GitHub Releases + in-app check** | Medium | Compare `APP_BUILD` / semver from `/api/presets` vs GitHub API |
| **WinSparkle** | Medium | C++ updater; needs native wrapper |
| **Microsoft Store MSIX** | High | Store handles updates |

Minimal viable: README link + in-app “Check for updates” opening latest GitHub release URL.

---

## 14. Security model

| Topic | Design |
| --- | --- |
| **Network** | Server binds **`127.0.0.1` only** — not reachable from LAN |
| **Auth** | None — single-user local tool |
| **File access** | User-selected uploads only; no arbitrary path read API |
| **Print** | Sends RAW bytes to user-selected Windows queue |
| **WebView** | Load only `http://127.0.0.1:8765/*`; block external URLs |
| **Updates** | Sign Setup.exe to reduce tampering |

Do not bind `0.0.0.0` without authentication — would expose print API to local network.

---

## 15. Testing matrix

Run after every packaging change.

### 15.1 Functional tests

| # | Test | Dev (`run-app.bat`) | Frozen exe |
| --- | --- | --- | --- |
| 1 | Window opens < 10s | ☐ | ☐ |
| 2 | `/api/presets` default `4x6` | ☐ | ☐ |
| 3 | Drop PNG → preview | ☐ | ☐ |
| 4 | Drop PDF → auto-crop | ☐ | ☐ |
| 5 | Multi-page PDF page picker | ☐ | ☐ |
| 6 | Calibrate media → printer feeds | ☐ | ☐ |
| 7 | Print 1 copy 4×6 shipping label | ☐ | ☐ |
| 8 | Print 3 copies (paced batch) | ☐ | ☐ |
| 9 | Download ZPL contains `^LL1218` for 4×6 | ☐ | ☐ |
| 10 | Close window → port 8765 free | ☐ | ☐ |

### 15.2 Environment matrix

| OS | Display scale | WebView2 | Printer |
| --- | --- | --- | --- |
| Windows 10 22H2 | 100% | Standalone runtime | GK420D USB |
| Windows 11 | 125% | Built-in | GX420d USB |
| Clean VM | 100% | Fresh WebView2 install | Optional |

### 15.3 Regression triggers

Rebuild and retest when changing:

- `requirements.txt` (especially pywebview, pypdfium2, pywin32)
- `static/*` (UI)
- `app/image_pipeline.py` (PDF/crop)
- PyInstaller version
- `--add-data` or `.spec` datas

---

## 16. Troubleshooting frozen builds

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Blank white window | Server not ready / WebView2 missing | Increase `_wait_for_server` timeout; install WebView2 |
| 404 / no CSS | `static/` not bundled | Fix `--add-data "static;static"` |
| Import error on start | Missing hidden import | Add to spec; `--collect-all <pkg>` |
| PDF fails in exe only | pypdfium2 DLL not collected | `--collect-all pypdfium2` |
| Print works in dev, fails in exe | pywin32 not bundled | Ensure hidden imports; run exe as same user |
| “Port already in use” | Stale `run.bat` console | Kill PID on 8765 (see `run.bat`) |
| SmartScreen blocks exe | Unsigned binary | Code sign or SmartScreen reputation over time |
| Huge `_internal` folder | Normal | Expect 150–300 MB with WebView2 + Python + PDFium |

**Debug command:**

```bat
cd "dist\GK420D Sticker Printer\_internal"
..\..\..\.venv\Scripts\python.exe -c "import app.main; print(app.main.STATIC)"
```

---

## 17. Alternative stacks (when not to use pywebview)

| Stack | When to choose | Cost |
| --- | --- | --- |
| **pywebview (current)** | Keep Python backend + web UI; fastest path | Low |
| **Electron** | Team knows JS; need Chromium features | High bundle size (~150 MB+); rewrite print in Node or keep Python sidecar |
| **Tauri + sidecar** | Rust shell; small binary; Python sidecar for print | Medium — still two processes |
| **WinUI 3 / WPF** | Microsoft-only shop; no web UI | Full UI rewrite |
| **CEF Python** | Need full Chromium control | Heavier than pywebview |

**Stay with pywebview** unless you eliminate Python entirely.

---

## 18. Checklist: ship a Windows app

### Developer — first-time setup

- [ ] Python 3.12+ installed
- [ ] Repo cloned; `run-app.bat` works
- [ ] Zebra queue installed in Windows
- [ ] Calibrate media tested on 4×6 stock

### Build standalone exe

- [ ] Run `build.bat` without errors
- [ ] `dist\GK420D Sticker Printer\GK420D Sticker Printer.exe` launches
- [ ] PDF drop + print tested on frozen build
- [ ] Entire folder zipped for portable distribution

### Production installer

- [ ] `assets/app.ico` created
- [ ] `gk420d.spec` checked into repo (optional but recommended)
- [ ] Inno Setup script builds `Setup.exe`
- [ ] WebView2 prerequisite handled
- [ ] Start menu shortcut works
- [ ] Uninstall removes files cleanly
- [ ] Code signed (optional)

### Documentation shipped to users

- [ ] README covers **Calibrate media** when changing label sizes
- [ ] BUILD.md points to this spec for maintainers
- [ ] Release notes list exe vs browser mode

### Release

- [ ] Git tag `v1.x.x`
- [ ] GitHub Release attaches `Setup.exe` + portable zip
- [ ] Version bumped in `APP_BUILD` or semver field

---

## Appendix A — File map (Windows-relevant)

| File | Role |
| --- | --- |
| `desktop.py` | Windows app entry: uvicorn thread + pywebview window |
| `run.bat` | Web mode: venv, browser launch |
| `run-app.bat` | Desktop dev mode: `pythonw desktop.py` |
| `web.bat` | Alias for `run.bat` |
| `build.bat` | PyInstaller production build |
| `start-exe.bat` | Launch built exe |
| `install-shortcut.bat` | Desktop + Startup → `run-app.bat` |
| `install-web-shortcut.bat` | Desktop → `run.bat` |
| `app/paths.py` | Frozen vs dev resource paths |
| `app/main.py` | FastAPI app + static mount |
| `static/*` | Entire UI (bundled unchanged) |
| `docs/BUILD.md` | Short build quick reference |
| `docs/WINDOWS_APP_SPEC.md` | This document |

---

## Appendix B — Minimal “convert web app to Windows app” prompt

Use this one-paragraph instruction when delegating to an coding agent:

> Wrap the existing FastAPI sticker printer (`app/main.py`, `static/`) as a Windows desktop app using **pywebview** and **PyInstaller onedir**. Entry point: `desktop.py` starts uvicorn on `127.0.0.1:8765` in a daemon thread, waits for the port, opens a 1220×900 webview window, exits on close. Bundle `static/` via `--add-data "static;static"`. Resolve assets with `app/paths.resource_root()` for frozen mode. Include hidden imports for pywin32, uvicorn, multipart, and `--collect-all webview`. Provide `build.bat`, optional `.spec`, Inno Setup installer, app icon, single-instance mutex, and `%LOCALAPPDATA%` logging. Do not bind `0.0.0.0`. Test PDF drop, 4×6 calibrate, and RAW print in the frozen exe.

---

## Appendix C — Relationship to other docs

| Document | Purpose |
| --- | --- |
| [README.md](../README.md) | End-user how-to (calibration, printing) |
| [SPEC.md](SPEC.md) | Full application technical specification |
| [BUILD.md](BUILD.md) | Short PyInstaller quick start |
| [RECREATE_PROMPT.md](RECREATE_PROMPT.md) | Rebuild entire project from scratch |
| **WINDOWS_APP_SPEC.md** (this file) | Web → Windows desktop conversion in detail |
