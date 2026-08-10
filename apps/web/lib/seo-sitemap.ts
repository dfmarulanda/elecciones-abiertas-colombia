import { unstable_cache } from "next/cache";

import {
  isPublishedCompleteRelease,
  publicSiteOrigin,
  SEO_REVALIDATE_SECONDS,
  SITEMAP_URL_LIMIT,
} from "@/lib/seo";

type Locale = "es" | "en";
type SitemapPartition = "national" | "departments" | `municipalities-${number}`;

type PublicRelease = {
  release_id: string;
  election_slug: string;
  status: "published";
};

type Geography = {
  id: string;
  level: string;
  name: string;
  has_published_facts?: boolean;
};

type Page<T> = {
  items: T[];
  page: { next_cursor: string | null; has_more: boolean };
};

export type SitemapUrl = { loc: string; lastmod: string };
// Each public geography has one ES and one EN URL in a partition.
const SITEMAP_UNIT_LIMIT = Math.floor(SITEMAP_URL_LIMIT / 2);

export type SeoSitemapCatalog = {
  lastmod: string;
  release: Pick<PublicRelease, "release_id" | "election_slug">;
  departments: Geography[];
  municipalities: Geography[];
  analysisReleaseId?: string;
};

function apiBase() {
  return process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
}

async function apiJson<T>(pathname: string) {
  const base = apiBase();
  if (!base) throw new Error("A public API URL is required for sitemaps.");
  const response = await fetch(`${base}${pathname}`, {
    next: { revalidate: SEO_REVALIDATE_SECONDS },
    headers: { Accept: "application/json" },
  });
  if (!response.ok)
    throw new Error(`Sitemap API request failed (${response.status}).`);
  return (await response.json()) as T;
}

async function optionalApiJson<T>(pathname: string) {
  try {
    return await apiJson<T>(pathname);
  } catch {
    return null;
  }
}

async function children(release: PublicRelease, parent: string) {
  const values: Geography[] = [];
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: "200" });
    if (cursor) query.set("cursor", cursor);
    const page = await apiJson<Page<Geography>>(
      `/api/v1/releases/${encodeURIComponent(release.release_id)}/elections/${encodeURIComponent(release.election_slug)}/geographies/${encodeURIComponent(parent)}/children?${query}`,
    );
    values.push(...page.items);
    cursor = page.page.next_cursor;
  } while (cursor && values.length < SITEMAP_URL_LIMIT);
  return values;
}

function activeRelease(releases: PublicRelease[]) {
  const configured = process.env.NEXT_PUBLIC_ACTIVE_RELEASE;
  return configured
    ? releases.find((release) => release.release_id === configured)
    : undefined;
}

/**
 * This deliberately enumerates no lower than municipality. It keeps sitemap
 * production bounded (about forty API pages nationally), avoids generating
 * 122k thin mesa URLs, and only promotes units with published facts.
 */
async function uncachedCatalog(): Promise<SeoSitemapCatalog | null> {
  if (!publicSiteOrigin()) return null;
  const release = activeRelease(
    await apiJson<PublicRelease[]>("/api/v1/release-elections"),
  );
  if (!release) return null;
  const summary = await apiJson<{
    data_version: string;
    release_status: string;
    synthetic: boolean;
    provenance: { retrieved_at: string };
    completion: { expected: number; reported: number; percent: number };
    coverage: {
      expected: number;
      retrieved: number;
      parsed: number;
      missing: number;
      ambiguous: number;
      excluded: number;
    };
    reconciliation: {
      status: "passed" | "blocked" | "not_run";
      exceptions: number;
    };
  }>(
    `/api/v1/elections/${encodeURIComponent(release.election_slug)}/summary?data_version=${encodeURIComponent(release.release_id)}`,
  );
  if (
    summary.data_version !== release.release_id ||
    !isPublishedCompleteRelease({
      release_id: release.release_id,
      data_version: release.release_id,
      status: summary.release_status,
      synthetic: summary.synthetic,
      created_at: summary.provenance.retrieved_at,
      summary,
    })
  ) {
    return null;
  }
  const analysis = await optionalApiJson<{
    analysis_release: {
      analysis_release_id: string;
      source_release_id: string;
      election_slug: string;
      exposure_tier: "preliminary_research" | "certified_public";
    };
  }>(
    `/api/v1/releases/${encodeURIComponent(release.release_id)}/elections/${encodeURIComponent(release.election_slug)}/analysis/summary`,
  );
  const analysisReleaseId =
    analysis?.analysis_release.exposure_tier === "certified_public" &&
    analysis.analysis_release.source_release_id === release.release_id &&
    analysis.analysis_release.election_slug === release.election_slug
      ? analysis.analysis_release.analysis_release_id
      : undefined;
  const departments = (await children(release, "CO")).filter(
    (item) => item.level === "department" && item.has_published_facts,
  );
  const municipalityPages = await Promise.all(
    departments.map((department) => children(release, department.id)),
  );
  const municipalities = municipalityPages
    .flat()
    .filter((item) => item.level === "municipality" && item.has_published_facts)
    .slice(0, SITEMAP_URL_LIMIT * 20);
  return {
    lastmod: summary.provenance.retrieved_at,
    release,
    departments,
    municipalities,
    analysisReleaseId,
  };
}

export const getSeoSitemapCatalog = unstable_cache(
  uncachedCatalog,
  ["seo-sitemap-v2"],
  {
    revalidate: SEO_REVALIDATE_SECONDS,
    tags: ["seo-sitemaps"],
  },
);

export function sitemapPartitions(
  catalog: SeoSitemapCatalog | null,
): SitemapPartition[] {
  if (!catalog) return [];
  const municipalityCount = Math.ceil(
    catalog.municipalities.length / SITEMAP_UNIT_LIMIT,
  );
  return [
    "national",
    "departments",
    ...Array.from(
      { length: municipalityCount },
      (_, index) => `municipalities-${index}` as const,
    ),
  ];
}

function localizedUrls(
  locale: Locale,
  pathname: string,
  lastmod: string,
): SitemapUrl[] {
  const origin = publicSiteOrigin();
  if (!origin) return [];
  return [
    { loc: new URL(`/${locale}${pathname}`, origin).toString(), lastmod },
  ];
}

export function sitemapUrls(
  catalog: SeoSitemapCatalog | null,
  partition: SitemapPartition,
): SitemapUrl[] {
  if (!catalog) return [];
  const both = (pathname: string, extra?: Record<string, string>) => [
    ...localizedUrls(
      "es",
      scopedPath(catalog, pathname, extra),
      catalog.lastmod,
    ),
    ...localizedUrls(
      "en",
      scopedPath(catalog, pathname, extra),
      catalog.lastmod,
    ),
  ];
  if (partition === "national")
    return [
      ...localizedUrls("es", "", catalog.lastmod),
      ...localizedUrls("en", "", catalog.lastmod),
      ...both("/resultados"),
      ...(catalog.analysisReleaseId
        ? both("/analitica", {
            analysis_release: catalog.analysisReleaseId,
          })
        : []),
    ];
  const rows =
    partition === "departments"
      ? catalog.departments
      : catalog.municipalities.slice(
          Number(partition.split("-")[1]) * SITEMAP_UNIT_LIMIT,
          (Number(partition.split("-")[1]) + 1) * SITEMAP_UNIT_LIMIT,
        );
  return rows.flatMap((item) =>
    both(`/resultados/geografia/${encodeURIComponent(item.id)}`),
  );
}

function scopedPath(
  catalog: SeoSitemapCatalog,
  pathname: string,
  extra: Record<string, string> = {},
) {
  const query = new URLSearchParams({
    release: catalog.release.release_id,
    election: catalog.release.election_slug,
    ...extra,
  });
  return `${pathname}?${query}`;
}

export function xml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
