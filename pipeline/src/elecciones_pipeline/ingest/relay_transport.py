"""Strict local transport for the private Railway election-source relay."""

from __future__ import annotations

import re
import stat
from pathlib import Path
from urllib.parse import urlsplit

import httpx

_OFFICIAL_HOSTS = {
    "resultadosprecpresidente2026-1v.registraduria.gov.co": 1,
    "resultadosprecpresidente2026-2v.registraduria.gov.co": 2,
}
_ACT_PATH = re.compile(r"^/json/ACT/PR/([A-Za-z0-9]{2,32})\.json$")
_FORWARDED_HEADERS = ("If-None-Match", "If-Modified-Since")


class RelayTransportError(RuntimeError):
    """A caller attempted to escape the reviewed relay surface."""


def relay_path_for_official_url(url: str | httpx.URL) -> str:
    """Translate one reviewed official pre-count URL to a typed relay path."""
    parsed = urlsplit(str(url))
    try:
        port = parsed.port
    except ValueError as exc:
        raise RelayTransportError("official URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise RelayTransportError("official URL is not a canonical reviewed HTTPS resource")
    hostname = (parsed.hostname or "").lower()
    round_number = _OFFICIAL_HOSTS.get(hostname)
    if round_number is None:
        raise RelayTransportError("official URL host is not available through the relay")
    if parsed.path == "/json/web/config.json":
        return f"/v1/precount/{round_number}/configuration"
    if parsed.path == "/json/nomenclator.json":
        return f"/v1/precount/{round_number}/nomenclator"
    act_match = _ACT_PATH.fullmatch(parsed.path)
    if act_match:
        return f"/v1/precount/{round_number}/act/{act_match.group(1)}"
    raise RelayTransportError("official URL path is not available through the relay")


def validate_relay_base_url(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise RelayTransportError("relay base URL has an invalid port") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or port is None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RelayTransportError("relay base URL must be explicit loopback HTTP with a port")
    return f"http://127.0.0.1:{port}"


def load_relay_token(path: Path) -> str:
    """Read a small owner-only token file without accepting links or whitespace."""
    if path.is_symlink() or not path.is_file():
        raise RelayTransportError("relay token must be a regular non-symlink file")
    metadata = path.stat()
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RelayTransportError("relay token file must not grant group or other permissions")
    if not 32 <= metadata.st_size <= 512:
        raise RelayTransportError("relay token file has an invalid size")
    raw = path.read_text(encoding="ascii")
    token = raw.removesuffix("\n")
    if not 32 <= len(token) <= 256 or not token.isascii() or any(char.isspace() for char in token):
        raise RelayTransportError("relay token has an invalid format")
    return token


class PrecountRelayTransport(httpx.AsyncBaseTransport):
    """Route only reviewed 2026 pre-count GETs through a loopback relay."""

    def __init__(
        self,
        relay_base_url: str,
        token: str,
        *,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.relay_base_url = validate_relay_base_url(relay_base_url)
        if (
            not 32 <= len(token) <= 256
            or not token.isascii()
            or any(character.isspace() for character in token)
        ):
            raise RelayTransportError("relay token has an invalid format")
        self._authorization = f"Bearer {token}"
        self._inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise RelayTransportError("relay transport permits GET only")
        relay_path = relay_path_for_official_url(request.url)
        headers = {"Authorization": self._authorization}
        for name in _FORWARDED_HEADERS:
            if value := request.headers.get(name):
                headers[name] = value
        relay_request = httpx.Request(
            "GET",
            f"{self.relay_base_url}{relay_path}",
            headers=headers,
        )
        return await self._inner.handle_async_request(relay_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


__all__ = [
    "PrecountRelayTransport",
    "RelayTransportError",
    "load_relay_token",
    "relay_path_for_official_url",
    "validate_relay_base_url",
]
