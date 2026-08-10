import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ANALYTICAL_DISCLOSURE_EN,
  ANALYTICAL_DISCLOSURE_ES,
  AnalysisAnomalySchema,
  AnalysisArtifactMetadataSchema,
  AnalysisReleaseMetadataSchema,
  ContextElectionSummarySchema,
  EvidenceDocumentSchema,
  GeographicCollectionCoverageSchema,
  MetricValueSchema,
  OutcomeSensitivityArtifactSchema,
  OutcomeSensitivitySchema,
  PackagedDatasetSchema,
  ReleaseManifestSchema,
  ReviewSignalSchema,
  reviewSignalTier,
} from "./schemas";

describe("shared data contracts", () => {
  it("rejects public points from preliminary statistical evidence", () => {
    const hash = "a".repeat(64);
    const anomaly = {
      id: "peer-1",
      mesa_id: "mesa-1",
      anomaly_types: ["peer_distribution" as const],
      is_anomaly: true,
      audit_priority_score: 0,
      explanation: {
        status: "non_evaluable" as const,
        preregistration_hash: null,
        available_data_hash: null,
        reviewed_at: null,
        quantitative_effect: { value: null, status: "unknown" as const },
        quantitative_p_value: { value: null, status: "unknown" as const },
        notes: null,
      },
      minimum_ballot_edits: { value: null, status: "unknown" as const },
      minimum_ballot_edits_status: "not_evaluable" as const,
      minimum_ballot_edits_reason: "documentary_bound_unavailable",
      components: [],
      research_preview: true,
      ineligible_reasons: ["independent_validation_pending"],
      methodology_version: "analysis-v1",
      disclosure: {
        es: ANALYTICAL_DISCLOSURE_ES,
        en: ANALYTICAL_DISCLOSURE_EN,
      },
      provenance: {
        data_version: "release-1",
        source_type: "pre_count" as const,
        legal_status: "preliminary" as const,
        source_url: "https://official.example/source.json",
        retrieved_at: "2026-08-10T10:00:00Z",
        content_hash: hash,
        parser_version: "parser-v1",
        transform_version: "transform-v1",
        methodology_version: "analysis-v1",
      },
      analysis_release: {
        analysis_release_id: "analysis-1",
        methodology_version: "analysis-v1",
        source_release_id: "release-1",
        election_slug: "election-1",
        exposure_tier: "preliminary_research" as const,
        preliminary_caveat: { es: "Preliminar", en: "Preliminary" },
        artifact_status: "research_preview" as const,
        evaluable: true,
        status_reasons: ["independent_validation_pending"],
        canonical_input_hash: hash,
        manifest_hash: hash,
        provenance_hash: hash,
        generated_at: "2026-08-10T10:00:00Z",
        approved_at: "2026-08-10T11:00:00Z",
      },
      family: "peer_distribution",
      evidence_tier: "research_preview" as const,
      evaluability: "evaluable" as const,
      public_evidence: {},
      calculations: {},
      limitations: ["Research preview."],
      provenance_hash: hash,
      typed_components: [
        {
          component_id: "peer-1:component-1",
          component_type: "peer_distribution",
          evidence_type: "research_preview",
          points: 0,
          value: 0.1,
          unit: "share",
          public_payload: {},
          provenance_hash: hash,
        },
      ],
    };
    expect(AnalysisAnomalySchema.parse(anomaly).audit_priority_score).toBe(0);
    expect(() =>
      AnalysisAnomalySchema.parse({ ...anomaly, audit_priority_score: 10 }),
    ).toThrow();
    expect(() =>
      AnalysisAnomalySchema.parse({
        ...anomaly,
        typed_components: [{ ...anomaly.typed_components[0], points: 10 }],
      }),
    ).toThrow();
  });

  it("binds public analysis metadata and artifacts to immutable hashes", () => {
    const hash = "a".repeat(64);
    const metadata = {
      analysis_release_id: "analysis-1",
      methodology_version: "analysis-v1",
      source_release_id: "release-1",
      election_slug: "election-1",
      exposure_tier: "preliminary_research" as const,
      preliminary_caveat: { es: "Preliminar", en: "Preliminary" },
      artifact_status: "research_preview" as const,
      evaluable: true,
      status_reasons: ["research_only"],
      canonical_input_hash: hash,
      manifest_hash: hash,
      provenance_hash: hash,
      generated_at: "2026-08-10T10:00:00Z",
      approved_at: "2026-08-10T11:00:00Z",
    };
    expect(
      AnalysisReleaseMetadataSchema.parse(metadata).analysis_release_id,
    ).toBe("analysis-1");
    expect(() =>
      AnalysisReleaseMetadataSchema.parse({
        ...metadata,
        preliminary_caveat: null,
      }),
    ).toThrow();
    expect(
      AnalysisArtifactMetadataSchema.parse({
        artifact_id: "manifest",
        kind: "manifest",
        schema_version: "1",
        media_type: "application/json",
        record_count: 1,
        byte_size: 100,
        byte_hash: hash,
        content_hash: hash,
        url: `https://eleccionesabiertas.co/artifacts/${hash}.json`,
        status: "available",
        status_reasons: [],
      }).status,
    ).toBe("available");
  });

  it("preserves observed zero separately from unavailable data", () => {
    expect(MetricValueSchema.parse({ value: 0, status: "observed" })).toEqual({
      value: 0,
      status: "observed",
    });
    expect(
      MetricValueSchema.parse({ value: null, status: "unavailable" }),
    ).toEqual({
      value: null,
      status: "unavailable",
    });
    expect(() =>
      MetricValueSchema.parse({ value: 0, status: "unavailable" }),
    ).toThrow();
  });

  it("keeps candidate historical summaries unknown, contextual, and caveated", () => {
    const provenance = {
      data_version: "historical-preview",
      source_type: "contextual_baseline" as const,
      legal_status: "context_only" as const,
      source_url: "https://official.example/archive.zip",
      retrieved_at: "2026-08-04T12:00:00Z",
      content_hash: "a".repeat(64),
      parser_version: "historical-v2",
      transform_version: "rollup-v2",
      methodology_version: null,
    };
    const summary = {
      election_slug: "presidencia-2022-round-2",
      election_name: { es: "Presidencia 2022", en: "2022 presidency" },
      round: 2,
      election_date: "2022-06-19",
      data_version: "historical-preview",
      release_status: "candidate" as const,
      release_class: "context_only" as const,
      synthetic: false as const,
      completion: { status: "unknown" as const, reason: "No denominator" },
      registered_electors: { value: null, status: "unavailable" as const },
      voters: { value: null, status: "unavailable" as const },
      valid_votes: { value: null, status: "unavailable" as const },
      blank_votes: { value: null, status: "unavailable" as const },
      null_votes: { value: null, status: "unavailable" as const },
      unmarked_votes: { value: null, status: "unavailable" as const },
      national_categories: [
        {
          category_key: "party:candidate",
          category_code: "candidate",
          category_name: "Opción publicada",
          category_kind: "published_mmv_category",
          votes: 0,
          status: "observed" as const,
          provenance,
        },
      ],
      coverage: {
        status: "unknown" as const,
        observed_geographies: 1,
        observed_result_facts: 1,
        observed_category_facts: 1,
        reason: "Observed rows are not a denominator",
      },
      reconciliation: {
        status: "not_run" as const,
        checked_facts: 0,
        exceptions: 0,
      },
      provenance: { ...provenance, preview_caveat: "Candidate preview" },
    };
    expect(ContextElectionSummarySchema.parse(summary).completion.status).toBe(
      "unknown",
    );
    expect(() =>
      ContextElectionSummarySchema.parse({
        ...summary,
        provenance: { ...provenance, preview_caveat: undefined },
      }),
    ).toThrow();
    expect(() =>
      ContextElectionSummarySchema.parse({
        ...summary,
        completion: { expected: 0, reported: 0, percent: 0 },
      }),
    ).toThrow();
  });

  it("requires same-origin Parquet dataset downloads", () => {
    const dataset = {
      id: "historical-parquet",
      title: { es: "Datos", en: "Data" },
      format: "parquet" as const,
      url: "/api/v1/releases/r/elections/e/datasets/d/download",
      schema_url: null,
      record_count: 0,
      byte_size: 0,
      content_hash: "a".repeat(64),
      filters: { data_version: "r" },
    };
    expect(PackagedDatasetSchema.parse(dataset).record_count).toBe(0);
    expect(() =>
      PackagedDatasetSchema.parse({
        ...dataset,
        url: "https://untrusted.example/data.parquet",
      }),
    ).toThrow();
  });

  it("validates the active fixture manifest", () => {
    const manifestPath = resolve(
      process.cwd(),
      "../../data/manifests/fixture-2026-round2-v1.json",
    );
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as unknown;
    expect(ReleaseManifestSchema.parse(manifest).release_id).toBe(
      "fixture-2026-round2-v1",
    );
  });

  it("accepts an E-14 index entry and rejects document rather than index provenance", () => {
    const base = {
      id: "e14-1",
      mesa_id: "mesa-1",
      document_type: "e14_delegate" as const,
      official_url: "https://official.example/e14.pdf",
      source_index_url: "https://official.example/index.json",
      source_index_hash: "a".repeat(64),
      indexed_at: "2026-08-03T12:00:00Z",
      index_status: "indexed" as const,
      provenance: {
        data_version: "r1",
        source_type: "e14_delegate" as const,
        legal_status: "documentary_evidence" as const,
        source_url: "https://official.example/index.json",
        retrieved_at: "2026-08-03T12:00:00Z",
        content_hash: "a".repeat(64),
        parser_version: "index-v1",
        transform_version: "index-v1",
        methodology_version: null,
      },
    };
    expect(EvidenceDocumentSchema.parse(base).index_status).toBe("indexed");
    expect(() =>
      EvidenceDocumentSchema.parse({
        ...base,
        provenance: { ...base.provenance, source_url: base.official_url },
      }),
    ).toThrow();
  });

  it("marks a geographic sample as distinct from full collection", () => {
    expect(
      GeographicCollectionCoverageSchema.parse({
        status: "sample_limited",
        expected_polling_places: 1,
        retrieved_polling_places: 1,
        expected_mesas: 122020,
        retrieved_mesas: 36,
      }),
    ).toMatchObject({ status: "sample_limited" });
    expect(
      GeographicCollectionCoverageSchema.parse({
        status: "full_scope",
        expected_polling_places: 1,
        retrieved_polling_places: 1,
        expected_mesas: 122020,
        retrieved_mesas: 36,
      }),
    ).toMatchObject({ status: "full_scope" });
  });

  it("keeps statistical signals from claiming votes and rejects duplicate components", () => {
    const component = {
      component_type: "peer_distribution" as const,
      points: 10,
      observed_value: 0.5,
      comparator: "all gates",
      calculation: "EB predictive tail",
      peer_definition: "leave-one-out peers",
      limitations: { es: "Guía", en: "Lead" },
      source_links: ["https://official.example/mesa"],
      evidence_artifact_hash: null,
      evidence_artifact_kind: null,
      analyzer_output_hash: "a".repeat(64),
      family_id: "release-1|presidencia-2026-r2|pre_count|turnout|none",
      expected_family_count: 100,
      expected_family_digest: "b".repeat(64),
      cohort_hash: "c".repeat(64),
      input_artifact_hash: "d".repeat(64),
      code_hash: "e".repeat(64),
      method_hash: "f".repeat(64),
      p_value: 0.001,
      q_value: 0.01,
      family_rank: 1,
      family_size: 100,
      adjustment_method: "benjamini-yekutieli" as const,
      analysis: {
        kind: "peer_distribution" as const,
        eligibility: "ineligible" as const,
        reason: "synthetic_fixture_not_production_eligible",
        public_point_eligible: false,
        analyzer_reason: "synthetic_fixture_not_production_eligible",
        observed_rate: { value: 0.5, status: "observed" as const },
        expected_rate: { value: null, status: "unknown" as const },
        comparator: "all gates",
        peer_definition: "leave-one-out peers",
        peer_count: { value: 100, status: "observed" as const },
        expected_unit_count: { value: 100, status: "observed" as const },
        expected_unit_digest: "b".repeat(64),
        standardized_residual: { value: null, status: "unknown" as const },
        effect_pp: { value: null, status: "unknown" as const },
        raw_p: { value: 0.001, status: "observed" as const },
        adjusted_q: { value: 0.01, status: "observed" as const },
        fit_method: "EB predictive tail",
        family_id: "release-1|presidencia-2026-r2|pre_count|turnout|none",
        cohort_hash: "c".repeat(64),
        input_hash: "d".repeat(64),
        output_hash: "a".repeat(64),
        code_hash: "e".repeat(64),
        method_hash: "f".repeat(64),
        analyzer_methodology_version: "peer-beta-binomial-eb-v3",
      },
    };
    const signal = {
      id: "signal-1",
      mesa_id: "mesa-1",
      score: 10,
      tier: "no_review_signals" as const,
      affected_vote_estimate: null,
      methodology_version: "peer-beta-binomial-eb-v2",
      components: [component],
      disclosure: { es: "Divulgación", en: "Disclosure" },
      provenance: {
        data_version: "release-1",
        source_type: "pre_count" as const,
        legal_status: "preliminary" as const,
        source_url: "https://official.example/source",
        retrieved_at: "2026-08-03T12:00:00Z",
        content_hash: "a".repeat(64),
        parser_version: "parser-v1",
        transform_version: "transform-v1",
        methodology_version: "peer-beta-binomial-eb-v2",
      },
    };
    expect(ReviewSignalSchema.parse(signal).affected_vote_estimate).toBeNull();
    expect(() =>
      ReviewSignalSchema.parse({ ...signal, affected_vote_estimate: 1 }),
    ).toThrow();
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        components: [component, component],
      }),
    ).toThrow();
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        tier: "statistical_or_coverage_issue",
      }),
    ).toThrow();
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        components: [{ ...component, analyzer_output_hash: null }],
      }),
    ).toThrow();
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        components: [{ ...component, p_value: 0.01 }],
      }),
    ).toThrow();
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        components: [{ ...component, family_size: 101 }],
      }),
    ).toThrow();
    const spatialComponent = {
      ...component,
      component_type: "spatial_cluster" as const,
      analyzer_mesa_id: "mesa-1",
      analysis_unit_id: "mesa-1",
      peer_residual_artifact_hash: "1".repeat(64),
      peer_methodology_version: "peer-beta-binomial-eb-v3",
      coordinate_source_url: "https://official.example/coordinates",
      coordinate_source_hash: "2".repeat(64),
      coordinate_accuracy_m: 10,
      coordinate_grain: "mesa" as const,
      analysis: {
        kind: "spatial_cluster" as const,
        eligibility: "ineligible" as const,
        reason: "synthetic_fixture_not_production_eligible",
        analysis_unit_id: "mesa-1",
        analysis_grain: "mesa" as const,
        neighbor_ids: ["mesa-2"],
        signal_kind: "positive_cluster",
        local_statistic: { value: 0.5, status: "observed" as const },
        local_residual: { value: null, status: "unknown" as const },
        raw_p: { value: 0.001, status: "observed" as const },
        adjusted_q: { value: 0.01, status: "observed" as const },
        seed: 1,
        permutations: { value: 999, status: "observed" as const },
        expected_unit_count: { value: 100, status: "observed" as const },
        expected_unit_digest: "b".repeat(64),
        family_id: "release-1|presidencia-2026-r2|pre_count|turnout|none",
        mesa_id: "mesa-1",
        peer_residual_hash: "1".repeat(64),
        input_hash: "d".repeat(64),
        output_hash: "a".repeat(64),
        code_hash: "e".repeat(64),
        method_hash: "f".repeat(64),
        geocode_source_url: "https://official.example/coordinates",
        geocode_source_hash: "2".repeat(64),
        coordinate_accuracy_m: 10,
        analyzer_methodology_version: "spatial-local-randomization-v1",
        peer_methodology_version: "peer-beta-binomial-eb-v3",
        analysis_unit_digest: null,
        expected_mesa_count: { value: null, status: "unknown" as const },
        expected_mesa_digest: null,
        mesa_membership_digest: null,
        expected_mesa_membership_digest: null,
      },
    };
    expect(
      ReviewSignalSchema.parse({
        ...signal,
        components: [spatialComponent],
      }).components.at(0)?.coordinate_grain,
    ).toBe("mesa");
    expect(() =>
      ReviewSignalSchema.parse({
        ...signal,
        components: [
          { ...spatialComponent, peer_residual_artifact_hash: undefined },
        ],
      }),
    ).toThrow();
    expect(
      ReviewSignalSchema.parse({
        ...signal,
        id: "signal-none",
        score: 0,
        tier: "no_review_signals",
        components: [],
      }).tier,
    ).toBe("no_review_signals");
  });

  it("freezes review tier boundaries at 14 and 15", () => {
    expect(reviewSignalTier(0)).toBe("no_review_signals");
    expect(reviewSignalTier(14)).toBe("no_review_signals");
    expect(reviewSignalTier(15)).toBe("statistical_or_coverage_issue");
  });

  it("keeps the pipeline outcome artifact separate from API release scope", () => {
    const artifact = {
      status: "not_evaluable" as const,
      evaluable: false,
      issues: [{ code: "observation_missing", record_ids: [] }],
      scope: null,
      outcome_source: null,
      leader_id: null,
      runner_up_id: null,
      leader_votes: null,
      runner_up_votes: null,
      observed_margin_votes: null,
      verified_record_ids: null,
      unresolved_record_ids: null,
      verified_affected_votes: null,
      verified_margin_shift_bound: null,
      unresolved_affected_vote_upper_bound: null,
      unresolved_margin_shift_upper_bound: null,
      combined_affected_vote_upper_bound: null,
      combined_margin_shift_upper_bound: null,
      verified_margin_headroom: null,
      combined_margin_headroom: null,
      tie_possible_from_verified: null,
      lead_change_possible_from_verified: null,
      tie_possible_including_unresolved: null,
      lead_change_possible_including_unresolved: null,
      source_links: [],
      evidence_hash: null,
      output_hash: "a".repeat(64),
      methodology_version: "outcome-sensitivity-v3.0.0" as const,
      calculation: "Authenticated documentary bounds only.",
      limitations: ["No typed replay was available."],
    };
    expect(OutcomeSensitivityArtifactSchema.parse(artifact).evaluable).toBe(
      false,
    );
    expect(() =>
      OutcomeSensitivityArtifactSchema.parse({
        ...artifact,
        release_id: "release-1",
      }),
    ).toThrow();
    expect(
      OutcomeSensitivitySchema.parse({
        ...artifact,
        release_id: "release-1",
        election_slug: "election-1",
        data_version: "release-1",
        margin_shift_factor: 2,
      }).status,
    ).toBe("not_evaluable");
    expect(() =>
      OutcomeSensitivityArtifactSchema.parse({
        ...artifact,
        verified_margin_shift_bound: 1,
      }),
    ).toThrow();
  });
});
