/**
 * The vote-hexagon generator, ported from the design's `dc-data.js` exactly —
 * same constants, same rounding (`toFixed`), same draw order. It is the thing
 * that draws every "N votes as N hexagons" figure on the page: the six
 * disputed votes in #reclamos and the 190-vote mesa 003 field in #mesa.
 *
 * Only adaptation from the source: `grid()` returns `{ points, vb }` instead
 * of attaching a `.vb` string property onto the points array. The source
 * relies on JS arrays being ordinary objects to smuggle `vb` alongside the
 * cell list; TypeScript's array typing does not allow that, and the split
 * changes nothing about the geometry or the rounding.
 */

export type Cell = [number, number];

export type Grid = {
  points: Cell[];
  /** Ready-to-use SVG viewBox string, e.g. "0 0 285.0 86.0". */
  vb: string;
};

export type MesaInput = {
  /** Votes for "Horizonte". */
  h: number;
  /** Votes for "Río". */
  r: number;
  /** Votes inside `h` that are in dispute between layers, if any. */
  disp?: number;
};

export type MesaHexes = {
  vb: string;
  /** Undisputed Horizonte votes. */
  dH: string;
  /** Río votes. */
  dR: string;
  /** Disputed votes (a subset of Horizonte's), at full cell size. */
  dD: string;
  /** Disputed votes again, at 0.3x size — the small center dot for the
   * "descontado" (discounted) state. */
  dDot: string;
};

/** Six-decimal source constant for the hex row height; kept unrounded like
 * the original so downstream `toFixed` rounding lands on the same digits. */
const SQRT3 = 1.7320508;

/** One hexagon path per cell, flat-topped, pointed left/right, at radius `r`. */
export function hexes(cells: Cell[], r: number): string {
  const q = +(r * 0.8660254).toFixed(2);
  const half = +(r / 2).toFixed(2);
  let d = "";
  for (let i = 0; i < cells.length; i++) {
    const [x, y] = cells[i] as Cell;
    d +=
      "M" + (x + r).toFixed(1) + " " + y.toFixed(1) +
      "L" + (x + half).toFixed(1) + " " + (y + q).toFixed(1) +
      "L" + (x - half).toFixed(1) + " " + (y + q).toFixed(1) +
      "L" + (x - r).toFixed(1) + " " + y.toFixed(1) +
      "L" + (x - half).toFixed(1) + " " + (y - q).toFixed(1) +
      "L" + (x + half).toFixed(1) + " " + (y - q).toFixed(1) +
      "Z";
  }
  return d;
}

/** Lays out `n` cells into a brick-like hex grid of `cols` columns, each cell
 * `step` apart, with odd columns offset half a row down. Returns the cell
 * centers plus a viewBox sized to exactly fit them. */
export function grid(n: number, step: number, cols: number): Grid {
  const hs = step * 1.5;
  const vs = step * SQRT3;
  const points: Cell[] = [];
  for (let k = 0; k < n; k++) {
    const c = k % cols;
    const row = (k - c) / cols;
    points.push([step + c * hs, step + row * vs + (c % 2 ? vs / 2 : 0)]);
  }
  const rows = Math.ceil(n / cols);
  const vb =
    "0 0 " +
    (step * 2 + (cols - 1) * hs).toFixed(1) +
    " " +
    (step * 2 + (rows - 1) * vs + (cols > 1 ? vs / 2 : 0)).toFixed(1);
  return { points, vb };
}

/**
 * Builds the four path strings a mesa figure needs: the undisputed Horizonte
 * votes, the Río votes, the disputed votes at full size, and the disputed
 * votes again at a third of the size (the "descontado" center dot). `mesa.h`
 * votes are laid out first, then `mesa.r` — the same order the design reads
 * a table's two candidate tallies.
 */
export function build(mesa: MesaInput, step: number, cols: number): MesaHexes {
  const cells = grid(mesa.h + mesa.r, step, cols);
  const from = mesa.disp ? mesa.h - mesa.disp : -1;
  const H: Cell[] = [];
  const R: Cell[] = [];
  const D: Cell[] = [];
  for (let k = 0; k < cells.points.length; k++) {
    const point = cells.points[k] as Cell;
    if (k < mesa.h) {
      (from >= 0 && k >= from ? D : H).push(point);
    } else {
      R.push(point);
    }
  }
  const rr = step * 0.93;
  return {
    vb: cells.vb,
    dH: hexes(H, rr),
    dR: hexes(R, rr),
    dD: hexes(D, rr),
    dDot: hexes(D, rr * 0.3),
  };
}
