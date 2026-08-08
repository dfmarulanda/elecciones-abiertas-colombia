import React from "react";
import { Gutter } from "@/components/page-primitives";
import { CoverageMap } from "@/components/coverage-map";
import { StateMark } from "@/components/state-marks";
import {
  TERRITORIES,
  UNCOVERED_DEPARTMENTS_COUNT,
  territoryTotals,
} from "@/lib/dc-fixture";
import { AppButton } from "@/components/app-button";
import { BitacoraTrack } from "@/components/bitacora-track";
import { buildBallots } from "@/lib/hexes";
import { CMP, computeCmpRow } from "@/lib/cmp-fixture";
import {
  ComparisonBands,
  type CmpRowContent,
} from "@/components/comparison-bands";

type Locale = "es" | "en";
type Text = (key: string, values?: Record<string, string | number>) => string;

/**
 * The design's own literal colour tokens (`dc-data.js`'s `PAPER`/`NEON` and
 * the paper/dark-field ink ramp used throughout `template-body.html`'s inline
 * `style="..."` attributes), not the app's `ec-*`/`--on-dark*` CSS custom
 * properties. #mesa, #territorios and #proceso below transcribe the source's
 * literal hex/rgba values, matching the precedent `ConteoHero` already set.
 */
const PAPER = "#F4F1EA";
const NEON = "#C4FF00";
const RIO = "#8C8E00";
const DARK_BG = "#151312";
const DARK_FG = "#F4F1EA";
const ON_DARK_2 = "#CFC8BC";
const ON_DARK_3 = "#928979";
const INK = "#211E1E";
const INK_2 = "#3E3831";
const INK_3 = "#5A5148";
const INK_4 = "#6B6259";
const RULE_FAINT_LIGHT = "rgba(33,30,30,.16)";

/**
 * The Rediseño v2 narrative sections, in the order the design fixes them:
 * comparación → mesa → territorios → proceso → bitácora → datos.
 *
 * All static content. None reads a release, so none degrades. Every string
 * comes from the message bundle so both legs of the wording gate are checked.
 * Nothing here publishes a forensic-screen figure: the comparison section
 * carries the METHOD and the principle, never a chi-square number, per the
 * site's own methodology.
 */

/* ── #comparación ─────────────────────────────────────────────────────────
   Ported VERBATIM from the source's `sections/comparacion.html` and
   `dc-data.js`'s `CMP`/`cmpRows`/`cmpLegend`/`toggleSimple`: the thermometer
   card, the three-line legend, the simple/técnico `AppButton` toggle, the
   four measured bands (χ² last-digit uniformity, unanimous mesas, exterior
   margin, exterior weight — each with its 2018/2022/2026 marks, its band of
   what was already seen, and, where one exists, its critical-value marker),
   and the static Benford aside that deliberately gets no band. Every
   `style="..."` value below is copied from that file, not approximated into
   the app's `ec-*` tokens — matching the precedent `ConteoHero` and `#mesa`/
   `#proceso` already set.
   The interactive half (the toggle and the four rows) lives in
   `ComparisonBands`, a Client Component: `dc-data.js` keeps `simple` in
   `this.state` and flips every row's prose with one `AppButton` click, so
   this needs real React state, not a description of a toggle. The numbers
   themselves (band position, marker position, the per-year values line) are
   locale-resolved once here via `lib/cmp-fixture.ts` and passed down as
   plain data — they are the fixture, not language-dependent copy, so they
   render identically in both locales the same way `lib/dc-fixture.ts` and
   `lib/hexes.ts` already do for the rest of the page. */
const CMP_METRIC_ORDER = ["digitUniformity", "unanimousMesas"] as const;

export function ComparisonSection({ locale, t }: { locale: Locale; t: Text }) {
  const legendItems = ["1", "2", "3"] as const;
  const rows: CmpRowContent[] = CMP.map((metric) => {
    const layout = computeCmpRow(metric, locale);
    const base = `comparison.metrics.${metric.key}`;
    return {
      key: metric.key,
      layout,
      plainLabel: t(`${base}.plainLabel`),
      techLabel: t(`${base}.techLabel`),
      plainUnit: t(`${base}.plainUnit`),
      techUnit: t(`${base}.techUnit`),
      human: t(`${base}.human`),
      plainReading: t(`${base}.plainReading`),
      techReading: t(`${base}.techReading`),
      plainCritLabel:
        metric.crit != null ? t(`${base}.plainCritLabel`) : undefined,
      techCritLabel:
        metric.crit != null ? t(`${base}.techCritLabel`) : undefined,
    };
  }).sort(
    (a, b) => CMP_METRIC_ORDER.indexOf(a.key) - CMP_METRIC_ORDER.indexOf(b.key),
  );

  return (
    <section
      id="comparacion"
      aria-label={t("comparison.eyebrow")}
      data-screen-label={t("comparison.eyebrow")}
      lang={locale}
      className="eac-section scroll-mt-24"
      style={{ maxWidth: 1440, margin: "0 auto", padding: "80px 46px 0" }}
    >
      <div style={{ paddingTop: 34, borderTop: `1px solid ${INK}` }}>
        <div
          className="eac-section-header"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) minmax(0,1.25fr)",
            gap: 64,
            alignItems: "baseline",
          }}
        >
          <div>
            <p className="mark" style={{ margin: 0, color: INK_4 }}>
              {t("comparison.eyebrow")}
            </p>
            <h2 className="head" style={{ margin: "16px 0 0" }}>
              {t("comparison.titleLine1")}
              <br />
              {t("comparison.titleLine2")}
            </h2>
          </div>
          <p
            style={{
              margin: 0,
              maxWidth: "42rem",
              fontSize: 17,
              lineHeight: 1.62,
              color: INK_2,
            }}
          >
            {t("comparison.introA")}
          </p>
        </div>

        <ComparisonBands
          thermometerLead={t("comparison.thermometer.lead")}
          thermometerBody={t("comparison.thermometer.body")}
          legendItems={legendItems.map((k) => t(`comparison.legend.${k}`))}
          toggleToTechnicalLabel={t("comparison.toggleToTechnical")}
          toggleToSimpleLabel={t("comparison.toggleToSimple")}
          rows={rows}
          insideVerdict={t("comparison.insideVerdict")}
          outsideVerdict={t("comparison.outsideVerdict")}
          benfordLabel={t("comparison.benford.label")}
          benfordBox={t("comparison.benford.box")}
          benfordBody={t("comparison.benford.body")}
          benfordFootnote={t("comparison.footnote")}
        />
      </div>
    </section>
  );
}

/* ── #mesa (dark) ─────────────────────────────────────────────────────────
   One real polling table from the pre-count, drawn vote by vote. The design's
   original illustrative "mesa 003" (with an invented E-14 dispute, a fake host
   and hash) is gone — this shows only what the pre-count actually reports for
   a single real mesa. */
type SampleMesa = {
  mesa_id: string;
  department: string | null;
  valid_votes: number;
  blank_votes: number;
  candidates: Record<string, number>;
};

/**
 * #mesa on the real preconteo: one actual polling table, drawn vote by vote
 * from its published pre-count tally. No invented E-14 dispute — the design's
 * original "mesa 003" was illustrative; this is a real mesa and shows only
 * what the pre-count actually reports for it.
 */
export function MesaSection({
  locale,
  t,
  mesa,
  candidates,
}: {
  locale: Locale;
  t: Text;
  mesa?: SampleMesa | null;
  candidates?: { id: string; name: { es: string; en: string } }[];
}) {
  if (!mesa || !candidates || candidates.length < 2) return null;
  const nf = new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US");
  const [a, b] = candidates;
  const av = mesa.candidates[a?.id ?? ""] ?? 0;
  const bv = mesa.candidates[b?.id ?? ""] ?? 0;
  // valid_votes includes blanks, so drawing only the two candidates would show
  // fewer hexagons than the caption's "N votos válidos" claims.
  const blank = Math.max(0, mesa.valid_votes - av - bv);
  const fig = buildBallots(av, bv, blank, 17, 14);
  const stat = (name: string, votes: number, color: string) => (
    <div style={{ background: DARK_BG, padding: "20px 20px 22px" }}>
      <p className="mono" style={{ margin: 0, fontSize: 12, color: ON_DARK_3 }}>
        {name}
      </p>
      <p
        className="fig"
        style={{ margin: "14px 0 0", fontSize: 52, lineHeight: 0.86, color }}
      >
        {nf.format(votes)}
      </p>
    </div>
  );
  return (
    <section
      id="mesa"
      data-theme="dark"
      data-screen-label={t("mesa.eyebrow")}
      aria-label={t("mesa.eyebrow")}
      lang={locale}
      className="scroll-mt-24"
      style={{
        background: DARK_BG,
        color: DARK_FG,
        marginTop: 80,
        padding: "60px 0 58px",
      }}
    >
      <div
        className="eac-gutter"
        style={{ maxWidth: 1440, margin: "0 auto", padding: "0 46px" }}
      >
        <div
          className="eac-section-header"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) minmax(0,1.25fr)",
            gap: 64,
            alignItems: "baseline",
          }}
        >
          <div>
            <p className="mark" style={{ margin: 0, color: ON_DARK_3 }}>
              {t("mesa.eyebrow")}
            </p>
            <h2 className="head" style={{ margin: "16px 0 0", color: DARK_FG }}>
              {t("mesa.realTitle")}
            </h2>
          </div>
          <p
            style={{
              margin: 0,
              maxWidth: "42rem",
              fontSize: 17,
              lineHeight: 1.62,
              color: ON_DARK_2,
            }}
          >
            {t("mesa.realIntro", {
              mesa: mesa.mesa_id,
              department: mesa.department ?? "",
            })}
          </p>
        </div>

        <div
          className="eac-two-column"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) minmax(0,1.15fr)",
            gap: 72,
            alignItems: "start",
            marginTop: 40,
          }}
        >
          <div>
            <svg
              viewBox={fig.vb}
              role="img"
              aria-label={t("mesa.realFigureAlt", {
                a: a?.name[locale] ?? "",
                av,
                b: b?.name[locale] ?? "",
                bv,
              })}
              style={{ display: "block", width: "100%", height: "auto" }}
            >
              <path d={fig.dA} fill={PAPER} />
              <path d={fig.dB} fill={RIO} />
              <path
                d={fig.dBlank}
                fill="none"
                stroke="rgba(196,255,0,.55)"
                strokeWidth={1.2}
              />
            </svg>
            <p
              className="mono"
              style={{ margin: "16px 0 0", fontSize: 12, color: ON_DARK_3 }}
            >
              {t("mesa.realFigureCaption", {
                total: nf.format(mesa.valid_votes),
                mesa: mesa.mesa_id,
              })}
            </p>
          </div>
          <div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(2,minmax(0,1fr))",
                gap: 1,
                background: "rgba(244,241,234,.24)",
                borderTop: "1px solid rgba(244,241,234,.4)",
                borderBottom: "1px solid rgba(244,241,234,.4)",
              }}
            >
              {stat(a?.name[locale] ?? "", av, PAPER)}
              {stat(b?.name[locale] ?? "", bv, "#B5B72E")}
            </div>
            <p
              style={{
                margin: "24px 0 0",
                maxWidth: "38rem",
                fontSize: 16,
                lineHeight: 1.62,
                color: ON_DARK_2,
              }}
            >
              {t("mesa.realFootnote")}
            </p>
            <div style={{ display: "flex", gap: 12, marginTop: 24 }}>
              <AppButton variant="outline" href="#datos">
                {t("mesa.downloadData")}
              </AppButton>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── #territorios ─────────────────────────────────────────────────────────
   Where collection happened: the design's D3 + topojson Colombia choropleth
   (see CoverageMap) with the two reporting territories, plus an always-
   rendered accessible table carrying the same numbers — the map's real
   no-JS/screen-reader equivalent, not a decorative aside. The 31 uncovered
   departments render as the site's NOT-COLLECTED mark — hollow and dashed —
   never as zero. This is the unknown-vs-zero showcase. */
type DeptRow = {
  id: string;
  name: string;
  valid_votes: number;
  candidates: Record<string, number>;
  mesas_reported: number;
};

export function TerritoriesSection({
  locale,
  t,
  departments,
  candidates,
}: {
  locale: Locale;
  t: Text;
  departments?: DeptRow[];
  candidates?: { id: string; name: { es: string; en: string } }[];
}) {
  const nf = new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US");

  // Real preconteo: render every department with observed results. Falls back
  // to the illustrative territories only when no release loaded.
  if (
    departments &&
    departments.length &&
    candidates &&
    candidates.length >= 2
  ) {
    return (
      <RealTerritories
        locale={locale}
        t={t}
        departments={departments}
        candidates={candidates}
        nf={nf}
      />
    );
  }
  // CoverageMap is a Client Component: `t` is a server-only function and
  // cannot cross that boundary as a prop, so every string it needs is
  // resolved here, once, into plain data.
  const mapLabels = {
    mapTitle: t("territories.map.title"),
    legendReporting: t("territories.map.legendReporting"),
    legendNotCollected: t("territories.map.legendNotCollected"),
    legendDepartments: t("territories.map.legendDepartments"),
    note: t("territories.map.note"),
    error: t("territories.map.error"),
    tooltipOf: t("territories.map.tooltipOf"),
    tooltipPrecount: t("territories.map.tooltipPrecount"),
    noscript: t("territories.map.noscript"),
    mesasUnit: t("territories.unit.mesas"),
    votesUnit: t("territories.unit.votes"),
    territoryNames: {
      bog: t("territories.covered.bog.name"),
      med: t("territories.covered.med.name"),
    },
  };
  return (
    <section
      id="territorios"
      aria-label={t("territories.eyebrow")}
      lang={locale}
      className="eac-section scroll-mt-24"
      style={{ maxWidth: 1440, margin: "0 auto", padding: "80px 46px 0" }}
    >
      <div
        className="eac-territories-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) 400px",
          gap: 64,
          alignItems: "start",
        }}
      >
        <div
          className="eac-map-frame"
          style={{ height: 470, border: `1px solid ${INK}` }}
        >
          <CoverageMap locale={locale} labels={mapLabels} />
        </div>
        <div>
          <p className="mark" style={{ margin: 0, color: INK_4 }}>
            {t("territories.eyebrow")}
          </p>
          <h2 className="head" style={{ margin: "14px 0 0", fontSize: 34 }}>
            {t("territories.title")}
          </h2>
          <p
            style={{
              margin: "16px 0 0",
              fontSize: 16,
              lineHeight: 1.6,
              color: INK_2,
            }}
          >
            {t("territories.intro")}
          </p>
          {/* The source renders this as an `<ol>` of bar rows (`t.wH`/`t.wR`
              proportion bars). Kept as an accessible `<table>` instead — a
              documented deviation from the literal markup, not from the
              design's numbers or its unknown-vs-zero distinction — because a
              real `<table>` with `scope`d headers is the stronger screen
              reader/no-JS equivalent to the map that #territorios itself asks
              for, and every column's value is still exactly what
              `territoryRows`/`terr` computes in the source. */}
          <div
            role="region"
            aria-label={t("territories.table.caption")}
            tabIndex={0}
            className="eac-table-scroll"
            style={{
              marginTop: 26,
              overflowX: "auto",
              borderTop: `1px solid ${INK}`,
            }}
          >
            <table
              style={{
                width: "100%",
                minWidth: "22rem",
                borderCollapse: "collapse",
                textAlign: "left",
              }}
            >
              <caption className="sr-only">
                {t("territories.table.caption")}
              </caption>
              <thead>
                <tr style={{ borderBottom: `1px solid ${INK}` }}>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                    }}
                  >
                    {t("territories.table.territory")}
                  </th>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                      textAlign: "right",
                    }}
                  >
                    {t("territories.table.mesas")}
                  </th>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                      textAlign: "right",
                    }}
                  >
                    {t("territories.table.horizonte")}
                  </th>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                      textAlign: "right",
                    }}
                  >
                    {t("territories.table.rio")}
                  </th>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                      textAlign: "right",
                    }}
                  >
                    {t("territories.table.total")}
                  </th>
                  <th
                    scope="col"
                    className="mono"
                    style={{
                      padding: "12px 0",
                      fontSize: 11,
                      fontWeight: 700,
                      color: INK_4,
                    }}
                  >
                    {t("territories.table.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {TERRITORIES.map((territory) => {
                  const totals = territoryTotals(territory.key);
                  return (
                    <tr
                      key={territory.key}
                      style={{ borderBottom: RULE_FAINT_LIGHT }}
                    >
                      <th
                        scope="row"
                        style={{ padding: "12px 12px 12px 0", fontWeight: 400 }}
                      >
                        <p
                          className="mark"
                          style={{ margin: 0, fontSize: 12, color: INK_4 }}
                        >
                          {t(`territories.covered.${territory.key}.name`)}
                        </p>
                        <p
                          className="mono"
                          style={{
                            margin: "4px 0 0",
                            fontSize: 11,
                            color: INK_3,
                          }}
                        >
                          {t(`territories.covered.${territory.key}.place`)}
                        </p>
                      </th>
                      <td
                        className="mono"
                        style={{
                          padding: "12px 12px 12px 0",
                          textAlign: "right",
                        }}
                      >
                        {totals.mesas}
                      </td>
                      <td
                        className="mono"
                        style={{
                          padding: "12px 12px 12px 0",
                          textAlign: "right",
                        }}
                      >
                        {nf.format(totals.horizonte)}
                      </td>
                      <td
                        className="mono"
                        style={{
                          padding: "12px 12px 12px 0",
                          textAlign: "right",
                        }}
                      >
                        {nf.format(totals.rio)}
                      </td>
                      <td
                        className="fig"
                        style={{
                          padding: "12px 12px 12px 0",
                          textAlign: "right",
                          fontSize: 16,
                        }}
                      >
                        {nf.format(totals.total)}
                      </td>
                      <td style={{ padding: "12px 0" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <StateMark state="observed" />
                          <span
                            className="mono"
                            style={{ fontSize: 11, color: INK_3 }}
                          >
                            {t("territories.table.statusReporting")}
                          </span>
                        </span>
                      </td>
                    </tr>
                  );
                })}
                <tr>
                  <th
                    scope="row"
                    style={{ padding: "12px 12px 12px 0", fontWeight: 400 }}
                  >
                    <p
                      className="mark"
                      style={{ margin: 0, fontSize: 12, color: INK_4 }}
                    >
                      {t("territories.uncovered.name")}
                    </p>
                  </th>
                  <td
                    colSpan={4}
                    className="mono"
                    style={{
                      padding: "12px 12px 12px 0",
                      fontSize: 11,
                      color: INK_3,
                    }}
                  >
                    {t("territories.uncovered.meta")}
                  </td>
                  <td style={{ padding: "12px 0" }}>
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <StateMark state="unavailable" />
                      <span className="sr-only">
                        {t("territories.uncovered.stateLabel")}
                      </span>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p
            style={{
              margin: "9px 0 0",
              maxWidth: "28rem",
              fontSize: 14,
              lineHeight: 1.5,
              color: INK_2,
            }}
          >
            {t("territories.uncovered.note")}
          </p>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 14,
              marginTop: 22,
            }}
          >
            <p
              className="fig"
              style={{ margin: 0, fontSize: 38, color: INK_4 }}
            >
              {UNCOVERED_DEPARTMENTS_COUNT}
            </p>
            <p
              style={{
                margin: 0,
                maxWidth: "22rem",
                fontSize: 14,
                lineHeight: 1.5,
                color: INK_3,
              }}
            >
              {t("territories.uncoveredStat")}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * #territorios on the real preconteo: every one of the 34 departments with its
 * observed vote split and mesa count. The pre-count is nationally complete, so
 * there is no "not collected" story — the map shows full national coverage.
 */
function RealTerritories({
  locale,
  t,
  departments,
  candidates,
  nf,
}: {
  locale: Locale;
  t: Text;
  departments: DeptRow[];
  candidates: { id: string; name: { es: string; en: string } }[];
  nf: Intl.NumberFormat;
}) {
  const [a, b] = candidates;
  const totalMesas = departments.reduce((s, d) => s + d.mesas_reported, 0);
  const mapLabels = {
    mapTitle: t("territories.map.title"),
    legendReporting: t("territories.map.legendReporting"),
    legendNotCollected: t("territories.map.legendNotCollected"),
    legendDepartments: t("territories.map.legendDepartments"),
    note: t("territories.map.note"),
    error: t("territories.map.error"),
    tooltipOf: t("territories.map.tooltipOf"),
    tooltipPrecount: t("territories.map.tooltipPrecount"),
    noscript: t("territories.map.noscript"),
    mesasUnit: t("territories.unit.mesas"),
    votesUnit: t("territories.unit.votes"),
    territoryNames: { bog: "", med: "" },
  };
  return (
    <section
      id="territorios"
      aria-label={t("territories.eyebrow")}
      lang={locale}
      className="eac-section scroll-mt-24"
      style={{ maxWidth: 1440, margin: "0 auto", padding: "80px 46px 0" }}
    >
      <div
        className="eac-territories-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) 400px",
          gap: 64,
          alignItems: "start",
        }}
      >
        <div
          className="eac-map-frame"
          style={{ height: 470, border: `1px solid ${INK}` }}
        >
          <CoverageMap locale={locale} labels={mapLabels} fullCoverage />
        </div>
        <div>
          <p className="mark" style={{ margin: 0, color: INK_4 }}>
            {t("territories.eyebrow")}
          </p>
          <h2 className="head" style={{ margin: "14px 0 0", fontSize: 34 }}>
            {t("territories.realTitle")}
          </h2>
          <p
            style={{
              margin: "16px 0 0",
              fontSize: 16,
              lineHeight: 1.6,
              color: INK_2,
            }}
          >
            {t("territories.realIntro", {
              departments: departments.length,
              mesas: nf.format(totalMesas),
            })}
          </p>
          <div
            role="region"
            aria-label={t("territories.table.caption")}
            tabIndex={0}
            className="eac-table-scroll"
            style={{
              marginTop: 26,
              overflowX: "auto",
              borderTop: `1px solid ${INK}`,
            }}
          >
            <table
              style={{
                width: "100%",
                minWidth: "24rem",
                borderCollapse: "collapse",
                textAlign: "left",
              }}
            >
              <caption className="sr-only">
                {t("territories.table.caption")}
              </caption>
              <thead>
                <tr style={{ borderBottom: `1px solid ${INK}` }}>
                  {[
                    t("territories.table.territory"),
                    t("territories.table.mesas"),
                    a?.name[locale] ?? "",
                    b?.name[locale] ?? "",
                    t("territories.table.total"),
                  ].map((h, i) => (
                    <th
                      key={i}
                      scope="col"
                      className="mono"
                      style={{
                        padding: "12px 12px 12px 0",
                        fontSize: 11,
                        fontWeight: 700,
                        color: INK_4,
                        textAlign: i === 0 ? "left" : "right",
                        whiteSpace: i > 1 ? "normal" : "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {departments.map((d) => {
                  const av = d.candidates[a?.id ?? ""] ?? 0;
                  const bv = d.candidates[b?.id ?? ""] ?? 0;
                  return (
                    <tr key={d.id} style={{ borderBottom: RULE_FAINT_LIGHT }}>
                      <th
                        scope="row"
                        style={{ padding: "10px 12px 10px 0", fontWeight: 400 }}
                      >
                        <span
                          className="mark"
                          style={{ fontSize: 12, color: INK_4 }}
                        >
                          {d.name}
                        </span>
                      </th>
                      <td
                        className="mono"
                        style={{
                          padding: "10px 12px 10px 0",
                          textAlign: "right",
                        }}
                      >
                        {nf.format(d.mesas_reported)}
                      </td>
                      <td
                        className="mono"
                        style={{
                          padding: "10px 12px 10px 0",
                          textAlign: "right",
                        }}
                      >
                        {nf.format(av)}
                      </td>
                      <td
                        className="mono"
                        style={{
                          padding: "10px 12px 10px 0",
                          textAlign: "right",
                        }}
                      >
                        {nf.format(bv)}
                      </td>
                      <td
                        className="fig"
                        style={{
                          padding: "10px 0",
                          textAlign: "right",
                          fontSize: 15,
                        }}
                      >
                        {nf.format(d.valid_votes)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 14,
              marginTop: 22,
            }}
          >
            <p
              className="fig"
              style={{ margin: 0, fontSize: 38, color: INK_4 }}
            >
              {departments.length}
            </p>
            <p
              style={{
                margin: 0,
                maxWidth: "22rem",
                fontSize: 14,
                lineHeight: 1.5,
                color: INK_3,
              }}
            >
              {t("territories.realCoverageStat")}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── #proceso (dark) ──────────────────────────────────────────────────────
   Ported verbatim from the source's `sections/proceso.html`: nine rows, each
   a 4-column grid (a hex-node timeline rail, the step number + title, the
   body copy, and an "art" column carrying either the gate's stop condition
   in neon or the non-gate step's artifact, labelled "Puerta de publicación" /
   "Deja registrado" — exactly `dc-data.js`'s `steps` mapping over `STEPS`).
   Steps 04, 06 and 08 are the design's three publication gates. */
const STEPS = [
  { n: "01" },
  { n: "02" },
  { n: "03" },
  { n: "04", gate: true },
  { n: "05" },
  { n: "06", gate: true },
  { n: "07" },
  { n: "08", gate: true },
  { n: "09" },
] as const;

export function ProcessSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section
      id="proceso"
      data-theme="dark"
      data-screen-label="Proceso"
      aria-label={t("process.eyebrow")}
      lang={locale}
      className="scroll-mt-24"
      style={{
        background: DARK_BG,
        color: DARK_FG,
        marginTop: 80,
        padding: "60px 0 58px",
      }}
    >
      <div
        className="eac-gutter"
        style={{ maxWidth: 1440, margin: "0 auto", padding: "0 46px" }}
      >
        <div
          className="eac-section-header"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0,1fr) minmax(0,1.25fr)",
            gap: 64,
            alignItems: "baseline",
          }}
        >
          <div>
            <p className="mark" style={{ margin: 0, color: ON_DARK_3 }}>
              {t("process.eyebrow")}
            </p>
            <h2 className="head" style={{ margin: "16px 0 0", color: DARK_FG }}>
              {t("process.title")}
            </h2>
          </div>
          <div>
            <p
              style={{
                margin: 0,
                maxWidth: "42rem",
                fontSize: 17,
                lineHeight: 1.62,
                color: ON_DARK_2,
              }}
            >
              {t("process.intro")}
            </p>
            <p
              className="mono"
              style={{ margin: "16px 0 0", fontSize: 12, color: NEON }}
            >
              {t("process.gateCount")}
            </p>
          </div>
        </div>

        <div
          style={{
            marginTop: 40,
            borderTop: "1px solid rgba(244,241,234,.26)",
          }}
        >
          {STEPS.map((s, i) => {
            const gate = "gate" in s && s.gate;
            const nodeBg = gate ? NEON : PAPER;
            const artFg = gate ? NEON : ON_DARK_3;
            const artLabel = gate
              ? t("process.gateLabel")
              : t("process.artLabel");
            const lineTop = i === 0 ? "22px" : "0";
            const lineH =
              i === 0
                ? "calc(100% - 22px)"
                : i === STEPS.length - 1
                  ? "22px"
                  : "100%";
            return (
              <div
                key={s.n}
                className="eac-process-step"
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "40px minmax(0,.85fr) minmax(0,1.75fr) minmax(0,1fr)",
                  gap: 26,
                  alignItems: "start",
                  padding: "22px 0 24px",
                  borderBottom: "1px solid rgba(244,241,234,.14)",
                }}
              >
                <div
                  style={{
                    position: "relative",
                    height: "100%",
                    minHeight: 40,
                  }}
                >
                  <div
                    aria-hidden="true"
                    style={{
                      position: "absolute",
                      left: 8,
                      top: lineTop,
                      height: lineH,
                      width: 1,
                      background: "rgba(244,241,234,.24)",
                    }}
                  />
                  <div
                    aria-hidden="true"
                    style={{
                      position: "relative",
                      width: 17,
                      height: 15,
                      marginTop: 5,
                      background: nodeBg,
                      clipPath:
                        "polygon(0 50%,25% 0,75% 0,100% 50%,75% 100%,25% 100%)",
                    }}
                  />
                </div>
                <div>
                  <p
                    className="mono"
                    style={{ margin: 0, fontSize: 12, color: ON_DARK_3 }}
                  >
                    {s.n}
                  </p>
                  <p
                    style={{
                      margin: "7px 0 0",
                      fontSize: 19,
                      fontWeight: 600,
                      letterSpacing: "-.012em",
                      lineHeight: 1.25,
                      color: DARK_FG,
                    }}
                  >
                    {t(`process.step.${s.n}.title`)}
                  </p>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: 15,
                    lineHeight: 1.6,
                    color: ON_DARK_2,
                  }}
                >
                  {t(`process.step.${s.n}.body`)}
                </p>
                <div>
                  <p
                    className="mono"
                    style={{ margin: 0, fontSize: 11, color: artFg }}
                  >
                    {artLabel}
                  </p>
                  <p
                    className="mono"
                    style={{
                      margin: "7px 0 0",
                      fontSize: 12,
                      lineHeight: 1.5,
                      color: ON_DARK_2,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {t(`process.step.${s.n}.art`)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <p
          style={{
            margin: "26px 0 0",
            maxWidth: "46rem",
            fontSize: 15,
            lineHeight: 1.6,
            color: ON_DARK_3,
          }}
        >
          {t("process.footnote")}
        </p>
      </div>
    </section>
  );
}

/* ── #bitácora ────────────────────────────────────────────────────────────
   The decisions log, in the order decisions were taken. Several were fixed
   before the 2026 data was seen — which is why they hold up afterward.
   Reproduced verbatim from the design's `bitacora` / `bitacora-track`: the
   two-column header, then the sticky scroll-driven stage where 12 phase stops
   sit on a sine wave and a neon polyline draws as it scrolls. The four phases
   and their three entries each come straight from dc-data.js's PHASES. */
const LOG_PHASES = [
  { n: "01", key: "p1", entries: ["e1", "e2", "e3"] },
  { n: "02", key: "p2", entries: ["e1", "e2", "e3"] },
  { n: "03", key: "p3", entries: ["e1", "e2", "e3"] },
  { n: "04", key: "p4", entries: ["e1", "e2", "e3"] },
] as const;

export function LogSection({ locale, t }: { locale: Locale; t: Text }) {
  const stops = LOG_PHASES.flatMap((phase) =>
    phase.entries.map((entry, entryIndex) => ({
      key: `${phase.key}-${entry}`,
      phase: t(`log.phase.${phase.key}.name`),
      phaseN: phase.n,
      when: t(`log.phase.${phase.key}.when`),
      title: t(`log.phase.${phase.key}.${entry}.title`),
      body: t(`log.phase.${phase.key}.${entry}.body`),
      first: entryIndex === 0,
    })),
  );
  return (
    <section
      id="bitacora"
      aria-label={t("log.eyebrow")}
      lang={locale}
      className="scroll-mt-24"
    >
      <Gutter className="pt-20">
        <div className="grid items-baseline gap-16 md:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <div>
            <p className="ec-mark m-0 text-[#6B6259]">{t("log.eyebrow")}</p>
            <h2 className="ec-head mt-4">
              {t("log.titleLine1")}
              <br />
              {t("log.titleLine2")}
            </h2>
          </div>
          <div>
            <p className="m-0 max-w-[42rem] text-[17px] leading-[1.62] text-ink-2">
              {t("log.intro")}
            </p>
            <p className="ec-mono mt-3.5 text-[12px] text-[#8A4B1E]">
              {t("log.note")}
            </p>
          </div>
        </div>
      </Gutter>
      <BitacoraTrack
        stops={stops}
        regionLabel={t("log.trackLabel")}
        hintLabel={t("log.trackHint")}
        milestoneWord={t("log.milestone")}
        ofWord={t("log.of")}
      />
    </section>
  );
}

/* ── #datos ───────────────────────────────────────────────────────────────
   Ported VERBATIM from the source's `sections/datos.html`: one baseline-
   aligned header row (eyebrow, intro sentence, `AppButton` — no big headline
   here, unlike every other section), the three-column dataset row (a
   hairline top rule, not a boxed card) and the three-column route list. The
   source goes straight from the dataset row to the route list with no
   heading between them; this keeps that, rather than inserting the app's own
   "Contrato de lectura" label the source doesn't have.
   Content note: the source's own dataset row is literal fixture filler
   (`"8 KB"`, `"sha256 por objeto"` for every format) appended with a fixed
   `"· 6 registros"`. This app instead describes what each format actually is
   (`data.file.*.size` reads e.g. "instantánea del preconteo", not a byte
   count) since claiming a specific file size for files this build does not
   serve would be its own kind of fabrication — a deliberate content
   departure the style transcription below does not re-introduce. */
const DATASETS = ["json", "parquet", "csv"] as const;
const ROUTES = [
  "/api/v1/release-elections",
  "/api/v1/releases/{release}/elections/{election}/results",
  "/api/v1/releases/{release}/datasets",
] as const;

export function DataSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section
      id="datos"
      aria-label={t("data.eyebrow")}
      lang={locale}
      className="scroll-mt-24"
    >
      <div
        className="eac-data-section eac-gutter"
        style={{ maxWidth: 1440, margin: "0 auto", padding: "72px 46px 88px" }}
      >
        <div
          className="eac-data-header"
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: 40,
            paddingTop: 30,
            borderTop: `1px solid ${INK}`,
            flexWrap: "wrap",
          }}
        >
          <h2 className="mark" style={{ margin: 0, color: INK_4 }}>
            {t("data.eyebrow")}
          </h2>
          <p
            style={{
              margin: 0,
              maxWidth: "44rem",
              fontSize: 16,
              lineHeight: 1.6,
              color: INK_2,
            }}
          >
            {t("data.intro")}
          </p>
          <AppButton variant="outline" size="sm" href={`/${locale}/api`}>
            {t("data.docsLabel")}
          </AppButton>
        </div>

        <div
          className="eac-three-up"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3,minmax(0,1fr))",
            gap: 56,
            marginTop: 30,
          }}
        >
          {DATASETS.map((d) => (
            <div
              key={d}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 14,
                paddingTop: 14,
                borderTop: `1px solid rgba(33,30,30,.2)`,
                flexWrap: "wrap",
              }}
            >
              <p
                className="mono"
                style={{
                  margin: 0,
                  fontSize: 13,
                  fontWeight: 700,
                  flex: "none",
                }}
              >
                {t(`data.file.${d}.format`)}
              </p>
              <p
                className="mono"
                style={{ margin: 0, fontSize: 12, color: INK_4, flex: "none" }}
              >
                {t(`data.file.${d}.size`)}
              </p>
              <p
                className="mono"
                style={{
                  margin: 0,
                  fontSize: 11,
                  color: INK_4,
                  overflowWrap: "anywhere",
                  minWidth: 0,
                }}
              >
                {t(`data.file.${d}.hash`)}
              </p>
            </div>
          ))}
        </div>

        <ul
          className="eac-three-up"
          style={{
            margin: "36px 0 0",
            padding: 0,
            listStyle: "none",
            display: "grid",
            gridTemplateColumns: "repeat(3,minmax(0,1fr))",
            gap: "0 56px",
          }}
        >
          {ROUTES.map((r) => (
            <li
              key={r}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 12,
                padding: "8px 0",
                borderBottom: "1px solid rgba(33,30,30,.12)",
              }}
            >
              <span
                className="mono"
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: INK_4,
                  flex: "none",
                }}
              >
                GET
              </span>
              <span
                className="mono"
                style={{ fontSize: 12, overflowWrap: "anywhere" }}
              >
                {r}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
