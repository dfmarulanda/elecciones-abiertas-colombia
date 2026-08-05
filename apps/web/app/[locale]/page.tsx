import { getTranslations, setRequestLocale } from "next-intl/server";
import { NationalSummary } from "@/components/national-summary";
import { SeoStructuredData } from "@/components/seo-structured-data";
import {
  dataAdapter,
  getPublicOutcomeSensitivity,
} from "@/data/fixture-adapter";
import {
  dataCatalogJsonLd,
  isIndexablePage,
  releaseMetadata,
  websiteJsonLd,
} from "@/lib/seo";
import type { Metadata } from "next";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}): Promise<Metadata> {
  const { locale } = await params;
  try {
    const release = await dataAdapter.getNationalSummary();
    return releaseMetadata({
      locale,
      title: release.election.name[locale],
      description:
        locale === "es"
          ? "Resultados nacionales, cobertura, conciliación y fuentes de una publicación electoral reproducible."
          : "National results, coverage, reconciliation and sources from a reproducible election publication.",
      release,
      page: "national",
    });
  } catch {
    return releaseMetadata({
      locale,
      title: "Elecciones Abiertas Colombia",
      description: "Election results require an available published release.",
      page: "national",
    });
  }
}

export default async function LocaleHome({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [release, t] = await Promise.all([
    dataAdapter.getRelease({ include: "review" }),
    getTranslations(),
  ]);
  const outcomeSensitivity = await getPublicOutcomeSensitivity({
    release: release.release.release_id,
    election: release.election.slug,
  });
  const indexable = isIndexablePage(release, "national");
  return (
    <>
      {indexable ? (
        <>
          <SeoStructuredData value={websiteJsonLd(locale)} />
          <SeoStructuredData value={dataCatalogJsonLd(locale, release)} />
        </>
      ) : null}
      <NationalSummary
        release={release}
        locale={locale}
        t={t}
        outcomeSensitivity={outcomeSensitivity}
      />
    </>
  );
}
