// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import type { ReleaseView } from "@/data/fixture-adapter";
import { publicResultLabels } from "@/lib/public-labels";

import { ResultsExplorer } from "./results-explorer";
import { ReleaseNotice } from "./page-primitives";

vi.mock("./result-map", () => ({
  ResultMap: () => <div />,
}));

const fixture = JSON.parse(
  readFileSync(
    path.resolve(process.cwd(), "../../data/fixtures/fixture-release.json"),
    "utf8",
  ),
) as ReleaseView;

describe("candidate release notices", () => {
  it("keeps the results route candidate/preliminary", () => {
    const release = structuredClone(fixture);
    release.release.synthetic = false;
    release.release.status = "candidate";
    render(
      <ResultsExplorer
        release={release}
        locale="en"
        filters={{}}
        enumLabels={publicResultLabels("en")}
      />,
    );
    expect(
      screen.getByText(/candidate release · preliminary reading/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/verified release/i)).not.toBeInTheDocument();
  });

  it("keeps a mesa-detail Page candidate/preliminary when status is plumbed", () => {
    render(
      <ReleaseNotice locale="es" synthetic={false} releaseStatus="candidate" />,
    );
    expect(
      screen.getByText(/release candidato · lectura preliminar/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/release inmutable/i)).not.toBeInTheDocument();
  });
});
