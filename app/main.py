from __future__ import annotations

import base64
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.calibration import build_calibration_image
from app.image_pipeline import ProcessSettings, image_to_png_bytes, load_image, process_image
from app.presets import PRESETS, resolve_size
from app.printer import list_printers, probe_printer, recommended_printer_name, send_raw
from app.paths import resource_root
from app.zpl import image_to_zpl, media_calibrate_zpl

ROOT = resource_root()
STATIC = ROOT / "static"

app = FastAPI(title="GK420D Sticker Printer")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/presets")
def presets() -> dict:
    return {"presets": list(PRESETS.values())}


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


@app.post("/api/preview")
async def preview(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = "4x4",
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    fit: Annotated[str, Form()] = "cover",
    dither: Annotated[str, Form()] = "floyd",
    contrast: Annotated[float, Form()] = 1.2,
    threshold: Annotated[int, Form()] = 128,
    sharpen: Annotated[str, Form()] = "true",
) -> dict:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen
    )
    source = await _read_image(file)
    gray, print_image = process_image(source, settings)
    return {
        **inches,
        **_fit_check(print_image, settings),
        "original_png": _png_b64(gray),
        "print_png": _png_b64(print_image),
    }


@app.post("/api/zpl")
async def download_zpl(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = "4x4",
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
) -> PlainTextResponse:
    settings, _ = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen
    )
    source = await _read_image(file)
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
    preset: Annotated[str, Form()] = "4x4",
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
) -> dict:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen
    )
    source = await _read_image(file)
    _, print_image = process_image(source, settings)
    zpl = image_to_zpl(
        print_image,
        darkness=darkness,
        speed=speed,
        copies=copies,
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    )
    _send(printer_name, zpl, "GK420D Sticker")
    return {
        "ok": True,
        **inches,
        **_fit_check(print_image, settings),
        "copies": max(1, min(99, copies)),
    }


@app.post("/api/calibrate")
async def print_calibration(
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = "4x4",
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
    preset: Annotated[str, Form()] = "4x4",
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
    )
    return settings, {
        "preset": preset_id,
        "width_in": width_in,
        "height_in": height_in,
        "width_dots": width_dots,
        "height_dots": height_dots,
    }


def _fit_check(print_image, settings: ProcessSettings) -> dict:
    width, height = print_image.size
    return {
        "bitmap_width": width,
        "bitmap_height": height,
        "fits_one_label": width == settings.width_dots and height == settings.height_dots,
    }


async def _read_image(file: UploadFile):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return load_image(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read image: {exc}") from exc


def _png_b64(image) -> str:
    return base64.b64encode(image_to_png_bytes(image)).decode("ascii")


def _as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _send(printer_name: str, zpl: str, job_name: str) -> None:
    if not printer_name.strip():
        raise HTTPException(status_code=400, detail="Choose a printer")
    try:
        send_raw(printer_name.strip(), zpl, job_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Print failed: {exc}") from exc
