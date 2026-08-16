"""Launch the sticker app as a Windows window. Closing the window stops the server."""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from app.main import app

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def main() -> None:
    if not _port_open():
        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()
        _wait_for_server()

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


def _run_server() -> None:
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    uvicorn.Server(config).run()


def _port_open() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.3):
            return True
    except OSError:
        return False


def _wait_for_server(timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_open():
            return
        time.sleep(0.1)
    raise RuntimeError(f"Server did not start on {URL}")


if __name__ == "__main__":
    main()
