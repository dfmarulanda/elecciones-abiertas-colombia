// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import path from "node:path";

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { components } from "@elecciones/contracts";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import type { ReleaseView } from "@/data/fixture-adapter";
import { reviewDisclosure } from "@/lib/review-disclosure";

import { NationalSummary } from "./national-summary";

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "../../data/fixtures/fixture-release.json"),
    "utf8",
  ),
) as ReleaseView;

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

function renderSummary(
  release: ReleaseView,
  locale: "es" | "en",
  outcomeSensitivity: components["schemas"]["OutcomeSensitivity"] | null = null,
) {
  return render(
    <NationalSummary
      release={release}
      locale={locale}
      t={translator(locale)}
      outcomeSensitivity={outcomeSensitivity}
    />,
  );
}

afterEach(cleanup);

describe("national summary statistics-first reading", () => {
  it("places the status and neutral two-candidate ledger before product CTAs", () => {
    const { container } = renderSummary(fixture, "es");
    const text = container.textContent ?? "";
    const main = container.querySelector("main");

    expect(main).toHaveAttribute("id", "main-content");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(text).toContain(fixture.fixture_notice.es);
    expect(text.indexOf(fixture.fixture_notice.es)).toBeLessThan(
      text.indexOf("Comparación de candidaturas"),
    );
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Presidencia 2026 · segunda vuelta",
    );
    expect(text.indexOf("Fijación sintética")).toBeLessThan(
      text.indexOf("Comparación de candidaturas"),
    );
    expect(text.indexOf("Comparación de candidaturas")).toBeLessThan(
      text.indexOf("Explorar resultados"),
    );
    expect(screen.getAllByText(/Votos válidos/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Qué se está leyendo")).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        "Participación: 80 %. Observado. Votantes / Personas inscritas: 1.200 / 1.500. Observado / Observado.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps missing sensitivity unavailable and treats a paginated review list as partial", () => {
    const partial = structuredClone(fixture);
    partial.review_page = {
      next_cursor: "next",
      has_more: true,
      limit: 10,
    };
    const { container } = renderSummary(partial, "en");

    expect(
      screen.getByText(
        "Outcome sensitivity is unavailable for this version and election.",
      ),
    ).toBeInTheDocument();
    expect(container).toHaveTextContent(
      "More records are outside this paginated window",
    );
    expect(container).toHaveTextContent("not added here as a national total");
  });

  it("keeps the approved review disclosure in each loaded signal", () => {
    renderSummary(fixture, "en");
    if (fixture.review_signals.length) {
      expect(screen.getAllByText(reviewDisclosure.en).length).toBeGreaterThan(
        0,
      );
    }
  });

  it("withholds review rows for a real candidate release even after reconciliation", () => {
    const candidate = structuredClone(fixture);
    candidate.summary.synthetic = false;
    candidate.summary.release_status = "candidate";
    candidate.summary.reconciliation.status = "passed";
    candidate.release.synthetic = false;
    candidate.release.status = "candidate";

    const { container } = renderSummary(candidate, "en");

    expect(screen.getAllByText("Candidate release · preliminary").length).toBe(
      1,
    );
    expect(container).toHaveTextContent("Review rows are withheld");
    expect(container).not.toHaveTextContent(
      candidate.review_signals[0]?.mesa_id ?? "never-present",
    );
    expect(container).not.toHaveTextContent(reviewDisclosure.en);
  });

  it("withholds review rows for an unreconciled real published release", () => {
    const release = structuredClone(fixture);
    release.summary.synthetic = false;
    release.summary.release_status = "published";
    release.summary.reconciliation.status = "blocked";
    release.release.synthetic = false;
    release.release.status = "published";

    const { container } = renderSummary(release, "es");

    expect(container).toHaveTextContent("Las filas de revisión no se muestran");
    expect(container).not.toHaveTextContent(reviewDisclosure.es);
  });

  it("distinguishes unavailable percentages from observed zero", () => {
    const release = structuredClone(fixture);
    release.summary.candidates[0]!.share = null;
    release.summary.candidates[1]!.share = 0;
    release.summary.turnout = null;

    renderSummary(release, "es");

    const candidates = screen.getAllByRole("listitem").slice(0, 2);
    expect(candidates[0]).toHaveTextContent("= No disponible");
    expect(candidates[1]).toHaveTextContent("= 0 %");
    const turnout = screen.getByText("Participación").parentElement;
    expect(turnout).toHaveTextContent("No disponible");
    expect(
      screen.getByLabelText(/^Participación: No disponible\. No disponible\./),
    ).toBeInTheDocument();
  });

  it("names observed zero turnout as zero rather than unavailable", () => {
    const release = structuredClone(fixture);
    release.summary.turnout = 0;

    renderSummary(release, "en");

    expect(
      screen.getByLabelText(/^Turnout: 0%\. Observed\./),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/^Turnout: Unavailable/),
    ).not.toBeInTheDocument();
  });

  it("displays the supplied completion percent without recalculating it", () => {
    const release = structuredClone(fixture);
    release.summary.completion = { reported: 1, expected: 4, percent: 0.3 };

    renderSummary(release, "en");

    expect(
      screen.getAllByText("Reporting progress")[0]!.parentElement,
    ).toHaveTextContent("30% · 1 / 4");
  });

  it("shows only matching components when one signal mixes documentary and statistical inputs", () => {
    const release = structuredClone(fixture);
    const documentary = release.review_signals.find((signal) =>
      signal.components.some(
        (component) =>
          component.component_type === "documentary_difference_major",
      ),
    )!;
    const statistical = release.review_signals.find((signal) =>
      signal.components.some(
        (component) => component.component_type === "peer_distribution",
      ),
    )!;
    documentary.components = [
      documentary.components[0]!,
      statistical.components[0]!,
    ];
    release.review_signals = [documentary];

    renderSummary(release, "en");

    const documentarySection = screen
      .getByRole("heading", { name: "Documentary differences" })
      .closest("section")!;
    const statisticalSection = screen
      .getByRole("heading", { name: "Peer and spatial signals" })
      .closest("section")!;
    expect(documentarySection).toHaveTextContent(
      "Major documentary difference",
    );
    expect(documentarySection).not.toHaveTextContent("Peer comparison");
    expect(statisticalSection).toHaveTextContent("Peer comparison");
    expect(statisticalSection).not.toHaveTextContent(
      "Major documentary difference",
    );
    expect(screen.getAllByText(/Overall audit-priority score/)).toHaveLength(2);
  });

  it.each([
    ["es", "Qué se está leyendo", "¿Las cifras de esta versión concilian?"],
    ["en", "What is being read", "Do the figures in this version reconcile?"],
  ] as const)(
    "keeps essential ladder and analytics CTA symmetric in %s",
    (locale, first, second) => {
      renderSummary(fixture, locale);
      expect(screen.getByRole("heading", { name: first })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: second })).toBeInTheDocument();
      expect(
        screen.getByRole("link", {
          name: locale === "es" ? "Analítica" : "Analytics",
        }),
      ).toHaveAttribute("href", `/${locale}/analitica`);
    },
  );
});
