"""Network helpers for LAN access.

When the LAN toggle is on (see :class:`~accoach.config.Config`), the web and
live servers bind ``0.0.0.0`` so a phone or tablet on the same network can open
the report and engineer pages — handy on a triple-monitor setup. These helpers
find the machine's LAN IP, build the device-facing URLs, and render a QR code so
the phone can just scan instead of typing the address. All offline, no CDN.
"""

from __future__ import annotations

import socket


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


def device_urls(port: int, ip: str | None = None) -> dict[str, str] | None:
    """Report + engineer + on-track test URLs a LAN device opens, or ``None`` if
    no LAN IP.

    Pass ``ip`` to skip auto-detection (useful for tests).
    """
    ip = ip if ip is not None else lan_ip()
    if not ip:
        return None
    base = f"http://{ip}:{port}"
    return {"report": base + "/", "engineer": base + "/engineer",
            "test": base + "/test"}


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
