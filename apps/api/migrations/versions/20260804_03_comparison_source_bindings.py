"""Bind approved semantic comparisons to exact source layers."""

import sqlalchemy as sa
from alembic import op

revision = "20260804_03"
down_revision = "20260804_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "semantic_category_crosswalks",
        sa.Column("current_source_id", sa.String(200), nullable=True),
    )
    op.add_column(
        "semantic_category_crosswalks",
        sa.Column("baseline_source_id", sa.String(200), nullable=True),
    )
    op.create_foreign_key(
        "fk_semantic_current_source",
        "semantic_category_crosswalks",
        "release_sources",
        ["current_release_id", "current_election_slug", "current_source_id"],
        ["release_id", "election_slug", "id"],
    )
    op.create_foreign_key(
        "fk_semantic_baseline_source",
        "semantic_category_crosswalks",
        "release_sources",
        ["baseline_release_id", "baseline_election_slug", "baseline_source_id"],
        ["release_id", "election_slug", "id"],
    )
    op.create_foreign_key(
        "fk_comparison_current_election",
        "comparison_crosswalks",
        "release_elections",
        ["current_release_id", "current_election_slug"],
        ["release_id", "election_slug"],
    )
    op.create_foreign_key(
        "fk_comparison_baseline_election",
        "comparison_crosswalks",
        "release_elections",
        ["baseline_release_id", "baseline_election_slug"],
        ["release_id", "election_slug"],
    )
    # Existing unbound rows intentionally remain unusable until explicitly re-approved.
    op.create_check_constraint(
        "ck_semantic_approved_source_binding",
        "semantic_category_crosswalks",
        "approved_at IS NULL OR (current_source_id IS NOT NULL AND baseline_source_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_comparison_baseline_election", "comparison_crosswalks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_comparison_current_election", "comparison_crosswalks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_semantic_baseline_source", "semantic_category_crosswalks", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_semantic_current_source", "semantic_category_crosswalks", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_semantic_approved_source_binding", "semantic_category_crosswalks", type_="check"
    )
    op.drop_column("semantic_category_crosswalks", "baseline_source_id")
    op.drop_column("semantic_category_crosswalks", "current_source_id")
