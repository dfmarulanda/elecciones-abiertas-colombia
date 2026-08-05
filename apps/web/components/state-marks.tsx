import React, { type CSSProperties, type ReactNode } from "react";
import {
  formatMetricValue,
  type MetricStatus,
  type MetricStatusLabels,
  type MetricValue,
} from "@/lib/metric-value";

/**
 * The visual vocabulary for absence.
 *
 * `unknown`, `unavailable`, `not_applicable` and an observed zero are four
 * different facts, and rendering any of the first three as `0` is the worst
 * error this project can make. `formatMetricValue` already prevents it in
 * text; these marks make the difference legible before the label is read.
 *
 * Every state differs by FORM, not only by colour — the same rule the ballot
 * copy states ("la posición se identifica por nombre y número de tarjeta,
 * nunca solo por color"):
 *
 *   observed zero   solid baseline rule + a real tabular `0`
 *   unknown         diagonal hatch (something is there, we cannot read it)
 *   unavailable     dashed hollow (nothing was published)
 *   not applicable  a struck hollow (the question does not apply)
 *
 * Each mark is decorative; the status word always ships beside it as text.
 */
export type AbsenceState = MetricStatus | "zero";

export function absenceState(metric: MetricValue): AbsenceState {
  if (metric.status !== "observed") return metric.status;
  return metric.value === 0 ? "zero" : "observed";
}

const HATCH = (stroke: string) =>
  `repeating-linear-gradient(-45deg, ${stroke} 0 1.5px, transparent 1.5px 5px)`;

function markStyle(state: AbsenceState, onDark: boolean): CSSProperties {
  const line = onDark ? "rgba(244,241,234,.40)" : "#211E1E";
  const faint = onDark ? "rgba(244,241,234,.24)" : "rgba(33,30,30,.30)";
  switch (state) {
    case "zero":
      return { borderBottom: `2px solid ${line}` };
    case "unknown":
      return { border: `1px solid ${faint}`, backgroundImage: HATCH(faint) };
    case "unavailable":
      return { border: `1px dashed ${line}` };
    case "not_applicable":
      return {
        border: `1px dashed ${faint}`,
        backgroundImage: `linear-gradient(to top right, transparent calc(50% - 0.5px), ${faint} calc(50% - 0.5px), ${faint} calc(50% + 0.5px), transparent calc(50% + 0.5px))`,
      };
    default:
      return { background: onDark ? "#F4F1EA" : "#211E1E" };
  }
}

/** A 12px square carrying the state's form. Always paired with its label. */
export function StateMark({
  state,
  onDark = false,
  className = "",
}: {
  state: AbsenceState;
  onDark?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-3 shrink-0 translate-y-px ${className}`}
      style={markStyle(state, onDark)}
    />
  );
}

/**
 * Renders a MetricValue with its state mark. Never emits a bare number for a
 * non-observed status — the number comes from `formatMetricValue`, which
 * returns the status label instead of a value in that case.
 */
export function MetricReading({
  metric,
  locale,
  labels,
  onDark = false,
  className = "",
}: {
  metric: MetricValue;
  locale: string;
  labels: MetricStatusLabels;
  onDark?: boolean;
  className?: string;
}) {
  const state = absenceState(metric);
  const { display, statusLabel } = formatMetricValue(metric, locale, labels);
  const observed = metric.status === "observed";
  return (
    <span className={`inline-flex items-baseline gap-2 ${className}`}>
      <StateMark state={state} onDark={onDark} />
      <span
        className={
          observed
            ? "ec-fig tabular-nums"
            : `text-meta ${onDark ? "text-on-dark-2" : "text-ink-3"}`
        }
      >
        {display}
      </span>
      {observed ? null : <span className="sr-only">{statusLabel}</span>}
    </span>
  );
}

/**
 * The design's panel for "this exists as a question but not as a datum": a
 * dashed, empty hexagon. Used wherever a section would otherwise be tempted to
 * draw an empty chart, which reads as zero.
 */
export function UnavailablePanel({
  label,
  detail,
  onDark = false,
  className = "",
}: {
  label: string;
  detail?: ReactNode;
  onDark?: boolean;
  className?: string;
}) {
  const stroke = onDark ? "rgba(244,241,234,.40)" : "#6B6259";
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 border border-dashed px-6 py-10 text-center ${className}`}
      style={{ borderColor: stroke }}
    >
      <svg
        viewBox="0 0 52 46"
        className="h-11 w-12"
        aria-hidden="true"
        focusable="false"
      >
        <path
          d="M13 1 H39 L51 23 L39 45 H13 L1 23 Z"
          fill="none"
          stroke={stroke}
          strokeWidth="1.5"
          strokeDasharray="5 4"
        />
      </svg>
      <p className={`ec-mark m-0 ${onDark ? "text-on-dark-3" : "text-ink-4"}`}>
        {label}
      </p>
      {detail ? (
        <p
          className={`m-0 max-w-[34ch] text-meta leading-relaxed ${onDark ? "text-on-dark-2" : "text-ink-3"}`}
        >
          {detail}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The key that makes the marks readable. Any section that uses a state mark
 * must render this once, or link to the page that does.
 */
export function StateLegend({
  t,
  onDark = false,
}: {
  t: (key: string) => string;
  onDark?: boolean;
}) {
  const rows: [AbsenceState, string, string][] = [
    ["zero", t("states.zero"), t("states.zeroNote")],
    ["unknown", t("states.unknown"), t("states.unknownNote")],
    ["unavailable", t("states.unavailable"), t("states.unavailableNote")],
    [
      "not_applicable",
      t("states.notApplicable"),
      t("states.notApplicableNote"),
    ],
  ];
  return (
    <div>
      <h3 className={`ec-mark m-0 ${onDark ? "text-on-dark-3" : "text-ink-4"}`}>
        {t("states.legend")}
      </h3>
      <dl className="mt-4 grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {rows.map(([state, label, note]) => (
          <div key={state} className="flex items-baseline gap-3">
            <StateMark state={state} onDark={onDark} />
            <div className="min-w-0">
              <dt className="text-meta-lg font-semibold">{label}</dt>
              <dd
                className={`m-0 text-meta leading-relaxed ${onDark ? "text-on-dark-2" : "text-ink-3"}`}
              >
                {note}
              </dd>
            </div>
          </div>
        ))}
      </dl>
    </div>
  );
}
