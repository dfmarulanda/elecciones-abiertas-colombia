"""Pydantic representations of the frozen public OpenAPI contract."""

import hashlib
import json
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

SourceType = Literal[
    "final_declaration",
    "scrutiny",
    "e14_delegate",
    "e14_transmission",
    "pre_count",
    "contextual_baseline",
]
LegalStatus = Literal[
    "controlling_final", "official_scrutiny", "documentary_evidence", "preliminary", "context_only"
]
MetricStatus = Literal["observed", "unknown", "unavailable", "not_applicable"]
GeographyLevel = Literal["national", "department", "municipality", "zone", "polling_place", "mesa"]
SignalTier = Literal[
    "documentary_review_prioritized",
    "documentary_comparison_recommended",
    "statistical_or_coverage_issue",
    "no_review_signals",
]
AnomalyType = Literal[
    "structural_arithmetic",
    "identity_coverage",
    "cross_source_documentary",
    "peer_distribution",
    "spatial",
]
ExplanationStatus = Literal[
    "explained",
    "partially_explained",
    "no_explanation_found_in_available_data",
    "non_evaluable",
]
_SHA256_PATTERN = r"^[a-f0-9]{64}$"
_STATISTICAL_COMPONENTS = {"peer_distribution", "spatial_cluster"}
_SIGNAL_COMPONENT_POINTS = {
    "verified_accounting_failure": 100,
    "conflicting_official_records": 100,
    "documentary_difference_major": 70,
    "documentary_difference_minor": 45,
    "document_missing_duplicated_ambiguous": 25,
    "peer_distribution": 10,
    "spatial_cluster": 10,
}
ANALYTICAL_DISCLOSURE_ES = (
    "Una anomalía prioriza revisión y no es una probabilidad ni un hallazgo de fraude. "
    "Una explicación posterior no elimina la anomalía detectada; la ausencia de explicación "
    "en los datos disponibles tampoco prueba fraude ni error."
)
ANALYTICAL_DISCLOSURE_EN = (
    "An anomaly prioritizes review and is not a probability or finding of fraud. "
    "A later explanation does not erase the detected anomaly; absence of an explanation in "
    "available data does not prove fraud or error."
)


def review_signal_tier(score: int) -> SignalTier:
    if score >= 70:
        return "documentary_review_prioritized"
    if score >= 45:
        return "documentary_comparison_recommended"
    if score >= 15:
        return "statistical_or_coverage_issue"
    return "no_review_signals"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LocalizedText(StrictModel):
    es: str
    en: str


class MetricValue(StrictModel):
    value: int | None = Field(ge=0)
    status: MetricStatus

    @model_validator(mode="after")
    def observed_values_are_explicit(self) -> "MetricValue":
        if self.status == "observed" and self.value is None:
            raise ValueError("Observed metrics require a numeric value")
        if self.status != "observed" and self.value is not None:
            raise ValueError("Non-observed metrics must use null")
        return self


class Provenance(StrictModel):
    data_version: str
    source_type: SourceType
    legal_status: LegalStatus
    source_url: HttpUrl
    retrieved_at: datetime
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    parser_version: str
    transform_version: str
    methodology_version: str | None


class PreviewProvenance(Provenance):
    """Provenance for a candidate release that must advertise its limitations."""

    preview_caveat: str | None = None


class Candidate(StrictModel):
    id: str
    ballot_number: int | None = Field(default=None, ge=1)
    name: LocalizedText
    short_name: LocalizedText


class CandidateResult(StrictModel):
    candidate_id: str
    votes: MetricValue


class CandidateSummary(StrictModel):
    candidate: Candidate
    votes: MetricValue
    share: float | None = Field(ge=0, le=1)


class ResultFact(StrictModel):
    id: str
    election_slug: str
    geography_id: str
    geography_level: GeographyLevel
    mesa_id: str | None
    registered_electors: MetricValue
    voters: MetricValue
    valid_votes: MetricValue
    blank_votes: MetricValue
    null_votes: MetricValue
    unmarked_votes: MetricValue
    candidates: list[CandidateResult]
    provenance: Provenance


class CursorMeta(StrictModel):
    next_cursor: str | None
    has_more: bool
    limit: int


class ResultPage(StrictModel):
    items: list[ResultFact]
    page: CursorMeta
    data_version: str


class ReleaseSourceRef(StrictModel):
    """Source metadata exposed by the release index.

    PostgreSQL-published releases currently expose the core five fields, while
    packaged historical candidates expose the complete source-manifest entry.
    Optional fields preserve that distinction instead of fabricating metadata.
    """

    id: str
    source_type: SourceType
    legal_status: LegalStatus
    source_url: HttpUrl
    content_hash: str = Field(pattern=_SHA256_PATTERN)
    retrieved_at: datetime | None = None
    media_type: str | None = None
    byte_size: int | None = Field(default=None, ge=0)
    parser_version: str | None = None
    transform_version: str | None = None
    published_grain: (
        Literal["mesa", "place", "municipality", "department", "national"] | None
    ) = None
    coverage: "Coverage | None" = None


class ReleaseElectionRef(StrictModel):
    release_id: str
    election_slug: str
    name_es: str
    name_en: str
    round: int = Field(gt=0)
    election_date: date
    status: Literal["fixture", "candidate", "published", "withdrawn"]
    release_class: Literal["context_only"] | None = None
    methodology_version: str | None
    release_manifest_hash: str = Field(pattern=_SHA256_PATTERN)
    exposure_approved_at: datetime | None
    sources: list[ReleaseSourceRef]

    @model_validator(mode="after")
    def candidate_context_is_not_approved(self) -> "ReleaseElectionRef":
        if self.status == "candidate" and self.exposure_approved_at is not None:
            raise ValueError("Candidate releases cannot claim approved public exposure")
        if self.release_class == "context_only" and any(
            source.legal_status != "context_only" for source in self.sources
        ):
            raise ValueError("Context-only release sources must remain context-only")
        return self


class NormalizedCategoryResult(StrictModel):
    """A source-published MMV category; it is not necessarily a candidate."""

    category_key: str
    category_code: str
    category_name: str
    category_kind: str
    votes: int | None = Field(ge=0)
    status: MetricStatus
    provenance: Provenance

    @model_validator(mode="after")
    def observed_votes_are_explicit(self) -> "NormalizedCategoryResult":
        if (self.status == "observed") != (self.votes is not None):
            raise ValueError(
                "Observed category votes require an integer; other states require null"
            )
        return self


class NormalizedCategoryPage(StrictModel):
    items: list[NormalizedCategoryResult]
    page: CursorMeta
    data_version: str
    sparse_category_semantics: str


class ScopedGeography(StrictModel):
    id: str
    level: GeographyLevel
    code: str
    name: str
    parent_id: str | None
    canonical_path: str | None = None
    has_published_facts: bool | None = None
    authoritative_coordinates: "Coordinates | None" = None


class ScopedGeographyResponse(StrictModel):
    item: ScopedGeography
    data_version: str


class ScopedGeographyPathResponse(StrictModel):
    items: list[ScopedGeography]
    data_version: str


class GeographyChildPage(StrictModel):
    items: list[ScopedGeography]
    page: CursorMeta
    data_version: str


class ScopedMesa(StrictModel):
    id: str
    display_number: str
    polling_place_id: str
    municipality_id: str
    department_id: str
    geography_path: list[ScopedGeography]
    results: list[ResultFact] = Field(max_length=200)
    data_version: str


class UnknownCompletion(StrictModel):
    status: Literal["unknown"]
    reason: str


class UnknownContextCoverage(StrictModel):
    status: Literal["unknown"]
    observed_geographies: int = Field(ge=0)
    observed_result_facts: int = Field(ge=0)
    observed_category_facts: int = Field(ge=0)
    reason: str | None = None


class PreliminaryElectionSummary(StrictModel):
    """A real, standard release served through the preliminary exposure.

    A deliberate sibling of ``ContextElectionSummary`` rather than a widening of
    it. Widening that model's literals would let a context-only historical
    release claim standard status, which is the same class of mislabel the
    preliminary scope exists to prevent — so each model pins the one class it
    describes and neither can impersonate the other.

    ``completion``, ``coverage`` and ``reconciliation`` are the pipeline's own
    recorded values. For this release that means completion reports 122,017 of
    122,020 and reconciliation is ``blocked`` with three exceptions; both are
    served as recorded, because deriving them from the loaded rows would report
    a complete count that reconciles.
    """

    election_slug: str
    election_name: LocalizedText
    round: int = Field(gt=0)
    election_date: date
    data_version: str
    release_status: Literal["candidate"]
    release_class: Literal["standard"]
    synthetic: Literal[False]
    #: Which door authorised this read. Required, so a preliminary payload
    #: cannot be serialised without saying that it is one.
    exposure_class: Literal["preliminary"]
    preliminary: Literal[True]
    preliminary_caveat: LocalizedText
    completion: "Completion"
    coverage: "Coverage"
    geographic_collection_coverage: dict[str, object] | None = None
    turnout: float | None = None
    registered_electors: MetricValue
    voters: MetricValue
    valid_votes: MetricValue
    blank_votes: MetricValue
    null_votes: MetricValue
    unmarked_votes: MetricValue
    #: Shares are over valid_votes, which includes blank ballots, so the
    #: candidate shares deliberately do not sum to 1.
    candidates: list["CandidateSummary"]
    national_categories: list[NormalizedCategoryResult]
    reconciliation: "Reconciliation"
    provenance: PreviewProvenance

    @model_validator(mode="after")
    def preliminary_states_its_own_limits(self) -> "PreliminaryElectionSummary":
        if not (self.preliminary_caveat.es and self.preliminary_caveat.en):
            raise ValueError("A preliminary summary requires a caveat in both languages")
        if self.provenance.data_version != self.data_version:
            raise ValueError("Summary provenance must match the requested data version")
        if self.provenance.legal_status != "preliminary":
            raise ValueError(
                "A preliminary summary cannot claim a controlling legal status"
            )
        return self


class ContextElectionSummary(StrictModel):
    """Truthful historical summary with no invented completion denominator."""

    election_slug: str
    election_name: LocalizedText
    round: int = Field(gt=0)
    election_date: date
    data_version: str
    release_status: Literal["candidate", "published", "withdrawn"]
    release_class: Literal["context_only"]
    synthetic: Literal[False]
    completion: UnknownCompletion
    registered_electors: MetricValue
    voters: MetricValue
    valid_votes: MetricValue
    blank_votes: MetricValue
    null_votes: MetricValue
    unmarked_votes: MetricValue
    national_categories: list[NormalizedCategoryResult]
    coverage: UnknownContextCoverage
    reconciliation: "Reconciliation"
    provenance: PreviewProvenance

    @model_validator(mode="after")
    def candidate_context_keeps_its_caveat_and_scope(self) -> "ContextElectionSummary":
        if self.release_status == "candidate" and not self.provenance.preview_caveat:
            raise ValueError("Candidate context summaries require a non-empty preview caveat")
        if self.provenance.data_version != self.data_version:
            raise ValueError("Summary provenance must match the requested data version")
        if self.provenance.legal_status != "context_only":
            raise ValueError("Historical summaries cannot claim controlling legal status")
        if any(
            item.provenance.data_version != self.data_version
            or item.provenance.legal_status != "context_only"
            for item in self.national_categories
        ):
            raise ValueError("National categories must retain context-only release provenance")
        return self


class PackagedDataset(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    title: LocalizedText
    format: Literal["parquet"]
    url: str = Field(pattern=r"^/api/v1/")
    schema_url: HttpUrl | None
    record_count: int = Field(ge=0)
    byte_size: int = Field(ge=0)
    content_hash: str = Field(pattern=_SHA256_PATTERN)
    filters: dict[str, str]

    @model_validator(mode="after")
    def download_is_same_origin(self) -> "PackagedDataset":
        if "://" in self.url or not self.url.startswith("/api/v1/"):
            raise ValueError("Packaged dataset downloads must use relative same-origin URLs")
        return self


class Coverage(StrictModel):
    expected: int = Field(ge=0)
    retrieved: int = Field(ge=0)
    parsed: int = Field(ge=0)
    missing: int = Field(ge=0)
    ambiguous: int = Field(ge=0)
    excluded: int = Field(ge=0)


class GeographicCollectionCoverage(StrictModel):
    status: Literal["national_only", "sample_limited", "full_scope"]
    expected_polling_places: int = Field(ge=0)
    retrieved_polling_places: int = Field(ge=0)
    expected_mesas: int = Field(ge=0)
    retrieved_mesas: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_match_status(self) -> "GeographicCollectionCoverage":
        if (
            self.retrieved_polling_places > self.expected_polling_places
            or self.retrieved_mesas > self.expected_mesas
        ):
            raise ValueError("Geographic collection counts must be monotonic")
        return self


class Completion(StrictModel):
    expected: int
    reported: int
    percent: float = Field(ge=0, le=1)


class Reconciliation(StrictModel):
    status: Literal["passed", "blocked", "not_run"]
    checked_facts: int
    exceptions: int


class ElectionSummary(StrictModel):
    election_slug: str
    election_name: LocalizedText
    round: int
    election_date: date
    data_version: str
    release_status: Literal["fixture", "candidate", "published", "withdrawn"]
    synthetic: bool
    completion: Completion
    registered_electors: MetricValue
    voters: MetricValue
    turnout: float | None = Field(ge=0, le=1)
    valid_votes: MetricValue
    blank_votes: MetricValue
    null_votes: MetricValue
    unmarked_votes: MetricValue
    candidates: list[CandidateSummary]
    coverage: Coverage
    geographic_collection_coverage: GeographicCollectionCoverage | None = None
    reconciliation: Reconciliation
    provenance: Provenance


class Coordinates(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    quality: Literal["authoritative", "approximate"]
    source_url: HttpUrl


class Geography(StrictModel):
    id: str
    level: GeographyLevel
    code: str
    name: str
    parent_id: str | None
    authoritative_coordinates: Coordinates | None


class MesaDetail(StrictModel):
    id: str
    display_number: str
    geography: Geography
    polling_place: Geography
    available_source_types: list[SourceType]
    result: ResultFact
    data_version: str


class EvidenceDocument(StrictModel):
    id: str
    mesa_id: str
    document_type: Literal["e14_delegate", "e14_transmission"]
    official_url: HttpUrl
    source_index_url: HttpUrl
    source_index_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    indexed_at: datetime
    index_status: Literal["indexed", "unavailable", "ambiguous"]
    provenance: Provenance

    @model_validator(mode="after")
    def is_a_source_index_record(self) -> "EvidenceDocument":
        if str(self.provenance.source_url) != str(self.source_index_url):
            raise ValueError("E-14 provenance must identify its source index")
        if self.provenance.content_hash != self.source_index_hash:
            raise ValueError("E-14 provenance hash must equal its source-index hash")
        return self


class EvidenceResponse(StrictModel):
    mesa_id: str
    documents: list[EvidenceDocument]
    data_version: str


class ComparisonItem(StrictModel):
    field: str
    left_source_type: SourceType
    right_source_type: SourceType
    left_value: MetricValue
    right_value: MetricValue
    signed_difference: int | None
    affected_vote_estimate: int | None = Field(default=None, ge=0)
    compatible_grain: bool
    notes: LocalizedText


class ComparisonResponse(StrictModel):
    mesa_id: str
    items: list[ComparisonItem]
    data_version: str


class HistoricalComparisonItem(StrictModel):
    category_key: str
    baseline_category_key: str
    category_kind: str
    semantic_crosswalk_version: str
    current_fact_id: str
    current_value: int | None = Field(ge=0)
    current_status: MetricStatus
    current_provenance: Provenance
    baseline_fact_id: str
    baseline_value: int | None = Field(ge=0)
    baseline_status: MetricStatus
    baseline_provenance: Provenance


class HistoricalComparisonResponse(StrictModel):
    comparison_status: Literal["not_comparable", "comparable", "descriptive_context_only"]
    reason: Literal[
        "missing_geography_crosswalk",
        "geography_crosswalk_unapproved",
        "missing_semantic_crosswalk",
        "semantic_crosswalk_unapproved",
        "no_compatible_facts",
        "no_approved_longitudinal_crosswalk",
        "missing_approved_context_crosswalk",
    ] | None = None
    eligible_for_integrity_analysis: bool | None = None
    comparison_key: str | None = None
    geography_crosswalk_version: str | None = None
    geography_approved_at: datetime | None = None
    baseline_geography_id: str | None = None
    data_version: str
    baseline_data_version: str
    geography_id: str
    requested_grain: GeographyLevel
    items: list[HistoricalComparisonItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def crosswalk_and_integrity_claims_are_consistent(self) -> "HistoricalComparisonResponse":
        if self.comparison_status == "descriptive_context_only":
            if self.eligible_for_integrity_analysis is not False:
                raise ValueError(
                    "Descriptive context must be explicitly ineligible"
                )
            crosswalk = (
                self.comparison_key,
                self.geography_crosswalk_version,
                self.geography_approved_at,
                self.baseline_geography_id,
            )
            if self.reason is not None and self.items:
                raise ValueError("Uncrosswalked descriptive context cannot emit compared facts")
            if self.reason is None and any(value is None for value in crosswalk):
                raise ValueError(
                    "Compared descriptive context requires an approved geography crosswalk"
                )
        elif self.comparison_status == "not_comparable":
            if self.reason is None or self.items:
                raise ValueError("Non-comparable responses require a reason and no facts")
        else:
            required = (
                self.comparison_key,
                self.geography_crosswalk_version,
                self.geography_approved_at,
                self.baseline_geography_id,
            )
            if any(value is None for value in required):
                raise ValueError("Comparable responses require an approved geography crosswalk")
            if self.eligible_for_integrity_analysis is not True:
                raise ValueError("Comparable responses must explicitly be analysis-eligible")
        return self


class Bulletin(StrictModel):
    id: str
    sequence: int
    published_at: datetime
    completion_percent: float = Field(ge=0, le=1)
    reported_mesas: int
    expected_mesas: int
    source_url: HttpUrl
    content_hash: str
    data_version: str


class BulletinResult(StrictModel):
    bulletin: Bulletin
    result: ResultFact
    provenance: Provenance


class SignalNumber(StrictModel):
    """A numeric analytical value whose absence is never silently treated as zero."""

    value: float | None
    status: MetricStatus

    @model_validator(mode="after")
    def explicit_observation(self) -> "SignalNumber":
        if (self.status == "observed") != (self.value is not None):
            raise ValueError(
                "Observed analytical values require a number; other states require null"
            )
        return self


class SignalCount(StrictModel):
    """An integer analytical count with explicit observed/unknown state."""

    value: int | None = Field(ge=0)
    status: MetricStatus

    @model_validator(mode="after")
    def explicit_observation(self) -> "SignalCount":
        if (self.status == "observed") != (self.value is not None):
            raise ValueError(
                "Observed analytical counts require an integer; other states require null"
            )
        return self


class DocumentarySignalAnalysis(StrictModel):
    kind: Literal["documentary"]
    eligibility: Literal["eligible", "ineligible"]
    reason: str | None
    evidence_artifact_hash: str = Field(pattern=_SHA256_PATTERN)
    evidence_artifact_kind: Literal["reconciliation_result", "document_review"]


class PeerSignalAnalysis(StrictModel):
    """The complete, replayable peer-distribution decision surface."""

    kind: Literal["peer_distribution"]
    eligibility: Literal["eligible", "ineligible"]
    reason: str | None
    public_point_eligible: bool
    analyzer_reason: str | None
    observed_rate: SignalNumber
    expected_rate: SignalNumber
    comparator: str
    peer_definition: str
    peer_count: SignalCount
    expected_unit_count: SignalCount
    expected_unit_digest: str = Field(pattern=_SHA256_PATTERN)
    standardized_residual: SignalNumber
    effect_pp: SignalNumber
    raw_p: SignalNumber
    adjusted_q: SignalNumber
    fit_method: str
    family_id: str
    cohort_hash: str = Field(pattern=_SHA256_PATTERN)
    input_hash: str = Field(pattern=_SHA256_PATTERN)
    output_hash: str = Field(pattern=_SHA256_PATTERN)
    code_hash: str = Field(pattern=_SHA256_PATTERN)
    method_hash: str = Field(pattern=_SHA256_PATTERN)
    analyzer_methodology_version: str


class SpatialSignalAnalysis(StrictModel):
    """The complete local-spatial decision surface, including exact membership."""

    kind: Literal["spatial_cluster"]
    eligibility: Literal["eligible", "ineligible"]
    reason: str | None
    analysis_unit_id: str
    analysis_grain: Literal["mesa", "polling_place"]
    neighbor_ids: list[str]
    signal_kind: str
    local_statistic: SignalNumber
    local_residual: SignalNumber
    raw_p: SignalNumber
    adjusted_q: SignalNumber
    seed: int | None
    permutations: SignalCount
    expected_unit_count: SignalCount
    expected_unit_digest: str = Field(pattern=_SHA256_PATTERN)
    family_id: str
    mesa_id: str
    peer_residual_hash: str = Field(pattern=_SHA256_PATTERN)
    input_hash: str = Field(pattern=_SHA256_PATTERN)
    output_hash: str = Field(pattern=_SHA256_PATTERN)
    code_hash: str = Field(pattern=_SHA256_PATTERN)
    method_hash: str = Field(pattern=_SHA256_PATTERN)
    geocode_source_url: HttpUrl
    geocode_source_hash: str = Field(pattern=_SHA256_PATTERN)
    coordinate_accuracy_m: float = Field(gt=0)
    analyzer_methodology_version: str
    peer_methodology_version: str
    analysis_unit_digest: str | None = Field(pattern=_SHA256_PATTERN)
    expected_mesa_count: SignalCount
    expected_mesa_digest: str | None = Field(pattern=_SHA256_PATTERN)
    mesa_membership_digest: str | None = Field(pattern=_SHA256_PATTERN)
    expected_mesa_membership_digest: str | None = Field(pattern=_SHA256_PATTERN)


SignalAnalysis = Annotated[
    DocumentarySignalAnalysis | PeerSignalAnalysis | SpatialSignalAnalysis,
    Field(discriminator="kind"),
]


class SignalComponent(StrictModel):
    component_type: Literal[
        "verified_accounting_failure",
        "conflicting_official_records",
        "documentary_difference_major",
        "documentary_difference_minor",
        "document_missing_duplicated_ambiguous",
        "peer_distribution",
        "spatial_cluster",
    ]
    points: int = Field(ge=0, le=100)
    observed_value: float | None
    comparator: str
    calculation: str
    peer_definition: str | None
    limitations: LocalizedText
    source_links: list[HttpUrl] = Field(min_length=1)
    evidence_artifact_hash: str | None = Field(pattern=_SHA256_PATTERN)
    evidence_artifact_kind: Literal["reconciliation_result", "document_review"] | None
    analyzer_output_hash: str | None = Field(pattern=_SHA256_PATTERN)
    family_id: str | None = Field(min_length=1)
    expected_family_count: int | None = Field(gt=0)
    expected_family_digest: str | None = Field(pattern=_SHA256_PATTERN)
    cohort_hash: str | None = Field(pattern=_SHA256_PATTERN)
    input_artifact_hash: str | None = Field(pattern=_SHA256_PATTERN)
    code_hash: str | None = Field(pattern=_SHA256_PATTERN)
    method_hash: str | None = Field(pattern=_SHA256_PATTERN)
    p_value: float | None = Field(ge=0, le=0.001)
    q_value: float | None = Field(ge=0, le=0.05)
    family_rank: int | None = Field(gt=0)
    family_size: int | None = Field(gt=0)
    adjustment_method: Literal["benjamini-yekutieli"] | None
    analyzer_mesa_id: str | None = Field(default=None, min_length=1)
    analysis_unit_id: str | None = Field(default=None, min_length=1)
    peer_residual_artifact_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    peer_methodology_version: str | None = Field(default=None, min_length=1)
    coordinate_source_url: HttpUrl | None = None
    coordinate_source_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    coordinate_accuracy_m: float | None = Field(default=None, gt=0)
    coordinate_grain: Literal["mesa", "polling_place"] | None = None
    analysis: SignalAnalysis

    @model_validator(mode="before")
    @classmethod
    def legacy_components_gain_an_explicit_analysis(cls, value: Any) -> Any:
        """Keep frozen synthetic fixtures readable while making public output typed.

        This migration only maps fields already present in the fixture; it does
        not infer votes, findings, or real-world evidence.
        """
        if not isinstance(value, dict) or "analysis" in value:
            return value
        value = dict(value)
        observed = value.get("observed_value")

        def number(item: object) -> dict[str, object]:
            return {
                "value": item,
                "status": "observed" if item is not None else "unknown",
            }

        def count(item: object) -> dict[str, object]:
            return {
                "value": item,
                "status": "observed" if item is not None else "unknown",
            }

        component_type = value.get("component_type")
        if component_type == "peer_distribution":
            public_eligible = value.get("public_point_eligible") is True
            reason = value.get("analyzer_reason") or value.get("reason")
            if "public_point_eligible" not in value:
                reason = "synthetic_fixture_not_production_eligible"
            value["analysis"] = {
                "kind": "peer_distribution",
                "eligibility": "eligible" if public_eligible else "ineligible",
                "reason": reason,
                "public_point_eligible": public_eligible,
                "analyzer_reason": reason,
                "observed_rate": number(
                    value.get("observed_rate", value.get("peer_observed_rate", observed))
                ),
                "expected_rate": number(
                    value.get("expected_rate", value.get("peer_expected_rate"))
                ),
                "comparator": value.get("comparator"),
                "peer_definition": value.get("peer_definition") or "not_recorded",
                "peer_count": count(
                    value.get("peers", value.get("peer_count", value.get("expected_family_count")))
                ),
                "expected_unit_count": count(value.get("expected_family_count")),
                "expected_unit_digest": value.get("expected_family_digest"),
                "standardized_residual": number(value.get("standardized_residual")),
                "effect_pp": number(value.get("effect_pp")),
                "raw_p": number(value.get("p_value")),
                "adjusted_q": number(value.get("q_value")),
                "fit_method": value.get("fit_method") or value.get("calculation"),
                "family_id": value.get("family_id"),
                "cohort_hash": value.get("cohort_hash"),
                "input_hash": value.get("input_artifact_hash"),
                "output_hash": value.get("analyzer_output_hash"),
                "code_hash": value.get("code_hash"),
                "method_hash": value.get("method_hash"),
                "analyzer_methodology_version": value.get("methodology_version")
                or "legacy-synthetic-unversioned",
            }
        elif component_type == "spatial_cluster":
            public_eligible = value.get("public_point_eligible") is True
            reason = value.get("analyzer_reason") or value.get("reason")
            if "public_point_eligible" not in value:
                reason = "legacy_component_without_exact_spatial_membership"
            value["analysis"] = {
                "kind": "spatial_cluster",
                "eligibility": "eligible" if public_eligible else "ineligible",
                "reason": reason,
                "analysis_unit_id": value.get("analysis_unit_id") or value.get("analyzer_mesa_id"),
                "analysis_grain": value.get("coordinate_grain") or "mesa",
                "neighbor_ids": value.get("neighbors", value.get("spatial_neighbors", [])),
                "signal_kind": value.get("signal_kind")
                or value.get("spatial_signal_kind")
                or "not_recorded",
                "local_statistic": number(value.get("local_statistic", observed)),
                "local_residual": number(
                    value.get("local_residual", value.get("spatial_local_residual"))
                ),
                "raw_p": number(value.get("p_value")),
                "adjusted_q": number(value.get("q_value")),
                "seed": value.get("randomization_seed"),
                "permutations": count(value.get("permutations", value.get("spatial_permutations"))),
                "expected_unit_count": count(value.get("expected_family_count")),
                "expected_unit_digest": value.get("expected_family_digest"),
                "family_id": value.get("family_id"),
                "mesa_id": value.get("analyzer_mesa_id"),
                "peer_residual_hash": value.get("peer_residual_artifact_hash"),
                "input_hash": value.get("input_artifact_hash"),
                "output_hash": value.get("analyzer_output_hash"),
                "code_hash": value.get("code_hash"),
                "method_hash": value.get("method_hash"),
                "geocode_source_url": value.get("coordinate_source_url"),
                "geocode_source_hash": value.get("coordinate_source_hash"),
                "coordinate_accuracy_m": value.get("coordinate_accuracy_m"),
                "analyzer_methodology_version": value.get("methodology_version")
                or "legacy-synthetic-unversioned",
                "peer_methodology_version": value.get("peer_methodology_version")
                or "legacy-synthetic-unversioned",
                "analysis_unit_digest": value.get("analysis_unit_digest"),
                "expected_mesa_count": count(value.get("expected_mesa_count")),
                "expected_mesa_digest": value.get("expected_mesa_digest"),
                "mesa_membership_digest": value.get("mesa_membership_digest"),
                "expected_mesa_membership_digest": value.get("expected_mesa_membership_digest"),
            }
        else:
            value["analysis"] = {
                "kind": "documentary",
                "eligibility": "eligible",
                "reason": None,
                "evidence_artifact_hash": value.get("evidence_artifact_hash"),
                "evidence_artifact_kind": value.get("evidence_artifact_kind"),
            }
        for pipeline_field in (
            "peer_observed_rate",
            "peer_expected_rate",
            "peer_count",
            "standardized_residual",
            "effect_pp",
            "fit_method",
            "public_point_eligible",
            "analyzer_reason",
            "spatial_neighbors",
            "spatial_signal_kind",
            "spatial_local_residual",
            "randomization_seed",
            "spatial_permutations",
            "analysis_unit_digest",
            "expected_mesa_count",
            "expected_mesa_digest",
            "mesa_membership_digest",
            "expected_mesa_membership_digest",
            "observed_rate",
            "expected_rate",
            "peers",
            "neighbors",
            "signal_kind",
            "local_statistic",
            "local_residual",
            "permutations",
            "methodology_version",
            "reason",
        ):
            value.pop(pipeline_field, None)
        return value

    @model_validator(mode="after")
    def analyzer_binding_is_complete(self) -> "SignalComponent":
        if self.points != _SIGNAL_COMPONENT_POINTS[self.component_type]:
            raise ValueError("component points do not match the frozen methodology")
        statistical_values = (
            self.analyzer_output_hash,
            self.family_id,
            self.expected_family_count,
            self.expected_family_digest,
            self.cohort_hash,
            self.input_artifact_hash,
            self.code_hash,
            self.method_hash,
            self.p_value,
            self.q_value,
            self.family_rank,
            self.family_size,
            self.adjustment_method,
        )
        statistical = self.component_type in _STATISTICAL_COMPONENTS
        evidence_binding = (self.evidence_artifact_hash, self.evidence_artifact_kind)
        if statistical and any(value is not None for value in evidence_binding):
            raise ValueError("statistical components cannot claim documentary evidence artifacts")
        if not statistical and any(value is None for value in evidence_binding):
            raise ValueError("documentary components require an authenticated evidence artifact")
        if statistical and any(value is None for value in statistical_values):
            raise ValueError("statistical components require a complete typed analyzer binding")
        if not statistical and any(value is not None for value in statistical_values):
            raise ValueError("documentary components cannot claim a statistical analyzer binding")
        optional_analyzer_values = (
            self.analyzer_mesa_id,
            self.analysis_unit_id,
            self.peer_residual_artifact_hash,
            self.peer_methodology_version,
            self.coordinate_source_url,
            self.coordinate_source_hash,
            self.coordinate_accuracy_m,
            self.coordinate_grain,
        )
        if not statistical and any(value is not None for value in optional_analyzer_values):
            raise ValueError("documentary components cannot claim optional analyzer provenance")
        spatial_values = (
            self.analysis_unit_id,
            self.peer_residual_artifact_hash,
            self.peer_methodology_version,
            self.coordinate_source_url,
            self.coordinate_source_hash,
            self.coordinate_accuracy_m,
            self.coordinate_grain,
        )
        populated_spatial = sum(value is not None for value in spatial_values)
        if populated_spatial and (
            self.component_type != "spatial_cluster" or populated_spatial != len(spatial_values)
        ):
            raise ValueError("spatial analyzer provenance must be complete and spatial-only")
        if (
            self.family_rank is not None
            and self.family_size is not None
            and self.family_rank > self.family_size
        ):
            raise ValueError("statistical family rank cannot exceed family size")
        if (
            self.family_size is not None
            and self.expected_family_count is not None
            and self.family_size > self.expected_family_count
        ):
            raise ValueError("adjusted family size cannot exceed expected family coverage")
        if (
            statistical
            and self.p_value is not None
            and self.q_value is not None
            and (self.q_value < self.p_value or self.p_value > 0.001 or self.q_value > 0.05)
        ):
            raise ValueError("statistical components must pass the frozen p/q gates")
        expected_kind = (
            "peer_distribution"
            if self.component_type == "peer_distribution"
            else "spatial_cluster"
            if self.component_type == "spatial_cluster"
            else "documentary"
        )
        if self.analysis.kind != expected_kind:
            raise ValueError("component type and typed analysis kind must match")
        return self


class ReviewSignal(StrictModel):
    id: str
    mesa_id: str
    score: int = Field(ge=0, le=100)
    tier: SignalTier
    affected_vote_estimate: int | None = Field(default=None, ge=0)
    methodology_version: str
    components: list[SignalComponent]
    disclosure: LocalizedText
    provenance: Provenance

    @model_validator(mode="after")
    def score_tier_and_components_are_consistent(self) -> "ReviewSignal":
        component_types = [component.component_type for component in self.components]
        if len(component_types) != len(set(component_types)):
            raise ValueError("review signals cannot duplicate component types")
        expected_tier = review_signal_tier(self.score)
        if self.tier != expected_tier:
            raise ValueError("review signal tier does not match its score")
        deterministic = max(
            (
                component.points
                for component in self.components
                if component.component_type not in _STATISTICAL_COMPONENTS
            ),
            default=0,
        )
        statistical = min(
            20,
            sum(
                component.points
                for component in self.components
                if component.component_type in _STATISTICAL_COMPONENTS
            ),
        )
        if self.score != min(100, deterministic + statistical):
            raise ValueError("review signal score does not match its components")
        if all(
            component in _STATISTICAL_COMPONENTS for component in component_types
        ) and self.affected_vote_estimate not in {None, 0}:
            raise ValueError("statistical-only signals cannot claim affected votes")
        return self


class ReviewSignalPage(StrictModel):
    items: list[ReviewSignal]
    page: CursorMeta
    data_version: str
    methodology_version: str
    disclosure: LocalizedText


class ExplanationMetadata(StrictModel):
    """Preregistered explanation-review metadata; it never changes detection."""

    status: ExplanationStatus
    preregistration_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    available_data_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    reviewed_at: datetime | None = None
    quantitative_effect: SignalNumber
    quantitative_p_value: SignalNumber
    notes: LocalizedText | None = None

    @model_validator(mode="after")
    def explanation_has_only_recorded_evidence(self) -> "ExplanationMetadata":
        if (
            self.status in {"explained", "partially_explained"}
            and self.preregistration_hash is None
        ):
            raise ValueError("explanatory conclusions require a preregistration hash")
        if self.status == "non_evaluable" and any(
            value is not None
            for value in (
                self.preregistration_hash,
                self.available_data_hash,
                self.reviewed_at,
                self.notes,
            )
        ):
            raise ValueError("non-evaluable explanations cannot claim review metadata")
        return self


class AnalysisAnomaly(StrictModel):
    id: str = Field(min_length=1)
    mesa_id: str = Field(min_length=1)
    anomaly_types: list[AnomalyType] = Field(min_length=1)
    is_anomaly: bool
    audit_priority_score: int = Field(ge=0, le=100)
    explanation: ExplanationMetadata
    minimum_ballot_edits: SignalCount
    minimum_ballot_edits_status: Literal["evaluable", "not_evaluable"]
    minimum_ballot_edits_reason: str | None = None
    components: list[SignalComponent]
    research_preview: bool
    ineligible_reasons: list[str]
    methodology_version: str = Field(min_length=1)
    disclosure: LocalizedText
    provenance: Provenance

    @model_validator(mode="after")
    def anomaly_semantics_are_separate_from_explanation(self) -> "AnalysisAnomaly":
        if len(self.anomaly_types) != len(set(self.anomaly_types)):
            raise ValueError("anomaly types must be unique")
        if self.minimum_ballot_edits_status == "evaluable":
            if self.minimum_ballot_edits.status != "observed":
                raise ValueError("evaluable ballot-edit bounds require an observed value")
        elif self.minimum_ballot_edits.status == "observed":
            raise ValueError("non-evaluable ballot-edit bounds must not contain a value")
        if (
            self.disclosure.es != ANALYTICAL_DISCLOSURE_ES
            or self.disclosure.en != ANALYTICAL_DISCLOSURE_EN
        ):
            raise ValueError("analysis disclosure is a permanent anti-fraud wording")
        return self


class AnalysisAnomalyPage(StrictModel):
    items: list[AnalysisAnomaly]
    page: CursorMeta
    data_version: str
    methodology_version: str
    disclosure: LocalizedText


class AnalysisSummary(StrictModel):
    election_slug: str
    data_version: str
    methodology_version: str
    total_records_evaluated: SignalCount
    anomaly_count: SignalCount
    anomaly_counts: dict[AnomalyType, SignalCount]
    missingness: Coverage
    research_preview: bool
    ineligible_reasons: list[str]
    disclosure: LocalizedText
    provenance: Provenance

    @model_validator(mode="after")
    def summary_disclosure_is_permanent(self) -> "AnalysisSummary":
        if (
            self.disclosure.es != ANALYTICAL_DISCLOSURE_ES
            or self.disclosure.en != ANALYTICAL_DISCLOSURE_EN
        ):
            raise ValueError("analysis disclosure is a permanent anti-fraud wording")
        return self


class AnalysisReport(StrictModel):
    report_kind: Literal["model_diagnostics", "validation", "local_sensitivity"]
    status: Literal["available", "research_preview", "ineligible", "not_evaluable"]
    research_preview: bool
    ineligible_reasons: list[str]
    methodology_version: str
    artifact_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    missingness: Coverage
    provenance: Provenance
    disclosure: LocalizedText
    metrics: dict[str, SignalNumber]

    @model_validator(mode="after")
    def report_disclosure_is_permanent(self) -> "AnalysisReport":
        if (
            self.disclosure.es != ANALYTICAL_DISCLOSURE_ES
            or self.disclosure.en != ANALYTICAL_DISCLOSURE_EN
        ):
            raise ValueError("analysis disclosure is a permanent anti-fraud wording")
        return self


class OutcomeGeographicScope(StrictModel):
    level: Literal["mesa", "place", "municipality", "department", "national"]
    key: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_key_matches_level(self) -> "OutcomeGeographicScope":
        expected_length = {
            "mesa": 4,
            "place": 3,
            "municipality": 2,
            "department": 1,
            "national": 1,
        }[self.level]
        if len(self.key) != expected_length or (self.level == "national" and self.key != ["CO"]):
            raise ValueError("Outcome geographic key does not match its level")
        return self


class OutcomeSourceScope(StrictModel):
    source_id: str = Field(min_length=1)
    fact_grain: Literal["mesa", "place", "municipality", "department", "national"]
    source_type: SourceType
    legal_status: LegalStatus

    @model_validator(mode="after")
    def source_type_matches_legal_status(self) -> "OutcomeSourceScope":
        expected = {
            "final_declaration": "controlling_final",
            "scrutiny": "official_scrutiny",
            "e14_delegate": "documentary_evidence",
            "e14_transmission": "documentary_evidence",
            "pre_count": "preliminary",
            "contextual_baseline": "context_only",
        }[self.source_type]
        if self.legal_status != expected:
            raise ValueError("Outcome source type and legal status are incompatible")
        return self


class OutcomeSensitivityIssue(StrictModel):
    code: str = Field(min_length=1)
    record_ids: list[Annotated[str, Field(min_length=1)]]


class OutcomeSensitivityArtifact(StrictModel):
    """Exact core artifact serialized by the pipeline, before API scoping."""

    status: Literal[
        "not_evaluable",
        "robust_within_evaluated_bounds",
        "tie_within_verified_bound",
        "lead_change_within_verified_bound",
        "tie_only_with_unresolved_bound",
        "lead_change_only_with_unresolved_bound",
    ]
    evaluable: bool
    issues: list[OutcomeSensitivityIssue]
    scope: OutcomeGeographicScope | None
    outcome_source: OutcomeSourceScope | None
    leader_id: Annotated[str, Field(min_length=1)] | None
    runner_up_id: Annotated[str, Field(min_length=1)] | None
    leader_votes: int | None = Field(ge=0)
    runner_up_votes: int | None = Field(ge=0)
    observed_margin_votes: int | None = Field(ge=0)
    verified_record_ids: list[Annotated[str, Field(min_length=1)]] | None
    unresolved_record_ids: list[Annotated[str, Field(min_length=1)]] | None
    verified_affected_votes: int | None = Field(ge=0)
    verified_margin_shift_bound: int | None = Field(ge=0)
    unresolved_affected_vote_upper_bound: int | None = Field(ge=0)
    unresolved_margin_shift_upper_bound: int | None = Field(ge=0)
    combined_affected_vote_upper_bound: int | None = Field(ge=0)
    combined_margin_shift_upper_bound: int | None = Field(ge=0)
    verified_margin_headroom: int | None
    combined_margin_headroom: int | None
    tie_possible_from_verified: bool | None
    lead_change_possible_from_verified: bool | None
    tie_possible_including_unresolved: bool | None
    lead_change_possible_including_unresolved: bool | None
    source_links: list[HttpUrl]
    evidence_hash: str | None = Field(pattern=_SHA256_PATTERN)
    output_hash: str = Field(pattern=_SHA256_PATTERN)
    methodology_version: Literal["outcome-sensitivity-v3.0.0"]
    calculation: str = Field(min_length=1)
    limitations: list[Annotated[str, Field(min_length=1)]]

    @model_validator(mode="before")
    @classmethod
    def raw_pipeline_hash_is_canonical(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = {
            key: item
            for key, item in value.items()
            if key
            not in {
                "release_id",
                "election_slug",
                "data_version",
                "margin_shift_factor",
                "output_hash",
            }
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if hashlib.sha256(encoded).hexdigest() != value.get("output_hash"):
            raise ValueError("Outcome sensitivity output_hash is not canonical")
        return value

    def pipeline_artifact_payload(self) -> dict[str, object]:
        payload = self.model_dump(
            mode="json",
            exclude={"release_id", "election_slug", "data_version", "margin_shift_factor"},
        )
        payload.pop("output_hash")
        return payload

    @model_validator(mode="after")
    def status_and_bounds_are_consistent(self) -> "OutcomeSensitivityArtifact":
        if self.evaluable != (self.status != "not_evaluable"):
            raise ValueError("Outcome sensitivity evaluable flag must match status")
        top_two_fields = (
            self.leader_id,
            self.runner_up_id,
            self.leader_votes,
            self.runner_up_votes,
            self.observed_margin_votes,
        )
        if any(value is None for value in top_two_fields) and any(
            value is not None for value in top_two_fields
        ):
            raise ValueError("Observed top-two outcome fields must be all present or all null")
        if self.leader_votes is not None:
            assert self.runner_up_votes is not None
            assert self.observed_margin_votes is not None
            if self.leader_votes < self.runner_up_votes or (
                self.observed_margin_votes != self.leader_votes - self.runner_up_votes
            ):
                raise ValueError("Observed outcome margin does not match the top-two totals")
        derived_fields = (
            self.verified_affected_votes,
            self.verified_margin_shift_bound,
            self.unresolved_affected_vote_upper_bound,
            self.unresolved_margin_shift_upper_bound,
            self.combined_affected_vote_upper_bound,
            self.combined_margin_shift_upper_bound,
            self.verified_margin_headroom,
            self.combined_margin_headroom,
            self.tie_possible_from_verified,
            self.lead_change_possible_from_verified,
            self.tie_possible_including_unresolved,
            self.lead_change_possible_including_unresolved,
        )
        if not self.evaluable:
            if (
                any(value is not None for value in derived_fields)
                or self.evidence_hash is not None
                or not self.issues
            ):
                raise ValueError("Non-evaluable outcome artifacts cannot publish decision bounds")
            return self
        if (
            self.scope is None
            or self.outcome_source is None
            or any(value is None for value in top_two_fields)
            or self.verified_record_ids is None
            or self.unresolved_record_ids is None
            or any(value is None for value in derived_fields)
            or self.evidence_hash is None
            or not self.source_links
            or self.issues
        ):
            raise ValueError("Evaluable outcome artifacts require complete typed decision data")
        assert self.leader_votes is not None
        assert self.runner_up_votes is not None
        assert self.observed_margin_votes is not None
        assert self.verified_affected_votes is not None
        assert self.verified_margin_shift_bound is not None
        assert self.unresolved_affected_vote_upper_bound is not None
        assert self.unresolved_margin_shift_upper_bound is not None
        assert self.combined_affected_vote_upper_bound is not None
        assert self.combined_margin_shift_upper_bound is not None
        if self.combined_affected_vote_upper_bound != (
            self.verified_affected_votes + self.unresolved_affected_vote_upper_bound
        ) or self.combined_margin_shift_upper_bound != (
            self.verified_margin_shift_bound + self.unresolved_margin_shift_upper_bound
        ):
            raise ValueError("Combined outcome bounds do not equal their typed components")
        if (
            self.verified_margin_shift_bound > 2 * self.verified_affected_votes
            or self.unresolved_margin_shift_upper_bound
            > 2 * self.unresolved_affected_vote_upper_bound
        ):
            raise ValueError("Margin-shift bounds exceed the frozen two-times factor")
        margin = self.observed_margin_votes
        verified_shift = self.verified_margin_shift_bound
        combined_shift = self.combined_margin_shift_upper_bound
        expected_status = (
            "lead_change_within_verified_bound"
            if verified_shift > margin
            else "lead_change_only_with_unresolved_bound"
            if combined_shift > margin
            else "tie_within_verified_bound"
            if verified_shift >= margin
            else "tie_only_with_unresolved_bound"
            if combined_shift >= margin
            else "robust_within_evaluated_bounds"
        )
        expected_values = (
            margin - verified_shift,
            margin - combined_shift,
            verified_shift >= margin,
            verified_shift > margin,
            combined_shift >= margin,
            combined_shift > margin,
        )
        actual_values = (
            self.verified_margin_headroom,
            self.combined_margin_headroom,
            self.tie_possible_from_verified,
            self.lead_change_possible_from_verified,
            self.tie_possible_including_unresolved,
            self.lead_change_possible_including_unresolved,
        )
        if self.status != expected_status or actual_values != expected_values:
            raise ValueError("Outcome status, headroom, or tie/change flags are inconsistent")
        return self


class OutcomeSensitivity(OutcomeSensitivityArtifact):
    """A core artifact bound to one immutable public release/election scope."""

    release_id: str
    election_slug: str
    data_version: str
    margin_shift_factor: Literal[2]

    @model_validator(mode="after")
    def release_scope_is_consistent(self) -> "OutcomeSensitivity":
        if self.data_version != self.release_id:
            raise ValueError("Outcome sensitivity data_version must equal release_id")
        return self


class Dataset(StrictModel):
    id: str
    title: LocalizedText
    format: Literal["csv", "parquet", "json"]
    url: HttpUrl
    schema_url: HttpUrl
    record_count: int
    byte_size: int
    content_hash: str
    filters: dict[str, str]
