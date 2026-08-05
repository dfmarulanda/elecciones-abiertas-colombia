from __future__ import annotations

from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.reconciliation import (
    ArithmeticRule,
    Completeness,
    ElectorBoundRule,
    MesaIdentity,
    MesaRecord,
    aggregate_hierarchy,
    classify_completeness,
    classify_official_correction,
    compare_aggregates,
    evaluate_source_arithmetic,
    identity_conflicts,
    reconcile,
    validate_elector_bounds,
    validate_source_arithmetic,
)


def _record(source: str, mesa: str, votes: int, registered: int | None = 20) -> MesaRecord:
    values = {"candidate": votes, "blank": 1, "total": votes + 1}
    return MesaRecord(
        source,
        MesaIdentity("D", "M", "P", mesa),
        values,
        registered,
        "https://official.example/acta",
        release_id="release-v1",
        election_slug="presidencia-2026-r2",
        data_version="data-v1",
        source_type="pre_count",
        legal_status="preliminary",
        content_hash=("a" if source == "precount" else "b") * 64,
        retrieved_at="2026-08-03T12:00:00+00:00",
        parser_version="parser-v1",
        transform_version="transform-v1",
        field_states={field: "observed" for field in (*values, "registered")}
        if registered is not None
        else {field: "observed" for field in values},
    )


def test_source_specific_arithmetic_and_observed_elector_bound() -> None:
    first = _record("precount", "1", 9)
    second = MesaRecord("scrutiny", first.identity, {"reported": 10}, None)
    issues = validate_source_arithmetic(
        (first, second), (ArithmeticRule("precount", ("candidate", "blank"), "total"),)
    )
    assert issues == ()
    national = [item for item in aggregate_hierarchy((first, second)) if item.level == "national"]
    assert {item.source: item.registered_observed for item in national} == {
        "precount": 20,
        "scrutiny": None,
    }


def test_declared_arithmetic_checks_are_never_silently_skipped() -> None:
    record = MesaRecord("precount", MesaIdentity("D", "M", "P", "1"), {"candidate": 3})
    checks = evaluate_source_arithmetic(
        (record,), (ArithmeticRule("precount", ("candidate", "blank"), "total"),)
    )
    assert checks[0].status.value == "not_evaluable"
    assert checks[0].reason == "missing_published_fields:blank,total"


def test_conflicts_completeness_and_exact_hierarchy_comparison() -> None:
    one = _record("a", "1", 5)
    conflicting = _record("a", "1", 6)
    other_source = _record("b", "1", 7)
    duplicates, conflicts = identity_conflicts((one, conflicting, other_source))
    assert duplicates == {"a": (one.identity,)}
    assert conflicts == {"a": (one.identity,)}
    expected = (one.identity, MesaIdentity("D", "M", "P", "missing"))
    assert classify_completeness(expected, (one,)) == {
        one.identity: Completeness.COMPLETE,
        expected[1]: Completeness.MISSING,
    }
    aggregates = aggregate_hierarchy((_record("a", "2", 5), other_source))
    result = compare_aggregates(aggregates, "a", "b", "candidate", "municipality")
    assert result[0].signed_difference == -2
    assert result[0].affected_votes_estimate == 2


def test_duplicate_rows_cannot_be_rolled_up_and_corrections_are_explicit() -> None:
    first = _record("a", "1", 1)
    with pytest.raises(ValueError, match="duplicate"):
        aggregate_hierarchy((first, first))
    changed = _record("a", "1", 2)
    assert (
        classify_official_correction(first, changed, official_correction_marker=False)
        == "unmarked_revision"
    )
    assert (
        classify_official_correction(first, changed, official_correction_marker=True)
        == "official_correction"
    )


def test_comparison_does_not_substitute_zero_for_an_unpublished_field() -> None:
    identity = MesaIdentity("D", "M", "P", "1")
    left = MesaRecord("left", identity, {"candidate": 2})
    right = MesaRecord("right", identity, {"other": 2})
    aggregates = aggregate_hierarchy((left, right))
    assert compare_aggregates(aggregates, "left", "right", "candidate", "mesa") == ()


def test_elector_bound_requires_an_observed_registered_field_and_source_rule() -> None:
    identity = MesaIdentity("D", "M", "P", "1")
    bounded = MesaRecord("precount", identity, {"voters": 21}, registered=20)
    unavailable = MesaRecord("scrutiny", identity, {"voters": 99}, registered=None)
    issues = validate_elector_bounds(
        (bounded, unavailable),
        (ElectorBoundRule("precount", "voters"), ElectorBoundRule("scrutiny", "voters")),
    )
    assert len(issues) == 1
    assert issues[0].source == "precount"


def test_partial_fields_remain_unavailable_instead_of_becoming_implicit_zero() -> None:
    identity_one = MesaIdentity("D", "M", "P", "1")
    identity_two = MesaIdentity("D", "M", "P", "2")
    aggregates = aggregate_hierarchy(
        (
            MesaRecord("precount", identity_one, {"candidate": 3, "blank": 1}),
            MesaRecord("precount", identity_two, {"candidate": 4}),
        )
    )
    national = next(item for item in aggregates if item.level == "national")
    assert national.values == {"candidate": 7}
    assert national.unavailable_fields == ("blank",)


def test_mixed_source_coverage_must_be_explicitly_partitioned() -> None:
    one = _record("precount", "1", 4)
    documentary = _record("e14", "1", 4)
    with pytest.raises(ValueError, match="expected_by_source"):
        reconcile((one, documentary), expected_identities=(one.identity,))
    result = reconcile(
        (one, documentary),
        expected_by_source={"precount": (one.identity,), "e14": (one.identity,)},
    )
    assert result.completeness_by_source["precount"][one.identity] == Completeness.COMPLETE
    assert result.completeness_by_source["e14"][one.identity] == Completeness.COMPLETE
    assert len(result.output_hash) == 64


def test_reconciliation_blocks_rollups_without_exact_expected_identity_universe() -> None:
    row = _record("precount", "1", 4)
    result = reconcile((row,))
    assert result.aggregates == ()
    with pytest.raises(ValueError, match="complete expected identities"):
        reconcile(
            (row,),
            expected_by_source={"precount": (row.identity, MesaIdentity("D", "M", "P", "x"))},
        )


def test_authenticated_reconciliation_rejects_missing_or_incompatible_provenance() -> None:
    row = _record("precount", "1", 4)
    missing_hash = MesaRecord(
        row.source,
        row.identity,
        row.values,
        row.registered,
        row.source_url,
        release_id=row.release_id,
        election_slug=row.election_slug,
        data_version=row.data_version,
        source_type=row.source_type,
        legal_status=row.legal_status,
        field_states=row.field_states,
    )
    with pytest.raises(ValueError, match="provenance"):
        reconcile((missing_hash,))
    with pytest.raises(ValueError, match="HTTPS source URLs"):
        reconcile((replace(row, source_url="http://official.example/acta"),))
    with pytest.raises(ValueError, match="timezone-aware"):
        reconcile((replace(row, retrieved_at="2026-08-03T12:00:00"),))
    incompatible = MesaRecord(
        "scrutiny",
        row.identity,
        row.values,
        row.registered,
        row.source_url,
        release_id="other-release",
        election_slug=row.election_slug,
        data_version=row.data_version,
        source_type="scrutiny",
        legal_status="official_scrutiny",
        content_hash="c" * 64,
        retrieved_at="2026-08-03T12:00:00+00:00",
        parser_version="parser-v1",
        transform_version="transform-v1",
        field_states=row.field_states,
    )
    with pytest.raises(ValueError, match="share release"):
        reconcile((row, incompatible))


def test_aggregate_grain_cannot_be_coerced_into_a_mesa_record() -> None:
    mesa = _record("precount", "1", 4)
    municipality_attached_to_mesa_identity = replace(
        mesa,
        published_grain="municipality",
    )
    with pytest.raises(ValueError, match="published_grain='mesa'"):
        reconcile((municipality_attached_to_mesa_identity,))
    with pytest.raises(ValueError, match="published at mesa grain"):
        aggregate_hierarchy((municipality_attached_to_mesa_identity,))
