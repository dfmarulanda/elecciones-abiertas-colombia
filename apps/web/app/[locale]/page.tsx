import { NextIntlClientProvider } from "next-intl";
import {
  getMessages,
  getTranslations,
  setRequestLocale,
} from "next-intl/server";
import "./design.css";
import { ConteoHero } from "@/components/conteo-hero";
import { ClaimsRegister } from "@/components/claims-register";
import {
  ComparisonSection,
  MesaSection,
  TerritoriesSection,
  ProcessSection,
  LogSection,
  DataSection,
} from "@/components/narrative-sections";
import { SeoStructuredData } from "@/components/seo-structured-data";
import { dataAdapter } from "@/data/fixture-adapter";
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
  const messages = await getMessages();
  // Most of the narrative reads no release and renders in both branches. The
  // data-backed sections (#territorios) take the real release when one loaded
  // and degrade to their unavailable state otherwise.
  const narrative = (
    rel?: Awaited<ReturnType<typeof dataAdapter.getRelease>>,
  ) => {
    const candidates = rel?.summary.candidates.map((c) => ({
      id: c.candidate.id,
      name: c.candidate.name,
    }));
    return (
      <>
        <ClaimsRegister locale={locale} t={t} />
        <ComparisonSection locale={locale} t={t} />
        <MesaSection
          locale={locale}
          t={t}
          mesa={rel?.sample_mesa}
          candidates={candidates}
        />
        <TerritoriesSection
          locale={locale}
          t={t}
          departments={rel?.department_rollup}
          candidates={candidates}
        />
        <ProcessSection locale={locale} t={t} />
        <LogSection locale={locale} t={t} />
        <DataSection locale={locale} t={t} />
      </>
    );
  };
  // The API refuses to serve a context-only historical release through the
  // legacy release contract rather than invent completion metadata. That
  // refusal is correct; rendering an explicit unavailable state is the honest
  // response to it, and it keeps the pages that need no active release usable.
  let release: Awaited<ReturnType<typeof dataAdapter.getRelease>>;
  try {
    release = await dataAdapter.getRelease({ include: "review" });
  } catch {
    // #conteo needs a release to show real vote totals; the rest of the
    // narrative does not. Keep it visible even when no release can be read,
    // and let #conteo itself degrade to its unavailable state rather than
    // disappear — it is the hero, so something must still render first.
    return (
      <NextIntlClientProvider messages={messages}>
        <div className="eac-design">
          <ConteoHero locale={locale} available={false} />
          {narrative()}
        </div>
      </NextIntlClientProvider>
    );
  }
  // The design's 8 sections (conteo, reclamos, comparación, mesa,
  // territorios, proceso, bitácora, datos) have no outcome-sensitivity
  // section, so the old NationalSummary's #05 panel has no home here; the
  // fixture-adapter call that fed it is dropped rather than left unused.
  const indexable = isIndexablePage(release, "national");
  return (
    <NextIntlClientProvider messages={messages}>
      <div className="eac-design">
        {indexable ? (
          <>
            <SeoStructuredData value={websiteJsonLd(locale)} />
            <SeoStructuredData value={dataCatalogJsonLd(locale, release)} />
          </>
        ) : null}
        <ConteoHero locale={locale} available summary={release.summary} />
        {narrative(release)}
      </div>
    </NextIntlClientProvider>
  );
}
