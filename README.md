# GK420D Sticker Printer

Windows app that turns an image into a crisp **203 DPI** black-and-white sticker and sends raw ZPL to a Zebra **GK420D** or **GX420d** over USB.

The printer can only burn a black dot or leave the paper white. This project does the conversion on the PC — exact label pixels, one dither pass, then RAW ZPL — so the Windows driver does not resize or dither again.

Two ways to run it:

- **Web version** — local FastAPI server in your browser
- **Standalone Windows app** — double-click an `.exe` (download a release or build it)

Default label size is **4" × 4"** (812 × 812 dots). Other sizes stay in the UI.

## What you need

- Windows 10 or 11
- A Zebra GK420D or GX420d already installed in Windows (ZDesigner queue)
- **Direct-thermal** sticker stock (no ribbon). This printer is not thermal-transfer.
- For the web version only: Python 3.12+

## Web version

From this folder:

```bat
run.bat
```

Leave the console open and go to http://127.0.0.1:8765. Closing the console stops the server.

`run-app.bat` opens the same UI in a desktop window, still using the local Python venv.

`install-shortcut.bat` puts a Desktop shortcut and a Startup-folder shortcut for `run-app.bat`.

## Standalone Windows app

Download the latest **Windows** zip from [Releases](https://github.com/coitax/Zebra-Printer/releases). Unzip it and run:

```
GK420D Sticker Printer\GK420D Sticker Printer.exe
```

Keep the `_internal` folder next to the exe. Copy the whole directory if you move it.

To build the exe yourself, see [docs/BUILD.md](docs/BUILD.md). Short version:

```bat
build.bat
```

That writes `dist\GK420D Sticker Printer\GK420D Sticker Printer.exe`. After a local build, `start-exe.bat` launches it.

## First print (4×4 stock)

If a test print lands across two labels, the gap sensor is not synced. Do this once after loading a roll:

1. Load **direct-thermal** 4×4 stock. Guides should just touch the liner.
2. Pull the liner so a **gap** sits under the printhead, then close the lid.
3. In the app, click **Calibrate media**. The printer will feed a few labels.
4. Press **FEED** once. It should advance exactly one label.
5. Click **Print one-label test**. The black box must stay on a single sticker.

Full steps: [docs/PRINTER_SETUP.md](docs/PRINTER_SETUP.md).

## Make images that survive 203 DPI

Generate art at **2×** the print size, then let the app downscale. For the default 4×4 label that is **1624 × 1624**.

Ask your generator for high-contrast black-and-white sticker art: bold shapes, thick outlines, no tiny text, no fine hair or watercolor. Export **PNG**. Do not pre-dither — the app does one controlled 1-bit pass (Floyd–Steinberg, Atkinson, or threshold).

Full recipe: [docs/AI_IMAGE_GUIDE.md](docs/AI_IMAGE_GUIDE.md).

## How a job is sent

```
AI / file  →  resize to 203 DPI  →  1-bit convert  →  ZPL ^GF  →  Windows RAW USB  →  printer
```

Each job forces gap sensing (`^MNY`), a single-label length (`^LL`), and a max search shorter than two labels so the printer cannot treat two 4×4 stickers as one 8" form.

## Docs

| Doc | What it covers |
| --- | --- |
| [docs/BUILD.md](docs/BUILD.md) | Build the standalone exe with PyInstaller |
| [docs/PRINTER_SETUP.md](docs/PRINTER_SETUP.md) | Load stock, calibrate media, one-label test |
| [docs/AI_IMAGE_GUIDE.md](docs/AI_IMAGE_GUIDE.md) | Pixel sizes, prompts, and what fails on thermal |

## License

Use and modify for your own printer.
