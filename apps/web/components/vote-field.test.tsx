// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { VoteField, fieldFromChild } from "./vote-field";

afterEach(cleanup);

const labels = {
  labelA: "A",
  labelB: "B",
  labelBlank: "Blanco",
  scaleLabel: (perHex: string) => `cada hexágono ≈ ${perHex}`,
  alt: "campo de votos",
};

/** One hexagon is one `M...Z` subpath. */
const countHexes = (d: string | null) => (d ? (d.match(/M/g) ?? []).length : 0);

function paths(container: HTMLElement) {
  const [a, b, blank] = Array.from(container.querySelectorAll("path"));
  return {
    a: countHexes(a?.getAttribute("d") ?? null),
    b: countHexes(b?.getAttribute("d") ?? null),
    blank: countHexes(blank?.getAttribute("d") ?? null),
  };
}

describe("vote field", () => {
  it("draws one hexagon per ballot for a real mesa", () => {
    // The real sample mesa: 92 + 44 + 2 blank = 138 valid votes.
    const { container } = render(
      <VoteField locale="es" a={92} b={44} blank={2} step={17} cols={14} {...labels} />,
    );
    const drawn = paths(container);
    expect(drawn).toEqual({ a: 92, b: 44, blank: 2 });
    expect(drawn.a + drawn.b + drawn.blank).toBe(138);
  });

  it("never draws a blank ballot as a candidate vote", () => {
    // The bug this guards: giving the runner-up every non-winner cell redraws
    // 426,848 blank ballots nationally as votes for a candidate.
    const { container } = render(
      <VoteField locale="es" a={50} b={30} blank={20} step={11} cols={10} {...labels} />,
    );
    expect(paths(container).b).toBe(30);
    expect(paths(container).blank).toBe(20);
  });

  it("rescales above the ceiling and says that it did", () => {
    const { container } = render(
      <VoteField
        locale="es"
        a={12959542}
        b={12708712}
        blank={426848}
        {...labels}
      />,
    );
    const drawn = paths(container);
    expect(drawn.a + drawn.b + drawn.blank).toBeLessThanOrEqual(1100);
    // Blanks survive rescaling rather than being rounded into a candidate.
    expect(drawn.blank).toBeGreaterThan(0);
    expect(screen.getByText(/cada hexágono ≈/)).toBeInTheDocument();
  });

  it("derives blanks from the valid total so the figure always closes", () => {
    // valid_votes INCLUDES blanks, so the remainder is what is not a candidate
    // vote -- computing it any other way lets the figure disagree with the total.
    expect(
      fieldFromChild({
        i: "x", l: "mesa", c: "1", n: "m",
        t: 141, v: 138, b: 2, x: 2, u: 1, k: [92, 44],
      }),
    ).toEqual({ a: 92, b: 44, blank: 2 });
  });

  it("renders nothing rather than an empty frame when a unit has no ballots", () => {
    const { container } = render(
      <VoteField locale="es" a={0} b={0} blank={0} {...labels} />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });
});
