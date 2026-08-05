import { FieldSection, Gutter, SectionHeader } from "@/components/page-primitives";

type Locale = "es" | "en";
type Text = (key: string) => string;

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
   together. The point is the principle — a number alone means nothing — so the
   section teaches the thermometer analogy and never displays 2026 in isolation
   or any single screen value. */
export function ComparisonSection({ locale, t }: { locale: Locale; t: Text }) {
  const years = ["2018", "2022", "2026"] as const;
  return (
    <section id="comparacion" aria-label={t("comparison.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("comparison.eyebrow")}
          title={t("comparison.title")}
          intro={
            <>
              <p className="m-0">{t("comparison.introA")}</p>
              <p className="mt-4">{t("comparison.introB")}</p>
            </>
          }
        />
        <div className="mt-11 grid items-stretch gap-6 sm:grid-cols-3">
          {years.map((y) => (
            <div
              key={y}
              className={`border border-rule p-7 ${y === "2026" ? "ec-field-dark border-transparent" : ""}`}
            >
              <p className="ec-mark m-0 text-ink-4">{t(`comparison.year.${y}.tag`)}</p>
              <p className="ec-fig mt-3 text-[clamp(1.5rem,3vw,2rem)]">{y}</p>
              <p className={`mt-4 text-[15px] leading-relaxed ${y === "2026" ? "text-[color:var(--on-dark-2)]" : "text-ink-2"}`}>
                {t(`comparison.year.${y}.note`)}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-6 max-w-[46rem] text-[14px] leading-relaxed text-ink-3">
          {t("comparison.footnote")}
        </p>
      </Gutter>
    </section>
  );
}

/* ── #mesa (dark) ─────────────────────────────────────────────────────────
   One table across three layers. Illustrative on synthetic data; states a
   six-vote difference without characterising it. */
export function MesaSection({ locale, t }: { locale: Locale; t: Text }) {
  const layers = ["precount", "e14", "scrutiny"] as const;
  return (
    <FieldSection id="mesa" label={t("mesa.eyebrow")} className="mt-20 scroll-mt-24">
      <div lang={locale}>
        <div className="grid items-start gap-x-14 gap-y-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
          <div>
            <p className="ec-mark m-0 text-[color:var(--on-dark-3)]">{t("mesa.eyebrow")}</p>
            <h2 className="ec-head mt-4">{t("mesa.title")}</h2>
          </div>
          <p className="max-w-[44rem] text-body leading-relaxed text-[color:var(--on-dark-2)]">
            {t("mesa.intro")}
          </p>
        </div>
        <div className="mt-10 grid gap-3 sm:grid-cols-3">
          {layers.map((l) => (
            <div key={l} className="border border-[color:var(--on-dark-3)]/40 p-6">
              <p className="ec-mono m-0 text-[12px] text-[color:var(--on-dark-3)]">
                {t(`mesa.layer.${l}.label`)}
              </p>
              <p className="ec-fig mt-3 text-[clamp(1.75rem,4vw,2.25rem)]">
                {t(`mesa.layer.${l}.value`)}
              </p>
              <p className="mt-2 text-[14px] leading-snug text-[color:var(--on-dark-2)]">
                {t(`mesa.layer.${l}.note`)}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-7 max-w-[46rem] text-[14px] leading-relaxed text-[color:var(--on-dark-2)]">
          {t("mesa.footnote")}
        </p>
      </div>
    </FieldSection>
  );
}

/* ── #territorios ─────────────────────────────────────────────────────────
   Where collection happened. The empty departments render as an explicit
   NOT-COLLECTED state — a hollow dashed mark — never as zero. This is the
   unknown-vs-zero showcase. */
const COVERED = ["antioquia", "cundinamarca", "valle"] as const;

export function TerritoriesSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section id="territorios" aria-label={t("territories.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("territories.eyebrow")}
          title={t("territories.title")}
          intro={t("territories.intro")}
        />
        <ol className="mt-11 grid list-none gap-px border border-rule bg-rule p-0 sm:grid-cols-2">
          {COVERED.map((d) => (
            <li key={d} className="bg-paper p-6">
              <div className="flex items-baseline justify-between gap-4">
                <p className="ec-mark m-0 text-ink-4">{t(`territories.covered.${d}.name`)}</p>
                <p className="ec-fig text-[clamp(1.25rem,2.5vw,1.5rem)]">
                  {t(`territories.covered.${d}.votes`)}
                </p>
              </div>
              <p className="ec-mono mt-2 text-[12px] text-ink-3">
                {t(`territories.covered.${d}.meta`)}
              </p>
            </li>
          ))}
          <li className="bg-paper p-6">
            <div className="flex items-baseline justify-between gap-4">
              <p className="ec-mark m-0 text-ink-4">{t("territories.uncovered.name")}</p>
              <span
                aria-label={t("territories.uncovered.stateLabel")}
                role="img"
                className="inline-block h-5 w-5 rounded-sm border-2 border-dashed border-ink-4"
              />
            </div>
            <p className="ec-mono mt-2 text-[12px] text-ink-3">
              {t("territories.uncovered.meta")}
            </p>
            <p className="mt-3 text-[14px] leading-relaxed text-ink-2">
              {t("territories.uncovered.note")}
            </p>
          </li>
        </ol>
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
        <div className="grid items-start gap-x-14 gap-y-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
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
   before the 2026 data was seen — which is why they hold up afterward. */
const LOG = ["layers", "sentinel", "benford", "indexonly", "retraction"] as const;

export function LogSection({ locale, t }: { locale: Locale; t: Text }) {
  return (
    <section id="bitacora" aria-label={t("log.eyebrow")} lang={locale} className="scroll-mt-24">
      <Gutter className="pt-20">
        <SectionHeader
          eyebrow={t("log.eyebrow")}
          title={t("log.title")}
          intro={t("log.intro")}
        />
        <ol className="mt-11 list-none border-t border-rule p-0">
          {LOG.map((k, i) => (
            <li
              key={k}
              className="grid gap-x-14 gap-y-2 border-b border-rule/60 py-6 lg:grid-cols-[8rem_minmax(0,1fr)]"
            >
              <p className="ec-mono m-0 text-[12px] text-ink-4">
                {String(i + 1).padStart(2, "0")} · {t(`log.entry.${k}.when`)}
              </p>
              <div>
                <p className="ec-claim m-0 text-[clamp(1.1rem,2vw,1.35rem)]">
                  {t(`log.entry.${k}.title`)}
                </p>
                <p className="mt-2 max-w-[46rem] text-[15px] leading-relaxed text-ink-2">
                  {t(`log.entry.${k}.body`)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Gutter>
    </section>
  );
}

/* ── #datos ───────────────────────────────────────────────────────────────
   The three files and the OpenAPI contract. Immutable, hash-carrying. */
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
        <SectionHeader
          eyebrow={t("data.eyebrow")}
          title={t("data.title")}
          intro={t("data.intro")}
        />
        <div className="mt-11 grid gap-3 sm:grid-cols-3">
          {DATASETS.map((d) => (
            <div key={d} className="border border-rule p-6">
              <p className="ec-mono m-0 text-[13px] font-bold">{t(`data.file.${d}.format`)}</p>
              <p className="ec-mono mt-2 text-[12px] text-ink-3">{t(`data.file.${d}.size`)}</p>
              <p className="ec-mono mt-4 break-all text-[11px] text-ink-4">
                {t(`data.file.${d}.hash`)}
              </p>
            </div>
          ))}
        </div>
        <p className="ec-mark mt-10 text-ink-4">{t("data.apiLabel")}</p>
        <ul className="mt-4 list-none border-t border-rule p-0">
          {ROUTES.map((r) => (
            <li key={r} className="flex flex-wrap items-baseline gap-x-4 border-b border-rule/60 py-3">
              <span className="ec-mono text-[12px] font-bold text-ink-3">GET</span>
              <span className="ec-mono break-all text-[13px]">{r}</span>
            </li>
          ))}
        </ul>
      </Gutter>
    </section>
  );
}
