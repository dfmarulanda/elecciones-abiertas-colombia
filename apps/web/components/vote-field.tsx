import React from "react";
import { buildBallots } from "@/lib/hexes";
import type { LeanChildResult } from "@/data/fixture-adapter";

type Locale = "es" | "en";

const PAPER = "#F4F1EA";
const RIO = "#8C8E00";
const HOLLOW = "rgba(196,255,0,.55)";

/** Above this many ballots one hexagon stops meaning one vote. Chosen from the
 * measured path-size budget: ~70-75 bytes of path data per hexagon, so ~1,000
 * cells is the comfortable ceiling for a single figure. */
const ONE_HEX_PER_VOTE_CEILING = 1000;

export type VoteFieldProps = {
  locale: Locale;
  /** Ballots for the leading candidate. */
  a: number;
  /** Ballots for the second candidate. */
  b: number;
  /** Blank ballots. Counted in valid votes, cast for no candidate. */
  blank: number;
  step?: number;
  cols?: number;
  labelA: string;
  labelB: string;
  labelBlank: string;
  /** Rendered when one hexagon stands for more than one ballot. */
  scaleLabel: (perHex: string) => string;
  alt: string;
};

/**
 * The vote field: every ballot drawn as a hexagon.
 *
 * Three quantities, never two. `valid_votes` includes blank ballots
 * (valid = Σcandidates + blank), so giving the runner-up every non-winner cell
 * silently redraws blank ballots as votes for a candidate — 426,848 of them at
 * national grain. Blanks render hollow and are attributed to no one.
 *
 * At mesa grain a real table holds a few hundred ballots, so one hexagon is one
 * vote and the figure is literal. Above the ceiling the field rescales and says
 * so, rather than growing a path the browser has to parse.
 */
export function VoteField({
  locale,
  a,
  b,
  blank,
  step = 11,
  cols = 42,
  labelA,
  labelB,
  labelBlank,
  scaleLabel,
  alt,
}: VoteFieldProps) {
  const total = a + b + blank;
  if (total <= 0) return null;

  const literal = total <= ONE_HEX_PER_VOTE_CEILING;
  const cells = literal ? total : cols * Math.round(ONE_HEX_PER_VOTE_CEILING / cols);
  const perHex = literal ? 1 : Math.max(1, Math.round(total / cells));

  const aCells = literal ? a : Math.round((a / total) * cells);
  const bCells = literal ? b : Math.round((b / total) * cells);
  const blankCells = literal ? blank : Math.max(0, cells - aCells - bCells);

  const figure = buildBallots(aCells, bCells, blankCells, step, cols);
  const nf = new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US");

  return (
    <figure style={{ margin: 0 }}>
      <svg
        viewBox={figure.vb}
        role="img"
        aria-label={alt}
        style={{ display: "block", width: "100%", height: "auto" }}
      >
        <path d={figure.dA} fill={PAPER} />
        <path d={figure.dB} fill={RIO} />
        <path d={figure.dBlank} fill="none" stroke={HOLLOW} strokeWidth={1.2} />
      </svg>
      <figcaption
        className="mono"
        style={{ margin: "12px 0 0", fontSize: 12, color: "#928979" }}
      >
        {literal ? null : `${scaleLabel(nf.format(perHex))} · `}
        {labelA} {nf.format(a)} · {labelB} {nf.format(b)} · {labelBlank}{" "}
        {nf.format(blank)}
      </figcaption>
    </figure>
  );
}

/** Build a field straight from a lean drill-down row. */
export function fieldFromChild(row: LeanChildResult): {
  a: number;
  b: number;
  blank: number;
} {
  const [a = 0, b = 0] = row.k.map((value) => value ?? 0);
  // Blanks are whatever the valid total holds beyond the candidates, never a
  // separately trusted field: that keeps the figure summing to `valid_votes`.
  const blank = Math.max(0, (row.v ?? 0) - a - b);
  return { a, b, blank };
}
