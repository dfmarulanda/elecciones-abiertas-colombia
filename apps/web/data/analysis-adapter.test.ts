import { afterEach, describe, expect, it, vi } from "vitest";

const releaseId = "release-public";
const election = "presidencia-2026-segunda-vuelta";
const hash = "a".repeat(64);
const analysisReleaseId = "analysis-release-1";
const disclosure = {
  es: "Una anomalía prioriza revisión y no es una probabilidad ni un hallazgo de fraude. Una explicación posterior no elimina la anomalía detectada; la ausencia de explicación en los datos disponibles tampoco prueba fraude ni error.",
  en: "An anomaly prioritizes review and is not a probability or finding of fraud. A later explanation does not erase the detected anomaly; absence of an explanation in available data does not prove fraud or error.",
};
const provenance = {
  data_version: releaseId,
  source_type: "scrutiny",
  legal_status: "official_scrutiny",
  source_url: "https://example.test/source",
  retrieved_at: "2026-08-04T12:00:00Z",
  content_hash: hash,
  parser_version: "parser-v1",
  transform_version: "transform-v1",
  methodology_version: "method-v1",
};
const analysisRelease = {
  analysis_release_id: analysisReleaseId,
  methodology_version: "method-v1",
  source_release_id: releaseId,
  election_slug: election,
  exposure_tier: "preliminary_research",
  preliminary_caveat: {
    es: "Investigacion preliminar.",
    en: "Preliminary research.",
  },
  artifact_status: "available",
  evaluable: true,
  status_reasons: ["independent_validation_pending"],
  canonical_input_hash: hash,
  manifest_hash: hash,
  provenance_hash: hash,
  generated_at: "2026-08-04T11:00:00Z",
  approved_at: "2026-08-04T12:00:00Z",
};
const anomaly = {
  id: "anomaly-1",
  mesa_id: "MESA-1",
  anomaly_types: ["cross_source_documentary"],
  is_anomaly: true,
  audit_priority_score: 70,
  explanation: {
    status: "non_evaluable",
    quantitative_effect: { value: null, status: "unknown" },
    quantitative_p_value: { value: null, status: "unknown" },
  },
  minimum_ballot_edits: { value: null, status: "unknown" },
  minimum_ballot_edits_status: "not_evaluable",
  minimum_ballot_edits_reason:
    "complete_mutually_exclusive_ballot_categories_not_published",
  components: [
    {
      component_type: "documentary_difference_major",
      points: 70,
      observed_value: 0,
      comparator: "Official compatible source",
      calculation: "0 − 0 = 0",
      peer_definition: null,
      limitations: { es: "Límite", en: "Limit" },
      source_links: ["https://example.test/source"],
      analysis: {
        kind: "documentary",
        eligibility: "eligible",
        reason: null,
      },
    },
  ],
  research_preview: true,
  ineligible_reasons: ["validation_not_published"],
  methodology_version: "method-v1",
  disclosure,
  provenance,
  analysis_release: analysisRelease,
  family: "cross-source-documentary",
  evidence_tier: "deterministic",
  evaluability: "evaluable",
  public_evidence: {},
  calculations: {},
  limitations: ["Document review is scoped to linked official records."],
  provenance_hash: hash,
  typed_components: [],
};
const releases = [
  {
    release_id: releaseId,
    election_slug: election,
    name_es: "Elección",
    name_en: "Election",
    round: 2,
    election_date: "2026-06-21",
    status: "published",
    methodology_version: "method-v1",
    release_manifest_hash: hash,
    exposure_approved_at: "2026-08-04T12:00:00Z",
    sources: [],
  },
];
const summary = {
  election_slug: election,
  data_version: releaseId,
  methodology_version: "method-v1",
  total_records_evaluated: { value: 1, status: "observed" },
  anomaly_count: { value: 1, status: "observed" },
  anomaly_counts: {
    cross_source_documentary: { value: 1, status: "observed" },
  },
  missingness: {
    expected: 1,
    retrieved: 1,
    parsed: 1,
    missing: 0,
    ambiguous: 0,
    excluded: 0,
  },
  research_preview: true,
  ineligible_reasons: ["validation_not_published"],
  disclosure,
  provenance,
  analysis_release: analysisRelease,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockPublicApi(
  options: {
    crossedVersion?: boolean;
    crossedMethodology?: boolean;
    invalidDetail?: boolean;
  } = {},
) {
  const requested: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      requested.push(url);
      if (url.endsWith("/api/v1/release-elections")) return json(releases);
      if (url.endsWith("/analysis/summary"))
        return json(
          options.crossedMethodology
            ? { ...summary, methodology_version: "method-v2" }
            : summary,
        );
      if (url.includes("/analysis/anomalies?"))
        return json({
          items: [anomaly],
          page: { next_cursor: null, has_more: false, limit: 25 },
          data_version: options.crossedVersion ? "other-release" : releaseId,
          methodology_version: "method-v1",
          disclosure,
          analysis_release: analysisRelease,
        });
      if (url.includes("/analysis/anomalies/anomaly-1"))
        return json(options.invalidDetail ? { id: "anomaly-1" } : anomaly);
      if (url.includes("/analysis/artifacts?"))
        return json({ items: [], analysis_release: analysisRelease });
      if (
        /\/analysis\/(model_diagnostics|validation|local_sensitivity)\?/.test(
          url,
        ) ||
        url.includes("/outcome-sensitivity?")
      )
        return json({ detail: "Not published" }, 404);
      throw new Error(`Unexpected URL: ${url}`);
    }),
  );
  return requested;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("frozen public analysis adapter", () => {
  it("pins the release and preserves type/cursor filters and an observed zero", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    const requested = mockPublicApi();
    const { getPublicAnalysis } = await import("./analysis-adapter");

    const state = await getPublicAnalysis({
      release: releaseId,
      election,
      anomalyType: "cross_source_documentary",
      cursor: "next-page",
    });

    expect(state.status).toBe("ready");
    if (state.status !== "ready") throw new Error("Expected ready analysis");
    expect(state.anomalies.items.at(0)?.components.at(0)?.observed_value).toBe(
      0,
    );
    const listUrl = new URL(
      requested.find((url) => url.includes("/analysis/anomalies?"))!,
    );
    expect(listUrl.pathname).toContain(
      `/releases/${releaseId}/elections/${election}`,
    );
    expect(listUrl.searchParams.get("anomaly_type")).toBe(
      "cross_source_documentary",
    );
    expect(listUrl.searchParams.get("cursor")).toBe("next-page");
    expect(listUrl.searchParams.get("analysis_release")).toBe(
      analysisReleaseId,
    );
    expect(state.analysisRelease.analysis_release_id).toBe(analysisReleaseId);
    expect(state.reports.validation.status).toBe("unavailable");
    expect(state.outcomeSensitivity.status).toBe("unavailable");
    expect(vi.mocked(fetch)).toHaveBeenCalled();
    for (const [, init] of vi.mocked(fetch).mock.calls) {
      expect(init).toMatchObject({ cache: "no-store" });
    }
  });

  it("fails closed when analytical resources cross release versions", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    mockPublicApi({ crossedVersion: true });
    const { getPublicAnalysis } = await import("./analysis-adapter");

    const state = await getPublicAnalysis({ release: releaseId, election });

    expect(state.status).toBe("error");
    if (state.status === "error")
      expect(state.error?.message).toMatch(/crossed immutable release scope/i);
  });

  it("fails closed when analytical resources cross methodology versions", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    mockPublicApi({ crossedMethodology: true });
    const { getPublicAnalysis } = await import("./analysis-adapter");

    const state = await getPublicAnalysis({ release: releaseId, election });

    expect(state.status).toBe("error");
    if (state.status === "error")
      expect(state.error?.message).toMatch(/crossed methodology versions/i);
  });

  it("narrows the contract-unknown detail response instead of trusting it", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:9999");
    mockPublicApi({ invalidDetail: true });
    const { getPublicAnalysisAnomaly } = await import("./analysis-adapter");

    const state = await getPublicAnalysisAnomaly("anomaly-1", {
      release: releaseId,
      election,
    });

    expect(state.status).toBe("error");
    if (state.status === "error")
      expect(state.error?.message).toMatch(
        /does not match the frozen contract/i,
      );
  });

  it("keeps an unconfigured fixture explicit instead of inventing analysis", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    const { getPublicAnalysis } = await import("./analysis-adapter");

    await expect(getPublicAnalysis()).resolves.toMatchObject({
      status: "fixture",
      releases: [],
    });
  });
});
