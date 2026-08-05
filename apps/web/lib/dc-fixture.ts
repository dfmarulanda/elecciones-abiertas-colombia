/**
 * The mesa and territory fixture data behind #territorios, ported from the
 * design's `dc-data.js` exactly — same six mesas, same disputed count on
 * mesa 003, same two reporting territories. Nothing here is inferred: the
 * per-territory totals below are *computed* from `MESAS`, the same way the
 * source's `renderVals()` computes `territoryRows`, so the map markers, the
 * accessible table and any future consumer read one number, not three
 * hand-typed copies of it.
 *
 * Only two reporting territories exist in this fixture. There is no entry
 * for the other 31 departments — that absence is the point (see
 * `UNCOVERED_DEPARTMENTS_COUNT`): they are not-collected, not zero.
 */

export type TerritoryKey = "bog" | "med";

export type Mesa = {
  id: string;
  t: TerritoryKey;
  /** Votes for "Horizonte". */
  h: number;
  /** Votes for "Río". */
  r: number;
  /** Votes inside `h` in dispute between layers, if any. */
  disp?: number;
};

export const MESAS: Mesa[] = [
  { id: "001", t: "bog", h: 105, r: 85 },
  { id: "002", t: "bog", h: 100, r: 92 },
  { id: "003", t: "bog", h: 108, r: 82, disp: 6 },
  { id: "004", t: "med", h: 97, r: 95 },
  { id: "005", t: "med", h: 96, r: 97 },
  { id: "006", t: "med", h: 96, r: 97 },
];

export type Territory = {
  key: TerritoryKey;
  /** Matches the ISO-3166-2 codes already used by the department crosswalk
   * in `lib/department-map.ts` (`REVIEWED_DEPARTMENT_CROSSWALK`). */
  isoCode: "CO-DC" | "CO-ANT";
  lon: number;
  lat: number;
};

export const TERRITORIES: Territory[] = [
  { key: "bog", isoCode: "CO-DC", lon: -74.0721, lat: 4.711 },
  { key: "med", isoCode: "CO-ANT", lon: -75.5636, lat: 6.2518 },
];

export const UNCOVERED_DEPARTMENTS_COUNT = 31;

export type TerritoryTotals = {
  mesas: number;
  horizonte: number;
  rio: number;
  total: number;
};

export function territoryTotals(key: TerritoryKey): TerritoryTotals {
  const rows = MESAS.filter((m) => m.t === key);
  const horizonte = rows.reduce((sum, m) => sum + m.h, 0);
  const rio = rows.reduce((sum, m) => sum + m.r, 0);
  return { mesas: rows.length, horizonte, rio, total: horizonte + rio };
}
