from __future__ import annotations

import hashlib

import pytest
from elecciones_pipeline.ops.railway_probe import (
    EXPECTED_BYTE_SIZE,
    EXPECTED_SHA256,
    HISTORICAL_ARCHIVES,
    HISTORICAL_REQUEST_INTERVAL_SECONDS,
    OFFICIAL_PATH,
    ProbeError,
    probe_historical_archives,
    probe_once,
)


class _Response:
    def __init__(
        self,
        body: bytes = b"",
        content_type: str = "application/json; charset=utf-8",
        *,
        headers: dict[str, str] | None = None,
        status: int = 200,
    ):
        self._body = body
        self._headers = {"Content-Type": content_type, **(headers or {})}
        self.status = status
        self.read_called = False

    def read(self, _limit: int) -> bytes:
        self.read_called = True
        return self._body

    def getheader(self, name: str) -> str | None:
        return self._headers.get(name)


class _Connection:
    def __init__(self, response: _Response):
        self.response = response
        self.requests: list[tuple[str, str]] = []
        self.request_headers: list[dict[str, str]] = []
        self.closed = False

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, path))
        self.request_headers.append(headers)

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_probe_makes_one_fixed_request_and_matches_reviewed_identity() -> None:
    # The production fixture is represented only by its immutable properties;
    # this test does not duplicate or fabricate official bytes.
    body = b"x" * EXPECTED_BYTE_SIZE
    connection = _Connection(_Response(body))

    with pytest.raises(ProbeError, match="did not match"):
        probe_once(
            resolver=lambda _host: ("8.8.8.8",),
            connection_factory=lambda *_args, **_kwargs: connection,  # type: ignore[arg-type]
        )

    assert connection.requests == [("GET", OFFICIAL_PATH)]
    assert connection.request_headers == [
        {
            "Accept": "application/json",
            "User-Agent": "EleccionesAbiertasColombia/0.1 controlled-egress-probe",
        }
    ]
    assert connection.closed
    assert hashlib.sha256(body).hexdigest() != EXPECTED_SHA256


def test_probe_rejects_empty_resolution_before_connecting() -> None:
    with pytest.raises(ProbeError, match="resolved to no address"):
        probe_once(
            resolver=lambda _host: (),
            connection_factory=lambda *_args, **_kwargs: pytest.fail("must not connect"),
        )


def test_historical_probe_uses_only_head_at_two_requests_per_second() -> None:
    responses = [
        _Response(
            content_type="application/zip",
            headers={
                "Content-Length": str(1_000 + index),
                "ETag": f'"etag-{index}"',
                "Last-Modified": "Mon, 04 Aug 2026 12:00:00 GMT",
            },
        )
        for index in range(len(HISTORICAL_ARCHIVES))
    ]
    connections = [_Connection(response) for response in responses]
    connection_iterator = iter(connections)
    pauses: list[float] = []

    results = probe_historical_archives(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: next(connection_iterator),  # type: ignore[arg-type]
        pause=pauses.append,
    )

    assert [connection.requests for connection in connections] == [
        [("HEAD", path)] for _target_id, path in HISTORICAL_ARCHIVES
    ]
    assert all(connection.closed for connection in connections)
    assert all(not response.read_called for response in responses)
    assert all(
        connection.request_headers
        == [
            {
                "Accept": "application/zip, application/octet-stream;q=0.9",
                "User-Agent": "EleccionesAbiertasColombia/0.1 controlled-egress-probe",
            }
        ]
        for connection in connections
    )
    assert pauses == [
        HISTORICAL_REQUEST_INTERVAL_SECONDS,
        HISTORICAL_REQUEST_INTERVAL_SECONDS,
        HISTORICAL_REQUEST_INTERVAL_SECONDS,
    ]
    assert [result["content_length"] for result in results] == [1000, 1001, 1002, 1003]
    assert [result["method"] for result in results] == ["HEAD"] * 4


def test_historical_probe_falls_back_to_one_byte_range_without_full_download() -> None:
    responses: list[_Response] = []
    for index in range(len(HISTORICAL_ARCHIVES)):
        responses.extend(
            [
                _Response(
                    content_type="text/html",
                    headers={"Content-Length": "66755"},
                    status=500,
                ),
                _Response(
                    body=b"P",
                    content_type="application/zip",
                    headers={
                        "Content-Length": "1",
                        "Content-Range": f"bytes 0-0/{5_000_000 + index}",
                        "ETag": f'"etag-{index}"',
                        "Last-Modified": "Mon, 04 Aug 2026 12:00:00 GMT",
                    },
                    status=206,
                ),
            ]
        )
    connections = [_Connection(response) for response in responses]
    connection_iterator = iter(connections)
    pauses: list[float] = []

    results = probe_historical_archives(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: next(connection_iterator),  # type: ignore[arg-type]
        pause=pauses.append,
    )

    assert [connection.requests[0][0] for connection in connections] == [
        "HEAD",
        "GET",
        "HEAD",
        "GET",
        "HEAD",
        "GET",
        "HEAD",
        "GET",
    ]
    assert all(
        connection.request_headers[0].get("Range") == "bytes=0-0"
        for connection in connections[1::2]
    )
    assert all(not response.read_called for response in responses[::2])
    assert all(response.read_called for response in responses[1::2])
    assert all(connection.closed for connection in connections)
    assert pauses == [HISTORICAL_REQUEST_INTERVAL_SECONDS] * 7
    assert [result["status"] for result in results] == [206] * 4
    assert [result["fallback_from_head_status"] for result in results] == [500] * 4
    assert [result["body_bytes_read"] for result in results] == [1] * 4
    assert [result["resource_length"] for result in results] == [
        5_000_000,
        5_000_001,
        5_000_002,
        5_000_003,
    ]
    assert all(result["range_honored"] for result in results)
