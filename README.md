# GK420D Sticker Printer

Windows app that turns a **PDF or image** into a crisp **203 DPI** black-and-white sticker and sends raw ZPL to a Zebra **GK420D** or **GX420d** over USB.

The printer can only burn a black dot or leave the paper white. This app does the conversion on your PC — exact label pixels, one dither pass, then RAW ZPL — so the Windows driver does not resize or dither again.

Default label size is **4" × 6"** (812 × 1218 dots), suited for shipping labels and tall stickers. Other sizes are available in the Size dropdown.

## What you need

- Windows 10 or 11
- A Zebra GK420D or GX420d installed in Windows (ZDesigner queue)
- **Direct-thermal** sticker stock (no ribbon). This printer is not thermal-transfer.
- Python 3.12+ (installed automatically by `run.bat` on first launch)

## Quick start

1. Double-click **`run.bat`** in this folder.
2. On first run, the script creates a virtual environment and installs dependencies (takes a minute).
3. Your browser opens to **http://127.0.0.1:8765**.
4. Leave the console window open while you print. Closing it stops the server.

Alternatives:

- **`run-app.bat`** — same UI in a desktop window (uses Python + pywebview).
- **`web.bat`** — opens the browser if the server is already running.
- **`install-web-shortcut.bat`** — adds a Desktop shortcut to launch via `run.bat`.

For a standalone `.exe` (no Python required), see [docs/BUILD.md](docs/BUILD.md) or download a release.

## Print a sticker

1. **Drop a file** on the drop zone — PNG, JPEG, WebP, GIF, TIFF, or **PDF** (e.g. a shipping label on letter paper).
2. For multi-page PDFs, pick the **Page** number.
3. The app **auto-crops** shipping labels to the 4×6 area. Drag the crop box if you need to adjust it.
4. Confirm the **Size** preset matches your physical stock (default **4" × 6"**).
5. Choose **Fit**:
   - **Cover** — fills the entire label (best for photos and full-bleed art).
   - **Contain** — letterboxes inside the label (keeps barcodes intact on shipping labels).
   - **Stretch** — stretches to exact label dimensions.
6. Pick a **dither mode** (Floyd–Steinberg for photos, Atkinson for punchy stickers, Threshold for logos/text).
7. Select your **Zebra printer** and click **Test connection**.
8. Click **Print sticker**.

The preview panel shows the exact 1-bit bitmap the printhead will burn. Use **Fit / 1× / 2×** zoom to inspect dot detail.

## IMPORTANT: Calibrate media when changing label sizes

If a print lands **across two labels**, sits in the middle of a gap, or only uses part of a tall label, the gap sensor is not synced to your stock. **This is the most common cause of “wrong size” prints** — not a bug in the app.

You must recalibrate whenever you:

- Load a **new roll** of a different size (4×4 vs 4×6, etc.)
- Switch between square stickers and shipping labels
- Replace stock after a jam or long idle period

### Step-by-step calibration

1. **Load the correct stock** — direct-thermal labels with die-cut gaps (not continuous or black-mark media).
2. Open the lid. Pull the liner forward so a **gap** sits under the printhead. Close the lid firmly. Guides should just touch the liner.
3. In the app, set **Size** to match the roll you loaded:
   - 4×4 square stickers → **4" × 4"**
   - 4×6 shipping labels → **4" × 6"** (default)
4. Click **Calibrate media**. The printer feeds several labels while it learns the gap spacing.
5. When feeding stops, press the printer's **FEED** button **once**. It should advance **exactly one** label and stop at the tear bar.
6. Click **Print one-label test**. The black border box must stay on a **single** sticker — no line should cross a gap.
7. If FEED still skips two labels:
   - Wipe the gap sensor window under the printhead
   - Confirm stock is gap/die-cut (not continuous)
   - Repeat **Calibrate media**

Repeat this whole sequence every time you change label paper size.

More detail: [docs/PRINTER_SETUP.md](docs/PRINTER_SETUP.md).

## Shipping label PDFs

Drop a PDF from USPS, UPS, FedEx, or similar. The app:

- Renders the page at high resolution
- Detects the label ink area and auto-crops to 4×6
- Switches to **Threshold** dither and **Contain** fit when the crop matches the label shape (keeps barcodes readable)
- Uses **Cover** when the crop aspect already matches the preset

Use **Auto-crop label** to re-apply detection, or drag the crop box manually.

## Batch copies

Set **Copies** (1–99) before printing. The app prints **one label at a time** with a pause between jobs so the printer power supply can recover. For batches of 3 or more:

- Use the original **20V power brick** plugged directly into a wall outlet (not a USB hub or power strip)
- Lower **Darkness** to 12–15
- Use **3 ips** speed instead of 2 ips

If the printer goes offline mid-batch, let it cool, reduce darkness, and try again with fewer copies.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| Browser does not open / page won't load | Check the console window is still open. Another app may be using port **8765** — `run.bat` kills stale listeners on startup; restart `run.bat`. |
| Print spans two labels or wrong length | **Calibrate media** for the size preset you selected. See section above. |
| Print looks like a small square on a tall label | Size preset may not match stock (e.g. 4×4 preset on 4×6 paper). Select the correct size and recalibrate. |
| Preview shows low ink fill / white bands | Switch **Fit** from Contain to **Cover**, or adjust the crop box. |
| Printer offline / jobs stuck in queue | Power on, check USB, uncheck **Use Printer Offline** in Windows printer properties. |
| Printer dies on 3rd+ copy | PSU overload — wall outlet, darkness 12–15, 3 ips, fewer copies per batch. |
| No Zebra in printer list | Install the ZDesigner GK420d/GX420d driver. Do not use Microsoft Print to PDF. |
| Fuzzy or muddy output | Raise contrast, use 2 ips, try Threshold for line art. Generate art at 2× print size (see [docs/AI_IMAGE_GUIDE.md](docs/AI_IMAGE_GUIDE.md)). |

## Label size reference

| Preset | Print dots @ 203 DPI |
| --- | --- |
| 2" × 2" | 406 × 406 |
| 3" × 2" | 609 × 406 |
| 4" × 3" | 812 × 609 |
| 4" × 4" | 812 × 812 |
| **4" × 6"** (default) | **812 × 1218** |
| 4.09" × 3" (full width) | 830 × 609 |

## Other docs

| Doc | What it covers |
| --- | --- |
| [docs/SPEC.md](docs/SPEC.md) | Technical architecture, API, ZPL format |
| [docs/PRINTER_SETUP.md](docs/PRINTER_SETUP.md) | Physical load, calibration, driver notes |
| [docs/AI_IMAGE_GUIDE.md](docs/AI_IMAGE_GUIDE.md) | Pixel sizes, prompts, what survives 203 DPI |
| [docs/BUILD.md](docs/BUILD.md) | Build the standalone Windows exe |
| [docs/WINDOWS_APP_SPEC.md](docs/WINDOWS_APP_SPEC.md) | Full spec: web app → Windows desktop app (pywebview, PyInstaller, installer) |
| [docs/RECREATE_PROMPT.md](docs/RECREATE_PROMPT.md) | Prompt to rebuild this app from scratch |

## License

Use and modify for your own printer.
