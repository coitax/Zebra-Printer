from __future__ import annotations

import base64
import time
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.calibration import build_calibration_image
from app.image_pipeline import (
    ProcessSettings,
    image_to_png_bytes,
    is_pdf,
    label_crop_for_image,
    load_image,
    normalize_crop,
    pdf_page_count,
    process_image,
)
from app.presets import DEFAULT_PRESET, PRESETS, resolve_size
from app.printer import inspect_printer, list_printers, probe_printer, recommended_printer_name, send_raw, wait_until_idle
from app.paths import resource_root
from app.zpl import graphic_batch_jobs, image_to_zpl, media_calibrate_zpl

ROOT = resource_root()
STATIC = ROOT / "static"

app = FastAPI(title="GK420D Sticker Printer")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


APP_BUILD = "4x6-adaptive-crop"


@app.get("/api/presets")
def presets() -> dict:
    return {
        "presets": list(PRESETS.values()),
        "default": DEFAULT_PRESET,
        "build": APP_BUILD,
    }


@app.get("/api/printers")
def printers() -> dict:
    try:
        found = list_printers()
        recommended = recommended_printer_name(found)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    return {
        "printers": [
            {
                "name": item.name,
                "description": item.description,
                "port": item.port,
                "driver": item.driver,
                "jobs": item.jobs,
                "online": item.online,
                "status_text": item.status_text,
                "likely_zebra": item.likely_zebra,
            }
            for item in found
        ],
        "default": recommended,
        "zebra_found": any(item.likely_zebra for item in found),
    }


@app.post("/api/printers/probe")
def probe(printer_name: Annotated[str, Form()]) -> dict:
    if not printer_name.strip():
        raise HTTPException(status_code=400, detail="Choose a printer")
    try:
        return probe_printer(printer_name.strip()).as_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Probe failed: {exc}") from exc


@app.post("/api/source")
async def source_preview(
    file: Annotated[UploadFile, File()],
    page: Annotated[int, Form()] = 1,
) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    filename = file.filename or ""
    try:
        pages = pdf_page_count(data) if is_pdf(data, filename) else 1
        image = load_image(data, page=page, filename=filename)
        detected = label_crop_for_image(image, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc
    left, top, right, bottom = detected["crop"]
    return {
        "pages": pages,
        "page": max(1, min(pages, page)),
        "width": image.width,
        "height": image.height,
        "png": _png_b64(image),
        "crop": [left, top, right, bottom],
        "suggested_preset": detected["suggested_preset"],
        "label_like": detected["label_like"],
    }


@app.post("/api/preview")
async def preview(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    fit: Annotated[str, Form()] = "cover",
    dither: Annotated[str, Form()] = "floyd",
    contrast: Annotated[float, Form()] = 1.2,
    threshold: Annotated[int, Form()] = 128,
    sharpen: Annotated[str, Form()] = "true",
    crop: Annotated[str, Form()] = "0,0,1,1",
    page: Annotated[int, Form()] = 1,
) -> dict:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = await _read_image(file, page=page)
    gray, print_image = process_image(source, settings)
    return {
        **inches,
        **_fit_check(gray, settings),
        "original_png": _png_b64(gray),
        "print_png": _png_b64(print_image),
    }


@app.post("/api/zpl")
async def download_zpl(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    fit: Annotated[str, Form()] = "cover",
    dither: Annotated[str, Form()] = "floyd",
    contrast: Annotated[float, Form()] = 1.2,
    threshold: Annotated[int, Form()] = 128,
    sharpen: Annotated[str, Form()] = "true",
    darkness: Annotated[int, Form()] = 18,
    speed: Annotated[int, Form()] = 2,
    copies: Annotated[int, Form()] = 1,
    crop: Annotated[str, Form()] = "0,0,1,1",
    page: Annotated[int, Form()] = 1,
) -> PlainTextResponse:
    settings, _ = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = await _read_image(file, page=page)
    _, print_image = process_image(source, settings)
    zpl = image_to_zpl(
        print_image,
        darkness=darkness,
        speed=speed,
        copies=copies,
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    )
    return PlainTextResponse(
        zpl,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="sticker.zpl"'},
    )


@app.post("/api/print")
async def print_sticker(
    file: Annotated[UploadFile, File()],
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    fit: Annotated[str, Form()] = "cover",
    dither: Annotated[str, Form()] = "floyd",
    contrast: Annotated[float, Form()] = 1.2,
    threshold: Annotated[int, Form()] = 128,
    sharpen: Annotated[str, Form()] = "true",
    darkness: Annotated[int, Form()] = 18,
    speed: Annotated[int, Form()] = 2,
    copies: Annotated[int, Form()] = 1,
    crop: Annotated[str, Form()] = "0,0,1,1",
    page: Annotated[int, Form()] = 1,
) -> dict:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = await _read_image(file, page=page)
    _, print_image = process_image(source, settings)
    copies = max(1, min(99, int(copies)))
    _print_paced(
        printer_name,
        print_image,
        copies=copies,
        darkness=darkness,
        speed=speed,
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    )
    return {
        "ok": True,
        **inches,
        **_fit_check(print_image, settings),
        "copies": copies,
    }


@app.post("/api/calibrate")
async def print_calibration(
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    darkness: Annotated[int, Form()] = 18,
    speed: Annotated[int, Form()] = 2,
) -> dict:
    width_in, height_in, width_dots, height_dots, preset_id = resolve_size(
        preset, width_in, height_in
    )
    print_image = build_calibration_image(width_dots, height_dots)
    zpl = image_to_zpl(
        print_image,
        darkness=darkness,
        speed=speed,
        copies=1,
        label_width=width_dots,
        label_height=height_dots,
    )
    _send(printer_name, zpl, "GK420D Calibration")
    return {
        "ok": True,
        "preset": preset_id,
        "width_in": width_in,
        "height_in": height_in,
        "width_dots": width_dots,
        "height_dots": height_dots,
        "fits_one_label": print_image.size == (width_dots, height_dots),
    }


@app.post("/api/media-calibrate")
async def media_calibrate(
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
) -> dict:
    width_in, height_in, width_dots, height_dots, preset_id = resolve_size(
        preset, width_in, height_in
    )
    _send(printer_name, media_calibrate_zpl(width_dots, height_dots), "GK420D Media Calibrate")
    return {
        "ok": True,
        "preset": preset_id,
        "width_in": width_in,
        "height_in": height_in,
        "width_dots": width_dots,
        "height_dots": height_dots,
        "message": "Media calibration sent. The printer will feed a few labels to find the gap.",
    }


def _settings_from_form(
    preset: str,
    width_in: float | None,
    height_in: float | None,
    fit: str,
    dither: str,
    contrast: float,
    threshold: int,
    sharpen: str,
    crop: str = "0,0,1,1",
) -> tuple[ProcessSettings, dict]:
    if fit not in {"contain", "cover", "stretch"}:
        raise HTTPException(status_code=400, detail="fit must be contain, cover, or stretch")
    if dither not in {"floyd", "atkinson", "threshold"}:
        raise HTTPException(status_code=400, detail="dither must be floyd, atkinson, or threshold")

    width_in, height_in, width_dots, height_dots, preset_id = resolve_size(
        preset, width_in, height_in
    )
    settings = ProcessSettings(
        width_dots=width_dots,
        height_dots=height_dots,
        fit=fit,  # type: ignore[arg-type]
        dither=dither,  # type: ignore[arg-type]
        contrast=contrast,
        threshold=threshold,
        sharpen=_as_bool(sharpen),
        crop=_parse_crop(crop),
    )
    return settings, {
        "preset": preset_id,
        "width_in": width_in,
        "height_in": height_in,
        "width_dots": width_dots,
        "height_dots": height_dots,
    }


def _fit_check(preview_image, settings: ProcessSettings) -> dict:
    width, height = preview_image.size
    ink_fill = _ink_fill_ratio(preview_image)
    return {
        "bitmap_width": width,
        "bitmap_height": height,
        "fits_one_label": width == settings.width_dots and height == settings.height_dots,
        "ink_fill_ratio": round(ink_fill, 4),
        "low_ink_fill": ink_fill < 0.85,
    }


def _ink_fill_ratio(image) -> float:
    """Share of label height (rows) that contain any ink."""
    width, height = image.size
    if height == 0 or width == 0:
        return 0.0
    pixels = image.load()
    threshold = 240 if image.mode != "1" else 128
    ink_rows = 0
    for y in range(height):
        for x in range(width):
            value = pixels[x, y]
            if value < threshold:
                ink_rows += 1
                break
    return ink_rows / height


async def _read_image(file: UploadFile, page: int = 1):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return load_image(data, page=page, filename=file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc


def _png_b64(image) -> str:
    return base64.b64encode(image_to_png_bytes(image)).decode("ascii")


def _parse_crop(value: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(part.strip()) for part in value.split(",")]
        if len(parts) != 4:
            raise ValueError("crop needs four numbers")
        return normalize_crop((parts[0], parts[1], parts[2], parts[3]))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="crop must be left,top,right,bottom") from exc


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _print_paced(
    printer_name: str,
    print_image,
    *,
    copies: int,
    darkness: int,
    speed: int,
    label_width: int,
    label_height: int,
    cooldown: float = 2.5,
) -> None:
    """Print one label at a time so the G-series PSU can recover between burns."""
    if copies == 1:
        zpl = image_to_zpl(
            print_image,
            darkness=darkness,
            speed=speed,
            label_width=label_width,
            label_height=label_height,
        )
        _send(printer_name, zpl, "GK420D Sticker")
        return

    download, print_one, cleanup = graphic_batch_jobs(
        print_image,
        darkness=darkness,
        speed=speed,
        label_width=label_width,
        label_height=label_height,
    )
    _send(printer_name, download, "GK420D Graphic")
    wait_until_idle(printer_name.strip())
    try:
        for index in range(copies):
            _assert_printer_awake(printer_name)
            _send(printer_name, print_one, f"GK420D Sticker {index + 1}")
            wait_until_idle(printer_name.strip())
            if index + 1 < copies:
                time.sleep(cooldown)
    finally:
        try:
            _send(printer_name, cleanup, "GK420D Cleanup")
        except Exception:
            pass


def _assert_printer_awake(printer_name: str) -> None:
    info = inspect_printer(printer_name.strip())
    if info.online:
        return
    raise HTTPException(
        status_code=502,
        detail=(
            "Printer went offline mid-batch. That is usually the power supply folding "
            "under a full 4×4 burn. Plug the original 20V brick straight into the wall, "
            "drop darkness to 12–15, use 3 ips for batches, and let the printer cool."
        ),
    )


def _send(printer_name: str, zpl: str, job_name: str) -> None:
    if not printer_name.strip():
        raise HTTPException(status_code=400, detail="Choose a printer")
    try:
        send_raw(printer_name.strip(), zpl, job_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Print failed: {exc}") from exc
