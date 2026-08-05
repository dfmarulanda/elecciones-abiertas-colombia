"""initial immutable election release schema

Revision ID: 20260803_01
Revises:
Create Date: 2026-08-03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260803_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "releases",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("methodology_version", sa.String(length=128)),
        sa.Column("manifest", sa.JSON(), nullable=False),
    )
    op.create_table(
        "elections",
        sa.Column("slug", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("name_es", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("election_date", sa.Date(), nullable=False),
    )
    op.create_table(
        "candidate_slates",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column("election_slug", sa.String(length=160), nullable=False),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("ballot_number", sa.Integer()),
        sa.Column("name_es", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("short_name_es", sa.Text(), nullable=False),
        sa.Column("short_name_en", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["election_slug", "release_id"],
            ["elections.slug", "elections.release_id"],
        ),
    )
    op.create_table(
        "crawls",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("retrieval_status", sa.String(length=32), nullable=False),
    )
    op.create_table(
        "source_provenance",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("crawl_id", sa.String(length=160)),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("legal_status", sa.String(length=48), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=128), nullable=False),
        sa.Column("transform_version", sa.String(length=128), nullable=False),
        sa.Column("methodology_version", sa.String(length=128)),
        sa.ForeignKeyConstraint(
            ["crawl_id", "release_id"],
            ["crawls.id", "crawls.release_id"],
        ),
    )
    op.create_table(
        "geographies",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.String(length=160)),
        sa.Column("coordinates", sa.JSON()),
        sa.ForeignKeyConstraint(
            ["parent_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    op.create_table(
        "polling_places",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("geography_id", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ["geography_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    op.create_table(
        "mesas",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("display_number", sa.String(length=64), nullable=False),
        sa.Column("polling_place_id", sa.String(length=160), nullable=False),
        sa.Column("municipality_id", sa.String(length=160), nullable=False),
        sa.Column("department_id", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(
            ["polling_place_id", "release_id"],
            ["polling_places.id", "polling_places.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["municipality_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["department_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
    )
    op.create_table(
        "result_facts",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("election_slug", sa.String(length=160), nullable=False),
        sa.Column("geography_id", sa.String(length=160), nullable=False),
        sa.Column("geography_level", sa.String(length=32), nullable=False),
        sa.Column("mesa_id", sa.String(length=160)),
        sa.Column(
            "source_provenance_id",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["election_slug", "release_id"],
            ["elections.slug", "elections.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["geography_id", "release_id"],
            ["geographies.id", "geographies.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_provenance_id", "release_id"],
            ["source_provenance.id", "source_provenance.release_id"],
        ),
    )
    op.create_table(
        "candidate_votes",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column(
            "result_fact_id",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("candidate_id", sa.String(length=160), nullable=False),
        sa.Column("value", sa.Integer()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_fact_id", "release_id"],
            ["result_facts.id", "result_facts.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id", "release_id"],
            ["candidate_slates.id", "candidate_slates.release_id"],
        ),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("mesa_id", sa.String(length=160), nullable=False),
        sa.Column("document_type", sa.String(length=48), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("full_file_hash", sa.String(length=64)),
        sa.Column("derivative_hash", sa.String(length=64)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
    )
    op.create_table(
        "reconciliations",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("result_fact_id", sa.String(length=160)),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checked_facts", sa.Integer(), nullable=False),
        sa.Column("exceptions", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_fact_id", "release_id"],
            ["result_facts.id", "result_facts.release_id"],
        ),
    )
    op.create_table(
        "methodologies",
        sa.Column("version", sa.String(length=128), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "signal_scores",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("mesa_id", sa.String(length=160), nullable=False),
        sa.Column("methodology_version", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(length=80), nullable=False),
        sa.Column("affected_vote_estimate", sa.Integer()),
        sa.Column("disclosure", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mesa_id", "release_id"],
            ["mesas.id", "mesas.release_id"],
        ),
        sa.ForeignKeyConstraint(
            ["methodology_version", "release_id"],
            ["methodologies.version", "methodologies.release_id"],
        ),
    )
    op.create_table(
        "signal_components",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column(
            "signal_score_id",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("component_type", sa.String(length=80), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["signal_score_id", "release_id"],
            ["signal_scores.id", "signal_scores.release_id"],
        ),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=160), primary_key=True),
        sa.Column(
            "release_id", sa.String(length=128), sa.ForeignKey("releases.id"), primary_key=True
        ),
        sa.Column("title", sa.JSON(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("object_url", sa.Text(), nullable=False),
        sa.Column("schema_url", sa.Text(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("datasets")
    op.drop_table("signal_components")
    op.drop_table("signal_scores")
    op.drop_table("methodologies")
    op.drop_table("reconciliations")
    op.drop_table("documents")
    op.drop_table("candidate_votes")
    op.drop_table("result_facts")
    op.drop_table("mesas")
    op.drop_table("polling_places")
    op.drop_table("geographies")
    op.drop_table("source_provenance")
    op.drop_table("crawls")
    op.drop_table("candidate_slates")
    op.drop_table("elections")
    op.drop_table("releases")
