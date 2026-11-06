from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app import api_service
from app.api_service import ApiError
from app.paths import resource_root

ROOT = resource_root()
STATIC = ROOT / "static"

app = FastAPI(title="GK420D Sticker Printer")

APP_BUILD = api_service.APP_BUILD


def _http_error(exc: ApiError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.message)


@app.get("/api/presets")
def presets() -> dict:
    return api_service.get_presets()


@app.get("/api/printers")
def printers() -> dict:
    try:
        return api_service.get_printers()
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/printers/probe")
def probe(printer_name: Annotated[str, Form()]) -> dict:
    try:
        return api_service.probe_printer_name(printer_name)
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/source")
async def source_preview(
    file: Annotated[UploadFile, File()],
    page: Annotated[int, Form()] = 1,
) -> dict:
    data = await file.read()
    try:
        return api_service.source_preview_bytes(data, filename=file.filename or "", page=page)
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/preview")
async def preview(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = api_service.DEFAULT_PRESET,
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
    data = await file.read()
    try:
        return api_service.preview_bytes(
            data,
            filename=file.filename or "",
            preset=preset,
            width_in=width_in,
            height_in=height_in,
            fit=fit,
            dither=dither,
            contrast=contrast,
            threshold=threshold,
            sharpen=sharpen,
            crop=crop,
            page=page,
        )
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/zpl")
async def download_zpl(
    file: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = api_service.DEFAULT_PRESET,
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
    data = await file.read()
    try:
        zpl = api_service.build_zpl_bytes(
            data,
            filename=file.filename or "",
            preset=preset,
            width_in=width_in,
            height_in=height_in,
            fit=fit,
            dither=dither,
            contrast=contrast,
            threshold=threshold,
            sharpen=sharpen,
            darkness=darkness,
            speed=speed,
            copies=copies,
            crop=crop,
            page=page,
        )
    except ApiError as exc:
        raise _http_error(exc) from exc
    return PlainTextResponse(
        zpl,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="sticker.zpl"'},
    )


@app.post("/api/print")
async def print_sticker(
    file: Annotated[UploadFile, File()],
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = api_service.DEFAULT_PRESET,
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
    data = await file.read()
    try:
        return api_service.print_sticker_bytes(
            data,
            printer_name=printer_name,
            filename=file.filename or "",
            preset=preset,
            width_in=width_in,
            height_in=height_in,
            fit=fit,
            dither=dither,
            contrast=contrast,
            threshold=threshold,
            sharpen=sharpen,
            darkness=darkness,
            speed=speed,
            copies=copies,
            crop=crop,
            page=page,
        )
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/calibrate")
async def print_calibration(
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = api_service.DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
    darkness: Annotated[int, Form()] = 18,
    speed: Annotated[int, Form()] = 2,
) -> dict:
    try:
        return api_service.print_calibration(
            printer_name,
            preset=preset,
            width_in=width_in,
            height_in=height_in,
            darkness=darkness,
            speed=speed,
        )
    except ApiError as exc:
        raise _http_error(exc) from exc


@app.post("/api/media-calibrate")
async def media_calibrate(
    printer_name: Annotated[str, Form()],
    preset: Annotated[str, Form()] = api_service.DEFAULT_PRESET,
    width_in: Annotated[float | None, Form()] = None,
    height_in: Annotated[float | None, Form()] = None,
) -> dict:
    try:
        return api_service.media_calibrate(
            printer_name,
            preset=preset,
            width_in=width_in,
            height_in=height_in,
        )
    except ApiError as exc:
        raise _http_error(exc) from exc


app.mount("/", StaticFiles(directory=STATIC, html=True), name="frontend")
