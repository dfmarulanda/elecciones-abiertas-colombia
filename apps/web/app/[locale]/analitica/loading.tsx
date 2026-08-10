"use client";

import { useParams } from "next/navigation";

import { AnalysisV2Shell } from "@/components/analysis-v2-primitives";
import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

export default function AnalysisLoading() {
  const params = useParams<{ locale?: string }>();
  const text =
    params.locale === "en" ? enMessages.analysis : esMessages.analysis;
  return (
    <AnalysisV2Shell ariaLabel={text.loading} busy mainId="analysis-loading">
      <section
        className="eac-analysis-state-hero eac-analysis-loading"
        role="status"
      >
        <div className="eac-gutter eac-analysis-state-hero__inner">
          <p className="mark">
            {params.locale === "en" ? "Analysis status" : "Estado del análisis"}
          </p>
          <h1 className="head">{text.loading}</h1>
          <div className="eac-analysis-loading__bar" aria-hidden="true" />
        </div>
      </section>
    </AnalysisV2Shell>
  );
}
