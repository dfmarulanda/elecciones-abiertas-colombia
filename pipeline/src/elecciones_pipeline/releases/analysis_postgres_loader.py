from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import Engine, text

from ..analytics.analysis_release import load_analysis_bundle


@dataclass(frozen=True)
class AnalysisLoadResult:
    analysis_release_id: str
    manifest_hash: str
    artifact_count: int
    anomaly_count: int
    report_count: int
    installed: bool


@dataclass(frozen=True)
class PreliminaryAnalysisApprovalResult:
    analysis_release_id: str
    manifest_hash: str
    approved: bool


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _json_file(path: Path) -> object:
    return json.loads(path.read_bytes())


def _artifact_url(base_url: str, analysis_release_id: str, artifact: dict[str, object]) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "analysis artifact base URL must be immutable HTTPS without authority data"
        )
    byte_hash = _required_string(artifact.get("byte_hash"), "artifact.byte_hash")
    kind = _required_string(artifact.get("kind"), "artifact.kind")
    return f"{base_url.rstrip('/')}/{analysis_release_id}/{byte_hash}-{kind}.json"


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def approve_preliminary_analysis_release(
    engine: Engine,
    analysis_release_id: str,
    *,
    approved_by: str,
    approved_at: datetime,
    approval_signature_hash: str,
    caveat_es: str,
    caveat_en: str,
) -> PreliminaryAnalysisApprovalResult:
    """Promote one validated internal overlay through the preliminary-only gate."""
    analysis_release_id = _required_string(analysis_release_id, "analysis_release_id")
    approved_by = _required_string(approved_by, "approved_by")
    caveat_es = _required_string(caveat_es, "caveat_es")
    caveat_en = _required_string(caveat_en, "caveat_en")
    if approved_at.tzinfo is None or approved_at.utcoffset() is None:
        raise ValueError("analysis approval time must be timezone-aware")
    if not _SHA256.fullmatch(approval_signature_hash):
        raise ValueError("analysis approval signature hash must be lowercase SHA-256")

    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT ar.lifecycle_state,ar.manifest_hash,ax.exposure_tier,"
                "ax.approved_by,ax.approved_at,ax.approval_signature_hash,"
                "ax.caveat_es,ax.caveat_en,ax.revoked_at "
                "FROM analysis_releases ar JOIN analysis_exposures ax USING "
                "(analysis_release_id,source_release_id,source_election_slug) "
                "WHERE ar.analysis_release_id=:analysis_release_id FOR UPDATE"
            ),
            {"analysis_release_id": analysis_release_id},
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("analysis release is not installed")
        if row["revoked_at"] is not None:
            raise ValueError("analysis exposure is revoked")
        manifest_hash = _required_string(row["manifest_hash"], "manifest_hash")
        if row["exposure_tier"] == "preliminary_research":
            expected = {
                "approved_by": approved_by,
                "approved_at": approved_at,
                "approval_signature_hash": approval_signature_hash,
                "caveat_es": caveat_es,
                "caveat_en": caveat_en,
            }
            if any(row[key] != value for key, value in expected.items()):
                raise ValueError("analysis release already has a different immutable approval")
            return PreliminaryAnalysisApprovalResult(
                analysis_release_id, manifest_hash, False
            )
        if row["exposure_tier"] != "internal":
            raise ValueError("analysis release is not eligible for preliminary approval")
        if row["lifecycle_state"] != "validated":
            raise ValueError("analysis release has not passed bundle validation")
        connection.execute(
            text(
                "UPDATE analysis_exposures SET exposure_tier='preliminary_research',"
                "approved_by=:approved_by,approved_at=:approved_at,"
                "approval_signature_hash=:approval_signature_hash,caveat_es=:caveat_es,"
                "caveat_en=:caveat_en WHERE analysis_release_id=:analysis_release_id"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "approved_by": approved_by,
                "approved_at": approved_at,
                "approval_signature_hash": approval_signature_hash,
                "caveat_es": caveat_es,
                "caveat_en": caveat_en,
            },
        )
    return PreliminaryAnalysisApprovalResult(analysis_release_id, manifest_hash, True)


def load_analysis_release(
    engine: Engine,
    manifest_path: Path,
    *,
    producer_operator_id: str,
    artifact_base_url: str,
) -> AnalysisLoadResult:
    """Load one verified bundle transactionally with an internal-only exposure."""
    if not producer_operator_id.strip():
        raise ValueError("analysis producer operator identity is required")
    manifest = load_analysis_bundle(manifest_path)
    analysis_release_id = _required_string(
        manifest.get("analysis_release_id"), "analysis_release_id"
    )
    source_release_id = _required_string(manifest.get("source_release_id"), "source_release_id")
    election_slug = _required_string(manifest.get("election_slug"), "election_slug")
    methodology = _required_string(manifest.get("methodology_version"), "methodology_version")
    input_hash = _required_string(manifest.get("canonical_input_hash"), "canonical_input_hash")
    runtime_hash = _required_string(
        manifest.get("producer_runtime_fingerprint"), "producer_runtime_fingerprint"
    )
    manifest_hash = _required_string(manifest.get("manifest_hash"), "manifest_hash")
    generated_at = datetime.fromisoformat(
        _required_string(manifest.get("generated_at"), "generated_at").replace("Z", "+00:00")
    )
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("analysis generated_at must be timezone-aware")
    artifacts_value = manifest.get("artifacts")
    if not isinstance(artifacts_value, list):
        raise ValueError("analysis manifest artifacts must be an array")
    artifacts = [value for value in artifacts_value if isinstance(value, dict)]
    if len(artifacts) != len(artifacts_value):
        raise ValueError("analysis manifest artifacts must contain objects")
    artifact_by_kind = {artifact.get("kind"): artifact for artifact in artifacts}
    required_kinds = {
        "canonical_input",
        "cohort_registry",
        "eligibility",
        "descriptive_summary",
        "deterministic_anomalies",
        "local_sensitivity",
        "model_diagnostics",
        "outcome_sensitivity",
        "research_status",
        "spatial_status",
        "validation",
    }
    if not required_kinds <= set(artifact_by_kind):
        raise ValueError("analysis bundle is missing a required artifact kind")
    parsed_artifacts = {
        kind: _json_file(manifest_path.parent / _required_string(artifact["filename"], "filename"))
        for kind, artifact in artifact_by_kind.items()
    }
    anomalies_value = parsed_artifacts["deterministic_anomalies"]
    eligibility_value = parsed_artifacts["eligibility"]
    descriptive_value = parsed_artifacts["descriptive_summary"]
    research_value = parsed_artifacts["research_status"]
    model_diagnostics_value = parsed_artifacts["model_diagnostics"]
    validation_value = parsed_artifacts["validation"]
    local_sensitivity_value = parsed_artifacts["local_sensitivity"]
    spatial_value = parsed_artifacts["spatial_status"]
    outcome_value = parsed_artifacts["outcome_sensitivity"]
    if not isinstance(anomalies_value, list) or not all(
        isinstance(value, dict) for value in anomalies_value
    ):
        raise ValueError("deterministic anomaly artifact must be an array of objects")
    if not all(
        isinstance(value, dict)
        for value in (
            eligibility_value,
            descriptive_value,
            research_value,
            model_diagnostics_value,
            validation_value,
            local_sensitivity_value,
            spatial_value,
            outcome_value,
        )
    ):
        raise ValueError("analysis report artifacts must be objects")
    assert isinstance(eligibility_value, dict)
    assert isinstance(descriptive_value, dict)
    assert isinstance(research_value, dict)
    assert isinstance(model_diagnostics_value, dict)
    assert isinstance(validation_value, dict)
    assert isinstance(local_sensitivity_value, dict)
    assert isinstance(spatial_value, dict)
    assert isinstance(outcome_value, dict)

    with engine.begin() as connection:
        existing = connection.execute(
            text(
                "SELECT manifest_hash FROM analysis_releases "
                "WHERE analysis_release_id=:analysis_release_id"
            ),
            {"analysis_release_id": analysis_release_id},
        ).scalar_one_or_none()
        if existing is not None:
            if existing != manifest_hash:
                raise ValueError("analysis release identity is already bound to another manifest")
            artifact_count = connection.execute(
                text(
                    "SELECT count(*) FROM analysis_artifacts "
                    "WHERE analysis_release_id=:analysis_release_id"
                ),
                {"analysis_release_id": analysis_release_id},
            ).scalar_one()
            anomaly_count = connection.execute(
                text(
                    "SELECT count(*) FROM analysis_anomalies "
                    "WHERE analysis_release_id=:analysis_release_id"
                ),
                {"analysis_release_id": analysis_release_id},
            ).scalar_one()
            report_count = connection.execute(
                text(
                    "SELECT count(*) FROM analysis_reports "
                    "WHERE analysis_release_id=:analysis_release_id"
                ),
                {"analysis_release_id": analysis_release_id},
            ).scalar_one()
            return AnalysisLoadResult(
                analysis_release_id,
                manifest_hash,
                int(artifact_count),
                int(anomaly_count),
                int(report_count),
                False,
            )
        host = urlsplit(artifact_base_url).hostname
        if (
            host is None
            or connection.execute(
                text("SELECT 1 FROM analysis_artifact_hosts WHERE host=:host"),
                {"host": host.lower()},
            ).scalar_one_or_none()
            is None
        ):
            raise ValueError("analysis artifact host is not allowlisted")
        connection.execute(
            text(
                "INSERT INTO analysis_releases(analysis_release_id,source_release_id,"
                "source_election_slug,methodology_version,canonical_input_hash,"
                "producer_runtime_fingerprint,producer_operator_id,lifecycle_state,generated_at,"
                "created_at,manifest_hash) VALUES(:analysis_release_id,:source_release_id,"
                ":election_slug,:methodology,:input_hash,:runtime_hash,:operator,'validated',"
                ":generated_at,CURRENT_TIMESTAMP,:manifest_hash)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "election_slug": election_slug,
                "methodology": methodology,
                "input_hash": input_hash,
                "runtime_hash": runtime_hash,
                "operator": producer_operator_id,
                "generated_at": generated_at,
                "manifest_hash": manifest_hash,
            },
        )
        for artifact in artifacts:
            status = _required_string(artifact.get("status"), "artifact.status")
            url = (
                _artifact_url(artifact_base_url, analysis_release_id, artifact)
                if status == "available"
                else None
            )
            connection.execute(
                text(
                    "INSERT INTO analysis_artifacts(analysis_release_id,source_release_id,"
                    "source_election_slug,artifact_id,kind,schema_version,media_type,record_count,"
                    "byte_size,byte_hash,content_hash,immutable_url,artifact_status,status_reason) "
                    "VALUES(:analysis_release_id,:source_release_id,:election_slug,:artifact_id,"
                    ":kind,:schema_version,:media_type,:record_count,:byte_size,:byte_hash,"
                    ":content_hash,:immutable_url,:status,:status_reason)"
                ),
                {
                    "analysis_release_id": analysis_release_id,
                    "source_release_id": source_release_id,
                    "election_slug": election_slug,
                    "artifact_id": artifact["artifact_id"],
                    "kind": artifact["kind"],
                    "schema_version": artifact["schema_version"],
                    "media_type": artifact["media_type"],
                    "record_count": artifact["record_count"],
                    "byte_size": artifact["byte_size"],
                    "byte_hash": artifact["byte_hash"],
                    "content_hash": artifact["content_hash"],
                    "immutable_url": url,
                    "status": status,
                    "status_reason": artifact.get("status_reason"),
                },
            )
        for anomaly in anomalies_value:
            anomaly_id = _required_string(anomaly.get("id"), "anomaly.id")
            family = _required_string(anomaly.get("family"), "anomaly.family")
            reason = anomaly.get("reason")
            explanation = _required_string(anomaly.get("explanation"), "anomaly.explanation")
            provenance = anomaly.get("provenance") or {}
            calculations = anomaly.get("calculations") or {}
            limitations = anomaly.get("limitations") or []
            evidence = {
                "affected_votes": anomaly.get("affected_votes"),
                "reason": reason,
            }
            connection.execute(
                text(
                    "INSERT INTO analysis_anomalies(analysis_release_id,source_release_id,"
                    "source_election_slug,anomaly_id,family,evidence_tier,audit_priority,"
                    "evaluability,reason_code,geography_id,explanation_es,explanation_en,evidence,"
                    "calculations,limitations,provenance_hash) VALUES(:analysis_release_id,"
                    ":source_release_id,:election_slug,:anomaly_id,:family,'deterministic',"
                    ":priority,:evaluability,:reason,:geography_id,:explanation,:explanation,"
                    "CAST(:evidence AS jsonb),CAST(:calculations AS jsonb),"
                    "CAST(:limitations AS jsonb),:provenance_hash)"
                ),
                {
                    "analysis_release_id": analysis_release_id,
                    "source_release_id": source_release_id,
                    "election_slug": election_slug,
                    "anomaly_id": anomaly_id,
                    "family": family,
                    "priority": anomaly.get("audit_priority_points", 0),
                    "evaluability": "evaluable" if anomaly.get("evaluable") else "not_evaluable",
                    "reason": reason,
                    "geography_id": anomaly.get("unit_id"),
                    "explanation": explanation,
                    "evidence": json.dumps(evidence, allow_nan=False),
                    "calculations": json.dumps(calculations, allow_nan=False),
                    "limitations": json.dumps(limitations, allow_nan=False),
                    "provenance_hash": _hash_json(provenance),
                },
            )
        reports: tuple[
            tuple[
                str,
                str,
                str,
                object,
                dict[str, object],
                dict[str, object],
                dict[str, object],
                str,
            ],
            ...,
        ] = (
            (
                "eligibility",
                "eligibility",
                "evaluable",
                None,
                eligibility_value,
                {},
                {},
                "eligibility",
            ),
            (
                "descriptive",
                "descriptive",
                "evaluable",
                None,
                descriptive_value,
                {},
                {},
                "descriptive_summary",
            ),
            (
                "model-diagnostics",
                "model_diagnostics",
                "research_preview",
                "independent_validation_required",
                model_diagnostics_value,
                {},
                {},
                "model_diagnostics",
            ),
            (
                "validation",
                "validation",
                "not_evaluable",
                artifact_by_kind["validation"].get("status_reason"),
                {},
                validation_value,
                {},
                "validation",
            ),
            (
                "local-sensitivity",
                "local_sensitivity",
                "not_evaluable",
                artifact_by_kind["local_sensitivity"].get("status_reason"),
                {},
                {},
                local_sensitivity_value,
                "local_sensitivity",
            ),
            (
                "outcome-sensitivity",
                "outcome_sensitivity",
                "not_evaluable",
                artifact_by_kind["outcome_sensitivity"].get("status_reason"),
                outcome_value,
                {},
                {},
                "outcome_sensitivity",
            ),
            (
                "spatial-status",
                "research_model",
                "not_evaluable",
                artifact_by_kind["spatial_status"].get("status_reason"),
                spatial_value,
                {},
                {},
                "spatial_status",
            ),
        )
        for (
            report_id,
            report_kind,
            evaluability,
            reason,
            diagnostics,
            validation,
            local_sensitivity,
            artifact_kind,
        ) in reports:
            connection.execute(
                text(
                    "INSERT INTO analysis_reports(analysis_release_id,source_release_id,"
                    "source_election_slug,report_id,report_kind,schema_version,evaluability,"
                    "status_reason,diagnostics,validation,local_sensitivity,artifact_id,"
                    "provenance_hash) "
                    "VALUES(:analysis_release_id,:source_release_id,:election_slug,:report_id,"
                    ":report_kind,'analysis-report-v1',:evaluability,:reason,"
                    "CAST(:diagnostics AS jsonb),CAST(:validation AS jsonb),"
                    "CAST(:local_sensitivity AS jsonb),:artifact_id,:provenance_hash)"
                ),
                {
                    "analysis_release_id": analysis_release_id,
                    "source_release_id": source_release_id,
                    "election_slug": election_slug,
                    "report_id": report_id,
                    "report_kind": report_kind,
                    "evaluability": evaluability,
                    "reason": reason,
                    "diagnostics": json.dumps(diagnostics, allow_nan=False),
                    "validation": json.dumps(validation, allow_nan=False),
                    "local_sensitivity": json.dumps(local_sensitivity, allow_nan=False),
                    "artifact_id": artifact_by_kind[artifact_kind]["artifact_id"],
                    "provenance_hash": _hash_json(
                        {
                            "diagnostics": diagnostics,
                            "validation": validation,
                            "local_sensitivity": local_sensitivity,
                        }
                    ),
                },
            )
        connection.execute(
            text(
                "INSERT INTO analysis_exposures(analysis_release_id,source_release_id,"
                "source_election_slug,exposure_tier,manifest_hash,exposed_at) VALUES("
                ":analysis_release_id,:source_release_id,:election_slug,'internal',"
                ":manifest_hash,CURRENT_TIMESTAMP)"
            ),
            {
                "analysis_release_id": analysis_release_id,
                "source_release_id": source_release_id,
                "election_slug": election_slug,
                "manifest_hash": manifest_hash,
            },
        )
    return AnalysisLoadResult(
        analysis_release_id,
        manifest_hash,
        len(artifacts),
        len(anomalies_value),
        len(reports),
        True,
    )
