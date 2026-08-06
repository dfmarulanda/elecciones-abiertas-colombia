"""Trusted-artifact registry: content-addressed storage, an append-only log, and rosters.

Nothing in this package makes a release eligible.  It makes honest verification
*possible* by giving a verifier three things it does not currently have: bytes
it can re-address, a declaration order it can re-derive, and a statement of
family membership that was not written by the party being checked.
"""

from .log import (
    ENTRY_KINDS,
    GENESIS_PREV_HASH,
    LOG_SCHEMA,
    AppendOnlyLog,
    Checkpoint,
    LogEntry,
    merkle_root,
    verify_entries,
    verify_log_file,
)
from .roster import (
    ABSENT,
    EXPECTED_REPORTING,
    MEMBER_STATES,
    PRESENT_UNREPORTED,
    PRESENT_UNREPORTED_MESAS_R2,
    ROSTER_SCHEMA,
    EnumerationSource,
    FamilyRoster,
    RosterMember,
    build_family_roster,
    enumeration_bytes_from_members,
    parse_enumeration_lines,
    roster_declaration_statement,
    verify_family_membership,
)
from .store import (
    DIGEST_ALGORITHM,
    ContentAddressedStore,
    RegistryError,
    canonical_json_bytes,
    canonical_json_digest,
    digest_bytes,
    require_digest,
)

__all__ = [
    "ABSENT",
    "DIGEST_ALGORITHM",
    "ENTRY_KINDS",
    "EXPECTED_REPORTING",
    "GENESIS_PREV_HASH",
    "LOG_SCHEMA",
    "MEMBER_STATES",
    "PRESENT_UNREPORTED",
    "PRESENT_UNREPORTED_MESAS_R2",
    "ROSTER_SCHEMA",
    "AppendOnlyLog",
    "Checkpoint",
    "ContentAddressedStore",
    "EnumerationSource",
    "FamilyRoster",
    "LogEntry",
    "RegistryError",
    "RosterMember",
    "build_family_roster",
    "canonical_json_bytes",
    "canonical_json_digest",
    "digest_bytes",
    "enumeration_bytes_from_members",
    "merkle_root",
    "parse_enumeration_lines",
    "require_digest",
    "roster_declaration_statement",
    "verify_entries",
    "verify_family_membership",
    "verify_log_file",
]
