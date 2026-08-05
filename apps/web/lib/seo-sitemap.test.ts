import { afterEach, describe, expect, it, vi } from "vitest";

import { SITEMAP_URL_LIMIT } from "@/lib/seo";
import {
  sitemapPartitions,
  sitemapUrls,
  type SeoSitemapCatalog,
} from "@/lib/seo-sitemap";

afterEach(() => vi.unstubAllEnvs());

describe("SEO sitemap partitions", () => {
  it("filters the catalog into deterministic bilingual URLs and URI-encodes ids", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://analysis.example.org");
    const catalog: SeoSitemapCatalog = {
      lastmod: "2026-08-04T12:00:00Z",
      release: { release_id: "release-1", election_slug: "election-1" },
      departments: [
        { id: "DEP Bogotá/11", level: "department", name: "Bogotá" },
      ],
      municipalities: [
        { id: "MUN 001/á", level: "municipality", name: "Bogotá" },
      ],
    };
    expect(sitemapPartitions(catalog)).toEqual([
      "national",
      "departments",
      "municipalities-0",
    ]);
    const urls = sitemapUrls(catalog, "municipalities-0");
    expect(urls).toHaveLength(2);
    expect(urls[0]?.loc).toContain("MUN%20001%2F%C3%A1");
    expect(urls[0]?.loc).toContain("release=release-1&election=election-1");
    expect(urls.every((item) => item.lastmod === catalog.lastmod)).toBe(true);
  });

  it("never exceeds the protocol's 50,000 URL cap when both locales are emitted", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://analysis.example.org");
    const catalog: SeoSitemapCatalog = {
      lastmod: "2026-08-04T12:00:00Z",
      release: { release_id: "release-1", election_slug: "election-1" },
      departments: [],
      municipalities: Array.from({ length: SITEMAP_URL_LIMIT }, (_, index) => ({
        id: `MUN-${index}`,
        level: "municipality",
        name: `Municipality ${index}`,
      })),
    };
    const partitions = sitemapPartitions(catalog);
    expect(partitions).toHaveLength(4); // national, departments, two municipality partitions
    for (const partition of partitions.filter((item) =>
      item.startsWith("municipalities-"),
    )) {
      expect(
        sitemapUrls(catalog, partition as `municipalities-${number}`).length,
      ).toBeLessThanOrEqual(SITEMAP_URL_LIMIT);
    }
  });

  it("does not publish sitemap partitions without a verified catalog", () => {
    expect(sitemapPartitions(null)).toEqual([]);
    expect(sitemapUrls(null, "national")).toEqual([]);
  });
});
