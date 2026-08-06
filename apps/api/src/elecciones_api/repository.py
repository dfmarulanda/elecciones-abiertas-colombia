"""Repository boundary and deterministic fixture implementation."""
# ruff: noqa: E501, S608

import hashlib
import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from .db import ReleaseModel
from .schemas import (
    ANALYTICAL_DISCLOSURE_EN,
    ANALYTICAL_DISCLOSURE_ES,
    AnalysisAnomaly,
    AnalysisReport,
    AnalysisSummary,
    Bulletin,
    BulletinResult,
    ComparisonItem,
    Dataset,
    ElectionSummary,
    EvidenceDocument,
    Geography,
    LocalizedText,
    MesaDetail,
    OutcomeSensitivity,
    OutcomeSensitivityArtifact,
    ResultFact,
    ReviewSignal,
)


class ReleaseNotFoundError(LookupError):
    pass


class ResourceNotFoundError(LookupError):
    pass


class RepositoryUnavailableError(RuntimeError):
    """The configured read model cannot safely serve a public release."""

    pass


_EMPTY_REVIEW_DISCLOSURE = LocalizedText(
    es=(
        "Este puntaje prioriza registros para revisión. No es una probabilidad ni un hallazgo "
        "de fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores."
    ),
    en=(
        "This score prioritizes records for review. It is not a probability or finding of fraud. "
        "Absence of a signal does not prove that a mesa was error-free."
    ),
)

_MAX_OUTCOME_ARTIFACT_BYTES = 2 * 1024 * 1024
_SHA256_HEX = frozenset("0123456789abcdef")
_CONTEXT_LEVELS = ("national", "department", "municipality", "zone", "polling_place", "mesa")
_CONTEXT_METRICS = (
    "registered_electors", "voters", "valid_votes", "blank_votes", "null_votes", "unmarked_votes"
)
_CONTEXT_STATUS = ("observed", "unknown", "unavailable", "not_applicable")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _SHA256_HEX for character in value)
    )


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


class ReadRepository(Protocol):
    """Read operations all implementations must offer to the HTTP layer."""

    @property
    def data_version(self) -> str: ...

    @property
    def is_fixture(self) -> bool: ...

    def summary(self, slug: str, version: str | None) -> ElectionSummary: ...

    def results(self, slug: str, version: str | None) -> list[ResultFact]: ...

    def geography(self, geography_id: str, version: str | None) -> Geography: ...

    def mesa(self, mesa_id: str, version: str | None, source_type: str | None) -> MesaDetail: ...

    def evidence(self, mesa_id: str, version: str | None) -> list[EvidenceDocument]: ...

    def comparisons(self, mesa_id: str, version: str | None) -> list[ComparisonItem]: ...

    def bulletins(self, slug: str, version: str | None) -> list[Bulletin]: ...

    def bulletin_result(self, bulletin_id: str, version: str | None) -> BulletinResult: ...

    def review_signals(self, slug: str, version: str | None) -> list[ReviewSignal]: ...

    def datasets(self, slug: str, version: str | None) -> list[Dataset]: ...

    def dataset(self, dataset_id: str, version: str | None) -> Dataset: ...

    def raw_dataset_rows(self, dataset_id: str, version: str | None) -> Iterable[ResultFact]: ...

    def dataset_artifact_url(self, dataset_id: str, version: str | None) -> str: ...

    def signal_geography_ids(self, mesa_id: str, version: str | None) -> set[str]: ...

    def review_methodology_version(self, slug: str, version: str | None) -> str: ...

    def review_disclosure(self, slug: str, version: str | None) -> LocalizedText: ...

    def analysis_summary(self, slug: str, version: str | None) -> AnalysisSummary: ...

    def anomalies(self, slug: str, version: str | None) -> list[AnalysisAnomaly]: ...

    def anomaly(self, slug: str, anomaly_id: str, version: str | None) -> AnalysisAnomaly: ...

    def analysis_report(
        self, slug: str, report_kind: str, version: str | None
    ) -> AnalysisReport: ...


class FixtureRepository:
    """A read-only release repository loaded from the synthetic development data."""

    _data: dict[str, Any]
    _version: str
    _is_fixture: bool

    def __init__(self, fixture_path: Path) -> None:
        loaded = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("The fixture release must be a JSON object.")
        self._data = cast(dict[str, Any], loaded)
        self._version = cast(str, self._data["release"]["data_version"])
        self._is_fixture = True

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any], *, is_fixture: bool) -> "FixtureRepository":
        """Validate a release-shaped materialized snapshot from the SQL read model."""
        repository = cls.__new__(cls)
        repository._data = snapshot
        repository._version = cast(str, snapshot["release"]["data_version"])
        repository._is_fixture = is_fixture
        return repository

    @property
    def is_fixture(self) -> bool:
        return self._is_fixture

    @property
    def data_version(self) -> str:
        return self._version

    def _assert_version(self, version: str | None) -> str:
        if version is not None and version != self._version:
            raise ReleaseNotFoundError(f"Release '{version}' was not found.")
        return self._version

    def _assert_election(self, slug: str, version: str | None) -> str:
        self._assert_version(version)
        if slug != self._data["election"]["slug"]:
            raise ResourceNotFoundError(f"Election '{slug}' was not found.")
        return self._version

    def _mesa(self, mesa_id: str, version: str | None) -> dict[str, Any]:
        self._assert_version(version)
        mesa = next((item for item in self._data["mesas"] if item["id"] == mesa_id), None)
        if mesa is None:
            raise ResourceNotFoundError(f"Mesa '{mesa_id}' was not found.")
        return cast(dict[str, Any], mesa)

    def summary(self, slug: str, version: str | None) -> ElectionSummary:
        self._assert_election(slug, version)
        return ElectionSummary.model_validate(self._data["summary"])

    def results(self, slug: str, version: str | None) -> list[ResultFact]:
        self._assert_election(slug, version)
        return [ResultFact.model_validate(item) for item in self._data["results"]]

    def geography(self, geography_id: str, version: str | None) -> Geography:
        self._assert_version(version)
        item = next(
            (entry for entry in self._data["geographies"] if entry["id"] == geography_id), None
        )
        if item is None:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        return Geography.model_validate(item)

    def mesa(self, mesa_id: str, version: str | None, source_type: str | None) -> MesaDetail:
        mesa = self._mesa(mesa_id, version)
        candidates = [
            result
            for result in self.results(self._data["election"]["slug"], version)
            if result.mesa_id == mesa_id
        ]
        if source_type is not None:
            candidates = [
                result for result in candidates if result.provenance.source_type == source_type
            ]
        if not candidates:
            raise ResourceNotFoundError("No result from that source layer was found for this mesa.")
        geography = self.geography(mesa["municipality_id"], version)
        polling_place = self.geography(mesa["polling_place_id"], version)
        source_types = sorted(
            {
                result.provenance.source_type
                for result in self.results(self._data["election"]["slug"], version)
                if result.mesa_id == mesa_id
            }
        )
        return MesaDetail.model_validate(
            {
                "id": mesa["id"],
                "display_number": mesa["display_number"],
                "geography": geography,
                "polling_place": polling_place,
                "available_source_types": source_types,
                "result": candidates[0],
                "data_version": self._version,
            }
        )

    def evidence(self, mesa_id: str, version: str | None) -> list[EvidenceDocument]:
        self._mesa(mesa_id, version)
        handling = self._data.get("evidence_handling", {})
        raw_evidence = self._data.get("evidence", [])
        if not isinstance(raw_evidence, list):
            raise RepositoryUnavailableError("The release evidence index is invalid.")
        # Immutable releases produced before the index-only policy can still
        # be read, but their historical document-processing fields are never
        # re-exposed.  A rematerialized release must use the new index shape.
        if any("source_index_url" not in item for item in raw_evidence if isinstance(item, Mapping)):
            return []
        if not isinstance(handling, Mapping) or handling:
            raise RepositoryUnavailableError("The release violates the E-14 index-only policy.")
        documents: list[EvidenceDocument] = []
        for item in raw_evidence:
            if not isinstance(item, Mapping):
                raise RepositoryUnavailableError("The release evidence index is invalid.")
            if item["mesa_id"] != mesa_id:
                continue
            documents.append(EvidenceDocument.model_validate(item))
        return documents

    def comparisons(self, mesa_id: str, version: str | None) -> list[ComparisonItem]:
        self._mesa(mesa_id, version)
        return [
            ComparisonItem.model_validate(item)
            for item in self._data["comparisons"].get(mesa_id, [])
        ]

    def bulletins(self, slug: str, version: str | None) -> list[Bulletin]:
        self._assert_election(slug, version)
        return [
            Bulletin.model_validate(
                {key: value for key, value in item.items() if key != "candidate_votes"}
            )
            for item in self._data["bulletins"]
        ]

    def bulletin_result(self, bulletin_id: str, version: str | None) -> BulletinResult:
        self._assert_version(version)
        bulletin_data = next(
            (item for item in self._data["bulletins"] if item["id"] == bulletin_id), None
        )
        if bulletin_data is None:
            raise ResourceNotFoundError(f"Bulletin '{bulletin_id}' was not found.")
        unknown = {"value": None, "status": "unknown"}
        result = {
            "id": f"{bulletin_id}-national",
            "election_slug": self._data["election"]["slug"],
            "geography_id": "CO",
            "geography_level": "national",
            "mesa_id": None,
            "registered_electors": unknown,
            "voters": unknown,
            "valid_votes": {
                "value": sum(bulletin_data["candidate_votes"].values()),
                "status": "observed",
            },
            "blank_votes": unknown,
            "null_votes": unknown,
            "unmarked_votes": unknown,
            "candidates": [
                {"candidate_id": candidate_id, "votes": {"value": votes, "status": "observed"}}
                for candidate_id, votes in bulletin_data["candidate_votes"].items()
            ],
            "provenance": self._data["provenance"],
        }
        bulletin = {key: value for key, value in bulletin_data.items() if key != "candidate_votes"}
        return BulletinResult.model_validate(
            {"bulletin": bulletin, "result": result, "provenance": self._data["provenance"]}
        )

    def review_signals(self, slug: str, version: str | None) -> list[ReviewSignal]:
        self._assert_election(slug, version)
        values = self._data["review_signals"]
        if self._is_fixture:

            def fixture_component(raw: Mapping[str, object]) -> dict[str, object]:
                component = dict(raw)
                statistical = component.get("component_type") in {
                    "peer_distribution",
                    "spatial_cluster",
                }
                component["evidence_artifact_hash"] = (
                    None
                    if statistical
                    else hashlib.sha256(
                        json.dumps(
                            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                        ).encode()
                    ).hexdigest()
                )
                component["evidence_artifact_kind"] = (
                    None
                    if statistical
                    else "reconciliation_result"
                    if component.get("component_type")
                    in {"verified_accounting_failure", "conflicting_official_records"}
                    else "document_review"
                )
                return component

            values = [
                {
                    **item,
                    "tier": ("no_review_signals" if int(item["score"]) < 15 else item["tier"]),
                    "components": [
                        fixture_component(component) for component in item["components"]
                    ],
                }
                for item in values
            ]
        return [ReviewSignal.model_validate(item) for item in values]

    def signal_geography_ids(self, mesa_id: str, version: str | None) -> set[str]:
        mesa = self._mesa(mesa_id, version)
        return {
            "CO",
            mesa["department_id"],
            mesa["municipality_id"],
            mesa["polling_place_id"],
            mesa_id,
        }

    def review_methodology_version(self, slug: str, version: str | None) -> str:
        self._assert_election(slug, version)
        return cast(str, self._data["release"]["methodology_version"])

    def review_disclosure(self, slug: str, version: str | None) -> LocalizedText:
        signals = self.review_signals(slug, version)
        if not signals:
            return _EMPTY_REVIEW_DISCLOSURE
        return signals[0].disclosure

    def _analysis_disclosure(self) -> LocalizedText:
        return LocalizedText(es=ANALYTICAL_DISCLOSURE_ES, en=ANALYTICAL_DISCLOSURE_EN)

    def anomalies(self, slug: str, version: str | None) -> list[AnalysisAnomaly]:
        """Project legacy immutable review signals into the v1 analysis resource.

        The projection exposes only facts already in the frozen release.  It
        purposefully records missing explanation and ballot-vector artifacts as
        non-evaluable instead of manufacturing an explanation or an estimate.
        """
        signals = self.review_signals(slug, version)
        type_map = {
            "verified_accounting_failure": "structural_arithmetic",
            "conflicting_official_records": "cross_source_documentary",
            "documentary_difference_major": "cross_source_documentary",
            "documentary_difference_minor": "cross_source_documentary",
            "document_missing_duplicated_ambiguous": "identity_coverage",
            "peer_distribution": "peer_distribution",
            "spatial_cluster": "spatial",
        }
        result: list[AnalysisAnomaly] = []
        for signal in signals:
            anomaly_types = sorted({type_map[item.component_type] for item in signal.components})
            preview_reasons = [
                "legacy_release_has_no_preregistered_explanation_artifact",
                "complete_ballot_vector_not_published",
            ]
            if any(item.component_type in {"peer_distribution", "spatial_cluster"} for item in signal.components):
                preview_reasons.append("independent_simulation_validation_artifact_not_published")
            result.append(
                AnalysisAnomaly.model_validate(
                    {
                        "id": signal.id,
                        "mesa_id": signal.mesa_id,
                        "anomaly_types": anomaly_types,
                        "is_anomaly": bool(signal.components),
                        "audit_priority_score": signal.score,
                        "explanation": {
                            "status": "non_evaluable",
                            "preregistration_hash": None,
                            "available_data_hash": None,
                            "reviewed_at": None,
                            "quantitative_effect": {"value": None, "status": "unknown"},
                            "quantitative_p_value": {"value": None, "status": "unknown"},
                            "notes": None,
                        },
                        "minimum_ballot_edits": {"value": None, "status": "unknown"},
                        "minimum_ballot_edits_status": "not_evaluable",
                        "minimum_ballot_edits_reason": "complete_mutually_exclusive_ballot_categories_not_published",
                        "components": [item.model_dump(mode="json") for item in signal.components],
                        "research_preview": True,
                        "ineligible_reasons": preview_reasons,
                        "methodology_version": signal.methodology_version,
                        "disclosure": self._analysis_disclosure(),
                        "provenance": signal.provenance,
                    }
                )
            )
        return result

    def anomaly(self, slug: str, anomaly_id: str, version: str | None) -> AnalysisAnomaly:
        value = next((item for item in self.anomalies(slug, version) if item.id == anomaly_id), None)
        if value is None:
            raise ResourceNotFoundError(f"Analysis anomaly '{anomaly_id}' was not found.")
        return value

    def analysis_summary(self, slug: str, version: str | None) -> AnalysisSummary:
        anomalies = self.anomalies(slug, version)
        coverage = self.summary(slug, version).coverage
        counts = {
            kind: sum(kind in item.anomaly_types for item in anomalies)
            for kind in (
                "structural_arithmetic",
                "identity_coverage",
                "cross_source_documentary",
                "peer_distribution",
                "spatial",
            )
        }
        provenance = self.summary(slug, version).provenance
        return AnalysisSummary.model_validate(
            {
                "election_slug": slug,
                "data_version": self._version,
                "methodology_version": self.review_methodology_version(slug, version),
                "total_records_evaluated": {"value": len(anomalies), "status": "observed"},
                "anomaly_count": {"value": sum(item.is_anomaly for item in anomalies), "status": "observed"},
                "anomaly_counts": {
                    kind: {"value": value, "status": "observed"} for kind, value in counts.items()
                },
                "missingness": coverage,
                "research_preview": True,
                "ineligible_reasons": [
                    "independent_simulation_validation_artifacts_not_published",
                    "hierarchical_and_psis_validation_not_implemented",
                ],
                "disclosure": self._analysis_disclosure(),
                "provenance": provenance,
            }
        )

    def analysis_report(self, slug: str, report_kind: str, version: str | None) -> AnalysisReport:
        if report_kind not in {"model_diagnostics", "validation", "local_sensitivity"}:
            raise ResourceNotFoundError(f"Analysis report '{report_kind}' was not found.")
        summary = self.summary(slug, version)
        reasons = {
            "model_diagnostics": ["hierarchical_model_not_implemented", "psis_diagnostics_not_implemented"],
            "validation": ["independent_simulation_artifacts_not_published"],
            "local_sensitivity": ["complete_ballot_vector_not_published"],
        }[report_kind]
        return AnalysisReport.model_validate(
            {
                "report_kind": report_kind,
                "status": "research_preview",
                "research_preview": True,
                "ineligible_reasons": reasons,
                "methodology_version": self.review_methodology_version(slug, version),
                "artifact_hash": None,
                "missingness": summary.coverage,
                "provenance": summary.provenance,
                "disclosure": self._analysis_disclosure(),
                "metrics": {},
            }
        )

    def datasets(self, slug: str, version: str | None) -> list[Dataset]:
        self._assert_election(slug, version)
        return [Dataset.model_validate(item) for item in self._data["datasets"]]

    def dataset(self, dataset_id: str, version: str | None) -> Dataset:
        self._assert_version(version)
        dataset = next((item for item in self._data["datasets"] if item["id"] == dataset_id), None)
        if dataset is None:
            raise ResourceNotFoundError(f"Dataset '{dataset_id}' was not found.")
        return Dataset.model_validate(dataset)

    def raw_dataset_rows(self, dataset_id: str, version: str | None) -> Iterable[ResultFact]:
        self.dataset(dataset_id, version)
        return self.results(self._data["election"]["slug"], version)

    def dataset_artifact_url(self, dataset_id: str, version: str | None) -> str:
        return str(self.dataset(dataset_id, version).url)


class PostgresReadRepository:
    """Bounded PostgreSQL adapter for materialized, immutable public releases.

    The normalised tables retain analytical lineage. This public read adapter only
    serves a pipeline-produced ``api_snapshot`` held in ``releases.manifest``;
    this keeps every response tied to one verified release and prevents routes
    from independently joining partially-published tables.
    """

    is_fixture = False

    def __init__(
        self,
        database_url: str,
        active_release_id: str,
        allowed_artifact_hosts: set[str] | None = None,
        outcome_artifact_fetcher: Callable[[str], bytes] | None = None,
    ) -> None:
        parsed = make_url(database_url)
        if not parsed.drivername.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL/Neon URL.")
        driver = parsed.drivername.replace("+asyncpg", "+psycopg")
        if driver == "postgresql":
            driver = "postgresql+psycopg"
        self._engine: Engine = create_engine(parsed.set(drivername=driver), pool_pre_ping=True)
        self._sessions = sessionmaker(self._engine, class_=Session, expire_on_commit=False)
        self._active_release_id = active_release_id
        self._release_cache: dict[str, FixtureRepository] = {}
        self._allowed_artifact_hosts = {
            host.lower().rstrip(".") for host in (allowed_artifact_hosts or set())
        }
        self._outcome_artifact_fetcher = outcome_artifact_fetcher

    @property
    def active_release_id(self) -> str:
        return self._active_release_id

    def _snapshot(self, version: str | None) -> FixtureRepository:
        selected_version = version or self._active_release_id
        cached = self._release_cache.get(selected_version)
        if cached is not None:
            return cached
        statement = select(ReleaseModel).where(ReleaseModel.id == selected_version)
        try:
            with self._sessions() as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                release = session.scalar(statement)
        except Exception as exc:
            raise RepositoryUnavailableError(
                "The configured PostgreSQL read model is unavailable."
            ) from exc
        if release is None:
            raise ReleaseNotFoundError(f"Release '{selected_version}' was not found.")
        manifest = release.manifest
        snapshot = manifest.get("api_snapshot") if isinstance(manifest, dict) else None
        if not isinstance(snapshot, dict):
            raise RepositoryUnavailableError(
                "The selected release has no validated api_snapshot materialization."
            )
        try:
            repository = FixtureRepository.from_snapshot(
                cast(dict[str, Any], snapshot), is_fixture=False
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RepositoryUnavailableError("The selected api_snapshot is invalid.") from exc
        if repository.data_version != release.id:
            raise RepositoryUnavailableError(
                "The api_snapshot data_version does not match its release id."
            )
        self._release_cache[selected_version] = repository
        return repository

    @property
    def data_version(self) -> str:
        selected = self._active_release_id
        if self._normalized(
            """SELECT 1 FROM release_exposures x JOIN releases r ON r.id=x.release_id
            WHERE x.release_id=:r AND x.access_scope='public' AND x.approved_at IS NOT NULL
            AND r.status='published' LIMIT 1""", {"r": selected}
        ):
            return selected
        return self._snapshot(None).data_version

    def summary(self, slug: str, version: str | None) -> ElectionSummary:
        self._legacy_public(slug, version)
        return self._snapshot(version).summary(slug, version)

    def results(self, slug: str, version: str | None) -> list[ResultFact]:
        self._legacy_public(slug, version)
        return self._snapshot(version).results(slug, version)

    def geography(self, geography_id: str, version: str | None) -> Geography:
        return self._public_snapshot(version).geography(geography_id, version)

    def mesa(self, mesa_id: str, version: str | None, source_type: str | None) -> MesaDetail:
        return self._public_snapshot(version).mesa(mesa_id, version, source_type)

    def evidence(self, mesa_id: str, version: str | None) -> list[EvidenceDocument]:
        return self._public_snapshot(version).evidence(mesa_id, version)

    def comparisons(self, mesa_id: str, version: str | None) -> list[ComparisonItem]:
        return self._public_snapshot(version).comparisons(mesa_id, version)

    def bulletins(self, slug: str, version: str | None) -> list[Bulletin]:
        self._legacy_public(slug, version)
        return self._snapshot(version).bulletins(slug, version)

    def bulletin_result(self, bulletin_id: str, version: str | None) -> BulletinResult:
        return self._public_snapshot(version).bulletin_result(bulletin_id, version)

    def review_signals(self, slug: str, version: str | None) -> list[ReviewSignal]:
        self._reject_context_analysis(version or self._active_release_id, slug)
        self._legacy_public(slug, version)
        return self._snapshot(version).review_signals(slug, version)

    def datasets(self, slug: str, version: str | None) -> list[Dataset]:
        selected = version or self._active_release_id
        if self._context_scope(selected, slug) is not None:
            return [Dataset.model_validate(item) for item in self._context_datasets(selected, slug)]
        self._legacy_public(slug, version)
        return self._snapshot(version).datasets(slug, version)

    def dataset(self, dataset_id: str, version: str | None) -> Dataset:
        return self._public_snapshot(version).dataset(dataset_id, version)

    def raw_dataset_rows(self, dataset_id: str, version: str | None) -> Iterable[ResultFact]:
        raise RepositoryUnavailableError(
            "Production datasets must be served from their immutable artifact."
        )

    def dataset_artifact_url(self, dataset_id: str, version: str | None) -> str:
        return self._public_snapshot(version).dataset_artifact_url(dataset_id, version)

    def signal_geography_ids(self, mesa_id: str, version: str | None) -> set[str]:
        return self._public_snapshot(version).signal_geography_ids(mesa_id, version)

    def review_methodology_version(self, slug: str, version: str | None) -> str:
        self._legacy_public(slug, version)
        return self._snapshot(version).review_methodology_version(slug, version)

    def review_disclosure(self, slug: str, version: str | None) -> LocalizedText:
        self._legacy_public(slug, version)
        return self._snapshot(version).review_disclosure(slug, version)

    def analysis_summary(self, slug: str, version: str | None) -> AnalysisSummary:
        self._reject_context_analysis(version or self._active_release_id, slug)
        self._legacy_public(slug, version)
        return self._snapshot(version).analysis_summary(slug, version)

    def anomalies(self, slug: str, version: str | None) -> list[AnalysisAnomaly]:
        self._reject_context_analysis(version or self._active_release_id, slug)
        self._legacy_public(slug, version)
        return self._snapshot(version).anomalies(slug, version)

    def anomaly(self, slug: str, anomaly_id: str, version: str | None) -> AnalysisAnomaly:
        self._reject_context_analysis(version or self._active_release_id, slug)
        self._legacy_public(slug, version)
        return self._snapshot(version).anomaly(slug, anomaly_id, version)

    def analysis_report(self, slug: str, report_kind: str, version: str | None) -> AnalysisReport:
        self._reject_context_analysis(version or self._active_release_id, slug)
        self._legacy_public(slug, version)
        return self._snapshot(version).analysis_report(slug, report_kind, version)

    # Normalized multirelease reads.  They intentionally do not fall back to a
    # JSON snapshot: an absent public exposure is not a legacy-preview request.
    def _normalized(self, statement: str, values: dict[str, object]) -> list[dict[str, object]]:
        try:
            with self._sessions() as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                return [dict(row) for row in session.execute(text(statement), values).mappings()]
        except Exception as exc:
            raise RepositoryUnavailableError(
                "The configured PostgreSQL read model is unavailable."
            ) from exc

    def _context_scope(self, release_id: str, election_slug: str) -> int | None:
        """Return the compact scope only after the ordinary public gate."""
        rows = self._normalized(
            """SELECT c.id FROM context_release_scopes c
            JOIN release_exposures x ON (x.release_id=c.release_id AND x.election_slug=c.election_slug)
            JOIN releases r ON r.id=c.release_id
            WHERE c.release_id=:r AND c.election_slug=:e AND x.access_scope='public'
            AND x.approved_at IS NOT NULL AND r.status='published'""",
            {"r": release_id, "e": election_slug},
        )
        return None if not rows else int(cast(Any, rows[0]["id"]))

    def _reject_context_analysis(self, release_id: str, election_slug: str) -> None:
        if self._context_scope(release_id, election_slug) is not None:
            raise ResourceNotFoundError(
                "Analysis and review signals are unavailable for a context-only historical release."
            )

    @staticmethod
    def _context_metrics(row: Mapping[str, object]) -> dict[str, dict[str, object]]:
        mask = int(cast(int, row["metrics_status"]))
        result: dict[str, dict[str, object]] = {}
        for offset, metric in enumerate(_CONTEXT_METRICS):
            status = _CONTEXT_STATUS[(mask >> (offset * 2)) & 3]
            result[metric] = {"value": row[metric], "status": status}
        return result

    def _context_datasets(self, release_id: str, election_slug: str) -> list[dict[str, object]]:
        rows = self._normalized(
            """SELECT manifest FROM releases r JOIN release_exposures x ON x.release_id=r.id
            WHERE r.id=:r AND x.election_slug=:e AND x.access_scope='public'
            AND x.approved_at IS NOT NULL AND r.status='published'""",
            {"r": release_id, "e": election_slug},
        )
        if not rows:
            raise ReleaseNotFoundError("The requested release/election is not publicly exposed.")
        manifest = rows[0]["manifest"]
        if not isinstance(manifest, dict):
            raise RepositoryUnavailableError("The context release manifest is invalid.")
        datasets = manifest.get("datasets")
        if not isinstance(datasets, list) or not all(isinstance(item, dict) for item in datasets):
            raise RepositoryUnavailableError("The context release manifest has invalid datasets.")
        return cast(list[dict[str, object]], datasets)

    def public_elections(self) -> list[dict[str, object]]:
        return self._normalized(
            """SELECT e.release_id,e.election_slug,e.name_es,e.name_en,e.round,e.election_date,r.status,r.methodology_version,
          x.manifest_hash AS release_manifest_hash,x.approved_at AS exposure_approved_at,
          COALESCE(json_agg(json_build_object('id',s.id,'source_type',s.source_type,'legal_status',s.legal_status,'source_url',s.source_url,'content_hash',s.content_hash)) FILTER (WHERE s.id IS NOT NULL), '[]'::json) AS sources
          FROM release_elections e JOIN release_exposures x USING (release_id,election_slug)
          JOIN releases r ON r.id=e.release_id LEFT JOIN release_sources s USING (release_id,election_slug)
          WHERE x.access_scope='public' AND x.approved_at IS NOT NULL AND r.status='published'
          GROUP BY e.release_id,e.election_slug,e.name_es,e.name_en,e.round,e.election_date,r.status,r.methodology_version,x.manifest_hash,x.approved_at
          ORDER BY e.election_date,e.election_slug""",
            {},
        ) + self._preliminary_elections()

    def _preliminary_elections(self) -> list[dict[str, object]]:
        """Catalogue entries for preliminary grants.

        Kept as a separate query rather than a relaxed predicate on the one
        above: the certified branch must stay exactly as it is. Note
        ``exposure_approved_at`` is emitted as NULL — the contract rejects a
        candidate release that claims an approval, and claiming one here would
        be the same mislabel in a different field.

        No extra ``exposure_class`` field is added. The frozen contract already
        distinguishes these unambiguously: the certified branch requires
        ``status='published'``, so a ``candidate`` entry in this catalogue can
        only have arrived through the preliminary door. Widening the contract to
        restate that would add a field that can disagree with the predicate that
        produced it.
        """
        rows = self._normalized(
            """SELECT e.release_id,e.election_slug,e.name_es,e.name_en,e.round,e.election_date,r.status,r.methodology_version,
          x.manifest_hash AS release_manifest_hash,
          NULL::timestamptz AS exposure_approved_at,
          COALESCE(json_agg(json_build_object('id',s.id,'source_type',s.source_type,'legal_status',s.legal_status,'source_url',s.source_url,'content_hash',s.content_hash)) FILTER (WHERE s.id IS NOT NULL), '[]'::json) AS sources
          FROM release_elections e JOIN release_exposures x USING (release_id,election_slug)
          JOIN releases r ON r.id=e.release_id LEFT JOIN release_sources s USING (release_id,election_slug)
          WHERE x.access_scope='preliminary' AND x.preliminary_approved_at IS NOT NULL
            AND r.status='candidate' AND r.synthetic = false
          GROUP BY e.release_id,e.election_slug,e.name_es,e.name_en,e.round,e.election_date,r.status,r.methodology_version,x.manifest_hash
          ORDER BY e.election_date,e.election_slug""",
            {},
        )
        return rows

    def _authorized(self, release_id: str, election_slug: str) -> None:
        rows = self._normalized(
            """SELECT 1 FROM release_exposures x JOIN releases r ON r.id=x.release_id
            WHERE x.release_id=:r AND x.election_slug=:e AND x.access_scope='public'
            AND x.approved_at IS NOT NULL AND r.status='published'""",
            {"r": release_id, "e": election_slug},
        )
        if not rows:
            raise ReleaseNotFoundError("The requested release/election is not publicly exposed.")

    def _preliminary_grant(
        self, release_id: str, election_slug: str
    ) -> dict[str, object] | None:
        """The second, disjoint door: a reviewed grant over a candidate release.

        Deliberately narrower than it looks. ``r.status='candidate'`` means a
        *published* release can never arrive through here either, so the two
        predicates exclude each other in both directions rather than one merely
        being weaker. The caveat text is read from the grant row, so a response
        cannot be labelled by anything other than the approval that authorised
        it.
        """
        rows = self._normalized(
            """SELECT x.preliminary_caveat_es, x.preliminary_caveat_en
            FROM release_exposures x JOIN releases r ON r.id=x.release_id
            WHERE x.release_id=:r AND x.election_slug=:e
            AND x.access_scope='preliminary' AND x.preliminary_approved_at IS NOT NULL
            AND r.status='candidate' AND r.synthetic = false""",
            {"r": release_id, "e": election_slug},
        )
        if not rows:
            return None
        return {
            "class": "preliminary",
            "caveat": {
                "es": rows[0]["preliminary_caveat_es"],
                "en": rows[0]["preliminary_caveat_en"],
            },
        }

    def _authorized_any(self, release_id: str, election_slug: str) -> dict[str, object]:
        """Authorise through either door and report WHICH one opened.

        Callers must carry the returned class into the response: a preliminary
        read that renders unlabelled is the failure this whole mechanism exists
        to prevent. Only the release-scoped normalized reads use this; legacy
        routes, datasets, analysis, review signals and outcome sensitivity stay
        on ``_authorized`` and remain certified-only.
        """
        grant = self._preliminary_grant(release_id, election_slug)
        if grant is not None:
            return grant
        self._authorized(release_id, election_slug)
        return {"class": "certified", "caveat": None}

    def _legacy_public(self, election_slug: str, version: str | None) -> None:
        """Do not let the legacy snapshot adapter bypass release exposure.

        FixtureRepository is still intentionally available for local fixtures;
        this guard applies only to PostgreSQL-backed public serving.
        """
        self._authorized(version or self._active_release_id, election_slug)

    def _assert_release_has_public_exposure(self, version: str | None) -> None:
        """Reject a private release before attempting to read its legacy snapshot.

        Legacy geography/mesa routes do not carry an election slug, so they
        cannot call ``_authorized`` directly. This keeps their error semantics
        aligned with the slug-scoped routes and avoids revealing whether an
        internal candidate happens to have an ``api_snapshot`` field.
        """
        selected_version = version or self._active_release_id
        rows = self._normalized(
            """SELECT 1 FROM release_exposures x JOIN releases r ON r.id=x.release_id
            WHERE x.release_id=:r AND x.access_scope='public'
            AND x.approved_at IS NOT NULL AND r.status='published' LIMIT 1""",
            {"r": selected_version},
        )
        if not rows:
            raise ReleaseNotFoundError("The requested release is not publicly exposed.")

    def _public_snapshot(self, version: str | None) -> FixtureRepository:
        self._assert_release_has_public_exposure(version)
        snapshot = self._snapshot(version)
        election = snapshot._data.get("election")
        slug = election.get("slug") if isinstance(election, Mapping) else None
        if not isinstance(slug, str) or not slug:
            raise RepositoryUnavailableError(
                "The selected api_snapshot has no valid election scope."
            )
        self._legacy_public(slug, version)
        return snapshot

    @staticmethod
    def _result_statement(
        release_id: str,
        election_slug: str,
        filters: Mapping[str, object],
        after: tuple[str, ...] | None,
        limit: int | None,
    ) -> tuple[str, dict[str, object]]:
        clauses = ["f.release_id=:r", "f.election_slug=:e"]
        values: dict[str, object] = {"r": release_id, "e": election_slug}
        for field, column in (
            ("geography_id", "f.geography_id"),
            ("geography_level", "f.geography_level"),
            ("source_id", "f.source_id"),
            ("source_type", "s.source_type"),
        ):
            if filters.get(field) is not None:
                clauses.append(f"{column}=:{field}")
                values[field] = filters[field]
        # canonical_path is supplied by the importer, never inferred from a
        # display name.  A slash boundary avoids prefix matches (CO-1/CO-10).
        if filters.get("geography_path") is not None:
            clauses.append(
                "(g.canonical_path=:geography_path OR g.canonical_path LIKE :geography_path_desc)"
            )
            values["geography_path"] = filters["geography_path"]
            values["geography_path_desc"] = f"{filters['geography_path']}/%"
        if filters.get("category_key") is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM release_category_facts cf WHERE cf.release_id=f.release_id AND cf.election_slug=f.election_slug AND cf.result_fact_id=f.id AND cf.category_key=:category_key)"
            )
            values["category_key"] = filters["category_key"]
        if filters.get("status") is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM release_category_facts sf WHERE sf.release_id=f.release_id AND sf.election_slug=f.election_slug AND sf.result_fact_id=f.id AND sf.status=:status)"
            )
            values["status"] = filters["status"]
        if after:
            clauses.append("(f.geography_level,f.geography_id,f.source_id,f.id) > (:a,:b,:c,:d)")
            values.update(dict(zip(("a", "b", "c", "d"), after, strict=True)))
        sql = (
            """SELECT f.id,f.geography_id,f.geography_level,f.mesa_id,f.source_id,f.metrics,
          s.source_type,s.legal_status,s.source_url,s.retrieved_at,s.content_hash,s.parser_version,s.transform_version
          FROM release_result_facts f JOIN release_sources s ON (s.release_id=f.release_id AND s.election_slug=f.election_slug AND s.id=f.source_id)
          JOIN release_geographies g ON (g.release_id=f.release_id AND g.election_slug=f.election_slug AND g.id=f.geography_id)
          WHERE """
            + " AND ".join(clauses)
            + " ORDER BY f.geography_level,f.geography_id,f.source_id,f.id"
        )
        if limit is not None:
            sql += " LIMIT :n"
            values["n"] = limit
        return sql, values

    def normalized_results(
        self,
        release_id: str,
        election_slug: str,
        filters: dict[str, object],
        after: tuple[str, ...] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            return self._context_results(scope_id, filters, after, limit + 1)
        sql, values = self._result_statement(release_id, election_slug, filters, after, limit + 1)
        return self._normalized(sql, values)

    def _context_results(
        self, scope_id: int, filters: Mapping[str, object], after: tuple[str, ...] | None, limit: int | None
    ) -> list[dict[str, object]]:
        clauses = ["f.scope_id=:scope"]
        values: dict[str, object] = {"scope": scope_id}
        for field, column in (("geography_id", "g.external_id"), ("source_id", "s.source_id")):
            if filters.get(field) is not None:
                clauses.append(f"{column}=:{field}")
                values[field] = filters[field]
        if filters.get("geography_level") is not None:
            try:
                values["level"] = _CONTEXT_LEVELS.index(str(filters["geography_level"]))
            except ValueError:
                return []
            clauses.append("g.level=:level")
        if filters.get("source_type") is not None:
            clauses.append("rs.source_type=:source_type")
            values["source_type"] = filters["source_type"]
        if filters.get("geography_path") is not None:
            path = self._context_path_ids(scope_id, str(filters["geography_path"]))
            if path is None:
                return []
            leaf = path[-1]
            clauses.append("g.tree_left>=:tree_left AND g.tree_right<=:tree_right")
            values.update({"tree_left": leaf["tree_left"], "tree_right": leaf["tree_right"]})
        if filters.get("category_key") is not None:
            clauses.append("EXISTS (SELECT 1 FROM context_category_facts cf JOIN context_categories c ON (c.scope_id=cf.scope_id AND c.id=cf.category_id) WHERE cf.scope_id=f.scope_id AND cf.geography_id=f.geography_id AND cf.source_ordinal=f.source_ordinal AND c.category_key=:category_key)")
            values["category_key"] = filters["category_key"]
        if filters.get("status") is not None:
            status = 0 if filters["status"] == "observed" else 2
            clauses.append("EXISTS (SELECT 1 FROM context_category_facts cf WHERE cf.scope_id=f.scope_id AND cf.geography_id=f.geography_id AND cf.source_ordinal=f.source_ordinal AND cf.status=:category_status)")
            values["category_status"] = status
        if after:
            clauses.append("(g.level,g.external_id,s.source_id,(g.external_id || ':' || s.source_id)) > (:a,:b,:c,:d)")
            try:
                cursor_level = _CONTEXT_LEVELS.index(after[0])
            except ValueError as exc:
                raise ResourceNotFoundError("The results cursor has an unknown geography level.") from exc
            values.update({"a": cursor_level, "b": after[1], "c": after[2], "d": after[3]})
        sql = """SELECT (g.external_id || ':' || s.source_id) AS id,g.external_id AS geography_id,
          CASE g.level WHEN 0 THEN 'national' WHEN 1 THEN 'department' WHEN 2 THEN 'municipality' WHEN 3 THEN 'zone' WHEN 4 THEN 'polling_place' ELSE 'mesa' END AS geography_level,
          CASE WHEN g.level=5 THEN g.external_id ELSE NULL END AS mesa_id,s.source_id,f.metrics_status,
          f.registered_electors,f.voters,f.valid_votes,f.blank_votes,f.null_votes,f.unmarked_votes,
          rs.source_type,rs.legal_status,rs.source_url,rs.retrieved_at,rs.content_hash,rs.parser_version,rs.transform_version
          FROM context_result_facts f JOIN context_geographies g ON (g.scope_id=f.scope_id AND g.id=f.geography_id)
          JOIN context_sources s ON (s.scope_id=f.scope_id AND s.ordinal=f.source_ordinal)
          JOIN context_release_scopes cs ON cs.id=f.scope_id
          JOIN release_sources rs ON (rs.release_id=cs.release_id AND rs.election_slug=cs.election_slug AND rs.id=s.source_id)
          WHERE """ + " AND ".join(clauses) + " ORDER BY g.level,g.external_id,s.source_id,(g.external_id || ':' || s.source_id)"
        if limit is not None:
            sql += " LIMIT :n"
            values["n"] = limit
        rows = self._normalized(sql, values)
        for row in rows:
            row["metrics"] = self._context_metrics(row)
        return rows

    def _context_path_ids(self, scope_id: int, geography_id: str) -> list[dict[str, object]] | None:
        external_id = geography_id.rsplit("/", 1)[-1]
        rows = self._normalized(
            """WITH RECURSIVE path AS (SELECT id,external_id,level,code,name,parent_id,tree_left,tree_right,0 AS depth
            FROM context_geographies WHERE scope_id=:scope AND external_id=:id
            UNION ALL SELECT g.id,g.external_id,g.level,g.code,g.name,g.parent_id,g.tree_left,g.tree_right,path.depth+1
            FROM context_geographies g JOIN path ON (g.scope_id=:scope AND g.id=path.parent_id))
            SELECT id,external_id,level,code,name,parent_id,tree_left,tree_right FROM path ORDER BY depth DESC""",
            {"scope": scope_id, "id": external_id},
        )
        if not rows:
            return None
        # The compact store derives this canonical path from the immutable
        # parent chain; it never guesses a hierarchy from a display name.
        canonical_path = "/".join(str(row["external_id"]) for row in rows)
        if "/" in geography_id and geography_id != canonical_path:
            return None
        return rows

    @staticmethod
    def _context_public_path(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "id": row["external_id"],
                "level": _CONTEXT_LEVELS[int(cast(Any, row["level"]))],
                "code": row["code"],
                "name": row["name"],
                "parent_id": None if index == 0 else rows[index - 1]["external_id"],
                "canonical_path": "/".join(str(item["external_id"]) for item in rows[: index + 1]),
            }
            for index, row in enumerate(rows)
        ]

    def _validated_outcome_url(
        self, value: object, *, content_hash: str | None = None, schema: bool = False
    ) -> str:
        if not isinstance(value, str) or value.strip() != value:
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset has an invalid immutable URL."
            )
        parsed = urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset has an invalid immutable URL."
            ) from exc
        allowed_hosts: set[str] = getattr(self, "_allowed_artifact_hosts", set())
        if (
            parsed.scheme != "https"
            or port not in (None, 443)
            or not parsed.hostname
            or parsed.hostname.lower().rstrip(".") not in allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.query)
            or bool(parsed.fragment)
        ):
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset has an invalid immutable URL."
            )
        if schema:
            if not parsed.path.endswith("/outcome-sensitivity.schema.json"):
                raise RepositoryUnavailableError(
                    "The outcome sensitivity dataset does not declare the frozen core schema."
                )
        elif content_hash is None or not parsed.path.endswith(f"/{content_hash}.json"):
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset URL is not content-addressed."
            )
        return value

    def _fetch_outcome_artifact(self, url: str, expected_size: int) -> bytes:
        fetcher = getattr(self, "_outcome_artifact_fetcher", None)
        if fetcher is not None:
            try:
                payload = fetcher(url)
            except Exception as exc:
                raise RepositoryUnavailableError(
                    "The immutable outcome sensitivity dataset could not be read."
                ) from exc
            if not isinstance(payload, bytes):
                raise RepositoryUnavailableError(
                    "The immutable outcome sensitivity dataset did not return bytes."
                )
        else:
            try:
                with (
                    httpx.Client(
                        follow_redirects=False,
                        timeout=httpx.Timeout(10.0, connect=3.0),
                        trust_env=False,
                        headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    ) as client,
                    client.stream("GET", url) as response,
                ):
                    if response.status_code != 200:
                        raise RepositoryUnavailableError(
                            "The immutable outcome sensitivity dataset is unavailable."
                        )
                    content_type = response.headers.get("content-type", "")
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    if media_type != "application/json" or response.headers.get(
                        "content-encoding", "identity"
                    ).lower() not in {"", "identity"}:
                        raise RepositoryUnavailableError(
                            "The immutable outcome sensitivity dataset is not plain JSON."
                        )
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            announced_size = int(content_length)
                        except ValueError as exc:
                            raise RepositoryUnavailableError(
                                "The immutable outcome sensitivity dataset has an invalid size."
                            ) from exc
                        if announced_size != expected_size:
                            raise RepositoryUnavailableError(
                                "The immutable outcome sensitivity dataset size does not match its declaration."
                            )
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > expected_size or size > _MAX_OUTCOME_ARTIFACT_BYTES:
                            raise RepositoryUnavailableError(
                                "The immutable outcome sensitivity dataset exceeds its declared size."
                            )
                        chunks.append(chunk)
                    payload = b"".join(chunks)
            except RepositoryUnavailableError:
                raise
            except httpx.HTTPError as exc:
                raise RepositoryUnavailableError(
                    "The immutable outcome sensitivity dataset could not be read."
                ) from exc
        if len(payload) != expected_size or len(payload) > _MAX_OUTCOME_ARTIFACT_BYTES:
            raise RepositoryUnavailableError(
                "The immutable outcome sensitivity dataset size does not match its declaration."
            )
        return payload

    def normalized_outcome_sensitivity(
        self, release_id: str, election_slug: str
    ) -> OutcomeSensitivity:
        """Return only a release-authenticated, pipeline-materialized outcome context.

        This adapter deliberately has no fallback computation: signal scores and
        historical comparisons cannot be reinterpreted as vote effects here.
        """
        self._authorized(release_id, election_slug)
        rows = self._normalized(
            """SELECT r.manifest,x.manifest_hash FROM releases r
            JOIN release_exposures x ON x.release_id=r.id
            WHERE r.id=:r AND x.election_slug=:e AND x.access_scope='public'
            AND x.approved_at IS NOT NULL AND r.status='published'""",
            {"r": release_id, "e": election_slug},
        )
        if not rows or not isinstance(rows[0].get("manifest"), Mapping):
            raise RepositoryUnavailableError("The selected release has no valid manifest.")
        manifest = cast(Mapping[str, object], rows[0]["manifest"])
        encoded_manifest = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(encoded_manifest).hexdigest() != rows[0].get("manifest_hash"):
            raise RepositoryUnavailableError(
                "The public exposure does not authenticate the selected manifest."
            )
        if "outcome_sensitivity" in manifest:
            raise ResourceNotFoundError(
                "Inline outcome sensitivity values are not public materializations."
            )
        datasets = manifest.get("datasets")
        declarations = datasets if isinstance(datasets, list) else []
        matching = [
            item
            for item in declarations
            if isinstance(item, Mapping)
            and isinstance(item.get("filters"), Mapping)
            and cast(Mapping[str, object], item["filters"]).get("artifact_kind")
            == "outcome_sensitivity"
            and cast(Mapping[str, object], item["filters"]).get("election_slug") == election_slug
            and cast(Mapping[str, object], item["filters"]).get("data_version") == release_id
        ]
        if not matching:
            raise ResourceNotFoundError(
                "No immutable outcome sensitivity dataset is published for this release/election."
            )
        if len(matching) != 1:
            raise RepositoryUnavailableError(
                "The release declares an ambiguous outcome sensitivity dataset."
            )
        declaration = matching[0]
        content_hash = declaration.get("content_hash")
        byte_size = declaration.get("byte_size")
        if (
            not _is_sha256(content_hash)
            or declaration.get("format") != "json"
            or declaration.get("record_count") != 1
            or type(byte_size) is not int
            or not 0 < byte_size <= _MAX_OUTCOME_ARTIFACT_BYTES
        ):
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset declaration is invalid."
            )
        assert isinstance(content_hash, str)
        assert isinstance(byte_size, int)
        artifact_url = self._validated_outcome_url(
            declaration.get("url"), content_hash=content_hash
        )
        self._validated_outcome_url(declaration.get("schema_url"), schema=True)
        raw_artifact = self._fetch_outcome_artifact(artifact_url, byte_size)
        if hashlib.sha256(raw_artifact).hexdigest() != content_hash:
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset bytes do not match the release manifest."
            )
        try:
            candidate = json.loads(
                raw_artifact.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_json_keys,
                parse_constant=_reject_nonfinite_json,
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryUnavailableError(
                "The immutable outcome sensitivity dataset is not strict JSON."
            ) from exc
        if not isinstance(candidate, dict) or any(
            key in candidate
            for key in (
                "artifact",
                "release_id",
                "election_slug",
                "data_version",
                "margin_shift_factor",
            )
        ):
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset must contain one unwrapped core artifact."
            )
        try:
            core = OutcomeSensitivityArtifact.model_validate(candidate)
        except ValueError as exc:
            raise RepositoryUnavailableError(
                "The published outcome sensitivity dataset violates the frozen core contract."
            ) from exc
        filters = cast(Mapping[str, object], declaration["filters"])
        expected_filters = {
            "artifact_kind": "outcome_sensitivity",
            "election_slug": election_slug,
            "data_version": release_id,
            "core_output_hash": core.output_hash,
            "methodology_version": core.methodology_version,
            "evidence_hash": core.evidence_hash or "none",
        }
        if dict(filters) != expected_filters:
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset declaration does not bind the exact core artifact."
            )
        if core.evaluable:
            raise ResourceNotFoundError(
                "Typed outcome replay material is unavailable for this release/election."
            )
        try:
            return OutcomeSensitivity.model_validate(
                {
                    **candidate,
                    "release_id": release_id,
                    "election_slug": election_slug,
                    "data_version": release_id,
                    "margin_shift_factor": 2,
                }
            )
        except ValueError as exc:
            raise RepositoryUnavailableError(
                "The outcome sensitivity dataset cannot be bound to the requested release."
            ) from exc

    def iter_normalized_results(
        self, release_id: str, election_slug: str, filters: Mapping[str, object]
    ) -> Iterator[dict[str, object]]:
        """Stream a CSV export without materialising an immutable release."""
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            yield from self._context_results(scope_id, filters, None, None)
            return
        sql, values = self._result_statement(release_id, election_slug, filters, None, None)
        try:
            with self._sessions() as session, session.begin():
                session.execute(text("SET TRANSACTION READ ONLY"))
                result = session.execute(text(sql), values).mappings().yield_per(500)
                yield from (dict(row) for row in result)
        except Exception as exc:
            raise RepositoryUnavailableError(
                "The configured PostgreSQL read model is unavailable."
            ) from exc

    def normalized_geography_path(
        self, release_id: str, election_slug: str, geography_id: str
    ) -> list[dict[str, object]]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            rows = self._context_path_ids(scope_id, geography_id)
            if rows is None:
                raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
            return self._context_public_path(rows)
        rows = self._normalized(
            """WITH RECURSIVE path AS (SELECT id,level,code,name,parent_id,0 depth FROM release_geographies WHERE release_id=:r AND election_slug=:e AND id=:id
          UNION ALL SELECT g.id,g.level,g.code,g.name,g.parent_id,path.depth+1 FROM release_geographies g JOIN path ON path.parent_id=g.id WHERE g.release_id=:r AND g.election_slug=:e)
          SELECT id,level,code,name,parent_id FROM path ORDER BY depth DESC""",
            {"r": release_id, "e": election_slug, "id": geography_id},
        )
        if not rows:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        return rows

    def normalized_geography_children(
        self,
        release_id: str,
        election_slug: str,
        geography_id: str,
        child_level: str | None,
        after: tuple[str, ...] | None,
        limit: int,
    ) -> list[dict[str, object]]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            parent_rows = self._context_path_ids(scope_id, geography_id)
            if parent_rows is None:
                raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
            parent = parent_rows[-1]
            clauses = ["g.scope_id=:scope", "g.parent_id=:parent"]
            compact_values: dict[str, object] = {"scope": scope_id, "parent": parent["id"], "n": limit + 1}
            if child_level is not None:
                if child_level not in _CONTEXT_LEVELS:
                    return []
                clauses.append("g.level=:level")
                compact_values["level"] = _CONTEXT_LEVELS.index(child_level)
            if after is not None:
                clauses.append("(g.level,g.code,g.external_id) > (:after_level,:after_code,:after_id)")
                try:
                    cursor_level = _CONTEXT_LEVELS.index(after[0])
                except ValueError as exc:
                    raise ResourceNotFoundError("The geography cursor has an unknown level.") from exc
                compact_values.update({"after_level": cursor_level, "after_code": after[1], "after_id": after[2]})
            children = self._normalized(
                """SELECT g.external_id AS id,CASE g.level WHEN 0 THEN 'national' WHEN 1 THEN 'department' WHEN 2 THEN 'municipality' WHEN 3 THEN 'zone' WHEN 4 THEN 'polling_place' ELSE 'mesa' END AS level,g.code,g.name,
                p.external_id AS parent_id,NULL::text AS canonical_path,
                EXISTS (SELECT 1 FROM context_result_facts f WHERE f.scope_id=g.scope_id AND f.geography_id=g.id) AS has_published_facts
                FROM context_geographies g JOIN context_geographies p ON (p.scope_id=g.scope_id AND p.id=g.parent_id)
                WHERE """ + " AND ".join(clauses) + " ORDER BY g.level,g.code,g.external_id LIMIT :n", compact_values
            )
            parent_path = "/".join(str(row["external_id"]) for row in parent_rows)
            for child in children:
                child["canonical_path"] = f"{parent_path}/{child['id']}"
            return children
        parent_rows_legacy = self._normalized(
            "SELECT 1 FROM release_geographies WHERE release_id=:r AND election_slug=:e AND id=:id",
            {"r": release_id, "e": election_slug, "id": geography_id},
        )
        if not parent_rows_legacy:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        clauses = ["g.release_id=:r", "g.election_slug=:e", "g.parent_id=:id"]
        values: dict[str, object] = {
            "r": release_id,
            "e": election_slug,
            "id": geography_id,
            "n": limit + 1,
        }
        if child_level is not None:
            clauses.append("g.level=:level")
            values["level"] = child_level
        if after is not None:
            clauses.append("(g.level,g.code,g.id) > (:after_level,:after_code,:after_id)")
            values.update(dict(zip(("after_level", "after_code", "after_id"), after, strict=True)))
        return self._normalized(
            """SELECT g.id,g.level,g.code,g.name,g.parent_id,g.canonical_path,
            EXISTS (SELECT 1 FROM release_result_facts f WHERE f.release_id=g.release_id
              AND f.election_slug=g.election_slug AND f.geography_id=g.id) AS has_published_facts
            FROM release_geographies g WHERE """
            + " AND ".join(clauses)
            + " ORDER BY g.level,g.code,g.id LIMIT :n",
            values,
        )

    def normalized_mesa(
        self,
        release_id: str,
        election_slug: str,
        mesa_id: str,
        source_id: str | None,
        source_type: str | None,
    ) -> dict[str, object]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            path = self._context_path_ids(scope_id, mesa_id)
            if path is None or int(cast(Any, path[-1]["level"])) != 5:
                raise ResourceNotFoundError(f"Mesa '{mesa_id}' was not found.")
            by_level = {int(cast(Any, row["level"])): row for row in path}
            required = (1, 2, 4, 5)
            if any(level not in by_level for level in required):
                raise RepositoryUnavailableError("The mesa context hierarchy is incomplete.")
            mesa = by_level[5]
            facts = self.normalized_results(release_id, election_slug, {"geography_id": mesa_id, "source_id": source_id, "source_type": source_type}, None, 200)
            return {
                "id": mesa_id, "display_number": mesa["code"],
                "polling_place_id": by_level[4]["external_id"], "municipality_id": by_level[2]["external_id"], "department_id": by_level[1]["external_id"],
                "geography_path": self._context_public_path(path), "results": facts,
            }
        rows = self._normalized(
            """SELECT id,display_number,polling_place_id,municipality_id,department_id
            FROM release_mesas WHERE release_id=:r AND election_slug=:e AND id=:id""",
            {"r": release_id, "e": election_slug, "id": mesa_id},
        )
        if not rows:
            raise ResourceNotFoundError(f"Mesa '{mesa_id}' was not found.")
        filters: dict[str, object] = {
            "geography_id": mesa_id,
            "source_id": source_id,
            "source_type": source_type,
        }
        facts = self.normalized_results(release_id, election_slug, filters, None, 200)
        if len(facts) > 200:
            raise RepositoryUnavailableError("A mesa has too many public source layers.")
        return {
            **rows[0],
            "geography_path": self.normalized_geography_path(release_id, election_slug, mesa_id),
            "results": facts,
        }

    def normalized_categories(
        self, release_id: str, election_slug: str, fact_id: str, after: str | None, limit: int
    ) -> list[dict[str, object]]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is not None:
            matches = self._normalized(
                """SELECT g.external_id,s.source_id FROM context_result_facts f
                JOIN context_geographies g ON (g.scope_id=f.scope_id AND g.id=f.geography_id)
                JOIN context_sources s ON (s.scope_id=f.scope_id AND s.ordinal=f.source_ordinal)
                WHERE f.scope_id=:scope AND (g.external_id || ':' || s.source_id)=:fact""",
                {"scope": scope_id, "fact": fact_id},
            )
            if len(matches) != 1:
                raise ResourceNotFoundError(f"Result fact '{fact_id}' was not found.")
            source_id = str(matches[0]["source_id"])
            geography_id = str(matches[0]["external_id"])
            return self._normalized(
                """SELECT c.category_key,c.category_code,c.category_name,c.category_kind,cf.votes,
                CASE cf.status WHEN 0 THEN 'observed' WHEN 1 THEN 'unknown' WHEN 2 THEN 'unavailable' ELSE 'not_applicable' END AS status,
                rs.source_type,rs.legal_status,rs.source_url,rs.retrieved_at,rs.content_hash,rs.parser_version,rs.transform_version
                FROM context_category_facts cf JOIN context_geographies g ON (g.scope_id=cf.scope_id AND g.id=cf.geography_id)
                JOIN context_sources s ON (s.scope_id=cf.scope_id AND s.ordinal=cf.source_ordinal)
                JOIN context_categories c ON (c.scope_id=cf.scope_id AND c.id=cf.category_id)
                JOIN context_release_scopes cs ON cs.id=cf.scope_id JOIN release_sources rs ON (rs.release_id=cs.release_id AND rs.election_slug=cs.election_slug AND rs.id=s.source_id)
                WHERE cf.scope_id=:scope AND g.external_id=:geo AND s.source_id=:source
                AND (CAST(:after AS text) IS NULL OR c.category_key>CAST(:after AS text)) ORDER BY c.category_key LIMIT :n""",
                {"scope": scope_id, "geo": geography_id, "source": source_id, "after": after, "n": limit + 1},
            )
        return self._normalized(
            """SELECT cf.category_key,cf.category_code,cf.category_name,cf.category_kind,cf.votes,cf.status,
            s.source_type,s.legal_status,s.source_url,s.retrieved_at,s.content_hash,s.parser_version,s.transform_version
            FROM release_category_facts cf
            JOIN release_result_facts f ON f.release_id=cf.release_id AND f.election_slug=cf.election_slug AND f.id=cf.result_fact_id
            JOIN release_sources s ON s.release_id=f.release_id AND s.election_slug=f.election_slug AND s.id=f.source_id
            WHERE cf.release_id=:r AND cf.election_slug=:e AND cf.result_fact_id=:fact_id
            AND (CAST(:a AS text) IS NULL OR cf.category_key>CAST(:a AS text))
            ORDER BY cf.category_key LIMIT :n""",
            {"r": release_id, "e": election_slug, "fact_id": fact_id, "a": after, "n": limit + 1},
        )

    def normalized_summary(self, release_id: str, election_slug: str) -> dict[str, object]:
        grant = self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is None:
            return self._standard_summary(release_id, election_slug, grant)
        election = self._normalized(
            """SELECT e.name_es,e.name_en,e.round,e.election_date,r.status FROM release_elections e
            JOIN releases r ON r.id=e.release_id WHERE e.release_id=:r AND e.election_slug=:e""",
            {"r": release_id, "e": election_slug},
        )[0]
        facts = self._context_results(scope_id, {"geography_level": "national"}, None, 2)
        if len(facts) != 1:
            raise RepositoryUnavailableError("The context release lacks exactly one national fact.")
        fact = facts[0]
        counts = self._normalized(
            """SELECT (SELECT count(*) FROM context_geographies WHERE scope_id=:scope) AS geographies,
            (SELECT count(*) FROM context_result_facts WHERE scope_id=:scope) AS facts,
            (SELECT count(*) FROM context_category_facts WHERE scope_id=:scope) AS category_facts""",
            {"scope": scope_id},
        )[0]
        national_categories = self.normalized_categories(
            release_id, election_slug, str(fact["id"]), None, 500
        )
        return {
            "election_slug": election_slug, "election_name": {"es": election["name_es"], "en": election["name_en"]},
            "round": election["round"], "election_date": election["election_date"], "data_version": release_id,
            "release_status": election["status"], "release_class": "context_only", "synthetic": False,
            "completion": {"status": "unknown", "reason": "The historical context artifact does not declare an expected reporting universe."},
            **cast(dict[str, object], fact["metrics"]), "national_categories": national_categories,
            "coverage": {"status": "unknown", "observed_geographies": counts["geographies"], "observed_result_facts": counts["facts"], "observed_category_facts": counts["category_facts"], "reason": "Observed rows are not an expected coverage denominator."},
            "reconciliation": {"status": "not_run", "checked_facts": 0, "exceptions": 0},
            "provenance": {"data_version": release_id, **{key: fact[key] for key in ("source_type", "legal_status", "source_url", "retrieved_at", "content_hash", "parser_version", "transform_version")}, "methodology_version": None},
        }

    def normalized_children_results(
        self,
        release_id: str,
        election_slug: str,
        geography_id: str,
        level: str | None,
        after: tuple[str, ...] | None,
        limit: int,
    ) -> dict[str, object]:
        """Children with their vote totals in ONE round trip.

        The existing ``/results`` shape emits an empty ``candidates`` array and
        a full provenance block per row, so candidate votes are only reachable
        through ``/result-facts/{id}/categories`` — up to 228 extra requests for
        a single polling place. That N+1, not payload size, is what makes a
        drill-down UI impossible on the existing routes.

        The lean row is ~77 bytes against ~1,166: ``{status,value}`` is
        unwrapped (a bare int is observed, ``null`` is not observed), provenance
        is hoisted to one page-level block, and candidate votes are positional
        against a page-level candidate list rather than repeating the candidate
        id on every row.

        ``registered_electors`` is omitted entirely rather than emitted as a
        null on every row: it is unavailable everywhere below national in this
        release, and an omitted field states that once instead of 122,020 times.
        """
        grant = self._authorized_any(release_id, election_slug)
        keyset = ""
        values: dict[str, object] = {
            "r": release_id,
            "e": election_slug,
            "g": geography_id,
            "n": limit + 1,
        }
        if level is not None:
            keyset += " AND g.level=:level"
            values["level"] = level
        if after is not None:
            keyset += " AND (g.level,g.code,g.id) > (:a0,:a1,:a2)"
            values.update({"a0": after[0], "a1": after[1], "a2": after[2]})

        # Categories are aggregated in a LATERAL rather than a GROUP BY: the
        # `metrics` column is `json`, which Postgres cannot group by (no
        # equality operator for the type), and a per-row lateral also avoids
        # grouping the whole join.
        rows = self._normalized(
            f"""SELECT g.id, g.level, g.code, g.name,
            f.id AS fact_id,
            f.metrics->'voters'->>'value' AS voters,
            f.metrics->'valid_votes'->>'value' AS valid_votes,
            f.metrics->'blank_votes'->>'value' AS blank_votes,
            f.metrics->'null_votes'->>'value' AS null_votes,
            f.metrics->'unmarked_votes'->>'value' AS unmarked_votes,
            COALESCE(cats.categories, '[]'::json) AS categories
            FROM release_geographies g
            LEFT JOIN release_result_facts f
              ON (f.release_id=g.release_id AND f.election_slug=g.election_slug
                  AND f.geography_id=g.id)
            LEFT JOIN LATERAL (
                SELECT json_agg(json_build_object('k', c.category_key, 'v', c.votes)
                                ORDER BY c.category_key) AS categories
                FROM release_category_facts c
                WHERE c.release_id=f.release_id AND c.election_slug=f.election_slug
                  AND c.result_fact_id=f.id
            ) cats ON true
            WHERE g.release_id=:r AND g.election_slug=:e AND g.parent_id=:g{keyset}
            ORDER BY g.level, g.code, g.id LIMIT :n""",
            values,
        )
        has_more = len(rows) > limit
        page = rows[:limit]

        candidates = self._normalized(
            """SELECT DISTINCT c.category_key FROM release_category_facts c
            WHERE c.release_id=:r AND c.election_slug=:e AND c.category_kind <> 'ballot_state'
            ORDER BY c.category_key""",
            {"r": release_id, "e": election_slug},
        )
        order = [str(row["category_key"]) for row in candidates]
        index = {key: position for position, key in enumerate(order)}

        def lean(row: Mapping[str, object]) -> dict[str, object]:
            votes: list[int | None] = [None] * len(order)
            for entry in cast(list[Any], row["categories"]):
                position = index.get(str(entry["k"]))
                if position is not None:
                    votes[position] = entry["v"]
            number = lambda key: (  # noqa: E731 - local projection helper
                None if row[key] is None else int(cast(Any, row[key]))
            )
            return {
                "i": row["id"],
                "l": row["level"],
                "c": row["code"],
                "n": row["name"],
                "t": number("voters"),
                "v": number("valid_votes"),
                "b": number("blank_votes"),
                "x": number("null_votes"),
                "u": number("unmarked_votes"),
                "k": votes,
            }

        return {
            "items": [lean(row) for row in page],
            "candidates": order,
            "has_more": has_more,
            "last": (
                None
                if not page
                else (str(page[-1]["level"]), str(page[-1]["code"]), str(page[-1]["id"]))
            ),
            "data_version": release_id,
            "exposure_class": grant.get("class"),
            "preliminary": grant.get("class") == "preliminary",
            "preliminary_caveat": grant.get("caveat"),
        }

    def _standard_summary(
        self, release_id: str, election_slug: str, grant: dict[str, object]
    ) -> dict[str, object]:
        """National summary for a standard release.

        Completion, coverage and reconciliation are read from
        ``release_summaries`` exactly as the pipeline recorded them, never
        recomputed from the loaded rows. That matters here specifically:
        reconciliation is ``blocked`` with three exceptions, and completion
        reports 122,017 of 122,020 installed mesas. Deriving either from the
        rows present would quietly report a passing reconciliation and a
        complete count.
        """
        election = self._normalized(
            """SELECT e.name_es,e.name_en,e.round,e.election_date,r.status,r.synthetic
            FROM release_elections e JOIN releases r ON r.id=e.release_id
            WHERE e.release_id=:r AND e.election_slug=:e""",
            {"r": release_id, "e": election_slug},
        )
        if not election:
            raise ResourceNotFoundError("The requested release/election was not found.")
        election_row = election[0]

        stored = self._normalized(
            """SELECT release_class, completion, coverage, geographic_collection_coverage,
            reconciliation, turnout, preview_caveat_es, preview_caveat_en
            FROM release_summaries WHERE release_id=:r AND election_slug=:e""",
            {"r": release_id, "e": election_slug},
        )
        if not stored:
            raise RepositoryUnavailableError(
                "The release has no recorded summary; it cannot be reconstructed from rows."
            )
        summary_row = stored[0]

        national = self._normalized(
            """SELECT f.id, f.metrics, f.source_id, s.source_type, s.legal_status,
            s.source_url, s.retrieved_at, s.content_hash, s.parser_version, s.transform_version
            FROM release_result_facts f
            JOIN release_sources s ON (s.release_id=f.release_id
                AND s.election_slug=f.election_slug AND s.id=f.source_id)
            WHERE f.release_id=:r AND f.election_slug=:e AND f.geography_level='national'""",
            {"r": release_id, "e": election_slug},
        )
        if len(national) != 1:
            raise RepositoryUnavailableError(
                "A standard release must carry exactly one national fact."
            )
        fact = national[0]
        categories = self.normalized_categories(
            release_id, election_slug, str(fact["id"]), None, 500
        )

        # The reader-facing summary needs candidates, not just raw categories:
        # every consumer of ElectionSummary expects {candidate, votes, share}.
        # Share is over valid_votes, which INCLUDES blank ballots, so the two
        # shares deliberately do not sum to 1.
        metrics = cast(dict[str, Any], fact["metrics"])
        valid = cast(Any, metrics.get("valid_votes") or {}).get("value")
        candidates: list[dict[str, object]] = []
        for entry in categories:
            row = cast(dict[str, Any], entry)
            key = str(row.get("category_key", ""))
            if not key.startswith("candidate:"):
                continue
            votes = row.get("votes")
            value = (
                votes.get("value")
                if isinstance(votes, Mapping)
                else votes
                if isinstance(votes, int)
                else None
            )
            candidates.append(
                {
                    "candidate": {
                        "id": str(row.get("category_code") or key),
                        "ballot_number": None,
                        "name": {
                            "es": row.get("category_name"),
                            "en": row.get("category_name"),
                        },
                        "short_name": {
                            "es": row.get("category_name"),
                            "en": row.get("category_name"),
                        },
                    },
                    "votes": {
                        "value": value,
                        "status": "observed" if value is not None else "unavailable",
                    },
                    "share": (
                        (value / valid) if value is not None and valid else None
                    ),
                }
            )

        caveat = cast(Any, grant.get("caveat")) or {
            "es": summary_row["preview_caveat_es"],
            "en": summary_row["preview_caveat_en"],
        }
        return {
            "election_slug": election_slug,
            "election_name": {"es": election_row["name_es"], "en": election_row["name_en"]},
            "round": election_row["round"],
            "election_date": election_row["election_date"],
            "data_version": release_id,
            "release_status": election_row["status"],
            "release_class": summary_row["release_class"],
            "synthetic": bool(election_row["synthetic"]),
            "exposure_class": grant.get("class"),
            "preliminary": grant.get("class") == "preliminary",
            "preliminary_caveat": caveat,
            "completion": summary_row["completion"],
            "coverage": summary_row["coverage"],
            "geographic_collection_coverage": summary_row["geographic_collection_coverage"],
            "reconciliation": summary_row["reconciliation"],
            "turnout": summary_row["turnout"],
            **cast(dict[str, object], fact["metrics"]),
            "candidates": candidates,
            "national_categories": categories,
            "provenance": {
                "data_version": release_id,
                **{
                    key: fact[key]
                    for key in (
                        "source_type",
                        "legal_status",
                        "source_url",
                        "retrieved_at",
                        "content_hash",
                        "parser_version",
                        "transform_version",
                    )
                },
                "methodology_version": None,
            },
        }

    def normalized_geography(self, release_id: str, election_slug: str, geography_id: str) -> dict[str, object]:
        self._authorized_any(release_id, election_slug)
        scope_id = self._context_scope(release_id, election_slug)
        if scope_id is None:
            # A standard release stores geographies in release_geographies
            # directly; only the compact context model needs the scope indirection.
            rows = self._normalized(
                """SELECT id, level, code, name, parent_id, canonical_path
                FROM release_geographies
                WHERE release_id=:r AND election_slug=:e AND id=:g""",
                {"r": release_id, "e": election_slug, "g": geography_id},
            )
            if not rows:
                raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
            row = rows[0]
            return {
                "id": row["id"],
                "level": row["level"],
                "code": row["code"],
                "name": row["name"],
                "parent_id": row["parent_id"],
                "canonical_path": row["canonical_path"],
                # Null on every geography in this release, including the
                # synthesised mesa rows. Absent, not zero.
                "authoritative_coordinates": None,
            }
        path = self._context_path_ids(scope_id, geography_id)
        if path is None:
            raise ResourceNotFoundError(f"Geography '{geography_id}' was not found.")
        row = path[-1]
        parent_id = None if row["parent_id"] is None else path[-2]["external_id"]
        return {"id": row["external_id"], "level": _CONTEXT_LEVELS[int(cast(Any, row["level"]))], "code": row["code"], "name": row["name"], "parent_id": parent_id, "canonical_path": "/".join(str(item["external_id"]) for item in path), "authoritative_coordinates": None}

    def normalized_comparison(
        self,
        release_id: str,
        election_slug: str,
        baseline_release_id: str,
        baseline_election_slug: str,
        geography_id: str,
        grain: str,
        category_key: str | None = None,
    ) -> dict[str, object]:
        self._authorized(release_id, election_slug)
        self._authorized(baseline_release_id, baseline_election_slug)
        current_scope = self._context_scope(release_id, election_slug)
        baseline_scope = self._context_scope(baseline_release_id, baseline_election_slug)
        if current_scope is not None or baseline_scope is not None:
            # The compact historical model deliberately has no approved stable
            # crosswalk. Matching identifiers alone is insufficient evidence of
            # comparability, even when their strings happen to be equal.
            return {"comparison_status": "descriptive_context_only", "reason": "missing_approved_context_crosswalk", "eligible_for_integrity_analysis": False, "items": []}
        rows = self._normalized(
            """SELECT c.comparison_key,c.version,c.baseline_geography_id,c.approved_at FROM comparison_crosswalks c
          WHERE c.current_release_id=:r AND c.current_election_slug=:e AND c.baseline_release_id=:br AND c.baseline_election_slug=:be AND c.current_geography_id=:g AND c.grain=:grain""",
            {
                "r": release_id,
                "e": election_slug,
                "br": baseline_release_id,
                "be": baseline_election_slug,
                "g": geography_id,
                "grain": grain,
            },
        )
        if not rows:
            return {"comparison_status": "not_comparable", "reason": "missing_geography_crosswalk"}
        geography = rows[0]
        if geography["approved_at"] is None:
            return {
                "comparison_status": "not_comparable",
                "reason": "geography_crosswalk_unapproved",
            }
        semantic_filters = ""
        values: dict[str, object] = {
            "r": release_id,
            "e": election_slug,
            "br": baseline_release_id,
            "be": baseline_election_slug,
            "g": geography_id,
            "bg": geography["baseline_geography_id"],
            "grain": grain,
            "comparison_key": geography["comparison_key"],
        }
        if category_key is not None:
            semantic_filters = " AND sc.current_category_key=:category_key"
            values["category_key"] = category_key
        semantic = self._normalized(
            """SELECT sc.current_category_key,sc.current_source_id,sc.baseline_category_key,sc.baseline_source_id,sc.category_kind,sc.version,sc.approved_at
            FROM semantic_category_crosswalks sc WHERE sc.current_release_id=:r AND sc.current_election_slug=:e
            AND sc.baseline_release_id=:br AND sc.baseline_election_slug=:be AND sc.comparison_key=:comparison_key"""
            + semantic_filters,
            values,
        )
        if not semantic:
            return {"comparison_status": "not_comparable", "reason": "missing_semantic_crosswalk"}
        if any(
            row["approved_at"] is None
            or row["current_source_id"] is None
            or row["baseline_source_id"] is None
            for row in semantic
        ):
            return {
                "comparison_status": "not_comparable",
                "reason": "semantic_crosswalk_unapproved",
            }
        # Pair only the two explicitly mapped category keys.  There is no name
        # join, fallback aggregation, or estimate. Context-only baseline facts
        # remain available as descriptive history, never integrity inputs.
        facts = self._normalized(
            """SELECT sc.current_category_key,sc.baseline_category_key,sc.category_kind,sc.version AS semantic_crosswalk_version,
              cf.votes AS current_value,cf.status AS current_status,cf.result_fact_id AS current_fact_id,
              cs.source_type AS current_source_type,cs.legal_status AS current_legal_status,cs.source_url AS current_source_url,cs.retrieved_at AS current_retrieved_at,cs.content_hash AS current_content_hash,cs.parser_version AS current_parser_version,cs.transform_version AS current_transform_version,
              bf.votes AS baseline_value,bf.status AS baseline_status,bf.result_fact_id AS baseline_fact_id,
              bs.source_type AS baseline_source_type,bs.legal_status AS baseline_legal_status,bs.source_url AS baseline_source_url,bs.retrieved_at AS baseline_retrieved_at,bs.content_hash AS baseline_content_hash,bs.parser_version AS baseline_parser_version,bs.transform_version AS baseline_transform_version
            FROM semantic_category_crosswalks sc
            JOIN release_category_facts cf ON cf.release_id=sc.current_release_id AND cf.election_slug=sc.current_election_slug AND cf.category_key=sc.current_category_key
            JOIN release_result_facts cfr ON cfr.release_id=cf.release_id AND cfr.election_slug=cf.election_slug AND cfr.id=cf.result_fact_id AND cfr.source_id=sc.current_source_id AND cfr.geography_id=:g AND cfr.geography_level=:grain
            JOIN release_sources cs ON cs.release_id=cfr.release_id AND cs.election_slug=cfr.election_slug AND cs.id=cfr.source_id
            JOIN release_category_facts bf ON bf.release_id=sc.baseline_release_id AND bf.election_slug=sc.baseline_election_slug AND bf.category_key=sc.baseline_category_key
            JOIN release_result_facts bfr ON bfr.release_id=bf.release_id AND bfr.election_slug=bf.election_slug AND bfr.id=bf.result_fact_id AND bfr.source_id=sc.baseline_source_id AND bfr.geography_id=:bg AND bfr.geography_level=:grain
            JOIN release_sources bs ON bs.release_id=bfr.release_id AND bs.election_slug=bfr.election_slug AND bs.id=bfr.source_id
            WHERE sc.current_release_id=:r AND sc.current_election_slug=:e AND sc.baseline_release_id=:br AND sc.baseline_election_slug=:be
            AND sc.comparison_key=:comparison_key AND sc.approved_at IS NOT NULL"""
            + semantic_filters
            + " ORDER BY sc.current_category_key,cfr.id,bfr.id",
            values,
        )
        if not facts:
            return {"comparison_status": "not_comparable", "reason": "no_compatible_facts"}
        descriptive_only = any(
            row["current_source_type"] == "contextual_baseline"
            or row["baseline_source_type"] == "contextual_baseline"
            for row in facts
        )
        return {
            "comparison_status": ("descriptive_context_only" if descriptive_only else "comparable"),
            "eligible_for_integrity_analysis": not descriptive_only,
            "comparison_key": geography["comparison_key"],
            "geography_crosswalk_version": geography["version"],
            "geography_approved_at": geography["approved_at"],
            "baseline_geography_id": geography["baseline_geography_id"],
            "items": facts,
        }
