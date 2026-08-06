from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import elecciones_pipeline.analytics.simulations as simulations
import pytest
from elecciones_pipeline.analytics.peer_signals import (
    MesaMetrics,
    cohort_digest,
    family_digest,
)
from elecciones_pipeline.analytics.spatial import (
    PEER_METHODOLOGY_VERSION,
    SpatialMesa,
    spatial_cohort_digest,
    spatial_family_digest,
    spatial_mesa_digest,
    spatial_mesa_membership_digest,
)


def _peer_family(
    count: int = 4,
    *,
    data_version: str = "release-r2-v1",
    metric: str = "candidate_share",
) -> tuple[MesaMetrics, ...]:
    identifiers = tuple(f"mesa-{index:02d}" for index in range(count))
    expected_digest = family_digest(identifiers)
    input_hash = "a" * 64
    cohort_hash = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version=data_version,
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric=metric,  # type: ignore[arg-type]
        candidate_id="candidate-a" if metric == "candidate_share" else None,
        expected_family_count=len(identifiers),
        expected_family_digest=expected_digest,
        input_artifact_hash=input_hash,
    )
    return tuple(
        MesaMetrics(
            mesa_id=identifier,
            place_id="place-1",
            municipality_id="municipality-1",
            department_id="department-1",
            metric=metric,  # type: ignore[arg-type]
            registered=1_200,
            ballots=1_000,
            candidate_votes=300 if metric == "candidate_share" else 0,
            valid_votes=950,
            blank_votes=20,
            null_unmarked_votes=50,
            candidate_id="candidate-a" if metric == "candidate_share" else None,
            election_slug="presidencia-2026-r2",
            data_version=data_version,
            source_layer="pre_count",
            source_type="pre_count",
            legal_status="preliminary",
            expected_family_count=len(identifiers),
            expected_family_digest=expected_digest,
            input_artifact_hash=input_hash,
            cohort_hash=cohort_hash,
            source_links=("https://official.example/results.json",),
            candidate_total_votes=930,
            denominator_provenance="joined_official",
        )
        for identifier in identifiers
    )


def test_end_to_end_validation_separates_null_fwer_and_per_run_alternative_fdp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = replace(simulations.CI_PROFILE, name="test-seed-17", seed=17)
    captured: list[tuple[MesaMetrics, ...]] = []

    def fake_peer_signals(rows: object) -> tuple[SimpleNamespace, ...]:
        family = tuple(rows)  # type: ignore[arg-type]
        call_index = len(captured)
        captured.append(family)
        family_id = "|".join(
            (
                family[0].data_version,
                family[0].election_slug,
                family[0].source_layer,
                family[0].metric,
                str(family[0].candidate_id),
            )
        )
        flagged: set[str] = set()
        if call_index >= 100:
            target = max(
                family,
                key=lambda row: row.candidate_votes / max(row.valid_votes, 1),
            )
            flagged.add(target.mesa_id)
            if (call_index - 100) % 2 == 0:
                false_positive = next(row for row in family if row.mesa_id != target.mesa_id)
                flagged.add(false_positive.mesa_id)
        return tuple(
            SimpleNamespace(
                family_id=family_id,
                mesa_id=row.mesa_id,
                signal=False,
                research_signal=row.mesa_id in flagged,
            )
            for row in family
        )

    monkeypatch.setattr(simulations, "peer_signals", fake_peer_signals)
    monkeypatch.setattr(
        simulations, "peer_research_detection", lambda item: bool(item.research_signal)
    )
    summary = simulations.run_end_to_end_validation(
        release_id="release-r2-v1",
        peer_records=_peer_family(),
        simulations=100,
        seed=17,
        profile=profile,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    assert summary.simulations == 200
    assert summary.null_simulations == summary.alternative_simulations == 100
    assert summary.family_error_count == 0
    assert summary.false_discovery_probability == 0.0
    assert summary.confusion_totals == {
        "true_positive": 50,
        "false_positive": 100,
        "false_negative": 50,
    }
    assert summary.empirical_fdr == pytest.approx(0.75)
    assert summary.injected_discrepancy_detection_rate == 0.5
    assert not summary.false_discovery_gate_passed
    assert not summary.release_gate_passed
    assert {run.fdp for run in summary.alternative_runs} == {0.5, 1.0}
    assert all(
        not run.public_flagged_keys for run in (*summary.null_runs, *summary.alternative_runs)
    )
    assert {run.injection_direction for run in summary.alternative_runs} == {"positive", "negative"}
    assert all(not run.injected_keys and run.fdp is None for run in summary.null_runs)

    original_hash = _peer_family()[0].input_artifact_hash
    assert len(captured) == 200
    for family in captured:
        first = family[0]
        assert first.input_artifact_hash != original_hash
        assert all(row.input_artifact_hash == first.input_artifact_hash for row in family)
        assert first.cohort_hash == cohort_digest(
            election_slug=first.election_slug,
            data_version=first.data_version,
            source_layer=first.source_layer,
            source_type=first.source_type,
            legal_status=first.legal_status,
            metric=first.metric,
            candidate_id=first.candidate_id,
            expected_family_count=first.expected_family_count,
            expected_family_digest=first.expected_family_digest,
            input_artifact_hash=first.input_artifact_hash,
        )
    payload = summary.artifact_payload()
    assert "attestation" not in payload and "artifact_hash" not in payload
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert summary.artifact_hash == hashlib.sha256(encoded.encode()).hexdigest()
    assert summary.attestation is not None
    assert summary.attestation.attests_artifact_hash == summary.artifact_hash


def test_simulation_keys_are_canonical_and_original_cohort_must_authenticate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert simulations.signal_key("peer", "a|b", "c") != simulations.signal_key(
        "spatial", "a", "b|c"
    )
    key = simulations.signal_key("peer", "family|with|separators", "mesa|1")
    assert simulations.decode_signal_key(key) == ("peer", "family|with|separators", "mesa|1")
    with pytest.raises(ValueError, match="canonical"):
        simulations.decode_signal_key('["peer", "family", "mesa"]')

    stale = tuple(replace(row, cohort_hash="f" * 64) for row in _peer_family())
    monkeypatch.setattr(simulations, "peer_signals", lambda rows: ())
    with pytest.raises(ValueError, match="declared cohort"):
        simulations.run_end_to_end_validation(
            release_id="release-r2-v1",
            peer_records=stale,
            simulations=100,
        )


def test_real_peer_detector_has_deterministic_null_control_and_injection_power() -> None:
    # The strict research endpoint requires a pool large enough for the plug-in
    # predictive tail to be calibrated, so the calibration family must exceed
    # that floor: a 31-peer family can no longer produce any detection at all,
    # which would make this null control vacuous rather than passing.
    rows = _peer_family(220, data_version="real-detector-validation-v1")
    profile = replace(simulations.CI_PROFILE, name="test-seed-29", seed=29)
    first = simulations.run_end_to_end_validation(
        release_id="real-detector-validation-v1",
        peer_records=rows,
        simulations=100,
        seed=29,
        profile=profile,
        injected_discrepancies=1,
        injection_size=0.9,
    )
    replay = simulations.run_end_to_end_validation(
        release_id="real-detector-validation-v1",
        peer_records=rows,
        simulations=100,
        seed=29,
        profile=profile,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    # Same measurements, same content hash.  The attestations differ in wall
    # clock even on one machine, which is exactly why they are not hashed.
    assert first.artifact_payload() == replay.artifact_payload()
    assert first.artifact_hash == replay.artifact_hash
    assert first.attestation != replay.attestation
    assert replace(first, attestation=None) == replace(replay, attestation=None)
    assert first.null_simulations == first.alternative_simulations == 100
    # The intentionally misspecified, heavy-tailed null is a stress design;
    # it must expose when the detector fails its calibration gate rather than
    # manufacture a passing result from a thin binomial simulator.
    assert first.family_error_count > 0
    assert first.family_error_upper_confidence >= 0.0
    assert first.empirical_fdr >= 0.0
    assert 0.0 < first.injected_discrepancy_detection_rate < 1.0
    assert any(run.flagged_keys for run in (*first.null_runs, *first.alternative_runs))
    assert all(not run.public_flagged_keys for run in (*first.null_runs, *first.alternative_runs))
    power = next(iter(first.power_by_family.values()))
    assert 0.0 <= float(power["lower_confidence_bound"]) <= 1.0
    assert isinstance(first.false_discovery_gate_passed, bool)
    assert isinstance(first.injected_discrepancy_gate_passed, bool)
    assert not first.release_gate_passed
    assert not first.production_eligible
    assert first.profile_name == profile.name
    assert first.profile_hash
    assert first.attestation is not None and first.attestation.runtime_fingerprint
    assert set(first.detector_bindings) == {"peer"}
    assert first.power_by_stratum
    assert not first.trusted_input_registry_verified
    assert not first.external_family_ledger_verified
    assert all(
        injection.realized_effect_pp > 0
        for run in first.alternative_runs
        for injection in run.injections
    )


def _perfect_detector(arm: int) -> object:
    """A detector that flags exactly the injected mesa and nothing else.

    This is not a claim about the real detector.  It is the only way to reach
    the branch where both computed gates pass, which is the branch the
    hardcoded ``release_gate_passed=False`` made unreachable.
    """
    calls = {"index": 0}

    def fake_peer_signals(rows: object) -> tuple[SimpleNamespace, ...]:
        family = tuple(rows)  # type: ignore[arg-type]
        call_index = calls["index"]
        calls["index"] += 1
        family_id = "|".join(
            (
                family[0].data_version,
                family[0].election_slug,
                family[0].source_layer,
                family[0].metric,
                str(family[0].candidate_id),
            )
        )
        flagged: set[str] = set()
        if call_index >= arm:
            shares = sorted(row.candidate_votes / max(row.valid_votes, 1) for row in family)
            median = shares[len(shares) // 2]
            # The injected mesa is the one furthest from the family centre in
            # either direction, so this catches negative injections too.
            target = max(
                family,
                key=lambda row: abs(row.candidate_votes / max(row.valid_votes, 1) - median),
            )
            flagged.add(target.mesa_id)
        return tuple(
            SimpleNamespace(
                family_id=family_id,
                mesa_id=row.mesa_id,
                signal=False,
                research_signal=row.mesa_id in flagged,
            )
            for row in family
        )

    return fake_peer_signals


def test_release_gate_boolean_is_the_computed_conjunction_not_a_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An artifact whose two computed gates both pass must say so.

    A hardcoded False here is indistinguishable, to the release verifier, from
    a producer who tampered with the gate booleans: the verifier recomputes the
    conjunction and reports any disagreement as a spoofed artifact.
    """
    profile = replace(simulations.CI_PROFILE, name="test-seed-41", seed=41)
    monkeypatch.setattr(simulations, "peer_signals", _perfect_detector(100))
    monkeypatch.setattr(
        simulations, "peer_research_detection", lambda item: bool(item.research_signal)
    )
    summary = simulations.run_end_to_end_validation(
        release_id="release-r2-v1",
        peer_records=_peer_family(),
        simulations=100,
        seed=41,
        profile=profile,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    assert summary.false_discovery_gate_passed
    assert summary.injected_discrepancy_gate_passed
    assert summary.release_gate_passed is (
        summary.false_discovery_gate_passed and summary.injected_discrepancy_gate_passed
    )
    assert summary.release_gate_passed is True
    # Passing the statistical gates is not eligibility, and must not leak into
    # it: those flags stay False and are not derived from this one.
    assert not summary.production_eligible
    assert not summary.independent_full_artifact_passed
    assert not summary.trusted_input_registry_verified
    assert not summary.external_family_ledger_verified
    assert summary.detector_validation["peer"]["production_eligible"] is False


def test_failing_gates_still_report_a_false_conjunction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same field must go red when a gate genuinely fails."""
    profile = replace(simulations.CI_PROFILE, name="test-seed-42", seed=42)
    # The detector fires on every run, including the pure-null arm.
    monkeypatch.setattr(simulations, "peer_signals", _perfect_detector(0))
    monkeypatch.setattr(
        simulations, "peer_research_detection", lambda item: bool(item.research_signal)
    )
    summary = simulations.run_end_to_end_validation(
        release_id="release-r2-v1",
        peer_records=_peer_family(),
        simulations=100,
        seed=42,
        profile=profile,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    assert not summary.false_discovery_gate_passed
    assert not summary.release_gate_passed


def test_attestation_is_recorded_but_excluded_from_the_content_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two hosts that measure the same numbers must produce the same hash.

    Hashing the runtime fingerprint made "bit-identical" and "independently
    replayed" mutually exclusive: no honest replay on a second machine could
    ever match, so the byte-comparison gate could only be satisfied by the
    producer verifying itself.
    """
    profile = replace(simulations.CI_PROFILE, name="test-seed-53", seed=53)
    monkeypatch.setattr(simulations, "peer_signals", _perfect_detector(100))
    monkeypatch.setattr(
        simulations, "peer_research_detection", lambda item: bool(item.research_signal)
    )

    def run() -> simulations.SimulationSummary:
        return simulations.run_end_to_end_validation(
            release_id="release-r2-v1",
            peer_records=_peer_family(),
            simulations=100,
            seed=53,
            profile=profile,
            injected_discrepancies=1,
            injection_size=0.9,
        )

    produced = run()
    assert produced.attestation is not None

    # Simulate the same measurements executed on a different machine.
    foreign = replace(
        produced.attestation,
        runtime_fingerprint="b" * 64,
        platform_identity="Linux-6.1.0-x86_64-with-glibc2.36",
        numpy_version="1.26.4",
        executed_at="2026-08-06T00:00:00.000000+00:00",
    )
    replayed = replace(produced, attestation=foreign).with_hash()

    assert replayed.artifact_hash == produced.artifact_hash
    assert replayed.artifact_payload() == produced.artifact_payload()
    assert replayed.attestation is not None
    assert replayed.attestation.runtime_fingerprint != produced.attestation.runtime_fingerprint
    assert replayed.attestation.attests_artifact_hash == produced.artifact_hash
    # The fingerprint is still evidence; it is simply not hashed.
    assert produced.attestation.runtime_fingerprint == simulations.simulation_runtime_fingerprint()
    assert "attestation" not in produced.artifact_payload()
    assert "runtime_fingerprint" not in produced.artifact_payload()


def test_full_release_profile_declares_1000_independent_runs_without_running_them() -> None:
    profile = simulations.FULL_RELEASE_PROFILE
    assert profile.null_simulations == profile.alternative_simulations == 1_000
    assert profile.independent_artifact_required
    assert profile.artifact_hash == simulations.FULL_RELEASE_PROFILE.artifact_hash
    with pytest.raises(ValueError, match="requires at least 1000"):
        simulations.run_end_to_end_validation(
            release_id="cannot-downgrade-full-profile",
            peer_records=_peer_family(),
            simulations=100,
            profile=profile,
        )
    with pytest.raises(ValueError, match="seed is frozen"):
        simulations.run_end_to_end_validation(
            release_id="cannot-reseed-full-profile",
            peer_records=_peer_family(),
            seed=profile.seed + 1,
            profile=profile,
        )
    with pytest.raises(ValueError, match="full-release profiles require"):
        simulations.SimulationProfile(
            name="full-release-counterfeit",
            null_simulations=100,
            alternative_simulations=100,
            seed=0,
            spatial_initial_permutations=9_999,
            spatial_max_permutations=9_999,
            independent_artifact_required=True,
            policy_boundary_injections=False,
        )


@pytest.mark.parametrize(
    "profile",
    (
        simulations.CI_PROFILE,
        replace(
            simulations.CI_PROFILE,
            name="unregistered-custom-profile",
            seed=111,
        ),
        replace(
            simulations.FULL_RELEASE_PROFILE,
            name="full-release-unregistered-profile",
            seed=111,
        ),
    ),
)
def test_every_profile_rejects_a_caller_seed_override(
    profile: simulations.SimulationProfile,
) -> None:
    with pytest.raises(ValueError, match="profile seed is frozen"):
        simulations.run_end_to_end_validation(
            release_id="cannot-override-profile-seed",
            peer_records=_peer_family(),
            seed=profile.seed + 1,
            profile=profile,
        )


def test_unknown_profile_name_is_not_a_seed_override_escape_hatch() -> None:
    with pytest.raises(ValueError, match="profile is not recognized"):
        simulations.run_end_to_end_validation(
            release_id="unknown-profile",
            peer_records=_peer_family(),
            seed=222,
            profile="unknown-profile",
        )


def test_one_detection_in_one_hundred_cannot_pass_the_power_confidence_gate() -> None:
    lower = simulations._lower_binomial_bound(1, 100)
    assert lower == pytest.approx(0.00025314603297742064)
    assert lower < 0.80


@pytest.mark.parametrize("metric", ["turnout", "candidate_share", "blank", "null_unmarked"])
def test_all_metric_simulators_preserve_focal_and_ballot_semantics(metric: str) -> None:
    source = _peer_family(8, metric=metric)
    generated = simulations._synthetic_peer_rows(source, simulations.np.random.default_rng(91))
    assert len(generated) == len(source)
    for row in generated:
        assert row.valid_votes == row.candidate_total_votes + row.blank_votes  # type: ignore[operator]
        assert row.ballots == row.valid_votes + row.null_unmarked_votes
        if metric == "candidate_share":
            assert 0 <= row.candidate_votes <= (row.candidate_total_votes or 0)
        else:
            assert row.candidate_votes == 0 and row.candidate_id is None

    null_evidence = simulations._run_evidence(
        mode="pure_null",
        run_index=0,
        run_seed=900,
        peer_rows=_peer_family(31, metric=metric),
        spatial_rows=(),
        injected_discrepancies=1,
        injection_size=0.25,
        spatial_initial_permutations=9_999,
        spatial_max_permutations=9_999,
        policy_boundary_injections=False,
    )
    assert not null_evidence.injections and not null_evidence.injected_keys
    assert not null_evidence.public_flagged_keys

    for run_index, direction in enumerate(("positive", "negative")):
        evidence = simulations._run_evidence(
            mode="alternative",
            run_index=run_index,
            run_seed=901 + run_index,
            peer_rows=_peer_family(31, metric=metric),
            spatial_rows=(),
            injected_discrepancies=1,
            injection_size=0.25,
            spatial_initial_permutations=9_999,
            spatial_max_permutations=9_999,
            policy_boundary_injections=False,
        )
        assert evidence.injection_direction == direction
        assert len(evidence.injections) == 1
        assert evidence.injections[0].realized_effect_pp > 0
        assert not evidence.public_flagged_keys


@pytest.mark.parametrize("metric", ["turnout", "candidate_share", "blank", "null_unmarked"])
@pytest.mark.parametrize("direction", ["positive", "negative"])
def test_injections_are_nonzero_saturation_aware_and_denominator_bound(
    metric: str, direction: str
) -> None:
    row = _peer_family(1, metric=metric)[0]
    before_num, before_den = simulations._simulation_pair(row)
    assert simulations._injection_capacity(row, direction) > 0  # type: ignore[arg-type]
    after = simulations._inject(row, 0.10, direction=direction)  # type: ignore[arg-type]
    after_num, after_den = simulations._simulation_pair(after)
    assert before_den == after_den
    assert before_num != after_num
    assert after.valid_votes == after.candidate_total_votes + after.blank_votes  # type: ignore[operator]
    assert after.ballots == after.valid_votes + after.null_unmarked_votes
    if metric == "candidate_share" and direction == "positive":
        assert after.candidate_votes - row.candidate_votes == round(row.valid_votes * 0.10)

    saturated = after
    capacity = simulations._injection_capacity(saturated, direction)  # type: ignore[arg-type]
    if capacity:
        saturated = simulations._inject(saturated, 1.0, direction=direction)  # type: ignore[arg-type]
    assert simulations._injection_capacity(saturated, direction) == 0  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="saturated"):
        simulations._inject(saturated, 0.1, direction=direction)  # type: ignore[arg-type]


def _spatial_family(
    count: int, *, data_version: str, peer_artifact_hash: str
) -> tuple[SpatialMesa, ...]:
    """Build a spatial family, then apply its immutable complete-family declaration."""
    raw = [
        SpatialMesa(
            mesa_id=f"mesa-{index:03d}",
            municipality_id="municipality-1",
            latitude=4.0 + index * 0.001,
            longitude=-74.0,
            residual=0.0,
            peer_residual_artifact_hash=peer_artifact_hash,
            election_slug="presidencia-2026-r2",
            data_version=data_version,
            source_layer="pre_count",
            source_type="pre_count",
            legal_status="preliminary",
            metric="candidate_share",
            candidate_id="candidate-a",
            peer_methodology_version=PEER_METHODOLOGY_VERSION,
            coordinate_source_url="https://official.example/coordinates.geojson",
            coordinate_source_hash="b" * 64,
            coordinate_accuracy_m=10.0,
            coordinate_grain="mesa",
            expected_family_count=count,
            expected_family_digest="d" * 64,
            expected_mesa_count=count,
            expected_mesa_digest="e" * 64,
            expected_mesa_membership_digest="c" * 64,
            cohort_hash="f" * 64,
            source_links=("https://official.example/source.json",),
        )
        for index in range(count)
    ]
    units = [row.mesa_id for row in raw]
    family_digest_value = spatial_family_digest(set(units))
    mesa_digest = spatial_mesa_digest(row.mesa_id for row in raw)
    membership = spatial_mesa_membership_digest(raw)
    first = raw[0]
    cohort = spatial_cohort_digest(
        peer_residual_artifact_hash=first.peer_residual_artifact_hash,
        election_slug=first.election_slug,
        data_version=first.data_version,
        source_layer=first.source_layer,
        source_type=first.source_type,
        legal_status=first.legal_status,
        metric=first.metric,
        candidate_id=first.candidate_id,
        peer_methodology_version=first.peer_methodology_version,
        coordinate_source_url=first.coordinate_source_url,
        coordinate_source_hash=first.coordinate_source_hash,
        coordinate_accuracy_m=first.coordinate_accuracy_m,
        coordinate_grain=first.coordinate_grain,
        expected_family_count=len(set(units)),
        expected_family_digest=family_digest_value,
        expected_mesa_count=len(raw),
        expected_mesa_digest=mesa_digest,
        expected_mesa_membership_digest=membership,
    )
    return tuple(
        replace(
            row,
            expected_family_count=len(set(units)),
            expected_family_digest=family_digest_value,
            expected_mesa_count=len(raw),
            expected_mesa_digest=mesa_digest,
            expected_mesa_membership_digest=membership,
            cohort_hash=cohort,
        )
        for row in raw
    )


def test_family_without_injected_alternatives_reports_unmeasured_power(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A detector family can be reached by a false positive alone, leaving it
    with zero injected alternatives.  Injections only ever mint peer keys, so
    the spatial family is exactly that case.  Dividing by that zero used to
    raise out of the release verifier instead of failing closed, and unmeasured
    power is not the same fact as zero power."""
    peers = _peer_family(count=40, data_version="r1")
    spatial = _spatial_family(40, data_version="r1", peer_artifact_hash="a" * 64)

    def always_flag_first(rows: object, **_kwargs: object) -> tuple[SimpleNamespace, ...]:
        family = tuple(rows)  # type: ignore[arg-type]
        first = family[0]
        return (
            SimpleNamespace(
                family_id="spatial-family",
                mesa_id=first.mesa_id,
                signal=False,
                research_signal=True,
                cohort_hash=first.cohort_hash,
                input_artifact_hash=first.peer_residual_artifact_hash,
                permutations=999,
            ),
        )

    monkeypatch.setattr(simulations, "spatial_residual_signals", always_flag_first)

    summary = simulations.run_end_to_end_validation(
        release_id="r1",
        peer_records=peers,
        spatial_records=spatial,
        simulations=100,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    unmeasured = {
        family_id: item
        for family_id, item in summary.power_by_family.items()
        if item["injected"] == 0
    }
    # The guard is only meaningful if this scenario is actually reached.
    assert unmeasured, summary.power_by_family
    for family_id, item in unmeasured.items():
        assert "spatial" in family_id
        assert item["power"] is None
        assert item["status"] == "no_injected_alternatives"
    for item in summary.power_by_family.values():
        if item["injected"]:
            assert isinstance(item["power"], float)
            assert item["status"] == "measured"


def _multi_place_peer_family(
    per_place: int = 10, places: int = 4, *, data_version: str = "clustered-v1"
) -> tuple[MesaMetrics, ...]:
    """A family spanning several polling places, so a cluster is a proper subset."""
    identifiers = tuple(
        f"mesa-{place:02d}-{index:02d}" for place in range(places) for index in range(per_place)
    )
    expected_digest = family_digest(identifiers)
    input_hash = "a" * 64
    cohort_hash = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version=data_version,
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        expected_family_count=len(identifiers),
        expected_family_digest=expected_digest,
        input_artifact_hash=input_hash,
    )
    return tuple(
        MesaMetrics(
            mesa_id=identifier,
            place_id=f"place-{identifier.split('-')[1]}",
            municipality_id="municipality-1",
            department_id="department-1",
            metric="candidate_share",
            registered=1_200,
            ballots=1_000,
            candidate_votes=300,
            valid_votes=950,
            blank_votes=20,
            null_unmarked_votes=50,
            candidate_id="candidate-a",
            election_slug="presidencia-2026-r2",
            data_version=data_version,
            source_layer="pre_count",
            source_type="pre_count",
            legal_status="preliminary",
            expected_family_count=len(identifiers),
            expected_family_digest=expected_digest,
            input_artifact_hash=input_hash,
            cohort_hash=cohort_hash,
            source_links=("https://official.example/results.json",),
            candidate_total_votes=930,
            denominator_provenance="joined_official",
        )
        for identifier in identifiers
    )


def test_alternative_arm_measures_clustered_and_scattered_power_separately() -> None:
    """Cluster-shaped irregularities -- one puesto, one jurado team, one
    transmission batch -- partly mask themselves against a leave-one-mesa-out
    peer screen, because the contaminated peers stay in the reference pool.
    Shape is therefore a stratum dimension, and the per-stratum power gate has
    to clear the clustered arm as well as the easy scattered one."""
    summary = simulations.run_end_to_end_validation(
        release_id="clustered-r1",
        peer_records=_multi_place_peer_family(),
        simulations=100,
        injected_discrepancies=1,
        injection_size=0.9,
    )

    shapes = {
        injection.shape
        for run in summary.alternative_runs
        for injection in run.injections
    }
    assert shapes == {"scattered", "clustered"}, shapes

    # Every clustered injection must name a whole polling place, and must leave
    # unshifted peers behind: a family-wide shift is not a cluster.
    for run in summary.alternative_runs:
        clustered = [i for i in run.injections if i.shape == "clustered"]
        if clustered:
            assert len(clustered) >= 2
            assert len(clustered) < len(_multi_place_peer_family())

    by_shape: dict[str, list[str]] = {"scattered": [], "clustered": []}
    for stratum in summary.power_by_stratum:
        for shape in by_shape:
            if f'"{shape}"' in stratum:
                by_shape[shape].append(stratum)
    assert by_shape["scattered"], summary.power_by_stratum
    assert by_shape["clustered"], summary.power_by_stratum
