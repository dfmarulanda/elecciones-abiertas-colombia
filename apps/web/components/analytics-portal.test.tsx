// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import path from "node:path";

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { ReleaseView } from "@/data/fixture-adapter";

import { AnalyticsPortal, calculateCandidateMargin } from "./analytics-portal";

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "../../data/fixtures/fixture-release.json"),
    "utf8",
  ),
) as ReleaseView;

afterEach(cleanup);

describe("analytics portal", () => {
  it("derives the national two-candidate margin from summary data", () => {
    const margin = calculateCandidateMargin(fixture.summary.candidates);

    expect(margin?.votes).toBe(54);
    expect(margin?.share).toBeCloseTo(0.0469565218);
  });

  it("renders a bilingual, source-scoped analytical reading", () => {
    render(<AnalyticsPortal locale="es" release={fixture} />);

    expect(
      screen.getByRole("heading", { name: "Portal de analítica electoral" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("54 votos")).toHaveLength(1);
    expect(screen.getByText("4,7 puntos porcentuales")).toBeInTheDocument();
    expect(screen.getByText("Cadena de publicación")).toBeInTheDocument();
    expect(screen.getByText("Faltantes").nextElementSibling).toHaveTextContent(
      "0",
    );
    expect(
      screen.getAllByText(
        "Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.",
      ),
    ).toHaveLength(4);
    expect(
      screen.getByText(
        "No disponible para esta versión pública. La ausencia no equivale a cero ni permite una conclusión sobre el resultado.",
      ),
    ).toBeInTheDocument();
  });

  it("names unknown metrics instead of coercing them to zero", () => {
    const unknownRelease = structuredClone(fixture);
    unknownRelease.summary.voters = { value: null, status: "unknown" };
    unknownRelease.summary.turnout = null;

    render(<AnalyticsPortal locale="en" release={unknownRelease} />);

    expect(screen.getAllByText(/Unknown/).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: "Election analytics portal" }),
    ).toBeInTheDocument();
  });

  it("treats null geographic coverage as absent", () => {
    const releaseWithoutCoverage = structuredClone(fixture);
    releaseWithoutCoverage.summary.geographic_collection_coverage = null;

    render(<AnalyticsPortal locale="en" release={releaseWithoutCoverage} />);

    expect(
      screen.queryByRole("complementary", {
        name: "Geographic coverage limit",
      }),
    ).not.toBeInTheDocument();
  });

  it("does not interpret an unrun candidate analysis as no anomalies", () => {
    const candidateRelease = structuredClone(fixture);
    candidateRelease.release.synthetic = false;
    candidateRelease.release.status = "candidate";
    candidateRelease.summary.reconciliation.status = "blocked";
    candidateRelease.review_signals = [];

    render(<AnalyticsPortal locale="es" release={candidateRelease} />);

    expect(
      // Sentence case in the DOM, uppercased by `.ec-mark`. Screen readers
      // spell shouty literals out letter by letter; CSS-cased text they read
      // as a word, so the casing lives in the stylesheet.
      screen.getByText("Release candidato · lectura preliminar."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "El análisis de señales no se ha publicado para esta versión. Una lista vacía no significa que no existan anomalías.",
      ),
    ).toBeInTheDocument();
  });

  it("anchors review leads in a municipality and keeps a single mesa singular", () => {
    const singularBulletin = structuredClone(fixture);
    const firstBulletin = singularBulletin.bulletins[0];
    if (!firstBulletin) throw new Error("Fixture requires a bulletin");
    singularBulletin.bulletins = [
      {
        ...firstBulletin,
        expected_mesas: 1,
        reported_mesas: 1,
      },
    ];

    render(<AnalyticsPortal locale="en" release={singularBulletin} />);

    expect(screen.getAllByText("Bogotá, D. C.").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 mesa$/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Mathematics detects unusual patterns and prioritizes documentary review. It does not establish intent, fraud, or responsibility.",
      ),
    ).toBeInTheDocument();
  });
});
