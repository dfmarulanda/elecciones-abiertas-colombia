"use client";

import { useState } from "react";
import { AppButton } from "@/components/app-button";
import {
  CMP_CRIT_BG,
  CMP_CRIT_FG,
  CMP_ZERO_BG,
  type CmpMetricKey,
  type CmpRowLayout,
} from "@/lib/cmp-fixture";

/**
 * The interactive two-thirds of #comparación, ported from `dc-data.js`'s
 * `simple` state and its `cmpRows`/`toggleSimple` logic — from the
 * thermometer card through the four measured rows to the (static) Benford
 * aside, exactly the span the design keeps in one bordered container. A
 * client component because the design's own AppButton (`{{ toggleSimple }}`)
 * flips every row between "palabras simples" and "nombres técnicos" without
 * a page reload — the same boolean the source keeps in `this.state.simple`,
 * just as React state instead of a class field. Everything numeric (band
 * position, marker position, the per-year values line) is locale-resolved
 * once by the server parent via `lib/cmp-fixture.ts` and passed in as
 * `layout`; only the prose that differs between the two reading levels is
 * switched here.
 */

export type CmpRowContent = {
  key: CmpMetricKey;
  layout: CmpRowLayout;
  plainLabel: string;
  techLabel: string;
  plainUnit: string;
  techUnit: string;
  human: string;
  plainReading: string;
  techReading: string;
  /** Only the digit-uniformity row has a critical-threshold marker label. */
  plainCritLabel?: string;
  techCritLabel?: string;
};

export function ComparisonBands({
  thermometerLead,
  thermometerBody,
  legendItems,
  toggleToTechnicalLabel,
  toggleToSimpleLabel,
  rows,
  insideVerdict,
  outsideVerdict,
  benfordLabel,
  benfordBox,
  benfordBody,
  benfordFootnote,
}: {
  thermometerLead: string;
  thermometerBody: string;
  legendItems: string[];
  toggleToTechnicalLabel: string;
  toggleToSimpleLabel: string;
  rows: CmpRowContent[];
  insideVerdict: string;
  outsideVerdict: string;
  benfordLabel: string;
  benfordBox: string;
  benfordBody: string;
  benfordFootnote: string;
}) {
  const [simple, setSimple] = useState(true);

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)",
          gap: 64,
          alignItems: "start",
          marginTop: 34,
        }}
      >
        <div style={{ background: "#151312", color: "#F4F1EA", padding: "30px 34px 32px" }}>
          <p style={{ margin: 0, fontSize: 18, lineHeight: 1.5 }}>{thermometerLead}</p>
          <p style={{ margin: "14px 0 0", fontSize: 16, lineHeight: 1.6, color: "#CFC8BC" }}>
            {thermometerBody}
          </p>
        </div>
        <div style={{ display: "grid", gap: 9 }}>
          {legendItems.map((item, i) => (
            <p key={i} style={{ margin: 0, fontSize: 15, lineHeight: 1.5, color: "#3E3831" }}>
              {item}
            </p>
          ))}
          {/* The simple/technical toggle only means something when there are
              measured rows to reword. With no rows it would be a control that
              changes nothing, so it is not rendered. */}
          {rows.length > 0 ? (
            <div style={{ marginTop: 10 }}>
              <AppButton
                variant="outline"
                size="sm"
                onClick={() => setSimple((s) => !s)}
                aria-pressed={!simple}
              >
                {simple ? toggleToTechnicalLabel : toggleToSimpleLabel}
              </AppButton>
            </div>
          ) : null}
        </div>
      </div>

      <div style={{ marginTop: 34, borderTop: "1px solid #211E1E" }}>
        {rows.map((r) => {
          const label = simple ? r.plainLabel : r.techLabel;
          const unit = simple ? r.plainUnit : r.techUnit;
          const reading = simple ? r.plainReading : r.techReading;
          const critLabel = simple ? r.plainCritLabel : r.techCritLabel;
          const verdict = r.layout.inside ? insideVerdict : outsideVerdict;
          return (
            <div
              key={r.key}
              style={{ padding: "24px 0 26px", borderBottom: "1px solid rgba(33,30,30,.16)" }}
            >
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 24 }}>
                <p
                  style={{
                    margin: 0,
                    maxWidth: "44rem",
                    fontSize: 19,
                    fontWeight: 600,
                    letterSpacing: "-.012em",
                    lineHeight: 1.28,
                  }}
                >
                  {label}
                </p>
                <p className="mono" style={{ margin: 0, fontSize: 12, color: "#6B6259", whiteSpace: "nowrap" }}>
                  {unit}
                </p>
              </div>
              <p
                style={{
                  display: simple ? "block" : "none",
                  margin: "10px 0 0",
                  maxWidth: "44rem",
                  fontSize: 15,
                  lineHeight: 1.55,
                  color: "#5A5148",
                }}
              >
                {r.human}
              </p>

              <div style={{ position: "relative", height: 66, marginTop: 16 }}>
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    top: 31,
                    height: 1,
                    background: "rgba(33,30,30,.3)",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: 23,
                    height: 17,
                    left: r.layout.bandL,
                    width: r.layout.bandW,
                    background: "rgba(33,30,30,.12)",
                    borderLeft: "1px solid rgba(33,30,30,.34)",
                    borderRight: "1px solid rgba(33,30,30,.34)",
                  }}
                />
                {r.layout.zeroL != null ? (
                  <div
                    style={{
                      position: "absolute",
                      top: 13,
                      bottom: 21,
                      left: r.layout.zeroL,
                      width: 1,
                      background: CMP_ZERO_BG,
                    }}
                  />
                ) : null}
                {r.layout.critL != null ? (
                  <>
                    <div
                      style={{
                        position: "absolute",
                        top: 9,
                        bottom: 17,
                        left: r.layout.critL,
                        width: 0,
                        borderLeft: `1px dashed ${CMP_CRIT_BG}`,
                      }}
                    />
                    <p
                      className="mono"
                      style={{
                        position: "absolute",
                        top: 0,
                        left: r.layout.critL,
                        margin: 0,
                        fontSize: 10,
                        color: CMP_CRIT_FG,
                        transform: "translateX(-50%)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {critLabel}
                    </p>
                  </>
                ) : null}
                {r.layout.marks.map((m) => (
                  <div
                    key={m.year}
                    style={{ position: "absolute", top: 25, left: m.x, transform: "translateX(-50%)" }}
                  >
                    <div style={{ width: 13, height: 13, background: "#151312", borderRadius: 999 }} />
                    <div style={{ width: 1, height: 9, margin: "0 auto", background: "rgba(33,30,30,.4)" }} />
                    <p
                      className="mono"
                      style={{
                        margin: 0,
                        fontSize: 11,
                        color: "#211E1E",
                        whiteSpace: "nowrap",
                        transform: "translateX(-50%)",
                        marginLeft: "50%",
                      }}
                    >
                      {m.year}
                    </p>
                  </div>
                ))}
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 24,
                  marginTop: 8,
                }}
              >
                <p style={{ margin: 0, fontSize: 17, fontWeight: 600, letterSpacing: "-.01em" }}>
                  {verdict}
                </p>
                <p className="mono" style={{ margin: 0, fontSize: 12, color: "#6B6259", whiteSpace: "nowrap" }}>
                  {r.layout.values}
                </p>
              </div>
              <p style={{ margin: "6px 0 0", maxWidth: "44rem", fontSize: 15, lineHeight: 1.55, color: "#3E3831" }}>
                {reading}
              </p>
            </div>
          );
        })}

        <div style={{ padding: "24px 0 26px", borderBottom: "1px solid rgba(33,30,30,.16)" }}>
          <p
            style={{
              margin: 0,
              maxWidth: "44rem",
              fontSize: 19,
              fontWeight: 600,
              letterSpacing: "-.012em",
              lineHeight: 1.28,
              color: "#6B6259",
            }}
          >
            {benfordLabel}
          </p>
          <div
            style={{
              position: "relative",
              height: 44,
              marginTop: 16,
              backgroundImage:
                "repeating-linear-gradient(135deg,transparent 0 7px,rgba(33,30,30,.13) 7px 8px)",
              borderTop: "1px solid rgba(33,30,30,.2)",
              borderBottom: "1px solid rgba(33,30,30,.2)",
            }}
          >
            <p
              className="mono"
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeContent: "center",
                margin: 0,
                fontSize: 12,
                color: "#5A5148",
              }}
            >
              {benfordBox}
            </p>
          </div>
          <p style={{ margin: "14px 0 0", maxWidth: "46rem", fontSize: 15, lineHeight: 1.55, color: "#3E3831" }}>
            {benfordBody}
          </p>
          <p className="mono" style={{ margin: "12px 0 0", fontSize: 12, color: "#6B6259" }}>
            {benfordFootnote}
          </p>
        </div>
      </div>
    </>
  );
}
