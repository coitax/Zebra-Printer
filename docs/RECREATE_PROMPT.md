# Recreate prompt

Copy everything inside the fenced block below and paste it to an AI coding agent to rebuild this application from scratch.

---

```
Build a Windows-focused "GK420D Sticker Printer" — a local web app that converts PDFs and images into exact 203 DPI 1-bit bitmaps and sends raw ZPL to a Zebra GK420D or GX420d direct-thermal label printer over USB via the Windows spooler.

## Goal

The Zebra GK420D/GX420d can only print black dots or white paper at 203 DPI. Windows printer drivers resize and dither jobs, destroying sticker quality. This app must do ALL conversion on the PC (resize, crop, dither to 1-bit) and send RAW ZPL so the driver passes bytes unchanged.

Primary use cases:
1. Print AI-generated sticker art on 4×4 or 4×6 direct-thermal labels
2. Print 4×6 shipping label PDFs (USPS/UPS/FedEx) dropped onto letter-size pages — auto-detect and crop the label area
3. Calibrate printer gap sensor when switching label stock sizes

## Tech stack

- Python 3.12+
- FastAPI + uvicorn (local server on 127.0.0.1:8765)
- Pillow for image processing
- pypdfium2 for PDF page rendering
- pywin32 (win32print) for RAW Windows printing — Windows only
- pywebview for optional desktop window mode
- Vanilla HTML/CSS/JS frontend (no React) served from /static
- PyInstaller onedir build for standalone .exe (optional)

Dependencies (requirements.txt):
  fastapi>=0.115.0
  uvicorn[standard]>=0.32.0
  python-multipart>=0.0.12
  pillow>=10.4.0
  pypdfium2>=4.30.0
  pywebview>=5.3
  pywin32>=308; sys_platform == "win32"

## Project structure

```
app/
  __init__.py
  main.py           # FastAPI app, all routes
  image_pipeline.py # load, PDF, crop detect, fit, dither
  zpl.py            # ZPL ^GFA encoding, media calibrate, batch graphics
  printer.py        # list/probe/send RAW via win32print
  presets.py        # label size presets, DPI=203
  calibration.py    # one-label test pattern generator
  paths.py          # resource root (dev vs PyInstaller frozen)
static/
  index.html
  app.js
  styles.css
desktop.py          # pywebview + background uvicorn
run.bat             # venv, pip install, kill stale :8765, open browser, uvicorn
run-app.bat         # launch desktop.py
build.bat           # PyInstaller onedir "GK420D Sticker Printer"
```

## Hardware constants

- DPI = 203
- MAX_WIDTH_DOTS = 830  (4.09 inches)
- MAX_HEIGHT_DOTS = 7917 (39 inches)
- dots = round(inches × 203), clamped to max
- Direct thermal only (^MTd), gap sensing (^MNY), tear-off (^MMT)
- Supported printers: Zebra GK420D, GX420d via ZDesigner Windows queue

## Label presets (app/presets.py)

| id    | inches    | dots      |
|-------|-----------|-----------|
| 2x2   | 2.0 × 2.0 | 406 × 406 |
| 3x2   | 3.0 × 2.0 | 609 × 406 |
| 4x3   | 4.0 × 3.0 | 812 × 609 |
| 4x4   | 4.0 × 4.0 | 812 × 812 |
| 4x6   | 4.0 × 6.0 | 812 × 1218 |
| full3 | 4.09 × 3.0| 830 × 609 |

DEFAULT_PRESET = "4x6" (shipping labels are the primary workflow).

resolve_size(preset, width_in, height_in) → (width_in, height_in, width_dots, height_dots, preset_id)
Custom sizes: min 0.25 inches per dimension.

## FastAPI endpoints (app/main.py)

GET  /                     → static/index.html
GET  /api/presets          → { presets: [...], default: "4x6", build: "4x6-adaptive-crop" }
GET  /api/printers         → { printers: [...], default: recommended_name, zebra_found: bool }
POST /api/printers/probe   → form: printer_name → probe result (identity, online, hints)
POST /api/source           → form: file, page=1 → source PNG + detected crop + suggested preset
POST /api/preview          → form: file + all settings → grayscale PNG + 1-bit PNG + ink_fill_ratio
POST /api/zpl              → form: file + settings → downloadable sticker.zpl
POST /api/print            → form: file + settings + printer_name → paced RAW print
POST /api/calibrate        → form: printer_name + preset → print one-label test pattern
POST /api/media-calibrate  → form: printer_name + preset → gap calibration ZPL

Common form fields:
- preset (default 4x6), width_in, height_in (for custom)
- fit: cover | contain | stretch (default cover)
- dither: floyd | atkinson | threshold (default floyd)
- contrast (default 1.2), threshold (default 128), sharpen (default true)
- crop: "left,top,right,bottom" normalized 0-1 (default "0,0,1,1")
- page: PDF page number (default 1)
- darkness (default 18, ZPL ^MD -30..30), speed (default 2 ips, ^PR 2..5)
- copies (1..99)

Preview response must include:
- fits_one_label: bitmap dimensions == label dots
- ink_fill_ratio: fraction of label rows containing any ink
- low_ink_fill: true if ink_fill_ratio < 0.85 (warn user about letterboxing)

## Image pipeline (app/image_pipeline.py)

ProcessSettings dataclass: width_dots, height_dots, fit, dither, contrast, threshold, sharpen, crop tuple.

### Load
- Detect PDF by magic bytes %PDF- or .pdf extension
- PDF: render with pypdfium2 at 406 DPI (2× print resolution), cap longest edge at 4500px
- Raster: Pillow open, flatten RGBA/LA/P+transparency onto white RGB background

### Auto-crop for shipping labels
detect_content_crop(image):
  - Grayscale, downscale if >900px for speed
  - Mask pixels where L < 240
  - Bounding box + small padding
  - If ink area ≥ 88% of page, return full frame (0,0,1,1)
  - Return normalized crop (left, top, right, bottom)

suggest_label_preset(image, crop, filename):
  - If aspect ≈ 4:6 or 6:4 (tolerance) OR filename contains shipping/shipment/postage/usps/ups/fedex/chit/label
  - Return "4x6"

label_crop_for_image:
  - Run detect_content_crop
  - If shipping label: expand_crop_to_aspect using _shipping_target_aspect
    - Pick portrait 4:6 (0.667) or landscape 6:4 (1.5) based on detected ink box orientation
  - Return { crop, suggested_preset, label_like }

expand_crop_to_aspect: center-expand crop box to target aspect ratio, clamped to image bounds.

### Processing order (process_image)
1. apply_crop(source, settings.crop)
2. _maybe_rotate_for_label: if label is portrait (width_dots < height_dots) and source is landscape (w > h), rotate 90° CW
3. Grayscale
4. Apply contrast (clamp 0.2..4.0, pivot at 128)
5. Optional UnsharpMask (radius=1.2, percent=140, threshold=2)
6. _fit_to_label:
   - cover: scale max(w,h ratio), center crop to exact dots
   - contain: scale min ratio, paste centered on white canvas
   - stretch: independent axis resize
7. _to_one_bit:
   - floyd: Pillow FLOYDSTEINBERG
   - atkinson: custom 6-neighbor error diffusion (/8 per step)
   - threshold: point lambda at cutoff

Return (grayscale_preview, mode_1_print_image) both exactly width_dots × height_dots.

## ZPL encoding (app/zpl.py)

label_setup(width_dots, height_dots):
```
^XA
^MTd
^MNY
^MMT
^PON
^LH0,0
^LT0
^LS0
^PW{width}
^LL{height}
^ML{max_label_length}
```
max_label_length = min(7917, max(height + 60, int(height × 1.2))) — never search two labels.

image_to_zpl(1-bit image):
  - Pad/crop bitmap to label dimensions on white canvas if needed
  - pack_bitmap: MSB-first, bit set = black (Pillow mode 1: 0 = black)
  - Emit: label_setup + ^PR{speed} + ^MD{darkness} + ^FO0,0^GFA,{total},{total},{bytes_per_row},{HEX}^FS + ^XZ

media_calibrate_zpl(width, height):
  label_setup + ^JUS + ^XZ + ~JC
  (save settings, run printer media calibration — feeds several labels to learn gap)

graphic_batch_jobs(image) for copies > 1:
  1. ~DGR:STICK.GRF,{len},{bytes_per_row},{hex}  — download to RAM
  2. print_one: label_setup + ^FO0,0^XGR:STICK.GRF,1,1^FS + ^XZ
  3. cleanup: ^XA^IDR:STICK.GRF^FS^XZ

## Paced batch printing (app/main.py _print_paced)

When copies == 1: single image_to_zpl + send_raw.

When copies > 1:
  1. Send download job
  2. wait_until_idle(printer)
  3. For each copy: check printer still online (raise helpful error if PSU folded — mention 20V brick, wall outlet, darkness 12-15, 3 ips)
  4. Send print_one job
  5. wait_until_idle
  6. Sleep 2.5s cooldown between copies
  7. Finally send cleanup (delete STICK.GRF), ignore cleanup errors

This prevents G-series power supply collapse on rapid full-label burns.

## Printer module (app/printer.py)

- list_printers(): EnumPrinters, detect likely Zebra by name/driver hints (zebra, zdesigner, gk420, gx420, zpl, etc.)
- recommended_printer_name(): first online Zebra, else default Windows printer
- probe_printer(): try TCP :9100 ~HI, spooler RAW write+read, port file; return model/firmware/delivery status
- send_raw(printer_name, zpl_string, job_name): OpenPrinter → StartDocPrinter(..., "RAW") → WritePrinter
- wait_until_idle(printer_name, timeout=45): poll job count and busy flags
- inspect_printer(): online status, port, driver, jobs

Raise RuntimeError with install instructions if pywin32 missing.

## Calibration test pattern (app/calibration.py)

build_calibration_image(width_dots, height_dots):
  Draw 1-bit test label: outer border, inner border, corner ticks, "ONE LABEL" text with dimensions,
  horizontal/vertical stroke samples (1-4 dot widths), checkerboard patch.
  Text: "If this box crosses a gap, calibrate media."
  Use threshold dither.

## Frontend UI (static/)

Dark warm theme (CSS variables: bg #14110e, accent #e3a008).

Layout: 2-column grid — left: drop zone + controls; right: crop canvas + dual previews (grayscale + 1-bit zebra-striped background).

### Drop zone
- Accept: PDF, PNG, JPEG, WebP, GIF, TIFF
- Document-level drag/drop (not just the label element)
- Text: "Drop a shipping label PDF or image" / "4×6 labels on letter pages are auto-cropped"

### On file load
1. POST /api/source with file + page
2. Show source on crop canvas (640×480 max, scaled to fit)
3. Apply server suggestions:
   - Set preset to suggested_preset (usually 4x6)
   - If label_like: threshold dither, contrast 1.0, sharpen off
   - Fit: cover if crop aspect matches preset within tolerance, else contain
   - Apply detected crop; enable Auto-crop / Reset crop buttons
4. Show PDF page selector if pages > 1

### Interactive crop
- Normalized crop rect stored in state
- Canvas overlay: drag to move, drag edges/corners to resize
- "Lock to label shape" checkbox: maintain preset aspect ratio during resize
- Crop sent as crop form field on preview/print

### Controls
- Size preset dropdown populated from /api/presets (select API default, not hardcoded)
- Custom width/height inputs (defaults 4 × 6 inches)
- Fit, dither, contrast slider, threshold slider (visible only for threshold mode), sharpen checkbox
- Printer dropdown + Test connection + Refresh
- Probe pill states: idle, checking, talking, online, offline, err
- Darkness slider, speed dropdown (2-5 ips), copies (1-99)
- Buttons: Print sticker (primary), Download ZPL, Print one-label test, Calibrate media
- Status line with ok/err styling
- Build tag in header eyebrow from API

### Preview
- Debounced 250ms POST /api/preview on settings change
- Show meta: inches, dots, 203 DPI
- fit-badge: green if fits_one_label, red if mismatch
- Warn if low_ink_fill: "Content may not fill the label — try Cover fit or adjust crop"
- Zoom: Fit (scale to frame), 1×, 2× with pixelated rendering

### Hints (must appear in UI)
- Calibrate media when prints cross gaps; select size matching physical stock first
- Batch copies: one at a time with pause; PSU guidance for 3+ copies
- Shipping PDFs snap to 4×6

## run.bat behavior

1. cd to script directory
2. Create .venv with py -3 if missing
3. pip install -r requirements.txt (quiet)
4. Kill any process listening on port 8765 (netstat + taskkill)
5. start browser to http://127.0.0.1:8765 after 2s delay
6. uvicorn app.main:app --host 127.0.0.1 --port 8765 (blocking — console stays open)

## desktop.py

- If port 8765 not open: start uvicorn in daemon thread, wait up to 8s
- Try pywebview window (1220×900, min 900×700, title "GK420D Sticker Printer")
- Fallback: webbrowser.open + keep-alive loop

## paths.py

resource_root(): PyInstaller _MEIPASS if frozen, else parent of app/ package.

## Edge cases and lessons learned

1. **Calibrate media is mandatory when switching label sizes** (4×4 ↔ 4×6). Wrong gap sync causes prints spanning two labels or using wrong length — this is NOT fixed by code alone. User must: select matching preset → Calibrate media → FEED once → Print one-label test.

2. **Default preset must be 4×6** for shipping label workflow. Single source of truth: DEFAULT_PRESET in presets.py, used in all API Form() defaults and exposed via GET /api/presets default field; UI selects API default.

3. **PDF drop**: shipping labels on letter paper need content detection + aspect-aware crop expansion (portrait 4:6 vs landscape 6:4). Filename heuristics help (shipment, shipping, usps, etc.).

4. **Landscape label content on portrait 4×6 stock**: rotate source 90° before fit when source aspect is landscape and label preset is portrait.

5. **Contain vs Cover**: shipping labels with matching crop aspect use Cover; mismatched use Contain to preserve barcodes. Warn when ink_fill_ratio < 0.85.

6. **Paced batches**: never send ^PQ99 on a full bitmap — G-series PSU dies on copy 3+. Download graphic once (~DGR), recall per copy (^XGR), 2.5s cooldown, wait_until_idle between jobs.

7. **RAW printing only**: never use driver rendering. Job datatype must be "RAW". User must pick ZDesigner queue, not Print to PDF.

8. **ZPL label length**: ^LL must match preset dots. ^ML must search gap but never as far as two labels (prevents treating two 4×4 stickers as one 8" form).

9. **203 DPI exact pixels**: always output bitmap exactly width_dots × height_dots before ZPL encode. No driver-side scaling.

10. **Stale server port**: run.bat kills existing :8765 listeners before starting.

11. **Alpha/transparency**: flatten to white, not black.

12. **Pre-dithering**: app does one controlled dither pass; tell users not to pre-dither in generators.

13. **Generate art at 2× print size** (e.g. 1624×2436 for 4×6) for cleaner downscale.

## Tests (tests/)

- test_presets.py: resolve_size('4x6') → 812×1218, DEFAULT_PRESET is 4x6
- test_api_presets.py: GET /api/presets returns default field
- test_image_pipeline.py: crop detection, aspect expansion, rotation, fit output dimensions

## README (user-facing)

Write a README focused on end users (not developers):
- What the app does
- Quick start: double-click run.bat
- IMPORTANT section on Calibrate media when changing label sizes (step by step for 4×4 vs 4×6)
- PDF/image drop workflow
- Troubleshooting: stale port 8765, wrong preset, PSU/batch copies
- Brief mention of exe build at end

## Acceptance criteria

- Drop a 4×6 shipping PDF on letter paper → auto-crop → preview fills label → print on GK420D
- Switch from 4×6 to 4×4 stock → Calibrate media → one-label test stays on single sticker
- Print 5 copies → paced with pauses, printer stays online
- Preview 1-bit image matches what prints (pixel-perfect at 203 DPI)
- Download ZPL contains ^PW, ^LL matching preset, ^GFA hex bitmap
- Works on Windows 10/11 with ZDesigner GK420d queue installed
- run.bat opens browser and serves UI without manual steps

Build the complete working application with all files, bat scripts, and tests.
```

---

To use: copy the entire contents of the fenced block above (from "Build a Windows-focused…" through "…bat scripts, and tests.") and paste into your agent.
