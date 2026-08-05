from __future__ import annotations

import threading

import pytest
from elecciones_pipeline.ops.railway_relay import (
    OfficialRelay,
    RelayError,
    _write_client_body,
    requests_per_second_from_environment,
    resolve_target,
)


class _Response:
    def __init__(self, *, status: int, headers: dict[str, str], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body
        self.read_limits: list[int] = []

    def getheader(self, name: str) -> str | None:
        return self.headers.get(name)

    def read(self, limit: int) -> bytes:
        self.read_limits.append(limit)
        return self.body[:limit]


class _Connection:
    def __init__(self, response: _Response):
        self.response = response
        self.requests: list[tuple[str, str, dict[str, str]]] = []
        self.closed = False

    def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
        self.requests.append((method, path, headers))

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_typed_routes_never_accept_caller_supplied_urls_or_documents() -> None:
    target = resolve_target("/v1/precount/2/act/00123456789012345")
    assert target.host == "resultadosprecpresidente2026-2v.registraduria.gov.co"
    assert target.path == "/json/ACT/PR/00123456789012345.json"

    historical = resolve_target("/v1/history/2018/1")
    assert historical.host == "observatorio.registraduria.gov.co"
    assert historical.path == "/anexos/MMV_NACIONAL_PRESIDENTE_2018_1v.zip"

    for forbidden in (
        "https://example.com/file.json",
        "/v1/precount/2/act/../secret",
        "/v1/precount/2/act/00.pdf",
        "/v1/precount/2/act/00?url=https://example.com",
        "/v1/history/2020/1",
        "/v1/history/2018/1.pdf",
    ):
        with pytest.raises(RelayError, match="allowlisted|forbidden"):
            resolve_target(forbidden)


def test_range_probe_reads_exactly_one_byte_and_forwards_no_arbitrary_headers() -> None:
    response = _Response(
        status=206,
        headers={
            "Content-Length": "1",
            "Content-Range": "bytes 0-0/61121207",
            "Content-Type": "application/zip",
            "ETag": '"reviewed"',
        },
        body=b"P",
    )
    connection = _Connection(response)
    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: connection,  # type: ignore[arg-type]
    )

    result = relay.fetch(resolve_target("/v1/history/2018/1"), range_probe=True)

    assert result.status == 206
    assert result.body == b"P"
    assert response.read_limits == [2]
    assert connection.closed
    assert connection.requests == [
        (
            "GET",
            "/anexos/MMV_NACIONAL_PRESIDENTE_2018_1v.zip",
            {
                "Accept": "application/zip",
                "Accept-Encoding": "identity",
                "Range": "bytes=0-0",
                "User-Agent": "EleccionesAbiertasColombia/0.1 controlled-egress-probe",
            },
        )
    ]


def test_range_probe_rejects_ignored_range_without_downloading_body() -> None:
    response = _Response(
        status=200,
        headers={
            "Content-Length": "61121207",
            "Content-Type": "application/zip",
        },
        body=b"this body must not be read",
    )
    connection = _Connection(response)
    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: connection,  # type: ignore[arg-type]
    )

    with pytest.raises(RelayError, match="ignored or malformed"):
        relay.fetch(resolve_target("/v1/history/2018/1"), range_probe=True)

    assert response.read_limits == []
    assert connection.closed


def test_json_response_type_and_size_are_fail_closed() -> None:
    response = _Response(
        status=200,
        headers={"Content-Length": "20", "Content-Type": "application/pdf"},
        body=b"%PDF-not-permitted",
    )
    connection = _Connection(response)
    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: connection,  # type: ignore[arg-type]
    )

    with pytest.raises(RelayError, match="content type"):
        relay.fetch(resolve_target("/v1/precount/2/configuration"))

    assert response.read_limits == []
    assert connection.closed


def test_conditional_not_modified_is_not_misclassified_as_a_redirect() -> None:
    response = _Response(
        status=304,
        headers={"ETag": '"unchanged"'},
        body=b"must not be read",
    )
    connection = _Connection(response)
    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: connection,  # type: ignore[arg-type]
    )

    result = relay.fetch(
        resolve_target("/v1/precount/2/act/00123456789012345"),
        if_none_match='"unchanged"',
    )

    assert result.status == 304
    assert result.body == b""
    assert result.headers == {"ETag": '"unchanged"'}
    assert response.read_limits == []
    assert connection.closed


@pytest.mark.parametrize("value", ("1.99", "5.01", "nan", "infinity", "not-a-rate"))
def test_rate_environment_is_strictly_bounded(value: str) -> None:
    with pytest.raises(RelayError):
        requests_per_second_from_environment({"COLLECTOR_RELAY_REQUESTS_PER_SECOND": value})


def test_rate_environment_defaults_to_two_and_accepts_reviewed_range() -> None:
    assert requests_per_second_from_environment({}) == 2.0
    assert requests_per_second_from_environment({"COLLECTOR_RELAY_REQUESTS_PER_SECOND": "4"}) == 4.0


def test_rate_limits_are_independent_per_official_host() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    response = _Response(
        status=200,
        headers={"Content-Length": "2", "Content-Type": "application/json"},
        body=b"{}",
    )
    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=lambda *_args, **_kwargs: _Connection(response),  # type: ignore[arg-type]
        requests_per_second=2,
        clock=lambda: now[0],
        sleep=sleep,
    )

    relay.fetch(resolve_target("/v1/precount/1/configuration"))
    relay.fetch(resolve_target("/v1/precount/2/configuration"))
    relay.fetch(resolve_target("/v1/precount/1/configuration"))

    # The second host receives its first request immediately. The third call
    # is back on host one and therefore consumes that host's 0.5 s spacing.
    assert sleeps == [0.5]


def test_at_most_two_connections_are_in_flight_per_host() -> None:
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    in_flight = [0]
    peak = [0]

    class BlockingConnection(_Connection):
        def getresponse(self) -> _Response:
            with lock:
                in_flight[0] += 1
                peak[0] = max(peak[0], in_flight[0])
                if in_flight[0] == 2:
                    started.set()
            assert release.wait(timeout=3)
            with lock:
                in_flight[0] -= 1
            return self.response

    def connection_factory(*_args: object, **_kwargs: object) -> BlockingConnection:
        return BlockingConnection(
            _Response(
                status=200,
                headers={"Content-Length": "2", "Content-Type": "application/json"},
                body=b"{}",
            )
        )

    relay = OfficialRelay(
        resolver=lambda _host: ("8.8.8.8",),
        connection_factory=connection_factory,  # type: ignore[arg-type]
        requests_per_second=5,
    )
    target = resolve_target("/v1/precount/2/configuration")
    failures: list[BaseException] = []

    def fetch() -> None:
        try:
            relay.fetch(target)
        except BaseException as exc:  # noqa: BLE001 - test thread boundary
            failures.append(exc)

    workers = [threading.Thread(target=fetch) for _ in range(3)]
    for worker in workers:
        worker.start()
    assert started.wait(timeout=2)
    with lock:
        assert in_flight[0] == 2
        assert peak[0] == 2
    release.set()
    for worker in workers:
        worker.join(timeout=3)
        assert not worker.is_alive()
    assert not failures
    assert peak[0] == 2


@pytest.mark.parametrize("error", (BrokenPipeError(), ConnectionResetError()))
def test_client_disconnect_is_silent_and_not_a_successful_write(error: OSError) -> None:
    class DroppedClient:
        def write(self, _body: bytes) -> None:
            raise error

    assert _write_client_body(DroppedClient(), b"official bytes") is False
