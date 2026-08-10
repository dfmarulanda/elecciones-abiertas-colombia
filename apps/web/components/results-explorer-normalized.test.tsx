// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PublicExplorer } from "@/data/fixture-adapter";
import { publicResultLabels } from "@/lib/public-labels";

import { ResultsExplorer } from "./results-explorer";

vi.mock("./result-map", () => ({ ResultMap: () => <div /> }));

afterEach(cleanup);

const explorer: PublicExplorer = {
  kind: "normalized",
  filters: {
    release: "release-2026-r2",
    election: "presidencia-2026-segunda-vuelta",
    geography: "CO-11001",
    baselineRelease: "historical-2022-r2",
    baselineElection: "presidencia-2022-segunda-vuelta",
    comparisonGrain: "municipality",
  },
  releases: [
    {
      release_id: "release-2026-r2",
      election_slug: "presidencia-2026-segunda-vuelta",
      name_es: "Presidencia 2026 · segunda vuelta",
      name_en: "2026 presidency · second round",
      round: 2,
      election_date: "2026-06-21",
      status: "published",
      methodology_version: "v1",
      release_manifest_hash: "a".repeat(64),
      exposure_approved_at: "2026-08-01T00:00:00Z",
      sources: [
        {
          id: "source-e26",
          source_type: "final_declaration",
          legal_status: "controlling_final",
          source_url: "https://example.test/e26",
          content_hash: "b".repeat(64),
        },
      ],
    },
    {
      release_id: "historical-2022-r2",
      election_slug: "presidencia-2022-segunda-vuelta",
      name_es: "Presidencia 2022 · segunda vuelta",
      name_en: "2022 presidency · second round",
      round: 2,
      election_date: "2022-06-19",
      status: "published",
      methodology_version: null,
      release_manifest_hash: "c".repeat(64),
      exposure_approved_at: "2026-08-01T00:00:00Z",
      sources: [],
    },
  ],
  selected: undefined,
  results: {
    data_version: "release-2026-r2",
    page: { has_more: false, limit: 50, next_cursor: null },
    items: [],
  },
  geographyPath: [],
  comparison: {
    comparison_status: "descriptive_context_only",
    eligible_for_integrity_analysis: false,
    comparison_key: "approved-context",
    geography_crosswalk_version: "geo-v1",
    geography_approved_at: "2026-08-01T00:00:00Z",
    baseline_geography_id: "CO-11001-2022",
    data_version: "release-2026-r2",
    baseline_data_version: "historical-2022-r2",
    geography_id: "CO-11001",
    requested_grain: "municipality",
    items: [],
  },
};

describe("normalized public explorer", () => {
  it("labels an approved candidate context as preliminary, never published", () => {
    const preliminary = {
      ...explorer.releases[0]!,
      status: "candidate" as const,
      exposure_class: "preliminary" as const,
      exposure_approved_at: null,
    };
    render(
      <ResultsExplorer
        explorer={{ ...explorer, selected: preliminary }}
        locale="es"
        filters={explorer.filters}
        enumLabels={publicResultLabels("es")}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Resultados preliminares" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: /resultados preliminares/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Resultados publicados" }),
    ).not.toBeInTheDocument();
  });

  it("lists only supplied public releases and labels 2022 as descriptive-only", () => {
    render(
      <ResultsExplorer
        explorer={explorer}
        locale="es"
        filters={explorer.filters}
        enumLabels={publicResultLabels("es")}
      />,
    );
    expect(screen.getByText("release-2026-r2")).toBeInTheDocument();
    expect(screen.getByText("historical-2022-r2")).toBeInTheDocument();
    expect(screen.queryByText(/candidate release/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/eligible_for_integrity_analysis: false/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/contexto descriptivo únicamente/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: /baseline histórico publicado/i }),
    ).toHaveTextContent("Presidencia 2022");
    expect(
      screen.getByRole("list", {
        name: /contextos históricos publicados disponibles/i,
      }),
    ).toHaveTextContent("historical-2022-r2");
    expect(screen.getByText(/contextos 2018/i)).toBeInTheDocument();
    expect(screen.getByText(/no significa cero/i)).toBeInTheDocument();
  });

  it("renders a human reason when an approved crosswalk is absent", () => {
    render(
      <ResultsExplorer
        explorer={{
          ...explorer,
          comparison: {
            comparison_status: "not_comparable",
            reason: "missing_geography_crosswalk",
            data_version: "release-2026-r2",
            baseline_data_version: "historical-2022-r2",
            geography_id: "CO-11001",
            requested_grain: "municipality",
          },
        }}
        locale="es"
        filters={explorer.filters}
        enumLabels={publicResultLabels("es")}
      />,
    );
    expect(
      screen.getByText(/falta la tabla de equivalencia geográfica/i),
    ).toBeInTheDocument();
  });

  it("keeps an unpublished 2018 baseline out of the English list and states the mesa gate", () => {
    render(
      <ResultsExplorer
        explorer={{
          ...explorer,
          filters: {
            ...explorer.filters,
            baselineRelease: "historical-2018-r1-candidate",
            baselineElection: "presidencia-2018-primera-vuelta",
            comparisonGrain: "mesa",
          },
          comparison: {
            comparison_status: "not_comparable",
            reason: "missing_geography_crosswalk",
            data_version: "release-2026-r2",
            baseline_data_version: "historical-2018-r1-candidate",
            geography_id: "CO-11001",
            requested_grain: "mesa",
          },
        }}
        locale="en"
        filters={{
          ...explorer.filters,
          baselineRelease: "historical-2018-r1-candidate",
          baselineElection: "presidencia-2018-primera-vuelta",
          comparisonGrain: "mesa",
        }}
        enumLabels={publicResultLabels("en")}
      />,
    );
    expect(
      screen.getByRole("combobox", { name: /published historical baseline/i }),
    ).not.toHaveTextContent("historical-2018-r1-candidate");
    expect(screen.getByText(/including 2018 contexts/i)).toBeInTheDocument();
    expect(screen.getByText(/mesa comparisons are enabled only/i)).toBeInTheDocument();
    expect(screen.getByText(/crosswalk is missing/i)).toBeInTheDocument();
  });
});
