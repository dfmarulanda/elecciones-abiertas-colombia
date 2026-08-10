import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import {
  AnalysisUnavailable,
  AnalysisWorkspace,
} from "@/components/analysis-workspace";
import {
  ANALYSIS_ANOMALY_TYPES,
  getPublicAnalysis,
  type AnalysisAnomalyType,
  type PublicAnalysisFilters,
} from "@/data/analysis-adapter";
import { dataAdapter } from "@/data/fixture-adapter";
import { releaseMetadata } from "@/lib/seo";

export const dynamic = "force-dynamic";

function first(value: string | string[] | undefined) {
  return typeof value === "string" ? value : value?.[0];
}

function readAnalysisFilters(
  query: Record<string, string | string[] | undefined>,
): PublicAnalysisFilters {
  const context = new URLSearchParams(first(query.context) ?? "");
  const anomalyType = first(query.tipo);
  return {
    release: context.get("release") ?? first(query.release),
    election: context.get("election") ?? first(query.election),
    analysisRelease:
      context.get("analysis_release") ?? first(query.analysis_release),
    cursor: first(query.cursor),
    anomalyType: ANALYSIS_ANOMALY_TYPES.includes(
      anomalyType as AnalysisAnomalyType,
    )
      ? (anomalyType as AnalysisAnomalyType)
      : undefined,
  };
}

function pathnameFor(filters: PublicAnalysisFilters) {
  const query = new URLSearchParams();
  if (filters.release) query.set("release", filters.release);
  if (filters.election) query.set("election", filters.election);
  if (filters.analysisRelease)
    query.set("analysis_release", filters.analysisRelease);
  if (filters.anomalyType) query.set("tipo", filters.anomalyType);
  return `/analitica${query.size ? `?${query}` : ""}`;
}

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en" }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const { locale } = await params;
  const filters = readAnalysisFilters(await searchParams);
  const pathname = pathnameFor(filters);
  const analysis = await getPublicAnalysis(filters);
  let release = null;
  if (
    analysis.status === "ready" &&
    analysis.analysisRelease.exposure_tier === "certified_public" &&
    analysis.selected.status === "published"
  ) {
    const candidate = await dataAdapter.getNationalSummary().catch(() => null);
    if (
      candidate?.release.release_id === analysis.selected.release_id &&
      candidate.election.slug === analysis.selected.election_slug
    ) {
      release = candidate;
    }
  }
  return releaseMetadata({
    locale,
    pathname,
    title:
      locale === "es"
        ? "Análisis estadístico reproducible"
        : "Reproducible statistical analysis",
    description:
      locale === "es"
        ? "Anomalías, explicaciones, prioridad de auditoría, cobertura y diagnósticos de un release electoral inmutable."
        : "Anomalies, explanations, audit priority, coverage, and diagnostics for an immutable election release.",
    release,
    page: "results",
  });
}

export default async function AnalyticsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en" }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const filters = readAnalysisFilters(await searchParams);
  const analysis = await getPublicAnalysis(filters);

  if (analysis.status === "ready") {
    return <AnalysisWorkspace locale={locale} analysis={analysis} />;
  }

  return (
    <AnalysisUnavailable
      locale={locale}
      status={analysis.status}
      selected={analysis.selected}
      message={analysis.error?.message}
    />
  );
}
