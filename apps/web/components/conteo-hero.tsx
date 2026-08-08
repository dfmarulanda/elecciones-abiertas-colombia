"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import type { components } from "@elecciones/contracts";
import { build, buildBallots } from "@/lib/hexes";
import { MESAS, TERRITORIES, type TerritoryKey } from "@/lib/dc-fixture";

type Locale = "es" | "en";
type ElectionSummary = components["schemas"]["ElectionSummary"];

const PAPER = "#F4F1EA";
const NEON = "#C4FF00";
const HOLLOW = "rgba(196,255,0,.55)";
const RIO = "#8C8E00";

const DIVIPOLE_PREFIX: Record<TerritoryKey, string> = {
  bog: "11-001-001-",
  med: "05-001-001-",
};

const CELL_SIZE = 11;
const CELL_COLS = 10;

type LayerKey = "pre" | "doc" | "legal";
type LayerVisualState = "full" | "flag" | "out";

const LAYER_ORDER: LayerKey[] = ["pre", "doc", "legal"];
const LAYER_VISUAL: Record<LayerKey, LayerVisualState> = {
  pre: "full",
  doc: "flag",
  legal: "out",
};

const TOTAL_H = MESAS.reduce((sum, m) => sum + m.h, 0);
const TOTAL_R = MESAS.reduce((sum, m) => sum + m.r, 0);
const DISPUTED = MESAS.reduce((sum, m) => sum + (m.disp ?? 0), 0);

function layerCounts(layer: LayerKey) {
  const h = layer === "legal" ? TOTAL_H - DISPUTED : TOTAL_H;
  return { h, r: TOTAL_R };
}

function formatInt(n: number, locale: Locale) {
  return new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US").format(n);
}

function formatPct(n: number, total: number, locale: Locale) {
  return new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format((n / total) * 100);
}

const isObserved = (m?: { value: number | null; status: string }) =>
  !!m && m.status === "observed" && m.value !== null;

/**
 * #conteo — the design's dark national-count hero. When a real ElectionSummary
 * is supplied (the preconteo release), it renders the REAL national total and
 * candidate split, with the vote field rescaled so each hexagon stands for a
 * bounded number of votes (the ~26M national count cannot be one-hex-per-vote).
 * Without a summary it falls back to the design's illustrative six-mesa field.
 */
export function ConteoHero({
  locale,
  available,
  summary,
}: {
  locale: Locale;
  available: boolean;
  summary?: ElectionSummary;
}) {
  const t = useTranslations();
  const [layer, setLayer] = useState<LayerKey>("pre");
  const [hover, setHover] = useState<string | null>(null);

  if (!available) {
    return <UnavailableHero locale={locale} t={t} />;
  }

  const real =
    summary && isObserved(summary.valid_votes) && summary.candidates.length >= 2
      ? summary
      : null;

  if (real) {
    return <RealConteo locale={locale} summary={real} />;
  }

  // ── Illustrative six-mesa fallback (the original design fixture) ──────────
  const step = CELL_SIZE;
  const { h: layerH, r: layerR } = layerCounts(layer);
  const total = layerH + layerR;
  const visual = LAYER_VISUAL[layer];
  const dispFill =
    visual === "full" ? PAPER : visual === "flag" ? NEON : "none";
  const dispStroke = visual === "out" ? HOLLOW : "none";
  const dotOp = visual === "out" ? 1 : 0;
  const delta =
    layer === "pre"
      ? { text: t("conteo.deltaDefault"), on: false }
      : { text: t(`conteo.layers.${layer}.delta`), on: true };

  const groups = TERRITORIES.map((territory) => {
    const mesas = MESAS.filter((m) => m.t === territory.key);
    const votes = mesas.reduce((sum, m) => sum + m.h + m.r, 0);
    return {
      key: territory.key,
      name: t(`territories.covered.${territory.key}.name`),
      meta: `${mesas.length} ${t("territories.unit.mesas")} · ${formatInt(votes, locale)} ${t("territories.unit.votes")}`,
      flex: votes,
      mesas,
    };
  });

  const hoveredMesa = hover ? MESAS.find((m) => m.id === hover) : undefined;
  const hoveredTerritory = hoveredMesa
    ? TERRITORIES.find((tr) => tr.key === hoveredMesa.t)
    : undefined;
  const hoverLine =
    hoveredMesa && hoveredTerritory
      ? `2026-R2-${DIVIPOLE_PREFIX[hoveredTerritory.key]}${hoveredMesa.id}    ${t("conteo.legend.horizonte")} ${hoveredMesa.h}    ${t("conteo.legend.rio")} ${hoveredMesa.r}    ${hoveredMesa.h + hoveredMesa.r} ${t("conteo.hoverValidUnit")}    ${hoveredMesa.disp ? t("conteo.hoverDisputed") : t("conteo.hoverClean")}`
      : t("conteo.hoverDefault");

  return (
    <main id="main-content" tabIndex={-1}>
      <section
        id="conteo"
        data-theme="dark"
        data-screen-label="El conteo"
        lang={locale}
        style={{
          background: "#151312",
          color: "#F4F1EA",
          padding: "60px 0 54px",
        }}
      >
        <div
          className="eac-gutter"
          style={{ maxWidth: 1440, margin: "0 auto", padding: "0 46px" }}
        >
          <div
            className="eac-hero-summary rise"
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0,1fr) auto",
              gap: 72,
              alignItems: "end",
            }}
          >
            <div>
              <p
                className="mono"
                style={{ margin: 0, fontSize: 12, color: "#928979" }}
              >
                {t("conteo.eyebrow")}
              </p>
              <h1
                aria-label={t("conteo.eyebrow")}
                className="eac-hero-heading"
                style={{
                  margin: "18px 0 0",
                  display: "flex",
                  alignItems: "baseline",
                  gap: 20,
                  flexWrap: "wrap",
                  color: "#F4F1EA",
                }}
              >
                <span
                  className="fig eac-hero-total"
                  style={{ fontSize: 118, lineHeight: 0.84 }}
                >
                  {formatInt(total, locale)}
                </span>
                <span
                  className="mark"
                  style={{ fontSize: 18, color: "#F4F1EA" }}
                >
                  {t("conteo.totalLabel")}
                </span>
              </h1>
              <p
                className="mono"
                style={{
                  margin: "14px 0 0",
                  fontSize: 13,
                  color: delta.on ? NEON : "#928979",
                }}
              >
                {delta.text}
              </p>
            </div>
            <div
              className="eac-candidate-totals"
              style={{
                display: "flex",
                gap: 52,
                alignItems: "flex-end",
                flex: "none",
              }}
            >
              <div style={{ textAlign: "right" }}>
                <p
                  className="mono"
                  style={{ margin: 0, fontSize: 12, color: "#928979" }}
                >
                  {t("conteo.horizonteLabel")}
                </p>
                <p
                  className="fig"
                  style={{
                    margin: "9px 0 0",
                    fontSize: 56,
                    lineHeight: 0.88,
                    color: "#F4F1EA",
                  }}
                >
                  {formatPct(layerH, total, locale)} %
                </p>
                <p
                  className="mono"
                  style={{ margin: "8px 0 0", fontSize: 13, color: "#CFC8BC" }}
                >
                  {formatInt(layerH, locale)} {t("territories.unit.votes")}
                </p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p
                  className="mono"
                  style={{ margin: 0, fontSize: 12, color: "#928979" }}
                >
                  {t("conteo.rioLabel")}
                </p>
                <p
                  className="fig"
                  style={{
                    margin: "9px 0 0",
                    fontSize: 56,
                    lineHeight: 0.88,
                    color: "#B5B72E",
                  }}
                >
                  {formatPct(layerR, total, locale)} %
                </p>
                <p
                  className="mono"
                  style={{ margin: "8px 0 0", fontSize: 13, color: "#CFC8BC" }}
                >
                  {formatInt(layerR, locale)} {t("territories.unit.votes")}
                </p>
              </div>
            </div>
          </div>

          <div className="field" style={{ marginTop: 44 }}>
            <div
              className="eac-territory-fields"
              style={{ display: "flex", gap: 70, alignItems: "flex-start" }}
            >
              {groups.map((group) => (
                <div key={group.key} style={{ flex: group.flex, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "space-between",
                      gap: 16,
                      paddingBottom: 11,
                      marginBottom: 18,
                      borderBottom: "1px solid rgba(244,241,234,.26)",
                    }}
                  >
                    <p className="mark" style={{ margin: 0, color: "#F4F1EA" }}>
                      {group.name}
                    </p>
                    <p
                      className="mono"
                      style={{ margin: 0, fontSize: 12, color: "#928979" }}
                    >
                      {group.meta}
                    </p>
                  </div>
                  <div
                    className="eac-mesa-fields"
                    style={{
                      display: "flex",
                      gap: 24,
                      alignItems: "flex-start",
                    }}
                  >
                    {group.mesas.map((mesa) => {
                      const g = build(mesa, step, CELL_COLS);
                      const opacity = !hover || hover === mesa.id ? 1 : 0.2;
                      const label = mesa.disp
                        ? layer === "doc"
                          ? t("conteo.mesaDisputed", { id: mesa.id })
                          : layer === "legal"
                            ? t("conteo.mesaDiscounted", { id: mesa.id })
                            : t("conteo.mesaPlain", { id: mesa.id })
                        : t("conteo.mesaPlain", { id: mesa.id });
                      const labelFg =
                        mesa.disp && layer !== "pre" ? NEON : "#928979";
                      return (
                        <div
                          key={mesa.id}
                          className="blk"
                          style={{ flex: "1 1 0", minWidth: 0, opacity }}
                          tabIndex={0}
                          onMouseEnter={() => setHover(mesa.id)}
                          onMouseLeave={() => setHover(null)}
                          onFocus={() => setHover(mesa.id)}
                          onBlur={() => setHover(null)}
                        >
                          <svg
                            viewBox={g.vb}
                            role="img"
                            aria-label={t("conteo.mesaAlt", {
                              id: mesa.id,
                              h: mesa.h,
                              r: mesa.r,
                            })}
                            style={{
                              display: "block",
                              width: "100%",
                              height: "auto",
                            }}
                          >
                            <path d={g.dH} fill="#F4F1EA" />
                            <path d={g.dR} fill={RIO} />
                            <path
                              d={g.dD}
                              fill={dispFill}
                              stroke={dispStroke}
                              strokeWidth={1.4}
                            />
                            <path d={g.dDot} fill={NEON} opacity={dotOp} />
                          </svg>
                          <p
                            className="mono"
                            style={{
                              margin: "13px 0 0",
                              fontSize: 12,
                              color: labelFg,
                            }}
                          >
                            {label}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div
            className="eac-layer-panel"
            style={{
              display: "grid",
              gridTemplateColumns: "auto minmax(0,1fr)",
              gap: 56,
              alignItems: "start",
              marginTop: 40,
              paddingTop: 28,
              borderTop: "1px solid rgba(244,241,234,.26)",
            }}
          >
            <div style={{ flex: "none" }}>
              <p
                className="mono"
                style={{ margin: "0 0 12px", fontSize: 12, color: "#928979" }}
              >
                {t("conteo.layerControlLabel")}
              </p>
              <div
                role="tablist"
                aria-label={t("conteo.layerControlLabel")}
                style={{
                  display: "inline-flex",
                  border: "1px solid rgba(244,241,234,.4)",
                }}
              >
                {LAYER_ORDER.map((key) => {
                  const selected = layer === key;
                  return (
                    <button
                      key={key}
                      type="button"
                      role="tab"
                      aria-selected={selected}
                      onClick={() => setLayer(key)}
                      className="mono"
                      style={{
                        border: 0,
                        borderLeft:
                          key === "pre"
                            ? "none"
                            : "1px solid rgba(244,241,234,.4)",
                        background: selected ? NEON : "transparent",
                        color: selected ? "#151312" : "#F4F1EA",
                        fontSize: 12,
                        padding: "9px 16px",
                        cursor: "pointer",
                      }}
                    >
                      {t(`conteo.layers.${key}.label`)}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <p
                style={{
                  margin: 0,
                  maxWidth: "48rem",
                  fontSize: 18,
                  lineHeight: 1.55,
                  color: "#F4F1EA",
                }}
              >
                {t(`conteo.layers.${layer}.note`)}
              </p>
              <Legend t={t} />
            </div>
          </div>

          <p
            className="mono"
            style={{
              margin: "28px 0 0",
              fontSize: 12,
              lineHeight: 1.7,
              color: "#928979",
              maxWidth: "58rem",
            }}
          >
            {hoverLine}
          </p>
        </div>
      </section>
    </main>
  );
}

const FIELD_COLS = 42;
const FIELD_ROWS = 16;

/**
 * The real preconteo hero: the national total and the two-candidate split from
 * the ElectionSummary, with the vote field rescaled to `each hex ≈ N votes`.
 * Single-source pre-count, so no layer switcher — that device only made sense
 * over the illustrative multi-source fixture.
 */
function RealConteo({
  locale,
  summary,
}: {
  locale: Locale;
  summary: ElectionSummary;
}) {
  const t = useTranslations();
  const total = summary.valid_votes.value ?? 0;
  const ranked = [...summary.candidates]
    .filter((c) => isObserved(c.votes))
    .sort((a, b) => (b.votes.value ?? 0) - (a.votes.value ?? 0));
  const [winner, runner] = ranked;
  const wVotes = winner?.votes.value ?? 0;
  const rVotes = runner?.votes.value ?? 0;

  // `valid_votes` includes blank ballots (valid = Σcandidates + blank), so the
  // field draws three quantities. Giving the runner-up every non-winner cell
  // would redraw 426,848 blank ballots as votes for a candidate.
  const cells = FIELD_COLS * FIELD_ROWS;
  const perHex = Math.max(1, Math.round(total / cells));
  const wCells = Math.round((wVotes / total) * cells);
  const rCells = Math.round((rVotes / total) * cells);
  const blankCells = Math.max(0, cells - wCells - rCells);
  const g = buildBallots(wCells, rCells, blankCells, CELL_SIZE, FIELD_COLS);

  const nameOf = (c?: ElectionSummary["candidates"][number]) => {
    if (!c) return "";
    return t("conteo.candidateLabel", {
      name: c.candidate.name[locale],
      number: c.candidate.ballot_number ?? "—",
    });
  };

  const turnout = summary.turnout;
  const completion = summary.completion;
  const turnoutText =
    turnout !== null && turnout !== undefined
      ? `${new Intl.NumberFormat(locale === "es" ? "es-CO" : "en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(turnout * 100)} %`
      : t("common.metricUnavailable");

  return (
    <main id="main-content" tabIndex={-1}>
      <section
        id="conteo"
        data-theme="dark"
        data-screen-label="El conteo"
        lang={locale}
        style={{
          background: "#151312",
          color: "#F4F1EA",
          padding: "60px 0 54px",
        }}
      >
        <div
          className="eac-gutter"
          style={{ maxWidth: 1440, margin: "0 auto", padding: "0 46px" }}
        >
          <div
            className="eac-hero-summary rise"
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0,1fr) auto",
              gap: 72,
              alignItems: "end",
            }}
          >
            <div>
              <p
                className="mono"
                style={{ margin: 0, fontSize: 12, color: "#928979" }}
              >
                {t("conteo.eyebrow")}
              </p>
              <h1
                aria-label={t("conteo.eyebrow")}
                className="eac-hero-heading"
                style={{
                  margin: "18px 0 0",
                  display: "flex",
                  alignItems: "baseline",
                  gap: 20,
                  flexWrap: "wrap",
                  color: "#F4F1EA",
                }}
              >
                <span
                  className="fig eac-hero-total"
                  style={{ fontSize: 118, lineHeight: 0.84 }}
                >
                  {formatInt(total, locale)}
                </span>
                <span
                  className="mark"
                  style={{ fontSize: 18, color: "#F4F1EA" }}
                >
                  {t("conteo.totalLabel")}
                </span>
              </h1>
              <p
                aria-label={t("conteo.turnoutAccessible", {
                  turnout: turnoutText,
                })}
                className="mono"
                style={{ margin: "14px 0 0", fontSize: 13, color: "#CFC8BC" }}
              >
                {t("conteo.preconteoNote", {
                  turnout: turnoutText,
                  reported: formatInt(completion.reported, locale),
                  expected: formatInt(completion.expected, locale),
                })}
              </p>
              <Link
                href={`/${locale}/resultados`}
                className="mono eac-results-link"
              >
                {t("home.openResults")}
              </Link>
            </div>
            <div
              className="eac-candidate-totals"
              style={{
                display: "flex",
                gap: 52,
                alignItems: "flex-end",
                flex: "none",
              }}
            >
              <div style={{ textAlign: "right" }}>
                <p
                  className="mono"
                  style={{
                    margin: 0,
                    fontSize: 12,
                    color: "#928979",
                    maxWidth: 220,
                  }}
                >
                  {nameOf(winner)}
                </p>
                <p
                  className="fig"
                  style={{
                    margin: "9px 0 0",
                    fontSize: 56,
                    lineHeight: 0.88,
                    color: "#F4F1EA",
                  }}
                >
                  {formatPct(wVotes, total, locale)} %
                </p>
                <p
                  className="mono"
                  style={{ margin: "8px 0 0", fontSize: 13, color: "#CFC8BC" }}
                >
                  {formatInt(wVotes, locale)} {t("territories.unit.votes")}
                </p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p
                  className="mono"
                  style={{
                    margin: 0,
                    fontSize: 12,
                    color: "#928979",
                    maxWidth: 220,
                  }}
                >
                  {nameOf(runner)}
                </p>
                <p
                  className="fig"
                  style={{
                    margin: "9px 0 0",
                    fontSize: 56,
                    lineHeight: 0.88,
                    color: "#B5B72E",
                  }}
                >
                  {formatPct(rVotes, total, locale)} %
                </p>
                <p
                  className="mono"
                  style={{ margin: "8px 0 0", fontSize: 13, color: "#CFC8BC" }}
                >
                  {formatInt(rVotes, locale)} {t("territories.unit.votes")}
                </p>
              </div>
            </div>
          </div>

          <div className="field" style={{ marginTop: 44 }}>
            <svg
              className="fade"
              viewBox={g.vb}
              role="img"
              aria-label={t("conteo.fieldAlt", {
                winner: nameOf(winner),
                runner: nameOf(runner),
                perHex: formatInt(perHex, locale),
              })}
              style={{ display: "block", width: "100%", height: "auto" }}
            >
              <path d={g.dA} fill="#F4F1EA" />
              <path d={g.dB} fill={RIO} />
              {/* Blank ballots: counted in valid_votes, cast for no candidate.
                  Hollow so they are never read as votes for either ticket. */}
              <path
                d={g.dBlank}
                fill="none"
                stroke={HOLLOW}
                strokeWidth={1.2}
              />
            </svg>
            <p
              className="mono"
              style={{ margin: "16px 0 0", fontSize: 12, color: "#CFC8BC" }}
            >
              {t("conteo.perHex", { n: formatInt(perHex, locale) })}
            </p>
          </div>

          <div
            style={{
              marginTop: 40,
              paddingTop: 28,
              borderTop: "1px solid rgba(244,241,234,.26)",
            }}
          >
            <Legend
              t={t}
              winner={nameOf(winner)}
              runner={nameOf(runner)}
              blank
            />
          </div>
        </div>
      </section>
    </main>
  );
}

function Legend({
  t,
  winner,
  runner,
  blank,
}: {
  t: ReturnType<typeof useTranslations>;
  winner?: string;
  runner?: string;
  /** Show the blank-ballot key. Only the real-data field draws them. */
  blank?: boolean;
}) {
  const items = [
    { t: winner || t("conteo.legend.horizonte"), bg: "#F4F1EA", bd: "#F4F1EA" },
    { t: runner || t("conteo.legend.rio"), bg: RIO, bd: RIO },
    ...(blank
      ? [{ t: t("conteo.legend.blank"), bg: "transparent", bd: HOLLOW }]
      : []),
  ];
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "10px 22px",
        marginTop: 4,
      }}
    >
      {items.map((k) => (
        <span
          key={k.t}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 13,
            color: "#CFC8BC",
            whiteSpace: "nowrap",
          }}
        >
          <span
            style={{
              width: 10,
              height: 10,
              flex: "none",
              background: k.bg,
              border: `1px solid ${k.bd}`,
            }}
          />
          {k.t}
        </span>
      ))}
    </div>
  );
}

function UnavailableHero({
  locale,
  t,
}: {
  locale: Locale;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <main id="main-content" tabIndex={-1}>
      <section
        id="conteo"
        data-theme="dark"
        data-screen-label="El conteo"
        lang={locale}
        style={{
          background: "#151312",
          color: "#F4F1EA",
          padding: "60px 0 54px",
        }}
      >
        <div
          className="eac-gutter"
          style={{ maxWidth: 1440, margin: "0 auto", padding: "0 46px" }}
        >
          <div
            className="eac-unavailable-grid rise"
            style={{
              display: "grid",
              gridTemplateColumns: "auto minmax(0,1fr)",
              gap: 44,
              alignItems: "center",
            }}
          >
            <svg
              viewBox="0 0 240 210"
              role="img"
              aria-label={t("territories.uncovered.name")}
              style={{ display: "block", width: 120, height: "auto" }}
            >
              <path
                d="M225 105L180 183L90 183L45 105L90 27L180 27Z"
                fill="none"
                stroke="#928979"
                strokeWidth={2}
                strokeDasharray="9 9"
              />
              <text
                x={135}
                y={114}
                textAnchor="middle"
                fontFamily="JetBrains Mono,ui-monospace,monospace"
                fontSize={15}
                fill="#928979"
              >
                {t("common.metricUnavailable").toLowerCase()}
              </text>
            </svg>
            <div>
              <p
                className="mono"
                style={{ margin: 0, fontSize: 12, color: "#928979" }}
              >
                {t("conteo.unavailableEyebrow")}
              </p>
              <h1
                style={{ margin: "12px 0 0", color: "#F4F1EA" }}
                className="head"
              >
                {t("releaseUnavailable.title")}
              </h1>
              <p
                style={{
                  margin: "16px 0 0",
                  maxWidth: "44rem",
                  fontSize: 17,
                  lineHeight: 1.6,
                  color: "#CFC8BC",
                }}
              >
                {t("releaseUnavailable.body")}
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
