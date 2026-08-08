"""Store immutable candidate and ballot metadata for normalized releases.

Revision ID: 20260808_01
Revises: 20260806_02
Create Date: 2026-08-08
"""

import sqlalchemy as sa
from alembic import op

revision = "20260808_01"
down_revision = "20260806_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "release_candidates",
        sa.Column("release_id", sa.String(128), primary_key=True),
        sa.Column("election_slug", sa.String(160), primary_key=True),
        sa.Column("id", sa.String(160), primary_key=True),
        sa.Column("ballot_number", sa.Integer(), nullable=False),
        sa.Column("name_es", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("short_name_es", sa.Text(), nullable=False),
        sa.Column("short_name_en", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
        sa.UniqueConstraint(
            "release_id",
            "election_slug",
            "ballot_number",
            name="uq_release_candidate_ballot",
        ),
    )
    op.execute(
        """
        INSERT INTO release_candidates
          (release_id,election_slug,id,ballot_number,name_es,name_en,short_name_es,short_name_en)
        SELECT e.release_id,e.election_slug,c.id,c.ballot,c.name_es,c.name_en,c.short_es,c.short_en
        FROM release_elections e
        CROSS JOIN (VALUES
          ('ivan-cepeda-aida-quilcue',1,
           'Iván Cepeda Castro / Aida Marina Quilcué Vivas',
           'Iván Cepeda Castro / Aida Marina Quilcué Vivas',
           'Cepeda / Quilcué','Cepeda / Quilcué'),
          ('abelardo-de-la-espriella-jose-manuel-restrepo',2,
           'Abelardo de la Espriella / José Manuel Restrepo',
           'Abelardo de la Espriella / José Manuel Restrepo',
           'De la Espriella / Restrepo','De la Espriella / Restrepo')
        ) AS c(id,ballot,name_es,name_en,short_es,short_en)
        WHERE e.release_id='candidate-2026-r2-dacb28aa766eec87'
          AND e.election_slug='presidencia-2026-segunda-vuelta'
        """
    )
    for operation, references in (
        ("insert", "REFERENCING NEW TABLE AS new_rows"),
        ("update", "REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows"),
        ("delete", "REFERENCING OLD TABLE AS old_rows"),
    ):
        op.execute(
            "CREATE TRIGGER release_candidates_scope_lock_before_"
            f"{operation} BEFORE {operation.upper()} ON release_candidates FOR EACH ROW "
            "EXECUTE FUNCTION lock_release_election_scope_before_write()"
        )
        op.execute(
            f"CREATE TRIGGER release_candidates_immutable_{operation} "
            f"AFTER {operation.upper()} ON release_candidates {references} FOR EACH STATEMENT "
            f"EXECUTE FUNCTION reject_exposed_release_{operation}()"
        )


def downgrade() -> None:
    op.drop_table("release_candidates")
