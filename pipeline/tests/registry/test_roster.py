from __future__ import annotations

import ast
import hashlib
import inspect
from dataclasses import replace

import pytest
from elecciones_pipeline.analytics.peer_signals import MesaMetrics
from elecciones_pipeline.registry import roster as roster_module
from elecciones_pipeline.registry.roster import (
    ABSENT,
    EXPECTED_REPORTING,
    PRESENT_UNREPORTED,
    PRESENT_UNREPORTED_MESAS_R2,
    RegistryError,
    RosterMember,
    build_family_roster,
    enumeration_bytes_from_members,
    parse_enumeration_lines,
    roster_declaration_statement,
    verify_family_membership,
)

REPORTING = tuple(f"mesa-{index:03d}" for index in range(6))


def _enumeration() -> bytes:
    members = [RosterMember(member_id=value, state=EXPECTED_REPORTING) for value in REPORTING]
    members += [
        RosterMember(member_id=value, state=PRESENT_UNREPORTED)
        for value in PRESENT_UNREPORTED_MESAS_R2
    ]
    members.append(RosterMember(member_id="mesa-retired", state=ABSENT))
    return enumeration_bytes_from_members(members)


def _roster(payload: bytes | None = None) -> roster_module.FamilyRoster:
    return build_family_roster(
        detector_id="peer",
        family_id="r1|presidencia-2026-r2|pre_count|candidate_share|candidate-a",
        election_slug="presidencia-2026-r2",
        data_version="r1",
        enumeration_bytes=_enumeration() if payload is None else payload,
        source_id="registraduria-divipole",
        source_url="https://official.example/divipole.csv",
        retrieved_at="2026-08-06T00:00:00+00:00",
    )


def test_roster_is_built_from_enumeration_bytes_and_binds_them(tmp_path_factory: object) -> None:
    payload = _enumeration()
    roster = _roster(payload)

    assert roster.source.content_hash == hashlib.sha256(payload).hexdigest()
    assert roster.source.record_count == 10
    assert roster.expected_reporting_ids == REPORTING
    assert roster.present_unreported_ids == tuple(sorted(PRESENT_UNREPORTED_MESAS_R2))
    assert roster.absent_ids == ("mesa-retired",)
    assert roster.state_counts == {
        EXPECTED_REPORTING: 6,
        PRESENT_UNREPORTED: 3,
        ABSENT: 1,
    }
    assert roster.artifact_hash and "artifact_hash" not in roster.artifact_payload()
    assert roster.with_hash().artifact_hash == roster.artifact_hash
    # Member ids are carried, not just a count and a digest.
    assert set(REPORTING) <= {member.member_id for member in roster.members}
    assert str(roster.state_counts[PRESENT_UNREPORTED]) in roster_declaration_statement(roster)


def test_the_roster_builder_cannot_be_handed_the_rows_it_authenticates() -> None:
    """If it reads what it authenticates, it authenticates nothing.

    This is a structural check, not a policy note: the enumeration path must
    have no parameter capable of carrying an analyzer row, so no future caller
    can quietly reintroduce the circularity that ``expected_family_digest``
    already has.
    """
    signature = inspect.signature(build_family_roster)
    annotations = {str(param.annotation) for param in signature.parameters.values()}
    assert not [text for text in annotations if "MesaMetrics" in text or "SpatialMesa" in text]

    # Nothing analytical is importable from here, so no code path in this
    # module can reach an analyzer row even indirectly.
    tree = ast.parse(inspect.getsource(roster_module))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not [name for name in imported if "analytics" in name or "peer_signals" in name]
    analytical = {"MesaMetrics", "SpatialMesa", "peer_signals"}
    assert not [name for name in vars(roster_module) if name in analytical]

    with pytest.raises(RegistryError, match="exact bytes"):
        build_family_roster(
            detector_id="peer",
            family_id="family",
            election_slug="presidencia-2026-r2",
            data_version="r1",
            enumeration_bytes=[],  # type: ignore[arg-type]
            source_id="registraduria-divipole",
            source_url="https://official.example/divipole.csv",
            retrieved_at="2026-08-06T00:00:00+00:00",
        )


def test_membership_requires_set_equality_not_a_matching_count() -> None:
    roster = _roster()
    acknowledged = PRESENT_UNREPORTED_MESAS_R2

    assert not verify_family_membership(
        roster, observed_ids=REPORTING, acknowledged_unreported_ids=acknowledged
    )

    # The attack the row-carried digest cannot see: drop one member and add a
    # different one, so the count still matches and the producer recomputes
    # every hash it controls.
    swapped = (*REPORTING[:-1], "mesa-999")
    findings = verify_family_membership(
        roster, observed_ids=swapped, acknowledged_unreported_ids=acknowledged
    )
    assert len(swapped) == len(REPORTING)
    assert any("missing from the analyzed family" in finding for finding in findings)
    assert any("absent from the roster" in finding for finding in findings)

    dropped = verify_family_membership(
        roster, observed_ids=REPORTING[:-1], acknowledged_unreported_ids=acknowledged
    )
    assert any("mesa-005" in finding for finding in dropped)


def test_present_but_unreported_is_a_third_state_that_must_be_named() -> None:
    """Round two's three uncounted mesas are neither present nor absent.

    They report ``votant = 0`` and satisfy both ballot identities at 0 = 0 + 0,
    so no arithmetic check can see them.  Silence about them must therefore be
    a finding, otherwise a producer's deletions travel in the same channel as a
    genuine reporting gap.
    """
    roster = _roster()
    assert set(roster.present_unreported_ids) == set(PRESENT_UNREPORTED_MESAS_R2)
    assert not set(roster.present_unreported_ids) & set(roster.expected_reporting_ids)
    assert not set(roster.present_unreported_ids) & set(roster.absent_ids)

    silent = verify_family_membership(roster, observed_ids=REPORTING)
    assert any("were not acknowledged" in finding for finding in silent)

    overclaimed = verify_family_membership(
        roster,
        observed_ids=REPORTING,
        acknowledged_unreported_ids=(*PRESENT_UNREPORTED_MESAS_R2, "mesa-004"),
    )
    assert any("not in that roster state" in finding for finding in overclaimed)

    analyzed_anyway = verify_family_membership(
        roster,
        observed_ids=(*REPORTING, PRESENT_UNREPORTED_MESAS_R2[0]),
        acknowledged_unreported_ids=PRESENT_UNREPORTED_MESAS_R2,
    )
    assert any("nevertheless analyzed" in finding for finding in analyzed_anyway)


def test_a_roster_over_a_dropped_subset_is_a_different_artifact() -> None:
    """The property row-carried declarations lack: the digest must move."""
    full = _roster()
    truncated = _roster(
        enumeration_bytes_from_members(
            [member for member in full.members if member.member_id != REPORTING[0]]
        )
    )
    assert truncated.artifact_hash != full.artifact_hash
    assert truncated.source.content_hash != full.source.content_hash
    assert truncated.state_counts[EXPECTED_REPORTING] == 5


def test_enumeration_parsing_rejects_malformed_and_duplicated_records() -> None:
    assert parse_enumeration_lines(b"# comment\n\nmesa-1\texpected_reporting\n") == (
        RosterMember(member_id="mesa-1", state=EXPECTED_REPORTING),
    )
    with pytest.raises(RegistryError, match="member_id"):
        parse_enumeration_lines(b"mesa-1 expected_reporting\n")
    with pytest.raises(RegistryError, match="unknown roster member state"):
        parse_enumeration_lines(b"mesa-1\tprobably_fine\n")
    with pytest.raises(RegistryError, match="repeats member ids"):
        _roster(b"mesa-1\texpected_reporting\nmesa-1\tabsent\n")
    with pytest.raises(RegistryError, match="at least one member"):
        _roster(b"# nothing here\n")


def test_analyzer_rows_still_carry_the_self_certifying_declaration() -> None:
    """Documents the gap this roster exists to close, so it cannot be forgotten.

    ``expected_family_count`` and ``expected_family_digest`` are fields on the
    rows.  A producer who drops a subset recomputes both over what is left and
    every downstream hash still validates.  The roster is only useful while it
    is enumerated somewhere these fields are not.
    """
    fields = {field for field in MesaMetrics.__dataclass_fields__}
    assert {"expected_family_count", "expected_family_digest"} <= fields
    assert replace  # the rows are trivially reconstructible by their producer
