"""Shared API logic for FastAPI routes and pywebview js_api."""

from __future__ import annotations

import base64
import time
from typing import Any

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
from app.zpl import graphic_batch_jobs, image_to_zpl, media_calibrate_zpl

APP_BUILD = "4x6-adaptive-crop"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def get_presets() -> dict[str, Any]:
    return {
        "presets": list(PRESETS.values()),
        "default": DEFAULT_PRESET,
        "build": APP_BUILD,
    }


def get_printers() -> dict[str, Any]:
    try:
        found = list_printers()
        recommended = recommended_printer_name(found)
    except RuntimeError as exc:
        raise ApiError(str(exc), 501) from exc
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


def probe_printer_name(printer_name: str) -> dict[str, Any]:
    if not printer_name.strip():
        raise ApiError("Choose a printer", 400)
    try:
        return probe_printer(printer_name.strip()).as_dict()
    except RuntimeError as exc:
        raise ApiError(str(exc), 501) from exc
    except Exception as exc:
        raise ApiError(f"Probe failed: {exc}", 502) from exc


def source_preview_bytes(data: bytes, *, filename: str = "", page: int = 1) -> dict[str, Any]:
    if not data:
        raise ApiError("Empty file", 400)
    try:
        pages = pdf_page_count(data) if is_pdf(data, filename) else 1
        image = load_image(data, page=page, filename=filename)
        detected = label_crop_for_image(image, filename)
    except Exception as exc:
        raise ApiError(f"Could not read file: {exc}", 400) from exc
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


def preview_bytes(
    data: bytes,
    *,
    filename: str = "",
    preset: str = DEFAULT_PRESET,
    width_in: float | None = None,
    height_in: float | None = None,
    fit: str = "cover",
    dither: str = "floyd",
    contrast: float = 1.2,
    threshold: int = 128,
    sharpen: str | bool = "true",
    crop: str = "0,0,1,1",
    page: int = 1,
) -> dict[str, Any]:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = _load_image(data, page=page, filename=filename)
    gray, print_image = process_image(source, settings)
    return {
        **inches,
        **_fit_check(gray, settings),
        "original_png": _png_b64(gray),
        "print_png": _png_b64(print_image),
    }


def build_zpl_bytes(
    data: bytes,
    *,
    filename: str = "",
    preset: str = DEFAULT_PRESET,
    width_in: float | None = None,
    height_in: float | None = None,
    fit: str = "cover",
    dither: str = "floyd",
    contrast: float = 1.2,
    threshold: int = 128,
    sharpen: str | bool = "true",
    darkness: int = 18,
    speed: int = 2,
    copies: int = 1,
    crop: str = "0,0,1,1",
    page: int = 1,
) -> str:
    settings, _ = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = _load_image(data, page=page, filename=filename)
    _, print_image = process_image(source, settings)
    return image_to_zpl(
        print_image,
        darkness=darkness,
        speed=speed,
        copies=max(1, min(99, int(copies))),
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    )


def print_sticker_bytes(
    data: bytes,
    *,
    printer_name: str,
    filename: str = "",
    preset: str = DEFAULT_PRESET,
    width_in: float | None = None,
    height_in: float | None = None,
    fit: str = "cover",
    dither: str = "floyd",
    contrast: float = 1.2,
    threshold: int = 128,
    sharpen: str | bool = "true",
    darkness: int = 18,
    speed: int = 2,
    copies: int = 1,
    crop: str = "0,0,1,1",
    page: int = 1,
) -> dict[str, Any]:
    settings, inches = _settings_from_form(
        preset, width_in, height_in, fit, dither, contrast, threshold, sharpen, crop
    )
    source = _load_image(data, page=page, filename=filename)
    _, print_image = process_image(source, settings)
    copies_n = max(1, min(99, int(copies)))
    _print_paced(
        printer_name,
        print_image,
        copies=copies_n,
        darkness=darkness,
        speed=speed,
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    )
    return {
        "ok": True,
        **inches,
        **_fit_check(print_image, settings),
        "copies": copies_n,
    }


def print_calibration(
    printer_name: str,
    *,
    preset: str = DEFAULT_PRESET,
    width_in: float | None = None,
    height_in: float | None = None,
    darkness: int = 18,
    speed: int = 2,
) -> dict[str, Any]:
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


def media_calibrate(
    printer_name: str,
    *,
    preset: str = DEFAULT_PRESET,
    width_in: float | None = None,
    height_in: float | None = None,
) -> dict[str, Any]:
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
    sharpen: str | bool,
    crop: str = "0,0,1,1",
) -> tuple[ProcessSettings, dict[str, Any]]:
    if fit not in {"contain", "cover", "stretch"}:
        raise ApiError("fit must be contain, cover, or stretch", 400)
    if dither not in {"floyd", "atkinson", "threshold"}:
        raise ApiError("dither must be floyd, atkinson, or threshold", 400)

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


def _fit_check(preview_image, settings: ProcessSettings) -> dict[str, Any]:
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


def _load_image(data: bytes, page: int = 1, filename: str = ""):
    if not data:
        raise ApiError("Empty file", 400)
    try:
        return load_image(data, page=page, filename=filename)
    except Exception as exc:
        raise ApiError(f"Could not read file: {exc}", 400) from exc


def _png_b64(image) -> str:
    return base64.b64encode(image_to_png_bytes(image)).decode("ascii")


def _parse_crop(value: str) -> tuple[float, float, float, float]:
    try:
        parts = [float(part.strip()) for part in value.split(",")]
        if len(parts) != 4:
            raise ValueError("crop needs four numbers")
        return normalize_crop((parts[0], parts[1], parts[2], parts[3]))
    except (TypeError, ValueError) as exc:
        raise ApiError("crop must be left,top,right,bottom", 400) from exc


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
    raise ApiError(
        "Printer went offline mid-batch. That is usually the power supply folding "
        "under a full 4×4 burn. Plug the original 20V brick straight into the wall, "
        "drop darkness to 12–15, use 3 ips for batches, and let the printer cool.",
        502,
    )


def _send(printer_name: str, zpl: str, job_name: str) -> None:
    if not printer_name.strip():
        raise ApiError("Choose a printer", 400)
    try:
        send_raw(printer_name.strip(), zpl, job_name)
    except RuntimeError as exc:
        raise ApiError(str(exc), 501) from exc
    except Exception as exc:
        raise ApiError(f"Print failed: {exc}", 502) from exc
