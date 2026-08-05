import { setRequestLocale } from "next-intl/server";
import { ResultsExplorer } from "@/components/results-explorer";
import { SeoStructuredData } from "@/components/seo-structured-data";
import { dataAdapter, getPublicExplorer } from "@/data/fixture-adapter";
import { publicResultLabels } from "@/lib/public-labels";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";
import { readResultFilters } from "@/lib/result-filters";
import { datasetJsonLd, isIndexablePage, releaseMetadata } from "@/lib/seo";
import type { Metadata } from "next";
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en" }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const { locale } = await params;
  const filters = readResultFilters(await searchParams);
  const scope = new URLSearchParams();
  if (filters.release) scope.set("release", filters.release);
  if (filters.election) scope.set("election", filters.election);
  const pathname = `/resultados${scope.size ? `?${scope}` : ""}`;
  try {
    const release = await dataAdapter.getNationalSummary();
    const matchesScope =
      (!filters.release || filters.release === release.release.release_id) &&
      (!filters.election || filters.election === release.election.slug);
    return releaseMetadata({
      locale,
      pathname,
      title:
        locale === "es" ? "Resultados por territorio" : "Results by territory",
      description:
        locale === "es"
          ? "Explore resultados publicados por territorio, fuente y categoría de voto."
          : "Explore published results by territory, source and ballot category.",
      release: matchesScope ? release : null,
      page: "results",
    });
  } catch {
    return releaseMetadata({
      locale,
      pathname,
      title: locale === "es" ? "Resultados" : "Results",
      description: "Published results are currently unavailable.",
      page: "results",
    });
  }
}

export default async function ResultsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en" }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const query = await searchParams;
  const filters = readResultFilters(query);
  const cursor = typeof query.cursor === "string" ? query.cursor : undefined;
  // Every other data route treats "no readable release" as a representable
  // state instead of crashing. This one used to let the adapter's refusal
  // escape, which is why it answered 500 whenever no standard release existed.
  const guard = await loadReleaseOrUnavailable(locale, async () => {
    const explorer = await getPublicExplorer({ ...filters, cursor });
    return {
      explorer,
      release:
        explorer.kind === "fixture"
          ? await dataAdapter.getRelease({
              include: "results",
              filters,
              cursor,
            })
          : undefined,
    };
  });
  if (guard.fallback) return guard.fallback;
  const { explorer, release } = guard.release;
  const summary =
    release ?? (await dataAdapter.getNationalSummary().catch(() => undefined));
  const indexable = isIndexablePage(summary, "results");
  return (
    <>
      {indexable && summary ? (
        <SeoStructuredData
          value={datasetJsonLd(
            locale,
            summary,
            locale === "es"
              ? "Resultados electorales publicados"
              : "Published election results",
            "/resultados",
          )}
        />
      ) : null}
      <ResultsExplorer
        release={release}
        explorer={explorer}
        locale={locale}
        filters={filters}
        enumLabels={publicResultLabels(locale)}
      />
    </>
  );
}
