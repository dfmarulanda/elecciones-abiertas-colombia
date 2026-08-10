// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import {
  AnalysisV2Section,
  AnalysisV2Shell,
  AnalysisV2StateBand,
} from "./analysis-v2-primitives";

afterEach(cleanup);

describe("analytics v2 primitives", () => {
  it("marks the analytics main landmark as design v2", () => {
    render(
      <AnalysisV2Shell ariaLabel="Analytics">
        <p>Body</p>
      </AnalysisV2Shell>,
    );

    expect(screen.getByRole("main", { name: "Analytics" })).toHaveAttribute(
      "data-design-version",
      "v2",
    );
    expect(screen.getByRole("main")).toHaveClass("eac-design", "eac-analysis");
  });

  it("allows suspense fallbacks to use a unique landmark id", () => {
    render(
      <AnalysisV2Shell ariaLabel="Loading analytics" mainId="analysis-loading">
        <p>Loading</p>
      </AnalysisV2Shell>,
    );

    expect(
      screen.getByRole("main", { name: "Loading analytics" }),
    ).toHaveAttribute("id", "analysis-loading");
    expect(document.querySelector("#main-content")).toBeNull();
  });

  it("renders a numbered section with an explicit tone", () => {
    render(
      <AnalysisV2Section
        dataSection="coverage"
        eyebrow="Coverage"
        number="02"
        title="Release status"
        tone="ink"
      >
        <p>Evidence</p>
      </AnalysisV2Section>,
    );

    const section = screen.getByRole("region", { name: "Release status" });
    expect(section).toHaveAttribute("data-analysis-section", "coverage");
    expect(section).toHaveClass("eac-analysis-section--ink");
    expect(screen.getByText("02")).toBeVisible();
    expect(screen.getByText("Evidence")).toBeVisible();
  });

  it("communicates evidence state with text rather than color alone", () => {
    render(
      <AnalysisV2StateBand
        tierLabel="Research preview"
        statusLabel="Not evaluable"
        reasons={["Authenticated coordinates missing"]}
        reasonsLabel="Reasons"
      />,
    );

    const band = screen.getByRole("region", {
      name: "Research preview · Not evaluable",
    });
    expect(band).toHaveTextContent("Research preview");
    expect(band).toHaveTextContent("Not evaluable");
    expect(band).toHaveTextContent("Authenticated coordinates missing");
  });
});
