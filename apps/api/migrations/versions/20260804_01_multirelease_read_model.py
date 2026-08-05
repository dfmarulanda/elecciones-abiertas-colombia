"""Scoped immutable release read model.

The legacy schema used global ids and is intentionally left untouched so a
rollback does not rewrite prior audit records.  Public serving uses the new
release/election scoped tables exclusively.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_01"
down_revision = "20260803_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_elections",
        sa.Column("release_id", sa.String(128), sa.ForeignKey("releases.id"), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("name_es", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("election_date", sa.Date(), nullable=False),
    )
    op.create_table(
        "release_exposures",
        sa.Column("release_id", sa.String(128), sa.ForeignKey("releases.id"), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("access_scope", sa.String(16), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
    )
    op.create_table(
        "release_geographies",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("level", sa.String(32), nullable=False),
        sa.Column("code", sa.String(96), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.String(200)),
        sa.Column("canonical_path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "parent_id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
    )
    op.create_table(
        "release_mesas",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("display_number", sa.String(64), nullable=False),
        sa.Column("polling_place_id", sa.String(200), nullable=False),
        sa.Column("municipality_id", sa.String(200), nullable=False),
        sa.Column("department_id", sa.String(200), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "polling_place_id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "municipality_id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "department_id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
    )
    op.create_table(
        "release_sources",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("legal_status", sa.String(48), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(128), nullable=False),
        sa.Column("transform_version", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
    )
    op.create_table(
        "release_result_facts",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("id", sa.String(240), primary_key=True),
        sa.Column("geography_id", sa.String(200), nullable=False),
        sa.Column("geography_level", sa.String(32), nullable=False),
        sa.Column("mesa_id", sa.String(200)),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "geography_id"],
            [
                "release_geographies.release_id",
                "release_geographies.election_slug",
                "release_geographies.id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "mesa_id"],
            ["release_mesas.release_id", "release_mesas.election_slug", "release_mesas.id"],
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "source_id"],
            ["release_sources.release_id", "release_sources.election_slug", "release_sources.id"],
        ),
    )
    op.create_table(
        "release_category_facts",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("result_fact_id", sa.String(240), primary_key=True),
        sa.Column("category_key", sa.String(300), primary_key=True),
        sa.Column("category_code", sa.String(96), nullable=False),
        sa.Column("category_name", sa.Text(), nullable=False),
        sa.Column("category_kind", sa.String(48), nullable=False),
        sa.Column("votes", sa.Integer()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug", "result_fact_id"],
            [
                "release_result_facts.release_id",
                "release_result_facts.election_slug",
                "release_result_facts.id",
            ],
        ),
    )
    op.create_table(
        "comparison_crosswalks",
        sa.Column("current_release_id", sa.String(128), primary_key=True),
        sa.Column("current_election_slug", sa.String(160), primary_key=True),
        sa.Column("baseline_release_id", sa.String(128), primary_key=True),
        sa.Column("baseline_election_slug", sa.String(160), primary_key=True),
        sa.Column("current_geography_id", sa.String(200), primary_key=True),
        sa.Column("baseline_geography_id", sa.String(200), nullable=False),
        sa.Column("grain", sa.String(32), nullable=False),
        sa.Column("comparison_key", sa.String(200), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
    )
    op.create_index(
        "ix_exposure_public", "release_exposures", ["access_scope", "release_id", "election_slug"]
    )
    op.create_index(
        "ix_geo_children",
        "release_geographies",
        ["release_id", "election_slug", "parent_id", "level", "code"],
    )
    op.create_index(
        "ix_mesa_scope",
        "release_mesas",
        ["release_id", "election_slug", "municipality_id", "polling_place_id", "id"],
    )
    op.create_index(
        "ix_result_page",
        "release_result_facts",
        ["release_id", "election_slug", "geography_level", "geography_id", "source_id", "id"],
    )
    op.create_index(
        "ix_result_mesa",
        "release_result_facts",
        ["release_id", "election_slug", "mesa_id", "source_id", "id"],
    )
    op.create_index(
        "ix_category_filter",
        "release_category_facts",
        ["release_id", "election_slug", "category_key", "result_fact_id"],
    )


def downgrade() -> None:
    for name in (
        "ix_category_filter",
        "ix_result_mesa",
        "ix_result_page",
        "ix_mesa_scope",
        "ix_geo_children",
        "ix_exposure_public",
    ):
        op.drop_index(name)
    for name in (
        "comparison_crosswalks",
        "release_category_facts",
        "release_result_facts",
        "release_sources",
        "release_mesas",
        "release_geographies",
        "release_exposures",
        "release_elections",
    ):
        op.drop_table(name)
