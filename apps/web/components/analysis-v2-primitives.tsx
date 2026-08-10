import React, { useId, type ReactNode } from "react";

type AnalysisV2SectionTone = "paper" | "ink";

export function AnalysisV2Shell({
  children,
  ariaLabel,
  busy = false,
}: {
  children: ReactNode;
  ariaLabel?: string;
  busy?: boolean;
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="eac-design eac-analysis"
      data-design-version="v2"
      aria-label={ariaLabel}
      aria-busy={busy || undefined}
    >
      {children}
    </main>
  );
}

export function AnalysisV2Section({
  number,
  eyebrow,
  title,
  intro,
  tone = "paper",
  id,
  dataSection,
  children,
}: {
  number: string;
  eyebrow: string;
  title: string;
  intro?: string;
  tone?: AnalysisV2SectionTone;
  id?: string;
  dataSection?: string;
  children: ReactNode;
}) {
  const generatedId = useId();
  const titleId = `${id ?? generatedId}-title`;
  return (
    <section
      id={id}
      className={`eac-analysis-section eac-analysis-section--${tone}`}
      data-analysis-section={dataSection}
      aria-labelledby={titleId}
    >
      <div className="eac-gutter eac-analysis-section__inner">
        <header className="eac-section-header eac-analysis-section__header">
          <p className="mono eac-analysis-section__number" aria-hidden="true">
            {number}
          </p>
          <div>
            <p className="mark eac-analysis-section__eyebrow">{eyebrow}</p>
            <h2 className="head" id={titleId}>
              {title}
            </h2>
            {intro ? (
              <p className="eac-analysis-section__intro">{intro}</p>
            ) : null}
          </div>
        </header>
        {children}
      </div>
    </section>
  );
}

export function AnalysisV2StateBand({
  tierLabel,
  statusLabel,
  reasons,
  reasonsLabel,
  className = "",
}: {
  tierLabel: string;
  statusLabel: string;
  reasons: string[];
  reasonsLabel: string;
  className?: string;
}) {
  const label = `${tierLabel} · ${statusLabel}`;
  return (
    <div
      className={`eac-analysis-state-band ${className}`.trim()}
      role="region"
      aria-label={label}
    >
      <div className="eac-analysis-state-band__labels">
        <span className="mark">{tierLabel}</span>
        <span className="mono">{statusLabel}</span>
      </div>
      {reasons.length ? (
        <div className="eac-analysis-state-band__reasons">
          <p className="mark">{reasonsLabel}</p>
          <ul>
            {reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
