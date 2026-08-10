import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import {
  AnalysisAnomalyDetail,
  AnalysisUnavailable,
} from "@/components/analysis-workspace";
import { getPublicAnalysisAnomaly } from "@/data/analysis-adapter";
import { dataAdapter } from "@/data/fixture-adapter";
import { releaseMetadata } from "@/lib/seo";

export const dynamic = "force-dynamic";

function first(value: string | string[] | undefined) {
  return typeof value === "string" ? value : value?.[0];
}

function detailPath(
  anomalyId: string,
  release?: string,
  election?: string,
  analysisRelease?: string,
) {
  const query = new URLSearchParams();
  if (release) query.set("release", release);
  if (election) query.set("election", election);
  if (analysisRelease) query.set("analysis_release", analysisRelease);
  return `/analitica/anomalias/${encodeURIComponent(anomalyId)}${query.size ? `?${query}` : ""}`;
}

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en"; anomalyId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const { locale, anomalyId } = await params;
  const query = await searchParams;
  const releaseId = first(query.release);
  const election = first(query.election);
  const analysisRelease = first(query.analysis_release);
  const pathname = detailPath(anomalyId, releaseId, election, analysisRelease);
  const state = await getPublicAnalysisAnomaly(anomalyId, {
    release: releaseId,
    election,
    analysisRelease,
  });
  let release = null;
  if (
    state.status === "ready" &&
    state.anomaly.analysis_release.exposure_tier === "certified_public" &&
    state.selected.status === "published"
  ) {
    const candidate = await dataAdapter.getNationalSummary().catch(() => null);
    if (
      candidate?.release.release_id === state.selected.release_id &&
      candidate.election.slug === state.selected.election_slug
    ) {
      release = candidate;
    }
  }
  return releaseMetadata({
    locale,
    pathname,
    title:
      locale === "es"
        ? `Análisis de mesa ${state.status === "ready" ? state.anomaly.mesa_id : anomalyId}`
        : `Mesa analysis ${state.status === "ready" ? state.anomaly.mesa_id : anomalyId}`,
    description:
      locale === "es"
        ? "Evidencia, explicación, elegibilidad, limitaciones y procedencia de una señal analítica publicada."
        : "Evidence, explanation, eligibility, limitations, and provenance for a published analytical signal.",
    release,
    page: "mesa",
    hasPublishedFacts: state.status === "ready",
    uniqueProvenance: state.status === "ready",
  });
}

export default async function AnalysisAnomalyPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en"; anomalyId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, anomalyId } = await params;
  setRequestLocale(locale);
  const query = await searchParams;
  const state = await getPublicAnalysisAnomaly(anomalyId, {
    release: first(query.release),
    election: first(query.election),
    analysisRelease: first(query.analysis_release),
  });

  if (state.status === "ready") {
    return <AnalysisAnomalyDetail locale={locale} state={state} />;
  }
  return (
    <AnalysisUnavailable
      locale={locale}
      status={state.status}
      selected={state.selected}
      message={state.error?.message}
    />
  );
}
