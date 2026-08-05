import React from "react";
import { FieldSection, Gutter, SectionHeader } from "@/components/page-primitives";
import { CoverageMap } from "@/components/coverage-map";
import { StateMark } from "@/components/state-marks";
import {
  TERRITORIES,
  UNCOVERED_DEPARTMENTS_COUNT,
  territoryTotals,
} from "@/lib/dc-fixture";
import { AppButton } from "@/components/app-button";
import { BitacoraTrack } from "@/components/bitacora-track";
import { build } from "@/lib/hexes";

type Locale = "es" | "en";
type Text = (key: string) => string;

/**
 * Mesa 003's real tally from the design's `MESAS` fixture: 108 votes for
 * Horizonte (six of them disputed against the E-14 acta) and 82 for Río —
 * 190 votes total. The hex figure below draws every one of them.
 */
const MESA_003 = { h: 108, r: 82, disp: 6 };
const MESA_003_HEXES = build(MESA_003, 17, 14);

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
   The moat: measure 2018, 2022 and 2026 with the same code and show them
   together. The point is the principle — a number alone means nothing — so
   the section teaches the thermometer analogy and the three-year framing.
   It deliberately stops short of the design's own forensic rows (the χ²,
   peer-unanimity and exterior-margin bands, and the Benford figures): this
   site's methodology keeps those concrete values in the methodology pages,
   with their code, not on this reading. The dark card is the design's own
   "2026 is scary alone" panel — the one place in this section that gets the
   full ec-field-dark treatment. */
export function ComparisonSection({ locale, t }: { locale: Locale; t: Text }) {
  const legendItems = ["1", "2", "3"] as const;
  return (
    <section id="comparacion" aria-label={t("comparison.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("comparison.eyebrow")}
          title={t("comparison.title")}
          intro={<p className="m-0">{t("comparison.introA")}</p>}
        />

        <div className="mt-[34px] grid items-start gap-x-16 gap-y-8 sm:grid-cols-2">
          <div className="ec-field-dark px-[34px] pb-8 pt-[30px]">
            <p className="m-0 text-[18px] leading-snug">{t("comparison.thermometer.lead")}</p>
            <p className="mt-3.5 text-[16px] leading-relaxed text-[color:var(--on-dark-2)]">
              {t("comparison.thermometer.body")}
            </p>
          </div>
          <div className="grid gap-[9px]">
            {legendItems.map((k) => (
              <p key={k} className="m-0 text-[15px] leading-relaxed text-ink-2">
                {t(`comparison.legend.${k}`)}
              </p>
            ))}
          </div>
        </div>

        <div className="mt-[34px] border-t border-rule">
          <div className="border-b border-rule-faint py-6">
            <p className="m-0 max-w-[44rem] text-[19px] font-semibold leading-tight tracking-[-0.012em] text-ink-4">
              {t("comparison.benford.label")}
            </p>
            <div
              aria-hidden="true"
              className="relative mt-4 h-11 border-y border-rule-faint"
              style={{
                backgroundImage:
                  "repeating-linear-gradient(135deg, transparent 0 7px, var(--rule-faint) 7px 8px)",
              }}
            >
              <p className="ec-mono absolute inset-0 m-0 grid place-content-center text-[12px] text-ink-3">
                {t("comparison.benford.box")}
              </p>
            </div>
            <p className="mt-3.5 max-w-[46rem] text-[15px] leading-relaxed text-ink-2">
              {t("comparison.benford.body")}
            </p>
            <p className="ec-mono mt-3 text-[12px] text-ink-4">
              {t("comparison.footnote")}
            </p>
          </div>
        </div>
      </Gutter>
    </section>
  );
}

/* ── #mesa (dark) ─────────────────────────────────────────────────────────
   The mesa 003 field: every one of its 190 votes drawn as a hexagon by the
   same generator as #reclamos, with the six disputed against the E-14 acta
   picked out in neon — the design's own "con los seis en disputa
   resaltados" figure, not a stat card standing in for it. */
const MESA_COMPARISON = ["precount", "e14", "difference"] as const;
const MESA_COMPARISON_TONE: Record<(typeof MESA_COMPARISON)[number], string> = {
  precount: "text-[color:var(--on-dark)]",
  e14: "text-[color:var(--on-dark)]",
  difference: "text-[color:var(--neon)]",
};

export function MesaSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <FieldSection id="mesa" label={t("mesa.eyebrow")} className="mt-20 scroll-mt-24">
      <div lang={locale}>
        <div className="grid items-start gap-x-16 gap-y-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <div>
            <p className="ec-mark m-0 text-[color:var(--on-dark-3)]">{t("mesa.eyebrow")}</p>
            <h2 className="ec-head mt-4">{t("mesa.title")}</h2>
          </div>
          <p className="max-w-[44rem] text-body leading-relaxed text-[color:var(--on-dark-2)]">
            {t("mesa.intro")}
          </p>
        </div>

        <div className="mt-10 grid items-start gap-x-[72px] gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <div>
            <svg
              viewBox={MESA_003_HEXES.vb}
              role="img"
              aria-label={t("mesa.figureAlt")}
              className="block h-auto w-full"
            >
              <path d={MESA_003_HEXES.dH} fill="var(--on-dark)" />
              <path d={MESA_003_HEXES.dR} fill="var(--rio)" />
              <path d={MESA_003_HEXES.dD} fill="var(--neon)" stroke="none" strokeWidth={2} />
              <path d={MESA_003_HEXES.dDot} fill="var(--neon)" opacity={0} />
            </svg>
            <p className="ec-mono mt-4 text-[12px] text-[color:var(--on-dark-3)]">
              {t("mesa.figureCaption")}
            </p>
          </div>
          <div>
            <div className="grid grid-cols-3 gap-px border-y border-[color:var(--on-dark-3)]/40 bg-[color:var(--on-dark-3)]/24">
              {MESA_COMPARISON.map((k) => (
                <div key={k} className="ec-field-dark px-5 py-5">
                  <p className="ec-mono m-0 text-[12px] text-[color:var(--on-dark-3)]">
                    {t(`mesa.comparison.${k}.label`)}
                  </p>
                  <p className={`ec-fig mt-3.5 text-[clamp(2rem,4vw,3.25rem)] leading-[0.86] ${MESA_COMPARISON_TONE[k]}`}>
                    {t(`mesa.comparison.${k}.value`)}
                  </p>
                  <p className="mt-2.5 text-[13px] leading-snug text-[color:var(--on-dark-2)]">
                    {t(`mesa.comparison.${k}.note`)}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-6 max-w-[38rem] text-[15px] leading-relaxed text-[color:var(--on-dark-2)]">
              {t("mesa.footnote")}
            </p>
          </div>
        </div>
      </div>
    </FieldSection>
  );
}

/* ── #territorios ─────────────────────────────────────────────────────────
   Where collection happened: the design's D3 + topojson Colombia choropleth
   (see CoverageMap) with the two reporting territories, plus an always-
   rendered accessible table carrying the same numbers — the map's real
   no-JS/screen-reader equivalent, not a decorative aside. The 31 uncovered
   departments render as the site's NOT-COLLECTED mark — hollow and dashed —
   never as zero. This is the unknown-vs-zero showcase. */
export function TerritoriesSection({ locale, t }: { locale: Locale; t: Text }) {
  const nf = new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US");
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
    <section id="territorios" aria-label={t("territories.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("territories.eyebrow")}
          title={t("territories.title")}
          intro={t("territories.intro")}
        />
        <div className="mt-11 grid items-start gap-16 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div className="h-[470px] border border-rule">
            <CoverageMap locale={locale} labels={mapLabels} />
          </div>
          <div>
            <div className="overflow-x-auto border-t border-rule">
              <table className="w-full min-w-[22rem] border-collapse text-left">
                <caption className="sr-only">{t("territories.table.caption")}</caption>
                <thead>
                  <tr className="border-b border-rule">
                    <th scope="col" className="ec-mono py-3 pr-3 text-[11px] font-bold text-ink-4">
                      {t("territories.table.territory")}
                    </th>
                    <th scope="col" className="ec-mono py-3 pr-3 text-right text-[11px] font-bold text-ink-4">
                      {t("territories.table.mesas")}
                    </th>
                    <th scope="col" className="ec-mono py-3 pr-3 text-right text-[11px] font-bold text-ink-4">
                      {t("territories.table.horizonte")}
                    </th>
                    <th scope="col" className="ec-mono py-3 pr-3 text-right text-[11px] font-bold text-ink-4">
                      {t("territories.table.rio")}
                    </th>
                    <th scope="col" className="ec-mono py-3 pr-3 text-right text-[11px] font-bold text-ink-4">
                      {t("territories.table.total")}
                    </th>
                    <th scope="col" className="ec-mono py-3 text-[11px] font-bold text-ink-4">
                      {t("territories.table.status")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {TERRITORIES.map((territory) => {
                    const totals = territoryTotals(territory.key);
                    return (
                      <tr key={territory.key} className="border-b border-rule-faint">
                        <th scope="row" className="py-3 pr-3 font-normal">
                          <p className="ec-mark m-0 text-[12px] text-ink-4">
                            {t(`territories.covered.${territory.key}.name`)}
                          </p>
                          <p className="ec-mono mt-1 text-[11px] text-ink-3">
                            {t(`territories.covered.${territory.key}.place`)}
                          </p>
                        </th>
                        <td className="ec-mono py-3 pr-3 text-right tabular-nums">
                          {totals.mesas}
                        </td>
                        <td className="ec-mono py-3 pr-3 text-right tabular-nums">
                          {nf.format(totals.horizonte)}
                        </td>
                        <td className="ec-mono py-3 pr-3 text-right tabular-nums">
                          {nf.format(totals.rio)}
                        </td>
                        <td className="ec-fig py-3 pr-3 text-right text-[16px] tabular-nums">
                          {nf.format(totals.total)}
                        </td>
                        <td className="py-3">
                          <span className="inline-flex items-center gap-2">
                            <StateMark state="observed" />
                            <span className="ec-mono text-[11px] text-ink-3">
                              {t("territories.table.statusReporting")}
                            </span>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  <tr>
                    <th scope="row" className="py-3 pr-3 font-normal">
                      <p className="ec-mark m-0 text-[12px] text-ink-4">
                        {t("territories.uncovered.name")}
                      </p>
                    </th>
                    <td colSpan={4} className="ec-mono py-3 pr-3 text-[11px] text-ink-3">
                      {t("territories.uncovered.meta")}
                    </td>
                    <td className="py-3">
                      <span className="inline-flex items-center gap-2">
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
            <p className="mt-3 max-w-[28rem] text-[14px] leading-relaxed text-ink-2">
              {t("territories.uncovered.note")}
            </p>
            <div className="mt-6 flex items-baseline gap-3.5">
              <p className="ec-fig m-0 text-[clamp(1.75rem,3vw,2.375rem)] text-ink-4">
                {UNCOVERED_DEPARTMENTS_COUNT}
              </p>
              <p className="m-0 max-w-[22rem] text-[14px] leading-snug text-ink-3">
                {t("territories.uncoveredStat")}
              </p>
            </div>
          </div>
        </div>
      </Gutter>
    </section>
  );
}

/* ── #proceso (dark) ──────────────────────────────────────────────────────
   Nine steps between the official document and the page. Three of them are
   gates that stop publication entirely if not cleared. */
const STEPS = [
  { n: "01", gate: false },
  { n: "02", gate: false },
  { n: "03", gate: true },
  { n: "04", gate: false },
  { n: "05", gate: true },
  { n: "06", gate: false },
  { n: "07", gate: false },
  { n: "08", gate: true },
  { n: "09", gate: false },
] as const;

export function ProcessSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <FieldSection id="proceso" label={t("process.eyebrow")} className="mt-20 scroll-mt-24">
      <div lang={locale}>
        <div className="grid items-start gap-x-16 gap-y-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <div>
            <p className="ec-mark m-0 text-[color:var(--on-dark-3)]">{t("process.eyebrow")}</p>
            <h2 className="ec-head mt-4">{t("process.title")}</h2>
          </div>
          <div className="max-w-[44rem] text-body leading-relaxed text-[color:var(--on-dark-2)]">
            <p className="m-0">{t("process.intro")}</p>
            <p className="ec-mono mt-4 text-[13px] text-[color:var(--neon)]">
              {t("process.gateCount")}
            </p>
          </div>
        </div>
        <ol className="mt-10 grid list-none gap-px border border-[color:var(--on-dark-3)]/30 bg-[color:var(--on-dark-3)]/30 p-0 sm:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="ec-field-dark p-6">
              <div className="flex items-center gap-3">
                <p className="ec-mono m-0 text-[12px] text-[color:var(--on-dark-3)]">{s.n}</p>
                {s.gate ? (
                  <span className="ec-mono rounded-sm border border-[color:var(--neon)] px-2 py-0.5 text-[10px] text-[color:var(--neon)]">
                    {t("process.gateTag")}
                  </span>
                ) : null}
              </div>
              <p className="mt-3 text-[15px] font-semibold leading-snug">
                {t(`process.step.${s.n}.title`)}
              </p>
              <p className="mt-2 text-[13px] leading-relaxed text-[color:var(--on-dark-2)]">
                {t(`process.step.${s.n}.body`)}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </FieldSection>
  );
}

/* ── #bitácora ────────────────────────────────────────────────────────────
   The decisions log, in the order decisions were taken. Several were fixed
   before the 2026 data was seen — which is why they hold up afterward.
   Reproduced as the design's own `bitacora-track` / `bit-stage`: a horizontal
   timeline of phase stops, not a vertical list. See BitacoraTrack for the
   adaptation this needed to keep it keyboard- and reduced-motion-safe. */
const LOG = ["layers", "sentinel", "benford", "indexonly", "retraction"] as const;

export function LogSection({ locale, t }: { locale: Locale; t: Text }) {
  const stops = LOG.map((key) => ({
    key,
    when: t(`log.entry.${key}.when`),
    title: t(`log.entry.${key}.title`),
    body: t(`log.entry.${key}.body`),
  }));
  return (
    <section id="bitacora" aria-label={t("log.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("log.eyebrow")}
          title={t("log.title")}
          intro={t("log.intro")}
        />
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
   The three files and the OpenAPI contract. Immutable, hash-carrying.
   Reproduces the design's own header row — eyebrow, intro sentence and an
   AppButton in one baseline-aligned line, no big headline here, unlike every
   other section — plus its dataset row layout (a hairline top rule, not a
   boxed card) and its three-column route list. */
const DATASETS = ["json", "parquet", "csv"] as const;
const ROUTES = [
  "/api/v1/release-elections",
  "/api/v1/releases/{release}/elections/{election}/results",
  "/api/v1/releases/{release}/datasets",
] as const;

export function DataSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section id="datos" aria-label={t("data.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="py-18">
        <div className="flex flex-wrap items-baseline justify-between gap-x-10 gap-y-4 border-t border-rule pt-7">
          <h2 className="ec-mark m-0 shrink-0 text-ink-4">{t("data.eyebrow")}</h2>
          <p className="m-0 max-w-[44rem] flex-1 text-[16px] leading-relaxed text-ink-2">
            {t("data.intro")}
          </p>
          <AppButton
            variant="outline"
            size="sm"
            href={`/${locale}/api`}
            className="shrink-0"
          >
            {t("data.docsLabel")}
          </AppButton>
        </div>

        <div className="mt-8 grid gap-x-14 gap-y-6 sm:grid-cols-3">
          {DATASETS.map((d) => (
            <div
              key={d}
              className="flex flex-wrap items-baseline gap-3.5 border-t border-rule-faint pt-3.5"
            >
              <p className="ec-mono m-0 shrink-0 text-[13px] font-bold">
                {t(`data.file.${d}.format`)}
              </p>
              <p className="ec-mono m-0 shrink-0 text-[12px] text-ink-3">
                {t(`data.file.${d}.size`)}
              </p>
              <p className="ec-mono m-0 min-w-0 break-all text-[11px] text-ink-4">
                {t(`data.file.${d}.hash`)}
              </p>
            </div>
          ))}
        </div>

        <p className="ec-mark mt-9 text-ink-4">{t("data.apiLabel")}</p>
        <ul className="mt-4 grid list-none gap-x-14 p-0 sm:grid-cols-3">
          {ROUTES.map((r) => (
            <li
              key={r}
              className="flex flex-wrap items-baseline gap-x-3 border-b border-rule/60 py-3"
            >
              <span className="ec-mono text-[11px] font-bold text-ink-3">GET</span>
              <span className="ec-mono break-all text-[12px]">{r}</span>
            </li>
          ))}
        </ul>
      </Gutter>
    </section>
  );
}
