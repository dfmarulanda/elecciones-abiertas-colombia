"""Independently enumerated family rosters.

The peer detector's multiplicity adjustment is only valid over a *complete*
family, so something has to say which members the family must contain.  Today
that something is ``expected_family_count`` / ``expected_family_digest``, which
are fields **on the rows themselves**.  A producer who drops an inconvenient
subset simply recomputes both fields over what is left, and every hash in the
pipeline still validates: the rows authenticate the rows.

This module builds that statement from a different direction.  A roster is
enumerated from an official registry of mesas — the divipole census, not the
result rows — and carries member ids, so the gate can require exact set
equality instead of a count and a digest that the producer also chose.

The structural rule is that :func:`build_family_roster` has no parameter that
can carry a ``MesaMetrics``, a ``SpatialMesa``, or anything else the analyzer
reads.  If the roster could read what it authenticates, it would authenticate
nothing, and the check would be a more expensive way of trusting the producer.

Membership is three-valued, because two values cannot express what round two
actually published.  Round one reports ``mesesc = metota = 122,020``; round two
reports ``mesesc = 122,017`` against the same 122,020 installed mesas.  Three
domestic mesas were installed and collected but never reported a count, all
with ``votant = 0``.  They satisfy both ballot identities trivially at
``0 = 0 + 0``, which is exactly why an arithmetic check cannot see them, and
they are absent from the analyzer's rows for an entirely legitimate reason.
Calling them ``absent`` would make a real gap indistinguishable from a
producer's deletion; calling them ``expected_reporting`` would make an honest
run fail forever.  They get their own state and must be acknowledged by name.
See ``docs/research/findings-ledger.md`` §2.2.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, replace

from .store import RegistryError, canonical_json_digest, digest_bytes, require_digest

ROSTER_SCHEMA = "elecciones-family-roster-v1"

EXPECTED_REPORTING = "expected_reporting"
PRESENT_UNREPORTED = "present_unreported"
ABSENT = "absent"
MEMBER_STATES = (EXPECTED_REPORTING, PRESENT_UNREPORTED, ABSENT)
_STATES = frozenset(MEMBER_STATES)

# The three round-two mesas that were installed and collected but reported no
# count (all votant = 0, all domestic).  Disjoint from the escrutinio's three
# non-digitalised actas.  Source: docs/research/findings-ledger.md §2.2.
PRESENT_UNREPORTED_MESAS_R2 = (
    "050010204000009",
    "250010401000004",
    "250010601000009",
)


@dataclass(frozen=True)
class RosterMember:
    """One enumerated member and its reporting state."""

    member_id: str
    state: str

    def __post_init__(self) -> None:
        if not isinstance(self.member_id, str) or not self.member_id:
            raise RegistryError("roster members need a non-empty id")
        if self.state not in _STATES:
            raise RegistryError(
                f"unknown roster member state {self.state!r}; expected one of {MEMBER_STATES}"
            )


@dataclass(frozen=True)
class EnumerationSource:
    """Where the enumeration came from, and the exact bytes it came as."""

    source_id: str
    source_url: str
    retrieved_at: str
    content_hash: str
    record_count: int

    def __post_init__(self) -> None:
        require_digest(self.content_hash)
        if not self.source_id or not self.source_url or not self.retrieved_at:
            raise RegistryError("an enumeration source needs an id, a url, and a retrieval time")
        if type(self.record_count) is not int or self.record_count < 1:
            raise RegistryError("an enumeration source must enumerate at least one record")


@dataclass(frozen=True)
class FamilyRoster:
    """A content-addressed statement of who belongs to one detector family."""

    schema: str
    detector_id: str
    family_id: str
    election_slug: str
    data_version: str
    source: EnumerationSource
    members: tuple[RosterMember, ...]
    state_counts: dict[str, int]
    artifact_hash: str = ""

    def artifact_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("artifact_hash")
        return payload

    def with_hash(self) -> FamilyRoster:
        return replace(self, artifact_hash=canonical_json_digest(self.artifact_payload()))

    def ids_in_state(self, state: str) -> tuple[str, ...]:
        if state not in _STATES:
            raise RegistryError(f"unknown roster member state {state!r}")
        return tuple(member.member_id for member in self.members if member.state == state)

    @property
    def expected_reporting_ids(self) -> tuple[str, ...]:
        return self.ids_in_state(EXPECTED_REPORTING)

    @property
    def present_unreported_ids(self) -> tuple[str, ...]:
        return self.ids_in_state(PRESENT_UNREPORTED)

    @property
    def absent_ids(self) -> tuple[str, ...]:
        return self.ids_in_state(ABSENT)


def parse_enumeration_lines(payload: bytes) -> tuple[RosterMember, ...]:
    """Parse the canonical enumeration text format: ``<member_id>\\t<state>``.

    Blank lines and ``#`` comments are ignored.  This parser reads registry
    bytes only; it has no access to, and no knowledge of, analyzer rows.
    """
    members: list[RosterMember] = []
    for number, raw in enumerate(payload.decode("utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            raise RegistryError(f"enumeration line {number} is not '<member_id>\\t<state>'")
        members.append(RosterMember(member_id=parts[0].strip(), state=parts[1].strip()))
    return tuple(members)


def build_family_roster(
    *,
    detector_id: str,
    family_id: str,
    election_slug: str,
    data_version: str,
    enumeration_bytes: bytes,
    source_id: str,
    source_url: str,
    retrieved_at: str,
    parse: Callable[[bytes], Iterable[RosterMember]] = parse_enumeration_lines,
) -> FamilyRoster:
    """Build a roster from enumeration bytes and nothing else.

    Note what is not in this signature: no rows, no analyzer artifact, no
    cohort declaration.  The roster is derivable from the registry bytes alone,
    which is the only reason its verdict on those rows means anything.
    """
    if not isinstance(enumeration_bytes, (bytes, bytearray)):
        raise RegistryError("an enumeration must be supplied as exact bytes")
    if not detector_id or not family_id or not election_slug or not data_version:
        raise RegistryError("a roster needs a detector, a family, an election, and a data version")
    payload = bytes(enumeration_bytes)
    members = tuple(parse(payload))
    if not members:
        raise RegistryError("an enumeration must produce at least one member")
    identifiers = [member.member_id for member in members]
    duplicates = sorted({value for value in identifiers if identifiers.count(value) > 1})
    if duplicates:
        raise RegistryError(f"enumeration repeats member ids: {duplicates[:5]}")
    ordered = tuple(sorted(members, key=lambda member: member.member_id))
    counts = {state: sum(1 for member in ordered if member.state == state) for state in MEMBER_STATES}
    source = EnumerationSource(
        source_id=source_id,
        source_url=source_url,
        retrieved_at=retrieved_at,
        content_hash=digest_bytes(payload),
        record_count=len(ordered),
    )
    return FamilyRoster(
        schema=ROSTER_SCHEMA,
        detector_id=detector_id,
        family_id=family_id,
        election_slug=election_slug,
        data_version=data_version,
        source=source,
        members=ordered,
        state_counts=counts,
    ).with_hash()


def verify_family_membership(
    roster: FamilyRoster,
    *,
    observed_ids: Iterable[str],
    acknowledged_unreported_ids: Iterable[str] = (),
) -> tuple[str, ...]:
    """Require exact set equality against the roster; return findings.

    Set equality, not a count and not a digest.  A count catches a producer who
    drops rows and forgets to renumber; only the ids catch a producer who drops
    one mesa and adds another, and only an external roster catches a producer
    who drops rows and recomputes both.

    Members in the ``present_unreported`` state must be acknowledged by name.
    Passing them silently would let a producer hide arbitrary deletions in the
    same channel a genuine reporting gap uses.
    """
    findings: list[str] = []
    observed = set(observed_ids)
    expected = set(roster.expected_reporting_ids)
    unreported = set(roster.present_unreported_ids)
    acknowledged = set(acknowledged_unreported_ids)

    missing = sorted(expected - observed)
    if missing:
        findings.append(f"roster members missing from the analyzed family: {missing[:10]}")
    extra = sorted(observed - expected)
    if extra:
        findings.append(f"analyzed family contains members absent from the roster: {extra[:10]}")

    unacknowledged = sorted(unreported - acknowledged)
    if unacknowledged:
        findings.append(
            "present-but-unreported roster members were not acknowledged: "
            f"{unacknowledged[:10]}"
        )
    overclaimed = sorted(acknowledged - unreported)
    if overclaimed:
        findings.append(
            f"members claimed as present-but-unreported are not in that roster state: "
            f"{overclaimed[:10]}"
        )
    smuggled = sorted(observed & unreported)
    if smuggled:
        findings.append(
            f"members recorded as unreported were nevertheless analyzed: {smuggled[:10]}"
        )
    return tuple(findings)


def roster_declaration_statement(roster: FamilyRoster) -> str:
    """A one-line statement for the registry log entry."""
    return (
        f"family roster {roster.family_id} for {roster.election_slug}/{roster.data_version}: "
        f"{roster.state_counts[EXPECTED_REPORTING]} expected reporting, "
        f"{roster.state_counts[PRESENT_UNREPORTED]} present but unreported, "
        f"{roster.state_counts[ABSENT]} absent, enumerated from {roster.source.source_id}"
    )


def enumeration_bytes_from_members(members: Sequence[RosterMember]) -> bytes:
    """Serialise members back to the canonical enumeration format."""
    lines = [f"{member.member_id}\t{member.state}" for member in members]
    return ("\n".join(lines) + "\n").encode("utf-8")
