"use client";

import { useParams } from "next/navigation";

import { AnalysisV2Shell } from "@/components/analysis-v2-primitives";
import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

export default function AnalysisError({ reset }: { reset: () => void }) {
  const params = useParams<{ locale?: string }>();
  const text =
    params.locale === "en" ? enMessages.analysis : esMessages.analysis;
  return (
    <AnalysisV2Shell ariaLabel={text.errorTitle}>
      <section className="eac-analysis-state-hero">
        <div className="eac-gutter eac-analysis-state-hero__inner">
          <p className="mark">
            {params.locale === "en" ? "Analysis status" : "Estado del análisis"}
          </p>
          <h1 className="head">{text.errorTitle}</h1>
        </div>
      </section>
      <section className="eac-analysis-state-body" role="alert">
        <div className="eac-gutter eac-analysis-state-body__inner">
          <p>{text.errorBody}</p>
          <button
            className="mono eac-analysis-action eac-analysis-action--primary"
            onClick={reset}
            type="button"
          >
            {text.retry}
          </button>
        </div>
      </section>
    </AnalysisV2Shell>
  );
}
