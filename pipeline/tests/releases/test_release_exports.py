from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from elecciones_pipeline.quality import PERMANENT_DISCLOSURE_EN, PERMANENT_DISCLOSURE_ES
from elecciones_pipeline.releases import (
    CurrentReleasePointer,
    ReleaseError,
    activate_current_release,
    build_candidate_manifest,
    export_dataset,
    publish_release,
    rollback_current_release,
)

from ..statistical_artifact_helper import passing_simulation_summary


def source(*, final: bool = False) -> dict[str, object]:
    source_type = "final_declaration" if final else "pre_count"
    return {
        "id": "final" if final else "precount",
        "source_type": source_type,
        "legal_status": "controlling_final" if final else "preliminary",
        "source_url": f"https://official.example.co/{source_type}",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "content_hash": "a" * 64,
        "media_type": "application/json",
        "byte_size": 123,
        "parser_version": "parser-v1",
        "transform_version": "transform-v1",
        "published_grain": "mesa",
        "coverage": {
            "expected": 1,
            "retrieved": 1,
            "parsed": 1,
            "missing": 0,
            "ambiguous": 0,
            "excluded": 0,
        },
    }


def fact() -> dict[str, object]:
    return {
        "source_id": "final",
        "source_type": "final_declaration",
        "legal_status": "controlling_final",
        "source_url": "https://official.example.co/final_declaration",
        "retrieved_at": "2026-01-01T00:00:00Z",
        "content_hash": "a" * 64,
        "parser_version": "parser-v1",
        "transform_version": "transform-v1",
        "data_version": "r1",
        "source_layer": "final_declaration",
        "grain": "mesa",
        "published_grain": "mesa",
        "inferred": False,
        "identity": {"department": "D", "municipality": "M", "place": "P", "mesa": "1"},
        "values": {"candidate": 1},
        "value_state": "observed",
        "value": 1,
    }


def passing_statistics() -> dict[str, object]:
    return passing_simulation_summary()


def candidate(
    artifact: object, *, sources: list[dict[str, object]], synthetic: bool = False
) -> dict[str, object]:
    return build_candidate_manifest(
        release_id="r1",
        election_slug="presidencia-2026",
        methodology_version="audit-priority-v1.0.0",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        git_commit="a" * 40,
        sources=sources,
        datasets=[artifact],
        artifact_base_url="https://artifacts.example.co",
        dataset_schema_url="https://schemas.example.co/result-fact.schema.json",
        dataset_titles={"facts": {"es": "Hechos", "en": "Facts"}},
        notes={"es": "Datos oficiales.", "en": "Official data."},
        synthetic=synthetic,
        aggregate_reconciled=True,
        statistical_validation_passed=True,
        wording_validation_passed=True,
    )


def test_exports_are_sorted_content_addressed_and_idempotent(tmp_path: Path) -> None:
    rows = [{"b": 2, "a": "z"}, {"a": "a", "b": 1}]
    for format_name in ("json", "csv", "parquet"):
        first = export_dataset(rows, name="facts", directory=tmp_path, format=format_name)
        second = export_dataset(
            list(reversed(rows)), name="facts", directory=tmp_path, format=format_name
        )
        assert first == second
        artifact = tmp_path / first.key
        assert first.sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert first.row_count == 2 and first.byte_size == artifact.stat().st_size


def test_synthetic_and_missing_final_source_cannot_publish(tmp_path: Path) -> None:
    artifact = export_dataset([], name="facts", directory=tmp_path, format="json")
    synthetic = candidate(artifact, sources=[source()], synthetic=True)
    with pytest.raises(ReleaseError):
        publish_release(
            synthetic,
            facts=(),
            directory=tmp_path,
            current_pointer=tmp_path / "current.json",
            statistical_summary=passing_statistics(),
            permanent_wording=f"{PERMANENT_DISCLOSURE_ES}\n{PERMANENT_DISCLOSURE_EN}",
            allowed_hosts={"official.example.co", "artifacts.example.co", "schemas.example.co"},
        )
    missing_final = candidate(artifact, sources=[source()])
    with pytest.raises(ReleaseError, match="final-declaration"):
        publish_release(
            missing_final,
            facts=(),
            directory=tmp_path,
            current_pointer=tmp_path / "current.json",
            statistical_summary=passing_statistics(),
            permanent_wording=f"{PERMANENT_DISCLOSURE_ES}\n{PERMANENT_DISCLOSURE_EN}",
            allowed_hosts={"official.example.co", "artifacts.example.co", "schemas.example.co"},
        )


def test_publish_remains_blocked_until_independent_pass_b(tmp_path: Path) -> None:
    artifact = export_dataset([fact()], name="facts", directory=tmp_path, format="json")
    comparison = source()
    manifest = candidate(artifact, sources=[source(final=True), comparison])
    comparison_fact = dict(fact())
    comparison_fact.update(
        {
            "source_id": "precount",
            "source_type": "pre_count",
            "legal_status": "preliminary",
            "source_url": "https://official.example.co/pre_count",
            "source_layer": "pre_count",
        }
    )
    pointer_path = tmp_path / "current.json"
    with pytest.raises(ValueError, match="pass_b_pending"):
        publish_release(
            manifest,
            facts=[fact(), comparison_fact],
            directory=tmp_path,
            current_pointer=pointer_path,
            statistical_summary=passing_statistics(),
            permanent_wording=f"{PERMANENT_DISCLOSURE_ES}\n{PERMANENT_DISCLOSURE_EN}",
            allowed_hosts={"official.example.co", "artifacts.example.co", "schemas.example.co"},
        )
    assert not pointer_path.exists()


def test_context_only_baseline_can_publish_without_activation_or_statistical_signals(
    tmp_path: Path,
) -> None:
    artifact = export_dataset([], name="facts", directory=tmp_path, format="json")
    contextual = source()
    contextual.update(
        {
            "id": "history",
            "source_type": "contextual_baseline",
            "legal_status": "context_only",
        }
    )
    manifest = candidate(artifact, sources=[contextual])
    manifest.update(
        {
            "release_class": "context_only",
            "statistical_validation_passed": False,
        }
    )
    manifest["datasets"][0]["filters"] = {
        "source_type": "contextual_baseline",
        "legal_status": "context_only",
    }

    result = publish_release(
        manifest,
        facts=(),
        directory=tmp_path,
        current_pointer=tmp_path / "current.json",
        statistical_summary={},
        permanent_wording=f"{PERMANENT_DISCLOSURE_ES}\n{PERMANENT_DISCLOSURE_EN}",
        allowed_hosts={"official.example.co", "artifacts.example.co", "schemas.example.co"},
        activate=False,
    )

    assert result is None
    assert not (tmp_path / "current.json").exists()
    published = json.loads((tmp_path / "manifests" / "r1.json").read_text())
    assert published["status"] == "published"
    assert published["release_class"] == "context_only"
    assert published["statistical_validation_passed"] is False


def test_pointer_activation_and_rollback_are_atomic_replacements(tmp_path: Path) -> None:
    current = tmp_path / "current.json"
    first = CurrentReleasePointer.create(
        release_id="r1",
        manifest_path="manifests/r1.json",
        synthetic=False,
        activated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = CurrentReleasePointer.create(
        release_id="r2",
        manifest_path="manifests/r2.json",
        synthetic=False,
        activated_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    activate_current_release(current, first)
    activate_current_release(current, second)
    rollback_current_release(current, first)
    assert json.loads(current.read_text()) == {
        "activated_at": "2026-01-01T00:00:00Z",
        "manifest_path": "manifests/r1.json",
        "release_id": "r1",
        "synthetic": False,
    }
