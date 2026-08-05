import type { Metadata } from "next";

import type { ReleaseView } from "@/data/fixture-adapter";

export const SEO_REVALIDATE_SECONDS = 60 * 60;
export const SITEMAP_URL_LIMIT = 50_000;

type Locale = "es" | "en";

type ReleaseQuality = {
  status: string;
  synthetic: boolean;
  created_at: string;
  data_version: string;
  release_id: string;
  summary: {
    completion?: { expected: number; reported: number; percent: number };
    coverage?: {
      expected: number;
      retrieved: number;
      parsed: number;
      missing: number;
      ambiguous: number;
      excluded: number;
    };
    reconciliation?: { status: string; exceptions: number };
  };
};

export type SeoPage = "national" | "results" | "geography" | "mesa";

function qualityOf(release: ReleaseQuality | ReleaseView): ReleaseQuality {
  return "release" in release
    ? { ...release.release, summary: release.summary }
    : release;
}

function normalizedOrigin(value: string | undefined) {
  if (!value) return undefined;
  try {
    return new URL(value.startsWith("http") ? value : `https://${value}`)
      .origin;
  } catch {
    return undefined;
  }
}

/**
 * The production domain is deliberately configuration-driven. Preview hosts
 * may render previews, but must not become canonical production addresses.
 */
export function publicSiteOrigin() {
  return normalizedOrigin(
    process.env.NEXT_PUBLIC_SITE_URL ??
      process.env.VERCEL_PROJECT_PRODUCTION_URL ??
      process.env.VERCEL_URL,
  );
}

export function localizedPath(locale: Locale, pathname = "") {
  const suffix = pathname.startsWith("/") ? pathname : `/${pathname}`;
  return `/${locale}${suffix === "/" ? "" : suffix}`;
}

export function absoluteUrl(pathname: string) {
  const origin = publicSiteOrigin();
  return origin ? new URL(pathname, origin).toString() : undefined;
}

export function localeAlternates(pathname: string) {
  return {
    es: localizedPath("es", pathname),
    en: localizedPath("en", pathname),
    "x-default": localizedPath("es", pathname),
  };
}

/** A release must be real, immutable, fully covered and reconciled before it can be indexed. */
export function isPublishedCompleteRelease(
  release: ReleaseQuality | ReleaseView,
) {
  const quality = qualityOf(release);
  const { completion, coverage, reconciliation } = quality.summary;
  if (!completion || !coverage || !reconciliation) return false;
  return (
    quality.status === "published" &&
    !quality.synthetic &&
    completion.expected > 0 &&
    completion.reported === completion.expected &&
    completion.percent === 1 &&
    coverage.expected > 0 &&
    coverage.retrieved === coverage.expected &&
    coverage.parsed === coverage.expected &&
    coverage.missing === 0 &&
    coverage.ambiguous === 0 &&
    coverage.excluded === 0 &&
    reconciliation.status === "passed" &&
    reconciliation.exceptions === 0
  );
}

export function isIndexablePage(
  release: ReleaseQuality | ReleaseView | null | undefined,
  page: SeoPage,
  options: { hasPublishedFacts?: boolean; uniqueProvenance?: boolean } = {},
) {
  if (!release || !isPublishedCompleteRelease(release)) return false;
  if (page === "mesa")
    return Boolean(options.hasPublishedFacts && options.uniqueProvenance);
  if (page === "geography") return options.hasPublishedFacts !== false;
  return true;
}

export function seoRobots(indexable: boolean): Metadata["robots"] {
  return indexable
    ? { index: true, follow: true }
    : { index: false, follow: false, nocache: true };
}

type ReleaseMetadataInput = {
  locale: Locale;
  pathname?: string;
  canonicalPathname?: string;
  title: string;
  description: string;
  release?: ReleaseQuality | ReleaseView | null;
  page: SeoPage;
  hasPublishedFacts?: boolean;
  uniqueProvenance?: boolean;
};

/**
 * All release-facing metadata uses the same eligibility gate as robots. This
 * prevents synthetic, candidate, withdrawn or partial snapshots from gaining
 * a durable search identity.
 */
export function releaseMetadata(input: ReleaseMetadataInput): Metadata {
  const pathname = input.pathname ?? "";
  const indexable = isIndexablePage(input.release, input.page, {
    hasPublishedFacts: input.hasPublishedFacts,
    uniqueProvenance: input.uniqueProvenance,
  });
  return {
    title: input.title,
    description: input.description,
    robots: seoRobots(indexable),
    alternates: {
      canonical: localizedPath(
        input.locale,
        input.canonicalPathname ?? (indexable ? pathname : "/resultados"),
      ),
      languages: localeAlternates(pathname),
    },
  };
}

function json(value: unknown) {
  return JSON.stringify(value).replaceAll("<", "\\u003c");
}

export function websiteJsonLd(locale: Locale) {
  const url = absoluteUrl(localizedPath(locale));
  if (!url) return null;
  return json({
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Elecciones Abiertas Colombia",
    url,
    inLanguage: locale === "es" ? "es-CO" : "en",
    description:
      locale === "es"
        ? "Visor público, bilingüe y reproducible de resultados electorales de Colombia."
        : "A public, bilingual and reproducible viewer of Colombian election results.",
  });
}

export function dataCatalogJsonLd(
  locale: Locale,
  release: ReleaseQuality | ReleaseView,
) {
  const quality = qualityOf(release);
  const url = absoluteUrl(localizedPath(locale, "descargas"));
  if (!url) return null;
  return json({
    "@context": "https://schema.org",
    "@type": "DataCatalog",
    name:
      locale === "es"
        ? "Catálogo de datos de Elecciones Abiertas Colombia"
        : "Elecciones Abiertas Colombia data catalog",
    url,
    inLanguage: locale === "es" ? "es-CO" : "en",
    dataset: {
      "@type": "Dataset",
      name: quality.data_version,
      dateModified: quality.created_at,
      identifier: quality.release_id,
    },
  });
}

export function breadcrumbJsonLd(
  locale: Locale,
  items: Array<{ name: string; pathname: string }>,
) {
  const list = items.flatMap((item, index) => {
    const itemUrl = absoluteUrl(localizedPath(locale, item.pathname));
    return itemUrl
      ? [
          {
            "@type": "ListItem",
            position: index + 1,
            name: item.name,
            item: itemUrl,
          },
        ]
      : [];
  });
  if (!list.length) return null;
  return json({
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: list,
  });
}

export function datasetJsonLd(
  locale: Locale,
  release: ReleaseQuality | ReleaseView,
  name: string,
  pathname: string,
) {
  const quality = qualityOf(release);
  const url = absoluteUrl(localizedPath(locale, pathname));
  if (!url) return null;
  return json({
    "@context": "https://schema.org",
    "@type": "Dataset",
    name,
    url,
    identifier: quality.release_id,
    version: quality.data_version,
    dateModified: quality.created_at,
    inLanguage: locale === "es" ? "es-CO" : "en",
    isBasedOn: quality.data_version,
  });
}
