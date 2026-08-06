/**
 * #comparación's four forensic tests, ported from the design's `dc-data.js`
 * `CMP` array exactly — same four metrics, same 2018/2022/2026 values, same
 * critical threshold, same padding and positioning math (`renderVals()`'s
 * `cmpRows` mapping). Kept separate from the prose (which lives in the
 * message bundle, keyed by `key` below) because these are the fixture's
 * numbers, not language-dependent copy: they must render identically in
 * Spanish and English, the same way `lib/dc-fixture.ts` and `lib/hexes.ts`
 * do for the rest of the page.
 *
 * One locale-aware adaptation from the source: `dc-data.js`'s `cf()` builds
 * its numeral strings by hand (`.replace(".", ",")`, a manual thousands
 * regex) because the design only ever spoke Spanish. This app is bilingual,
 * so `cf` below defers to `Intl.NumberFormat` per locale instead — same
 * decimal places, same grouping, same sign rule (a leading "−" for negative
 * values, a leading "+" only for positive values in a signed/thousands
 * metric), just with the right separators for `en-US` too.
 */

export type Locale = "es" | "en";

export type CmpMetricKey =
  | "digitUniformity"
  | "unanimousMesas"
  | "exteriorMargin"
  | "exteriorWeight";

type CmpMetric = {
  key: CmpMetricKey;
  /** [2018, 2022, 2026]. */
  v: [number, number, number];
  crit: number | null;
  dec: number;
  thousands?: boolean;
  suffix?: string;
  /** Whether zero is a meaningful reference point on this band (drawn as a
   * vertical rule) — true for the two exterior-vote metrics, where the sign
   * of the value is the entire point. */
  zero?: boolean;
};

/**
 * EMPTY BY DECISION — this array previously carried four bands copied verbatim
 * from the design mock `dc-data.js`. None of them was computed by any code in
 * this repository, and one of them was formally retracted:
 *
 *  - `digitUniformity` (χ² 14.5 / 38.9 / 33.7, crit 16.9) and `unanimousMesas`
 *    (0.21 / 0.38 / 0.54 %) had no derivation, no provenance hash and no
 *    reproduction path anywhere in the repo. They were design placeholders.
 *  - `exteriorMargin` / `exteriorWeight` (the "70.9% of the national margin
 *    came from abroad" pair) were RETRACTED in `docs/research/method-record.md`
 *    §16: measured across all 34 departments the exterior ranks 10th of 34, and
 *    department 01 alone accounts for 419.5% of the margin. The figure was
 *    selection on the outcome and does not survive.
 *
 * The layout math below (`computeCmpRow`, `cf`, the marker colours) is kept
 * because it is sound and locale-correct; it is waiting for values that are
 * actually computed from the real 122,020-mesa release, with provenance.
 * Until then this section publishes its principle and no numbers.
 */
export const CMP: CmpMetric[] = [];

/** Colours for the critical-threshold marker and the zero rule — fixture
 * constants from the design, not language-dependent, so they live beside the
 * numbers rather than in the message bundle. */
export const CMP_CRIT_FG = "#8A4B1E";
export const CMP_CRIT_BG = "rgba(138,75,30,.75)";
export const CMP_ZERO_BG = "rgba(33,30,30,.55)";

/**
 * The Benford statistic is deliberately NOT published. The previous value
 * ("2018 · 3.995   2022 · 4.415   2026 · 4.644") came from the design mock and
 * is computed nowhere in this repository. Printing a statistic for a test the
 * page itself argues is invalid — Benford does not hold for vote counts with
 * heterogeneous precinct sizes (`method-record.md`) — invites exactly the
 * misreading the section exists to prevent. The explanation stays; the number
 * goes.
 */
export function benfordFootnote(_locale: Locale): string {
  return "";
}

function cf(
  n: number,
  dec: number,
  thousands: boolean,
  suffix: string | undefined,
  locale: Locale,
): string {
  const abs = Math.abs(n);
  const nf = new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
    useGrouping: thousands,
  });
  const sign = n < 0 ? "−" : thousands && n > 0 ? "+" : "";
  return sign + nf.format(abs) + (suffix ?? "");
}

export type CmpRowLayout = {
  key: CmpMetricKey;
  bandL: string;
  bandW: string;
  /** Absolute-position percentage of the zero rule, or `null` when this
   * metric has none. */
  zeroL: string | null;
  /** Absolute-position percentage of the critical-threshold marker, or
   * `null` when this metric has none. */
  critL: string | null;
  marks: { year: 2018 | 2022 | 2026; x: string }[];
  /** "2018 14,5    2022 38,9    2026 33,7" — space-joined per-year readout,
   * four spaces between years exactly as the source's `.join("    ")`. */
  values: string;
  /** Whether the 2026 value falls inside the [2018, 2022] range — the same
   * test the design's own verdict copy switches on. */
  inside: boolean;
};

/** Ported from `renderVals()`'s `cmpRows` map, one metric at a time. */
export function computeCmpRow(metric: CmpMetric, locale: Locale): CmpRowLayout {
  const pts = metric.crit != null ? [...metric.v, metric.crit] : [...metric.v];
  if (metric.zero) pts.push(0);
  let lo = Math.min(...pts);
  let hi = Math.max(...pts);
  const pad = (hi - lo) * 0.14 || 1;
  lo -= pad;
  hi += pad;
  const pos = (x: number) => `${(((x - lo) / (hi - lo)) * 100).toFixed(2)}%`;

  const bLo = Math.min(metric.v[0], metric.v[1]);
  const bHi = Math.max(metric.v[0], metric.v[1]);
  const inside = metric.v[2] >= bLo && metric.v[2] <= bHi;
  const years = [2018, 2022, 2026] as const;

  return {
    key: metric.key,
    bandL: pos(bLo),
    bandW: `${(((bHi - bLo) / (hi - lo)) * 100).toFixed(2)}%`,
    zeroL: metric.zero ? pos(0) : null,
    critL: metric.crit != null ? pos(metric.crit) : null,
    marks: years.map((year, i) => ({ year, x: pos(metric.v[i]!) })),
    values: years
      .map((year, i) => `${year} ${cf(metric.v[i]!, metric.dec, !!metric.thousands, metric.suffix, locale)}`)
      .join("    "),
    inside,
  };
}
