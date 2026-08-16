from __future__ import annotations

import re
import socket
import time
from dataclasses import asdict, dataclass, field

PRINTER_STATUS_FLAGS = (
    (0x00000001, "paused"),
    (0x00000002, "error"),
    (0x00000008, "paper jam"),
    (0x00000010, "paper out"),
    (0x00000040, "paper problem"),
    (0x00000080, "offline"),
    (0x00000100, "I/O active"),
    (0x00000200, "busy"),
    (0x00000400, "printing"),
    (0x00001000, "not available"),
    (0x00002000, "waiting"),
    (0x00004000, "processing"),
    (0x00100000, "needs attention"),
    (0x00200000, "out of memory"),
    (0x00400000, "cover open"),
)

PRINTER_ATTRIBUTE_WORK_OFFLINE = 0x00000400
PRINTER_ATTRIBUTE_ENABLE_BIDI = 0x00000800
JOB_STATUS_ERROR = 0x00000002
JOB_STATUS_OFFLINE = 0x00000020
JOB_STATUS_PAPEROUT = 0x00000040
JOB_STATUS_DELETED = 0x00000004
JOB_STATUS_PRINTED = 0x00000080
ZEBRA_HINTS = (
    "zebra",
    "zdesigner",
    "gk420",
    "gx420",
    "zd420",
    "zt230",
    "zp450",
    "zpl",
)


@dataclass(frozen=True)
class PrinterInfo:
    name: str
    description: str
    port: str = ""
    driver: str = ""
    jobs: int = 0
    online: bool = True
    status_text: str = "unknown"
    likely_zebra: bool = False


@dataclass
class ProbeResult:
    ok: bool
    talking: bool
    name: str
    port: str = ""
    driver: str = ""
    online: bool = False
    likely_zebra: bool = False
    status_text: str = "unknown"
    jobs: int = 0
    identity: str = ""
    model: str = ""
    firmware: str = ""
    method: str = ""
    delivered: bool = False
    bidirectional: bool | None = None
    message: str = ""
    hints: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def list_printers() -> list[PrinterInfo]:
    win32print = _win32print()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    printers = []
    seen: set[str] = set()
    for entry in win32print.EnumPrinters(flags):
        name = entry[2]
        if not name or name in seen:
            continue
        seen.add(name)
        printers.append(inspect_printer(name, description=entry[1] or ""))
    printers.sort(key=lambda item: (not item.likely_zebra, item.name.lower()))
    return printers


def default_printer_name() -> str | None:
    win32print = _win32print()
    try:
        name = win32print.GetDefaultPrinter()
    except Exception:
        return None
    return name or None


def recommended_printer_name(printers: list[PrinterInfo] | None = None) -> str | None:
    found = printers if printers is not None else list_printers()
    for item in found:
        if item.likely_zebra and item.online:
            return item.name
    for item in found:
        if item.likely_zebra:
            return item.name
    return default_printer_name()


def inspect_printer(printer_name: str, description: str = "") -> PrinterInfo:
    details = _printer_details(printer_name)
    driver = details.get("driver") or ""
    likely = _looks_like_zebra(printer_name, driver, description)
    return PrinterInfo(
        name=printer_name,
        description=description,
        port=details.get("port") or "",
        driver=driver,
        jobs=int(details.get("jobs") or 0),
        online=bool(details.get("online", True)),
        status_text=str(details.get("status_text") or "unknown"),
        likely_zebra=likely,
    )


def probe_printer(printer_name: str) -> ProbeResult:
    info = inspect_printer(printer_name)
    result = ProbeResult(
        ok=False,
        talking=False,
        name=info.name,
        port=info.port,
        driver=info.driver,
        online=info.online,
        likely_zebra=info.likely_zebra,
        status_text=info.status_text,
        jobs=info.jobs,
    )

    if not info.likely_zebra:
        result.hints.append("This does not look like a Zebra queue. Prefer a ZDesigner / GK420 name.")
    if not info.online:
        result.message = f"Windows reports {info.name} as {info.status_text}."
        result.hints.append("Power the GK420D on, plug in USB, and clear Use Printer Offline.")
        return result

    details = _printer_details(info.name)
    result.bidirectional = details.get("bidirectional")

    identity, method, delivered = _query_identity(info.name, info.port)
    result.delivered = delivered
    result.method = method or "windows-status"
    if identity:
        model, firmware = _parse_hi(identity)
        result.talking = True
        result.ok = True
        result.identity = identity
        result.model = model
        result.firmware = firmware
        who = model or identity
        extra = f" firmware {firmware}" if firmware else ""
        result.message = f"{who} answered{extra}."
        return result

    if delivered and info.likely_zebra:
        result.talking = True
        result.ok = True
        result.message = (
            f"ZPL reached {info.name} on {info.port or 'USB'}. "
            "The printer accepted the job."
        )
        if result.bidirectional is False:
            result.hints.append("Enable bidirectional support in the ZDesigner driver to read model/firmware.")
        return result

    if info.likely_zebra and info.online:
        result.ok = True
        result.message = (
            f"{info.name} is installed and online on {info.port or 'an unknown port'}, "
            "but Windows did not confirm a ZPL handshake."
        )
        result.hints.append("In printer properties, enable bidirectional support and uncheck Use Printer Offline.")
        result.hints.append("If jobs sit in the queue, the USB cable or driver is not passing data.")
    else:
        result.message = f"{info.name} is online, but it never identified itself as a Zebra."
        result.hints.append("Select the ZDesigner GK420d / GX420d queue, not Microsoft Print to PDF.")
    return result


def send_raw(printer_name: str, payload: str | bytes, job_name: str = "GK420D Sticker") -> None:
    win32print = _win32print()
    data = payload.encode("ascii") if isinstance(payload, str) else payload
    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(handle, 1, (job_name, None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def _printer_details(printer_name: str) -> dict:
    win32print = _win32print()
    handle = win32print.OpenPrinter(printer_name)
    try:
        info = win32print.GetPrinter(handle, 2)
    finally:
        win32print.ClosePrinter(handle)

    status = int(info.get("Status") or 0)
    attributes = int(info.get("Attributes") or 0)
    flags = [label for bit, label in PRINTER_STATUS_FLAGS if status & bit]
    work_offline = bool(attributes & PRINTER_ATTRIBUTE_WORK_OFFLINE)
    if work_offline and "offline" not in flags:
        flags.append("offline")
    online = not work_offline and not (status & (0x00000080 | 0x00001000 | 0x00000002))
    status_text = ", ".join(flags) if flags else ("online" if online else "offline")
    return {
        "port": info.get("pPortName") or "",
        "driver": info.get("pDriverName") or "",
        "jobs": int(info.get("cJobs") or 0),
        "online": online,
        "status_text": status_text,
        "bidirectional": bool(attributes & PRINTER_ATTRIBUTE_ENABLE_BIDI),
    }


def _looks_like_zebra(*parts: str) -> bool:
    blob = " ".join(part or "" for part in parts).lower()
    return any(hint in blob for hint in ZEBRA_HINTS)


def _query_identity(printer_name: str, port: str) -> tuple[str, str, bool]:
    commands = (b"~HI\r\n", b'! U1 getvar "device.product_name"\r\n')
    host = _port_host(port)
    if host:
        for command in commands:
            reply = _query_tcp(host, command)
            if reply:
                return reply, f"tcp:{host}:9100", True
    delivered = False
    for command in commands:
        reply, accepted = _query_spooler(printer_name, command)
        delivered = delivered or accepted
        if reply:
            return reply, "windows-raw", True
    reply = _query_port_file(port, b"~HI\r\n")
    if reply:
        return reply, f"port:{port}", True
    return "", "job-accepted" if delivered else "no-reply", delivered


def _query_tcp(host: str, command: bytes, timeout: float = 2.0) -> str:
    try:
        with socket.create_connection((host, 9100), timeout=timeout) as sock:
            sock.sendall(command)
            sock.settimeout(timeout)
            chunks = []
            try:
                while True:
                    piece = sock.recv(1024)
                    if not piece:
                        break
                    chunks.append(piece)
                    if len(b"".join(chunks)) >= 32:
                        break
            except TimeoutError:
                pass
        return _clean_reply(b"".join(chunks))
    except OSError:
        return ""


def _query_spooler(printer_name: str, command: bytes) -> tuple[str, bool]:
    win32print = _win32print()
    handle = win32print.OpenPrinter(printer_name)
    job_id = None
    try:
        job_id = win32print.StartDocPrinter(handle, 1, ("GK420D Identity", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, command)
            time.sleep(0.2)
            early = _read_printer(win32print, handle)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
        chunks = [early] if early else []
        deadline = time.time() + 1.5
        while time.time() < deadline:
            piece = _read_printer(win32print, handle)
            if piece:
                chunks.append(piece)
                break
            time.sleep(0.1)
        reply = _clean_reply(b"".join(chunks))
        delivered = _job_was_accepted(win32print, handle, job_id)
        return reply, delivered
    except Exception:
        return "", False
    finally:
        win32print.ClosePrinter(handle)


def _job_was_accepted(win32print, handle, job_id) -> bool:
    if not job_id:
        return False
    deadline = time.time() + 3.0
    saw_job = False
    while time.time() < deadline:
        try:
            job = win32print.GetJob(handle, job_id, 1)
        except Exception:
            return True
        saw_job = True
        status = int(job.get("Status") or 0)
        if status & (JOB_STATUS_ERROR | JOB_STATUS_OFFLINE | JOB_STATUS_PAPEROUT):
            return False
        if status & (JOB_STATUS_PRINTED | JOB_STATUS_DELETED):
            return True
        time.sleep(0.15)
    return saw_job


def _read_printer(win32print, handle) -> bytes:
    try:
        result = win32print.ReadPrinter(handle, 1024)
    except Exception:
        return b""
    if isinstance(result, tuple):
        data = result[1] if len(result) > 1 else result[0]
    else:
        data = result
    if isinstance(data, str):
        return data.encode("latin1", errors="ignore")
    return data or b""


def _query_port_file(port: str, command: bytes) -> str:
    cleaned = (port or "").rstrip(":").strip()
    if not cleaned or cleaned.upper().startswith("WSD") or cleaned.upper() == "NUL":
        return ""
    if _port_host(port):
        return ""
    try:
        import win32con
        import win32file
    except ImportError:
        return ""
    path = f"\\\\.\\{cleaned}"
    handle = None
    try:
        handle = win32file.CreateFile(
            path,
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0,
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )
        win32file.WriteFile(handle, command)
        time.sleep(0.25)
        _rc, data = win32file.ReadFile(handle, 1024)
        return _clean_reply(data)
    except Exception:
        return ""
    finally:
        if handle is not None:
            try:
                win32file.CloseHandle(handle)
            except Exception:
                pass


def _port_host(port: str) -> str | None:
    text = (port or "").strip()
    match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", text)
    if match:
        return match.group(1)
    return None


def _clean_reply(data: bytes) -> str:
    if not data:
        return ""
    text = data.decode("ascii", errors="ignore")
    text = text.replace("\x02", "").replace("\x03", "").replace("\x1e", "")
    text = " ".join(text.split())
    if not text or text.startswith("Microsoft"):
        return ""
    return text[:200]


def _parse_hi(identity: str) -> tuple[str, str]:
    parts = [part.strip() for part in identity.split(",") if part.strip()]
    if len(parts) >= 2 and parts[1][:1] in {"V", "v"}:
        return parts[0], parts[1]
    if identity and " " not in identity and len(identity) < 40:
        return identity, ""
    return parts[0] if parts else identity, parts[1] if len(parts) > 1 else ""


def _win32print():
    try:
        import win32print
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is required to talk to Windows printers. "
            "Install dependencies with run.bat or pip install -r requirements.txt."
        ) from exc
    return win32print
