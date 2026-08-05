"""Deterministic, source-aware election analytics.

These routines produce review leads, not findings of fraud.  They deliberately
avoid Benford tests and contextual-history scoring.
"""

from .outcome_sensitivity import (
    METHODOLOGY_VERSION as OUTCOME_SENSITIVITY_METHODOLOGY_VERSION,
)
from .outcome_sensitivity import (
    AffectedVoteVerification,
    BoundBasis,
    EvidenceBasis,
    GeographicScope,
    OutcomeObservation,
    OutcomeSensitivity,
    SensitivityStatus,
    SourceFactArtifact,
    SourceFactScope,
    UnresolvedRecordBound,
    VerifiedAffectedRecord,
    analyze_outcome_sensitivity,
    fact_set_hash,
    margin_shift_certificate,
)
from .peer_signals import MesaMetrics, PeerSignal, peer_signals
from .priority import METHODOLOGY_VERSION, AuditPriority, audit_priority
from .reconciliation import (
    ArithmeticCheck,
    CheckStatus,
    ComparisonStatus,
    ExplanationStatus,
    MesaRecord,
    ReconciliationResult,
    evaluate_source_arithmetic,
    reconcile,
)
from .simulations import (
    SimulationRunEvidence,
    SimulationSummary,
    run_end_to_end_validation,
)
from .spatial import SpatialMesa, SpatialSignal, spatial_residual_signals

__all__ = [
    "METHODOLOGY_VERSION",
    "AffectedVoteVerification",
    "ArithmeticCheck",
    "AuditPriority",
    "BoundBasis",
    "CheckStatus",
    "ComparisonStatus",
    "EvidenceBasis",
    "ExplanationStatus",
    "GeographicScope",
    "MesaRecord",
    "MesaMetrics",
    "OutcomeObservation",
    "OUTCOME_SENSITIVITY_METHODOLOGY_VERSION",
    "OutcomeSensitivity",
    "PeerSignal",
    "ReconciliationResult",
    "SensitivityStatus",
    "SimulationRunEvidence",
    "SimulationSummary",
    "SpatialMesa",
    "SpatialSignal",
    "SourceFactArtifact",
    "SourceFactScope",
    "UnresolvedRecordBound",
    "VerifiedAffectedRecord",
    "analyze_outcome_sensitivity",
    "audit_priority",
    "fact_set_hash",
    "evaluate_source_arithmetic",
    "margin_shift_certificate",
    "peer_signals",
    "reconcile",
    "run_end_to_end_validation",
    "spatial_residual_signals",
]
