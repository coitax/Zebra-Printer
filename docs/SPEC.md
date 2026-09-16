# GK420D Sticker Printer — Technical Specification

## Overview

Local-first Windows sticker printer for Zebra GK420D / GX420d direct-thermal label printers. Accepts images and PDFs, converts to exact 203 DPI 1-bit bitmaps, encodes ZPL `^GFA` graphics, and sends RAW jobs via `win32print` — bypassing driver scaling and dithering.

**Build tag:** exposed as `APP_BUILD` in API (`4x6-adaptive-crop` at time of writing).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser UI (static/index.html, app.js, styles.css)       │
│  Drop PDF/image · crop · presets · preview · print        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP (127.0.0.1:8765)
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI (app/main.py)                                      │
│  /api/source · /api/preview · /api/print · /api/zpl · …     │
└──────┬─────────────────┬──────────────────┬─────────────────┘
       │                 │                  │
┌──────▼──────┐  ┌───────▼────────┐  ┌─────▼─────┐
│ image_      │  │ zpl.py         │  │ printer.py│
│ pipeline.py │  │ ZPL encode     │  │ win32print│
│ PIL + PDF   │  │ ^GFA, ~DGR     │  │ RAW send  │
└─────────────┘  └────────────────┘  └───────────┘
```

### Run modes

| Mode | Entry | Server | UI |
| --- | --- | --- | --- |
| Web | `run.bat` | uvicorn on `:8765` | System browser |
| Desktop window | `run-app.bat` / `desktop.py` | uvicorn in background thread | pywebview window |
| Standalone exe | PyInstaller onedir build | Same as desktop | Bundled webview + static |

`run.bat` creates `.venv`, installs deps, kills stale `:8765` listeners, opens browser after 2s delay.

`desktop.py` reuses an existing server if port 8765 is already open.

`app/paths.py` resolves `static/` from repo root or PyInstaller `_MEIPASS`.

## Hardware constraints

| Parameter | Value |
| --- | --- |
| Supported printers | Zebra GK420D, GX420d (203 DPI G-series) |
| Resolution | 203 dots/inch (0.125 mm/dot) |
| Max print width | 4.09 in / **830 dots** |
| Max print length | 39 in / **7917 dots** |
| Media | Direct-thermal only (no ribbon) |
| Media sensing | Gap/notch (`^MNY`) |
| Connection | USB via Windows spooler (RAW datatype) |

Dot conversion: `dots = round(inches × 203)`, clamped to max width/height.

## Label presets

Defined in `app/presets.py`:

| ID | Inches | Dots (203 DPI) |
| --- | --- | --- |
| `2x2` | 2.0 × 2.0 | 406 × 406 |
| `3x2` | 3.0 × 2.0 | 609 × 406 |
| `4x3` | 4.0 × 3.0 | 812 × 609 |
| `4x4` | 4.0 × 4.0 | 812 × 812 |
| `4x6` | 4.0 × 6.0 | 812 × 1218 |
| `full3` | 4.09 × 3.0 | 830 × 609 |
| `custom` | user inches | computed |

**Default preset:** `4x6` (`DEFAULT_PRESET`).

`resolve_size(preset, width_in, height_in)` returns inches, dots, and preset id. Custom minimum 0.25 in per dimension.

## API endpoints

Base URL: `http://127.0.0.1:8765`

### Static

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Serves `static/index.html` |
| GET | `/static/*` | CSS, JS assets |

### JSON / form endpoints

All POST endpoints accept `multipart/form-data` unless noted.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/presets` | `{ presets[], default, build }` |
| GET | `/api/printers` | Windows printer list + recommended default |
| POST | `/api/printers/probe` | `printer_name` → identity / online status |
| POST | `/api/source` | Load file, detect crop, return source PNG + metadata |
| POST | `/api/preview` | Process file → grayscale + 1-bit PNG previews |
| POST | `/api/zpl` | Process file → downloadable ZPL text |
| POST | `/api/print` | Process file → paced RAW print to printer |
| POST | `/api/calibrate` | Print one-label test pattern |
| POST | `/api/media-calibrate` | Send gap calibration sequence |

### Common form fields

| Field | Default | Notes |
| --- | --- | --- |
| `preset` | `4x6` | Preset id or `custom` |
| `width_in`, `height_in` | — | Required for custom |
| `fit` | `cover` | `contain`, `cover`, `stretch` |
| `dither` | `floyd` | `floyd`, `atkinson`, `threshold` |
| `contrast` | `1.2` | 0.2–4.0 |
| `threshold` | `128` | Used when dither=threshold |
| `sharpen` | `true` | UnsharpMask before dither |
| `crop` | `0,0,1,1` | Normalized left,top,right,bottom |
| `page` | `1` | PDF page index |
| `darkness` | `18` | ZPL `^MD` (-30..30) |
| `speed` | `2` | ZPL `^PR` ips (2..5) |
| `copies` | `1` | 1..99 (paced batch for >1) |
| `printer_name` | — | Windows queue name |

### Preview response extras

```json
{
  "preset": "4x6",
  "width_in": 4.0,
  "height_in": 6.0,
  "width_dots": 812,
  "height_dots": 1218,
  "bitmap_width": 812,
  "bitmap_height": 1218,
  "fits_one_label": true,
  "ink_fill_ratio": 0.96,
  "low_ink_fill": false,
  "original_png": "<base64>",
  "print_png": "<base64>"
}
```

`low_ink_fill` is true when fewer than 85% of label rows contain ink (letterboxing warning).

### Source response

```json
{
  "pages": 1,
  "page": 1,
  "width": 2550,
  "height": 3300,
  "png": "<base64 full page render>",
  "crop": [0.12, 0.08, 0.88, 0.72],
  "suggested_preset": "4x6",
  "label_like": true
}
```

## Image pipeline

Implementation: `app/image_pipeline.py`

### Stages (in order)

1. **Load**
   - PDF: `pypdfium2` render at 406 DPI (2× print), capped at 4500 px longest edge
   - Raster: Pillow open, flatten alpha → white background

2. **Crop** (`apply_crop`)
   - Normalized rect clamped to image bounds, minimum 2% width/height

3. **Auto-detect** (`label_crop_for_image`)
   - `detect_content_crop`: threshold non-white pixels (L < 240), bounding box + padding
   - If ink covers ≥88% of page, use full frame
   - `suggest_label_preset`: 4:6 aspect or shipping filename tokens → `4x6`
   - `expand_crop_to_aspect`: expand to portrait 4:6 or landscape 6:4 based on ink box orientation

4. **Rotation** (`_maybe_rotate_for_label`)
   - If target label is portrait and source is landscape, rotate 90° CW

5. **Grayscale + contrast** (optional UnsharpMask sharpen)

6. **Fit to label** (`_fit_to_label`)
   - `cover`: scale to fill, center crop
   - `contain`: scale to fit, white letterbox
   - `stretch`: independent axis scale

7. **1-bit conversion**
   - `floyd`: Pillow Floyd–Steinberg
   - `atkinson`: custom error diffusion
   - `threshold`: hard cutoff

Output: `(grayscale_preview, mode_1_print_image)` both exactly `width_dots × height_dots`.

## ZPL format

Implementation: `app/zpl.py`

### Label setup (`label_setup`)

Every job starts with:

```
^XA
^MTd          ; direct thermal
^MNY          ; gap/notch sensing
^MMT          ; tear-off mode
^PON          ; print orientation normal
^LH0,0        ; label home
^LT0          ; top offset
^LS0          ; left offset
^PW{width}    ; print width dots
^LL{height}   ; label length dots
^ML{max_len}  ; max label search (height + margin, ≤ 1.2× height, never 2 labels)
```

`max_label_length_dots(h) = min(7917, max(h + 60, int(h × 1.2)))`

### Graphic field

```
^PR{speed}
^MD{darkness}
^FO0,0^GFA,{total_bytes},{total_bytes},{bytes_per_row},{HEX}^FS
^XZ
```

Bitmap packing: MSB-first per row, bit set = black (print). Pillow mode `1`: 0 = black.

### Media calibration (`media_calibrate_zpl`)

```
{label_setup}^JUS^XZ~JC
```

Sets gap mode and label dimensions, saves (`^JUS`), runs factory media calibrate (`~JC`).

### Batch printing (`graphic_batch_jobs`)

For copies > 1:

1. `~DGR:STICK.GRF,...` — download graphic to printer RAM
2. Per copy: `{label_setup}^FO0,0^XGR:STICK.GRF,1,1^FS^XZ`
3. Cleanup: `^XA^IDR:STICK.GRF^FS^XZ`

Paced by `_print_paced` in `main.py`: wait for idle between jobs, 2.5 s cooldown, offline check with PSU guidance.

## Printer integration

Implementation: `app/printer.py`

- **List:** `EnumPrinters` local + connections, sort Zebra-likely first
- **Detect Zebra:** name/driver contains zebra, zdesigner, gk420, gx420, etc.
- **Probe:** TCP :9100 `~HI`, spooler RAW query, port file read; returns model/firmware if bidirectional
- **Send:** `OpenPrinter` → `StartDocPrinter(..., "RAW")` → `WritePrinter`
- **Wait:** `wait_until_idle` polls job count and status flags until clear or timeout (45 s)

Requires `pywin32` on Windows. Returns HTTP 501 if unavailable.

## Calibration image

`app/calibration.py` generates a 1-bit test pattern: border, corner ticks, stroke samples, checkerboard, dimension text. Used by `/api/calibrate`.

## Frontend behavior

`static/app.js` state machine:

- Document-level drag/drop (not just dropzone)
- On file set → `POST /api/source` → crop canvas + suggestions
- Label-like PDFs: preset → 4×6, threshold dither, contrast 1.0, no sharpen; fit cover if crop aspect matches else contain
- Interactive crop canvas with aspect lock to selected preset
- Debounced preview (250 ms) → `POST /api/preview`
- Ink fill warning when `low_ink_fill`
- Build tag from `/api/presets`

## File map

```
/workspace
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI routes, paced print orchestration
│   ├── image_pipeline.py # Load, crop, PDF, dither, fit
│   ├── zpl.py            # ZPL encoding, batch graphics
│   ├── printer.py        # Windows spooler RAW I/O
│   ├── presets.py        # Label sizes, DPI constants
│   ├── calibration.py    # One-label test pattern
│   └── paths.py            # Resource root (dev vs frozen)
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── desktop.py              # pywebview launcher
├── run.bat                 # venv + uvicorn + browser
├── run-app.bat             # desktop window
├── web.bat                 # browser-only shortcut
├── install-web-shortcut.bat
├── build.bat               # PyInstaller onedir
├── start-exe.bat
├── requirements.txt
├── tests/
│   ├── test_presets.py
│   ├── test_api_presets.py
│   └── test_image_pipeline.py
└── docs/
```

## Dependencies

| Package | Purpose |
| --- | --- |
| fastapi | HTTP API |
| uvicorn | ASGI server |
| python-multipart | File upload parsing |
| pillow | Image processing |
| pypdfium2 | PDF rendering |
| pywebview | Desktop window (optional) |
| pywin32 | Windows printer API (Windows only) |

Build adds: pyinstaller

## Known limitations

1. **Windows only** — printing requires win32print; image preview works cross-platform but print endpoints return 501 elsewhere.
2. **No gray or color** — output is strictly 1-bit thermal.
3. **Driver must pass RAW unchanged** — ZDesigner queue required; generic/text drivers will corrupt ZPL.
4. **Media calibration is manual** — user must run Calibrate media when changing stock size; app sends correct `^LL` but printer gap sensor must match.
5. **Batch copies limited by PSU** — G-series power brick can fold under rapid full-label burns; paced printing mitigates but cannot fix undervoltage.
6. **PDF rendering quality** — complex vector PDFs rasterized at 406 DPI; very large pages scaled down to 4500 px cap.
7. **Auto-crop heuristics** — tuned for shipping labels on letter paper; unusual layouts may need manual crop.
8. **Landscape content on portrait stock** — auto-rotates wide ink boxes 90°; extreme aspect mismatches may still letterbox with Contain fit.
9. **Single graphic per batch job** — batch reuses downloaded `STICK.GRF`; different images require separate print calls.
10. **ZPL download ignores paced batch** — `/api/zpl` emits single-label ZPL without `^PQ`; copies param accepted but not emitted in single-job path.
11. **Localhost binding** — server listens on 127.0.0.1 only (not LAN-accessible by default).
12. **No print queue UI** — relies on Windows spooler; no job cancellation from app.

## Testing

```bat
.venv\Scripts\python.exe -m pytest tests/
```

Covers preset resolution, API default preset, image pipeline crop/aspect/rotation.
