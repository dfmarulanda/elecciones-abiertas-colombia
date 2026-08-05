// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  PublicGeographyView,
  PublicMesaView,
  PublicReleaseRef,
} from "@/data/fixture-adapter";

import {
  NormalizedGeographyView,
  NormalizedMesaView,
  NormalizedUnavailable,
} from "./normalized-geography-view";

afterEach(cleanup);

const release: PublicReleaseRef = {
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
      id: "source-scrutiny",
      source_type: "scrutiny",
      legal_status: "official_scrutiny",
      source_url: "https://example.test/e24",
      content_hash: "b".repeat(64),
    },
  ],
};

const provenance = {
  data_version: release.release_id,
  source_type: "scrutiny" as const,
  legal_status: "official_scrutiny" as const,
  source_url: "https://example.test/e24",
  retrieved_at: "2026-08-01T00:00:00Z",
  content_hash: "b".repeat(64),
  parser_version: "parser-v1",
  transform_version: "transform-v1",
  methodology_version: "method-v1",
};
const metric = { value: 120, status: "observed" as const };

describe("normalized geography and mesa views", () => {
  it("links municipality children to polling place and preserves the scoped URL", () => {
    const view: PublicGeographyView = {
      releases: [release],
      selected: release,
      geographyId: "MUN-001",
      path: [
        {
          id: "CO",
          level: "national",
          code: "CO",
          name: "Colombia",
          parent_id: null,
        },
        {
          id: "DEP-11",
          level: "department",
          code: "11",
          name: "Bogotá D.C.",
          parent_id: "CO",
        },
        {
          id: "MUN-001",
          level: "municipality",
          code: "001",
          name: "Bogotá",
          parent_id: "DEP-11",
        },
      ],
      children: {
        data_version: release.release_id,
        page: { has_more: true, next_cursor: "geo-next", limit: 50 },
        items: [
          {
            id: "PLACE-01",
            level: "polling_place",
            code: "01",
            name: "Colegio Central",
            parent_id: "MUN-001",
            canonical_path: "CO/DEP-11/MUN-001/PLACE-01",
            has_published_facts: false,
          },
        ],
      },
    };
    render(
      <NormalizedGeographyView
        view={view}
        locale="es"
        filters={{ source: "scrutiny" }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Bogotá" })).toBeInTheDocument();
    expect(screen.getByText("Municipio")).toBeInTheDocument();
    expect(screen.getByText("1 unidad hija")).toBeInTheDocument();
    expect(screen.getByText("Puesto de votación")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Bogotá" }).parentElement,
    ).toHaveClass("whitespace-nowrap");
    expect(
      screen.getByRole("link", { name: /ver siguiente nivel/i }),
    ).toHaveAttribute(
      "href",
      expect.stringMatching(
        /geografia\/PLACE-01.*release=release-2026-r2.*source=scrutiny/,
      ),
    );
    expect(
      screen.getByRole("link", { name: /siguiente página/i }),
    ).toHaveAttribute("href", expect.stringMatching(/cursor=geo-next/));
  });

  it("renders a direct mesa with exact source and provenance", () => {
    const view: PublicMesaView = {
      releases: [release],
      selected: release,
      mesa: {
        id: "MESA-001",
        display_number: "001",
        polling_place_id: "PLACE-01",
        municipality_id: "MUN-001",
        department_id: "DEP-11",
        data_version: release.release_id,
        geography_path: [
          {
            id: "CO",
            level: "national",
            code: "CO",
            name: "Colombia",
            parent_id: null,
          },
          {
            id: "DEP-11",
            level: "department",
            code: "11",
            name: "Bogotá D.C.",
            parent_id: "CO",
          },
          {
            id: "MUN-001",
            level: "municipality",
            code: "001",
            name: "Bogotá",
            parent_id: "DEP-11",
          },
          {
            id: "PLACE-01",
            level: "polling_place",
            code: "01",
            name: "Colegio Central",
            parent_id: "MUN-001",
          },
          {
            id: "MESA-001",
            level: "mesa",
            code: "001",
            name: "Mesa 001",
            parent_id: "PLACE-01",
          },
        ],
        results: [
          {
            id: "fact-mesa-001",
            election_slug: release.election_slug,
            geography_id: "MESA-001",
            geography_level: "mesa",
            mesa_id: "MESA-001",
            registered_electors: metric,
            voters: metric,
            valid_votes: metric,
            blank_votes: { value: null, status: "unavailable" },
            null_votes: { value: null, status: "unavailable" },
            unmarked_votes: { value: null, status: "unavailable" },
            candidates: [],
            provenance,
          },
        ],
      },
    };
    render(
      <NormalizedMesaView
        view={view}
        locale="en"
        filters={{ source: "scrutiny" }}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Mesa 001" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Source" })).toHaveValue(
      "scrutiny",
    );
    expect(
      screen.getByRole("option", { name: "Scrutiny" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Official scrutiny")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Bogotá" }).parentElement,
    ).toHaveClass("whitespace-nowrap");
    expect(screen.getByText("parser-v1")).toBeInTheDocument();
  });

  it("states typed 404 absence without displaying zero", () => {
    render(<NormalizedUnavailable locale="es" kind="mesa" status={404} />);
    expect(
      screen.getByText(/404.*no existe una publicación/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no se sustituye.*valor cero/i),
    ).toBeInTheDocument();
  });
});
