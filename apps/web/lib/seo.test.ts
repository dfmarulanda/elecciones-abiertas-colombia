import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReleaseView } from "@/data/fixture-adapter";
import {
  dataCatalogJsonLd,
  datasetJsonLd,
  isIndexablePage,
  isPublishedCompleteRelease,
  localeAlternates,
  releaseMetadata,
  websiteJsonLd,
} from "@/lib/seo";

const complete = (): ReleaseView =>
  ({
    release: {
      release_id: "real-release-1",
      data_version: "real-release-1",
      status: "published",
      synthetic: false,
      created_at: "2026-08-04T12:00:00Z",
      methodology_version: "method-v1",
    },
    summary: {
      completion: { expected: 10, reported: 10, percent: 1 },
      coverage: {
        expected: 10,
        retrieved: 10,
        parsed: 10,
        missing: 0,
        ambiguous: 0,
        excluded: 0,
      },
      reconciliation: { status: "passed", checked_facts: 10, exceptions: 0 },
    },
  }) as ReleaseView;

afterEach(() => vi.unstubAllEnvs());

describe("release SEO eligibility", () => {
  it("keeps a synthetic fixture out of search even when its arithmetic passes", () => {
    const fixture = complete();
    fixture.release.status = "fixture";
    fixture.release.synthetic = true;
    const metadata = releaseMetadata({
      locale: "es",
      title: "Fixture",
      description: "Fixture",
      release: fixture,
      page: "national",
    });
    expect(metadata.robots).toEqual({
      index: false,
      follow: false,
      nocache: true,
    });
    expect(metadata.alternates).toMatchObject({ canonical: "/es/resultados" });
  });

  it("indexes only a published, complete, reconciled real release", () => {
    const release = complete();
    expect(isPublishedCompleteRelease(release)).toBe(true);
    expect(isIndexablePage(release, "national")).toBe(true);
    expect(
      isIndexablePage(release, "mesa", {
        hasPublishedFacts: true,
        uniqueProvenance: true,
      }),
    ).toBe(true);
    expect(isIndexablePage(release, "mesa", { hasPublishedFacts: true })).toBe(
      false,
    );
    expect(
      isIndexablePage(release, "geography", { hasPublishedFacts: false }),
    ).toBe(false);
  });

  it("treats partial coverage, unknown coverage and observed zero as non-indexable", () => {
    const partial = complete();
    partial.summary.coverage.missing = 1;
    expect(isPublishedCompleteRelease(partial)).toBe(false);
    const zero = complete();
    zero.summary.coverage.expected = 0;
    zero.summary.coverage.retrieved = 0;
    zero.summary.coverage.parsed = 0;
    expect(isPublishedCompleteRelease(zero)).toBe(false);
    const unknown = complete();
    (unknown.summary as { coverage?: unknown }).coverage = undefined;
    expect(isIndexablePage(unknown, "national")).toBe(false);
  });

  it("creates localized canonical and alternate links and consolidates a thin mesa upward", () => {
    const release = complete();
    const metadata = releaseMetadata({
      locale: "en",
      pathname: "/resultados/mesa/Mesa Bogotá/1",
      title: "Mesa",
      description: "Mesa",
      release,
      page: "mesa",
      hasPublishedFacts: false,
      uniqueProvenance: false,
    });
    expect(metadata.alternates).toMatchObject({
      canonical: "/en/resultados",
      languages: localeAlternates("/resultados/mesa/Mesa Bogotá/1"),
    });
  });

  it("emits truthful website and dataset structured data without government attribution", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://analysis.example.org");
    const release = complete();
    const website = JSON.parse(websiteJsonLd("es")!);
    const catalog = JSON.parse(dataCatalogJsonLd("en", release)!);
    const dataset = JSON.parse(
      datasetJsonLd("es", release, "Resultados", "/resultados")!,
    );
    expect(website["@type"]).toBe("WebSite");
    expect(catalog["@type"]).toBe("DataCatalog");
    expect(dataset).toMatchObject({
      "@type": "Dataset",
      identifier: "real-release-1",
    });
    expect(
      JSON.stringify([website, catalog, dataset]).toLowerCase(),
    ).not.toContain("government");
    expect(
      JSON.stringify([website, catalog, dataset]).toLowerCase(),
    ).not.toContain("gobierno");
  });
});
