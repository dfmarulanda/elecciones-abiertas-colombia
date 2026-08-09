// @vitest-environment jsdom

import { readFileSync } from "node:fs";
import path from "node:path";

import type { components } from "@elecciones/contracts";
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConteoHero } from "./conteo-hero";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ConteoHero", () => {
  it("allows long candidate legend labels to wrap on narrow screens", () => {
    vi.stubGlobal("React", React);
    const release = JSON.parse(
      readFileSync(
        path.resolve(process.cwd(), "../../data/fixtures/fixture-release.json"),
        "utf8",
      ),
    ) as { summary: components["schemas"]["ElectionSummary"] };
    const messages = JSON.parse(
      readFileSync(path.resolve(process.cwd(), "messages/es.json"), "utf8"),
    ) as Record<string, unknown>;

    render(
      <NextIntlClientProvider locale="es" messages={messages}>
        <ConteoHero locale="es" available summary={release.summary} />
      </NextIntlClientProvider>,
    );

    const legend = screen
      .getAllByText("Candidatura Horizonte · tarjetón 1")
      .find((element) => element.tagName === "SPAN");
    expect(legend).toHaveStyle({
      whiteSpace: "normal",
      overflowWrap: "anywhere",
    });
  });
});
