"""Async SQLAlchemy storage shape for verified immutable releases.

The public app deliberately uses the fixture repository by default; these models
make the production Postgres representation explicit without coupling routes to
an ORM session.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# The original tables below are retained for audit/legacy snapshot imports.  New
# public reads use these explicitly scoped tables.  An id is never globally
# meaningful: the release and election are part of every identity.
class ReleaseExposureModel(Base):
    __tablename__ = "release_exposures"
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    access_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # A preliminary grant is disjoint from the certified one: CHECK constraints
    # forbid a row from carrying both approvals (migration 20260806_01).
    preliminary_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preliminary_caveat_es: Mapped[str | None] = mapped_column(Text)
    preliminary_caveat_en: Mapped[str | None] = mapped_column(Text)


class ReleaseElectionModel(Base):
    __tablename__ = "release_elections"
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    name_es: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    __table_args__ = (UniqueConstraint("release_id", "election_slug", name="uq_release_election"),)


class ReleaseSummaryModel(Base):
    """Pipeline-computed summary blocks, stored verbatim.

    These are not derivable from the loaded rows: completion reports 122,017
    reported against 122,020 installed, and reconciliation is ``blocked`` with
    three exceptions. Recomputing them from the rows would silently convert a
    blocked reconciliation into a passing one, so they are copied as recorded
    and served as recorded.
    """

    __tablename__ = "release_summaries"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_class: Mapped[str] = mapped_column(String(32), nullable=False)
    completion: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    coverage: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    geographic_collection_coverage: Mapped[dict[str, object] | None] = mapped_column(JSON)
    reconciliation: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    turnout: Mapped[float | None] = mapped_column(Float)
    preview_caveat_es: Mapped[str | None] = mapped_column(Text)
    preview_caveat_en: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
    )


class ReleaseGeographyModel(Base):
    __tablename__ = "release_geographies"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(200))
    canonical_path: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
            deferrable=True,
            initially="IMMEDIATE",
        ),
    )


class ReleaseMesaModel(Base):
    __tablename__ = "release_mesas"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    display_number: Mapped[str] = mapped_column(String(64), nullable=False)
    polling_place_id: Mapped[str] = mapped_column(String(200), nullable=False)
    municipality_id: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[str] = mapped_column(String(200), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
            deferrable=True,
            initially="IMMEDIATE",
        ),
    )


class ReleaseSourceModel(Base):
    __tablename__ = "release_sources"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    legal_status: Mapped[str] = mapped_column(String(48), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(128), nullable=False)


class ReleaseResultFactModel(Base):
    __tablename__ = "release_result_facts"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    geography_id: Mapped[str] = mapped_column(String(200), nullable=False)
    geography_level: Mapped[str] = mapped_column(String(32), nullable=False)
    mesa_id: Mapped[str | None] = mapped_column(String(200))
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    # Per-fact provenance. All 136,459 leaf facts carry distinct hashes, so
    # hoisting provenance to the source row for list responses would lose the
    # per-mesa evidence trail; the detail endpoint reads these instead.
    fact_content_hash: Mapped[str | None] = mapped_column(String(64))
    fact_retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
            deferrable=True,
            initially="IMMEDIATE",
        ),
    )


class ReleaseCategoryFactModel(Base):
    __tablename__ = "release_category_facts"
    release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    result_fact_id: Mapped[str] = mapped_column(String(240), primary_key=True)
    category_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    category_code: Mapped[str] = mapped_column(String(96), nullable=False)
    category_name: Mapped[str] = mapped_column(Text, nullable=False)
    category_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    votes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
            deferrable=True,
            initially="IMMEDIATE",
        ),
    )


class ComparisonCrosswalkModel(Base):
    __tablename__ = "comparison_crosswalks"
    current_release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    current_election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    baseline_release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    baseline_election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    current_geography_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    baseline_geography_id: Mapped[str] = mapped_column(String(200), nullable=False)
    grain: Mapped[str] = mapped_column(String(32), nullable=False)
    comparison_key: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    # A row is deliberately not an approval by itself.  This timestamp is set
    # only by the release approval workflow, never inferred from names/codes.
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SemanticCategoryCrosswalkModel(Base):
    """An independently approved category equivalence for historical reads."""

    __tablename__ = "semantic_category_crosswalks"
    current_release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    current_election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    baseline_release_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    baseline_election_slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    comparison_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    current_category_key: Mapped[str] = mapped_column(String(300), primary_key=True)
    current_source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    baseline_category_key: Mapped[str] = mapped_column(String(300), nullable=False)
    baseline_source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    category_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseModel(Base):
    __tablename__ = "releases"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    methodology_version: Mapped[str | None] = mapped_column(String(128))
    manifest: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class ElectionModel(Base):
    __tablename__ = "elections"
    slug: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    name_es: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)


class CandidateSlateModel(Base):
    __tablename__ = "candidate_slates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["election_slug", "release_id"],
            ["elections.slug", "elections.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), nullable=False)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    ballot_number: Mapped[int | None] = mapped_column(Integer)
    name_es: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    short_name_es: Mapped[str] = mapped_column(Text, nullable=False)
    short_name_en: Mapped[str] = mapped_column(Text, nullable=False)


class CrawlModel(Base):
    __tablename__ = "crawls"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_status: Mapped[str] = mapped_column(String(32), nullable=False)


class SourceProvenanceModel(Base):
    __tablename__ = "source_provenance"
    __table_args__ = (
        ForeignKeyConstraint(
            ["crawl_id", "release_id"],
            ["crawls.id", "crawls.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    crawl_id: Mapped[str | None] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(48), nullable=False)
    legal_status: Mapped[str] = mapped_column(String(48), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(128), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(128), nullable=False)
    methodology_version: Mapped[str | None] = mapped_column(String(128))


class GeographyModel(Base):
    __tablename__ = "geographies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["parent_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String(160))
    coordinates: Mapped[dict[str, object] | None] = mapped_column(JSON)


class PollingPlaceModel(Base):
    __tablename__ = "polling_places"
    __table_args__ = (
        ForeignKeyConstraint(
            ["geography_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    geography_id: Mapped[str] = mapped_column(String(160), nullable=False)


class MesaModel(Base):
    __tablename__ = "mesas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["polling_place_id", "release_id"],
            ["polling_places.id", "polling_places.release_id"],
        ),
        ForeignKeyConstraint(
            ["municipality_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
        ForeignKeyConstraint(
            ["department_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    display_number: Mapped[str] = mapped_column(String(64), nullable=False)
    polling_place_id: Mapped[str] = mapped_column(String(160), nullable=False)
    municipality_id: Mapped[str] = mapped_column(String(160), nullable=False)
    department_id: Mapped[str] = mapped_column(String(160), nullable=False)


class ResultFactModel(Base):
    __tablename__ = "result_facts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["election_slug", "release_id"],
            ["elections.slug", "elections.release_id"],
        ),
        ForeignKeyConstraint(
            ["geography_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
        ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
        ForeignKeyConstraint(
            ["source_provenance_id", "release_id"],
            ["source_provenance.id", "source_provenance.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    election_slug: Mapped[str] = mapped_column(String(160), nullable=False)
    geography_id: Mapped[str] = mapped_column(String(160), nullable=False)
    geography_level: Mapped[str] = mapped_column(String(32), nullable=False)
    mesa_id: Mapped[str | None] = mapped_column(String(160))
    source_provenance_id: Mapped[str] = mapped_column(String(160), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class CandidateVoteModel(Base):
    __tablename__ = "candidate_votes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_fact_id", "release_id"],
            ["result_facts.id", "result_facts.release_id"],
        ),
        ForeignKeyConstraint(
            ["candidate_id", "release_id"],
            ["candidate_slates.id", "candidate_slates.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    result_fact_id: Mapped[str] = mapped_column(String(160), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class DocumentModel(Base):
    __tablename__ = "documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    mesa_id: Mapped[str] = mapped_column(String(160), nullable=False)
    document_type: Mapped[str] = mapped_column(String(48), nullable=False)
    official_url: Mapped[str] = mapped_column(Text, nullable=False)
    full_file_hash: Mapped[str | None] = mapped_column(String(64))
    derivative_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_payload: Mapped[dict[str, object]] = mapped_column("metadata", JSON, nullable=False)


class ReconciliationModel(Base):
    __tablename__ = "reconciliations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["result_fact_id", "release_id"],
            ["result_facts.id", "result_facts.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    result_fact_id: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    checked_facts: Mapped[int] = mapped_column(Integer, nullable=False)
    exceptions: Mapped[int] = mapped_column(Integer, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class MethodologyModel(Base):
    __tablename__ = "methodologies"
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class SignalScoreModel(Base):
    __tablename__ = "signal_scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
        ForeignKeyConstraint(
            ["methodology_version", "release_id"],
            ["methodologies.version", "methodologies.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    mesa_id: Mapped[str] = mapped_column(String(160), nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[str] = mapped_column(String(80), nullable=False)
    affected_vote_estimate: Mapped[int | None] = mapped_column(Integer)
    disclosure: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class SignalComponentModel(Base):
    __tablename__ = "signal_components"
    __table_args__ = (
        ForeignKeyConstraint(
            ["signal_score_id", "release_id"],
            ["signal_scores.id", "signal_scores.release_id"],
        ),
    )
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    signal_score_id: Mapped[str] = mapped_column(String(160), nullable=False)
    component_type: Mapped[str] = mapped_column(String(80), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class DatasetModel(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    title: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    object_url: Mapped[str] = mapped_column(Text, nullable=False)
    schema_url: Mapped[str] = mapped_column(Text, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    filters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
