// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { components } from "@elecciones/contracts";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import {
  OutcomeSensitivityPanel,
  ReviewSignalDetails,
} from "./investigation-details";

type Outcome = components["schemas"]["OutcomeSensitivity"];

const base: Outcome = {
  release_id: "release-public",
  election_slug: "presidencia-2026",
  data_version: "release-public",
  margin_shift_factor: 2,
  status: "not_evaluable",
  evaluable: false,
  issues: [],
  scope: null,
  outcome_source: null,
  leader_id: null,
  runner_up_id: null,
  leader_votes: null,
  runner_up_votes: null,
  observed_margin_votes: null,
  verified_record_ids: null,
  unresolved_record_ids: null,
  verified_affected_votes: null,
  verified_margin_shift_bound: null,
  unresolved_affected_vote_upper_bound: null,
  unresolved_margin_shift_upper_bound: null,
  combined_affected_vote_upper_bound: null,
  combined_margin_shift_upper_bound: null,
  verified_margin_headroom: null,
  combined_margin_headroom: null,
  tie_possible_from_verified: null,
  lead_change_possible_from_verified: null,
  tie_possible_including_unresolved: null,
  lead_change_possible_including_unresolved: null,
  source_links: [],
  evidence_hash: null,
  output_hash: "a".repeat(64),
  methodology_version: "outcome-sensitivity-v3.0.0",
  calculation: "Documentary bounds only.",
  limitations: ["No statistical values are affected votes."],
};

afterEach(cleanup);

describe("outcome sensitivity panel", () => {
  it("labels all published result states in plain language", () => {
    const cases: Array<[Outcome["status"], string]> = [
      ["not_evaluable", "No evaluable"],
      [
        "robust_within_evaluated_bounds",
        "Robusto dentro de los límites evaluados",
      ],
      [
        "tie_within_verified_bound",
        "Empate posible dentro del límite verificado",
      ],
      [
        "lead_change_within_verified_bound",
        "Cambio de liderazgo posible dentro del límite verificado",
      ],
      [
        "tie_only_with_unresolved_bound",
        "Empate posible solo al incluir registros no resueltos",
      ],
      [
        "lead_change_only_with_unresolved_bound",
        "Cambio de liderazgo posible solo al incluir registros no resueltos",
      ],
    ];
    for (const [status, label] of cases) {
      const { unmount } = render(
        <OutcomeSensitivityPanel
          locale="es"
          outcome={{ ...base, status, evaluable: status !== "not_evaluable" }}
        />,
      );
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it("calls an absent endpoint not available rather than zero", () => {
    render(<OutcomeSensitivityPanel locale="en" outcome={null} />);
    expect(
      screen.getByText(/not available for this public release/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("Source, grain, and limits")).toBeInTheDocument();
  });

  it("surfaces blocking issues without rendering decision bounds when not evaluable", () => {
    render(
      <OutcomeSensitivityPanel
        locale="en"
        outcome={{
          ...base,
          issues: [
            {
              code: "missing_compatible_outcome_source",
              record_ids: ["fact-1"],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("Not evaluable")).toBeInTheDocument();
    expect(
      screen.getByText(/cannot evaluate or publish decision bounds/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/missing compatible outcome source/i),
    ).toHaveTextContent("fact-1");
    expect(screen.queryByText("Observed margin")).not.toBeInTheDocument();
  });

  it("renders supplied bounds only for an evaluable outcome", () => {
    render(
      <OutcomeSensitivityPanel
        locale="en"
        outcome={{
          ...base,
          status: "robust_within_evaluated_bounds",
          evaluable: true,
          observed_margin_votes: 54,
          verified_margin_shift_bound: 12,
          unresolved_margin_shift_upper_bound: 8,
          verified_margin_headroom: 42,
          combined_margin_headroom: 34,
        }}
      />,
    );

    expect(
      screen.getByText("Robust within evaluated bounds"),
    ).toBeInTheDocument();
    expect(screen.getByText("Observed margin").parentElement).toHaveTextContent(
      "54",
    );
    expect(screen.queryByText("Blocking conditions")).not.toBeInTheDocument();
  });

  it("includes the exact supplied signal provenance in expert details", async () => {
    const { fixtureAdapter } = await import("@/data/fixture-adapter");
    const release = await fixtureAdapter.getRelease();
    const signal = release.review_signals[0]!;

    render(<ReviewSignalDetails locale="en" signal={signal} />);

    expect(screen.getByText("Exact signal provenance")).toBeInTheDocument();
    expect(
      screen.getByText(signal.provenance.data_version),
    ).toBeInTheDocument();
    expect(screen.getByText(signal.provenance.source_url)).toHaveAttribute(
      "href",
      signal.provenance.source_url,
    );
    expect(
      screen.getByText(signal.provenance.content_hash),
    ).toBeInTheDocument();
    expect(screen.getByText(signal.methodology_version)).toBeInTheDocument();
  });
});
