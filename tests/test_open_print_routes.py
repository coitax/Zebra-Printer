"""Open print routes must reject unauthenticated and cross-site calls before any printer I/O.

These tests are the spec for the browser-mode server started by ``run.bat``.
They fail while ``POST /api/print``, ``POST /api/calibrate``, ``POST /api/media-calibrate``,
and ``POST /api/printers/probe`` accept a request that has no per-launch secret.

Contract the fix has to meet:

- ``app.main.launch_secret()`` returns the secret generated for this process.
  The same value is returned for the life of the process. It is not a literal
  in ``app/`` and it is not present in unauthenticated HTTP responses.
- Every state-changing route listed above requires that secret in the
  ``X-GK420D-Token`` request header. A form field or query parameter of the
  same name does not count: a cross-site HTML form can set those, and it
  cannot set this header.
- When the request has an ``Origin`` header, that origin must equal the
  origin of that request (scheme, host, and port). ``http://127.0.0.1:8765``
  is the TestClient origin. The loopback test uses whatever port it bound.
  Any other origin, including ``null``, is rejected even if the header
  secret is correct.
- Rejection status is 401 or 403, and it happens before ``OpenPrinter``,
  ``StartDocPrinter``, or ``WritePrinter``.
- A request with the header secret and a matching origin still submits the
  raw job for that route, to the printer name in the form.

``GET /api/printers`` and ``GET /api/presets`` are read-only and are not
required to demand the secret. ``POST /api/source``, ``POST /api/preview``,
and ``POST /api/zpl`` do not submit a printer job and are not covered.
``app.desktop_api.Api`` is not covered: desktop mode does not listen on HTTP.
"""

from __future__ import annotations

import socket
import sys
import threading
import types
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main as main_module
from app.calibration import build_calibration_image
from app.image_pipeline import load_image, process_image
from app.main import app
from app.presets import resolve_size
from app.zpl import image_to_zpl, media_calibrate_zpl

PRINTER = "ZDesigner GK420d"
TOKEN_HEADER = "X-GK420D-Token"
APP_ORIGIN = "http://127.0.0.1:8765"
FOREIGN_ORIGIN = "https://evil.example"
PLACEHOLDER_TOKEN = "placeholder-token-value"
STATE_CHANGING_FORM_ROUTES = (
    "/api/media-calibrate",
    "/api/calibrate",
    "/api/printers/probe",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


class RecordingSpooler:
    """Stand-in for the win32print calls ``app.printer`` makes.

    ``send_raw`` opens a printer, starts a RAW document, and writes the ZPL
    bytes. ``probe`` additionally reads a status and a job. This recorder
    keeps those buffers so a test can see a job that was submitted. It does
    not apply a Windows ACL or talk to hardware.
    """

    def __init__(self) -> None:
        self.events: list[tuple] = []

    def OpenPrinter(self, name, defaults=None):
        self.events.append(("OpenPrinter", name))
        return {"name": name}

    def ClosePrinter(self, handle):
        self.events.append(("ClosePrinter",))

    def StartDocPrinter(self, handle, level, doc_info):
        self.events.append(("StartDocPrinter", level, doc_info))
        return 1

    def EndDocPrinter(self, handle):
        self.events.append(("EndDocPrinter",))

    def StartPagePrinter(self, handle):
        self.events.append(("StartPagePrinter",))

    def EndPagePrinter(self, handle):
        self.events.append(("EndPagePrinter",))

    def WritePrinter(self, handle, data):
        payload = bytes(data)
        self.events.append(("WritePrinter", payload))
        return len(payload)

    def ReadPrinter(self, handle, size):
        self.events.append(("ReadPrinter", size))
        return b"GK420d,V1.0\r\n"

    def GetPrinter(self, handle, level):
        self.events.append(("GetPrinter", level))
        return {
            "Status": 0,
            "Attributes": 0,
            "pPortName": "USB001",
            "pDriverName": "ZDesigner GK420d",
            "cJobs": 0,
        }

    def GetJob(self, handle, job_id, level):
        self.events.append(("GetJob", job_id, level))
        return {"Status": 0x80}

    def EnumPrinters(self, flags, name=None, level=1):
        self.events.append(("EnumPrinters", flags))
        return [(flags, "ZDesigner", PRINTER)]

    def GetDefaultPrinter(self):
        self.events.append(("GetDefaultPrinter",))
        return PRINTER

    def written(self) -> list[bytes]:
        return [event[1] for event in self.events if event[0] == "WritePrinter"]

    def summary(self) -> str:
        lines = []
        for event in self.events:
            if event[0] == "WritePrinter":
                payload = event[1]
                lines.append(f"WritePrinter {len(payload)} bytes {payload[:180]!r}")
            else:
                lines.append(repr(event))
        return "\n".join(lines) if lines else "<no printer calls>"


def _install_spooler(spooler: RecordingSpooler) -> None:
    module = types.ModuleType("win32print")
    module.PRINTER_ENUM_LOCAL = 2
    module.PRINTER_ENUM_CONNECTIONS = 4
    for name in (
        "OpenPrinter",
        "ClosePrinter",
        "StartDocPrinter",
        "EndDocPrinter",
        "StartPagePrinter",
        "EndPagePrinter",
        "WritePrinter",
        "ReadPrinter",
        "GetPrinter",
        "GetJob",
        "EnumPrinters",
        "GetDefaultPrinter",
    ):
        setattr(module, name, getattr(spooler, name))
    sys.modules["win32print"] = module


@pytest.fixture
def spooler():
    recorder = RecordingSpooler()
    _install_spooler(recorder)
    return recorder


@pytest.fixture
def client():
    return TestClient(app, base_url=APP_ORIGIN)


def launch_secret() -> str:
    fn = getattr(main_module, "launch_secret", None)
    if not callable(fn):
        pytest.fail("app.main.launch_secret() is missing")
    value = fn()
    if not isinstance(value, str) or len(value) < 16 or value == PLACEHOLDER_TOKEN:
        pytest.fail("launch_secret() must return a process-generated string of at least 16 characters")
    return value


def auth_headers(origin: str | None = APP_ORIGIN) -> dict[str, str]:
    headers = {TOKEN_HEADER: launch_secret()}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def form_fields() -> dict[str, str]:
    return {
        "printer_name": PRINTER,
        "preset": "custom",
        "width_in": "1",
        "height_in": "1",
    }


def black_png() -> bytes:
    image = Image.new("L", (16, 16), 0)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def assert_refused(response, spooler: RecordingSpooler) -> None:
    assert response.status_code in (401, 403), (
        f"status={response.status_code} body={response.text[:300]!r}\n{spooler.summary()}"
    )
    assert spooler.events == [], spooler.summary()


def expected_media_job() -> bytes:
    _width_in, _height_in, width_dots, height_dots, _preset = resolve_size("custom", 1.0, 1.0)
    return media_calibrate_zpl(width_dots, height_dots).encode("ascii")


def expected_calibration_job() -> bytes:
    _width_in, _height_in, width_dots, height_dots, _preset = resolve_size("custom", 1.0, 1.0)
    image = build_calibration_image(width_dots, height_dots)
    return image_to_zpl(
        image,
        darkness=18,
        speed=2,
        copies=1,
        label_width=width_dots,
        label_height=height_dots,
    ).encode("ascii")


def expected_print_job(png: bytes) -> bytes:
    from app.api_service import _settings_from_form

    settings, _inches = _settings_from_form(
        "custom", 1.0, 1.0, "cover", "threshold", 1.0, 128, "false", "0,0,1,1"
    )
    source = load_image(png, page=1, filename="art.png")
    _gray, print_image = process_image(source, settings)
    return image_to_zpl(
        print_image,
        darkness=18,
        speed=2,
        label_width=settings.width_dots,
        label_height=settings.height_dots,
    ).encode("ascii")


def assert_raw_job(spooler: RecordingSpooler, payload: bytes, job_name: str) -> None:
    documents = [event for event in spooler.events if event[0] == "StartDocPrinter"]
    assert documents == [("StartDocPrinter", 1, (job_name, None, "RAW"))], spooler.summary()
    opened = [event[1] for event in spooler.events if event[0] == "OpenPrinter"]
    assert opened, spooler.summary()
    assert all(name == PRINTER for name in opened), spooler.summary()
    assert spooler.written() == [payload], spooler.summary()


@pytest.mark.parametrize("route", STATE_CHANGING_FORM_ROUTES)
@pytest.mark.parametrize("encoding", ["urlencoded", "multipart"])
def test_cross_site_form_does_not_submit_a_printer_job(client, spooler, route, encoding):
    kwargs = {"data": form_fields(), "headers": {"Origin": FOREIGN_ORIGIN}}
    if encoding == "multipart":
        kwargs["files"] = {"note": ("note.txt", b"note", "text/plain")}
    response = client.post(route, **kwargs)
    assert_refused(response, spooler)


@pytest.mark.parametrize("route", STATE_CHANGING_FORM_ROUTES)
def test_local_client_without_a_token_does_not_submit_a_printer_job(client, spooler, route):
    response = client.post(route, data=form_fields())
    assert_refused(response, spooler)


def test_cross_site_print_of_an_uploaded_image_does_not_submit_a_job(client, spooler):
    response = client.post(
        "/api/print",
        data={**form_fields(), "copies": "1", "dither": "threshold", "sharpen": "false"},
        files={"file": ("art.png", black_png(), "image/png")},
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert_refused(response, spooler)


def test_print_without_a_token_does_not_submit_a_job(client, spooler):
    response = client.post(
        "/api/print",
        data={**form_fields(), "copies": "1", "dither": "threshold", "sharpen": "false"},
        files={"file": ("art.png", black_png(), "image/png")},
    )
    assert_refused(response, spooler)


@pytest.mark.parametrize("route", ("/api/media-calibrate", "/api/calibrate", "/api/print"))
def test_placeholder_token_header_does_not_submit_a_job(client, spooler, route):
    headers = {TOKEN_HEADER: PLACEHOLDER_TOKEN, "Origin": APP_ORIGIN}
    kwargs = {
        "data": {**form_fields(), "copies": "1", "dither": "threshold", "sharpen": "false"},
        "headers": headers,
    }
    if route == "/api/print":
        kwargs["files"] = {"file": ("art.png", black_png(), "image/png")}
    response = client.post(route, **kwargs)
    assert_refused(response, spooler)


def test_token_in_the_form_body_does_not_media_calibrate(client, spooler):
    secret = launch_secret()
    response = client.post(
        "/api/media-calibrate",
        data={**form_fields(), TOKEN_HEADER: secret, "token": secret},
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert_refused(response, spooler)


def test_token_in_the_query_string_does_not_media_calibrate(client, spooler):
    secret = launch_secret()
    response = client.post(
        f"/api/media-calibrate?{TOKEN_HEADER}={secret}&token={secret}",
        data=form_fields(),
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert_refused(response, spooler)


@pytest.mark.parametrize("origin", (FOREIGN_ORIGIN, "null", "https://127.0.0.1:8765", "http://127.0.0.1:9"))
def test_foreign_origin_is_rejected_with_the_launch_secret(client, spooler, origin):
    response = client.post(
        "/api/media-calibrate",
        data=form_fields(),
        headers=auth_headers(origin),
    )
    assert_refused(response, spooler)


def test_launch_secret_is_stable_and_not_in_app_source_or_http_responses(client, spooler):
    secret = launch_secret()
    assert launch_secret() == secret
    for path in REPO_ROOT.joinpath("app").rglob("*.py"):
        assert secret not in path.read_text(encoding="utf-8")
    for path in ("/", "/app.js", "/api/presets", "/api/printers"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert secret not in response.text
    assert spooler.written() == []


def test_authorized_media_calibrate_writes_save_and_calibration_commands(client, spooler):
    response = client.post("/api/media-calibrate", data=form_fields(), headers=auth_headers())
    assert response.status_code == 200, response.text
    payload = expected_media_job()
    assert b"^JUS\n" in payload
    assert payload.endswith(b"^XZ\n~JC\n")
    assert_raw_job(spooler, payload, "GK420D Media Calibrate")


def test_authorized_one_label_test_writes_a_raw_label(client, spooler):
    response = client.post(
        "/api/calibrate",
        data={**form_fields(), "darkness": "18", "speed": "2"},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    payload = expected_calibration_job()
    assert b"^XA\n" in payload and b"^GFA," in payload
    assert_raw_job(spooler, payload, "GK420D Calibration")


def test_authorized_print_writes_the_uploaded_artwork(client, spooler):
    png = black_png()
    response = client.post(
        "/api/print",
        data={
            **form_fields(),
            "fit": "cover",
            "dither": "threshold",
            "contrast": "1",
            "threshold": "128",
            "sharpen": "false",
            "darkness": "18",
            "speed": "2",
            "copies": "1",
            "crop": "0,0,1,1",
            "page": "1",
        },
        files={"file": ("art.png", png, "image/png")},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    payload = expected_print_job(png)
    assert b"^GFA," in payload
    assert_raw_job(spooler, payload, "GK420D Sticker")


def test_authorized_probe_writes_to_the_named_printer(client, spooler):
    response = client.post(
        "/api/printers/probe",
        data={"printer_name": PRINTER},
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    assert any(payload.startswith(b"~HI") for payload in spooler.written()), spooler.summary()
    opened = [event[1] for event in spooler.events if event[0] == "OpenPrinter"]
    assert PRINTER in opened


def test_loopback_listener_rejects_a_cross_site_form_before_printer_io(spooler):
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    config_cls, server_cls = _uvicorn()
    server = server_cls(config_cls(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = _deadline(5)
    while not server.started and thread.is_alive() and _now() < deadline:
        _sleep(0.02)
    assert server.started, "uvicorn did not bind 127.0.0.1"
    try:
        response = httpx.post(
            f"{origin}/api/media-calibrate",
            data=form_fields(),
            headers={"Origin": FOREIGN_ORIGIN},
            timeout=5,
        )
        assert_refused(response, spooler)
        allowed = httpx.post(
            f"{origin}/api/media-calibrate",
            data=form_fields(),
            headers={TOKEN_HEADER: launch_secret(), "Origin": origin},
            timeout=5,
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
    assert allowed.status_code == 200, allowed.text
    assert_raw_job(spooler, expected_media_job(), "GK420D Media Calibrate")


def _uvicorn():
    import uvicorn

    return uvicorn.Config, uvicorn.Server


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _now() -> float:
    import time

    return time.monotonic()


def _deadline(seconds: float) -> float:
    return _now() + seconds


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
