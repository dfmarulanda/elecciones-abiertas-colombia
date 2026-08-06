"""Preliminary exposure: a second door that cannot become the certified one.

The certified gate is ``access_scope='public' AND approved_at IS NOT NULL AND
releases.status='published'``. It exists so uncertified numbers can never be
served as certified results, and not one character of it changes here.

A preliminary pre-count is real data that will never satisfy that gate: it is a
``candidate`` release by construction. Rather than weaken the predicate, this
adds a structurally disjoint third scope. The two doors are mutually exclusive
in BOTH directions, enforced by CHECK constraints rather than by application
discipline, so a row cannot be both and no code path can make it so:

  * a ``preliminary`` exposure must carry ``preliminary_approved_at`` and both
    caveat strings, and must have ``approved_at IS NULL``;
  * a ``public`` (certified) exposure must have ``preliminary_approved_at IS
    NULL``.

The bilingual caveat is stored on the row, not hardcoded in the API, so the
text that labels the data travels with the grant that authorised it.

Revision ID: 20260806_01
Revises: 20260804_05
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from alembic import op

revision = "20260806_01"
down_revision = "20260804_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "release_exposures",
        sa.Column("preliminary_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "release_exposures", sa.Column("preliminary_caveat_es", sa.Text(), nullable=True)
    )
    op.add_column(
        "release_exposures", sa.Column("preliminary_caveat_en", sa.Text(), nullable=True)
    )

    op.create_check_constraint(
        "ck_exposure_scope",
        "release_exposures",
        "access_scope IN ('internal','public','preliminary')",
    )
    # A preliminary grant can never carry a certified approval, and must carry
    # the caveat text that labels every response it authorises.
    op.create_check_constraint(
        "ck_preliminary_is_not_certified",
        "release_exposures",
        """
        access_scope <> 'preliminary' OR (
            preliminary_approved_at IS NOT NULL
            AND approved_at IS NULL
            AND length(coalesce(preliminary_caveat_es,'')) > 0
            AND length(coalesce(preliminary_caveat_en,'')) > 0
        )
        """,
    )
    # And a certified grant can never carry a preliminary approval.
    op.create_check_constraint(
        "ck_certified_is_not_preliminary",
        "release_exposures",
        "access_scope <> 'public' OR preliminary_approved_at IS NULL",
    )

    op.create_index(
        "ix_exposure_preliminary",
        "release_exposures",
        ["access_scope", "release_id", "election_slug"],
    )

    # Extend the transition guard. Every exposure still ENTERS as ``internal``
    # (validate_release_exposure, migration 04), and the certified transition is
    # reproduced here character for character. The only addition is a second
    # permitted destination.
    #
    # Note what stays impossible: both permitted transitions originate at
    # ``internal``, so ``preliminary -> public`` has no path. Preliminary data
    # can never be promoted into the certified scope; it would have to be loaded
    # again as a new, genuinely published release.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_release_exposure_update() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF OLD.release_id IS DISTINCT FROM NEW.release_id
             OR OLD.election_slug IS DISTINCT FROM NEW.election_slug
             OR OLD.manifest_hash IS DISTINCT FROM NEW.manifest_hash THEN
            RAISE EXCEPTION 'release exposure identity and manifest hash are immutable';
          END IF;
          IF OLD.access_scope IS DISTINCT FROM NEW.access_scope
             AND NOT (
               OLD.access_scope='internal' AND NEW.access_scope='public'
               AND NEW.approved_at IS NOT NULL
             )
             AND NOT (
               OLD.access_scope='internal' AND NEW.access_scope='preliminary'
               AND NEW.preliminary_approved_at IS NOT NULL
               AND NEW.approved_at IS NULL
             ) THEN
            RAISE EXCEPTION 'release exposure scope may only transition internal to public or internal to preliminary';
          END IF;
          IF OLD.access_scope IS NOT DISTINCT FROM NEW.access_scope
             AND OLD.approved_at IS DISTINCT FROM NEW.approved_at THEN
            RAISE EXCEPTION 'release exposure approval changes require publication';
          END IF;
          IF OLD.access_scope IS NOT DISTINCT FROM NEW.access_scope
             AND OLD.preliminary_approved_at IS DISTINCT FROM NEW.preliminary_approved_at THEN
            RAISE EXCEPTION 'release exposure approval changes require publication';
          END IF;
          RETURN NEW;
        END $$
        """
    )


def downgrade() -> None:
    # Restore the certified-only transition guard exactly as migration 04 wrote it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_release_exposure_update() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF OLD.release_id IS DISTINCT FROM NEW.release_id
             OR OLD.election_slug IS DISTINCT FROM NEW.election_slug
             OR OLD.manifest_hash IS DISTINCT FROM NEW.manifest_hash THEN
            RAISE EXCEPTION 'release exposure identity and manifest hash are immutable';
          END IF;
          IF OLD.access_scope IS DISTINCT FROM NEW.access_scope
             AND NOT (
               OLD.access_scope='internal' AND NEW.access_scope='public'
               AND NEW.approved_at IS NOT NULL
             ) THEN
            RAISE EXCEPTION 'release exposure scope may only transition internal to public';
          END IF;
          IF OLD.access_scope IS NOT DISTINCT FROM NEW.access_scope
             AND OLD.approved_at IS DISTINCT FROM NEW.approved_at THEN
            RAISE EXCEPTION 'release exposure approval changes require publication';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.drop_index("ix_exposure_preliminary", table_name="release_exposures")
    op.drop_constraint("ck_certified_is_not_preliminary", "release_exposures", type_="check")
    op.drop_constraint("ck_preliminary_is_not_certified", "release_exposures", type_="check")
    op.drop_constraint("ck_exposure_scope", "release_exposures", type_="check")
    op.drop_column("release_exposures", "preliminary_caveat_en")
    op.drop_column("release_exposures", "preliminary_caveat_es")
    op.drop_column("release_exposures", "preliminary_approved_at")
