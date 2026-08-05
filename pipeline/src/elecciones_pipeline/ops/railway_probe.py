"""Bounded Railway egress probes followed by an idle private worker.

This module has no listener, URL parameter, crawl command, or document logic.
It can contact only the reviewed Registraduría configuration and the four
allowlisted historical-result archives, using one GET and metadata-only HEADs.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import signal
import socket
import threading
import time
from collections.abc import Callable

OFFICIAL_HOST = "resultadosprecpresidente2026-2v.registraduria.gov.co"
OFFICIAL_PATH = "/json/web/config.json"
EXPECTED_STATUS = 200
EXPECTED_CONTENT_TYPE = "application/json"
EXPECTED_BYTE_SIZE = 931
EXPECTED_SHA256 = "6cf56876f26e690bce28ba4d19d190f0fe6f67e5b68c2d2bbf064ac5d3d7ab5f"
MAX_RESPONSE_BYTES = 16_384
USER_AGENT = "EleccionesAbiertasColombia/0.1 controlled-egress-probe"

HISTORICAL_HOST = "observatorio.registraduria.gov.co"
HISTORICAL_ARCHIVES = (
    (
        "registraduria-mmv-president-2022-r1",
        "/anexos/MMV_NACIONAL_PRESIDENTE_2022_1v.zip",
    ),
    (
        "registraduria-mmv-president-2022-r2",
        "/anexos/MMV_NACIONAL_PRESIDENTE_2022_2v.zip",
    ),
    (
        "registraduria-mmv-president-2018-r1",
        "/anexos/MMV_NACIONAL_PRESIDENTE_2018_1v.zip",
    ),
    (
        "registraduria-mmv-president-2018-r2",
        "/anexos/MMV_NACIONAL_PRESIDENTE_2018_2v.zip",
    ),
)
HISTORICAL_REQUEST_INTERVAL_SECONDS = 0.5


class ProbeError(RuntimeError):
    """The single reviewed source did not match its immutable expectation."""


def _public_addresses(host: str) -> tuple[str, ...]:
    addresses = {
        item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM) if item[4]
    }
    if not addresses:
        raise ProbeError("official host resolved to no address")
    parsed = tuple(ipaddress.ip_address(address) for address in sorted(addresses))
    if any(not address.is_global for address in parsed):
        raise ProbeError("official host resolved to a non-public address")
    return tuple(str(address) for address in parsed)


def probe_once(
    *,
    resolver: Callable[[str], tuple[str, ...]] = _public_addresses,
    connection_factory: Callable[..., http.client.HTTPSConnection] = http.client.HTTPSConnection,
) -> dict[str, object]:
    """Issue exactly one GET and validate status, media type, size, and hash."""
    resolved_addresses = resolver(OFFICIAL_HOST)
    if not resolved_addresses:
        raise ProbeError("official host resolved to no address")
    connection = connection_factory(OFFICIAL_HOST, 443, timeout=15)
    try:
        connection.request(
            "GET",
            OFFICIAL_PATH,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip()
        result = {
            "byte_size": len(body),
            "content_type": content_type,
            "sha256": hashlib.sha256(body).hexdigest(),
            "status": response.status,
            "target_id": "registraduria-precount-configuration-2026-r2",
        }
    finally:
        connection.close()
    expected = {
        "byte_size": EXPECTED_BYTE_SIZE,
        "content_type": EXPECTED_CONTENT_TYPE,
        "sha256": EXPECTED_SHA256,
        "status": EXPECTED_STATUS,
    }
    observed = {key: result[key] for key in expected}
    if observed != expected:
        raise ProbeError("official configuration did not match its reviewed status/type/size/hash")
    return result


def probe_historical_archives(
    *,
    resolver: Callable[[str], tuple[str, ...]] = _public_addresses,
    connection_factory: Callable[..., http.client.HTTPSConnection] = http.client.HTTPSConnection,
    pause: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    """Read headers only for the four fixed historical-result archives."""
    resolved_addresses = resolver(HISTORICAL_HOST)
    if not resolved_addresses:
        raise ProbeError("historical host resolved to no address")

    request_issued = False

    def request_metadata(
        *, target_id: str, path: str, method: str, headers: dict[str, str]
    ) -> dict[str, object]:
        nonlocal request_issued
        if request_issued:
            pause(HISTORICAL_REQUEST_INTERVAL_SECONDS)
        request_issued = True
        connection = connection_factory(HISTORICAL_HOST, 443, timeout=15)
        try:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            content_length_header = response.getheader("Content-Length")
            try:
                content_length = (
                    int(content_length_header) if content_length_header is not None else None
                )
            except ValueError as exc:
                raise ProbeError("historical archive returned an invalid content length") from exc
            if content_length is not None and content_length < 0:
                raise ProbeError("historical archive returned a negative content length")
            content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip()
            content_range = response.getheader("Content-Range")
            body_bytes_read = len(response.read(2)) if method == "GET" else 0
            resource_length = content_length
            if method == "GET" and content_range:
                range_total = content_range.rsplit("/", 1)[-1]
                resource_length = int(range_total) if range_total.isdigit() else None
            return {
                "body_bytes_read": body_bytes_read,
                "content_length": content_length,
                "content_range": content_range,
                "content_type": content_type or None,
                "etag": response.getheader("ETag"),
                "last_modified": response.getheader("Last-Modified"),
                "method": "GET_RANGE" if method == "GET" else method,
                "range_honored": method == "GET"
                and response.status == 206
                and content_range is not None,
                "resource_length": resource_length,
                "status": response.status,
                "target_id": target_id,
            }
        finally:
            connection.close()

    results: list[dict[str, object]] = []
    for target_id, path in HISTORICAL_ARCHIVES:
        headers = {
            "Accept": "application/zip, application/octet-stream;q=0.9",
            "User-Agent": USER_AGENT,
        }
        result = request_metadata(
            target_id=target_id,
            path=path,
            method="HEAD",
            headers=headers,
        )
        head_status = result["status"]
        if not isinstance(head_status, int):
            raise ProbeError("historical archive returned an invalid status")
        if not 200 <= head_status < 300:
            result = request_metadata(
                target_id=target_id,
                path=path,
                method="GET",
                headers={**headers, "Range": "bytes=0-0"},
            )
            result["fallback_from_head_status"] = head_status
        results.append(result)
    return results


def main() -> int:
    try:
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
    try:
        historical_results = probe_historical_archives()
    except Exception as exc:  # noqa: BLE001 - bounded operational error boundary
        print(
            json.dumps(
                {"error": type(exc).__name__, "state": "historical_probe_failed"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        return 2
    for historical_result in historical_results:
        print(
            json.dumps(
                {"probe": historical_result, "state": "metadata_observed"},
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
    stop = threading.Event()

    def stop_worker(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, stop_worker)
    signal.signal(signal.SIGINT, stop_worker)
    print('{"state":"idle","crawl_started":false}', flush=True)
    while not stop.wait(3600):
        pass
    print('{"state":"stopped"}', flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
