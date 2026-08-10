// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicAnalysisReady } from "@/data/analysis-adapter";

import { AnalysisUnavailable, AnalysisWorkspace } from "./analysis-workspace";

const hash = "a".repeat(64);
const analysisRelease = {
  analysis_release_id: "analysis-release-1",
  methodology_version: "analysis-method-v1",
  source_release_id: "candidate-release-1",
  election_slug: "presidencia-2026",
  exposure_tier: "preliminary_research",
  preliminary_caveat: {
    es: "Investigación preliminar; no es una conclusión certificada.",
    en: "Preliminary research; this is not a certified conclusion.",
  },
  artifact_status: "available",
  evaluable: true,
  status_reasons: ["independent_validation_pending"],
  canonical_input_hash: hash,
  manifest_hash: hash,
  provenance_hash: hash,
  generated_at: "2026-08-10T12:00:00Z",
  approved_at: "2026-08-10T13:00:00Z",
} as const;

const state = {
  status: "ready",
  releases: [
    {
      release_id: "candidate-release-1",
      election_slug: "presidencia-2026",
      name_es: "Presidencia 2026",
      name_en: "2026 presidential election",
      round: 2,
      election_date: "2026-06-21",
      status: "candidate",
      exposure_class: "preliminary",
      methodology_version: null,
      release_manifest_hash: hash,
      exposure_approved_at: null,
      sources: [],
    },
  ],
  selected: {
    release_id: "candidate-release-1",
    election_slug: "presidencia-2026",
    name_es: "Presidencia 2026",
    name_en: "2026 presidential election",
    round: 2,
    election_date: "2026-06-21",
    status: "candidate",
    exposure_class: "preliminary",
    methodology_version: null,
    release_manifest_hash: hash,
    exposure_approved_at: null,
    sources: [],
  },
  filters: {},
  analysisRelease,
  summary: {
    election_slug: "presidencia-2026",
    data_version: "candidate-release-1",
    methodology_version: "analysis-method-v1",
    total_records_evaluated: { value: 120, status: "observed" },
    anomaly_count: { value: 3, status: "observed" },
    anomaly_counts: {
      structural_arithmetic: { value: 3, status: "observed" },
      identity_coverage: { value: 0, status: "observed" },
      cross_source_documentary: { value: 0, status: "observed" },
      peer_distribution: { value: null, status: "unavailable" },
      spatial: { value: null, status: "unavailable" },
    },
    missingness: {
      expected: 123,
      retrieved: 123,
      parsed: 120,
      missing: 0,
      ambiguous: 0,
      excluded: 3,
    },
    research_preview: true,
    ineligible_reasons: ["independent_validation_pending"],
    disclosure: {
      es: "Una señal no prueba fraude ni votos afectados.",
      en: "A signal does not prove fraud or affected votes.",
    },
    provenance: {
      data_version: "candidate-release-1",
      source_type: "precount",
      legal_status: "preliminary_informational",
      source_url: "https://example.test/source",
      retrieved_at: "2026-08-10T12:00:00Z",
      content_hash: hash,
      parser_version: "parser-v1",
      transform_version: "transform-v1",
      methodology_version: "analysis-method-v1",
    },
    analysis_release: analysisRelease,
  },
  anomalies: {
    items: [],
    page: { next_cursor: null, has_more: false, limit: 25 },
    data_version: "candidate-release-1",
    methodology_version: "analysis-method-v1",
    disclosure: {
      es: "Una señal no prueba fraude ni votos afectados.",
      en: "A signal does not prove fraud or affected votes.",
    },
    analysis_release: analysisRelease,
  },
  reports: {
    model_diagnostics: {
      status: "unavailable",
      reason: "report_not_published",
    },
    validation: { status: "unavailable", reason: "report_not_published" },
    local_sensitivity: {
      status: "unavailable",
      reason: "report_not_published",
    },
  },
  outcomeSensitivity: {
    status: "unavailable",
    reason: "documentary_registry_not_validated",
  },
  artifacts: {
    status: "available",
    value: [
      {
        artifact_id: "manifest",
        kind: "run_manifest",
        schema_version: "1",
        media_type: "application/json",
        record_count: 1,
        byte_size: 100,
        byte_hash: hash,
        content_hash: hash,
        url: `https://artifacts.example.test/${hash}/manifest.json`,
        status: "available",
        status_reasons: [],
      },
    ],
  },
} as unknown as PublicAnalysisReady;

beforeEach(() => vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.test"));
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("analysis evidence portal", () => {
  it("orders every evidence tier and exposes explicit unavailable reasons", () => {
    const { container } = render(
      <AnalysisWorkspace locale="en" analysis={state} />,
    );
    const text = container.textContent ?? "";
    const ordered = [
      "The short answer",
      "Release, coverage, and missingness",
      "Descriptive insights",
      "Deterministic review priorities",
      "Peer-distribution preview",
      "Spatial status",
      "Outcome sensitivity",
      "Expert diagnostics, validation, provenance, and downloads",
    ];
    ordered.reduce((previous, heading) => {
      const position = text.indexOf(heading);
      expect(position, heading).toBeGreaterThan(previous);
      return position;
    }, -1);
    expect(container).toHaveTextContent("Documentary registry not validated");
    expect(container).toHaveTextContent("Report not published");
    expect(container).toHaveTextContent(
      "A signal does not prove fraud or affected votes.",
    );
  });

  it("uses one composite context control and keeps the analysis id in links", () => {
    render(<AnalysisWorkspace locale="en" analysis={state} />);

    expect(screen.getByLabelText("Release, election, and analysis")).toBe(
      screen.getByRole("combobox", {
        name: "Release, election, and analysis",
      }),
    );
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(screen.queryByRole("combobox", { name: "Release" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Election" })).toBeNull();
    expect(screen.getByRole("link", { name: /download/i })).toHaveAttribute(
      "href",
      expect.stringContaining("analysis_release=analysis-release-1"),
    );
  });

  it("derives preliminary framing and evidence status from API metadata", () => {
    render(<AnalysisWorkspace locale="en" analysis={state} />);

    expect(screen.getAllByText("Preliminary research").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText(analysisRelease.preliminary_caveat.en),
    ).toBeVisible();
    expect(
      screen.getByText("Candidate release · preliminary reading."),
    ).toBeVisible();
  });

  it("keeps an unavailable candidate context preliminary", () => {
    render(
      <AnalysisUnavailable
        locale="en"
        status="unavailable"
        selected={state.selected}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: "The preliminary analysis is unavailable",
      }),
    ).toBeVisible();
    expect(
      screen.getByText("Candidate release · preliminary reading."),
    ).toBeVisible();
  });
});
