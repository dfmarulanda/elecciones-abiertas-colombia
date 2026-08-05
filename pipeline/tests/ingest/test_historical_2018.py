from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import elecciones_pipeline.cli as cli
import elecciones_pipeline.ingest.historical_2018 as historical
import pytest
import respx
from elecciones_pipeline.cli import app
from elecciones_pipeline.ingest.historical_2018 import (
    HISTORICAL_2018_URLS,
    Historical2018Error,
    HistoricalBuild,
    _rows,
    build_historical_2018_release,
    fetch_historical_2018,
    import_historical_2018_archives,
)
from elecciones_pipeline.ingest.models import Snapshot
from elecciones_pipeline.ingest.storage import LocalObjectStore
from httpx import Response
from typer.testing import CliRunner

HEADER = (
    "DEP;DEPNOMBRE;MUN;MUNNOMBRE;ZONA;PUESTO;PUESNOMBRE;MESA;CORCODIGO;CORNOMBRE;"
    "CIR;PAR;PARNOMBRE;CAN;CANNOMBRE;VOTOS\n"
)
ROW = (
    "05;ANTIOQUÍA;001;MEDELLÍN;01;A3;PUESTO Ñ;001;01;PRESIDENTE;00;1235;PARTIDO;"
    "002;CANDIDATO;0007\n"
)


@pytest.fixture(autouse=True)
def _legacy_csv_fixture_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep inherited CSV safety cases isolated from the real XLSX profile."""
    monkeypatch.setattr(
        historical, "_MEMBER_RE", re.compile(r"^MMV_NACIONAL_PRESIDENTE_2018_[12]v\.csv$")
    )


def _zip(payload: str, name: str = "MMV_NACIONAL_PRESIDENTE_2018_1v.csv") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(name, payload.encode("latin-1"))
    return buffer.getvalue()


def _snapshot(round_number: int = 1) -> Snapshot:
    return Snapshot(
        url=HISTORICAL_2018_URLS[round_number],
        content_hash="a" * 64,
        object_key="sha256/" + "a" * 64,
        media_type="application/zip",
        byte_size=1,
        retrieved_at=datetime(2026, 8, 4, tzinfo=UTC),
    )


def test_parser_preserves_latin1_and_complete_provenance() -> None:
    row = list(_rows(_zip(HEADER + ROW), 1, _snapshot(), data_version="release-x"))[0]
    assert row["dep_name"] == "ANTIOQUÍA"
    assert row["puesto_code"] == "A3"
    assert row["votes"] == 7
    assert {key: row[key] for key in ("data_version", "source_type", "legal_status")} == {
        "data_version": "release-x",
        "source_type": "contextual_baseline",
        "legal_status": "context_only",
    }
    assert row["parser_version"] == historical.PARSER_VERSION
    assert row["transform_version"] == historical.TRANSFORM_VERSION


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("wrong;header\nvalue;value\n", "header"),
        (HEADER + ROW.replace("0007", "-1"), "VOTOS"),
        (HEADER + ROW.replace("0007", "1.5"), "VOTOS"),
        (HEADER + ROW.replace("0007", "10001"), "VOTOS"),
        (HEADER + ROW.replace("ANTIOQUÍA", ""), "blank DEPNOMBRE"),
    ],
)
def test_parser_rejects_schema_and_invalid_vote_values(payload: str, message: str) -> None:
    with pytest.raises(Historical2018Error, match=message):
        list(_rows(_zip(payload), 1, _snapshot()))


def test_parser_rejects_extra_missing_duplicate_and_name_conflict() -> None:
    for header in (HEADER.replace(";VOTOS", ";EXTRA;VOTOS"), HEADER.replace(";VOTOS", "")):
        with pytest.raises(Historical2018Error, match="header"):
            list(_rows(_zip(header + ROW), 1, _snapshot()))
    with pytest.raises(Historical2018Error, match="duplicate semantic"):
        list(_rows(_zip(HEADER + ROW + ROW), 1, _snapshot()))
    with pytest.raises(Historical2018Error, match="conflicting names"):
        list(_rows(_zip(HEADER + ROW + ROW.replace("ANTIOQUÍA", "OTRO")), 1, _snapshot()))


def test_parser_rejects_unsafe_zip_shapes() -> None:
    with pytest.raises(Historical2018Error, match="member name"):
        list(_rows(_zip(HEADER + ROW, "other.csv"), 1, _snapshot()))
    with pytest.raises(Historical2018Error, match="member name"):
        list(_rows(_zip(HEADER + ROW, "../../MMV_NACIONAL_PRESIDENTE_2018_1v.csv"), 1, _snapshot()))
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("MMV_NACIONAL_PRESIDENTE_2018_1v.csv", (HEADER + ROW).encode("latin-1"))
        archive.writestr("extra.csv", b"x")
    with pytest.raises(Historical2018Error, match="exactly one"):
        list(_rows(buffer.getvalue(), 1, _snapshot()))
    with pytest.raises(Historical2018Error, match="compression ratio"):
        list(_rows(_zip("x" * 3_000_000), 1, _snapshot()))
    with pytest.raises(Historical2018Error, match="ZIP"):
        list(_rows(b"not-a-zip", 1, _snapshot()))
    encrypted = bytearray(_zip(HEADER + ROW))
    # Set the encrypted flag in both local-file and central-directory headers.
    for marker, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        position = encrypted.index(marker)
        encrypted[position + flag_offset] |= 1
    with pytest.raises(Historical2018Error, match="unsafe MMV ZIP member"):
        list(_rows(bytes(encrypted), 1, _snapshot()))


def test_import_accepts_only_reviewed_safe_archives_into_sha_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = {
        1: _zip(HEADER + ROW),
        2: _zip(HEADER + ROW, "MMV_NACIONAL_PRESIDENTE_2018_2v.csv"),
    }
    _set_reviewed_metadata(monkeypatch, payloads)
    paths = {number: tmp_path / f"round-{number}.zip" for number in payloads}
    for number, path in paths.items():
        path.write_bytes(payloads[number])
    snapshots = import_historical_2018_archives(tmp_path / "state", paths)
    for number, snapshot in snapshots.items():
        assert snapshot.content_hash == hashlib.sha256(payloads[number]).hexdigest()
        assert snapshot.etag == f'"fixture-{number}"'
        stored = tmp_path / "state" / "objects" / snapshot.object_key
        assert stored.read_bytes() == payloads[number]
    paths[1].write_bytes(b"not-a-zip")
    with pytest.raises(Historical2018Error, match="reviewed size"):
        import_historical_2018_archives(tmp_path / "rejected", paths)


def _set_reviewed_metadata(monkeypatch: pytest.MonkeyPatch, payloads: dict[int, bytes]) -> None:
    monkeypatch.setattr(
        historical,
        "EXPECTED_SOURCE_METADATA",
        {
            number: {"byte_size": len(payload), "etag": f'"fixture-{number}"'}
            for number, payload in payloads.items()
        },
    )


def _mock_payloads(payloads: dict[int, bytes]) -> None:
    for round_number, payload in payloads.items():
        respx.get(HISTORICAL_2018_URLS[round_number]).mock(
            return_value=Response(
                200,
                headers={"Content-Type": "application/zip", "ETag": f'"fixture-{round_number}"'},
                content=payload,
            )
        )


@pytest.mark.asyncio
async def test_fetch_is_conditional_idempotent_and_records_changed_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = {1: _zip(HEADER + ROW), 2: _zip(HEADER + ROW, "MMV_NACIONAL_PRESIDENTE_2018_2v.csv")}
    _set_reviewed_metadata(monkeypatch, first)
    with respx.mock:
        _mock_payloads(first)
        snapshots = await fetch_historical_2018(tmp_path, max_attempts=1)
    with respx.mock:
        for url in HISTORICAL_2018_URLS.values():
            respx.get(url).mock(return_value=Response(304))
        assert await fetch_historical_2018(tmp_path, recheck=True, max_attempts=1) == snapshots
    changed = _zip(HEADER + ROW.replace("0007", "0008"))
    _set_reviewed_metadata(monkeypatch, {1: changed, 2: first[2]})
    with respx.mock:
        respx.get(HISTORICAL_2018_URLS[1]).mock(
            return_value=Response(
                200,
                headers={"Content-Type": "application/zip", "ETag": '"fixture-1"'},
                content=changed,
            )
        )
        respx.get(HISTORICAL_2018_URLS[2]).mock(return_value=Response(304))
        updated = await fetch_historical_2018(tmp_path, recheck=True, max_attempts=1)
    assert updated[1].content_hash == hashlib.sha256(changed).hexdigest()
    assert updated[1].snapshot_number == 2


@pytest.mark.asyncio
async def test_fetch_retries_and_rejects_redirect_and_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payloads = {1: _zip(HEADER + ROW), 2: _zip(HEADER + ROW, "MMV_NACIONAL_PRESIDENTE_2018_2v.csv")}
    _set_reviewed_metadata(monkeypatch, payloads)
    with respx.mock:
        route = respx.get(HISTORICAL_2018_URLS[1])
        route.side_effect = [
            Response(503),
            Response(
                200,
                headers={"Content-Type": "application/zip", "ETag": '"fixture-1"'},
                content=payloads[1],
            ),
        ]
        respx.get(HISTORICAL_2018_URLS[2]).mock(
            return_value=Response(
                200,
                headers={"Content-Type": "application/zip", "ETag": '"fixture-2"'},
                content=payloads[2],
            )
        )
        assert (await fetch_historical_2018(tmp_path, max_attempts=2))[1].snapshot_number == 1
    with respx.mock:
        respx.get(HISTORICAL_2018_URLS[1]).mock(
            return_value=Response(302, headers={"Location": "https://evil.invalid/a.zip"})
        )
        with pytest.raises(Exception, match="allowlist"):
            await fetch_historical_2018(tmp_path / "redirect", max_attempts=1)
    with respx.mock:
        respx.get(HISTORICAL_2018_URLS[1]).mock(
            return_value=Response(200, headers={"Content-Type": "text/html"}, content=b"PK\x03\x04")
        )
        with pytest.raises(Historical2018Error, match="content type"):
            await fetch_historical_2018(tmp_path / "type", max_attempts=1)
    with respx.mock:
        _set_reviewed_metadata(monkeypatch, {1: b"not-a-zip", 2: payloads[2]})
        respx.get(HISTORICAL_2018_URLS[1]).mock(
            return_value=Response(
                200,
                headers={"Content-Type": "application/zip", "ETag": '"fixture-1"'},
                content=b"not-a-zip",
            )
        )
        with pytest.raises(Historical2018Error, match="not a ZIP"):
            await fetch_historical_2018(tmp_path / "magic", max_attempts=1)
    with respx.mock:
        _set_reviewed_metadata(monkeypatch, payloads)
        respx.get(HISTORICAL_2018_URLS[1]).mock(
            return_value=Response(
                200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Length": str(len(payloads[1]) + 1),
                },
                content=b"PK\x03\x04",
            )
        )
        with pytest.raises(Historical2018Error, match="Content-Length"):
            await fetch_historical_2018(tmp_path / "size", max_attempts=1)


def test_two_frozen_builds_have_identical_artifact_and_manifest_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state"
    objects = LocalObjectStore(state / "objects")
    raw = {1: _zip(HEADER + ROW), 2: _zip(HEADER + ROW, "MMV_NACIONAL_PRESIDENTE_2018_2v.csv")}
    snapshots: dict[int, Snapshot] = {}
    for round_number, payload in raw.items():
        key = asyncio.run(objects.put(payload, content_type="application/zip"))
        snapshots[round_number] = Snapshot(
            url=HISTORICAL_2018_URLS[round_number],
            content_hash=hashlib.sha256(payload).hexdigest(),
            object_key=key,
            media_type="application/zip",
            byte_size=len(payload),
            retrieved_at=datetime(2026, 8, 4, tzinfo=UTC),
        )

    async def frozen_fetch(*_args: object, **_kwargs: object) -> dict[int, Snapshot]:
        return snapshots

    monkeypatch.setattr(historical, "fetch_historical_2018", frozen_fetch)
    with pytest.raises(Historical2018Error, match="retired fixed v1"):
        build_historical_2018_release(
            state,
            tmp_path / "historical-2018-mmv-context-v1",
            tmp_path / "retired-manifest",
            git_commit="frozen",
        )
    one = build_historical_2018_release(
        state, tmp_path / "one", tmp_path / "man-one", git_commit="frozen"
    )
    two = build_historical_2018_release(
        state, tmp_path / "two", tmp_path / "man-two", git_commit="frozen"
    )
    assert one.release_id == two.release_id
    for first, second in zip(
        (one.rows_path, one.rollups_path, one.geography_path, one.metadata_path, one.manifest_path),
        (two.rows_path, two.rollups_path, two.geography_path, two.metadata_path, two.manifest_path),
        strict=True,
    ):
        assert first.read_bytes() == second.read_bytes(), first.name


def test_historical_cli_atomically_installs_v2_then_is_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release_id = "historical-2018-mmv-context-v2-0123456789abcdef"
    content = {"rows": b"rows-v1"}

    def fake_build(
        _state: Path, output: Path, manifests: Path, *, git_commit: str
    ) -> HistoricalBuild:
        assert git_commit == "frozen"
        output.mkdir(parents=True)
        manifests.mkdir(parents=True)
        rows = output / "historical-2018-mmv.parquet"
        rollups = output / "historical-2018-rollups.parquet"
        geography = output / "historical-2018-geography.parquet"
        metadata = output / "historical-2018-metadata.json"
        manifest = manifests / f"{release_id}.json"
        rows.write_bytes(content["rows"])
        rollups.write_bytes(b"rollups")
        geography.write_bytes(b"geography")
        metadata.write_bytes(b"metadata")
        manifest.write_bytes(b'{"status":"candidate"}\n')
        return HistoricalBuild(
            manifest, metadata, rows, rollups, geography, {1: 1, 2: 1}, {1: 1, 2: 1}, release_id
        )

    monkeypatch.setattr(cli, "build_historical_2018_release", fake_build)
    release_root = tmp_path / "releases"
    manifest_root = tmp_path / "manifests"
    arguments = [
        "historical-2018-build",
        "--state-dir",
        str(tmp_path / "state"),
        "--release-root",
        str(release_root),
        "--manifest-dir",
        str(manifest_root),
        "--git-commit",
        "frozen",
    ]
    first = CliRunner().invoke(app, arguments)
    assert first.exit_code == 0, first.output
    payload = json.loads(first.stdout)
    assert payload["status"] == "candidate_non_active"
    assert payload["installed"] is True
    target_rows = release_root / release_id / "historical-2018-mmv.parquet"
    target_manifest = manifest_root / f"{release_id}.json"
    before = (target_rows.read_bytes(), target_manifest.read_bytes())

    second = CliRunner().invoke(app, arguments)
    assert second.exit_code == 0, second.output
    assert json.loads(second.stdout)["no_op"] is True
    assert (target_rows.read_bytes(), target_manifest.read_bytes()) == before

    content["rows"] = b"conflicting-rows"
    conflict = CliRunner().invoke(app, arguments)
    assert conflict.exit_code == 2
    assert "refusing to overwrite" in conflict.output
    assert target_rows.read_bytes() == before[0]


def test_historical_cli_help_marks_context_candidate_non_active() -> None:
    help_result = CliRunner().invoke(app, ["historical-2018-build", "--help"])
    assert help_result.exit_code == 0
    assert "context-only candidate" in help_result.output
    assert "never activate" in help_result.output
