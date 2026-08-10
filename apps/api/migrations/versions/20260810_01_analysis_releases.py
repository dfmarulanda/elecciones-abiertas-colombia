"""Add immutable statistical-analysis releases and independent exposures.

Revision ID: 20260810_01
Revises: 20260808_01
Create Date: 2026-08-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260810_01"
down_revision = "20260808_01"
branch_labels = None
depends_on = None

_HASH_CHECK = "{column} ~ '^[0-9a-f]{{64}}$'"


def _hash_check(column: str) -> str:
    return _HASH_CHECK.format(column=column)


def upgrade() -> None:
    op.create_table(
        "analysis_releases",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("methodology_version", sa.String(128), nullable=False),
        sa.Column("canonical_input_hash", sa.String(64), nullable=False),
        sa.Column("producer_runtime_fingerprint", sa.String(64), nullable=False),
        sa.Column("producer_operator_id", sa.String(200), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_release_id", "source_election_slug"],
            ["release_elections.release_id", "release_elections.election_slug"],
        ),
        sa.UniqueConstraint(
            "source_release_id",
            "source_election_slug",
            "methodology_version",
            "canonical_input_hash",
            name="uq_analysis_release_binding",
        ),
        sa.UniqueConstraint(
            "analysis_release_id",
            "source_release_id",
            "source_election_slug",
            name="uq_analysis_release_scope",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('generated','validated','retired')",
            name="ck_analysis_release_lifecycle",
        ),
        sa.CheckConstraint(
            _hash_check("canonical_input_hash"), name="ck_analysis_release_input_hash"
        ),
        sa.CheckConstraint(
            _hash_check("producer_runtime_fingerprint"),
            name="ck_analysis_release_runtime_hash",
        ),
        sa.CheckConstraint(_hash_check("manifest_hash"), name="ck_analysis_release_manifest_hash"),
        sa.CheckConstraint(
            "length(btrim(methodology_version)) > 0 AND length(btrim(producer_operator_id)) > 0",
            name="ck_analysis_release_required_identity",
        ),
    )
    op.create_index(
        "ix_analysis_release_source",
        "analysis_releases",
        ["source_release_id", "source_election_slug", "created_at", "analysis_release_id"],
    )

    op.create_table(
        "analysis_artifact_hosts",
        sa.Column("host", sa.String(253), primary_key=True),
        sa.CheckConstraint(
            "host = lower(host) AND host ~ '^[a-z0-9][a-z0-9.-]*[a-z0-9]$' "
            "AND host !~ '\\.\\.' AND host !~ '[@:/?#]'",
            name="ck_analysis_artifact_host_safe",
        ),
    )
    op.execute(
        "INSERT INTO analysis_artifact_hosts(host) "
        "VALUES ('eleccionesabiertas.co'),('github.com')"
    )
    op.create_table(
        "analysis_artifacts",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("artifact_id", sa.String(200), primary_key=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("record_count", sa.BigInteger(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("byte_hash", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("immutable_url", sa.Text()),
        sa.Column("artifact_status", sa.String(32), nullable=False),
        sa.Column("status_reason", sa.Text()),
        sa.ForeignKeyConstraint(
            ["analysis_release_id", "source_release_id", "source_election_slug"],
            [
                "analysis_releases.analysis_release_id",
                "analysis_releases.source_release_id",
                "analysis_releases.source_election_slug",
            ],
        ),
        sa.UniqueConstraint(
            "analysis_release_id",
            "source_release_id",
            "source_election_slug",
            "artifact_id",
            name="uq_analysis_artifact_scope",
        ),
        sa.CheckConstraint(
            "artifact_status IN ('available','not_evaluable','unavailable','withheld')",
            name="ck_analysis_artifact_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND byte_size >= 0", name="ck_analysis_artifact_sizes"
        ),
        sa.CheckConstraint(_hash_check("byte_hash"), name="ck_analysis_artifact_byte_hash"),
        sa.CheckConstraint(_hash_check("content_hash"), name="ck_analysis_artifact_content_hash"),
        sa.CheckConstraint(
            "(artifact_status='available' AND immutable_url IS NOT NULL) OR "
            "(artifact_status<>'available' AND immutable_url IS NULL "
            "AND length(coalesce(status_reason,'')) > 0)",
            name="ck_analysis_artifact_availability",
        ),
        sa.CheckConstraint(
            "media_type IN ('application/json','application/schema+json',"
            "'application/vnd.apache.parquet','text/plain')",
            name="ck_analysis_artifact_media_type",
        ),
    )
    op.create_index(
        "ix_analysis_artifact_kind",
        "analysis_artifacts",
        ["analysis_release_id", "kind", "artifact_status", "artifact_id"],
    )

    op.create_table(
        "analysis_anomalies",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("anomaly_id", sa.String(200), primary_key=True),
        sa.Column("family", sa.String(80), nullable=False),
        sa.Column("evidence_tier", sa.String(40), nullable=False),
        sa.Column("audit_priority", sa.Integer(), nullable=False),
        sa.Column("evaluability", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(160)),
        sa.Column("geography_id", sa.String(200)),
        sa.Column("metric", sa.String(100)),
        sa.Column("candidate_id", sa.String(200)),
        sa.Column("explanation_es", sa.Text(), nullable=False),
        sa.Column("explanation_en", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("calculations", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("provenance_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_release_id", "source_release_id", "source_election_slug"],
            [
                "analysis_releases.analysis_release_id",
                "analysis_releases.source_release_id",
                "analysis_releases.source_election_slug",
            ],
        ),
        sa.UniqueConstraint(
            "analysis_release_id",
            "source_release_id",
            "source_election_slug",
            "anomaly_id",
            name="uq_analysis_anomaly_scope",
        ),
        sa.CheckConstraint(
            "evidence_tier IN ('descriptive','deterministic','research_preview',"
            "'independently_validated','non_evaluable')",
            name="ck_analysis_anomaly_evidence_tier",
        ),
        sa.CheckConstraint(
            "evaluability IN ('evaluable','not_evaluable','unavailable')",
            name="ck_analysis_anomaly_evaluability",
        ),
        sa.CheckConstraint("audit_priority BETWEEN 0 AND 100", name="ck_analysis_anomaly_priority"),
        sa.CheckConstraint(
            "evidence_tier NOT IN ('research_preview','non_evaluable') OR audit_priority=0",
            name="ck_analysis_anomaly_preview_zero_points",
        ),
        sa.CheckConstraint(
            "evaluability='evaluable' OR length(coalesce(reason_code,'')) > 0",
            name="ck_analysis_anomaly_reason",
        ),
        sa.CheckConstraint(_hash_check("provenance_hash"), name="ck_analysis_anomaly_hash"),
    )
    op.create_index(
        "ix_analysis_anomaly_page",
        "analysis_anomalies",
        ["analysis_release_id", "family", "evidence_tier", "audit_priority", "anomaly_id"],
    )

    op.create_table(
        "analysis_anomaly_components",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("anomaly_id", sa.String(200), primary_key=True),
        sa.Column("component_id", sa.String(200), primary_key=True),
        sa.Column("component_type", sa.String(100), nullable=False),
        sa.Column("evidence_type", sa.String(100), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric()),
        sa.Column("unit", sa.String(80)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("provenance_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_release_id", "source_release_id", "source_election_slug", "anomaly_id"],
            [
                "analysis_anomalies.analysis_release_id",
                "analysis_anomalies.source_release_id",
                "analysis_anomalies.source_election_slug",
                "analysis_anomalies.anomaly_id",
            ],
        ),
        sa.CheckConstraint("points BETWEEN 0 AND 100", name="ck_analysis_component_points"),
        sa.CheckConstraint(
            "evidence_type <> 'research_preview' OR points=0",
            name="ck_analysis_component_preview_zero_points",
        ),
        sa.CheckConstraint(
            "component_type NOT IN ('peer_distribution','spatial','spatial_cluster') "
            "OR points <= 20",
            name="ck_analysis_component_statistical_cap",
        ),
        sa.CheckConstraint(_hash_check("provenance_hash"), name="ck_analysis_component_hash"),
    )

    op.create_table(
        "analysis_reports",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("report_id", sa.String(200), primary_key=True),
        sa.Column("report_kind", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("evaluability", sa.String(32), nullable=False),
        sa.Column("status_reason", sa.Text()),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("validation", sa.JSON(), nullable=False),
        sa.Column("local_sensitivity", sa.JSON(), nullable=False),
        sa.Column("artifact_id", sa.String(200)),
        sa.Column("provenance_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_release_id", "source_release_id", "source_election_slug"],
            [
                "analysis_releases.analysis_release_id",
                "analysis_releases.source_release_id",
                "analysis_releases.source_election_slug",
            ],
        ),
        sa.ForeignKeyConstraint(
            [
                "analysis_release_id",
                "source_release_id",
                "source_election_slug",
                "artifact_id",
            ],
            [
                "analysis_artifacts.analysis_release_id",
                "analysis_artifacts.source_release_id",
                "analysis_artifacts.source_election_slug",
                "analysis_artifacts.artifact_id",
            ],
        ),
        sa.CheckConstraint(
            "report_kind IN ('eligibility','coverage','descriptive','model_diagnostics',"
            "'validation','local_sensitivity','outcome_sensitivity','research_model')",
            name="ck_analysis_report_kind",
        ),
        sa.CheckConstraint(
            "evaluability IN ('evaluable','not_evaluable','unavailable','research_preview')",
            name="ck_analysis_report_evaluability",
        ),
        sa.CheckConstraint(
            "evaluability IN ('evaluable','research_preview') OR "
            "length(coalesce(status_reason,'')) > 0",
            name="ck_analysis_report_reason",
        ),
        sa.CheckConstraint(_hash_check("provenance_hash"), name="ck_analysis_report_hash"),
    )

    op.create_table(
        "analysis_exposures",
        sa.Column("analysis_release_id", sa.String(160), primary_key=True),
        sa.Column("source_release_id", sa.String(128), nullable=False),
        sa.Column("source_election_slug", sa.String(160), nullable=False),
        sa.Column("exposure_tier", sa.String(32), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("exposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by", sa.String(200)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approval_signature_hash", sa.String(64)),
        sa.Column("caveat_es", sa.Text()),
        sa.Column("caveat_en", sa.Text()),
        sa.Column("pass_b_packet_hash", sa.String(64)),
        sa.Column("pass_b_runtime_fingerprint", sa.String(64)),
        sa.Column("pass_b_operator_id", sa.String(200)),
        sa.Column("independent_reviewer_id", sa.String(200)),
        sa.Column("independent_review_signature_hash", sa.String(64)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", sa.String(200)),
        sa.Column("revocation_reason", sa.Text()),
        sa.ForeignKeyConstraint(
            ["analysis_release_id", "source_release_id", "source_election_slug"],
            [
                "analysis_releases.analysis_release_id",
                "analysis_releases.source_release_id",
                "analysis_releases.source_election_slug",
            ],
        ),
        sa.CheckConstraint(
            "exposure_tier IN ('internal','preliminary_research','certified_public')",
            name="ck_analysis_exposure_tier",
        ),
        sa.CheckConstraint(_hash_check("manifest_hash"), name="ck_analysis_exposure_manifest_hash"),
        sa.CheckConstraint(
            "(exposure_tier='internal' AND approved_by IS NULL AND approved_at IS NULL "
            "AND approval_signature_hash IS NULL AND caveat_es IS NULL AND caveat_en IS NULL "
            "AND pass_b_packet_hash IS NULL AND pass_b_runtime_fingerprint IS NULL "
            "AND pass_b_operator_id IS NULL AND independent_reviewer_id IS NULL "
            "AND independent_review_signature_hash IS NULL) OR "
            "(exposure_tier='preliminary_research' AND length(coalesce(approved_by,'')) > 0 "
            "AND approved_at IS NOT NULL AND approval_signature_hash IS NOT NULL "
            "AND length(coalesce(caveat_es,'')) > 0 AND length(coalesce(caveat_en,'')) > 0 "
            "AND pass_b_packet_hash IS NULL AND pass_b_runtime_fingerprint IS NULL "
            "AND pass_b_operator_id IS NULL AND independent_reviewer_id IS NULL "
            "AND independent_review_signature_hash IS NULL) OR "
            "(exposure_tier='certified_public' AND length(coalesce(approved_by,'')) > 0 "
            "AND approved_at IS NOT NULL AND approval_signature_hash IS NOT NULL "
            "AND length(coalesce(caveat_es,'')) > 0 AND length(coalesce(caveat_en,'')) > 0 "
            "AND pass_b_packet_hash IS NOT NULL AND pass_b_runtime_fingerprint IS NOT NULL "
            "AND length(coalesce(pass_b_operator_id,'')) > 0 "
            "AND length(coalesce(independent_reviewer_id,'')) > 0 "
            "AND independent_review_signature_hash IS NOT NULL)",
            name="ck_analysis_exposure_approval",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND length(coalesce(revoked_by,'')) > 0 "
            "AND length(coalesce(revocation_reason,'')) > 0)",
            name="ck_analysis_exposure_revocation",
        ),
        sa.CheckConstraint(
            "approval_signature_hash IS NULL OR approval_signature_hash ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_exposure_approval_signature",
        ),
        sa.CheckConstraint(
            "pass_b_packet_hash IS NULL OR pass_b_packet_hash ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_exposure_pass_b_hash",
        ),
        sa.CheckConstraint(
            "pass_b_runtime_fingerprint IS NULL OR pass_b_runtime_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_exposure_pass_b_runtime",
        ),
        sa.CheckConstraint(
            "independent_review_signature_hash IS NULL OR "
            "independent_review_signature_hash ~ '^[0-9a-f]{64}$'",
            name="ck_analysis_exposure_review_signature",
        ),
    )
    op.create_index(
        "ix_analysis_exposure_selection",
        "analysis_exposures",
        ["source_release_id", "source_election_slug", "exposure_tier", "approved_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.execute(
        """
        CREATE FUNCTION validate_analysis_artifact() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE artifact_host text;
        BEGIN
          IF NEW.artifact_status='available' THEN
            IF NEW.immutable_url !~ '^https://[A-Za-z0-9.-]+/[^?#]+$' THEN
              RAISE EXCEPTION 'available analysis artifact requires an immutable HTTPS URL';
            END IF;
            artifact_host := lower(substring(NEW.immutable_url from '^https://([^/]+)/'));
            IF NOT EXISTS (
              SELECT 1 FROM public.analysis_artifact_hosts h WHERE h.host=artifact_host
            ) THEN
              RAISE EXCEPTION 'analysis artifact host is not allowlisted';
            END IF;
            IF position(NEW.byte_hash in NEW.immutable_url)=0 THEN
              RAISE EXCEPTION 'analysis artifact URL must be content-addressed by byte hash';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_artifact_validate
        BEFORE INSERT OR UPDATE ON analysis_artifacts FOR EACH ROW
        EXECUTE FUNCTION validate_analysis_artifact()
        """
    )

    op.execute(
        """
        CREATE FUNCTION guard_analysis_content_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE release_id text;
        BEGIN
          release_id := CASE WHEN TG_OP='DELETE' THEN OLD.analysis_release_id
                             ELSE NEW.analysis_release_id END;
          PERFORM 1 FROM public.analysis_releases r
          WHERE r.analysis_release_id=release_id FOR KEY SHARE;
          IF EXISTS (
            SELECT 1 FROM public.analysis_exposures e
            WHERE e.analysis_release_id=release_id
          ) THEN
            RAISE EXCEPTION 'exposed analysis release rows are immutable';
          END IF;
          RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
        END $$
        """
    )
    for table in (
        "analysis_artifacts",
        "analysis_anomalies",
        "analysis_anomaly_components",
        "analysis_reports",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_immutable "
            f"BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW "
            "EXECUTE FUNCTION guard_analysis_content_mutation()"
        )

    op.execute(
        """
        CREATE FUNCTION guard_analysis_release_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM public.analysis_exposures e
            WHERE e.analysis_release_id=OLD.analysis_release_id
          ) THEN
            RAISE EXCEPTION 'exposed analysis release rows are immutable';
          END IF;
          RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_releases_immutable
        BEFORE UPDATE OR DELETE ON analysis_releases FOR EACH ROW
        EXECUTE FUNCTION guard_analysis_release_mutation()
        """
    )

    op.execute(
        """
        CREATE FUNCTION guard_analysis_artifact_hosts() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          RAISE EXCEPTION 'analysis artifact host allowlist entries are append-only';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_artifact_hosts_append_only
        BEFORE UPDATE OR DELETE ON analysis_artifact_hosts FOR EACH ROW
        EXECUTE FUNCTION guard_analysis_artifact_hosts()
        """
    )

    op.execute(
        """
        CREATE FUNCTION guard_analysis_exposure_write() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE release_row public.analysis_releases%ROWTYPE;
        DECLARE source_status text;
        DECLARE source_scope text;
        DECLARE source_approved_at timestamptz;
        BEGIN
          SELECT * INTO release_row FROM public.analysis_releases r
          WHERE r.analysis_release_id=NEW.analysis_release_id FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'analysis exposure references an unknown analysis release';
          END IF;
          IF NEW.source_release_id IS DISTINCT FROM release_row.source_release_id
             OR NEW.source_election_slug IS DISTINCT FROM release_row.source_election_slug
             OR NEW.manifest_hash IS DISTINCT FROM release_row.manifest_hash THEN
            RAISE EXCEPTION 'analysis exposure scope and manifest must match its analysis release';
          END IF;

          IF TG_OP='INSERT' THEN
            IF NEW.exposure_tier<>'internal' THEN
              RAISE EXCEPTION 'analysis exposure must enter through the internal gate';
            END IF;
            RETURN NEW;
          END IF;

          IF OLD.analysis_release_id IS DISTINCT FROM NEW.analysis_release_id
             OR OLD.source_release_id IS DISTINCT FROM NEW.source_release_id
             OR OLD.source_election_slug IS DISTINCT FROM NEW.source_election_slug
             OR OLD.manifest_hash IS DISTINCT FROM NEW.manifest_hash
             OR OLD.exposed_at IS DISTINCT FROM NEW.exposed_at THEN
            RAISE EXCEPTION 'analysis exposure identity and manifest are immutable';
          END IF;
          IF OLD.revoked_at IS NOT NULL AND (
             OLD.revoked_at IS DISTINCT FROM NEW.revoked_at
             OR OLD.revoked_by IS DISTINCT FROM NEW.revoked_by
             OR OLD.revocation_reason IS DISTINCT FROM NEW.revocation_reason) THEN
            RAISE EXCEPTION 'analysis exposure revocation is immutable';
          END IF;
          IF OLD.revoked_at IS NULL AND NEW.revoked_at IS NOT NULL THEN
            IF OLD.exposure_tier IS DISTINCT FROM NEW.exposure_tier
               OR OLD.approved_by IS DISTINCT FROM NEW.approved_by
               OR OLD.approved_at IS DISTINCT FROM NEW.approved_at
               OR OLD.approval_signature_hash IS DISTINCT FROM NEW.approval_signature_hash
               OR OLD.caveat_es IS DISTINCT FROM NEW.caveat_es
               OR OLD.caveat_en IS DISTINCT FROM NEW.caveat_en
               OR OLD.pass_b_packet_hash IS DISTINCT FROM NEW.pass_b_packet_hash
               OR OLD.pass_b_runtime_fingerprint IS DISTINCT FROM NEW.pass_b_runtime_fingerprint
               OR OLD.pass_b_operator_id IS DISTINCT FROM NEW.pass_b_operator_id
               OR OLD.independent_reviewer_id IS DISTINCT FROM NEW.independent_reviewer_id
               OR OLD.independent_review_signature_hash
                  IS DISTINCT FROM NEW.independent_review_signature_hash THEN
              RAISE EXCEPTION 'analysis exposure revocation must be independent';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.revoked_at IS DISTINCT FROM NEW.revoked_at
             OR OLD.revoked_by IS DISTINCT FROM NEW.revoked_by
             OR OLD.revocation_reason IS DISTINCT FROM NEW.revocation_reason THEN
            RAISE EXCEPTION 'analysis exposure revocation is immutable';
          END IF;
          IF OLD.exposure_tier IS NOT DISTINCT FROM NEW.exposure_tier THEN
            IF OLD.approved_by IS DISTINCT FROM NEW.approved_by
               OR OLD.approved_at IS DISTINCT FROM NEW.approved_at
               OR OLD.approval_signature_hash IS DISTINCT FROM NEW.approval_signature_hash
               OR OLD.caveat_es IS DISTINCT FROM NEW.caveat_es
               OR OLD.caveat_en IS DISTINCT FROM NEW.caveat_en
               OR OLD.pass_b_packet_hash IS DISTINCT FROM NEW.pass_b_packet_hash
               OR OLD.pass_b_runtime_fingerprint IS DISTINCT FROM NEW.pass_b_runtime_fingerprint
               OR OLD.pass_b_operator_id IS DISTINCT FROM NEW.pass_b_operator_id
               OR OLD.independent_reviewer_id IS DISTINCT FROM NEW.independent_reviewer_id
               OR OLD.independent_review_signature_hash
                  IS DISTINCT FROM NEW.independent_review_signature_hash THEN
              RAISE EXCEPTION 'analysis exposure approval is immutable';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.exposure_tier<>'internal'
             OR NEW.exposure_tier NOT IN ('preliminary_research','certified_public') THEN
            RAISE EXCEPTION USING MESSAGE =
              'analysis exposure may only transition internal to ' ||
              'preliminary_research or certified_public';
          END IF;

          SELECT r.status,e.access_scope,e.approved_at INTO
            source_status,source_scope,source_approved_at
          FROM public.releases r
          JOIN public.release_exposures e
            ON e.release_id=r.id
           AND e.election_slug=release_row.source_election_slug
          WHERE r.id=release_row.source_release_id;
          IF NEW.exposure_tier='preliminary_research' AND NOT (
             source_status='candidate' AND source_scope='preliminary') THEN
            RAISE EXCEPTION 'preliminary analysis requires preliminary source exposure';
          END IF;
          IF NEW.exposure_tier='certified_public' AND NOT (
             source_status='published' AND source_scope='public'
             AND source_approved_at IS NOT NULL) THEN
            RAISE EXCEPTION 'certified source release required';
          END IF;
          IF NEW.exposure_tier='certified_public' AND (
             NEW.pass_b_runtime_fingerprint=release_row.producer_runtime_fingerprint
             OR NEW.pass_b_operator_id=release_row.producer_operator_id
             OR NEW.independent_reviewer_id=release_row.producer_operator_id) THEN
            RAISE EXCEPTION 'independent runtime, operator, and reviewer required';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_exposures_guard
        BEFORE INSERT OR UPDATE ON analysis_exposures FOR EACH ROW
        EXECUTE FUNCTION guard_analysis_exposure_write()
        """
    )
    op.execute(
        """
        CREATE FUNCTION guard_analysis_exposure_delete() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          RAISE EXCEPTION 'analysis exposure must be revoked, not deleted';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER analysis_exposures_no_delete
        BEFORE DELETE ON analysis_exposures FOR EACH ROW
        EXECUTE FUNCTION guard_analysis_exposure_delete()
        """
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_exposure_selection", table_name="analysis_exposures")
    op.drop_table("analysis_exposures")
    op.execute("DROP FUNCTION guard_analysis_exposure_delete()")
    op.execute("DROP FUNCTION guard_analysis_exposure_write()")
    op.drop_table("analysis_reports")
    op.drop_table("analysis_anomaly_components")
    op.drop_index("ix_analysis_anomaly_page", table_name="analysis_anomalies")
    op.drop_table("analysis_anomalies")
    op.drop_index("ix_analysis_artifact_kind", table_name="analysis_artifacts")
    op.drop_table("analysis_artifacts")
    op.drop_table("analysis_artifact_hosts")
    op.drop_index("ix_analysis_release_source", table_name="analysis_releases")
    op.drop_table("analysis_releases")
    op.execute("DROP FUNCTION guard_analysis_artifact_hosts()")
    op.execute("DROP FUNCTION guard_analysis_release_mutation()")
    op.execute("DROP FUNCTION guard_analysis_content_mutation()")
    op.execute("DROP FUNCTION validate_analysis_artifact()")
