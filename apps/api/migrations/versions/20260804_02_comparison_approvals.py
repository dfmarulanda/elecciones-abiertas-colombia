"""Require explicit semantic approval for historical comparisons.

This is intentionally additive: existing geography mappings remain auditable,
but cannot authorize public comparisons until explicitly approved.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_02"
down_revision = "20260804_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comparison_crosswalks", sa.Column("approved_at", sa.DateTime(timezone=True))
    )
    op.create_table(
        "semantic_category_crosswalks",
        sa.Column("current_release_id", sa.String(128), primary_key=True),
        sa.Column("current_election_slug", sa.String(160), primary_key=True),
        sa.Column("baseline_release_id", sa.String(128), primary_key=True),
        sa.Column("baseline_election_slug", sa.String(160), primary_key=True),
        sa.Column("comparison_key", sa.String(200), primary_key=True),
        sa.Column("current_category_key", sa.String(300), primary_key=True),
        sa.Column("baseline_category_key", sa.String(300), nullable=False),
        sa.Column("category_kind", sa.String(48), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_semantic_crosswalk_lookup",
        "semantic_category_crosswalks",
        [
            "current_release_id",
            "current_election_slug",
            "baseline_release_id",
            "baseline_election_slug",
            "comparison_key",
            "current_category_key",
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_crosswalk_lookup", table_name="semantic_category_crosswalks")
    op.drop_table("semantic_category_crosswalks")
    op.drop_column("comparison_crosswalks", "approved_at")
