"""Compact read model for large context-only historical releases.

Revision ID: 20260804_05
Revises: 20260804_04
Create Date: 2026-08-04
"""

import sqlalchemy as sa
from alembic import op

revision = "20260804_05"
down_revision = "20260804_04"
branch_labels = None
depends_on = None

_METRICS = (
    "registered_electors",
    "voters",
    "valid_votes",
    "blank_votes",
    "null_votes",
    "unmarked_votes",
)
_COMPACT_TABLES = (
    "context_geographies",
    "context_sources",
    "context_result_facts",
    "context_categories",
    "context_category_facts",
)


def _metric_check() -> str:
    checks = []
    for offset, metric in enumerate(_METRICS):
        shift = offset * 2
        checks.append(
            f"((metrics_status >> {shift}) & 3) = 0 AND {metric} IS NOT NULL "
            f"OR ((metrics_status >> {shift}) & 3) <> 0 AND {metric} IS NULL"
        )
        checks.append(f"{metric} IS NULL OR {metric} >= 0")
    return " AND ".join(f"({check})" for check in checks)


def upgrade() -> None:
    op.create_table(
        "context_release_scopes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("release_id", sa.String(128), nullable=False),
        sa.Column("election_slug", sa.String(160), nullable=False),
        sa.Column("geography_count", sa.BigInteger()),
        sa.Column("result_fact_count", sa.BigInteger()),
        sa.Column("category_fact_count", sa.BigInteger()),
        sa.Column("semantic_key_hash", sa.String(64)),
        sa.Column("content_row_hash", sa.String(64)),
        sa.CheckConstraint(
            "geography_count IS NULL OR geography_count >= 0",
            name="ck_context_scope_geography_count",
        ),
        sa.CheckConstraint(
            "result_fact_count IS NULL OR result_fact_count >= 0",
            name="ck_context_scope_result_fact_count",
        ),
        sa.CheckConstraint(
            "category_fact_count IS NULL OR category_fact_count >= 0",
            name="ck_context_scope_category_fact_count",
        ),
        sa.ForeignKeyConstraint(
            ["release_id", "election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "release_id", "election_slug", name="uq_context_release_scope"
        ),
    )
    op.create_table(
        "context_geographies",
        sa.Column("scope_id", sa.BigInteger(), primary_key=True),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.String(96), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("tree_left", sa.Integer(), nullable=False),
        sa.Column("tree_right", sa.Integer(), nullable=False),
        sa.CheckConstraint("level BETWEEN 0 AND 5", name="ck_context_geo_level"),
        sa.CheckConstraint(
            "tree_left > 0 AND tree_right > tree_left",
            name="ck_context_geo_tree_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["context_release_scopes.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["scope_id", "parent_id"],
            ["context_geographies.scope_id", "context_geographies.id"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("scope_id", "external_id", name="uq_context_geo_external"),
    )
    op.create_table(
        "context_sources",
        sa.Column("scope_id", sa.BigInteger(), primary_key=True),
        sa.Column("ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("source_id", sa.String(200), nullable=False),
        sa.CheckConstraint("ordinal > 0", name="ck_context_source_ordinal"),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["context_release_scopes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("scope_id", "source_id", name="uq_context_source_external"),
    )
    op.create_table(
        "context_result_facts",
        sa.Column("scope_id", sa.BigInteger(), primary_key=True),
        sa.Column("geography_id", sa.Integer(), primary_key=True),
        sa.Column("source_ordinal", sa.SmallInteger(), primary_key=True),
        sa.Column("metrics_status", sa.SmallInteger(), nullable=False),
        *[sa.Column(metric, sa.BigInteger()) for metric in _METRICS],
        sa.CheckConstraint(
            "metrics_status BETWEEN 0 AND 4095", name="ck_context_fact_metric_mask"
        ),
        sa.CheckConstraint(_metric_check(), name="ck_context_fact_metric_values"),
        sa.ForeignKeyConstraint(
            ["scope_id", "geography_id"],
            ["context_geographies.scope_id", "context_geographies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id", "source_ordinal"],
            ["context_sources.scope_id", "context_sources.ordinal"],
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "context_categories",
        sa.Column("scope_id", sa.BigInteger(), primary_key=True),
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("category_key", sa.String(300), nullable=False),
        sa.Column("category_code", sa.String(96), nullable=False),
        sa.Column("category_name", sa.Text(), nullable=False),
        sa.Column("category_kind", sa.String(48), nullable=False),
        sa.CheckConstraint("id > 0", name="ck_context_category_id"),
        sa.ForeignKeyConstraint(
            ["scope_id"], ["context_release_scopes.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "scope_id", "category_key", name="uq_context_category_external"
        ),
    )
    op.create_table(
        "context_category_facts",
        sa.Column("scope_id", sa.BigInteger(), nullable=False),
        sa.Column("geography_id", sa.Integer(), nullable=False),
        sa.Column("source_ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("category_id", sa.SmallInteger(), nullable=False),
        sa.Column("votes", sa.BigInteger()),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("status BETWEEN 0 AND 3", name="ck_context_category_status"),
        sa.CheckConstraint(
            "(status = 0 AND votes IS NOT NULL AND votes >= 0) "
            "OR (status <> 0 AND votes IS NULL)",
            name="ck_context_category_value",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id", "geography_id", "source_ordinal"],
            [
                "context_result_facts.scope_id",
                "context_result_facts.geography_id",
                "context_result_facts.source_ordinal",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id", "category_id"],
            ["context_categories.scope_id", "context_categories.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_context_geo_children",
        "context_geographies",
        ["scope_id", "parent_id"],
    )
    op.create_index(
        "ix_context_geo_order",
        "context_geographies",
        ["scope_id", "level", "external_id"],
    )
    # Rollup category rows are copied in immutable geography order.  A compact
    # BRIN keeps exact mesa/category reads bounded without an 85 MB duplicate
    # B-tree; duplicate identities are checked once by the exposure gate below.
    op.create_index(
        "ix_context_category_geo_brin",
        "context_category_facts",
        ["scope_id", "geography_id"],
        postgresql_using="brin",
        postgresql_with={"pages_per_range": 16},
    )

    # Advisory transaction locks serialize compact writes with exposure.  This
    # retains immutable publication without executing a PL/pgSQL trigger once
    # per one of the ~1.3M category rows.
    op.execute(
        """
        CREATE FUNCTION lock_context_release_scope(p_scope_id bigint) RETURNS void
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected record;
        BEGIN
          SELECT release_id,election_slug INTO STRICT selected
          FROM public.context_release_scopes WHERE id=p_scope_id;
          PERFORM pg_advisory_xact_lock(
            hashtextextended(selected.release_id || chr(31) || selected.election_slug, 0)
          );
          PERFORM public.lock_release_election_scope(
            selected.release_id,selected.election_slug
          );
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_context_insert() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected_scope bigint;
        BEGIN
          FOR selected_scope IN SELECT DISTINCT scope_id FROM new_rows ORDER BY scope_id
          LOOP
            PERFORM public.lock_context_release_scope(selected_scope);
            IF EXISTS (
              SELECT 1 FROM public.context_release_scopes c
              JOIN public.release_exposures x USING(release_id,election_slug)
              WHERE c.id=selected_scope
            ) THEN RAISE EXCEPTION 'exposed context release rows are immutable'; END IF;
          END LOOP;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_context_update() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected_scope bigint;
        BEGIN
          FOR selected_scope IN
            SELECT scope_id FROM old_rows UNION SELECT scope_id FROM new_rows ORDER BY 1
          LOOP
            PERFORM public.lock_context_release_scope(selected_scope);
            IF EXISTS (
              SELECT 1 FROM public.context_release_scopes c
              JOIN public.release_exposures x USING(release_id,election_slug)
              WHERE c.id=selected_scope
            ) THEN RAISE EXCEPTION 'exposed context release rows are immutable'; END IF;
          END LOOP;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_context_delete() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected_scope bigint;
        BEGIN
          FOR selected_scope IN SELECT DISTINCT scope_id FROM old_rows ORDER BY scope_id
          LOOP
            PERFORM public.lock_context_release_scope(selected_scope);
            IF EXISTS (
              SELECT 1 FROM public.context_release_scopes c
              JOIN public.release_exposures x USING(release_id,election_slug)
              WHERE c.id=selected_scope
            ) THEN RAISE EXCEPTION 'exposed context release rows are immutable'; END IF;
          END LOOP;
          RETURN NULL;
        END $$
        """
    )
    for table in _COMPACT_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_immutable_insert AFTER INSERT ON {table} "
            "REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_context_insert()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable_update AFTER UPDATE ON {table} "
            "REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_context_update()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable_delete AFTER DELETE ON {table} "
            "REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_context_delete()"
        )
    op.execute(
        """
        CREATE FUNCTION guard_context_scope_write() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected record;
        BEGIN
          IF TG_OP='DELETE' THEN selected := OLD; ELSE selected := NEW; END IF;
          PERFORM pg_advisory_xact_lock(
            hashtextextended(selected.release_id || chr(31) || selected.election_slug, 0)
          );
          PERFORM public.lock_release_election_scope(
            selected.release_id,selected.election_slug
          );
          IF EXISTS (
            SELECT 1 FROM public.release_exposures
            WHERE release_id=selected.release_id
              AND election_slug=selected.election_slug
          ) THEN RAISE EXCEPTION 'exposed context release scope is immutable'; END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER context_release_scopes_guard_write "
        "BEFORE UPDATE OR DELETE ON context_release_scopes FOR EACH ROW "
        "EXECUTE FUNCTION guard_context_scope_write()"
    )
    op.execute(
        """
        CREATE FUNCTION lock_context_exposure() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          PERFORM pg_advisory_xact_lock(
            hashtextextended(NEW.release_id || chr(31) || NEW.election_slug, 0)
          );
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER release_exposure_context_lock "
        "BEFORE INSERT OR UPDATE ON release_exposures FOR EACH ROW "
        "EXECUTE FUNCTION lock_context_exposure()"
    )
    op.execute(
        """
        CREATE FUNCTION validate_context_release_exposure() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE selected record;
        DECLARE context_scope_id bigint;
        BEGIN
          FOR selected IN SELECT DISTINCT release_id,election_slug FROM new_rows
          LOOP
            SELECT id INTO context_scope_id FROM public.context_release_scopes
            WHERE release_id=selected.release_id AND election_slug=selected.election_slug;
            IF context_scope_id IS NULL THEN CONTINUE; END IF;
            IF NOT EXISTS (
              SELECT 1 FROM public.releases r
              WHERE r.id=selected.release_id
                AND r.manifest->>'release_class'='context_only'
                AND COALESCE((r.manifest->>'statistical_validation_passed')::boolean,false)=false
            ) THEN
              RAISE EXCEPTION
                'compact context data requires a non-statistical context_only manifest';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.release_sources s
              WHERE s.release_id=selected.release_id
                AND s.election_slug=selected.election_slug
                AND (s.source_type<>'contextual_baseline' OR s.legal_status<>'context_only')
            ) OR EXISTS (
              SELECT 1 FROM public.context_sources cs
              LEFT JOIN public.context_release_scopes c ON c.id=cs.scope_id
              LEFT JOIN public.release_sources s
                ON s.release_id=c.release_id AND s.election_slug=c.election_slug
               AND s.id=cs.source_id
              WHERE cs.scope_id=context_scope_id AND s.id IS NULL
            ) THEN
              RAISE EXCEPTION 'compact context source lineage is invalid';
            END IF;
            IF (SELECT count(*) FROM public.context_geographies
                WHERE scope_id=context_scope_id AND level=0 AND parent_id IS NULL)<>1
               OR EXISTS (
                 SELECT 1 FROM public.context_geographies child
                 LEFT JOIN public.context_geographies parent
                   ON parent.scope_id=child.scope_id AND parent.id=child.parent_id
                 WHERE child.scope_id=context_scope_id AND (
                   (child.level=0 AND child.parent_id IS NOT NULL)
                   OR (child.level>0 AND (
                     parent.id IS NULL OR parent.level<>child.level-1
                     OR NOT (
                       child.tree_left>parent.tree_left
                       AND child.tree_right<parent.tree_right
                     )
                   ))
                 )
               ) THEN
              RAISE EXCEPTION 'compact context geography hierarchy is invalid';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.release_result_facts
              WHERE release_id=selected.release_id AND election_slug=selected.election_slug
            ) OR EXISTS (
              SELECT 1 FROM public.release_category_facts
              WHERE release_id=selected.release_id AND election_slug=selected.election_slug
            ) THEN
              RAISE EXCEPTION 'one release scope cannot mix compact and legacy facts';
            END IF;
            IF EXISTS (
              SELECT 1 FROM public.context_release_scopes c
              WHERE c.id=context_scope_id AND (
                c.geography_count IS NULL OR c.result_fact_count IS NULL
                OR c.category_fact_count IS NULL
                OR c.semantic_key_hash !~ '^[0-9a-f]{64}$'
                OR c.content_row_hash !~ '^[0-9a-f]{64}$'
                OR c.geography_count<>(
                  SELECT count(*) FROM public.context_geographies g
                  WHERE g.scope_id=context_scope_id
                )
                OR c.result_fact_count<>(
                  SELECT count(*) FROM public.context_result_facts f
                  WHERE f.scope_id=context_scope_id
                )
                OR c.category_fact_count<>(
                  SELECT count(*) FROM public.context_category_facts cf
                  WHERE cf.scope_id=context_scope_id
                )
              )
            ) THEN
              RAISE EXCEPTION 'compact context load audit is absent or inconsistent';
            END IF;
          END LOOP;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER release_exposure_validate_context_insert "
        "AFTER INSERT ON release_exposures REFERENCING NEW TABLE AS new_rows "
        "FOR EACH STATEMENT EXECUTE FUNCTION validate_context_release_exposure()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER release_exposure_validate_context_insert ON release_exposures"
    )
    op.execute("DROP FUNCTION validate_context_release_exposure()")
    op.execute("DROP TRIGGER release_exposure_context_lock ON release_exposures")
    op.execute("DROP FUNCTION lock_context_exposure()")
    op.execute("DROP TRIGGER context_release_scopes_guard_write ON context_release_scopes")
    op.execute("DROP FUNCTION guard_context_scope_write()")
    for table in reversed(_COMPACT_TABLES):
        for operation in ("delete", "update", "insert"):
            op.execute(f"DROP TRIGGER {table}_immutable_{operation} ON {table}")
    op.execute("DROP FUNCTION reject_exposed_context_delete()")
    op.execute("DROP FUNCTION reject_exposed_context_update()")
    op.execute("DROP FUNCTION reject_exposed_context_insert()")
    op.execute("DROP FUNCTION lock_context_release_scope(bigint)")
    for name, table in (
        ("ix_context_category_geo_brin", "context_category_facts"),
        ("ix_context_geo_order", "context_geographies"),
        ("ix_context_geo_children", "context_geographies"),
    ):
        op.drop_index(name, table_name=table)
    for table in (
        "context_category_facts",
        "context_categories",
        "context_result_facts",
        "context_sources",
        "context_geographies",
        "context_release_scopes",
    ):
        op.drop_table(table)
