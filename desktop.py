"""Launch the sticker app as a Windows window. Closing the window stops the server."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from app.main import APP_BUILD, app

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"
WAIT_TIMEOUT_SEC = 15.0

_server_error: str | None = None
_server_error_lock = threading.Lock()
_logger = logging.getLogger("gk420d.desktop")


def main() -> None:
    _configure_logging()
    try:
        _ensure_server_running()
    except RuntimeError as exc:
        _show_fatal_error(str(exc))
        sys.exit(1)

    try:
        import webview
    except ImportError:
        webbrowser.open(URL)
        print(f"Opened {URL}. Keep this window open to keep the server running.")
        print("Close this window to stop the app.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
        return

    window = webview.create_window(
        "GK420D Sticker Printer",
        URL,
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
    _logger.info("Starting GK420D Sticker Printer desktop")


def _log_directory() -> Path | None:
    if sys.platform != "win32":
        return None
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if not local:
        return None
    return local / "GK420D Sticker Printer"


def _ensure_server_running() -> None:
    """Kill stale listeners, start uvicorn, wait until our API responds."""
    last_error = "The local server did not start."
    for attempt in (1, 2):
        _logger.info("Server start attempt %s", attempt)
        _kill_listeners_on_port(PORT)
        time.sleep(0.25)

        if _port_open() and not _is_our_server():
            _logger.warning("Port %s is in use by another application", PORT)
            if attempt == 1:
                _kill_listeners_on_port(PORT)
                time.sleep(0.25)
                continue
            raise RuntimeError(
                f"Port {PORT} is already in use by another program. "
                "Close other apps using that port and try again."
            )

        _clear_server_error()
        thread = threading.Thread(target=_run_server, name="uvicorn", daemon=True)
        thread.start()

        try:
            _wait_for_server(timeout=WAIT_TIMEOUT_SEC)
        except RuntimeError as exc:
            last_error = str(exc)
            thread_err = _peek_server_error()
            if thread_err:
                last_error = f"{last_error}\n\n{thread_err}"
            _logger.error("Server wait failed: %s", last_error)
            if attempt == 1:
                _kill_listeners_on_port(PORT)
                continue
            raise RuntimeError(last_error) from exc

        if _is_our_server():
            _logger.info("Server ready at %s", URL)
            return

        last_error = (
            f"Something on {URL} is not this app. "
            "Close other GK420D or dev server instances and try again."
        )
        if attempt == 1:
            _kill_listeners_on_port(PORT)
            continue
        raise RuntimeError(last_error)

    raise RuntimeError(last_error)


def _run_server() -> None:
    global _server_error
    try:
        _logger.info("Uvicorn starting on %s:%s", HOST, PORT)
        config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
        uvicorn.Server(config).run()
    except Exception:
        err = traceback.format_exc()
        _logger.exception("Uvicorn failed")
        with _server_error_lock:
            _server_error = err


def _clear_server_error() -> None:
    global _server_error
    with _server_error_lock:
        _server_error = None


def _peek_server_error() -> str | None:
    with _server_error_lock:
        return _server_error


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.3):
            return True
    except OSError:
        return False


def _is_our_server() -> bool:
    try:
        req = urllib.request.Request(
            f"{URL}/api/presets",
            headers={"User-Agent": "GK420D-Desktop/1"},
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("build") == APP_BUILD
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


def _wait_for_server(timeout: float = WAIT_TIMEOUT_SEC) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        thread_err = _peek_server_error()
        if thread_err:
            raise RuntimeError(f"Server crashed while starting:\n{thread_err}")
        if _is_our_server():
            return
        time.sleep(0.1)
    thread_err = _peek_server_error()
    if thread_err:
        raise RuntimeError(f"Server crashed while starting:\n{thread_err}")
    raise RuntimeError(f"Server did not start on {URL}")


def _kill_listeners_on_port(port: int) -> None:
    if sys.platform != "win32":
        return
    try:
        result = subprocess.run(
            ["netstat", "-aon"],
            capture_output=True,
            text=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        _logger.warning("netstat failed: %s", exc)
        return

    suffix = f":{port}"
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if suffix not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        pid_text = parts[-1]
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid <= 0:
            continue
        pids.add(pid)

    our_pid = os.getpid()
    for pid in sorted(pids):
        if pid == our_pid:
            continue
        _logger.info("Killing stale listener PID %s on port %s", pid, port)
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def _show_fatal_error(message: str) -> None:
    _logger.error("Fatal: %s", message)
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                0,
                message,
                "GK420D Sticker Printer",
                0x00000010,  # MB_ICONERROR
            )
            return
        except OSError:
            pass
    print(message, file=sys.stderr)


if __name__ == "__main__":
    main()
