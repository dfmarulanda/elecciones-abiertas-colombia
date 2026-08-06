"""Indexes, summary storage and per-fact provenance for a standard release.

A 140,695-geography / 140,695-fact release makes three existing gaps expensive
or wrong:

  * ``ix_result_page`` leads with ``geography_level``, so neither a per-geography
    join nor ``?geography_id=`` can use it — every drill-down click would scan
    the whole fact table. ``ix_result_geo`` fixes that and is the highest-impact
    index here.
  * ``canonical_path LIKE :path || '/%'`` (the subtree filter) is unindexed.
  * ``ix_mesa_scope`` leads with ``municipality_id``, so listing a department's
    mesas has no index.

``release_summaries`` stores the pipeline-computed completion/coverage/
reconciliation blocks. They are NOT derivable from the loaded rows — completion
reports 122,017 reported against 122,020 installed, and reconciliation is
``blocked`` with 3 exceptions. Recomputing them from rows would quietly turn a
blocked reconciliation into a passing one, so the values are copied verbatim
and served as recorded.

``fact_content_hash`` / ``fact_retrieved_at`` keep per-mesa verifiability while
list responses hoist provenance to the source: all 136,459 leaf facts have
distinct hashes, so collapsing them onto four source rows would lose the
per-mesa evidence trail.

Revision ID: 20260806_02
Revises: 20260806_01
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_02"
down_revision = "20260806_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_result_geo",
        "release_result_facts",
        ["release_id", "election_slug", "geography_id"],
    )
    op.create_index(
        "ix_geo_level_code",
        "release_geographies",
        ["release_id", "election_slug", "level", "code"],
    )
    op.create_index(
        "ix_mesa_department",
        "release_mesas",
        ["release_id", "election_slug", "department_id", "polling_place_id", "id"],
    )
    # text_pattern_ops so a left-anchored LIKE on the subtree prefix is indexable.
    op.execute(
        "CREATE INDEX ix_geo_path ON release_geographies "
        "(release_id, election_slug, canonical_path text_pattern_ops)"
    )

    op.add_column(
        "release_result_facts",
        sa.Column("fact_content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "release_result_facts",
        sa.Column("fact_retrieved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "release_summaries",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("release_class", sa.String(32), nullable=False),
        sa.Column("completion", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.JSON(), nullable=False),
        sa.Column("geographic_collection_coverage", sa.JSON(), nullable=True),
        sa.Column("reconciliation", sa.JSON(), nullable=False),
        sa.Column("turnout", sa.Float(), nullable=True),
        sa.Column("preview_caveat_es", sa.Text(), nullable=True),
        sa.Column("preview_caveat_en", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
    )


def downgrade() -> None:
    op.drop_table("release_summaries")
    op.drop_column("release_result_facts", "fact_retrieved_at")
    op.drop_column("release_result_facts", "fact_content_hash")
    op.execute("DROP INDEX IF EXISTS ix_geo_path")
    op.drop_index("ix_mesa_department", table_name="release_mesas")
    op.drop_index("ix_geo_level_code", table_name="release_geographies")
    op.drop_index("ix_result_geo", table_name="release_result_facts")
