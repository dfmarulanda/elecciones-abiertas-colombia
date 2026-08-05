"""Private, loopback-only relay for reviewed official election sources.

The relay is reachable only through Railway SSH port forwarding.  It accepts
typed resource identities, never caller-supplied URLs, and cannot address
documents or PDFs.  It exists solely to let the local resumable collector keep
using its local immutable objects and SQLite checkpoints when the local network
cannot reach the reviewed official JSON hosts.
"""

from __future__ import annotations

import hmac
import http.client
import ipaddress
import json
import math
import os
import re
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .railway_probe import USER_AGENT, _public_addresses, probe_once

RELAY_BIND = "127.0.0.1"
RELAY_PORT = 8787
# These limits are intentionally per official origin.  Rounds one and two use
# different reviewed hosts, so a global semaphore would needlessly serialize
# them while not adding protection for either origin.
MAX_CONNECTIONS_PER_HOST = 2
DEFAULT_REQUESTS_PER_SECOND = 2.0
REQUESTS_PER_SECOND_ENV = "COLLECTOR_RELAY_REQUESTS_PER_SECOND"
MIN_TOKEN_LENGTH = 32

_PRECOUNT_HOSTS = {
    1: "resultadosprecpresidente2026-1v.registraduria.gov.co",
    2: "resultadosprecpresidente2026-2v.registraduria.gov.co",
}
_HISTORICAL_PATHS = {
    (2018, 1): "/anexos/MMV_NACIONAL_PRESIDENTE_2018_1v.zip",
    (2018, 2): "/anexos/MMV_NACIONAL_PRESIDENTE_2018_2v.zip",
    (2022, 1): "/anexos/MMV_NACIONAL_PRESIDENTE_2022_1v.zip",
    (2022, 2): "/anexos/MMV_NACIONAL_PRESIDENTE_2022_2v.zip",
}
_HISTORICAL_HOST = "observatorio.registraduria.gov.co"
_PRECOUNT_ROOT = re.compile(r"^/v1/precount/([12])/(configuration|nomenclator)$")
_PRECOUNT_ACT = re.compile(r"^/v1/precount/([12])/act/([A-Za-z0-9]{2,32})$")
_HISTORICAL = re.compile(r"^/v1/history/(2018|2022)/([12])$")
_CONTENT_RANGE = re.compile(r"^bytes 0-0/[1-9][0-9]*$")


class RelayError(RuntimeError):
    """The request violated relay policy or the upstream response was unsafe."""


def _validated_requests_per_second(value: float) -> float:
    if not math.isfinite(value) or not 2.0 <= value <= 5.0:
        raise RelayError("per-host request rate must be a finite value in [2, 5]")
    return value


def requests_per_second_from_environment(
    environment: dict[str, str] | None = None,
) -> float:
    """Read the one bounded operational tuning knob without weakening defaults."""
    source = os.environ if environment is None else environment
    raw = source.get(
        REQUESTS_PER_SECOND_ENV, str(DEFAULT_REQUESTS_PER_SECOND)
    )
    try:
        return _validated_requests_per_second(float(raw))
    except (TypeError, ValueError) as exc:
        raise RelayError("per-host request rate must be numeric") from exc


@dataclass(frozen=True)
class RelayTarget:
    target_id: str
    host: str
    path: str
    accept: str
    allowed_content_types: frozenset[str]
    max_body_bytes: int
    permits_full_download: bool


@dataclass(frozen=True)
class RelayResponse:
    status: int
    headers: dict[str, str]
    body: bytes


def resolve_target(path: str) -> RelayTarget:
    """Map one typed local path to one reviewed, hardcoded official URL."""
    if "%" in path or "?" in path or "#" in path:
        raise RelayError("encoded paths, query strings, and fragments are forbidden")
    root_match = _PRECOUNT_ROOT.fullmatch(path)
    if root_match:
        round_number = int(root_match.group(1))
        kind = root_match.group(2)
        official_path = (
            "/json/web/config.json" if kind == "configuration" else "/json/nomenclator.json"
        )
        max_body = 64 * 1024 if kind == "configuration" else 32 * 1024 * 1024
        return RelayTarget(
            target_id=f"precount-2026-r{round_number}-{kind}",
            host=_PRECOUNT_HOSTS[round_number],
            path=official_path,
            accept="application/json",
            allowed_content_types=frozenset({"application/json"}),
            max_body_bytes=max_body,
            permits_full_download=True,
        )
    act_match = _PRECOUNT_ACT.fullmatch(path)
    if act_match:
        round_number = int(act_match.group(1))
        scope = act_match.group(2)
        return RelayTarget(
            target_id=f"precount-2026-r{round_number}-act",
            host=_PRECOUNT_HOSTS[round_number],
            path=f"/json/ACT/PR/{scope}.json",
            accept="application/json",
            allowed_content_types=frozenset({"application/json"}),
            max_body_bytes=1024 * 1024,
            permits_full_download=True,
        )
    historical_match = _HISTORICAL.fullmatch(path)
    if historical_match:
        year, round_number = int(historical_match.group(1)), int(historical_match.group(2))
        return RelayTarget(
            target_id=f"historical-mmv-{year}-r{round_number}",
            host=_HISTORICAL_HOST,
            path=_HISTORICAL_PATHS[(year, round_number)],
            accept="application/zip",
            allowed_content_types=frozenset({"application/zip"}),
            max_body_bytes=70 * 1024 * 1024,
            permits_full_download=True,
        )
    raise RelayError("resource identity is not allowlisted")


class _HostRateLimit:
    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._requests_per_second = _validated_requests_per_second(requests_per_second)
        self._next_request_at = 0.0
        self._lock = threading.Lock()
        self._clock = clock
        self._sleep = sleep

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + 1 / self._requests_per_second
        if delay:
            self._sleep(delay)


@dataclass
class _HostLimit:
    connections: threading.BoundedSemaphore
    rate: _HostRateLimit


class OfficialRelay:
    """Bounded official fetcher shared by the loopback HTTP handler."""

    def __init__(
        self,
        *,
        resolver: Callable[[str], tuple[str, ...]] = _public_addresses,
        connection_factory: Callable[..., http.client.HTTPSConnection] = (
            http.client.HTTPSConnection
        ),
        requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._resolver = resolver
        self._connection_factory = connection_factory
        self._requests_per_second = _validated_requests_per_second(requests_per_second)
        self._clock = clock
        self._sleep = sleep
        self._host_limits: dict[str, _HostLimit] = {}
        self._host_limits_lock = threading.Lock()

    def _host_limit(self, host: str) -> _HostLimit:
        with self._host_limits_lock:
            return self._host_limits.setdefault(
                host,
                _HostLimit(
                    connections=threading.BoundedSemaphore(MAX_CONNECTIONS_PER_HOST),
                    rate=_HostRateLimit(
                        self._requests_per_second, clock=self._clock, sleep=self._sleep
                    ),
                ),
            )

    def fetch(
        self,
        target: RelayTarget,
        *,
        if_none_match: str | None = None,
        if_modified_since: str | None = None,
        range_probe: bool = False,
    ) -> RelayResponse:
        addresses = self._resolver(target.host)
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise RelayError("official host did not resolve exclusively to public addresses")
        headers = {
            "Accept": target.accept,
            "Accept-Encoding": "identity",
            "User-Agent": USER_AGENT,
        }
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        if if_modified_since:
            headers["If-Modified-Since"] = if_modified_since
        if range_probe:
            headers["Range"] = "bytes=0-0"

        host_limit = self._host_limit(target.host)
        with host_limit.connections:
            host_limit.rate.wait()
            connection = self._connection_factory(target.host, 443, timeout=60)
            try:
                connection.request("GET", target.path, headers=headers)
                response = connection.getresponse()
                if response.status == 304:
                    response_headers = {
                        name: value
                        for name in ("ETag", "Last-Modified")
                        if (value := response.getheader(name)) is not None
                    }
                    return RelayResponse(status=304, headers=response_headers, body=b"")
                if 300 <= response.status < 400:
                    raise RelayError("official redirects are never followed by the relay")
                response_headers = {
                    name: value
                    for name in (
                        "Content-Type",
                        "ETag",
                        "Last-Modified",
                        "Retry-After",
                        "Content-Range",
                    )
                    if (value := response.getheader(name)) is not None
                }
                if not 200 <= response.status < 300:
                    return RelayResponse(status=response.status, headers=response_headers, body=b"")

                content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip()
                if content_type not in target.allowed_content_types:
                    raise RelayError(
                        "official response content type is not allowed for this resource"
                    )
                length_header = response.getheader("Content-Length")
                if length_header is None or not length_header.isdigit():
                    raise RelayError("official response needs a valid Content-Length")
                content_length = int(length_header)
                if content_length > target.max_body_bytes:
                    raise RelayError("official response exceeds the resource body cap")
                if range_probe:
                    content_range = response.getheader("Content-Range") or ""
                    if (
                        response.status != 206
                        or content_length != 1
                        or _CONTENT_RANGE.fullmatch(content_range) is None
                    ):
                        raise RelayError("official source ignored or malformed the one-byte range")
                    body = response.read(2)
                    if len(body) != 1:
                        raise RelayError("one-byte range returned an unexpected body size")
                else:
                    body = response.read(target.max_body_bytes + 1)
                    if len(body) > target.max_body_bytes:
                        raise RelayError("official response exceeded the resource body cap")
                    if len(body) != content_length:
                        raise RelayError("official response length did not match Content-Length")
                response_headers["Content-Type"] = content_type
                response_headers["Content-Length"] = str(len(body))
                return RelayResponse(status=response.status, headers=response_headers, body=body)
            finally:
                connection.close()


class RelayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, token: str, relay: OfficialRelay):
        self.token = token
        self.relay = relay
        self.request_count = 0
        self.request_count_lock = threading.Lock()
        super().__init__((RELAY_BIND, RELAY_PORT), RelayRequestHandler)


def _write_client_body(stream: object, body: bytes) -> bool:
    """Write a completed upstream response without treating a dropped client as upstream failure."""
    try:
        # ``wfile`` is deliberately structural here to keep this boundary easy
        # to exercise without opening a real listener in tests.
        stream.write(body)  # type: ignore[attr-defined]
    except (BrokenPipeError, ConnectionResetError):
        return False
    return True


class RelayRequestHandler(BaseHTTPRequestHandler):
    server: RelayHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json_error(self, status: int, code: str) -> None:
        body = json.dumps({"error": code}, separators=(",", ":"), sort_keys=True).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return
        _write_client_body(self.wfile, body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.token}"
        if not hmac.compare_digest(supplied, expected):
            self._json_error(401, "unauthorized")
            return
        try:
            target = resolve_target(self.path)
            range_header = self.headers.get("Range")
            if range_header is not None and range_header != "bytes=0-0":
                raise RelayError("only the one-byte metadata range is permitted")
            result = self.server.relay.fetch(
                target,
                if_none_match=self.headers.get("If-None-Match"),
                if_modified_since=self.headers.get("If-Modified-Since"),
                range_probe=range_header is not None,
            )
        except RelayError:
            self._json_error(502, "relay_policy_or_upstream_validation_failed")
            return

        try:
            self.send_response(result.status)
            for name, value in result.headers.items():
                self.send_header(name, value)
            if "Content-Length" not in result.headers:
                self.send_header("Content-Length", str(len(result.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            return
        if result.body and not _write_client_body(self.wfile, result.body):
            return

        with self.server.request_count_lock:
            self.server.request_count += 1
            request_count = self.server.request_count
        if request_count <= 5 or request_count % 1000 == 0 or result.status >= 400:
            print(
                json.dumps(
                    {
                        "bytes": len(result.body),
                        "request_count": request_count,
                        "state": "relay_request",
                        "status": result.status,
                        "target_id": target.target_id,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                flush=True,
            )


def main() -> int:
    token = os.environ.get("COLLECTOR_RELAY_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH:
        print('{"state":"relay_configuration_error"}', flush=True)
        return 2
    try:
        requests_per_second = requests_per_second_from_environment()
        result = probe_once()
    except Exception as exc:  # noqa: BLE001 - bounded operational error boundary
        print(
            json.dumps(
                {"error": type(exc).__name__, "state": "probe_failed"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    print(
        json.dumps({"probe": result, "state": "verified"}, separators=(",", ":"), sort_keys=True),
        flush=True,
    )
    server = RelayHTTPServer(token, OfficialRelay(requests_per_second=requests_per_second))

    def stop_server(_signum: int, _frame: object) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    print(
        json.dumps(
            {
                "bind": RELAY_BIND,
                "crawl_started": False,
                "per_host_requests_per_second": requests_per_second,
                "port": RELAY_PORT,
                "public_listener": False,
                "state": "relay_ready",
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
        flush=True,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
    print('{"state":"stopped"}', flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
