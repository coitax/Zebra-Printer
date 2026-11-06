"""pywebview js_api — same operations as HTTP routes, no server."""

from __future__ import annotations

import base64
from typing import Any

from app import api_service


class Api:
    """Exposed to JavaScript as window.pywebview.api."""

    def get_presets(self) -> dict[str, Any]:
        return api_service.get_presets()

    def get_printers(self) -> dict[str, Any]:
        return api_service.get_printers()

    def probe_printer(self, printer_name: str) -> dict[str, Any]:
        return api_service.probe_printer_name(printer_name)

    def source_preview(
        self,
        file_b64: str,
        filename: str = "",
        page: int = 1,
    ) -> dict[str, Any]:
        data = base64.b64decode(file_b64)
        return api_service.source_preview_bytes(data, filename=filename, page=int(page))

    def preview(self, params: dict[str, Any]) -> dict[str, Any]:
        data = base64.b64decode(params["file_b64"])
        return api_service.preview_bytes(
            data,
            filename=str(params.get("filename") or ""),
            preset=str(params.get("preset") or api_service.DEFAULT_PRESET),
            width_in=_optional_float(params.get("width_in")),
            height_in=_optional_float(params.get("height_in")),
            fit=str(params.get("fit") or "cover"),
            dither=str(params.get("dither") or "floyd"),
            contrast=float(params.get("contrast") or 1.2),
            threshold=int(params.get("threshold") or 128),
            sharpen=params.get("sharpen", "true"),
            crop=str(params.get("crop") or "0,0,1,1"),
            page=int(params.get("page") or 1),
        )

    def build_zpl(self, params: dict[str, Any]) -> str:
        data = base64.b64decode(params["file_b64"])
        return api_service.build_zpl_bytes(
            data,
            filename=str(params.get("filename") or ""),
            preset=str(params.get("preset") or api_service.DEFAULT_PRESET),
            width_in=_optional_float(params.get("width_in")),
            height_in=_optional_float(params.get("height_in")),
            fit=str(params.get("fit") or "cover"),
            dither=str(params.get("dither") or "floyd"),
            contrast=float(params.get("contrast") or 1.2),
            threshold=int(params.get("threshold") or 128),
            sharpen=params.get("sharpen", "true"),
            darkness=int(params.get("darkness") or 18),
            speed=int(params.get("speed") or 2),
            copies=int(params.get("copies") or 1),
            crop=str(params.get("crop") or "0,0,1,1"),
            page=int(params.get("page") or 1),
        )

    def print_sticker(self, params: dict[str, Any]) -> dict[str, Any]:
        data = base64.b64decode(params["file_b64"])
        return api_service.print_sticker_bytes(
            data,
            printer_name=str(params.get("printer_name") or ""),
            filename=str(params.get("filename") or ""),
            preset=str(params.get("preset") or api_service.DEFAULT_PRESET),
            width_in=_optional_float(params.get("width_in")),
            height_in=_optional_float(params.get("height_in")),
            fit=str(params.get("fit") or "cover"),
            dither=str(params.get("dither") or "floyd"),
            contrast=float(params.get("contrast") or 1.2),
            threshold=int(params.get("threshold") or 128),
            sharpen=params.get("sharpen", "true"),
            darkness=int(params.get("darkness") or 18),
            speed=int(params.get("speed") or 2),
            copies=int(params.get("copies") or 1),
            crop=str(params.get("crop") or "0,0,1,1"),
            page=int(params.get("page") or 1),
        )

    def calibrate(self, params: dict[str, Any]) -> dict[str, Any]:
        return api_service.print_calibration(
            str(params.get("printer_name") or ""),
            preset=str(params.get("preset") or api_service.DEFAULT_PRESET),
            width_in=_optional_float(params.get("width_in")),
            height_in=_optional_float(params.get("height_in")),
            darkness=int(params.get("darkness") or 18),
            speed=int(params.get("speed") or 2),
        )

    def media_calibrate(self, params: dict[str, Any]) -> dict[str, Any]:
        return api_service.media_calibrate(
            str(params.get("printer_name") or ""),
            preset=str(params.get("preset") or api_service.DEFAULT_PRESET),
            width_in=_optional_float(params.get("width_in")),
            height_in=_optional_float(params.get("height_in")),
        )


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
