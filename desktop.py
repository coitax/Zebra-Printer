"""GK420D sticker app — desktop window with pywebview js_api (no HTTP server)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from app.desktop_api import Api
from app.paths import resource_root

_logger = logging.getLogger("gk420d.desktop")


def main() -> None:
    _configure_logging()
    index_path = resource_root() / "static" / "index.html"
    if not index_path.is_file():
        _show_fatal_error(f"UI not found:\n{index_path}")
        sys.exit(1)

    url = index_path.resolve().as_uri()
    _logger.info("Loading UI from %s", url)

    try:
        import webview
    except ImportError:
        _show_fatal_error(
            "pywebview is not installed. Use run.bat for browser mode, or pip install -r requirements.txt."
        )
        sys.exit(1)

    api = Api()
    window = webview.create_window(
        "GK420D Sticker Printer",
        url,
        js_api=api,
        width=1220,
        height=900,
        min_size=(900, 700),
    )
    webview.start()
    del window


def _configure_logging() -> None:
    log_dir = _log_directory()
    if log_dir is None:
        logging.basicConfig(level=logging.INFO)
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "desktop.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    _logger.info("Starting GK420D Sticker Printer desktop (no local HTTP server)")


def _log_directory() -> Path | None:
    if sys.platform != "win32":
        return None
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if not local:
        return None
    return local / "GK420D Sticker Printer"


def _show_fatal_error(message: str) -> None:
    _logger.error("Fatal: %s", message)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                0,
                message,
                "GK420D Sticker Printer",
                0x00000010,
            )
            return
        except OSError:
            pass
    print(message, file=sys.stderr)


if __name__ == "__main__":
    main()
