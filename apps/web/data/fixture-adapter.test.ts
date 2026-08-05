import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { ReleaseView } from "./fixture-adapter";
import { fixtureAdapter } from "./fixture-adapter";

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "../../data/fixtures/fixture-release.json"),
    "utf8",
  ),
) as ReleaseView;

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("fixture release adapter", () => {
  it("projects fixture evidence as an index-only public view", async () => {
    const release = await fixtureAdapter.getNationalSummary();
    expect(release.release.status).toBe("fixture");
    expect(release.release.synthetic).toBe(true);
    expect(release.summary.release_status).toBe("fixture");
    expect("evidence_handling" in release).toBe(false);
    expect(release.comparisons).toEqual({});

    const documents = await fixtureAdapter.getEvidence(
      "2026-R2-11-001-001-003",
    );
    expect(documents).toHaveLength(1);
    expect(documents[0]).toMatchObject({
      id: "e14-003-delegate",
      mesa_id: "2026-R2-11-001-001-003",
      document_type: "e14_delegate",
      official_url: expect.stringMatching(/^https:\/\//),
      source_index_url: expect.stringMatching(/^https:\/\//),
      source_index_hash: expect.stringMatching(/^[a-f0-9]{64}$/),
      index_status: "indexed",
    });
    for (const document of [...release.evidence, ...documents]) {
      for (const forbidden of [
        "cached_derivative_url",
        "full_file_hash",
        "derivative_hash",
        "pii_reviewed",
        "retrieval_status",
        "extraction_status",
        "transcription",
        "extracted_votes",
      ]) {
        expect(document).not.toHaveProperty(forbidden);
      }
    }
    await expect(
      fixtureAdapter.getComparisons("2026-R2-11-001-001-003"),
    ).resolves.toEqual([]);
  });

  it("pins the review request to the summary version without an active-release env", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    vi.stubEnv("NEXT_PUBLIC_ACTIVE_RELEASE", "");
    const requested: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        requested.push(url);
        const body = url.includes("/review-signals?")
          ? {
              items: fixture.review_signals,
              page: { next_cursor: null, has_more: false, limit: 50 },
              data_version: fixture.summary.data_version,
              methodology_version: fixture.release.methodology_version,
              disclosure: fixture.review_signals[0]?.disclosure ?? {
                es: "No disponible",
                en: "Unavailable",
              },
            }
          : fixture.summary;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const { dataAdapter } = await import("./fixture-adapter");

    await dataAdapter.getRelease({ include: "review" });

    const reviewUrl = new URL(
      requested.find((url) => url.includes("/review-signals?"))!,
    );
    expect(reviewUrl.searchParams.get("data_version")).toBe(
      fixture.summary.data_version,
    );
  });

  it("projects unexpected live evidence fields through the same index-only allowlist", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    const wireDocument = fixture.evidence.find(
      (document) => document.mesa_id === "2026-R2-11-001-001-003",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        if (url.includes("/evidence?")) {
          return new Response(JSON.stringify({ documents: [wireDocument] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const { dataAdapter } = await import("./fixture-adapter");

    const [document] = await dataAdapter.getEvidence("2026-R2-11-001-001-003");

    expect(document).toMatchObject({
      id: "e14-003-delegate",
      index_status: "indexed",
      official_url: expect.stringMatching(/^https:\/\//),
    });
    expect(document).not.toHaveProperty("cached_derivative_url");
    expect(document).not.toHaveProperty("full_file_hash");
    expect(document).not.toHaveProperty("extraction_status");
  });

  it("fails closed when a review response crosses summary versions", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    vi.stubEnv("NEXT_PUBLIC_ACTIVE_RELEASE", "");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        const body = url.includes("/review-signals?")
          ? {
              items: [],
              page: { next_cursor: null, has_more: false, limit: 50 },
              data_version: "different-version",
              methodology_version: fixture.release.methodology_version,
              disclosure: { es: "No disponible", en: "Unavailable" },
            }
          : fixture.summary;
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    const { dataAdapter } = await import("./fixture-adapter");

    await expect(dataAdapter.getRelease({ include: "review" })).rejects.toThrow(
      /does not match summary version/,
    );
  });
});
