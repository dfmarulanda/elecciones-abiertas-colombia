import { getTranslations, setRequestLocale } from "next-intl/server";
import { NationalSummary } from "@/components/national-summary";
import { ReleaseUnavailable } from "@/components/release-unavailable";
import { ClaimsRegister } from "@/components/claims-register";
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
  const t = await getTranslations();
  // The API refuses to serve a context-only historical release through the
  // legacy release contract rather than invent completion metadata. That
  // refusal is correct; rendering an explicit unavailable state is the honest
  // response to it, and it keeps the pages that need no active release usable.
  let release: Awaited<ReturnType<typeof dataAdapter.getRelease>>;
  try {
    release = await dataAdapter.getRelease({ include: "review" });
  } catch {
    // The national summary needs a release; the claims register does not.
    // Keep the static narrative visible even when no release can be read.
    return (
      <>
        <ReleaseUnavailable
          locale={locale}
          title={t("releaseUnavailable.title")}
          body={t("releaseUnavailable.body")}
          methodology={t("releaseUnavailable.methodology")}
          sources={t("releaseUnavailable.sources")}
        />
        <ClaimsRegister locale={locale} t={t} />
      </>
    );
  }
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
      <ClaimsRegister locale={locale} t={t} />
    </>
  );
}
