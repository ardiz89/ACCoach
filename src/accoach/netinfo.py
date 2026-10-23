"""Network helpers for LAN access.

When the LAN toggle is on (see :class:`~accoach.config.Config`), the web and
live servers bind ``0.0.0.0`` so a phone or tablet on the same network can open
the report and engineer pages — handy on a triple-monitor setup. These helpers
find the machine's LAN IP, build the device-facing URLs, and render a QR code so
the phone can just scan instead of typing the address. All offline, no CDN.
"""

from __future__ import annotations

import socket
from urllib.parse import quote


def lan_ip() -> str | None:
    """Best-effort LAN IP that other devices use to reach this machine.

    Opens a UDP socket toward a public address and reads the local endpoint the
    OS picks for the default route. No packet is actually sent, so it works
    offline too. Returns ``None`` if no usable (non-loopback) interface is found.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except OSError:
        return None
    if ip and not ip.startswith("127."):
        return ip
    return None


def local_addresses() -> set[str]:
    """Gli indirizzi con cui questo PC si presenta a se stesso.

    Serve a `/health` per distinguere il report aperto sul PC del pilota da un
    tablet: un client il cui indirizzo e' uno di questi non e' un altro
    dispositivo (nemmeno quando entra dall'IP di rete del PC). Best-effort: un
    nome che non si risolve non deve mai far cadere `/health`.
    """
    out = {"127.0.0.1", "::1"}
    ip = lan_ip()
    if ip:
        out.add(ip)
    try:
        out.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except Exception:  # noqa: BLE001 - best-effort, mai eccezioni
        pass
    return out


def device_urls(port: int, ip: str | None = None,
                key: str | None = None) -> dict[str, str] | None:
    """Report + engineer + tablet + on-track test URLs a LAN device opens, or ``None`` if
    no LAN IP.

    Pass ``ip`` to skip auto-detection (useful for tests). Con ``key`` ogni URL
    finisce con ``?k=<key>``: il guardiano (`accoach.guard`) non fa entrare un
    dispositivo in rete senza la chiave, e il QR e' l'unico modo in cui il
    tablet la riceve. Alla prima pagina il guardiano la mette in un cookie.
    """
    ip = ip if ip is not None else lan_ip()
    if not ip:
        return None
    base = f"http://{ip}:{port}"
    tail = f"?k={quote(key, safe='')}" if key else ""
    return {"report": base + "/" + tail, "engineer": base + "/engineer" + tail,
            "tablet": base + "/tablet" + tail, "test": base + "/test" + tail}


def display_address(url: str) -> str:
    """L'URL di un QR come si legge sotto il codice: la chiave su una riga sua.

    L'iPad del pilota (iOS 9.3.6) non legge i QR, quindi l'indirizzo si scrive a
    mano ed e' la strada principale. Un URL non ha spazi e una QLabel non lo
    manda a capo: con la chiave in coda usciva dalla colonna. Si spezza prima
    di ``?k=``, che resta in vista e dice che la riga continua.
    """
    base, sep, tail = url.partition("?")
    return f"{base}\n?{tail}" if sep else url


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """True if something is listening on ``host:port``.

    The QR codes are built from the config, so they look ready even when no
    server is behind them — scanning one then yields a page that never loads.
    The launcher polls this to say so out loud. Probing the port (rather than
    tracking the child process) also sees servers started outside the hub.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def qr_png(data: str, scale: int = 6) -> bytes | None:
    """PNG bytes of a QR code for ``data``, or ``None`` if segno is unavailable.

    The launcher renders this into the QR dialog; callers degrade to showing the
    plain URL when this returns ``None``.
    """
    try:
        import segno
    except ImportError:
        return None
    import io

    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=2)
    return buf.getvalue()
