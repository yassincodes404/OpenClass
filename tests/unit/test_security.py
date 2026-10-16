"""Pin DNS results at the actual transport boundary, preserving TLS identity."""

import socket

import httpx
import pytest
from openclass_server.security import PublicHTTPTransport


async def test_transport_pins_public_ip_and_preserves_host_and_sni(monkeypatch):
    calls = []
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    async def send(self, request):
        calls.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    async with httpx.AsyncClient(transport=PublicHTTPTransport()) as client:
        result = await client.get("https://public.example/path")
    assert result.text == "ok"
    assert calls[0].url.host == "93.184.216.34"
    assert calls[0].headers["host"] == "public.example"
    assert calls[0].extensions["sni_hostname"] == "public.example"


async def test_rebinding_private_address_is_rejected_before_connect(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    async with httpx.AsyncClient(transport=PublicHTTPTransport()) as client:
        with pytest.raises(ValueError, match="loopback"):
            await client.get("https://public.example")


@pytest.mark.parametrize(
    "addresses",
    [
        ["93.184.216.34", "10.0.0.1"],
        ["169.254.169.254"],
        ["100.64.0.1"],
        ["::ffff:127.0.0.1"],
    ],
)
async def test_all_dns_answers_must_be_public(monkeypatch, addresses):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses
        ],
    )

    async def forbidden(self, request):
        pytest.fail("A mixed/private DNS answer must never open a connection")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    async with httpx.AsyncClient(transport=PublicHTTPTransport()) as client:
        with pytest.raises(ValueError):
            await client.get("https://public.example")


async def test_each_dispatch_resolves_again_without_reusing_validated_hostname(monkeypatch):
    addresses = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(addresses), 443))],
    )
    calls = []

    async def send(self, request):
        calls.append(request)
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    async with httpx.AsyncClient(transport=PublicHTTPTransport()) as client:
        assert (await client.get("https://public.example")).status_code == 200
        with pytest.raises(ValueError):
            await client.get("https://public.example")
    assert len(calls) == 1
