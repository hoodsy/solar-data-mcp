"""F1: the sync_* download guard — only the dataset's official https host, and
only public addresses (no SSRF to internal/metadata endpoints)."""

import socket

import pytest
from solar_mcp_core import net
from solar_mcp_core.config import TRACKING_THE_SUN
from solar_mcp_core.errors import BadInput


def _fake_getaddrinfo(ip: str) -> object:
    def inner(host: str, port: int, *args: object, **kwargs: object) -> list[object]:
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]

    return inner


def test_rejects_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("solar_mcp_core.net.socket.getaddrinfo", _fake_getaddrinfo("128.3.0.1"))
    with pytest.raises(BadInput, match="https"):
        net.assert_allowed_download_url("http://emp.lbl.gov/tts.csv", TRACKING_THE_SUN)


def test_rejects_non_official_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("solar_mcp_core.net.socket.getaddrinfo", _fake_getaddrinfo("128.3.0.1"))
    with pytest.raises(BadInput, match="official host"):
        net.assert_allowed_download_url("https://attacker.example/tts.csv", TRACKING_THE_SUN)


@pytest.mark.parametrize(
    "ip",
    ["169.254.169.254", "127.0.0.1", "10.0.0.5", "192.168.1.1", "0.0.0.0"],
)
def test_rejects_non_routable_address(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    # Even the official host is refused if it resolves to an internal address
    # (DNS-rebinding / misconfiguration backstop). 169.254.169.254 = cloud metadata.
    monkeypatch.setattr("solar_mcp_core.net.socket.getaddrinfo", _fake_getaddrinfo(ip))
    with pytest.raises(BadInput):
        net.assert_allowed_download_url("https://emp.lbl.gov/tts.csv", TRACKING_THE_SUN)


def test_accepts_official_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("solar_mcp_core.net.socket.getaddrinfo", _fake_getaddrinfo("128.3.0.1"))
    net.assert_allowed_download_url("https://emp.lbl.gov/tracking_the_sun.csv", TRACKING_THE_SUN)
