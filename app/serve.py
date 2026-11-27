"""Browser-mode launcher: serve the API on 127.0.0.1 and open the page with this launch's secret."""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn

from app.main import app, launch_secret

HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def launch_url(port: int) -> str:
    # The secret rides in the fragment, which the browser never sends to the server.
    return f"http://{HOST}:{port}/#token={launch_secret()}"


def main() -> None:
    parser = argparse.ArgumentParser(description="GK420D sticker printer (browser mode)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = uvicorn.Server(
        uvicorn.Config(app, host=HOST, port=args.port, proxy_headers=False, log_level="info")
    )
    threading.Thread(
        target=_open_when_ready, args=(server, args.port, not args.no_browser), daemon=True
    ).start()
    server.run()


def _open_when_ready(server: uvicorn.Server, port: int, open_browser: bool) -> None:
    # Only hand out the secret once this process owns the port.
    while not server.started:
        if server.should_exit:
            return
        time.sleep(0.05)
    url = launch_url(port)
    print(f"\nGK420D sticker printer is running. If the browser did not open, visit:\n  {url}\n", flush=True)
    if open_browser:
        webbrowser.open(url)


if __name__ == "__main__":
    main()
