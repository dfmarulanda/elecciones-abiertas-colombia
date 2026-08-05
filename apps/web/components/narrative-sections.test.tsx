// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import path from "node:path";

import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { TerritoriesSection } from "./narrative-sections";

vi.mock("./coverage-map", () => ({
  CoverageMap: () => <div data-testid="coverage-map-stub" />,
}));

function messages(locale: "es" | "en") {
  return JSON.parse(
    readFileSync(
      path.resolve(process.cwd(), `messages/${locale}.json`),
      "utf8",
    ),
  ) as Record<string, unknown>;
}

function translator(locale: "es" | "en") {
  const dictionary = messages(locale);
  return (key: string) => {
    const value = key
      .split(".")
      .reduce<unknown>(
        (current, segment) =>
          typeof current === "object" && current !== null
            ? (current as Record<string, unknown>)[segment]
            : undefined,
        dictionary,
      );
    if (typeof value !== "string") throw new Error(`Missing message: ${key}`);
    return value;
  };
}

describe("TerritoriesSection", () => {
  it("renders the real two reporting territories with their computed totals, in both languages", () => {
    for (const locale of ["es", "en"] as const) {
      const { unmount } = render(
        <TerritoriesSection locale={locale} t={translator(locale)} />,
      );

      // The real fixture territories, not the earlier antioquia/cundinamarca/valle
      // stand-ins — mesa totals are computed from lib/dc-fixture's MESAS.
      expect(screen.getByText("Bogotá, D. C.")).toBeInTheDocument();
      expect(screen.getByText("Antioquia · Medellín")).toBeInTheDocument();
      expect(screen.getByText("572")).toBeInTheDocument(); // bog: 313 + 259
      expect(screen.getByText("578")).toBeInTheDocument(); // med: 289 + 289
      expect(screen.getAllByText("313").length).toBeGreaterThan(0);
      expect(screen.getAllByText("289").length).toBeGreaterThan(0);

      // The map mount point is present (stubbed here; the real D3 draw is
      // covered by manual/browser verification, not jsdom).
      expect(screen.getByTestId("coverage-map-stub")).toBeInTheDocument();

      unmount();
    }
  });

  it("gives the accessible table real column headers with scope, and marks the 31 uncovered departments distinctly from zero", () => {
    render(<TerritoriesSection locale="es" t={translator("es")} />);

    const table = screen.getByRole("table");
    const headers = within(table).getAllByRole("columnheader");
    expect(headers.length).toBeGreaterThanOrEqual(5);
    for (const header of headers) {
      expect(header).toHaveAttribute("scope", "col");
    }

    // "31" appears as the uncovered-departments count.
    expect(screen.getByText("31")).toBeInTheDocument();

    // The uncovered row's status carries the not-collected label, distinct
    // from an observed zero, via an accessible name (not colour alone).
    expect(
      screen.getByText("Estado: no recolectado (distinto de cero)"),
    ).toBeInTheDocument();
  });
});
