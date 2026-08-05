from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from elecciones_pipeline.catalog import SourceCatalog, load_source_catalog
from elecciones_pipeline.ingest import SQLiteCheckpointStore
from elecciones_pipeline.ingest.models import Snapshot
from elecciones_pipeline.releases import (
    build_candidate_manifest,
    build_national_precount_candidate,
    export_dataset,
)
from elecciones_pipeline.releases.candidate import (
    _PROFILES,
    _candidate_data,
    _geographic_snapshot_records,
)

ROOT = Path(__file__).resolve().parents[3]


def _snapshot(*, url: str, content: bytes, object_key: str) -> Snapshot:
    return Snapshot(
        url=url,
        content_hash=hashlib.sha256(content).hexdigest(),
        object_key=object_key,
        media_type="application/json",
        byte_size=len(content),
        retrieved_at=datetime(2026, 8, 3, 22, 56, 31, tzinfo=UTC),
    )


def _candidate_state(tmp_path: Path, catalog: SourceCatalog) -> tuple[Path, str]:
    """Create the smallest durable crawl state accepted by the candidate builder."""
    state = tmp_path / "state"
    state.mkdir()
    roots = catalog.manifest_entrypoints()
    checkpoint = SQLiteCheckpointStore(state / "checkpoints.sqlite3")
    snapshots = {
        "precount_configuration": b'{"version":1}',
        "precount_nomenclator": b'{"amb":[]}',
    }
    if "scrutiny_manifest" in roots:
        snapshots["scrutiny_manifest"] = b'{"data/esc/v1/divipole/":"divipole.json"}'
    for identifier, raw in snapshots.items():
        digest = hashlib.sha256(raw).hexdigest()
        key = f"sha256/{digest}"
        if identifier == "scrutiny_manifest":
            target = state / "objects" / key
            target.parent.mkdir(parents=True)
            target.write_bytes(raw)
        checkpoint.record_snapshot(_snapshot(url=roots[identifier], content=raw, object_key=key))

    national_url = catalog.precount_source().entrypoints["national_results"]
    national_raw = b'{"official":"national-act"}'
    national_digest = hashlib.sha256(national_raw).hexdigest()
    checkpoint.record_snapshot(
        _snapshot(
            url=national_url,
            content=national_raw,
            object_key=f"sha256/{national_digest}",
        )
    )
    round_one = catalog.election_slug == "presidencia-2026-primera-vuelta"
    if round_one:
        profile = _PROFILES[catalog.election_slug]
        candidate_rows = [
            {
                "party_code": party,
                "candidate_code": candidate,
                "ballot_position": str(position),
                "votes": {"state": "observed", "value": position},
            }
            for position, (party, candidate) in enumerate(profile.candidates, start=1)
        ]
        totals = {
            "metota": 10,
            "mesesc": 10,
            "centota": 200,
            "votant": 105,
            "absten": 95,
            "votnul": 4,
            "votnma": 1,
            "votblan": 9,
            "votval": 100,
        }
    else:
        candidate_rows = [
            {
                "party_code": "2",
                "candidate_code": "1",
                "ballot_position": "1",
                "votes": {"state": "observed", "value": 350},
            },
            {
                "party_code": "3",
                "candidate_code": "2",
                "ballot_position": "2",
                "votes": {"state": "observed", "value": 410},
            },
        ]
        totals = {
            "metota": 10,
            "mesesc": 10,
            "centota": 1_000,
            "votant": 800,
            "absten": 200,
            "votnul": 10,
            "votnma": 5,
            "votblan": 25,
            "votval": 785,
        }
    normalized = {
        "election_id": "1",
        "totals": [
            {"name": name, "state": "observed", "value": value}
            for name, value in totals.items()
        ],
        "candidates": candidate_rows,
        "provenance": {
            "content_hash": national_digest,
            "retrieved_at": "2026-08-03T22:56:31Z",
            "source_url": national_url,
        },
    }
    with sqlite3.connect(state / "crawl.sqlite3") as connection:
        connection.execute(
            """
            CREATE TABLE items (
                plan_id TEXT, grain TEXT, parse_status TEXT, normalized_json TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO items VALUES (?, 'national', 'parsed', ?)",
            ("national-plan", json.dumps(normalized)),
        )

    return state, "national-plan"


def _summary_accounting(snapshot_path: Path) -> dict[str, int]:
    summary = json.loads(snapshot_path.read_text(encoding="utf-8"))["summary"]
    return {
        "candidate_votes": sum(item["votes"]["value"] for item in summary["candidates"]),
        "blank_votes": summary["blank_votes"]["value"],
        "valid_votes": summary["valid_votes"]["value"],
        "null_votes": summary["null_votes"]["value"],
        "unmarked_votes": summary["unmarked_votes"]["value"],
        "voters": summary["voters"]["value"],
    }


def test_candidate_build_is_deterministic_and_uses_per_dataset_schema_urls(tmp_path: Path) -> None:
    catalog = load_source_catalog(ROOT / "config/sources/presidencia-2026-segunda-vuelta.json")
    state, plan_id = _candidate_state(tmp_path, catalog)
    kwargs = {
        "catalog": catalog,
        "state_directory": state,
        "plan_id": plan_id,
        "output_directory": tmp_path / "releases",
        "manifest_directory": tmp_path / "manifests",
        "git_commit": "a" * 40,
    }

    first = build_national_precount_candidate(**kwargs)
    second = build_national_precount_candidate(**kwargs)

    assert first == second
    manifest = json.loads(first.manifest_path.read_text())
    datasets = {item["id"]: item for item in manifest["datasets"]}
    assert manifest["status"] == "candidate"
    assert manifest["synthetic"] is False
    assert datasets["national-precount-results-json"]["schema_url"].endswith(
        "/result-fact.schema.json"
    )
    assert datasets["national-precount-results-parquet"]["schema_url"].endswith(
        "/result-fact.schema.json"
    )
    assert datasets["national-precount-results-flat-csv"]["schema_url"].endswith(
        "/result-fact-flat.schema.json"
    )
    assert _summary_accounting(first.snapshot_path) == {
        "candidate_votes": 760,
        "blank_votes": 25,
        "valid_votes": 785,
        "null_votes": 10,
        "unmarked_votes": 5,
        "voters": 800,
    }
    assert first.snapshot_path.read_bytes()
    assert first.publication_blockers


def test_first_round_profile_has_all_reviewed_slates_in_ballot_order() -> None:
    profile = _PROFILES["presidencia-2026-primera-vuelta"]
    normalized = {
        "candidates": [
            {
                "party_code": party,
                "candidate_code": candidate,
                "ballot_position": str(position),
                "votes": {"state": "observed", "value": position},
            }
            for position, (party, candidate) in enumerate(profile.candidates, start=1)
        ]
    }
    candidates, results = _candidate_data(normalized, profile)
    assert len(candidates) == len(results) == 13
    assert [candidate["ballot_number"] for candidate in candidates] == list(range(1, 14))
    assert {item["candidate_id"] for item in results} == {
        candidate[0] for candidate in profile.candidates.values() if isinstance(candidate, tuple)
    }


def test_first_round_candidate_is_byte_reproducible_from_frozen_inputs(tmp_path: Path) -> None:
    catalog = load_source_catalog(ROOT / "config/sources/presidencia-2026-primera-vuelta.json")
    state, plan_id = _candidate_state(tmp_path, catalog)

    def build(run: str):
        return build_national_precount_candidate(
            catalog=catalog,
            state_directory=state,
            plan_id=plan_id,
            output_directory=tmp_path / run / "releases",
            manifest_directory=tmp_path / run / "manifests",
            git_commit="b" * 40,
        )

    first = build("first")
    second = build("second")
    assert first.release_id == second.release_id
    assert first.snapshot_hash == second.snapshot_hash
    assert first.snapshot_path.read_bytes() == second.snapshot_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert _summary_accounting(first.snapshot_path) == {
        "candidate_votes": 91,
        "blank_votes": 9,
        "valid_votes": 100,
        "null_votes": 4,
        "unmarked_votes": 1,
        "voters": 105,
    }

    with sqlite3.connect(state / "crawl.sqlite3") as connection:
        normalized = json.loads(
            connection.execute("SELECT normalized_json FROM items").fetchone()[0]
        )
        normalized["provenance"]["content_hash"] = "f" * 64
        connection.execute(
            "UPDATE items SET normalized_json = ?", (json.dumps(normalized),)
        )
    checkpoint = SQLiteCheckpointStore(state / "checkpoints.sqlite3")
    source_url = catalog.precount_source().entrypoints["national_results"]
    checkpoint.record_snapshot(
        _snapshot(url=source_url, content=b"changed source", object_key="sha256/" + "f" * 64)
        .model_copy(update={"content_hash": "f" * 64})
    )
    changed = build("changed")
    assert changed.release_id != first.release_id


def test_manifest_schema_url_override_preserves_default_fallback(tmp_path: Path) -> None:
    json_artifact = export_dataset([{"id": 1}], name="nested", directory=tmp_path, format="json")
    csv_artifact = export_dataset([{"id": 1}], name="flat", directory=tmp_path, format="csv")
    manifest = build_candidate_manifest(
        release_id="candidate-schema-test",
        election_slug="presidencia-2026",
        methodology_version="method-v1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        git_commit="a" * 40,
        sources=[
            {
                "id": "precount",
                "source_type": "pre_count",
                "legal_status": "preliminary",
                "source_url": "https://official.example.co/precount",
                "retrieved_at": "2026-01-01T00:00:00Z",
                "content_hash": "a" * 64,
                "media_type": "application/json",
                "byte_size": 1,
                "parser_version": "parser-v1",
                "transform_version": "transform-v1",
                "coverage": {
                    "expected": 1,
                    "retrieved": 1,
                    "parsed": 1,
                    "missing": 0,
                    "ambiguous": 0,
                    "excluded": 0,
                },
            }
        ],
        datasets=[json_artifact, csv_artifact],
        artifact_base_url="https://artifacts.example.co",
        dataset_schema_url="https://schemas.example.co/default.schema.json",
        dataset_schema_urls={"flat": "https://schemas.example.co/flat.schema.json"},
        dataset_titles={
            "nested": {"es": "Anidado", "en": "Nested"},
            "flat": {"es": "Plano", "en": "Flat"},
        },
        notes={"es": "Datos oficiales.", "en": "Official data."},
    )

    schemas = {item["id"]: item["schema_url"] for item in manifest["datasets"]}
    assert schemas == {
        "flat-csv": "https://schemas.example.co/flat.schema.json",
        "nested-json": "https://schemas.example.co/default.schema.json",
    }


def test_geographic_candidate_records_preserve_unknowns_and_block_bad_place_rollup(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    nomenclator = {
        "amb": [
            {
                "elec": 1,
                "ambitos": [
                    {
                        "i": 0,
                        "n": "COLOMBIA",
                        "c": "00",
                        "s": "CO",
                        "l": 1,
                        "m": 0,
                        "p": [],
                        "r": [0],
                        "h": [{"l": 2, "p": [1]}],
                    },
                    {
                        "i": 1,
                        "n": "D",
                        "c": "16",
                        "s": "D",
                        "l": 2,
                        "m": 0,
                        "p": [{"l": 1, "p": [0]}],
                        "r": [1],
                        "h": [{"l": 3, "p": [2]}],
                    },
                    {
                        "i": 2,
                        "n": "M",
                        "c": "16001",
                        "s": "M",
                        "l": 3,
                        "m": 0,
                        "p": [{"l": 2, "p": [1]}],
                        "r": [2],
                        "h": [{"l": 4, "p": [3]}],
                    },
                    {
                        "i": 3,
                        "n": "Z",
                        "c": "1600106",
                        "s": "Z",
                        "l": 4,
                        "m": 0,
                        "p": [{"l": 3, "p": [2]}],
                        "r": [3],
                        "h": [{"l": 6, "p": [4]}],
                    },
                    {
                        "i": 4,
                        "n": "P",
                        "c": "160010603",
                        "s": "P",
                        "l": 6,
                        "m": 2,
                        "p": [{"l": 4, "p": [3]}],
                        "r": [4],
                        "h": [],
                    },
                ],
            }
        ]
    }
    digest = hashlib.sha256(json.dumps(nomenclator, separators=(",", ":")).encode()).hexdigest()
    with sqlite3.connect(state / "crawl.sqlite3") as connection:
        connection.executescript(
            """
            CREATE TABLE plans (
                id TEXT PRIMARY KEY, stage TEXT, nomenclator_hash TEXT, expected INTEGER,
                sample_limited INTEGER
            );
            CREATE TABLE items (plan_id TEXT, source_url TEXT, scope_code TEXT, grain TEXT,
                parent_scope_code TEXT, parse_status TEXT, normalized_json TEXT);
            """
        )
        connection.executemany(
            "INSERT INTO plans VALUES (?, ?, ?, ?, ?)",
            [("places", "places", digest, 1, 1), ("mesas", "mesas", digest, 2, 1)],
        )

        def normalized(scope: str, grain: str, voters: int | None) -> dict[str, object]:
            totals = []
            for name in ("centota", "votant", "votval", "votblan", "votnul", "votnma"):
                totals.append(
                    {
                        "name": name,
                        "state": "unknown" if name == "votnul" else "observed",
                        "value": (None if name == "votnul" else 0 if name == "centota" else voters),
                    }
                )
            return {
                "scope_code": scope,
                "grain": grain,
                "totals": totals,
                "candidates": [
                    {
                        "party_code": "2",
                        "candidate_code": "1",
                        "votes": {"state": "observed", "value": voters},
                    },
                    {
                        "party_code": "3",
                        "candidate_code": "2",
                        "votes": {"state": "observed", "value": voters},
                    },
                ],
                "provenance": {
                    "source_type": "pre_count",
                    "legal_status": "preliminary",
                    "source_url": f"https://official.example/{scope}",
                    "retrieved_at": "2026-08-03T00:00:00Z",
                    "content_hash": "a" * 64,
                    "parser_version": "registraduria-precount-act@1.0.0",
                    "transform_version": "precount-normalized@1.0.0",
                },
            }

        connection.executemany(
            "INSERT INTO items VALUES (?, ?, ?, ?, ?, 'parsed', ?)",
            [
                (
                    "places",
                    "https://official.example/160010603",
                    "160010603",
                    "polling_place",
                    None,
                    json.dumps(normalized("160010603", "polling_place", 3)),
                ),
                (
                    "mesas",
                    "https://official.example/160010603000001",
                    "160010603000001",
                    "mesa",
                    "160010603",
                    json.dumps(normalized("160010603000001", "mesa", 1)),
                ),
                (
                    "mesas",
                    "https://official.example/160010603000002",
                    "160010603000002",
                    "mesa",
                    "160010603",
                    json.dumps(normalized("160010603000002", "mesa", 1)),
                ),
            ],
        )

    geographies, mesas, results, blockers, coverage = _geographic_snapshot_records(
        state_directory=state,
        places_plan_id="places",
        mesas_plan_id="mesas",
        data_version="candidate-test",
        nomenclator_payload=nomenclator,
        nomenclator_hash=digest,
        election_slug="presidencia-2026-segunda-vuelta",
        expected_mesas=2,
    )

    assert {item["id"] for item in geographies} == {
        "CO",
        "scope:16",
        "scope:16001",
        "scope:1600106",
        "scope:160010603",
    }
    assert [item["id"] for item in mesas] == ["160010603000001", "160010603000002"]
    assert next(item for item in results if item["id"] == "precount-mesa-160010603000001")[
        "null_votes"
    ] == {"value": None, "status": "unknown"}
    assert next(item for item in results if item["id"] == "precount-mesa-160010603000001")[
        "registered_electors"
    ] == {"value": None, "status": "unavailable"}
    assert next(item for item in results if item["id"] == "precount-place-160010603")[
        "registered_electors"
    ] == {"value": None, "status": "unavailable"}
    assert blockers
    assert coverage == {
        "status": "sample_limited",
        "expected_polling_places": 1,
        "retrieved_polling_places": 1,
        "expected_mesas": 2,
        "retrieved_mesas": 2,
    }
