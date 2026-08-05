import type { components as FrozenApiComponents } from "../../../packages/contracts/src/generated/api";

import {
  getPublicReleaseSelection,
  PublicApiError,
  publicApiJson,
  publicNormalizedApiConfigured,
  type PublicExplorerFilters,
  type PublicReleaseRef,
} from "@/data/fixture-adapter";

type S = FrozenApiComponents["schemas"];

export type AnalysisSummary = S["AnalysisSummary"];
export type AnalysisAnomaly = S["AnalysisAnomaly"];
export type AnalysisAnomalyPage = S["AnalysisAnomalyPage"];
export type AnalysisReport = S["AnalysisReport"];
export type OutcomeSensitivity = S["OutcomeSensitivity"];
export type SignalComponent = S["SignalComponent"];
export type AnalysisAnomalyType = AnalysisAnomaly["anomaly_types"][number];
export type AnalysisReportKind = AnalysisReport["report_kind"];

export const ANALYSIS_ANOMALY_TYPES = [
  "structural_arithmetic",
  "identity_coverage",
  "cross_source_documentary",
  "peer_distribution",
  "spatial",
] as const satisfies readonly AnalysisAnomalyType[];

const REPORT_KINDS = [
  "model_diagnostics",
  "validation",
  "local_sensitivity",
] as const satisfies readonly AnalysisReportKind[];

export type PublicAnalysisFilters = Pick<
  PublicExplorerFilters,
  "release" | "election" | "cursor"
> & {
  anomalyType?: AnalysisAnomalyType;
};

export type PublicAnalysisReady = {
  status: "ready";
  releases: PublicReleaseRef[];
  selected: PublicReleaseRef;
  filters: PublicAnalysisFilters;
  summary: AnalysisSummary;
  anomalies: AnalysisAnomalyPage;
  reports: Partial<Record<AnalysisReportKind, AnalysisReport>>;
  outcomeSensitivity: OutcomeSensitivity | null;
};

export type PublicAnalysisState =
  | PublicAnalysisReady
  | {
      status: "fixture" | "no_release" | "unavailable" | "error";
      releases: PublicReleaseRef[];
      selected?: PublicReleaseRef;
      filters: PublicAnalysisFilters;
      error?: { status?: number; message: string };
    };

export type PublicAnomalyDetailState =
  | {
      status: "ready";
      releases: PublicReleaseRef[];
      selected: PublicReleaseRef;
      anomaly: AnalysisAnomaly;
    }
  | {
      status: "fixture" | "no_release" | "not_found" | "error";
      releases: PublicReleaseRef[];
      selected?: PublicReleaseRef;
      error?: { status?: number; message: string };
    };

function prefixFor(selected: PublicReleaseRef) {
  return `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
}

function errorView(error: unknown) {
  return {
    status: error instanceof PublicApiError ? error.status : undefined,
    message:
      error instanceof Error
        ? error.message
        : "The published analysis service is unavailable.",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isLocalizedText(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.es === "string" &&
    typeof value.en === "string"
  );
}

function isSignalNumber(value: unknown) {
  return (
    isRecord(value) &&
    (typeof value.value === "number" || value.value === null) &&
    ["observed", "unknown", "unavailable", "not_applicable"].includes(
      String(value.status),
    )
  );
}

function isProvenance(value: unknown) {
  return (
    isRecord(value) &&
    typeof value.data_version === "string" &&
    typeof value.source_type === "string" &&
    typeof value.legal_status === "string" &&
    typeof value.source_url === "string" &&
    typeof value.retrieved_at === "string" &&
    typeof value.content_hash === "string" &&
    typeof value.parser_version === "string" &&
    typeof value.transform_version === "string"
  );
}

function isSignalComponent(value: unknown) {
  if (!isRecord(value) || !isRecord(value.analysis)) return false;
  return (
    [
      "verified_accounting_failure",
      "conflicting_official_records",
      "documentary_difference_major",
      "documentary_difference_minor",
      "document_missing_duplicated_ambiguous",
      "peer_distribution",
      "spatial_cluster",
    ].includes(String(value.component_type)) &&
    typeof value.points === "number" &&
    (typeof value.observed_value === "number" ||
      value.observed_value === null) &&
    typeof value.comparator === "string" &&
    typeof value.calculation === "string" &&
    (typeof value.peer_definition === "string" ||
      value.peer_definition === null) &&
    isLocalizedText(value.limitations) &&
    isStringArray(value.source_links) &&
    ["documentary", "peer_distribution", "spatial_cluster"].includes(
      String(value.analysis.kind),
    )
  );
}

/**
 * The frozen OpenAPI currently types the anomaly-detail response as unknown.
 * Narrow it at the web boundary and fail closed instead of trusting a cast.
 */
export function isAnalysisAnomaly(value: unknown): value is AnalysisAnomaly {
  if (!isRecord(value) || !isRecord(value.explanation)) return false;
  return (
    typeof value.id === "string" &&
    value.id.length > 0 &&
    typeof value.mesa_id === "string" &&
    value.mesa_id.length > 0 &&
    Array.isArray(value.anomaly_types) &&
    value.anomaly_types.length > 0 &&
    value.anomaly_types.every((item) =>
      ANALYSIS_ANOMALY_TYPES.includes(item as AnalysisAnomalyType),
    ) &&
    typeof value.is_anomaly === "boolean" &&
    Number.isInteger(value.audit_priority_score) &&
    Number(value.audit_priority_score) >= 0 &&
    Number(value.audit_priority_score) <= 100 &&
    [
      "explained",
      "partially_explained",
      "no_explanation_found_in_available_data",
      "non_evaluable",
    ].includes(String(value.explanation.status)) &&
    isSignalNumber(value.explanation.quantitative_effect) &&
    isSignalNumber(value.explanation.quantitative_p_value) &&
    isSignalNumber(value.minimum_ballot_edits) &&
    ["evaluable", "not_evaluable"].includes(
      String(value.minimum_ballot_edits_status),
    ) &&
    Array.isArray(value.components) &&
    value.components.every(isSignalComponent) &&
    typeof value.research_preview === "boolean" &&
    isStringArray(value.ineligible_reasons) &&
    typeof value.methodology_version === "string" &&
    isLocalizedText(value.disclosure) &&
    isProvenance(value.provenance)
  );
}

function assertFrozenScope(
  selected: PublicReleaseRef,
  summary: AnalysisSummary,
  anomalies: AnalysisAnomalyPage,
  reports: Partial<Record<AnalysisReportKind, AnalysisReport>>,
  outcome: OutcomeSensitivity | null,
) {
  const expectedVersion = selected.release_id;
  const expectedMethodology = summary.methodology_version;
  if (
    summary.election_slug !== selected.election_slug ||
    summary.data_version !== expectedVersion ||
    anomalies.data_version !== expectedVersion
  ) {
    throw new Error("Analysis resources crossed immutable release scope.");
  }
  if (
    anomalies.methodology_version !== expectedMethodology ||
    (selected.methodology_version !== null &&
      selected.methodology_version !== expectedMethodology)
  ) {
    throw new Error("Analysis resources crossed methodology versions.");
  }
  for (const anomaly of anomalies.items) {
    if (!isAnalysisAnomaly(anomaly)) {
      throw new Error(
        "The anomaly resource does not match the frozen contract.",
      );
    }
    if (
      anomaly.methodology_version !== expectedMethodology ||
      anomaly.provenance.data_version !== expectedVersion
    ) {
      throw new Error("An anomaly crossed immutable release scope.");
    }
  }
  for (const [kind, report] of Object.entries(reports)) {
    if (
      report.report_kind !== kind ||
      report.methodology_version !== expectedMethodology ||
      report.provenance.data_version !== expectedVersion
    ) {
      throw new Error("An analytical report crossed immutable release scope.");
    }
  }
  if (
    outcome &&
    (outcome.release_id !== expectedVersion ||
      outcome.election_slug !== selected.election_slug ||
      outcome.data_version !== expectedVersion)
  ) {
    throw new Error("Outcome sensitivity crossed immutable release scope.");
  }
}

async function optionalJson<T>(pathname: string): Promise<T | null> {
  try {
    return await publicApiJson<T>(pathname);
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) return null;
    throw error;
  }
}

export async function getPublicAnalysis(
  filters: PublicAnalysisFilters = {},
): Promise<PublicAnalysisState> {
  if (!publicNormalizedApiConfigured()) {
    return { status: "fixture", releases: [], filters };
  }
  let releases: PublicReleaseRef[] = [];
  let selected: PublicReleaseRef | undefined;
  try {
    const selection = await getPublicReleaseSelection(filters);
    releases = selection.releases;
    selected = selection.selected;
    if (!selected) return { status: "no_release", releases, filters };

    const prefix = prefixFor(selected);
    const anomalyQuery = new URLSearchParams({ limit: "25" });
    if (filters.cursor) anomalyQuery.set("cursor", filters.cursor);
    if (filters.anomalyType)
      anomalyQuery.set("anomaly_type", filters.anomalyType);

    const [summary, anomalies, reportValues, outcomeSensitivity] =
      await Promise.all([
        optionalJson<AnalysisSummary>(`${prefix}/analysis/summary`),
        optionalJson<AnalysisAnomalyPage>(
          `${prefix}/analysis/anomalies?${anomalyQuery}`,
        ),
        Promise.all(
          REPORT_KINDS.map(
            async (kind) =>
              [
                kind,
                await optionalJson<AnalysisReport>(
                  `${prefix}/analysis/${kind}`,
                ),
              ] as const,
          ),
        ),
        optionalJson<OutcomeSensitivity>(`${prefix}/outcome-sensitivity`),
      ]);
    if (!summary || !anomalies) {
      return {
        status: "unavailable",
        releases,
        selected,
        filters,
        error: { status: 404, message: "Published analysis is unavailable." },
      };
    }
    const reports = Object.fromEntries(
      reportValues.filter(
        (entry): entry is readonly [AnalysisReportKind, AnalysisReport] =>
          entry[1] !== null,
      ),
    ) as Partial<Record<AnalysisReportKind, AnalysisReport>>;
    assertFrozenScope(
      selected,
      summary,
      anomalies,
      reports,
      outcomeSensitivity,
    );
    return {
      status: "ready",
      releases,
      selected,
      filters,
      summary,
      anomalies,
      reports,
      outcomeSensitivity,
    };
  } catch (error) {
    return {
      status: "error",
      releases,
      selected,
      filters,
      error: errorView(error),
    };
  }
}

export async function getPublicAnalysisAnomaly(
  anomalyId: string,
  filters: Pick<PublicAnalysisFilters, "release" | "election"> = {},
): Promise<PublicAnomalyDetailState> {
  if (!publicNormalizedApiConfigured()) {
    return { status: "fixture", releases: [] };
  }
  let releases: PublicReleaseRef[] = [];
  let selected: PublicReleaseRef | undefined;
  try {
    const selection = await getPublicReleaseSelection(filters);
    releases = selection.releases;
    selected = selection.selected;
    if (!selected) return { status: "no_release", releases };
    const prefix = prefixFor(selected);
    const value = await publicApiJson<unknown>(
      `${prefix}/analysis/anomalies/${encodeURIComponent(anomalyId)}`,
    );
    if (!isAnalysisAnomaly(value)) {
      throw new Error("The anomaly detail does not match the frozen contract.");
    }
    if (
      value.provenance.data_version !== selected.release_id ||
      (selected.methodology_version !== null &&
        value.methodology_version !== selected.methodology_version)
    ) {
      throw new Error("The anomaly detail crossed immutable release scope.");
    }
    return { status: "ready", releases, selected, anomaly: value };
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) {
      return {
        status: "not_found",
        releases,
        selected,
        error: errorView(error),
      };
    }
    return {
      status: "error",
      releases,
      selected,
      error: errorView(error),
    };
  }
}
