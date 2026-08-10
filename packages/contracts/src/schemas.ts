import { z } from "zod";

import {
  E14_INDEX_STATUSES,
  ANOMALY_TYPES,
  EXPLANATION_STATUSES,
  GEOGRAPHY_LEVELS,
  LEGAL_STATUSES,
  METRIC_STATUSES,
  RELEASE_STATUSES,
  SIGNAL_COMPONENTS,
  SIGNAL_TIERS,
  SOURCE_TYPES,
} from "./enums";

export const ANALYTICAL_DISCLOSURE_ES =
  "Una anomalía prioriza revisión y no es una probabilidad ni un hallazgo de fraude. Una explicación posterior no elimina la anomalía detectada; la ausencia de explicación en los datos disponibles tampoco prueba fraude ni error.";
export const ANALYTICAL_DISCLOSURE_EN =
  "An anomaly prioritizes review and is not a probability or finding of fraud. A later explanation does not erase the detected anomaly; absence of an explanation in available data does not prove fraud or error.";

export const LocalizedTextSchema = z.object({
  es: z.string().min(1),
  en: z.string().min(1),
});

/** A release/election pair; candidate previews are never implied to be published. */
export const ReleaseElectionRefSchema = z
  .object({
    release_id: z.string().min(1),
    election_slug: z.string().min(1),
    name_es: z.string().min(1),
    name_en: z.string().min(1),
    round: z.number().int().positive(),
    election_date: z.string().date(),
    status: z.enum(RELEASE_STATUSES),
    release_class: z.literal("context_only").optional(),
    methodology_version: z.string().nullable(),
    release_manifest_hash: z.string().regex(/^[a-f0-9]{64}$/),
    exposure_approved_at: z.iso.datetime().nullable(),
    sources: z.array(
      z.object({
        id: z.string().min(1),
        source_type: z.enum(SOURCE_TYPES),
        legal_status: z.enum(LEGAL_STATUSES),
        source_url: z.string().url(),
        content_hash: z.string().regex(/^[a-f0-9]{64}$/),
        retrieved_at: z.iso.datetime().nullable().optional(),
        media_type: z.string().min(1).nullable().optional(),
        byte_size: z.number().int().nonnegative().nullable().optional(),
        parser_version: z.string().min(1).nullable().optional(),
        transform_version: z.string().min(1).nullable().optional(),
        published_grain: z
          .enum(["mesa", "place", "municipality", "department", "national"])
          .nullable()
          .optional(),
        coverage: z
          .object({
            expected: z.number().int().nonnegative(),
            retrieved: z.number().int().nonnegative(),
            parsed: z.number().int().nonnegative(),
            missing: z.number().int().nonnegative(),
            ambiguous: z.number().int().nonnegative(),
            excluded: z.number().int().nonnegative(),
          })
          .nullable()
          .optional(),
      }),
    ),
  })
  .superRefine((release, context) => {
    if (
      release.status === "candidate" &&
      release.exposure_approved_at !== null
    ) {
      context.addIssue({
        code: "custom",
        message: "Candidate releases cannot claim approved public exposure",
      });
    }
    if (
      release.release_class === "context_only" &&
      release.sources.some((source) => source.legal_status !== "context_only")
    ) {
      context.addIssue({
        code: "custom",
        message: "Context-only release sources must remain context-only",
      });
    }
  });

export const CategoryResultSchema = z.object({
  category_key: z.string().min(1),
  category_code: z.string().min(1),
  category_name: z.string().min(1),
  category_kind: z.string().min(1),
  votes: z.number().int().nonnegative().nullable(),
  status: z.enum(METRIC_STATUSES),
  provenance: z.object({
    data_version: z.string().min(1),
    source_type: z.enum(SOURCE_TYPES),
    legal_status: z.enum(LEGAL_STATUSES),
    source_url: z.string().url(),
    retrieved_at: z.iso.datetime(),
    content_hash: z.string().regex(/^[a-f0-9]{64}$/),
    parser_version: z.string().min(1),
    transform_version: z.string().min(1),
    methodology_version: z.string().nullable(),
  }),
});

export const CategoryPageSchema = z.object({
  items: z.array(CategoryResultSchema),
  page: z.object({
    next_cursor: z.string().nullable(),
    has_more: z.boolean(),
    limit: z.number().int().positive(),
  }),
  data_version: z.string().min(1),
  sparse_category_semantics: z.string().min(1),
});

export const NormalizedCategoryResultSchema = CategoryResultSchema.superRefine(
  (category, context) => {
    if ((category.status === "observed") !== (category.votes !== null)) {
      context.addIssue({
        code: "custom",
        message:
          "Observed category votes require an integer; other states require null",
      });
    }
  },
);

export const NormalizedCategoryPageSchema = z.object({
  items: z.array(NormalizedCategoryResultSchema),
  page: z.object({
    next_cursor: z.string().nullable(),
    has_more: z.boolean(),
    limit: z.number().int().positive(),
  }),
  data_version: z.string().min(1),
  sparse_category_semantics: z.string().min(1),
});

export const ScopedGeographySchema = z.object({
  id: z.string().min(1),
  level: z.enum(GEOGRAPHY_LEVELS),
  code: z.string().min(1),
  name: z.string().min(1),
  parent_id: z.string().nullable(),
  canonical_path: z.string().optional(),
  has_published_facts: z.boolean().optional(),
  authoritative_coordinates: z
    .object({
      latitude: z.number().min(-90).max(90),
      longitude: z.number().min(-180).max(180),
      quality: z.enum(["authoritative", "approximate"]),
      source_url: z.string().url(),
    })
    .nullable()
    .optional(),
});

export const ScopedGeographyResponseSchema = z.object({
  item: ScopedGeographySchema,
  data_version: z.string().min(1),
});

export const ScopedGeographyPathResponseSchema = z.object({
  items: z.array(ScopedGeographySchema),
  data_version: z.string().min(1),
});

export const GeographyChildPageSchema = z.object({
  items: z.array(ScopedGeographySchema),
  page: z.object({
    next_cursor: z.string().nullable(),
    has_more: z.boolean(),
    limit: z.number().int().positive(),
  }),
  data_version: z.string().min(1),
});

export const MetricValueSchema = z
  .object({
    value: z.number().int().nonnegative().nullable(),
    status: z.enum(METRIC_STATUSES),
  })
  .superRefine((metric, context) => {
    if (metric.status === "observed" && metric.value === null) {
      context.addIssue({
        code: "custom",
        message: "Observed metrics require a numeric value",
      });
    }
    if (metric.status !== "observed" && metric.value !== null) {
      context.addIssue({
        code: "custom",
        message: "Non-observed metrics must use null",
      });
    }
  });

export const ProvenanceSchema = z.object({
  data_version: z.string().min(1),
  source_type: z.enum(SOURCE_TYPES),
  legal_status: z.enum(LEGAL_STATUSES),
  source_url: z.string().url(),
  retrieved_at: z.iso.datetime(),
  content_hash: z.string().regex(/^[a-f0-9]{64}$/),
  parser_version: z.string().min(1),
  transform_version: z.string().min(1),
  methodology_version: z.string().min(1).nullable(),
});

const historicalComparisonBase = {
  data_version: z.string().min(1),
  baseline_data_version: z.string().min(1),
  geography_id: z.string().min(1),
  requested_grain: z.enum(GEOGRAPHY_LEVELS),
};
const historicalComparisonReason = z.enum([
  "missing_geography_crosswalk",
  "geography_crosswalk_unapproved",
  "missing_semantic_crosswalk",
  "semantic_crosswalk_unapproved",
  "no_compatible_facts",
  "no_approved_longitudinal_crosswalk",
  "missing_approved_context_crosswalk",
]);
const historicalComparisonItem = z.object({
  category_key: z.string().min(1),
  baseline_category_key: z.string().min(1),
  category_kind: z.string().min(1),
  semantic_crosswalk_version: z.string().min(1),
  current_fact_id: z.string().min(1),
  current_value: z.number().int().nonnegative().nullable(),
  current_status: z.enum(METRIC_STATUSES),
  current_provenance: z.lazy(() => ProvenanceSchema),
  baseline_fact_id: z.string().min(1),
  baseline_value: z.number().int().nonnegative().nullable(),
  baseline_status: z.enum(METRIC_STATUSES),
  baseline_provenance: z.lazy(() => ProvenanceSchema),
});

export const HistoricalComparisonSchema = z
  .discriminatedUnion("comparison_status", [
    z.object({
      ...historicalComparisonBase,
      comparison_status: z.literal("not_comparable"),
      reason: historicalComparisonReason,
      eligible_for_integrity_analysis: z.boolean().nullable().optional(),
      items: z.array(historicalComparisonItem).max(0).default([]),
    }),
    z.object({
      ...historicalComparisonBase,
      comparison_status: z.literal("descriptive_context_only"),
      reason: historicalComparisonReason.nullable().optional(),
      eligible_for_integrity_analysis: z.literal(false),
      comparison_key: z.string().min(1).nullable().optional(),
      geography_crosswalk_version: z.string().min(1).nullable().optional(),
      geography_approved_at: z.iso.datetime().nullable().optional(),
      baseline_geography_id: z.string().min(1).nullable().optional(),
      items: z.array(historicalComparisonItem),
    }),
    z.object({
      ...historicalComparisonBase,
      comparison_status: z.literal("comparable"),
      reason: historicalComparisonReason.nullable().optional(),
      eligible_for_integrity_analysis: z.literal(true),
      comparison_key: z.string().min(1),
      geography_crosswalk_version: z.string().min(1),
      geography_approved_at: z.iso.datetime(),
      baseline_geography_id: z.string().min(1),
      items: z.array(historicalComparisonItem),
    }),
  ])
  .superRefine((comparison, context) => {
    if (comparison.comparison_status !== "descriptive_context_only") return;
    if (comparison.reason && comparison.items.length > 0) {
      context.addIssue({
        code: "custom",
        message: "Uncrosswalked descriptive context cannot emit compared facts",
      });
    }
    if (
      !comparison.reason &&
      (!comparison.comparison_key ||
        !comparison.geography_crosswalk_version ||
        !comparison.geography_approved_at ||
        !comparison.baseline_geography_id)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Compared descriptive context requires an approved geography crosswalk",
      });
    }
  });

export const CandidateSchema = z.object({
  id: z.string().min(1),
  ballot_number: z.number().int().positive().nullable(),
  name: LocalizedTextSchema,
  short_name: LocalizedTextSchema,
});

export const CandidateResultSchema = z.object({
  candidate_id: z.string().min(1),
  votes: MetricValueSchema,
});

export const CandidateSummarySchema = z.object({
  candidate: CandidateSchema,
  votes: MetricValueSchema,
  share: z.number().min(0).max(1).nullable(),
});

export const ResultFactSchema = z.object({
  id: z.string().min(1),
  election_slug: z.string().min(1),
  geography_id: z.string().min(1),
  geography_level: z.enum(GEOGRAPHY_LEVELS),
  mesa_id: z.string().min(1).nullable(),
  registered_electors: MetricValueSchema,
  voters: MetricValueSchema,
  valid_votes: MetricValueSchema,
  blank_votes: MetricValueSchema,
  null_votes: MetricValueSchema,
  unmarked_votes: MetricValueSchema,
  candidates: z.array(CandidateResultSchema),
  provenance: ProvenanceSchema,
});

export const ScopedMesaSchema = z.object({
  id: z.string().min(1),
  display_number: z.string().min(1),
  polling_place_id: z.string().min(1),
  municipality_id: z.string().min(1),
  department_id: z.string().min(1),
  geography_path: z.array(ScopedGeographySchema),
  results: z.array(ResultFactSchema).max(200),
  data_version: z.string().min(1),
});

export const CoverageSchema = z
  .object({
    expected: z.number().int().nonnegative(),
    retrieved: z.number().int().nonnegative(),
    parsed: z.number().int().nonnegative(),
    missing: z.number().int().nonnegative(),
    ambiguous: z.number().int().nonnegative(),
    excluded: z.number().int().nonnegative(),
  })
  .superRefine((coverage, context) => {
    const accounted =
      coverage.parsed +
      coverage.missing +
      coverage.ambiguous +
      coverage.excluded;
    if (accounted !== coverage.expected) {
      context.addIssue({
        code: "custom",
        message: "parsed + missing + ambiguous + excluded must equal expected",
      });
    }
    if (
      coverage.parsed > coverage.retrieved ||
      coverage.retrieved > coverage.expected
    ) {
      context.addIssue({
        code: "custom",
        message: "Coverage counts must be monotonic",
      });
    }
  });

export const GeographicCollectionCoverageSchema = z
  .object({
    status: z.enum(["national_only", "sample_limited", "full_scope"]),
    expected_polling_places: z.number().int().nonnegative(),
    retrieved_polling_places: z.number().int().nonnegative(),
    expected_mesas: z.number().int().nonnegative(),
    retrieved_mesas: z.number().int().nonnegative(),
  })
  .superRefine((coverage, context) => {
    if (
      coverage.retrieved_polling_places > coverage.expected_polling_places ||
      coverage.retrieved_mesas > coverage.expected_mesas
    ) {
      context.addIssue({
        code: "custom",
        message: "Geographic collection counts must be monotonic",
      });
    }
  });

export const SourceObjectSchema = z.object({
  id: z.string().min(1),
  source_type: z.enum(SOURCE_TYPES),
  legal_status: z.enum(LEGAL_STATUSES),
  source_url: z.string().url(),
  retrieved_at: z.iso.datetime(),
  content_hash: z.string().regex(/^[a-f0-9]{64}$/),
  media_type: z.string().min(1),
  byte_size: z.number().int().nonnegative(),
  parser_version: z.string().min(1),
  transform_version: z.string().min(1),
  published_grain: z
    .enum(["mesa", "place", "municipality", "department", "national"])
    .optional(),
  coverage: CoverageSchema,
});

export const DatasetSchema = z.object({
  id: z.string().min(1),
  title: LocalizedTextSchema,
  format: z.enum(["csv", "parquet", "json"]),
  url: z.string().url(),
  schema_url: z.string().url(),
  record_count: z.number().int().nonnegative(),
  byte_size: z.number().int().nonnegative(),
  content_hash: z.string().regex(/^[a-f0-9]{64}$/),
  filters: z.record(z.string(), z.string()),
});

export const ReleaseManifestSchema = z.object({
  schema_version: z.literal("1.0.0"),
  release_id: z.string().min(1),
  election_slug: z.string().min(1),
  data_version: z.string().min(1),
  status: z.enum(RELEASE_STATUSES),
  synthetic: z.boolean(),
  created_at: z.iso.datetime(),
  methodology_version: z.string().min(1),
  parser_versions: z.record(z.string(), z.string()),
  git_commit: z.string().min(1),
  sources: z.array(SourceObjectSchema).min(1),
  datasets: z.array(DatasetSchema).min(1),
  aggregate_reconciled: z.boolean(),
  statistical_validation_passed: z.boolean(),
  wording_validation_passed: z.boolean(),
  notes: LocalizedTextSchema,
});

export const ElectionSummarySchema = z.object({
  election_slug: z.string().min(1),
  election_name: LocalizedTextSchema,
  round: z.number().int(),
  election_date: z.string().date(),
  data_version: z.string().min(1),
  release_status: z.enum(RELEASE_STATUSES),
  synthetic: z.boolean(),
  completion: z.object({
    expected: z.number().int().nonnegative(),
    reported: z.number().int().nonnegative(),
    percent: z.number().min(0).max(1),
  }),
  registered_electors: MetricValueSchema,
  voters: MetricValueSchema,
  turnout: z.number().min(0).max(1).nullable(),
  valid_votes: MetricValueSchema,
  blank_votes: MetricValueSchema,
  null_votes: MetricValueSchema,
  unmarked_votes: MetricValueSchema,
  candidates: z.array(CandidateSummarySchema),
  coverage: CoverageSchema,
  geographic_collection_coverage: GeographicCollectionCoverageSchema.optional(),
  reconciliation: z.object({
    status: z.enum(["passed", "blocked", "not_run"]),
    checked_facts: z.number().int().nonnegative(),
    exceptions: z.number().int().nonnegative(),
  }),
  provenance: ProvenanceSchema,
});

export const PreviewProvenanceSchema = ProvenanceSchema.extend({
  preview_caveat: z.string().min(1).nullable().optional(),
});

export const UnknownCompletionSchema = z.object({
  status: z.literal("unknown"),
  reason: z.string().min(1),
});

export const UnknownContextCoverageSchema = z.object({
  status: z.literal("unknown"),
  observed_geographies: z.number().int().nonnegative(),
  observed_result_facts: z.number().int().nonnegative(),
  observed_category_facts: z.number().int().nonnegative(),
  reason: z.string().min(1).nullable().optional(),
});

export const ContextElectionSummarySchema = z
  .object({
    election_slug: z.string().min(1),
    election_name: LocalizedTextSchema,
    round: z.number().int().positive(),
    election_date: z.string().date(),
    data_version: z.string().min(1),
    release_status: z.enum(["candidate", "published", "withdrawn"]),
    release_class: z.literal("context_only"),
    synthetic: z.literal(false),
    completion: UnknownCompletionSchema,
    registered_electors: MetricValueSchema,
    voters: MetricValueSchema,
    valid_votes: MetricValueSchema,
    blank_votes: MetricValueSchema,
    null_votes: MetricValueSchema,
    unmarked_votes: MetricValueSchema,
    national_categories: z.array(NormalizedCategoryResultSchema),
    coverage: UnknownContextCoverageSchema,
    reconciliation: z.object({
      status: z.enum(["passed", "blocked", "not_run"]),
      checked_facts: z.number().int().nonnegative(),
      exceptions: z.number().int().nonnegative(),
    }),
    provenance: PreviewProvenanceSchema,
  })
  .superRefine((summary, context) => {
    if (
      summary.release_status === "candidate" &&
      !summary.provenance.preview_caveat
    ) {
      context.addIssue({
        code: "custom",
        message: "Candidate context summaries require a preview caveat",
      });
    }
    if (
      summary.provenance.data_version !== summary.data_version ||
      summary.provenance.legal_status !== "context_only"
    ) {
      context.addIssue({
        code: "custom",
        message: "Summary provenance must remain in its context-only release",
      });
    }
    if (
      summary.national_categories.some(
        (category) =>
          category.provenance.data_version !== summary.data_version ||
          category.provenance.legal_status !== "context_only",
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "National categories must retain context-only provenance",
      });
    }
  });

export const PackagedDatasetSchema = z.object({
  id: z.string().regex(/^[A-Za-z0-9._-]+$/),
  title: LocalizedTextSchema,
  format: z.literal("parquet"),
  url: z.string().regex(/^\/api\/v1\//),
  schema_url: z.string().url().nullable(),
  record_count: z.number().int().nonnegative(),
  byte_size: z.number().int().nonnegative(),
  content_hash: z.string().regex(/^[a-f0-9]{64}$/),
  filters: z.record(z.string(), z.string()),
});

const sha256Schema = z.string().regex(/^[a-f0-9]{64}$/);
const statisticalComponents = new Set(["peer_distribution", "spatial_cluster"]);
const componentPoints: Record<(typeof SIGNAL_COMPONENTS)[number], number> = {
  verified_accounting_failure: 100,
  conflicting_official_records: 100,
  documentary_difference_major: 70,
  documentary_difference_minor: 45,
  document_missing_duplicated_ambiguous: 25,
  peer_distribution: 10,
  spatial_cluster: 10,
};

export function reviewSignalTier(score: number): (typeof SIGNAL_TIERS)[number] {
  if (score >= 70) return "documentary_review_prioritized";
  if (score >= 45) return "documentary_comparison_recommended";
  if (score >= 15) return "statistical_or_coverage_issue";
  return "no_review_signals";
}

/** A number with a state, so a missing analytical value cannot become zero. */
export const SignalNumberSchema = z
  .object({ value: z.number().nullable(), status: z.enum(METRIC_STATUSES) })
  .superRefine((value, context) => {
    if ((value.status === "observed") !== (value.value !== null)) {
      context.addIssue({
        code: "custom",
        message:
          "Observed analytical values require a number; other states require null",
      });
    }
  });

export const SignalCountSchema = z
  .object({
    value: z.number().int().nonnegative().nullable(),
    status: z.enum(METRIC_STATUSES),
  })
  .superRefine((value, context) => {
    if ((value.status === "observed") !== (value.value !== null)) {
      context.addIssue({
        code: "custom",
        message:
          "Observed analytical counts require an integer; other states require null",
      });
    }
  });

export const DocumentarySignalAnalysisSchema = z.object({
  kind: z.literal("documentary"),
  eligibility: z.enum(["eligible", "ineligible"]),
  reason: z.string().min(1).nullable(),
  evidence_artifact_hash: sha256Schema,
  evidence_artifact_kind: z.enum(["reconciliation_result", "document_review"]),
});

export const PeerSignalAnalysisSchema = z.object({
  kind: z.literal("peer_distribution"),
  eligibility: z.enum(["eligible", "ineligible"]),
  reason: z.string().min(1).nullable(),
  public_point_eligible: z.boolean(),
  analyzer_reason: z.string().min(1).nullable(),
  observed_rate: SignalNumberSchema,
  expected_rate: SignalNumberSchema,
  comparator: z.string().min(1),
  peer_definition: z.string().min(1),
  peer_count: SignalCountSchema,
  expected_unit_count: SignalCountSchema,
  expected_unit_digest: sha256Schema,
  standardized_residual: SignalNumberSchema,
  effect_pp: SignalNumberSchema,
  raw_p: SignalNumberSchema,
  adjusted_q: SignalNumberSchema,
  fit_method: z.string().min(1),
  family_id: z.string().min(1),
  cohort_hash: sha256Schema,
  input_hash: sha256Schema,
  output_hash: sha256Schema,
  code_hash: sha256Schema,
  method_hash: sha256Schema,
  analyzer_methodology_version: z.string().min(1),
});

export const SpatialSignalAnalysisSchema = z.object({
  kind: z.literal("spatial_cluster"),
  eligibility: z.enum(["eligible", "ineligible"]),
  reason: z.string().min(1).nullable(),
  analysis_unit_id: z.string().min(1),
  analysis_grain: z.enum(["mesa", "polling_place"]),
  neighbor_ids: z.array(z.string().min(1)),
  signal_kind: z.string().min(1),
  local_statistic: SignalNumberSchema,
  local_residual: SignalNumberSchema,
  raw_p: SignalNumberSchema,
  adjusted_q: SignalNumberSchema,
  seed: z.number().int().nullable(),
  permutations: SignalCountSchema,
  expected_unit_count: SignalCountSchema,
  expected_unit_digest: sha256Schema,
  family_id: z.string().min(1),
  mesa_id: z.string().min(1),
  peer_residual_hash: sha256Schema,
  input_hash: sha256Schema,
  output_hash: sha256Schema,
  code_hash: sha256Schema,
  method_hash: sha256Schema,
  geocode_source_url: z.string().url(),
  geocode_source_hash: sha256Schema,
  coordinate_accuracy_m: z.number().positive(),
  analyzer_methodology_version: z.string().min(1),
  peer_methodology_version: z.string().min(1),
  analysis_unit_digest: sha256Schema.nullable(),
  expected_mesa_count: SignalCountSchema,
  expected_mesa_digest: sha256Schema.nullable(),
  mesa_membership_digest: sha256Schema.nullable(),
  expected_mesa_membership_digest: sha256Schema.nullable(),
});

export const SignalAnalysisSchema = z.discriminatedUnion("kind", [
  DocumentarySignalAnalysisSchema,
  PeerSignalAnalysisSchema,
  SpatialSignalAnalysisSchema,
]);

export const SignalComponentSchema = z
  .object({
    component_type: z.enum(SIGNAL_COMPONENTS),
    points: z.number().int().min(0).max(100),
    observed_value: z.number().nullable(),
    comparator: z.string().min(1),
    calculation: z.string().min(1),
    peer_definition: z.string().min(1).nullable(),
    limitations: LocalizedTextSchema,
    source_links: z.array(z.string().url()).min(1),
    evidence_artifact_hash: sha256Schema.nullable(),
    evidence_artifact_kind: z
      .enum(["reconciliation_result", "document_review"])
      .nullable(),
    analyzer_output_hash: sha256Schema.nullable(),
    family_id: z.string().min(1).nullable(),
    expected_family_count: z.number().int().positive().nullable(),
    expected_family_digest: sha256Schema.nullable(),
    cohort_hash: sha256Schema.nullable(),
    input_artifact_hash: sha256Schema.nullable(),
    code_hash: sha256Schema.nullable(),
    method_hash: sha256Schema.nullable(),
    p_value: z.number().min(0).max(0.001).nullable(),
    q_value: z.number().min(0).max(0.05).nullable(),
    family_rank: z.number().int().positive().nullable(),
    family_size: z.number().int().positive().nullable(),
    adjustment_method: z.literal("benjamini-yekutieli").nullable(),
    analyzer_mesa_id: z.string().min(1).nullable().optional(),
    analysis_unit_id: z.string().min(1).nullable().optional(),
    peer_residual_artifact_hash: sha256Schema.nullable().optional(),
    peer_methodology_version: z.string().min(1).nullable().optional(),
    coordinate_source_url: z.string().url().nullable().optional(),
    coordinate_source_hash: sha256Schema.nullable().optional(),
    coordinate_accuracy_m: z.number().positive().nullable().optional(),
    coordinate_grain: z.enum(["mesa", "polling_place"]).nullable().optional(),
    analysis: SignalAnalysisSchema,
  })
  .superRefine((component, context) => {
    if (component.points !== componentPoints[component.component_type]) {
      context.addIssue({
        code: "custom",
        message: "Signal component points do not match the frozen methodology",
      });
    }
    const expectedAnalysisKind =
      component.component_type === "peer_distribution"
        ? "peer_distribution"
        : component.component_type === "spatial_cluster"
          ? "spatial_cluster"
          : "documentary";
    if (component.analysis.kind !== expectedAnalysisKind) {
      context.addIssue({
        code: "custom",
        message: "Component type and typed analysis kind must match",
      });
    }
    const statisticalFields = [
      "analyzer_output_hash",
      "family_id",
      "expected_family_count",
      "expected_family_digest",
      "cohort_hash",
      "input_artifact_hash",
      "code_hash",
      "method_hash",
      "p_value",
      "q_value",
      "family_rank",
      "family_size",
      "adjustment_method",
    ] as const;
    const isStatistical = statisticalComponents.has(component.component_type);
    const evidenceFields = [
      component.evidence_artifact_hash,
      component.evidence_artifact_kind,
    ];
    if (isStatistical && evidenceFields.some((value) => value !== null)) {
      context.addIssue({
        code: "custom",
        message:
          "Statistical components cannot claim documentary evidence artifacts",
      });
    }
    if (!isStatistical && evidenceFields.some((value) => value === null)) {
      context.addIssue({
        code: "custom",
        message:
          "Documentary components require an authenticated evidence artifact",
      });
    }
    const populated = statisticalFields.filter(
      (field) => component[field] !== null,
    );
    if (isStatistical && populated.length !== statisticalFields.length) {
      context.addIssue({
        code: "custom",
        message:
          "Statistical components require a complete typed analyzer binding",
      });
    }
    if (!isStatistical && populated.length !== 0) {
      context.addIssue({
        code: "custom",
        message:
          "Documentary components cannot claim a statistical analyzer binding",
      });
    }
    const optionalAnalyzerFields = [
      "analyzer_mesa_id",
      "analysis_unit_id",
      "peer_residual_artifact_hash",
      "peer_methodology_version",
      "coordinate_source_url",
      "coordinate_source_hash",
      "coordinate_accuracy_m",
      "coordinate_grain",
    ] as const;
    if (
      !isStatistical &&
      optionalAnalyzerFields.some((field) => component[field] != null)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Documentary components cannot claim optional analyzer provenance",
      });
    }
    const spatialFields = [
      "analysis_unit_id",
      "peer_residual_artifact_hash",
      "peer_methodology_version",
      "coordinate_source_url",
      "coordinate_source_hash",
      "coordinate_accuracy_m",
      "coordinate_grain",
    ] as const;
    const populatedSpatial = spatialFields.filter(
      (field) => component[field] != null,
    );
    if (
      populatedSpatial.length !== 0 &&
      (component.component_type !== "spatial_cluster" ||
        populatedSpatial.length !== spatialFields.length)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Spatial analyzer provenance must be complete and spatial-only",
      });
    }
    if (
      component.family_rank !== null &&
      component.family_size !== null &&
      component.family_rank > component.family_size
    ) {
      context.addIssue({
        code: "custom",
        message: "Statistical family rank cannot exceed family size",
      });
    }
    if (
      component.family_size !== null &&
      component.expected_family_count !== null &&
      component.family_size > component.expected_family_count
    ) {
      context.addIssue({
        code: "custom",
        message: "Adjusted family size cannot exceed expected family coverage",
      });
    }
    if (
      isStatistical &&
      component.p_value !== null &&
      component.q_value !== null &&
      (component.q_value < component.p_value ||
        component.p_value > 0.001 ||
        component.q_value > 0.05)
    ) {
      context.addIssue({
        code: "custom",
        message: "Statistical components must pass the frozen p/q gates",
      });
    }
  });

export const ReviewSignalSchema = z
  .object({
    id: z.string().min(1),
    mesa_id: z.string().min(1),
    score: z.number().int().min(0).max(100),
    tier: z.enum(SIGNAL_TIERS),
    affected_vote_estimate: z.number().int().nonnegative().nullable(),
    methodology_version: z.string().min(1),
    components: z.array(SignalComponentSchema),
    disclosure: LocalizedTextSchema,
    provenance: ProvenanceSchema,
  })
  .superRefine((signal, context) => {
    const componentTypes = signal.components.map(
      (component) => component.component_type,
    );
    if (new Set(componentTypes).size !== componentTypes.length) {
      context.addIssue({
        code: "custom",
        message: "Review signals cannot duplicate component types",
      });
    }
    const expectedTier = reviewSignalTier(signal.score);
    if (signal.tier !== expectedTier) {
      context.addIssue({
        code: "custom",
        message: "Review signal tier does not match its score",
      });
    }
    const deterministicPoints = Math.max(
      0,
      ...signal.components
        .filter(
          (component) => !statisticalComponents.has(component.component_type),
        )
        .map((component) => component.points),
    );
    const statisticalPoints = Math.min(
      20,
      signal.components
        .filter((component) =>
          statisticalComponents.has(component.component_type),
        )
        .reduce((total, component) => total + component.points, 0),
    );
    if (
      signal.score !== Math.min(100, deterministicPoints + statisticalPoints)
    ) {
      context.addIssue({
        code: "custom",
        message: "Review signal score does not match its components",
      });
    }
    const statisticalOnly = componentTypes.every((component) =>
      ["peer_distribution", "spatial_cluster"].includes(component),
    );
    if (
      statisticalOnly &&
      signal.affected_vote_estimate !== null &&
      signal.affected_vote_estimate !== 0
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Statistical-only signals cannot claim an affected-vote estimate",
      });
    }
  });

export const OutcomeGeographicScopeSchema = z
  .object({
    level: z.enum(["mesa", "place", "municipality", "department", "national"]),
    key: z.array(z.string().min(1)).min(1),
  })
  .superRefine((scope, context) => {
    const expectedLength = {
      mesa: 4,
      place: 3,
      municipality: 2,
      department: 1,
      national: 1,
    }[scope.level];
    if (
      scope.key.length !== expectedLength ||
      (scope.level === "national" && scope.key[0] !== "CO")
    ) {
      context.addIssue({
        code: "custom",
        message: "Outcome geographic key does not match its level",
      });
    }
  });

export const OutcomeSourceScopeSchema = z
  .object({
    source_id: z.string().min(1),
    fact_grain: z.enum([
      "mesa",
      "place",
      "municipality",
      "department",
      "national",
    ]),
    source_type: z.enum(SOURCE_TYPES),
    legal_status: z.enum(LEGAL_STATUSES),
  })
  .superRefine((source, context) => {
    const legalStatusBySourceType = {
      final_declaration: "controlling_final",
      scrutiny: "official_scrutiny",
      e14_delegate: "documentary_evidence",
      e14_transmission: "documentary_evidence",
      pre_count: "preliminary",
      contextual_baseline: "context_only",
    } as const;
    if (source.legal_status !== legalStatusBySourceType[source.source_type]) {
      context.addIssue({
        code: "custom",
        message: "Outcome source type and legal status are incompatible",
      });
    }
  });

export const OutcomeSensitivityIssueSchema = z.object({
  code: z.string().min(1),
  record_ids: z.array(z.string().min(1)),
});

const nullableOutcomeCountSchema = z.number().int().nonnegative().nullable();

const outcomeSensitivityArtifactShape = {
  status: z.enum([
    "not_evaluable",
    "robust_within_evaluated_bounds",
    "tie_within_verified_bound",
    "lead_change_within_verified_bound",
    "tie_only_with_unresolved_bound",
    "lead_change_only_with_unresolved_bound",
  ]),
  evaluable: z.boolean(),
  issues: z.array(OutcomeSensitivityIssueSchema),
  scope: OutcomeGeographicScopeSchema.nullable(),
  outcome_source: OutcomeSourceScopeSchema.nullable(),
  leader_id: z.string().min(1).nullable(),
  runner_up_id: z.string().min(1).nullable(),
  leader_votes: nullableOutcomeCountSchema,
  runner_up_votes: nullableOutcomeCountSchema,
  observed_margin_votes: nullableOutcomeCountSchema,
  verified_record_ids: z.array(z.string().min(1)).nullable(),
  unresolved_record_ids: z.array(z.string().min(1)).nullable(),
  verified_affected_votes: nullableOutcomeCountSchema,
  verified_margin_shift_bound: nullableOutcomeCountSchema,
  unresolved_affected_vote_upper_bound: nullableOutcomeCountSchema,
  unresolved_margin_shift_upper_bound: nullableOutcomeCountSchema,
  combined_affected_vote_upper_bound: nullableOutcomeCountSchema,
  combined_margin_shift_upper_bound: nullableOutcomeCountSchema,
  verified_margin_headroom: z.number().int().nullable(),
  combined_margin_headroom: z.number().int().nullable(),
  tie_possible_from_verified: z.boolean().nullable(),
  lead_change_possible_from_verified: z.boolean().nullable(),
  tie_possible_including_unresolved: z.boolean().nullable(),
  lead_change_possible_including_unresolved: z.boolean().nullable(),
  source_links: z.array(z.string().url()),
  evidence_hash: sha256Schema.nullable(),
  output_hash: sha256Schema,
  methodology_version: z.literal("outcome-sensitivity-v3.0.0"),
  calculation: z.string().min(1),
  limitations: z.array(z.string().min(1)),
};

const outcomeSensitivityArtifactBaseSchema = z.strictObject(
  outcomeSensitivityArtifactShape,
);

function outcomeSensitivityArtifactIssues(
  outcome: z.infer<typeof outcomeSensitivityArtifactBaseSchema>,
): string[] {
  const issues: string[] = [];
  if (outcome.evaluable !== (outcome.status !== "not_evaluable")) {
    issues.push("Outcome sensitivity evaluable flag must match status");
  }
  const topTwo = [
    outcome.leader_id,
    outcome.runner_up_id,
    outcome.leader_votes,
    outcome.runner_up_votes,
    outcome.observed_margin_votes,
  ];
  const presentTopTwo = topTwo.filter((value) => value !== null).length;
  if (presentTopTwo !== 0 && presentTopTwo !== topTwo.length) {
    issues.push(
      "Observed top-two outcome fields must be all present or all null",
    );
  }
  if (
    outcome.leader_votes !== null &&
    outcome.runner_up_votes !== null &&
    outcome.observed_margin_votes !== null &&
    (outcome.leader_votes < outcome.runner_up_votes ||
      outcome.observed_margin_votes !==
        outcome.leader_votes - outcome.runner_up_votes)
  ) {
    issues.push("Observed outcome margin does not match the top-two totals");
  }
  const derived = [
    outcome.verified_affected_votes,
    outcome.verified_margin_shift_bound,
    outcome.unresolved_affected_vote_upper_bound,
    outcome.unresolved_margin_shift_upper_bound,
    outcome.combined_affected_vote_upper_bound,
    outcome.combined_margin_shift_upper_bound,
    outcome.verified_margin_headroom,
    outcome.combined_margin_headroom,
    outcome.tie_possible_from_verified,
    outcome.lead_change_possible_from_verified,
    outcome.tie_possible_including_unresolved,
    outcome.lead_change_possible_including_unresolved,
  ];
  if (!outcome.evaluable) {
    if (
      derived.some((value) => value !== null) ||
      outcome.evidence_hash !== null ||
      outcome.issues.length === 0
    ) {
      issues.push(
        "Non-evaluable outcome artifacts cannot publish decision bounds",
      );
    }
    return issues;
  }
  if (
    presentTopTwo !== topTwo.length ||
    outcome.scope === null ||
    outcome.outcome_source === null ||
    outcome.verified_record_ids === null ||
    outcome.unresolved_record_ids === null ||
    derived.some((value) => value === null) ||
    outcome.evidence_hash === null ||
    outcome.source_links.length === 0 ||
    outcome.issues.length !== 0
  ) {
    issues.push(
      "Evaluable outcome artifacts require complete typed decision data",
    );
    return issues;
  }
  const verifiedAffected = outcome.verified_affected_votes as number;
  const verifiedShift = outcome.verified_margin_shift_bound as number;
  const unresolvedAffected =
    outcome.unresolved_affected_vote_upper_bound as number;
  const unresolvedShift = outcome.unresolved_margin_shift_upper_bound as number;
  const combinedAffected = outcome.combined_affected_vote_upper_bound as number;
  const combinedShift = outcome.combined_margin_shift_upper_bound as number;
  const margin = outcome.observed_margin_votes as number;
  if (
    combinedAffected !== verifiedAffected + unresolvedAffected ||
    combinedShift !== verifiedShift + unresolvedShift
  ) {
    issues.push("Combined outcome bounds do not equal their typed components");
  }
  if (
    verifiedShift > 2 * verifiedAffected ||
    unresolvedShift > 2 * unresolvedAffected
  ) {
    issues.push("Margin-shift bounds exceed the frozen two-times factor");
  }
  const expectedStatus =
    verifiedShift > margin
      ? "lead_change_within_verified_bound"
      : combinedShift > margin
        ? "lead_change_only_with_unresolved_bound"
        : verifiedShift >= margin
          ? "tie_within_verified_bound"
          : combinedShift >= margin
            ? "tie_only_with_unresolved_bound"
            : "robust_within_evaluated_bounds";
  if (
    outcome.status !== expectedStatus ||
    outcome.verified_margin_headroom !== margin - verifiedShift ||
    outcome.combined_margin_headroom !== margin - combinedShift ||
    outcome.tie_possible_from_verified !== verifiedShift >= margin ||
    outcome.lead_change_possible_from_verified !== verifiedShift > margin ||
    outcome.tie_possible_including_unresolved !== combinedShift >= margin ||
    outcome.lead_change_possible_including_unresolved !== combinedShift > margin
  ) {
    issues.push(
      "Outcome status, headroom, or tie/change flags are inconsistent",
    );
  }
  return issues;
}

export const OutcomeSensitivityArtifactSchema =
  outcomeSensitivityArtifactBaseSchema.superRefine((outcome, context) => {
    for (const message of outcomeSensitivityArtifactIssues(outcome)) {
      context.addIssue({ code: "custom", message });
    }
  });

export const OutcomeSensitivitySchema = z
  .strictObject({
    release_id: z.string().min(1),
    election_slug: z.string().min(1),
    data_version: z.string().min(1),
    margin_shift_factor: z.literal(2),
    ...outcomeSensitivityArtifactShape,
  })
  .superRefine((outcome, context) => {
    if (outcome.release_id !== outcome.data_version) {
      context.addIssue({
        code: "custom",
        message: "Outcome sensitivity data_version must equal release_id",
      });
    }
    for (const message of outcomeSensitivityArtifactIssues(outcome)) {
      context.addIssue({ code: "custom", message });
    }
  });

export const GeographySchema = z.object({
  id: z.string().min(1),
  level: z.enum(GEOGRAPHY_LEVELS),
  code: z.string().min(1),
  name: z.string().min(1),
  parent_id: z.string().min(1).nullable(),
  authoritative_coordinates: z
    .object({
      latitude: z.number().min(-90).max(90),
      longitude: z.number().min(-180).max(180),
      quality: z.enum(["authoritative", "approximate"]),
      source_url: z.string().url(),
    })
    .nullable(),
});

export const EvidenceDocumentSchema = z
  .object({
    id: z.string().min(1),
    mesa_id: z.string().min(1),
    document_type: z.enum(["e14_delegate", "e14_transmission"]),
    official_url: z.string().url(),
    source_index_url: z.string().url(),
    source_index_hash: z.string().regex(/^[a-f0-9]{64}$/),
    indexed_at: z.string().datetime({ offset: true }),
    index_status: z.enum(E14_INDEX_STATUSES),
    provenance: ProvenanceSchema,
  })
  .superRefine((document, context) => {
    if (document.provenance.source_url !== document.source_index_url) {
      context.addIssue({
        code: "custom",
        message:
          "E-14 provenance must identify the immutable source index, not the document",
      });
    }
    if (document.provenance.content_hash !== document.source_index_hash) {
      context.addIssue({
        code: "custom",
        message: "E-14 provenance hash must equal the source index hash",
      });
    }
  });

export const ExplanationMetadataSchema = z
  .object({
    status: z.enum(EXPLANATION_STATUSES),
    preregistration_hash: sha256Schema.nullable(),
    available_data_hash: sha256Schema.nullable(),
    reviewed_at: z.string().datetime({ offset: true }).nullable(),
    quantitative_effect: SignalNumberSchema,
    quantitative_p_value: SignalNumberSchema,
    notes: LocalizedTextSchema.nullable(),
  })
  .superRefine((value, context) => {
    if (
      (value.status === "explained" ||
        value.status === "partially_explained") &&
      value.preregistration_hash === null
    ) {
      context.addIssue({
        code: "custom",
        message: "Explanations require preregistration",
      });
    }
    if (
      value.status === "non_evaluable" &&
      (value.preregistration_hash !== null ||
        value.available_data_hash !== null ||
        value.reviewed_at !== null ||
        value.notes !== null)
    ) {
      context.addIssue({
        code: "custom",
        message: "Non-evaluable explanations have no review evidence",
      });
    }
  });

const analyticalDisclosureSchema = z.object({
  es: z.literal(ANALYTICAL_DISCLOSURE_ES),
  en: z.literal(ANALYTICAL_DISCLOSURE_EN),
});

export const AnalysisReleaseMetadataSchema = z
  .strictObject({
    analysis_release_id: z.string().min(1),
    methodology_version: z.string().min(1),
    source_release_id: z.string().min(1),
    election_slug: z.string().min(1),
    exposure_tier: z.enum(["preliminary_research", "certified_public"]),
    preliminary_caveat: LocalizedTextSchema.nullable(),
    artifact_status: z.enum([
      "available",
      "research_preview",
      "not_evaluable",
      "unavailable",
      "withheld",
    ]),
    evaluable: z.boolean(),
    status_reasons: z.array(z.string().min(1)),
    canonical_input_hash: sha256Schema,
    manifest_hash: sha256Schema,
    provenance_hash: sha256Schema,
    generated_at: z.string().datetime({ offset: true }),
    approved_at: z.string().datetime({ offset: true }),
  })
  .superRefine((value, context) => {
    if (
      value.exposure_tier === "preliminary_research" &&
      (value.preliminary_caveat === null ||
        !value.preliminary_caveat.es ||
        !value.preliminary_caveat.en)
    ) {
      context.addIssue({
        code: "custom",
        message: "Preliminary analysis requires a bilingual caveat",
      });
    }
    if (
      value.exposure_tier === "certified_public" &&
      value.preliminary_caveat !== null
    ) {
      context.addIssue({
        code: "custom",
        message: "Certified analysis cannot carry preliminary framing",
      });
    }
    if (
      value.evaluable &&
      ["not_evaluable", "unavailable", "withheld"].includes(
        value.artifact_status,
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Evaluability and artifact status disagree",
      });
    }
  });

export const AnalysisOutcomeSensitivitySchema = OutcomeSensitivitySchema.and(
  z.strictObject({ analysis_release: AnalysisReleaseMetadataSchema }),
);

export const AnalysisAnomalyComponentSchema = z.strictObject({
  component_id: z.string().min(1),
  component_type: z.string().min(1),
  evidence_type: z.string().min(1),
  points: z.number().int().min(0).max(100),
  value: z.number().nullable(),
  unit: z.string().nullable(),
  public_payload: z.record(z.string(), z.unknown()),
  provenance_hash: sha256Schema,
});

export const AnalysisAnomalySchema = z
  .object({
    id: z.string().min(1),
    mesa_id: z.string().min(1),
    anomaly_types: z.array(z.enum(ANOMALY_TYPES)).min(1),
    is_anomaly: z.boolean(),
    audit_priority_score: z.number().int().min(0).max(100),
    explanation: ExplanationMetadataSchema,
    minimum_ballot_edits: SignalCountSchema,
    minimum_ballot_edits_status: z.enum(["evaluable", "not_evaluable"]),
    minimum_ballot_edits_reason: z.string().min(1).nullable(),
    components: z.array(SignalComponentSchema),
    research_preview: z.boolean(),
    ineligible_reasons: z.array(z.string().min(1)),
    methodology_version: z.string().min(1),
    disclosure: analyticalDisclosureSchema,
    provenance: ProvenanceSchema,
    analysis_release: AnalysisReleaseMetadataSchema,
    family: z.string().min(1),
    evidence_tier: z.enum([
      "descriptive",
      "deterministic",
      "research_preview",
      "independently_validated",
      "non_evaluable",
    ]),
    evaluability: z.enum(["evaluable", "not_evaluable", "unavailable"]),
    public_evidence: z.record(z.string(), z.unknown()),
    calculations: z.record(z.string(), z.unknown()),
    limitations: z.array(z.string().min(1)),
    provenance_hash: sha256Schema,
    typed_components: z.array(AnalysisAnomalyComponentSchema),
  })
  .superRefine((value, context) => {
    if (new Set(value.anomaly_types).size !== value.anomaly_types.length) {
      context.addIssue({
        code: "custom",
        message: "Anomaly types must be unique",
      });
    }
    if (
      (value.minimum_ballot_edits_status === "evaluable") !==
      (value.minimum_ballot_edits.status === "observed")
    ) {
      context.addIssue({
        code: "custom",
        message: "Ballot edit status must be explicit",
      });
    }
    if (
      (value.evidence_tier === "research_preview" ||
        value.evidence_tier === "non_evaluable") &&
      value.audit_priority_score !== 0
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Research-preview and non-evaluable evidence has zero priority",
      });
    }
    const statisticalTypes = new Set([
      "peer_distribution",
      "spatial",
      "spatial_cluster",
    ]);
    const statisticalPoints = value.typed_components
      .filter((component) => statisticalTypes.has(component.component_type))
      .reduce((sum, component) => sum + component.points, 0);
    if (statisticalPoints > 20) {
      context.addIssue({
        code: "custom",
        message: "Statistical evidence is capped at twenty priority points",
      });
    }
    if (
      value.typed_components.some(
        (component) =>
          component.evidence_type === "research_preview" &&
          component.points !== 0,
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Research-preview components contribute zero public points",
      });
    }
    if (
      value.analysis_release.exposure_tier === "preliminary_research" &&
      [...value.components, ...value.typed_components].some(
        (component) =>
          statisticalTypes.has(component.component_type) &&
          component.points !== 0,
      )
    ) {
      context.addIssue({
        code: "custom",
        message:
          "Preliminary statistical evidence contributes zero public points",
      });
    }
  });

export const AnalysisAnomalyPageSchema = z.object({
  items: z.array(AnalysisAnomalySchema),
  page: z.object({
    next_cursor: z.string().nullable(),
    has_more: z.boolean(),
    limit: z.number().int().positive(),
  }),
  data_version: z.string().min(1),
  methodology_version: z.string().min(1),
  disclosure: analyticalDisclosureSchema,
  analysis_release: AnalysisReleaseMetadataSchema,
});

export const AnalysisSummarySchema = z.object({
  election_slug: z.string().min(1),
  data_version: z.string().min(1),
  methodology_version: z.string().min(1),
  total_records_evaluated: SignalCountSchema,
  anomaly_count: SignalCountSchema,
  anomaly_counts: z.record(z.enum(ANOMALY_TYPES), SignalCountSchema),
  missingness: CoverageSchema,
  research_preview: z.boolean(),
  ineligible_reasons: z.array(z.string().min(1)),
  disclosure: analyticalDisclosureSchema,
  provenance: ProvenanceSchema,
  analysis_release: AnalysisReleaseMetadataSchema,
});

export const AnalysisReportSchema = z.object({
  report_kind: z.enum(["model_diagnostics", "validation", "local_sensitivity"]),
  status: z.enum([
    "available",
    "research_preview",
    "ineligible",
    "not_evaluable",
  ]),
  research_preview: z.boolean(),
  ineligible_reasons: z.array(z.string().min(1)),
  methodology_version: z.string().min(1),
  artifact_hash: sha256Schema.nullable(),
  missingness: CoverageSchema,
  provenance: ProvenanceSchema,
  disclosure: analyticalDisclosureSchema,
  metrics: z.record(z.string(), SignalNumberSchema),
  analysis_release: AnalysisReleaseMetadataSchema,
});

export const AnalysisArtifactMetadataSchema = z
  .strictObject({
    artifact_id: z.string().min(1),
    kind: z.string().min(1),
    schema_version: z.string().min(1),
    media_type: z.enum([
      "application/json",
      "application/schema+json",
      "application/vnd.apache.parquet",
      "text/plain",
    ]),
    record_count: z.number().int().nonnegative(),
    byte_size: z.number().int().nonnegative(),
    byte_hash: sha256Schema,
    content_hash: sha256Schema,
    url: z.string().url().nullable(),
    status: z.enum(["available", "not_evaluable", "unavailable", "withheld"]),
    status_reasons: z.array(z.string().min(1)),
  })
  .superRefine((value, context) => {
    if (value.status === "available" && value.url === null) {
      context.addIssue({
        code: "custom",
        message: "Available analysis artifacts require an immutable URL",
      });
    }
    if (value.status !== "available" && value.url !== null) {
      context.addIssue({
        code: "custom",
        message: "Unavailable analysis artifacts cannot expose a URL",
      });
    }
    if (value.url !== null && !value.url.includes(value.byte_hash)) {
      context.addIssue({
        code: "custom",
        message: "Analysis artifact URL must contain its byte hash",
      });
    }
  });

export const AnalysisArtifactPageSchema = z.strictObject({
  items: z.array(AnalysisArtifactMetadataSchema),
  analysis_release: AnalysisReleaseMetadataSchema,
});

export const AnalysisArtifactDetailSchema = z.strictObject({
  item: AnalysisArtifactMetadataSchema,
  analysis_release: AnalysisReleaseMetadataSchema,
});

export type MetricValue = z.infer<typeof MetricValueSchema>;
export type Provenance = z.infer<typeof ProvenanceSchema>;
export type ResultFact = z.infer<typeof ResultFactSchema>;
export type ReleaseElectionRef = z.infer<typeof ReleaseElectionRefSchema>;
export type ContextElectionSummary = z.infer<
  typeof ContextElectionSummarySchema
>;
export type NormalizedCategoryResult = z.infer<
  typeof NormalizedCategoryResultSchema
>;
export type PackagedDataset = z.infer<typeof PackagedDatasetSchema>;
export type ScopedGeography = z.infer<typeof ScopedGeographySchema>;
export type ScopedMesa = z.infer<typeof ScopedMesaSchema>;
export type ReleaseManifest = z.infer<typeof ReleaseManifestSchema>;
export type ReviewSignal = z.infer<typeof ReviewSignalSchema>;
export type EvidenceDocument = z.infer<typeof EvidenceDocumentSchema>;
export type AnalysisAnomaly = z.infer<typeof AnalysisAnomalySchema>;
export type AnalysisAnomalyComponent = z.infer<
  typeof AnalysisAnomalyComponentSchema
>;
export type AnalysisSummary = z.infer<typeof AnalysisSummarySchema>;
export type AnalysisReport = z.infer<typeof AnalysisReportSchema>;
export type AnalysisReleaseMetadata = z.infer<
  typeof AnalysisReleaseMetadataSchema
>;
export type AnalysisArtifactMetadata = z.infer<
  typeof AnalysisArtifactMetadataSchema
>;
export type AnalysisOutcomeSensitivity = z.infer<
  typeof AnalysisOutcomeSensitivitySchema
>;
