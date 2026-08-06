/**
 * #comparación's measured bands. The layout math (band placement, the critical
 * marker, the padding) is the design's `renderVals()` `cmpRows` mapping kept
 * verbatim; the VALUES are computed from each election's own mesa records, not
 * ported from the mock. They live here rather than in the message bundle
 * because they must render identically in Spanish and English.
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

export type CmpMetricKey = "digitUniformity" | "unanimousMesas";

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
 * Computed, not copied. Every value below comes from running one code path over
 * all three elections' own mesa records:
 *
 *   `scripts/compute-comparison-statistics.py`  → 2026, 122,020 mesas
 *   `scripts/compute-historical-comparison.py`  → 2018, 97,644 · 2022, 103,363
 *
 * emitting `data/derived/comparison-statistics-2026.json` and
 * `comparison-statistics-historical.json`, each carrying the sha256 of its
 * source artifact. The previous values here were design placeholders from
 * `dc-data.js` that no code computed, alongside an exterior-margin pair that
 * `docs/research/method-record.md` §16 formally retracted as selection on the
 * outcome — the exterior ranks 10th of 34 departments, and department 01 alone
 * accounts for 419.47% of the national margin. Those two bands are gone and are
 * not replaced: the honest exterior reading is a participation rate, not a share
 * of an unstable net margin.
 *
 * What the remaining two show is the section's actual argument. The last-digit
 * test exceeds its critical value in ALL THREE elections, and 2022 — an election
 * nobody disputes on these grounds — exceeds it by more than 2026 does.
 *
 * IMPORTANT comparability limit, which the copy must state: 2026 is the
 * preconteo while 2018 and 2022 are the MMV mesa annex. Different stages of the
 * count, not one instrument measured three times.
 */
export const CMP: CmpMetric[] = [
  {
    key: "digitUniformity",
    // 2018 / 2022 / 2026 — pooled across both candidates, counts >= 10.
    v: [30.17, 55.72, 35.52],
    crit: 16.92,
    dec: 2,
  },
  {
    key: "unanimousMesas",
    // Share of mesas where one candidate received exactly zero.
    v: [0.354, 0.504, 0.627],
    crit: null,
    dec: 3,
    suffix: " %",
  },
];

/** Colours for the critical-threshold marker and the zero rule — fixture
 * constants from the design, not language-dependent, so they live beside the
 * numbers rather than in the message bundle. */
export const CMP_CRIT_FG = "#8A4B1E";
export const CMP_CRIT_BG = "rgba(138,75,30,.75)";
export const CMP_ZERO_BG = "rgba(33,30,30,.55)";


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
