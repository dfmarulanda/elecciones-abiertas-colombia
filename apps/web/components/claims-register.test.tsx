// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import path from "node:path";

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { ClaimsRegister } from "./claims-register";

function translator(locale: "es" | "en") {
  const dictionary = JSON.parse(
    readFileSync(
      path.resolve(process.cwd(), `messages/${locale}.json`),
      "utf8",
    ),
  ) as Record<string, unknown>;
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

// The six Detector de Mentiras pieces the section cross-references. Kept
// literal here so a typo'd or silently repointed URL fails the suite rather
// than shipping a dead attribution.
const SOURCES = [
  "https://www.lasillavacia.com/detector-de-mentiras/falso/rachas-en-puestos-no-prueban-fraude-como-dijo-petro-y-sucedieron-en-2022/",
  "https://www.lasillavacia.com/detector-de-mentiras/falso/formularios-e-14-no-prueban-fraude-a-favor-de-de-la-espriella-en-segunda-vuelta/",
  "https://www.lasillavacia.com/detector-de-mentiras/falso/grafica-viral-impulsa-narrativa-de-fraude-con-datos-falsos-a-favor-de-cepeda/",
  "https://www.lasillavacia.com/detector-de-mentiras/ni-la-demanda-de-petro-ni-su-pagina-de-pruebas-muestran-fraude-contra-cepeda/",
  "https://www.lasillavacia.com/detector-de-mentiras/petro-lanza-nuevas-denuncias-de-fraude-sin-sustento-tras-segunda-vuelta/",
  "https://www.lasillavacia.com/detector-de-mentiras/falso/coronell-no-ha-concluido-que-las-pruebas-de-petro-comprueban-el-fraude-electoral/",
];

describe("ClaimsRegister cross-check block", () => {
  it("links every cross-referenced claim out to its source, safely, in both languages", () => {
    for (const locale of ["es", "en"] as const) {
      const { unmount } = render(
        <ClaimsRegister locale={locale} t={translator(locale)} />,
      );

      const outbound = screen
        .getAllByRole("link")
        .filter((link) =>
          (link.getAttribute("href") ?? "").includes("lasillavacia.com"),
        );
      expect(outbound.map((link) => link.getAttribute("href"))).toEqual(
        SOURCES,
      );
      for (const link of outbound) {
        expect(link).toHaveAttribute("target", "_blank");
        // Both tokens: noopener for the opener handle, noreferrer so the
        // outbound click does not leak this site's URL as a referrer.
        expect(link).toHaveAttribute("rel", "noopener noreferrer");
        // The articles are Spanish-only, including from the English page.
        expect(link).toHaveAttribute("hreflang", "es");
        expect(link.textContent?.trim().length ?? 0).toBeGreaterThan(0);
      }

      unmount();
    }
  });

  it("attributes each rating to the newsroom rather than presenting it as this site's verdict", () => {
    for (const locale of ["es", "en"] as const) {
      const t = translator(locale);
      const { unmount } = render(<ClaimsRegister locale={locale} t={t} />);

      // Every cross-referenced card carries the source's name and labels the
      // rating as theirs ("Su veredicto" / "Their verdict").
      expect(
        screen.getAllByText(t("claims.crossChecked.sourceLabel")),
      ).toHaveLength(SOURCES.length);
      const attributed = screen
        .getAllByText(
          new RegExp(`^${t("claims.crossChecked.verdictPrefix")} ·`),
        )
        .map((node) => node.textContent ?? "");
      expect(attributed).toHaveLength(SOURCES.length);
      for (const key of ["runs", "forms", "viralChart", "attribution"]) {
        expect(attributed).toContain(
          `${t("claims.crossChecked.verdictPrefix")} · ${t(`claims.crossChecked.${key}.verdictTag`)}`,
        );
      }

      // This site's own tag on those cards says only that someone else also
      // looked — it never repeats their rating as a finding of ours.
      expect(
        screen.getAllByText(t("claims.crossChecked.verdict")),
      ).toHaveLength(SOURCES.length);

      unmount();
    }
  });

  it("says the repository computes the runs test itself and treats the outcome as neutral", () => {
    render(<ClaimsRegister locale="es" t={translator("es")} />);

    const answer = translator("es")("claims.crossChecked.runs.answer");
    expect(screen.getByText(answer)).toBeInTheDocument();
    // The two load-bearing facts about pipeline/.../runs_replication.py: it
    // runs the same test, and its result is a neutral association that is
    // never eligible for public review-priority points.
    expect(answer).toContain("Wald–Wolfowitz");
    expect(answer).toContain("asociación de investigación neutral");
    expect(answer).toContain("prioridad de revisión");

    const method = translator("es")("claims.crossChecked.runs.method");
    expect(screen.getByText(method)).toBeInTheDocument();
    expect(method).toContain("max-T");
  });
});
