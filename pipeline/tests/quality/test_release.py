from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from elecciones_pipeline.analytics.priority import DISCLOSURE_EN, DISCLOSURE_ES
from elecciones_pipeline.quality import (
    QualityError,
    canonical_hash,
    exact_rollup,
    scan_public_text,
    validate_arithmetic,
    verify_release,
)
from elecciones_pipeline.quality.release import (
    _statistical_errors,
    audit_allowed_hosts,
    validate_manifest,
    validate_value_states,
)

from ..statistical_artifact_helper import passing_simulation_summary, trusted_simulation_inputs

FIXTURES = Path(__file__).parents[1] / "fixtures" / "release_quality_cases.json"
HASH = "a" * 64
SOURCE_URL = "https://official.example.co/results"


def source(
    *,
    identifier: str = "precount",
    source_type: str = "pre_count",
    legal_status: str = "preliminary",
) -> dict[str, object]:
    return {
        "id": identifier,
        "source_type": source_type,
        "legal_status": legal_status,
        "source_url": SOURCE_URL,
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "content_hash": HASH,
        "media_type": "application/json",
        "byte_size": 42,
        "parser_version": "parser-v1",
        "transform_version": "transform-v1",
        "published_grain": "mesa",
        "coverage": {
            "expected": 2,
            "retrieved": 2,
            "parsed": 2,
            "missing": 0,
            "ambiguous": 0,
            "excluded": 0,
        },
    }


def dataset() -> dict[str, object]:
    return {
        "id": "facts-json",
        "title": {"es": "Hechos electorales", "en": "Election facts"},
        "format": "json",
        "url": "https://official.example.co/datasets/facts.json",
        "schema_url": "https://official.example.co/schemas/facts.json",
        "record_count": 2,
        "byte_size": 200,
        "content_hash": HASH,
        "filters": {"grain": "mesa"},
    }


def manifest(
    *,
    status: str = "fixture",
    synthetic: bool = True,
    sources: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "$schema": "https://eleccionesabiertas.co/schemas/release-manifest.schema.json",
        "schema_version": "1.0.0",
        "release_id": "r1",
        "election_slug": "presidencia-2026",
        "data_version": "r1",
        "status": status,
        "synthetic": synthetic,
        "created_at": "2026-01-01T00:00:00+00:00",
        "methodology_version": "method-v1",
        "parser_versions": {item["id"]: "parser-v1" for item in (sources or [source()])},
        "git_commit": "0123456789abcdef",
        "sources": sources or [source()],
        "datasets": [dataset()],
        "aggregate_reconciled": True,
        "statistical_validation_passed": True,
        "wording_validation_passed": True,
        "notes": {"es": "Datos con procedencia.", "en": "Data with provenance."},
    }


def fact(
    mesa: str,
    votes: int,
    *,
    source_id: str = "precount",
    source_type: str = "pre_count",
    legal_status: str = "preliminary",
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "source_id": source_id,
        "source_type": source_type,
        "legal_status": legal_status,
        "source_url": SOURCE_URL,
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "content_hash": HASH,
        "parser_version": "parser-v1",
        "transform_version": "transform-v1",
        "data_version": "r1",
        "source_layer": source_type,
        "grain": "mesa",
        "published_grain": "mesa",
        "identity": {"department": "D", "municipality": "M", "place": "P", "mesa": mesa},
        "values": {"candidate": votes, "blank": 1, "total": votes + 1},
        "value_state": "observed",
        "value": votes,
    }
    row.update(extra)
    return row


def simulation_summary(**overrides: object) -> dict[str, object]:
    result = passing_simulation_summary()
    result.update(overrides)
    return result


def test_frozen_cases_document_every_required_release_failure() -> None:
    cases = json.loads(FIXTURES.read_text())
    assert set(cases) >= {
        "arithmetic_failure",
        "duplicate_identity",
        "missing_source",
        "official_correction",
        "ambiguous_join",
        "transcription_mismatch",
        "one_vote_documentary_difference",
    }
    assert "never publish" in cases["fixture_notice"].lower()
    assert (
        cases["one_vote_documentary_difference"]["document"]
        - cases["one_vote_documentary_difference"]["precount"]
        == 1
    )


def test_complete_manifest_uses_frozen_source_enums_and_dataset_contract() -> None:
    assert validate_manifest(manifest()) == ()
    invalid = manifest()
    first_source = invalid["sources"][0]
    assert isinstance(first_source, dict)
    first_source["legal_status"] = "pre_count"
    assert "provenance" in {item.code for item in validate_manifest(invalid)}


def test_arithmetic_duplicate_and_source_traceability_are_gated() -> None:
    cases = json.loads(FIXTURES.read_text())
    bad = fact("1", 3, values=cases["arithmetic_failure"])
    assert (
        validate_arithmetic((bad,), {"precount": (("candidate", "blank"), "total")})[0].code
        == "arithmetic"
    )
    report = verify_release(
        manifest(), facts=(fact("1", 2), fact("1", 2), fact("2", 2, source_id="missing"))
    )
    assert {"duplicate_identity", "traceability", "aggregate_reconciliation"} <= {
        item.code for item in report.errors
    }


def test_zero_is_observed_not_unknown_or_unavailable() -> None:
    assert validate_value_states((fact("1", 0),)) == ()
    errors = validate_value_states(
        (fact("2", 0, value_state="unknown"), fact("3", 0, value_state="unavailable"))
    )
    assert [item.code for item in errors] == ["value_state", "value_state"]


def test_wide_rollups_are_exact_and_reject_partial_field_sets() -> None:
    totals = exact_rollup((fact("1", 2), fact("2", 3)))
    by_level = {row["level"]: row for row in totals if row["level"] != "mesa"}
    assert by_level["national"]["values"] == {"blank": 2, "candidate": 5, "total": 7}
    with pytest.raises(QualityError, match="partial metric field set"):
        exact_rollup((fact("1", 2), fact("2", 3, values={"candidate": 3, "total": 3})))

    declared = fact(
        "rollup",
        5,
        grain="place",
        published_grain="place",
        is_rollup=True,
        values={"candidate": 5, "blank": 2, "total": 7},
    )
    matching = verify_release(manifest(), facts=(fact("1", 2), fact("2", 3), declared))
    assert "aggregate_reconciliation" not in {item.code for item in matching.errors}
    broken = dict(declared)
    broken["values"] = {"candidate": 5, "blank": 2, "total": 8}
    assert "aggregate_reconciliation" in {
        item.code
        for item in verify_release(manifest(), facts=(fact("1", 2), fact("2", 3), broken)).errors
    }


def test_long_facts_are_supported_by_exact_rollup() -> None:
    first = fact("1", 2, metric="votes", record_type="candidate", party_id="p1")
    second = fact("2", 3, metric="votes", record_type="candidate", party_id="p1")
    first.pop("values")
    second.pop("values")
    totals = exact_rollup((first, second))
    national = next(row for row in totals if row["level"] == "national")
    assert national["value"] == 5
    assert national["source_layer"] == "pre_count"


def test_provenance_coverage_inference_and_ambiguous_join_fail() -> None:
    broken = manifest()
    source_coverage = broken["sources"][0]["coverage"]  # type: ignore[index]
    assert isinstance(source_coverage, dict)
    source_coverage.update({"expected": 2, "retrieved": 1, "parsed": 2})
    incomplete = fact(
        "1", 1, inferred=True, join_status="ambiguous", methodology_version="method-v0"
    )
    incomplete.pop("parser_version")
    mismatched = fact("2", 1, content_hash="b" * 64)
    codes = {item.code for item in verify_release(broken, facts=(incomplete, mismatched)).errors}
    assert {"coverage", "mesa_inference", "ambiguous_join", "methodology", "provenance"} <= codes


@pytest.mark.parametrize(
    "source_type,legal_status",
    [("final_declaration", "controlling_final"), ("scrutiny", "official_scrutiny")],
)
def test_final_and_scrutiny_facts_require_explicit_published_grain(
    source_type: str, legal_status: str
) -> None:
    source_id = source_type
    release = manifest(
        sources=[source(identifier=source_id, source_type=source_type, legal_status=legal_status)]
    )
    missing = fact(
        "1",
        1,
        source_id=source_id,
        source_type=source_type,
        legal_status=legal_status,
        inferred=False,
    )
    missing.pop("published_grain")
    explicit = fact(
        "2",
        1,
        source_id=source_id,
        source_type=source_type,
        legal_status=legal_status,
        inferred=False,
        published_grain="mesa",
    )
    assert "source_grain" in {
        item.code for item in verify_release(release, facts=(missing,)).errors
    }
    assert "source_grain" not in {
        item.code for item in verify_release(release, facts=(explicit,)).errors
    }


def test_candidate_needs_facts_actual_simulation_shape_and_exact_audit_disclosures() -> None:
    candidate = manifest(status="candidate", synthetic=False)
    no_facts = verify_release(
        candidate,
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    assert "facts" in {item.code for item in no_facts.errors}
    failed = verify_release(
        candidate,
        facts=(fact("1", 1),),
        statistical_summary=simulation_summary(false_discovery_gate_passed=False),
        permanent_wording="not the required disclosure",
    )
    assert {"statistics", "permanent_wording"} <= {item.code for item in failed.errors}
    passed = verify_release(
        candidate,
        facts=(fact("1", 1),),
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    assert "aggregate_reconciliation" in {item.code for item in passed.errors}


def test_statistical_release_gate_rejects_spoofed_booleans_and_all_flag_fdr() -> None:
    candidate = manifest(status="candidate", synthetic=False)
    spoofed = {
        "simulations": 100,
        "false_discovery_gate_passed": True,
        "injected_discrepancy_gate_passed": True,
        "release_gate_passed": True,
    }
    assert "statistics" in {
        item.code
        for item in verify_release(
            candidate,
            facts=(fact("1", 1),),
            statistical_summary=spoofed,
            permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
        ).errors
    }
    all_flag = simulation_summary(
        confusion_totals={"true_positive": 0, "false_positive": 100, "false_negative": 0}
    )
    all_flag["empirical_fdr"] = 1.0
    payload = dict(all_flag)
    payload.pop("artifact_hash")
    all_flag["artifact_hash"] = canonical_hash(payload)
    assert "statistics" in {
        item.code
        for item in verify_release(
            candidate,
            facts=(fact("1", 1),),
            statistical_summary=all_flag,
            permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
        ).errors
    }


def test_statistical_artifact_recomputes_run_fdp_confusion_code_and_cohort_bindings() -> None:
    def rehash(summary: dict[str, object]) -> dict[str, object]:
        payload = dict(summary)
        payload.pop("artifact_hash", None)
        summary["artifact_hash"] = canonical_hash(payload)
        return summary

    spoofed_fdp = deepcopy(simulation_summary())
    spoofed_fdp["empirical_fdr"] = 1 / 3
    assert _statistical_errors(rehash(spoofed_fdp), release_id="r1")

    spoofed_confusion = deepcopy(simulation_summary())
    confusion = dict(spoofed_confusion["confusion_totals"])  # type: ignore[arg-type]
    confusion["true_positive"] = 99
    spoofed_confusion["confusion_totals"] = confusion
    assert _statistical_errors(rehash(spoofed_confusion), release_id="r1")

    stale_code = deepcopy(simulation_summary())
    bindings = deepcopy(stale_code["detector_bindings"])
    assert isinstance(bindings, dict)
    peer_binding = bindings["peer"]
    assert isinstance(peer_binding, dict)
    peer_binding["code_hash"] = "f" * 64
    stale_code["detector_bindings"] = bindings
    stale_code["detector_hash"] = canonical_hash(bindings)
    stale_code["methodology_hash"] = canonical_hash(
        {
            "detectors": bindings,
            "simulation_methodology_version": stale_code["methodology_version"],
        }
    )
    assert _statistical_errors(rehash(stale_code), release_id="r1")

    stale_run_cohort = deepcopy(simulation_summary())
    runs = list(stale_run_cohort["alternative_runs"])  # type: ignore[arg-type]
    first_run = dict(runs[0])  # type: ignore[arg-type]
    first_run["peer_cohort_hash"] = "e" * 64
    runs[0] = first_run
    stale_run_cohort["alternative_runs"] = tuple(runs)
    assert _statistical_errors(rehash(stale_run_cohort), release_id="r1")


def test_statistical_replay_rejects_a_rehashed_perfect_fabrication() -> None:
    """A caller cannot turn a summary plus hashes into analyzer evidence."""
    trusted = trusted_simulation_inputs()
    real = passing_simulation_summary()
    genuine_errors = _statistical_errors(
        real,
        release_id="r1",
        replay_inputs=trusted,
        trusted_registry_artifact_hashes=frozenset({str(trusted.registry_artifact_hash)}),
    )
    assert not any("injection spec is invalid" in finding.detail for finding in genuine_errors)
    stale_key_schema = deepcopy(real)
    stale_key_schema["injection_spec"] = {
        **stale_key_schema["injection_spec"],  # type: ignore[arg-type]
        "key_schema": "canonical-json-[family_id,mesa_id]",
    }
    payload = dict(stale_key_schema)
    payload.pop("artifact_hash")
    stale_key_schema["artifact_hash"] = canonical_hash(payload)
    assert any(
        "injection spec is invalid" in finding.detail
        for finding in _statistical_errors(
            stale_key_schema,
            release_id="r1",
            replay_inputs=trusted,
            trusted_registry_artifact_hashes=frozenset({str(trusted.registry_artifact_hash)}),
        )
    )
    fabricated = deepcopy(real)
    fabricated["injected_discrepancy_detection_rate"] = 1.0
    fabricated["confusion_totals"] = {
        "true_positive": 100,
        "false_positive": 0,
        "false_negative": 0,
    }
    fabricated["release_gate_passed"] = True
    fabricated["injected_discrepancy_gate_passed"] = True
    payload = dict(fabricated)
    payload.pop("artifact_hash")
    fabricated["artifact_hash"] = canonical_hash(payload)
    assert _statistical_errors(
        fabricated,
        release_id="r1",
        replay_inputs=trusted,
        trusted_registry_artifact_hashes=frozenset({str(trusted.registry_artifact_hash)}),
    )

    # Even a byte-valid, internally consistent non-decision field cannot be
    # smuggled through: the complete regenerated artifact is compared.
    replay_mismatch = deepcopy(real)
    replay_mismatch["limitations"] = ["manufactured helper claim"]
    payload = dict(replay_mismatch)
    payload.pop("artifact_hash")
    replay_mismatch["artifact_hash"] = canonical_hash(payload)
    assert any(
        "does not exactly match trusted analyzer replay" in finding.detail
        for finding in _statistical_errors(
            replay_mismatch,
            release_id="r1",
            replay_inputs=trusted,
            trusted_registry_artifact_hashes=frozenset({str(trusted.registry_artifact_hash)}),
        )
    )


def test_published_release_needs_controlling_final_source_and_published_grain() -> None:
    final = source(
        identifier="final", source_type="final_declaration", legal_status="controlling_final"
    )
    published = manifest(status="published", synthetic=False, sources=[final])
    fact_row = fact(
        "1",
        1,
        source_id="final",
        source_type="final_declaration",
        legal_status="controlling_final",
        inferred=False,
        published_grain="mesa",
    )
    report = verify_release(
        published,
        facts=(fact_row,),
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    assert "aggregate_reconciliation" in {item.code for item in report.errors}
    without_final = manifest(status="published", synthetic=False)
    report = verify_release(
        without_final,
        facts=(fact("1", 1),),
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    assert "final_declaration" in {item.code for item in report.errors}


def test_reconciliation_compares_exact_same_field_same_grain_values() -> None:
    final = source(
        identifier="final", source_type="final_declaration", legal_status="controlling_final"
    )
    precount = source()
    candidate = manifest(status="candidate", synthetic=False, sources=[final, precount])
    final_fact = fact(
        "1",
        1,
        source_id="final",
        source_type="final_declaration",
        legal_status="controlling_final",
        inferred=False,
    )
    matching = fact("1", 1)
    report = verify_release(
        candidate,
        facts=(final_fact, matching),
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    codes = {item.code for item in report.errors}
    assert "aggregate_reconciliation" not in codes
    assert {"statistics_pass_b_pending", "outcome_pass_b_pending"} <= codes

    unequal = fact("1", 2)
    unequal_report = verify_release(
        candidate,
        facts=(final_fact, unequal),
        statistical_summary=simulation_summary(),
        permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}",
    )
    assert "aggregate_reconciliation" in {item.code for item in unequal_report.errors}


def test_manifest_grain_and_both_context_markers_fail_closed() -> None:
    final = source(
        identifier="final", source_type="final_declaration", legal_status="controlling_final"
    )
    mismatched = fact(
        "1",
        1,
        source_id="final",
        source_type="final_declaration",
        legal_status="controlling_final",
        inferred=False,
        grain="municipality",
        published_grain="municipality",
    )
    assert "source_grain" in {
        item.code for item in verify_release(manifest(sources=[final]), facts=(mismatched,)).errors
    }

    contextual = source(
        identifier="history",
        source_type="contextual_baseline",
        legal_status="context_only",
    )
    contextual_fact = fact(
        "1",
        1,
        source_id="history",
        source_type="contextual_baseline",
        legal_status="context_only",
        source_layer="pre_count",
    )
    assert "analytics_context_only" in {
        item.code
        for item in verify_release(manifest(sources=[contextual]), facts=(contextual_fact,)).errors
    }
    assert "analytics_context_only" in {
        item.code for item in verify_release(manifest(sources=[contextual])).errors
    }


def test_context_only_class_requires_contextual_provenance_and_disabled_statistics() -> None:
    contextual = source(
        identifier="history", source_type="contextual_baseline", legal_status="context_only"
    )
    candidate = manifest(status="candidate", synthetic=False, sources=[contextual])
    candidate.update({"release_class": "context_only", "statistical_validation_passed": False})
    candidate["datasets"][0]["filters"] = {
        "source_type": "contextual_baseline",
        "legal_status": "context_only",
    }
    assert validate_manifest(candidate) == ()
    assert verify_release(candidate, permanent_wording=f"{DISCLOSURE_ES}\n{DISCLOSURE_EN}").passed

    invalid = dict(candidate)
    invalid["statistical_validation_passed"] = True
    assert "context_only" in {item.code for item in validate_manifest(invalid)}


def test_partial_rollups_pii_and_allowlist_are_gated() -> None:
    partial = manifest()
    coverage = partial["sources"][0]["coverage"]  # type: ignore[index]
    assert isinstance(coverage, dict)
    coverage.update({"expected": 2, "retrieved": 1, "parsed": 1, "missing": 1})
    report = verify_release(
        partial,
        facts=(fact("1", 1, is_rollup=True, grain="place"),),
        public_text=("ana@example.co +57 300 123 4567 CC 12345678",),
        public_urls=("https://evil.example/a",),
        allowed_hosts={"official.example.co"},
    )
    assert {"partial_rollup", "pii", "allowlist"} <= {item.code for item in report.errors}
    assert canonical_hash({"b": [2, 1], "a": 1}) == canonical_hash({"a": 1, "b": [2, 1]})
    assert (
        audit_allowed_hosts(
            ("https://official.example.co/a", "https://evil.example/a"), {"official.example.co"}
        )[0].code
        == "allowlist"
    )
    assert len(scan_public_text(("ana@example.co",))) == 1
