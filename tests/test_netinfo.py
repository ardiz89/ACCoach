"""netinfo: LAN address, device URLs, and QR rendering for phone/tablet access."""
import socket

from accoach import netinfo


def test_device_urls_builds_report_and_engineer():
    urls = netinfo.device_urls(8778, ip="192.168.1.50")
    assert urls == {
        "report": "http://192.168.1.50:8778/",
        "engineer": "http://192.168.1.50:8778/engineer",
        "test": "http://192.168.1.50:8778/test",
    }


def test_device_urls_none_without_ip():
    assert netinfo.device_urls(8778, ip="") is None


def test_lan_ip_is_none_or_non_loopback():
    ip = netinfo.lan_ip()
    assert ip is None or not ip.startswith("127.")


def test_port_open_sees_a_listening_socket():
    # Bind port 0 to let the OS hand us a free one, so the test never collides
    # with a real HONE server (or a second test run) on 8777/8778.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert netinfo.port_open(port) is True
    # Closed again once the socket is out of scope.
    assert netinfo.port_open(port) is False


def test_qr_png_is_a_png_when_segno_present():
    png = netinfo.qr_png("http://192.168.1.50:8778/")
    # segno is a declared dependency, so we expect real PNG bytes here.
    assert png is not None
    assert png[:4] == b"\x89PNG"
