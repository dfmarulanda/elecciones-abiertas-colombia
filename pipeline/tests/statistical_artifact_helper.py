"""Analyzer-generated fixtures for statistical release tests.

This module intentionally has no shortcut for manufacturing a successful
artifact.  Tests that need an artifact run the same peer analyzer and simulator
as production validation; replay inputs are exposed separately for the release
gate's independent verification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from functools import lru_cache

from elecciones_pipeline.analytics.peer_signals import MesaMetrics, cohort_digest, family_digest
from elecciones_pipeline.analytics.simulations import (
    TrustedSimulationInputs,
    canonical_input_hashes,
    run_end_to_end_validation,
)


def _records() -> tuple[MesaMetrics, ...]:
    ids = tuple(f"mesa-{index:03d}" for index in range(31))
    digest = family_digest(ids)
    original_hash = "a" * 64
    cohort = cohort_digest(
        election_slug="presidencia-2026-r2",
        data_version="r1",
        source_layer="pre_count",
        source_type="pre_count",
        legal_status="preliminary",
        metric="candidate_share",
        candidate_id="candidate-a",
        expected_family_count=len(ids),
        expected_family_digest=digest,
        input_artifact_hash=original_hash,
    )
    return tuple(
        MesaMetrics(
            mesa_id=mesa_id,
            place_id="place-1",
            municipality_id="municipality-1",
            department_id="department-1",
            metric="candidate_share",
            registered=1200,
            ballots=1000,
            candidate_votes=300,
            valid_votes=950,
            blank_votes=20,
            null_unmarked_votes=10,
            candidate_id="candidate-a",
            election_slug="presidencia-2026-r2",
            data_version="r1",
            source_layer="pre_count",
            source_type="pre_count",
            legal_status="preliminary",
            expected_family_count=len(ids),
            expected_family_digest=digest,
            input_artifact_hash=original_hash,
            cohort_hash=cohort,
            source_links=("https://official.example/results.json",),
        )
        for mesa_id in ids
    )


def trusted_simulation_inputs() -> TrustedSimulationInputs:
    provisional = TrustedSimulationInputs(peer_records=_records())
    registry = canonical_input_hashes(provisional)
    registry_hash = hashlib.sha256(
        json.dumps(
            {"schema": "canonical-input-hash-registry-v1", "hashes": registry},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return TrustedSimulationInputs(
        peer_records=provisional.peer_records,
        canonical_input_hash_registry=registry,
        registry_artifact_hash=registry_hash,
    )


@lru_cache(maxsize=1)
def _summary() -> dict[str, object]:
    inputs = trusted_simulation_inputs()
    return asdict(
        run_end_to_end_validation(
            release_id="r1",
            peer_records=inputs.peer_records,
            simulations=100,
            injected_discrepancies=1,
            injection_size=0.9,
        )
    )


def passing_simulation_summary(*, release_id: str = "r1") -> dict[str, object]:
    """Compatibility name; returns a real analyzer artifact, never a fake one."""
    result = dict(_summary())
    result["release_id"] = release_id
    # The release id is inside the content address.
    if release_id != "r1":
        inputs = trusted_simulation_inputs()
        result = asdict(
            run_end_to_end_validation(
                release_id=release_id,
                peer_records=inputs.peer_records,
                simulations=100,
                seed=29,
                injected_discrepancies=1,
                injection_size=0.9,
            )
        )
    return result
