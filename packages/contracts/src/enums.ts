export const SOURCE_TYPES = [
  "final_declaration",
  "scrutiny",
  "e14_delegate",
  "e14_transmission",
  "pre_count",
  "contextual_baseline",
] as const;

export type SourceType = (typeof SOURCE_TYPES)[number];

export const LEGAL_STATUSES = [
  "controlling_final",
  "official_scrutiny",
  "documentary_evidence",
  "preliminary",
  "context_only",
] as const;

export type LegalStatus = (typeof LEGAL_STATUSES)[number];

export const METRIC_STATUSES = [
  "observed",
  "unknown",
  "unavailable",
  "not_applicable",
] as const;

export type MetricStatus = (typeof METRIC_STATUSES)[number];

export const GEOGRAPHY_LEVELS = [
  "national",
  "department",
  "municipality",
  "zone",
  "polling_place",
  "mesa",
] as const;

export type GeographyLevel = (typeof GEOGRAPHY_LEVELS)[number];

export const RELEASE_STATUSES = [
  "fixture",
  "candidate",
  "published",
  "withdrawn",
] as const;

export type ReleaseStatus = (typeof RELEASE_STATUSES)[number];

/** E-14 documents are external references only; no binary is retrieved. */
export const E14_INDEX_STATUSES = [
  "indexed",
  "unavailable",
  "ambiguous",
] as const;

export type E14IndexStatus = (typeof E14_INDEX_STATUSES)[number];

export const SIGNAL_TIERS = [
  "documentary_review_prioritized",
  "documentary_comparison_recommended",
  "statistical_or_coverage_issue",
  "no_review_signals",
] as const;

export type SignalTier = (typeof SIGNAL_TIERS)[number];

export const SIGNAL_COMPONENTS = [
  "verified_accounting_failure",
  "conflicting_official_records",
  "documentary_difference_major",
  "documentary_difference_minor",
  "document_missing_duplicated_ambiguous",
  "peer_distribution",
  "spatial_cluster",
] as const;

export type SignalComponentType = (typeof SIGNAL_COMPONENTS)[number];

export const ANOMALY_TYPES = [
  "structural_arithmetic",
  "identity_coverage",
  "cross_source_documentary",
  "peer_distribution",
  "spatial",
] as const;

export type AnomalyType = (typeof ANOMALY_TYPES)[number];

export const EXPLANATION_STATUSES = [
  "explained",
  "partially_explained",
  "no_explanation_found_in_available_data",
  "non_evaluable",
] as const;

export type ExplanationStatus = (typeof EXPLANATION_STATUSES)[number];
