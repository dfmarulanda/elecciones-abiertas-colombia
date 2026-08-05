from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from elecciones_pipeline.catalog import load_source_catalog
from elecciones_pipeline.ingest.checkpoint import SQLiteCheckpointStore
from elecciones_pipeline.ingest.precount import PrecountPlanEntry
from elecciones_pipeline.ingest.precount_crawl import EnumeratedMesa, _plan_id, crawl_precount

ROOT = Path(__file__).resolve().parents[3]
ORIGIN = "https://resultadosprecpresidente2026-2v.registraduria.gov.co"
ROUND1_ORIGIN = "https://resultadosprecpresidente2026-1v.registraduria.gov.co"


def nomenclator() -> dict[str, object]:
    return {
        "amb": [
            {
                "elec": 1,
                "ambitos": [
                    {
                        "i": 0,
                        "n": "COLOMBIA",
                        "c": "00",
                        "s": "COLOMBIA",
                        "l": 1,
                        "m": 0,
                        "p": [],
                        "r": [0],
                        "h": [{"l": 2, "p": [1]}],
                    },
                    {
                        "i": 1,
                        "n": "BOGOTA D.C.",
                        "c": "16",
                        "s": "BOGOTA-DC",
                        "l": 2,
                        "m": 0,
                        "p": [{"l": 1, "p": [0]}],
                        "r": [1],
                        "h": [{"l": 3, "p": [2]}],
                    },
                    {
                        "i": 2,
                        "n": "BOGOTA D.C.",
                        "c": "16001",
                        "s": "BOGOTA-DC",
                        "l": 3,
                        "m": 0,
                        "p": [{"l": 2, "p": [1]}],
                        "r": [2],
                        "h": [{"l": 4, "p": [3]}],
                    },
                    {
                        "i": 3,
                        "n": "ZONA 06",
                        "c": "1600106",
                        "s": "ZONA-06",
                        "l": 4,
                        "m": 0,
                        "p": [{"l": 3, "p": [2]}],
                        "r": [3],
                        "h": [{"l": 5, "p": [4]}],
                    },
                    {
                        "i": 4,
                        "n": "COMUNA 1",
                        "c": "16001061",
                        "s": "COMUNA-1",
                        "l": 5,
                        "m": 0,
                        "p": [{"l": 4, "p": [3]}],
                        "r": [4],
                        "h": [{"l": 6, "p": [5]}],
                    },
                    {
                        "i": 5,
                        "n": "ABRAHAM LINCOLN",
                        "c": "160010603",
                        "s": "ABRAHAM-LINCOLN",
                        "l": 6,
                        "m": 2,
                        "p": [{"l": 5, "p": [4]}],
                        "r": [5],
                        "h": [],
                    },
                ],
            }
        ]
    }


def act(scope: str, department: str, mesas: tuple[str, ...] = ()) -> dict[str, object]:
    def party(code: str, candidate: str, position: str, votes: str, share: str):
        return {
            "act": {
                "codpar": code,
                "vot": votes,
                "pvot": share,
                "cantotabla": [
                    {
                        "amb": scope,
                        "codcan": candidate,
                        "sorteo": position,
                        "nomcan": f"NOMBRE {candidate}",
                        "apecan": f"APELLIDO {candidate}",
                        "nomcan2": f"VICE {candidate}",
                        "apecan2": f"VICEAPELLIDO {candidate}",
                        "vot": votes,
                        "pvot": share,
                    }
                ],
            }
        }

    return {
        "elec": "1",
        "amb": scope,
        "dept": department,
        "totales": {
            "act": {
                "metota": "2",
                "mesesc": "1",
                "meserr": "0",
                "centota": "300",
                "votant": "200",
                "absten": "100",
                "votnul": "2",
                "votnma": "1",
                "votblan": "7",
                "votval": "197",
                "pmesesc": "50,00%",
                "pvotant": "66,67%",
                "pabsten": "33,33%",
                "pvotnul": "1,00%",
                "pvotnma": "0,50%",
                "pvotblan": "3,55%",
                "pvotval": "98,50%",
            }
        },
        "camaras": [
            {
                "cam": "0",
                "cir": "0",
                "partotabla": [
                    party("2", "1", "1", "90", "45,69%"),
                    party("3", "2", "2", "100", "50,76%"),
                ],
                "mapagan": [{"amb": mesa, "nombre": "Mesa 1"} for mesa in mesas],
            }
        ],
    }


def responses() -> dict[str, object]:
    return {
        f"{ORIGIN}/json/web/config.json": {"version": 1},
        f"{ORIGIN}/json/nomenclator.json": nomenclator(),
        "https://escrutinios2vueltapresidente2026.registraduria.gov.co/data/index.json": {
            "data/esc/v1/divipole/": "divipole.json"
        },
        f"{ORIGIN}/json/ACT/PR/00.json": act("00", "00"),
        f"{ORIGIN}/json/ACT/PR/16.json": act("16", "16"),
        f"{ORIGIN}/json/ACT/PR/16001.json": act("16001", "16"),
        f"{ORIGIN}/json/ACT/PR/1600106.json": act("1600106", "16"),
        f"{ORIGIN}/json/ACT/PR/16001061.json": act("16001061", "16"),
        f"{ORIGIN}/json/ACT/PR/160010603.json": act("160010603", "16", ("160010603000001",)),
        f"{ORIGIN}/json/ACT/PR/160010603000001.json": act("160010603000001", "16"),
    }


def run_crawl(tmp_path: Path, stage: str):
    payloads = responses()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = payloads.get(str(request.url))
        if payload is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            json=payload,
            headers={"ETag": f'"{len(json.dumps(payload))}"'},
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"),
                tmp_path,
                stage=stage,  # type: ignore[arg-type]
                requests_per_second=5,
                limit=1 if stage == "mesas" else None,
                http_client=client,
            )

    return asyncio.run(run())


def test_national_crawl_stores_raw_before_normalized_parse(tmp_path: Path) -> None:
    report = run_crawl(tmp_path, "national")
    assert report.expected == report.planned == report.retrieved == report.parsed == 1
    assert report.missing == report.ambiguous == 0
    assert report.complete
    assert list((tmp_path / "objects/sha256").iterdir())
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        normalized = json.loads(
            connection.execute(
                "SELECT normalized_json FROM items WHERE plan_id = ?", (report.plan_id,)
            ).fetchone()[0]
        )
    assert normalized["scope_code"] == "00"
    assert normalized["provenance"]["content_hash"]
    assert "cedula" not in json.dumps(normalized)


def test_resume_does_not_refetch_checkpointed_successful_items(tmp_path: Path) -> None:
    first = run_crawl(tmp_path, "national")
    payloads = responses()
    successful_url = f"{ORIGIN}/json/ACT/PR/00.json"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        assert url != successful_url, "a checkpointed crawl item must be reused"
        payload = payloads.get(url)
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def resume():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"),
                tmp_path,
                stage="national",
                requests_per_second=5,
                http_client=client,
            )

    resumed = asyncio.run(resume())
    assert resumed.plan_id == first.plan_id
    assert resumed.reused == 1
    assert calls


def test_retry_nonparsed_only_leaves_parsed_rows_untouched_and_fills_the_gap(
    tmp_path: Path,
) -> None:
    first = run_crawl(tmp_path, "aggregates")
    retry_url = f"{ORIGIN}/json/ACT/PR/16001.json"
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        preserved = connection.execute(
            """SELECT source_hash, object_key, retrieved_at, normalized_json, updated_at
            FROM items WHERE plan_id = ? AND source_url = ?""",
            (first.plan_id, f"{ORIGIN}/json/ACT/PR/16.json"),
        ).fetchone()
        connection.execute(
            """UPDATE items SET network_status = 'failed', parse_status = 'missing',
            normalized_json = NULL, error = 'transport failure for test'
            WHERE plan_id = ? AND source_url = ?""",
            (first.plan_id, retry_url),
        )
        connection.commit()

    payloads = responses()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        payload = payloads.get(url)
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def retry():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"),
                tmp_path,
                stage="aggregates",
                requests_per_second=5,
                retry_nonparsed_only=True,
                http_client=client,
            )

    report = asyncio.run(retry())
    assert report.plan_id == first.plan_id
    assert report.expected == report.planned == report.parsed == report.retrieved == 6
    assert report.missing == report.ambiguous == 0
    act_calls = [url for url in calls if "/json/ACT/PR/" in url]
    assert act_calls == [retry_url]
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        unchanged = connection.execute(
            """SELECT source_hash, object_key, retrieved_at, normalized_json, updated_at
            FROM items WHERE plan_id = ? AND source_url = ?""",
            (first.plan_id, f"{ORIGIN}/json/ACT/PR/16.json"),
        ).fetchone()
    assert unchanged == preserved


def test_retry_nonparsed_only_refuses_new_or_sample_mismatched_plan(tmp_path: Path) -> None:
    catalog = load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = responses().get(str(request.url))
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def retry(**kwargs: object):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(catalog, tmp_path, http_client=client, **kwargs)

    with pytest.raises(Exception, match="requires an existing matching crawl plan"):
        asyncio.run(retry(stage="aggregates", retry_nonparsed_only=True))
    run_crawl(tmp_path, "aggregates")
    with pytest.raises(Exception, match="requires an existing matching crawl plan"):
        asyncio.run(retry(stage="aggregates", limit=1, retry_nonparsed_only=True))
    with pytest.raises(Exception, match="cannot be combined"):
        asyncio.run(
            retry(
                stage="aggregates", refresh_existing=True, retry_nonparsed_only=True,
            )
        )


@pytest.mark.parametrize(
    ("catalog_name", "origin"),
    [
        ("presidencia-2026-segunda-vuelta.json", ORIGIN),
        ("presidencia-2026-primera-vuelta.json", ROUND1_ORIGIN),
    ],
)
def test_resume_conditionally_refetches_ambiguous_raw_response_until_it_parses(
    tmp_path: Path, catalog_name: str, origin: str
) -> None:
    payloads = {
        url.replace(ORIGIN, origin): payload
        for url, payload in responses().items()
        if catalog_name.startswith("presidencia-2026-segunda") or "escrutinios" not in url
    }
    national_url = f"{origin}/json/ACT/PR/00.json"
    transient = {"active": True}
    calls: list[str] = []
    national_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url == national_url:
            national_headers.append(dict(request.headers))
        if url == national_url and transient["active"]:
            return httpx.Response(200, content=b'in-Policies: {"elec":"1"}')
        payload = payloads.get(url)
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources" / catalog_name),
                tmp_path,
                stage="national",
                requests_per_second=5,
                http_client=client,
            )

    first = asyncio.run(run())
    assert first.ambiguous == 1
    transient["active"] = False
    second = asyncio.run(run())
    assert second.parsed == second.retrieved == 1
    assert second.ambiguous == second.missing == 0
    assert calls.count(national_url) == 5
    assert all("if-none-match" not in headers for headers in national_headers[1:])
    assert all("if-modified-since" not in headers for headers in national_headers[1:])


@pytest.mark.parametrize(
    ("raw_attempts", "expect_parsed", "expected_snapshots"),
    [
        ([b'in-Policies: {"elec":"1"}', None], True, 2),
        ([b"in-Policies: first", b"in-Policies: second", None], True, 3),
        ([b"in-Policies: one", b"in-Policies: two", b"in-Policies: three", b"four"], False, 4),
    ],
)
def test_decode_retry_is_bounded_fresh_and_preserves_every_raw_snapshot(
    tmp_path: Path,
    raw_attempts: list[bytes | None],
    expect_parsed: bool,
    expected_snapshots: int,
) -> None:
    payloads = responses()
    national_url = f"{ORIGIN}/json/ACT/PR/00.json"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == national_url:
            requests.append(request)
            raw = raw_attempts.pop(0)
            if raw is not None:
                return httpx.Response(200, content=raw)
        payload = payloads.get(str(request.url))
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"),
                tmp_path,
                stage="national",
                requests_per_second=5,
                http_client=client,
            )

    report = asyncio.run(run())
    if expect_parsed:
        assert report.parsed == 1
    else:
        assert report.ambiguous == 1
    snapshots = SQLiteCheckpointStore(tmp_path / "checkpoints.sqlite3").snapshots(national_url)
    assert len(snapshots) == expected_snapshots
    assert all("if-none-match" not in request.headers for request in requests[1:])
    assert all("if-modified-since" not in request.headers for request in requests[1:])


def test_mesa_plan_id_ignores_recovered_place_hash_when_published_ids_match() -> None:
    entry = PrecountPlanEntry(
        source_url=f"{ORIGIN}/json/ACT/PR/160010603000001.json",
        election_id="1",
        election_siglas="PR",
        scope_code="160010603000001",
        scope_level=7,
        grain="mesa",
        kind="mesa",
        department_code="16",
        parent_scope_code="160010603",
    )
    first = EnumeratedMesa(
        entry, f"{ORIGIN}/json/ACT/PR/160010603.json", "a" * 64, "a" * 64
    )
    recovered = EnumeratedMesa(
        entry, f"{ORIGIN}/json/ACT/PR/160010603.json", "b" * 64, "a" * 64
    )
    assert _plan_id(
        stage="mesas", nomenclator_hash="c" * 64, expected=1, entries=(first,)
    ) == _plan_id(stage="mesas", nomenclator_hash="c" * 64, expected=1, entries=(recovered,))


def test_aggregate_crawl_collects_canonical_hierarchy_and_resumes(tmp_path: Path) -> None:
    first = run_crawl(tmp_path, "aggregates")
    assert first.expected == first.planned == first.parsed == 6
    assert first.complete
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        rows = connection.execute(
            "SELECT grain, scope_code, parent_scope_code "
            "FROM items WHERE plan_id = ? ORDER BY grain",
            (first.plan_id,),
        ).fetchall()
    assert {(row[0], row[1], row[2]) for row in rows} == {
        ("national", "00", None),
        ("department", "16", None),
        ("municipality", "16001", None),
        ("zone", "1600106", None),
        ("comuna", "16001061", None),
        ("polling_place", "160010603", None),
    }

    resumed = run_crawl(tmp_path, "aggregates")
    assert resumed.plan_id == first.plan_id
    assert resumed.reused == 6


def test_aggregate_schema_drift_is_raw_retained_and_not_mesa_data(tmp_path: Path) -> None:
    payloads = responses()
    broken = payloads[f"{ORIGIN}/json/ACT/PR/16001.json"]
    assert isinstance(broken, dict)
    del broken["totales"]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = payloads.get(str(request.url))
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json"),
                tmp_path,
                stage="aggregates",
                requests_per_second=5,
                http_client=client,
            )

    report = asyncio.run(run())
    assert report.parsed == 5
    assert report.ambiguous == 1
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        row = connection.execute(
            "SELECT grain, normalized_json, source_hash FROM items "
            "WHERE plan_id = ? AND scope_code = '16001'",
            (report.plan_id,),
        ).fetchone()
    assert row[0] == "municipality"
    assert row[1] is None
    assert len(row[2]) == 64


def test_mesa_crawl_enumerates_only_observed_ids_and_reports_gap(tmp_path: Path) -> None:
    report = run_crawl(tmp_path, "mesas")
    assert report.sample_limited is True
    assert report.expected == 2
    assert report.planned == report.parsed == 1
    assert report.missing == 1
    assert not report.complete
    with sqlite3.connect(tmp_path / "crawl.sqlite3") as connection:
        mesa = connection.execute(
            """
            SELECT scope_code, parent_scope_code, discovered_from_hash
            FROM items
            WHERE plan_id = ?
            """,
            (report.plan_id,),
        ).fetchone()
    assert mesa[0] == "160010603000001"
    assert mesa[1] == "160010603"
    assert len(mesa[2]) == 64


def test_round1_mixed_catalog_precount_crawls_never_request_scrutiny(
    tmp_path: Path,
) -> None:
    payloads = {
        url.replace(ORIGIN, ROUND1_ORIGIN): payload
        for url, payload in responses().items()
        if "escrutinios" not in url
    }
    mesa = payloads[f"{ROUND1_ORIGIN}/json/ACT/PR/160010603000001.json"]
    assert isinstance(mesa, dict)
    mesa["totales"]["act"]["centota"] = "0"  # type: ignore[index]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        payload = payloads.get(url)
        assert payload is not None
        return httpx.Response(200, json=payload)

    async def run(stage: str, limit: int | None = None, state: Path | None = None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await crawl_precount(
                load_source_catalog(ROOT / "config/sources/presidencia-2026-primera-vuelta.json"),
                state or tmp_path,
                stage=stage,  # type: ignore[arg-type]
                requests_per_second=5,
                limit=limit,
                http_client=client,
            )

    national = asyncio.run(run("national"))
    places = asyncio.run(run("places"))
    mesa_state = tmp_path / "mesas"
    mesas = asyncio.run(run("mesas", limit=1, state=mesa_state))
    assert national.complete and national.expected == 1
    assert places.complete and places.expected == 1
    assert mesas.sample_limited and mesas.planned == mesas.parsed == 1
    assert mesas.expected == 2 and mesas.missing == 1
    assert calls
    assert all(url.startswith(ROUND1_ORIGIN) for url in calls)
    assert not any("escrutinios" in url for url in calls)

    with sqlite3.connect(mesa_state / "crawl.sqlite3") as connection:
        normalized = json.loads(
            connection.execute(
                "SELECT normalized_json FROM items WHERE plan_id = ?", (mesas.plan_id,)
            ).fetchone()[0]
        )
    centota = next(metric for metric in normalized["totals"] if metric["name"] == "centota")
    # The collector preserves the official zero raw value; later candidate
    # materialization is responsible for marking geographic electorate as
    # unavailable rather than inferring or apportioning it.
    assert centota["raw"] == "0"
    assert centota["value"] == 0
