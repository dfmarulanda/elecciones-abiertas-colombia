"""Enforce scalable, release-gated integrity for immutable bulk loads.

High-volume text-composite relationships are validated set-wise by the loader
before exposure.  PostgreSQL retains direct election ownership for every row
and rejects any mutation after the internal exposure gate is installed.
"""

from alembic import op

revision = "20260804_04"
down_revision = "20260804_03"
branch_labels = None
depends_on = None

_DROPPED_FKS = (
    (
        "release_geographies",
        "release_geographies_release_id_election_slug_parent_id_fkey",
    ),
    ("release_mesas", "release_mesas_release_id_election_slug_id_fkey"),
    ("release_mesas", "release_mesas_release_id_election_slug_polling_place_id_fkey"),
    ("release_mesas", "release_mesas_release_id_election_slug_municipality_id_fkey"),
    ("release_mesas", "release_mesas_release_id_election_slug_department_id_fkey"),
    (
        "release_result_facts",
        "release_result_facts_release_id_election_slug_geography_id_fkey",
    ),
    (
        "release_result_facts",
        "release_result_facts_release_id_election_slug_mesa_id_fkey",
    ),
    (
        "release_result_facts",
        "release_result_facts_release_id_election_slug_source_id_fkey",
    ),
    (
        "release_category_facts",
        "release_category_facts_release_id_election_slug_result_fac_fkey",
    ),
)

_IMMUTABLE_TABLES = (
    "release_elections",
    "release_sources",
    "release_geographies",
    "release_mesas",
    "release_result_facts",
    "release_category_facts",
)


def upgrade() -> None:
    for table, constraint in _DROPPED_FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
    op.create_foreign_key(
        "fk_release_result_facts_election",
        "release_result_facts",
        "release_elections",
        ["release_id", "election_slug"],
        ["release_id", "election_slug"],
        deferrable=True,
        initially="IMMEDIATE",
    )
    op.create_foreign_key(
        "fk_release_category_facts_election",
        "release_category_facts",
        "release_elections",
        ["release_id", "election_slug"],
        ["release_id", "election_slug"],
        deferrable=True,
        initially="IMMEDIATE",
    )
    for table, constraint in (
        ("release_geographies", "release_geographies_release_id_election_slug_fkey"),
        ("release_mesas", "release_mesas_release_id_election_slug_fkey"),
    ):
        op.execute(
            f'ALTER TABLE "{table}" ALTER CONSTRAINT "{constraint}" DEFERRABLE INITIALLY IMMEDIATE'
        )

    op.execute(
        """
        CREATE FUNCTION lock_release_election_scope(
          p_release_id text, p_election_slug text
        ) RETURNS void
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          PERFORM 1 FROM public.release_elections e
          WHERE e.release_id=p_release_id AND e.election_slug=p_election_slug
          FOR UPDATE;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_release_insert() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE locked_scope record;
        BEGIN
          FOR locked_scope IN
            SELECT DISTINCT n.release_id,n.election_slug
            FROM new_rows n ORDER BY n.release_id,n.election_slug
          LOOP
            PERFORM public.lock_release_election_scope(
              locked_scope.release_id,locked_scope.election_slug
            );
          END LOOP;
          IF EXISTS (
            SELECT 1 FROM new_rows n JOIN public.release_exposures e
              ON e.release_id=n.release_id AND e.election_slug=n.election_slug
          ) THEN
            RAISE EXCEPTION 'exposed release rows are immutable';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    # Take the scope lock before the foreign-key checks that run after a row
    # write.  `FOR UPDATE` then excludes a concurrent exposure's FK
    # `KEY SHARE` lock as well, so the exposure cannot overtake a writer that
    # was already waiting for this scope.
    op.execute(
        """
        CREATE FUNCTION lock_release_election_scope_before_write() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            PERFORM public.lock_release_election_scope(OLD.release_id,OLD.election_slug);
            RETURN OLD;
          ELSIF TG_OP='INSERT' THEN
            PERFORM public.lock_release_election_scope(NEW.release_id,NEW.election_slug);
            RETURN NEW;
          END IF;

          IF (OLD.release_id,OLD.election_slug) <= (NEW.release_id,NEW.election_slug) THEN
            PERFORM public.lock_release_election_scope(OLD.release_id,OLD.election_slug);
            IF (OLD.release_id,OLD.election_slug) IS DISTINCT FROM
               (NEW.release_id,NEW.election_slug) THEN
              PERFORM public.lock_release_election_scope(NEW.release_id,NEW.election_slug);
            END IF;
          ELSE
            PERFORM public.lock_release_election_scope(NEW.release_id,NEW.election_slug);
            PERFORM public.lock_release_election_scope(OLD.release_id,OLD.election_slug);
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_release_update() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE locked_scope record;
        BEGIN
          FOR locked_scope IN
            SELECT scope.release_id,scope.election_slug
            FROM (
              SELECT n.release_id,n.election_slug FROM old_rows n
              UNION
              SELECT n.release_id,n.election_slug FROM new_rows n
            ) scope
            ORDER BY scope.release_id,scope.election_slug
          LOOP
            PERFORM public.lock_release_election_scope(
              locked_scope.release_id,locked_scope.election_slug
            );
          END LOOP;
          IF EXISTS (
            SELECT 1 FROM old_rows n JOIN public.release_exposures e
              ON e.release_id=n.release_id AND e.election_slug=n.election_slug
            UNION ALL
            SELECT 1 FROM new_rows n JOIN public.release_exposures e
              ON e.release_id=n.release_id AND e.election_slug=n.election_slug
          ) THEN
            RAISE EXCEPTION 'exposed release rows are immutable';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_release_delete() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE locked_scope record;
        BEGIN
          FOR locked_scope IN
            SELECT DISTINCT n.release_id,n.election_slug
            FROM old_rows n ORDER BY n.release_id,n.election_slug
          LOOP
            PERFORM public.lock_release_election_scope(
              locked_scope.release_id,locked_scope.election_slug
            );
          END LOOP;
          IF EXISTS (
            SELECT 1 FROM old_rows n JOIN public.release_exposures e
              ON e.release_id=n.release_id AND e.election_slug=n.election_slug
          ) THEN
            RAISE EXCEPTION 'exposed release rows are immutable';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    for table in _IMMUTABLE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_scope_lock_before_write "
            f"BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION lock_release_election_scope_before_write()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable_insert AFTER INSERT ON {table} "
            "REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_release_insert()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable_update AFTER UPDATE ON {table} "
            "REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_release_update()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable_delete AFTER DELETE ON {table} "
            "REFERENCING OLD TABLE AS old_rows FOR EACH STATEMENT "
            "EXECUTE FUNCTION reject_exposed_release_delete()"
        )
    # The exposure row is the database gate, not merely a loader convention.
    # Re-check the relationships whose per-row text FKs were removed before a
    # release/election can become readable, then make the validated rows
    # immutable through the statement triggers above.
    op.execute(
        """
        CREATE FUNCTION validate_release_exposure() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE locked_scope record;
        BEGIN
          IF EXISTS (
            SELECT 1 FROM new_rows n
            WHERE n.access_scope<>'internal' OR n.approved_at IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'release exposure must enter through the internal gate';
          END IF;
          FOR locked_scope IN
            SELECT DISTINCT n.release_id,n.election_slug
            FROM new_rows n ORDER BY n.release_id,n.election_slug
          LOOP
            PERFORM 1 FROM public.releases r
            WHERE r.id=locked_scope.release_id FOR NO KEY UPDATE;
            PERFORM public.lock_release_election_scope(
              locked_scope.release_id,locked_scope.election_slug
            );

            IF EXISTS (
              SELECT 1 FROM public.release_geographies g
              WHERE g.release_id=locked_scope.release_id
                AND g.election_slug=locked_scope.election_slug
                AND (
                  g.level NOT IN (
                    'national','department','municipality','zone','polling_place','mesa'
                  )
                  OR (g.level='national' AND g.parent_id IS NOT NULL)
                  OR (g.level<>'national' AND g.parent_id IS NULL)
                )
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT g.parent_id AS id,
                  CASE g.level
                    WHEN 'department' THEN 'national'
                    WHEN 'municipality' THEN 'department'
                    WHEN 'zone' THEN 'municipality'
                    WHEN 'mesa' THEN 'polling_place'
                  END AS level
                FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
                  AND g.level IN ('department','municipality','zone','mesa')
                EXCEPT
                SELECT g.id,g.level FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
              ) missing_geography_parent
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT g.parent_id FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
                  AND g.level='polling_place'
                EXCEPT
                SELECT g.id FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
                  AND g.level IN ('zone','municipality')
              ) missing_polling_place_parent
            ) THEN
              RAISE EXCEPTION 'release exposure rejected: invalid geography hierarchy';
            END IF;

            IF EXISTS (
              SELECT 1 FROM (
                SELECT required.id,required.level FROM (
                  SELECT m.id,'mesa'::text AS level FROM public.release_mesas m
                  WHERE m.release_id=locked_scope.release_id
                    AND m.election_slug=locked_scope.election_slug
                  UNION ALL
                  SELECT m.polling_place_id,'polling_place'::text
                  FROM public.release_mesas m
                  WHERE m.release_id=locked_scope.release_id
                    AND m.election_slug=locked_scope.election_slug
                  UNION ALL
                  SELECT m.municipality_id,'municipality'::text
                  FROM public.release_mesas m
                  WHERE m.release_id=locked_scope.release_id
                    AND m.election_slug=locked_scope.election_slug
                  UNION ALL
                  SELECT m.department_id,'department'::text
                  FROM public.release_mesas m
                  WHERE m.release_id=locked_scope.release_id
                    AND m.election_slug=locked_scope.election_slug
                ) required
                EXCEPT
                SELECT g.id,g.level FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
              ) missing_mesa_geography
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT m.id,m.polling_place_id FROM public.release_mesas m
                WHERE m.release_id=locked_scope.release_id
                  AND m.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT g.id,g.parent_id FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
                  AND g.level='mesa'
              ) invalid_mesa_parent
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT m.municipality_id,m.department_id FROM public.release_mesas m
                WHERE m.release_id=locked_scope.release_id
                  AND m.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT g.id,g.parent_id FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
                  AND g.level='municipality'
              ) invalid_municipality_parent
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT m.polling_place_id,m.municipality_id
                FROM public.release_mesas m
                WHERE m.release_id=locked_scope.release_id
                  AND m.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT p.id,
                  CASE parent.level
                    WHEN 'municipality' THEN parent.id
                    WHEN 'zone' THEN parent.parent_id
                  END
                FROM public.release_geographies p
                JOIN public.release_geographies parent
                  ON (parent.release_id,parent.election_slug,parent.id)=
                     (p.release_id,p.election_slug,p.parent_id)
                WHERE p.release_id=locked_scope.release_id
                  AND p.election_slug=locked_scope.election_slug
                  AND p.level='polling_place'
              ) invalid_polling_place_municipality
            ) THEN
              RAISE EXCEPTION 'release exposure rejected: invalid mesa geography lineage';
            END IF;

            IF EXISTS (
              SELECT 1 FROM public.release_result_facts f
              WHERE f.release_id=locked_scope.release_id
                AND f.election_slug=locked_scope.election_slug
                AND (
                  f.geography_level NOT IN (
                    'national','department','municipality','zone','polling_place','mesa'
                  )
                  OR (
                    f.geography_level='mesa'
                    AND (f.mesa_id IS NULL OR f.mesa_id<>f.geography_id)
                  )
                  OR (f.geography_level<>'mesa' AND f.mesa_id IS NOT NULL)
                )
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT f.geography_id,f.geography_level
                FROM public.release_result_facts f
                WHERE f.release_id=locked_scope.release_id
                  AND f.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT g.id,g.level FROM public.release_geographies g
                WHERE g.release_id=locked_scope.release_id
                  AND g.election_slug=locked_scope.election_slug
              ) missing_fact_geography
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT f.mesa_id FROM public.release_result_facts f
                WHERE f.release_id=locked_scope.release_id
                  AND f.election_slug=locked_scope.election_slug
                  AND f.mesa_id IS NOT NULL
                EXCEPT
                SELECT m.id FROM public.release_mesas m
                WHERE m.release_id=locked_scope.release_id
                  AND m.election_slug=locked_scope.election_slug
              ) missing_fact_mesa
            ) OR EXISTS (
              SELECT 1 FROM (
                SELECT f.source_id FROM public.release_result_facts f
                WHERE f.release_id=locked_scope.release_id
                  AND f.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT s.id FROM public.release_sources s
                WHERE s.release_id=locked_scope.release_id
                  AND s.election_slug=locked_scope.election_slug
              ) missing_fact_source
            ) THEN
              RAISE EXCEPTION 'release exposure rejected: invalid result fact relationship';
            END IF;

            IF EXISTS (
              SELECT 1 FROM (
                SELECT c.result_fact_id FROM public.release_category_facts c
                WHERE c.release_id=locked_scope.release_id
                  AND c.election_slug=locked_scope.election_slug
                EXCEPT
                SELECT f.id FROM public.release_result_facts f
                WHERE f.release_id=locked_scope.release_id
                  AND f.election_slug=locked_scope.election_slug
              ) missing_category_fact
            ) THEN
              RAISE EXCEPTION 'release exposure rejected: invalid category fact relationship';
            END IF;
          END LOOP;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER release_exposures_scope_lock_before_write "
        "BEFORE INSERT OR UPDATE OR DELETE ON release_exposures FOR EACH ROW "
        "EXECUTE FUNCTION lock_release_election_scope_before_write()"
    )
    op.execute(
        "CREATE TRIGGER release_exposure_validate_insert "
        "AFTER INSERT ON release_exposures REFERENCING NEW TABLE AS new_rows "
        "FOR EACH STATEMENT "
        "EXECUTE FUNCTION validate_release_exposure()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_release_exposure_update() RETURNS trigger
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
    op.execute(
        "CREATE TRIGGER release_exposure_guard_update "
        "BEFORE UPDATE ON release_exposures FOR EACH ROW "
        "EXECUTE FUNCTION guard_release_exposure_update()"
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposure_delete() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          RAISE EXCEPTION 'release exposure rows cannot be deleted';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER release_exposure_immutable_delete "
        "BEFORE DELETE ON release_exposures FOR EACH ROW "
        "EXECUTE FUNCTION reject_exposure_delete()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_exposed_release_update() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.release_exposures e WHERE e.release_id=OLD.id
          ) THEN
            IF OLD.id IS DISTINCT FROM NEW.id
               OR OLD.synthetic IS DISTINCT FROM NEW.synthetic
               OR OLD.created_at IS DISTINCT FROM NEW.created_at
               OR OLD.methodology_version IS DISTINCT FROM NEW.methodology_version
               OR OLD.manifest::jsonb IS DISTINCT FROM NEW.manifest::jsonb THEN
              RAISE EXCEPTION 'exposed release metadata is immutable';
            END IF;
            IF OLD.status IS DISTINCT FROM NEW.status
               AND NOT (
                 (OLD.status='candidate' AND NEW.status IN ('published','withdrawn'))
                 OR (OLD.status='published' AND NEW.status='withdrawn')
               ) THEN
              RAISE EXCEPTION 'invalid exposed release status transition';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER releases_guard_exposed_update "
        "BEFORE UPDATE ON releases FOR EACH ROW "
        "EXECUTE FUNCTION guard_exposed_release_update()"
    )
    op.execute(
        """
        CREATE FUNCTION reject_exposed_release_row_delete() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.release_exposures e WHERE e.release_id=OLD.id
          ) THEN
            RAISE EXCEPTION 'exposed releases cannot be deleted';
          END IF;
          RETURN OLD;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER releases_reject_exposed_delete "
        "BEFORE DELETE ON releases FOR EACH ROW "
        "EXECUTE FUNCTION reject_exposed_release_row_delete()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER releases_reject_exposed_delete ON releases")
    op.execute("DROP FUNCTION reject_exposed_release_row_delete()")
    op.execute("DROP TRIGGER releases_guard_exposed_update ON releases")
    op.execute("DROP FUNCTION guard_exposed_release_update()")
    op.execute("DROP TRIGGER release_exposure_guard_update ON release_exposures")
    op.execute("DROP FUNCTION guard_release_exposure_update()")
    op.execute("DROP TRIGGER release_exposures_scope_lock_before_write ON release_exposures")
    op.execute("DROP TRIGGER release_exposure_validate_insert ON release_exposures")
    op.execute("DROP FUNCTION validate_release_exposure()")
    op.execute("DROP TRIGGER release_exposure_immutable_delete ON release_exposures")
    op.execute("DROP FUNCTION reject_exposure_delete()")
    for table in reversed(_IMMUTABLE_TABLES):
        for operation in ("delete", "update", "insert"):
            op.execute(f"DROP TRIGGER {table}_immutable_{operation} ON {table}")
        op.execute(f"DROP TRIGGER {table}_scope_lock_before_write ON {table}")
    op.execute("DROP FUNCTION reject_exposed_release_delete()")
    op.execute("DROP FUNCTION reject_exposed_release_update()")
    op.execute("DROP FUNCTION reject_exposed_release_insert()")
    op.execute("DROP FUNCTION lock_release_election_scope_before_write()")
    op.execute("DROP FUNCTION lock_release_election_scope(text, text)")
    op.drop_constraint(
        "fk_release_category_facts_election",
        "release_category_facts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_release_result_facts_election",
        "release_result_facts",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "release_geographies_release_id_election_slug_parent_id_fkey",
        "release_geographies",
        "release_geographies",
        ["release_id", "election_slug", "parent_id"],
        ["release_id", "election_slug", "id"],
    )
    op.create_foreign_key(
        "release_mesas_release_id_election_slug_id_fkey",
        "release_mesas",
        "release_geographies",
        ["release_id", "election_slug", "id"],
        ["release_id", "election_slug", "id"],
    )
    for suffix, column in (
        ("polling_place_id", "polling_place_id"),
        ("municipality_id", "municipality_id"),
        ("department_id", "department_id"),
    ):
        op.create_foreign_key(
            f"release_mesas_release_id_election_slug_{suffix}_fkey",
            "release_mesas",
            "release_geographies",
            ["release_id", "election_slug", column],
            ["release_id", "election_slug", "id"],
        )
    for suffix, column, target in (
        ("geography_id", "geography_id", "release_geographies"),
        ("mesa_id", "mesa_id", "release_mesas"),
        ("source_id", "source_id", "release_sources"),
    ):
        op.create_foreign_key(
            f"release_result_facts_release_id_election_slug_{suffix}_fkey",
            "release_result_facts",
            target,
            ["release_id", "election_slug", column],
            ["release_id", "election_slug", "id"],
        )
    op.create_foreign_key(
        "release_category_facts_release_id_election_slug_result_fac_fkey",
        "release_category_facts",
        "release_result_facts",
        ["release_id", "election_slug", "result_fact_id"],
        ["release_id", "election_slug", "id"],
    )
    for table, constraint in (
        ("release_geographies", "release_geographies_release_id_election_slug_fkey"),
        ("release_mesas", "release_mesas_release_id_election_slug_fkey"),
    ):
        op.execute(f'ALTER TABLE "{table}" ALTER CONSTRAINT "{constraint}" NOT DEFERRABLE')
