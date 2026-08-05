// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { GeographicCoverageNotice } from "./geographic-coverage-notice";

describe("GeographicCoverageNotice", () => {
  it("plainly distinguishes a mesa sample from national coverage in both languages", () => {
    const coverage = {
      status: "sample_limited" as const,
      expected_polling_places: 1,
      retrieved_polling_places: 1,
      expected_mesas: 122_020,
      retrieved_mesas: 36,
    };
    const { rerender } = render(
      <GeographicCoverageNotice coverage={coverage} locale="es" />,
    );
    expect(
      screen.getByText(/muestra, no una cobertura nacional/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/36.*122[.\u00a0,]?020/)).toBeInTheDocument();
    rerender(<GeographicCoverageNotice coverage={coverage} locale="en" />);
    expect(
      screen.getByText(/sample, not national coverage/i),
    ).toBeInTheDocument();
  });
});
