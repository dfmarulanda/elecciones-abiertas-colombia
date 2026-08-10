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
  it("defaults the public explorer to the configured active release", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    vi.stubEnv("NEXT_PUBLIC_ACTIVE_RELEASE", "candidate-live");
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify([
            {
              release_id: "historical-2018",
              election_slug: "presidencia-2018-segunda-vuelta",
            },
            {
              release_id: "candidate-live",
              election_slug: "presidencia-2026-segunda-vuelta",
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { getPublicReleaseSelection } = await import("./fixture-adapter");

    const { selected } = await getPublicReleaseSelection({});

    expect(selected).toMatchObject({
      release_id: "candidate-live",
      election_slug: "presidencia-2026-segunda-vuelta",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:9999/api/v1/release-elections",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

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

  it("hydrates a preliminary summary with normalized department results instead of a fixture fallback", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    vi.stubEnv("NEXT_PUBLIC_ACTIVE_RELEASE", "candidate-live");
    const requested: string[] = [];
    const preliminarySummary = {
      ...fixture.summary,
      data_version: "candidate-live",
      release_status: "candidate",
      synthetic: false,
      preliminary: true,
      preliminary_caveat: {
        es: "Resultados preliminares; no certificados.",
        en: "Preliminary results; not certified.",
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input);
        requested.push(url);
        if (url.includes("/api/v1/elections/") && url.includes("/summary?")) {
          return new Response(JSON.stringify({ detail: "Not found" }), {
            status: 404,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.endsWith("/api/v1/release-elections")) {
          return new Response(
            JSON.stringify([
              {
                release_id: "candidate-live",
                election_slug: fixture.election.slug,
                name_es: fixture.election.name.es,
                name_en: fixture.election.name.en,
                round: fixture.election.round,
                election_date: fixture.election.election_date,
                status: "candidate",
                exposure_class: "preliminary",
                methodology_version: fixture.release.methodology_version,
                release_manifest_hash: "a".repeat(64),
                exposure_approved_at: null,
                sources: [],
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.endsWith("/summary")) {
          return new Response(JSON.stringify(preliminarySummary), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/geographies/CO/children-results?")) {
          return new Response(
            JSON.stringify({
              items: [
                {
                  i: "scope:01",
                  l: "department",
                  c: "01",
                  n: "ANTIOQUIA",
                  t: 120,
                  v: 117,
                  b: 3,
                  x: 0,
                  u: 0,
                  k: [70, 44],
                },
                {
                  i: "scope:16",
                  l: "department",
                  c: "16",
                  n: "BOGOTA D.C.",
                  t: 230,
                  v: 225,
                  b: 5,
                  x: 0,
                  u: 0,
                  k: [90, 130],
                },
              ],
              candidates: [
                `candidate:${preliminarySummary.candidates[0]!.candidate.id}`,
                `candidate:${preliminarySummary.candidates[1]!.candidate.id}`,
              ],
              page: { next_cursor: null, has_more: false, limit: 50 },
              data_version: "candidate-live",
              exposure_class: "preliminary",
              preliminary: true,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
    const { dataAdapter } = await import("./fixture-adapter");

    const release = await dataAdapter.getRelease({ include: "review" });

    expect(release.department_rollup).toEqual([
      {
        id: "scope:01",
        code: "01",
        name: "ANTIOQUIA",
        valid_votes: 117,
        candidates: {
          [preliminarySummary.candidates[0]!.candidate.id]: 70,
          [preliminarySummary.candidates[1]!.candidate.id]: 44,
        },
        mesas_reported: null,
      },
      {
        id: "scope:16",
        code: "16",
        name: "BOGOTA D.C.",
        valid_votes: 225,
        candidates: {
          [preliminarySummary.candidates[0]!.candidate.id]: 90,
          [preliminarySummary.candidates[1]!.candidate.id]: 130,
        },
        mesas_reported: null,
      },
    ]);
    expect(
      requested.some((url) =>
        url.includes("/geographies/CO/children-results?level=department"),
      ),
    ).toBe(true);
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
