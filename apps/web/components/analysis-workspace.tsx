import { ArrowRight, ExternalLink, FlaskConical, Search } from "lucide-react";
import Link from "next/link";
import React from "react";

import { OutcomeSensitivityPanel } from "@/components/investigation-details";
import { Page } from "@/components/page-primitives";
import { StatusBadge } from "@/components/ui";
import { analysisArtifactDownloadUrl } from "@/data/analysis-adapter";
import type {
  AnalysisAnomaly,
  AnalysisAnomalyType,
  AnalysisArtifactMetadata,
  AnalysisReport,
  AnalysisReportKind,
  AnalysisReleaseMetadata,
  AnalysisSummary,
  PublicAnalysisReady,
  PublicAnomalyDetailState,
  SignalComponent,
} from "@/data/analysis-adapter";
import type { PublicReleaseRef } from "@/data/fixture-adapter";
import { legalStatusLabel, sourceTypeLabel } from "@/lib/public-labels";
import { reviewDisclosure } from "@/lib/review-disclosure";
import { formatDate, formatNumber } from "@/lib/utils";
import enMessages from "@/messages/en.json";
import esMessages from "@/messages/es.json";

type Locale = "es" | "en";

const analysisCatalog = {
  es: esMessages.analysis,
  en: enMessages.analysis,
} as const;

type EvidenceTier = AnalysisAnomaly["evidence_tier"];

const copy = {
  es: {
    eyebrow: "Análisis reproducible · versión congelada",
    title: "Qué encontró el análisis — y qué no puede afirmar",
    intro:
      "Empiece por la conclusión legible. Después puede abrir la evidencia, los comparadores y el diagnóstico exacto del modelo.",
    researchTitle:
      "Vista de investigación: todavía no es una conclusión pública",
    researchBody:
      "Esta versión no superó todas las compuertas metodológicas publicadas. Los registros se muestran para inspección y reproducción, no como hallazgos concluyentes.",
    plainAnswer: "La respuesta corta",
    evaluated: "Registros evaluados",
    qualifying: "Registros que cumplen alguna regla publicada",
    qualifyingByRule: "Desglose por tipo de regla",
    unavailable: "No disponible",
    unknown: "Desconocido",
    notApplicable: "No aplica",
    noPublicConclusion:
      "Con este release no puede publicarse una conclusión estadística definitiva.",
    recordsMet: (anomalies: string, evaluated: string) =>
      `${anomalies} de ${evaluated} registros evaluados cumplen al menos una regla publicada.`,
    noRecordsMet: (evaluated: string) =>
      `Ninguno de los ${evaluated} registros evaluados cumple una regla publicada en esta versión.`,
    countUnavailable:
      "El conteo de registros que cumplen reglas no está disponible.",
    doesNotMean:
      "Esto no responde por sí solo si hubo fraude. Una señal identifica algo que merece revisión bajo reglas explícitas; la evidencia documental y las explicaciones se evalúan por separado.",
    coverage: "Qué datos entraron en el análisis",
    coverageIntro:
      "La cobertura es parte del resultado: ausente, ambiguo y excluido nunca se convierten en cero.",
    expected: "Esperados",
    retrieved: "Recuperados",
    parsed: "Interpretados",
    missing: "Ausentes",
    ambiguous: "Ambiguos",
    excluded: "Excluidos",
    explorer: "Explore registro por registro",
    explorerIntro:
      "Filtre por la familia de regla. La URL conserva release, elección, filtro y cursor para que otra persona pueda reproducir la misma lectura.",
    release: "Release",
    election: "Elección",
    anomalyType: "Tipo de regla",
    allTypes: "Todos los tipos",
    apply: "Aplicar filtros",
    reset: "Quitar filtro",
    empty: "No hay registros publicados para este filtro.",
    emptyCaveat:
      "Esto no significa que el territorio esté libre de errores; solo describe el conjunto publicado y el filtro activo.",
    mesa: "Mesa",
    detected: "Cumple la regla",
    notDetected: "No cumple la regla",
    researchCandidate: "Candidato de investigación",
    anomalyFamilies: "Reglas activadas",
    explanation: "Estado de la explicación",
    priority: "Prioridad de auditoría",
    observed: "Valor observado",
    comparator: "Comparador publicado",
    details: "Abrir evidencia completa",
    result: "Ver resultado de la mesa",
    next: "Siguiente página",
    end: "Fin del conjunto publicado",
    exactLimits: "Condiciones que impiden una conclusión",
    nonePublished: "No se publicaron condiciones bloqueantes.",
    expertReports: "Diagnósticos para especialistas",
    expertIntro:
      "Estas salidas no cambian la detección. Permiten revisar elegibilidad, validación, sensibilidad, artefactos y faltantes.",
    noMetrics: "No se publicaron métricas para este reporte.",
    reportStatus: "Estado",
    methodology: "Metodología",
    artifact: "Artefacto",
    metric: "Métrica",
    value: "Valor",
    status: "Condición",
    missingness: "Faltantes del reporte",
    version: "Versión de datos",
    source: "Fuente",
    legal: "Condición jurídica",
    retrievedAt: "Recuperado",
    hash: "Hash de contenido",
    explanationReview: "Qué se sabe de la explicación",
    explanationMeaning:
      "La explicación se revisa después de detectar la señal y nunca borra la detección original.",
    effect: "Efecto cuantitativo registrado",
    pValue: "Valor p de la explicación",
    reviewedAt: "Revisado",
    preregistration: "Prerregistro",
    availableData: "Datos disponibles",
    noNotes: "No hay notas explicativas publicadas.",
    ballotEdits: "Cambio mínimo de papeletas",
    ballotEditsMeaning:
      "Es un límite mecánico, no una estimación de votos fraudulentos.",
    components: "Evidencia que activó la regla",
    calculation: "Cálculo publicado",
    peerDefinition: "Definición de pares",
    limitations: "Limitaciones",
    eligibility: "Elegibilidad",
    sources: "Fuentes",
    noSources: "No hay enlaces de fuente publicados en este componente.",
    replay: "Detalles para reproducir",
    back: "Volver al explorador",
    anomalyTitle: "Análisis de mesa",
  },
  en: {
    eyebrow: "Reproducible analysis · frozen version",
    title: "What the analysis found — and what it cannot claim",
    intro:
      "Start with the plain-language conclusion. Then open the evidence, comparators, and exact model diagnostics.",
    researchTitle: "Research view: this is not yet a public conclusion",
    researchBody:
      "This version did not pass every published methodology gate. Records are available for inspection and reproduction, not as conclusive findings.",
    plainAnswer: "The short answer",
    evaluated: "Records evaluated",
    qualifying: "Records meeting at least one published rule",
    qualifyingByRule: "Breakdown by rule type",
    unavailable: "Unavailable",
    unknown: "Unknown",
    notApplicable: "Not applicable",
    noPublicConclusion:
      "This release cannot support a definitive public statistical conclusion.",
    recordsMet: (anomalies: string, evaluated: string) =>
      `${anomalies} of ${evaluated} evaluated records meet at least one published rule.`,
    noRecordsMet: (evaluated: string) =>
      `None of the ${evaluated} evaluated records meets a published rule in this version.`,
    countUnavailable: "The count of records meeting rules is unavailable.",
    doesNotMean:
      "This does not answer by itself whether fraud occurred. A signal identifies something that merits review under explicit rules; documentary evidence and explanations are assessed separately.",
    coverage: "Which data entered the analysis",
    coverageIntro:
      "Coverage is part of the result: missing, ambiguous, and excluded are never turned into zero.",
    expected: "Expected",
    retrieved: "Retrieved",
    parsed: "Parsed",
    missing: "Missing",
    ambiguous: "Ambiguous",
    excluded: "Excluded",
    explorer: "Explore record by record",
    explorerIntro:
      "Filter by rule family. The URL preserves release, election, filter, and cursor so another person can reproduce the same reading.",
    release: "Release",
    election: "Election",
    anomalyType: "Rule type",
    allTypes: "All types",
    apply: "Apply filters",
    reset: "Clear filter",
    empty: "No published records match this filter.",
    emptyCaveat:
      "This does not mean the territory was error-free; it only describes the published set and active filter.",
    mesa: "Mesa",
    detected: "Meets the rule",
    notDetected: "Does not meet the rule",
    researchCandidate: "Research candidate",
    anomalyFamilies: "Triggered rules",
    explanation: "Explanation status",
    priority: "Audit priority",
    observed: "Observed value",
    comparator: "Published comparator",
    details: "Open complete evidence",
    result: "View mesa result",
    next: "Next page",
    end: "End of published set",
    exactLimits: "Conditions blocking a conclusion",
    nonePublished: "No blocking conditions were published.",
    expertReports: "Diagnostics for specialists",
    expertIntro:
      "These outputs do not change detection. They expose eligibility, validation, sensitivity, artifacts, and missingness.",
    noMetrics: "No metrics were published for this report.",
    reportStatus: "Status",
    methodology: "Methodology",
    artifact: "Artifact",
    metric: "Metric",
    value: "Value",
    status: "Status",
    missingness: "Report missingness",
    version: "Data version",
    source: "Source",
    legal: "Legal status",
    retrievedAt: "Retrieved",
    hash: "Content hash",
    explanationReview: "What is known about the explanation",
    explanationMeaning:
      "Explanation review happens after signal detection and never erases the original detection.",
    effect: "Recorded quantitative effect",
    pValue: "Explanation p-value",
    reviewedAt: "Reviewed",
    preregistration: "Preregistration",
    availableData: "Available data",
    noNotes: "No explanatory notes were published.",
    ballotEdits: "Minimum ballot edits",
    ballotEditsMeaning:
      "This is a mechanical bound, not an estimate of fraudulent votes.",
    components: "Evidence that triggered the rule",
    calculation: "Published calculation",
    peerDefinition: "Peer definition",
    limitations: "Limitations",
    eligibility: "Eligibility",
    sources: "Sources",
    noSources: "No source links were published for this component.",
    replay: "Replay details",
    back: "Back to explorer",
    anomalyTitle: "Mesa analysis",
  },
} as const;

const anomalyTypeLabels: Record<AnalysisAnomalyType, Record<Locale, string>> = {
  structural_arithmetic: {
    es: "La aritmética o un límite estructural no cierra",
    en: "Arithmetic or a structural bound does not reconcile",
  },
  identity_coverage: {
    es: "Identidad, documento o cobertura ausente/ambigua",
    en: "Missing or ambiguous identity, document, or coverage",
  },
  cross_source_documentary: {
    es: "Fuentes documentales compatibles no coinciden",
    en: "Compatible documentary sources differ",
  },
  peer_distribution: {
    es: "Distribución distante de mesas comparables",
    en: "Distribution differs from comparable mesas",
  },
  spatial: {
    es: "Agrupación espacial de residuos del modelo",
    en: "Spatial cluster in model residuals",
  },
};

const explanationLabels: Record<string, Record<Locale, string>> = {
  explained: {
    es: "Hay una explicación documentada",
    en: "A documented explanation is available",
  },
  partially_explained: {
    es: "La explicación documentada es parcial",
    en: "The documented explanation is partial",
  },
  no_explanation_found_in_available_data: {
    es: "No se encontró explicación en los datos disponibles",
    en: "No explanation was found in available data",
  },
  non_evaluable: {
    es: "No se pudo evaluar una explicación",
    en: "An explanation could not be evaluated",
  },
};

const componentLabels: Record<
  SignalComponent["component_type"],
  Record<Locale, string>
> = {
  verified_accounting_failure: {
    es: "Falla contable verificada",
    en: "Verified accounting failure",
  },
  conflicting_official_records: {
    es: "Registros oficiales en conflicto",
    en: "Conflicting official records",
  },
  documentary_difference_major: {
    es: "Diferencia documental mayor",
    en: "Major documentary difference",
  },
  documentary_difference_minor: {
    es: "Diferencia documental menor",
    en: "Minor documentary difference",
  },
  document_missing_duplicated_ambiguous: {
    es: "Documento ausente, duplicado o ambiguo",
    en: "Missing, duplicated, or ambiguous document",
  },
  peer_distribution: {
    es: "Distribución entre pares",
    en: "Peer distribution",
  },
  spatial_cluster: {
    es: "Agrupación espacial",
    en: "Spatial cluster",
  },
};

const reportLabels: Record<AnalysisReportKind, Record<Locale, string>> = {
  model_diagnostics: {
    es: "Diagnóstico del modelo",
    en: "Model diagnostics",
  },
  validation: { es: "Validación", en: "Validation" },
  local_sensitivity: {
    es: "Sensibilidad local",
    en: "Local sensitivity",
  },
};

const reportStatusLabels: Record<string, Record<Locale, string>> = {
  available: { es: "Disponible", en: "Available" },
  research_preview: { es: "Vista de investigación", en: "Research preview" },
  ineligible: { es: "No elegible", en: "Ineligible" },
  not_evaluable: { es: "No evaluable", en: "Not evaluable" },
};

function readableCode(value: string, locale: Locale) {
  const known: Record<string, Record<Locale, string>> = {
    independent_simulation_validation_artifacts_not_published: {
      es: "No se publicaron artefactos independientes de validación por simulación.",
      en: "Independent simulation-validation artifacts were not published.",
    },
    hierarchical_and_psis_validation_not_implemented: {
      es: "La validación jerárquica y PSIS no está implementada en este artefacto.",
      en: "Hierarchical and PSIS validation is not implemented in this artifact.",
    },
    legacy_release_has_no_preregistered_explanation_artifact: {
      es: "El release heredado no incluye un artefacto de explicación prerregistrado.",
      en: "The legacy release has no preregistered explanation artifact.",
    },
    complete_ballot_vector_not_published: {
      es: "No se publicó el vector completo y mutuamente excluyente de papeletas.",
      en: "The complete mutually exclusive ballot vector was not published.",
    },
    complete_mutually_exclusive_ballot_categories_not_published: {
      es: "No se publicaron categorías completas y mutuamente excluyentes de papeletas.",
      en: "Complete mutually exclusive ballot categories were not published.",
    },
    independent_simulation_validation_artifact_not_published: {
      es: "No se publicó el artefacto independiente de validación por simulación.",
      en: "The independent simulation-validation artifact was not published.",
    },
    hierarchical_model_not_implemented: {
      es: "El modelo jerárquico no está implementado en este reporte.",
      en: "The hierarchical model is not implemented in this report.",
    },
    psis_diagnostics_not_implemented: {
      es: "No se implementaron diagnósticos PSIS en este reporte.",
      en: "PSIS diagnostics are not implemented in this report.",
    },
    independent_simulation_artifacts_not_published: {
      es: "No se publicaron artefactos independientes de simulación.",
      en: "Independent simulation artifacts were not published.",
    },
  };
  return known[value]?.[locale] ?? value.replaceAll("_", " ");
}

function signalDisplay(
  signal: { value: number | null; status: string },
  locale: Locale,
) {
  const c = copy[locale];
  if (signal.status === "observed" && signal.value !== null)
    return formatNumber(signal.value, locale);
  if (signal.status === "unknown") return c.unknown;
  if (signal.status === "not_applicable") return c.notApplicable;
  return c.unavailable;
}

function signalStatusLabel(status: string, locale: Locale) {
  const labels: Record<string, Record<Locale, string>> = {
    observed: { es: "Observado", en: "Observed" },
    unknown: { es: "Desconocido", en: "Unknown" },
    unavailable: { es: "No disponible", en: "Unavailable" },
    not_applicable: { es: "No aplica", en: "Not applicable" },
    evaluable: { es: "Evaluable", en: "Evaluable" },
    not_evaluable: { es: "No evaluable", en: "Not evaluable" },
    eligible: { es: "Elegible", en: "Eligible" },
    ineligible: { es: "No elegible", en: "Ineligible" },
    available: { es: "Disponible", en: "Available" },
    research_preview: {
      es: "Investigación preliminar",
      en: "Research preview",
    },
  };
  return labels[status]?.[locale] ?? status.replaceAll("_", " ");
}

function nullableNumber(value: number | null, locale: Locale) {
  return value === null
    ? copy[locale].unavailable
    : new Intl.NumberFormat(locale, { maximumFractionDigits: 6 }).format(value);
}

function scopedQuery(
  selected: PublicReleaseRef,
  values: Record<string, string | null | undefined> = {},
  analysisRelease?: string,
) {
  const query = new URLSearchParams({
    release: selected.release_id,
    election: selected.election_slug,
  });
  if (analysisRelease) query.set("analysis_release", analysisRelease);
  for (const [key, value] of Object.entries(values)) {
    if (value) query.set(key, value);
  }
  return query.toString();
}

function sentenceCode(value: string, locale: Locale) {
  const readable = readableCode(value, locale);
  return `${readable.charAt(0).toUpperCase()}${readable.slice(1)}`;
}

function evidenceTierLabel(tier: EvidenceTier, locale: Locale) {
  const a = analysisCatalog[locale];
  return {
    descriptive: a.descriptiveTier,
    deterministic: a.deterministicTier,
    research_preview: a.researchTier,
    independently_validated: a.validatedTier,
    non_evaluable: a.nonEvaluableTier,
  }[tier];
}

function EvidenceState({
  locale,
  tier,
  status,
  reasons = [],
}: {
  locale: Locale;
  tier: EvidenceTier;
  status: string;
  reasons?: string[];
}) {
  const a = analysisCatalog[locale];
  return (
    <div className="mt-4 border-l-4 border-neon pl-4 text-xs">
      <div className="flex flex-wrap gap-2">
        <StatusBadge tone={tier === "research_preview" ? "fixture" : "neutral"}>
          {a.evidenceTier}: {evidenceTierLabel(tier, locale)}
        </StatusBadge>
        <StatusBadge>
          {a.evaluability}: {signalStatusLabel(status, locale)}
        </StatusBadge>
      </div>
      {reasons.length ? (
        <div className="mt-3">
          <p className="font-bold uppercase">{a.reasons}</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">
            {reasons.map((reason) => (
              <li key={reason}>{sentenceCode(reason, locale)}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function safeHttpUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function CoverageTable({
  locale,
  coverage,
  caption,
}: {
  locale: Locale;
  coverage: AnalysisSummary["missingness"];
  caption: string;
}) {
  const c = copy[locale];
  const rows = [
    [c.expected, coverage.expected],
    [c.retrieved, coverage.retrieved],
    [c.parsed, coverage.parsed],
    [c.missing, coverage.missing],
    [c.ambiguous, coverage.ambiguous],
    [c.excluded, coverage.excluded],
  ] as const;
  return (
    <div className="overflow-x-auto border border-ink" tabIndex={0}>
      <table className="w-full min-w-[34rem] border-collapse text-left text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-ink text-paper">
          <tr>
            {rows.map(([label]) => (
              <th
                className="border-r border-[#9B9B9B] p-3 last:border-r-0"
                key={label}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {rows.map(([label, value]) => (
              <td
                className="border-r border-ink p-3 font-display text-2xl font-bold tabular-nums last:border-r-0"
                key={label}
              >
                {formatNumber(value, locale)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function ResearchGate({
  locale,
  reasons,
}: {
  locale: Locale;
  reasons: string[];
}) {
  const c = copy[locale];
  return (
    <section
      className="border border-ink bg-neon p-5 text-ink sm:p-6"
      role="status"
    >
      <div className="flex items-start gap-3">
        <FlaskConical className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <div>
          <h2 className="font-display text-xl font-bold leading-tight uppercase">
            {c.researchTitle}
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6">{c.researchBody}</p>
          {reasons.length ? (
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm">
              {reasons.map((reason) => (
                <li key={reason}>{readableCode(reason, locale)}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function ReleaseRail({
  locale,
  selected,
  summary,
  analysisRelease,
}: {
  locale: Locale;
  selected: PublicReleaseRef;
  summary: Pick<AnalysisSummary, "data_version" | "methodology_version">;
  analysisRelease: AnalysisReleaseMetadata;
}) {
  const c = copy[locale];
  const a = analysisCatalog[locale];
  return (
    <dl className="grid gap-px border border-ink bg-ink text-sm sm:grid-cols-2 lg:grid-cols-4">
      {[
        [c.release, selected.release_id],
        [c.election, selected.election_slug],
        [a.analysisRelease, analysisRelease.analysis_release_id],
        [c.methodology, summary.methodology_version],
        [a.canonicalInput, analysisRelease.canonical_input_hash],
        [a.manifest, analysisRelease.manifest_hash],
        [a.provenance, analysisRelease.provenance_hash],
        [
          analysisRelease.exposure_tier === "preliminary_research"
            ? a.preliminary
            : a.certified,
          `${a.generated}: ${formatDate(analysisRelease.generated_at, locale)} · ${a.approved}: ${formatDate(analysisRelease.approved_at, locale)}`,
        ],
      ].map(([label, value]) => (
        <div className="min-w-0 bg-paper p-4" key={label}>
          <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
            {label}
          </dt>
          <dd className="mt-1 break-all font-mono text-xs">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function PlainConclusion({
  locale,
  summary,
}: {
  locale: Locale;
  summary: AnalysisSummary;
}) {
  const c = copy[locale];
  const evaluated = signalDisplay(summary.total_records_evaluated, locale);
  const anomalies = signalDisplay(summary.anomaly_count, locale);
  let answer: string = c.countUnavailable;
  if (summary.research_preview || summary.ineligible_reasons.length) {
    answer = c.noPublicConclusion;
  } else if (
    summary.anomaly_count.status === "observed" &&
    summary.anomaly_count.value !== null &&
    summary.total_records_evaluated.status === "observed" &&
    summary.total_records_evaluated.value !== null
  ) {
    answer =
      summary.anomaly_count.value === 0
        ? c.noRecordsMet(evaluated)
        : c.recordsMet(anomalies, evaluated);
  }
  return (
    <section className="grid border-x border-b border-ink lg:grid-cols-12">
      <div className="px-4 py-8 sm:px-6 lg:col-span-8 lg:px-8">
        <p className="font-mono text-[11px] font-bold tracking-[.12em] text-muted uppercase">
          01 / {c.plainAnswer}
        </p>
        <h2 className="mt-3 max-w-3xl font-display text-2xl font-bold leading-tight uppercase sm:text-4xl">
          {answer}
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">
          {c.doesNotMean}
        </p>
      </div>
      <dl className="grid border-t border-ink bg-ink text-paper sm:grid-cols-2 lg:col-span-4 lg:grid-cols-1 lg:border-t-0 lg:border-l">
        <div className="p-5 sm:p-6">
          <dt className="text-xs text-[#9B9B9B]">{c.evaluated}</dt>
          <dd className="mt-2 font-display text-4xl font-bold tabular-nums">
            {evaluated}
          </dd>
          <dd className="mt-1 font-mono text-[11px] text-[#9B9B9B] uppercase">
            {signalStatusLabel(summary.total_records_evaluated.status, locale)}
          </dd>
        </div>
        <div className="border-t border-[#9B9B9B] p-5 sm:p-6">
          <dt className="text-xs text-[#9B9B9B]">{c.qualifying}</dt>
          <dd className="mt-2 font-display text-4xl font-bold tabular-nums">
            {anomalies}
          </dd>
          <dd className="mt-1 font-mono text-[11px] text-[#9B9B9B] uppercase">
            {signalStatusLabel(summary.anomaly_count.status, locale)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function AnomalyCard({
  locale,
  anomaly,
  selected,
}: {
  locale: Locale;
  anomaly: AnalysisAnomaly;
  selected: PublicReleaseRef;
}) {
  const c = copy[locale];
  const primary = anomaly.components[0];
  const detailQuery = scopedQuery(
    selected,
    {},
    anomaly.analysis_release.analysis_release_id,
  );
  const resultQuery = scopedQuery(
    selected,
    {},
    anomaly.analysis_release.analysis_release_id,
  );
  return (
    <li className="border-b border-ink py-6 last:border-b-0">
      <article>
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_12rem]">
          <div className="min-w-0">
            <div className="flex flex-wrap gap-2">
              <StatusBadge
                tone={anomaly.research_preview ? "fixture" : "neutral"}
              >
                {anomaly.research_preview
                  ? c.researchCandidate
                  : anomaly.is_anomaly
                    ? c.detected
                    : c.notDetected}
              </StatusBadge>
              {anomaly.anomaly_types.map((type) => (
                <StatusBadge key={type}>
                  {anomalyTypeLabels[type][locale]}
                </StatusBadge>
              ))}
            </div>
            <p className="mt-4 font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
              {c.mesa} · {anomaly.mesa_id}
            </p>
            <h3 className="mt-2 break-words font-display text-2xl font-bold leading-tight uppercase">
              {explanationLabels[anomaly.explanation.status]?.[locale] ??
                anomaly.explanation.status}
            </h3>
            <EvidenceState
              locale={locale}
              tier={anomaly.evidence_tier}
              status={anomaly.evaluability}
              reasons={anomaly.ineligible_reasons}
            />
            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-bold">{c.observed}</dt>
                <dd className="mt-1 text-muted">
                  {primary
                    ? nullableNumber(primary.observed_value, locale)
                    : c.unavailable}
                </dd>
              </div>
              <div>
                <dt className="font-bold">{c.comparator}</dt>
                <dd className="mt-1 break-words text-muted">
                  {primary?.comparator || c.unavailable}
                </dd>
              </div>
            </dl>
          </div>
          <div className="border border-ink bg-ink p-5 text-paper lg:text-right">
            <p className="font-display text-5xl font-bold tabular-nums">
              {anomaly.audit_priority_score}
              <span className="text-base">/100</span>
            </p>
            <p className="mt-2 text-xs text-[#9B9B9B]">{c.priority}</p>
            <p className="mt-4 text-xs leading-5 text-[#9B9B9B]">
              {reviewDisclosure[locale]}
            </p>
          </div>
        </div>
        <p className="mt-5 border border-ink p-4 text-sm leading-6">
          {anomaly.disclosure[locale]}
        </p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Link
            className="inline-flex min-h-11 items-center justify-center gap-2 border border-ink bg-ink px-4 font-mono text-xs font-bold uppercase text-paper hover:bg-neon hover:text-ink"
            href={`/${locale}/analitica/anomalias/${encodeURIComponent(anomaly.id)}?${detailQuery}`}
          >
            {c.details} <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center gap-2 border border-ink px-4 font-mono text-xs font-bold uppercase hover:bg-neon"
            href={`/${locale}/resultados/mesa/${encodeURIComponent(anomaly.mesa_id)}?${resultQuery}`}
          >
            {c.result}
          </Link>
        </div>
      </article>
    </li>
  );
}

function ExpertReport({
  locale,
  report,
}: {
  locale: Locale;
  report: AnalysisReport;
}) {
  const c = copy[locale];
  const metrics = Object.entries(report.metrics);
  return (
    <details className="group border-b border-ink last:border-b-0">
      <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 py-4 font-bold after:text-xl after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
        <span>
          {reportLabels[report.report_kind][locale]} ·{" "}
          {reportStatusLabels[report.status]?.[locale] ?? report.status}
        </span>
      </summary>
      <div className="pb-6">
        <EvidenceState
          locale={locale}
          tier={
            report.status === "not_evaluable" || report.status === "ineligible"
              ? "non_evaluable"
              : report.research_preview
                ? "research_preview"
                : "independently_validated"
          }
          status={report.status}
          reasons={report.ineligible_reasons}
        />
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-bold">{c.methodology}</dt>
            <dd className="mt-1 break-all font-mono text-xs text-muted">
              {report.methodology_version}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.artifact}</dt>
            <dd className="mt-1 break-all font-mono text-xs text-muted">
              {report.artifact_hash ?? c.unavailable}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.reportStatus}</dt>
            <dd className="mt-1 text-muted">
              {reportStatusLabels[report.status]?.[locale] ?? report.status}
            </dd>
          </div>
        </dl>
        {metrics.length ? (
          <div className="mt-5 overflow-x-auto border border-ink" tabIndex={0}>
            <table className="w-full min-w-[30rem] border-collapse text-left text-sm">
              <caption className="sr-only">
                {reportLabels[report.report_kind][locale]}
              </caption>
              <thead className="bg-ink text-paper">
                <tr>
                  <th className="p-3">{c.metric}</th>
                  <th className="p-3">{c.value}</th>
                  <th className="p-3">{c.status}</th>
                </tr>
              </thead>
              <tbody>
                {metrics.map(([name, metric]) => (
                  <tr className="border-t border-ink" key={name}>
                    <th className="p-3 font-mono text-xs">{name}</th>
                    <td className="p-3 tabular-nums">
                      {signalDisplay(metric, locale)}
                    </td>
                    <td className="p-3">
                      {signalStatusLabel(metric.status, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-5 border border-ink p-4 text-sm">{c.noMetrics}</p>
        )}
        <div className="mt-5">
          <CoverageTable
            locale={locale}
            coverage={report.missingness}
            caption={`${c.missingness}: ${reportLabels[report.report_kind][locale]}`}
          />
        </div>
        <p className="mt-5 text-sm leading-6 text-muted">
          {report.disclosure[locale]}
        </p>
      </div>
    </details>
  );
}

function ExpectedEvidence({
  locale,
  title,
  intro,
  tier,
  status,
  reasons,
  children,
}: {
  locale: Locale;
  title: string;
  intro: string;
  tier: EvidenceTier;
  status: string;
  reasons: string[];
  children?: React.ReactNode;
}) {
  return (
    <section className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8">
      <h2 className="font-display text-2xl font-bold uppercase sm:text-3xl">
        {title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">{intro}</p>
      <EvidenceState
        locale={locale}
        tier={tier}
        status={status}
        reasons={reasons}
      />
      {children}
    </section>
  );
}

function ArtifactDownloads({
  locale,
  artifacts,
  selected,
  analysisRelease,
}: {
  locale: Locale;
  artifacts: AnalysisArtifactMetadata[];
  selected: PublicReleaseRef;
  analysisRelease: AnalysisReleaseMetadata;
}) {
  const a = analysisCatalog[locale];
  return (
    <div className="mt-8">
      <h3 className="font-display text-xl font-bold uppercase">
        {a.downloads}
      </h3>
      {artifacts.length ? (
        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {artifacts.map((artifact) => {
            const href = analysisArtifactDownloadUrl(
              selected,
              analysisRelease,
              artifact,
            );
            return (
              <li
                className="min-w-0 border border-ink p-4"
                key={artifact.artifact_id}
              >
                <p className="break-words font-bold">{artifact.kind}</p>
                <p className="mt-1 break-all font-mono text-[11px] text-muted">
                  {artifact.byte_hash}
                </p>
                <EvidenceState
                  locale={locale}
                  tier={
                    artifact.status === "available"
                      ? "descriptive"
                      : "non_evaluable"
                  }
                  status={artifact.status}
                  reasons={artifact.status_reasons}
                />
                {href ? (
                  <a
                    className="mt-4 inline-flex min-h-11 max-w-full items-center gap-2 break-words border border-ink px-4 font-mono text-xs font-bold uppercase hover:bg-neon"
                    href={href}
                  >
                    {a.download}{" "}
                    <ExternalLink
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-4 border border-ink p-4 text-sm">
          {a.artifactUnavailable}
        </p>
      )}
    </div>
  );
}

export function AnalysisWorkspace({
  locale,
  analysis,
}: {
  locale: Locale;
  analysis: PublicAnalysisReady;
}) {
  const c = copy[locale];
  const a = analysisCatalog[locale];
  const { selected, summary, anomalies } = analysis;
  const peerAnomalies = anomalies.items.filter((item) =>
    item.anomaly_types.includes("peer_distribution"),
  );
  const spatialAnomalies = anomalies.items.filter((item) =>
    item.anomaly_types.includes("spatial"),
  );
  const resetQuery = scopedQuery(
    selected,
    {},
    analysis.analysisRelease.analysis_release_id,
  );
  const nextQuery = scopedQuery(
    selected,
    {
      tipo: analysis.filters.anomalyType,
      cursor: anomalies.page.next_cursor,
    },
    analysis.analysisRelease.analysis_release_id,
  );
  const contextValue = (release: PublicReleaseRef) => {
    const value = new URLSearchParams({
      release: release.release_id,
      election: release.election_slug,
    });
    if (
      release.release_id === selected.release_id &&
      release.election_slug === selected.election_slug
    ) {
      value.set(
        "analysis_release",
        analysis.analysisRelease.analysis_release_id,
      );
    }
    return value.toString();
  };
  return (
    <Page
      locale={locale}
      eyebrow={c.eyebrow}
      title={c.title}
      synthetic={false}
      releaseStatus={selected.status}
    >
      <p className="max-w-3xl text-base leading-7 text-muted">{c.intro}</p>
      <div className="mt-6">
        <ReleaseRail
          locale={locale}
          selected={selected}
          summary={summary}
          analysisRelease={analysis.analysisRelease}
        />
      </div>
      {summary.research_preview || summary.ineligible_reasons.length ? (
        <div className="mt-6">
          <ResearchGate locale={locale} reasons={summary.ineligible_reasons} />
        </div>
      ) : null}
      {analysis.analysisRelease.preliminary_caveat ? (
        <p
          className="mt-6 border border-ink bg-neon p-4 text-sm leading-6"
          role="status"
        >
          {analysis.analysisRelease.preliminary_caveat[locale]}
        </p>
      ) : null}
      <div className="mt-6">
        <PlainConclusion locale={locale} summary={summary} />
      </div>
      <p className="border-x border-b border-ink p-4 text-sm leading-6 sm:p-6">
        {summary.disclosure[locale]}
      </p>

      <section
        className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8"
        aria-labelledby="analysis-coverage"
      >
        <h2
          id="analysis-coverage"
          className="mt-3 font-display text-2xl font-bold uppercase sm:text-3xl"
        >
          {a.releaseStatus}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          {c.coverageIntro}
        </p>
        <div className="mt-6">
          <CoverageTable
            locale={locale}
            coverage={summary.missingness}
            caption={c.coverage}
          />
        </div>
        <EvidenceState
          locale={locale}
          tier="descriptive"
          status={analysis.analysisRelease.artifact_status}
          reasons={analysis.analysisRelease.status_reasons}
        />
      </section>

      <section className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8">
        <h2 className="font-display text-2xl font-bold uppercase sm:text-3xl">
          {a.descriptive}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          {a.descriptiveIntro}
        </p>
        <h3 className="mt-7 font-bold">{c.qualifyingByRule}</h3>
        <dl className="mt-3 grid gap-px border border-ink bg-ink sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(summary.anomaly_counts).map(([type, count]) => (
            <div className="min-w-0 bg-paper p-4" key={type}>
              <dt className="text-xs leading-5 text-muted">
                {anomalyTypeLabels[type as AnalysisAnomalyType]?.[locale] ??
                  type}
              </dt>
              <dd className="mt-3 font-display text-3xl font-bold tabular-nums">
                {signalDisplay(count, locale)}
              </dd>
              <dd className="mt-1 font-mono text-[10px] text-muted uppercase">
                {signalStatusLabel(count.status, locale)}
              </dd>
            </div>
          ))}
        </dl>
        <EvidenceState locale={locale} tier="descriptive" status="available" />
      </section>

      <section
        className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8"
        aria-labelledby="analysis-explorer"
      >
        <h2
          id="analysis-explorer"
          className="mt-3 font-display text-2xl font-bold uppercase sm:text-3xl"
        >
          {a.deterministic}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          {a.deterministicIntro} {c.explorerIntro}
        </p>
        <form
          className="mt-6 grid gap-4 border-y border-ink py-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_auto] lg:items-end"
          aria-label={c.explorer}
        >
          <label className="grid gap-2 font-mono text-[11px] font-bold uppercase">
            {a.context}
            <select
              className="min-h-11 min-w-0 border border-ink bg-paper px-3 text-sm font-normal normal-case"
              name="context"
              defaultValue={contextValue(selected)}
            >
              {analysis.releases.map((release) => (
                <option
                  value={contextValue(release)}
                  key={`${release.release_id}:${release.election_slug}`}
                >
                  {locale === "es" ? release.name_es : release.name_en} ·{" "}
                  {release.release_id}
                  {release.release_id === selected.release_id
                    ? ` · ${analysis.analysisRelease.analysis_release_id}`
                    : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-2 font-mono text-[11px] font-bold uppercase">
            {c.anomalyType}
            <select
              className="min-h-11 min-w-0 border border-ink bg-paper px-3 text-sm font-normal normal-case"
              name="tipo"
              defaultValue={analysis.filters.anomalyType ?? ""}
            >
              <option value="">{c.allTypes}</option>
              {Object.entries(anomalyTypeLabels).map(([type, labels]) => (
                <option value={type} key={type}>
                  {labels[locale]}
                </option>
              ))}
            </select>
          </label>
          <button
            className="inline-flex min-h-11 items-center justify-center gap-2 border border-ink bg-ink px-4 font-mono text-xs font-bold uppercase text-paper hover:bg-neon hover:text-ink"
            type="submit"
          >
            <Search className="size-4" aria-hidden="true" /> {c.apply}
          </button>
        </form>
        {analysis.filters.anomalyType ? (
          <Link
            className="mt-4 inline-flex min-h-11 items-center underline underline-offset-4"
            href={`/${locale}/analitica?${resetQuery}`}
          >
            {c.reset}
          </Link>
        ) : null}
        {anomalies.items.length ? (
          <ol className="mt-4 border-t border-ink">
            {anomalies.items.map((anomaly) => (
              <AnomalyCard
                locale={locale}
                anomaly={anomaly}
                selected={selected}
                key={anomaly.id}
              />
            ))}
          </ol>
        ) : (
          <div className="mt-6 border border-ink p-5" role="status">
            <p className="font-bold">{c.empty}</p>
            <p className="mt-2 text-sm leading-6 text-muted">{c.emptyCaveat}</p>
          </div>
        )}
        <nav
          className="mt-6 flex flex-col gap-3 border-t border-ink pt-5 sm:flex-row sm:items-center sm:justify-between"
          aria-label={c.explorer}
        >
          <p className="text-sm text-muted">
            {anomalies.page.has_more ? c.explorerIntro : c.end}
          </p>
          {anomalies.page.has_more && anomalies.page.next_cursor ? (
            <Link
              className="inline-flex min-h-11 items-center justify-center gap-2 border border-ink px-4 font-mono text-xs font-bold uppercase hover:bg-neon"
              href={`/${locale}/analitica?${nextQuery}`}
            >
              {c.next} <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          ) : null}
        </nav>
      </section>

      <ExpectedEvidence
        locale={locale}
        title={a.peer}
        intro={a.peerIntro}
        tier="research_preview"
        status={peerAnomalies.length ? "evaluable" : "not_evaluable"}
        reasons={
          peerAnomalies.length
            ? peerAnomalies.flatMap((item) => item.ineligible_reasons)
            : ["peer_results_not_published"]
        }
      >
        {!peerAnomalies.length ? (
          <p className="mt-5 text-sm">{a.noPeer}</p>
        ) : null}
      </ExpectedEvidence>

      <ExpectedEvidence
        locale={locale}
        title={a.spatial}
        intro={a.spatialIntro}
        tier={spatialAnomalies.length ? "research_preview" : "non_evaluable"}
        status={spatialAnomalies.length ? "evaluable" : "not_evaluable"}
        reasons={
          spatialAnomalies.length
            ? spatialAnomalies.flatMap((item) => item.ineligible_reasons)
            : ["authenticated_coordinates_not_available"]
        }
      >
        {!spatialAnomalies.length ? (
          <p className="mt-5 text-sm">{a.noSpatial}</p>
        ) : null}
      </ExpectedEvidence>

      <ExpectedEvidence
        locale={locale}
        title={a.outcome}
        intro={a.outcomeIntro}
        tier={
          analysis.outcomeSensitivity.status === "available" &&
          analysis.outcomeSensitivity.value.evaluable
            ? "independently_validated"
            : "non_evaluable"
        }
        status={
          analysis.outcomeSensitivity.status === "available" &&
          analysis.outcomeSensitivity.value.evaluable
            ? "evaluable"
            : "not_evaluable"
        }
        reasons={
          analysis.outcomeSensitivity.status === "available"
            ? analysis.outcomeSensitivity.value.issues.map(
                (issue) => issue.code,
              )
            : [analysis.outcomeSensitivity.reason]
        }
      >
        <div className="mt-6">
          <OutcomeSensitivityPanel
            locale={locale}
            outcome={
              analysis.outcomeSensitivity.status === "available"
                ? analysis.outcomeSensitivity.value
                : null
            }
          />
        </div>
      </ExpectedEvidence>

      <section className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8">
        <h2 className="font-display text-2xl font-bold uppercase sm:text-3xl">
          {a.expert}
        </h2>
        <p className="mt-3 text-sm leading-6 text-muted">{a.expertIntro}</p>
        <div className="mt-6 border-t border-ink">
          {Object.entries(analysis.reports).map(([kind, resource]) =>
            resource.status === "available" ? (
              <ExpertReport
                locale={locale}
                report={resource.value}
                key={kind}
              />
            ) : (
              <div className="border-b border-ink py-5" key={kind}>
                <p className="font-bold">
                  {reportLabels[kind as AnalysisReportKind][locale]}
                </p>
                <p className="mt-2 text-sm text-muted">{a.reportUnavailable}</p>
                <EvidenceState
                  locale={locale}
                  tier="non_evaluable"
                  status="unavailable"
                  reasons={[resource.reason]}
                />
              </div>
            ),
          )}
        </div>
        <ArtifactDownloads
          locale={locale}
          artifacts={
            analysis.artifacts.status === "available"
              ? analysis.artifacts.value
              : []
          }
          selected={selected}
          analysisRelease={analysis.analysisRelease}
        />
        {analysis.artifacts.status === "unavailable" ? (
          <EvidenceState
            locale={locale}
            tier="non_evaluable"
            status="unavailable"
            reasons={[analysis.artifacts.reason]}
          />
        ) : null}
      </section>

      <section className="border-x border-b border-ink bg-ink p-5 text-paper sm:p-7">
        <p className="text-sm leading-6">{summary.disclosure[locale]}</p>
        <dl className="mt-5 grid gap-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-[#9B9B9B]">{c.source}</dt>
            <dd className="mt-1">
              {sourceTypeLabel(locale, summary.provenance.source_type)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.legal}</dt>
            <dd className="mt-1">
              {legalStatusLabel(locale, summary.provenance.legal_status)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.retrievedAt}</dt>
            <dd className="mt-1">
              {formatDate(summary.provenance.retrieved_at, locale)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.hash}</dt>
            <dd className="mt-1 break-all font-mono">
              {summary.provenance.content_hash}
            </dd>
          </div>
        </dl>
      </section>
    </Page>
  );
}

export function AnalysisUnavailable({
  locale,
  status,
  selected,
  message,
}: {
  locale: Locale;
  status: "no_release" | "unavailable" | "error" | "fixture" | "not_found";
  selected?: PublicReleaseRef;
  message?: string;
}) {
  const es = locale === "es";
  const sourceStatus = selected?.status ?? "candidate";
  const title =
    status === "not_found"
      ? es
        ? "Análisis no encontrado"
        : "Analysis not found"
      : status === "no_release"
        ? es
          ? "No hay un release analítico público"
          : "No public analytical release is available"
        : status === "fixture"
          ? es
            ? "Análisis real no publicado"
            : "Real analysis is not published"
          : sourceStatus === "published"
            ? es
              ? "El análisis publicado no está disponible"
              : "The published analysis is unavailable"
            : es
              ? "El análisis preliminar no está disponible"
              : "The preliminary analysis is unavailable";
  return (
    <Page
      locale={locale}
      eyebrow={es ? "Estado del análisis" : "Analysis status"}
      title={title}
      synthetic={status === "fixture"}
      releaseStatus={sourceStatus}
    >
      <section className="border border-ink p-5 sm:p-7" role="alert">
        <p className="max-w-3xl text-sm leading-6">
          {es
            ? "No se sustituyen recursos ausentes por datos de muestra ni por ceros. Revise la conexión o seleccione un release público compatible."
            : "Missing resources are not replaced with sample data or zeros. Check the connection or select a compatible public release."}
        </p>
        {message ? (
          <details className="group mt-5 border-t border-ink pt-2">
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 font-mono text-xs font-bold uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
              {es ? "Detalle técnico" : "Technical detail"}
            </summary>
            <p className="break-words text-sm text-muted">{message}</p>
          </details>
        ) : null}
      </section>
    </Page>
  );
}

function ComponentEvidence({
  locale,
  component,
  index,
}: {
  locale: Locale;
  component: SignalComponent;
  index: number;
}) {
  const c = copy[locale];
  const analysis = component.analysis;
  const eligibility = analysis.eligibility;
  const reason = analysis.reason;
  const sources = component.source_links.flatMap((source) => {
    const href = safeHttpUrl(source);
    return href ? [{ source, href }] : [];
  });
  const replayEntries = Object.entries(component).filter(
    ([key, value]) =>
      value !== null &&
      ![
        "component_type",
        "points",
        "observed_value",
        "comparator",
        "calculation",
        "peer_definition",
        "limitations",
        "source_links",
        "analysis",
      ].includes(key),
  );
  return (
    <article className="border-t border-ink py-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="font-mono text-[11px] font-bold text-muted uppercase">
            {String(index + 1).padStart(2, "0")}
          </p>
          <h3 className="mt-2 font-display text-xl font-bold uppercase">
            {componentLabels[component.component_type][locale]}
          </h3>
        </div>
        <StatusBadge tone={eligibility === "eligible" ? "success" : "neutral"}>
          {c.eligibility}: {signalStatusLabel(eligibility, locale)}
        </StatusBadge>
      </div>
      {reason ? (
        <p className="mt-3 text-sm text-muted">
          {readableCode(reason, locale)}
        </p>
      ) : null}
      <dl className="mt-5 grid gap-px border border-ink bg-ink text-sm sm:grid-cols-2">
        <div className="bg-paper p-4">
          <dt className="font-bold">{c.observed}</dt>
          <dd className="mt-2 text-muted">
            {nullableNumber(component.observed_value, locale)}
          </dd>
        </div>
        <div className="bg-paper p-4">
          <dt className="font-bold">{c.comparator}</dt>
          <dd className="mt-2 break-words text-muted">
            {component.comparator || c.unavailable}
          </dd>
        </div>
      </dl>
      <div className="mt-5 grid gap-5 text-sm lg:grid-cols-2">
        <div>
          <h4 className="font-bold">{c.calculation}</h4>
          <p className="mt-2 leading-6 text-muted">
            {component.calculation || c.unavailable}
          </p>
        </div>
        <div>
          <h4 className="font-bold">{c.peerDefinition}</h4>
          <p className="mt-2 leading-6 text-muted">
            {component.peer_definition ?? c.notApplicable}
          </p>
        </div>
        <div>
          <h4 className="font-bold">{c.limitations}</h4>
          <p className="mt-2 leading-6 text-muted">
            {component.limitations[locale]}
          </p>
        </div>
        <div>
          <h4 className="font-bold">{c.sources}</h4>
          {sources.length ? (
            <ul className="mt-2 space-y-2">
              {sources.map(({ source, href }) => (
                <li key={source}>
                  <a
                    className="inline-flex min-h-11 items-center gap-2 break-all underline underline-offset-4"
                    href={href}
                    rel="noreferrer"
                  >
                    <ExternalLink
                      className="size-4 shrink-0"
                      aria-hidden="true"
                    />
                    {source}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-muted">{c.noSources}</p>
          )}
        </div>
      </div>
      <details className="group mt-5 border-t border-ink pt-2">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 font-mono text-xs font-bold uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
          {c.replay}
        </summary>
        <dl className="grid gap-3 pb-3 text-xs sm:grid-cols-2">
          {replayEntries.length ? (
            replayEntries.map(([key, value]) => (
              <div className="min-w-0 border border-line p-3" key={key}>
                <dt className="font-bold">{key}</dt>
                <dd className="mt-1 break-all font-mono text-muted">
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </dd>
              </div>
            ))
          ) : (
            <div>{c.unavailable}</div>
          )}
          <div className="min-w-0 border border-line p-3 sm:col-span-2">
            <dt className="font-bold">analysis</dt>
            <dd className="mt-1 break-all font-mono text-muted">
              {JSON.stringify(analysis)}
            </dd>
          </div>
        </dl>
      </details>
    </article>
  );
}

export function AnalysisAnomalyDetail({
  locale,
  state,
}: {
  locale: Locale;
  state: Extract<PublicAnomalyDetailState, { status: "ready" }>;
}) {
  const c = copy[locale];
  const { anomaly, selected } = state;
  const query = scopedQuery(
    selected,
    {},
    anomaly.analysis_release.analysis_release_id,
  );
  const notes = anomaly.explanation.notes?.[locale];
  return (
    <Page
      locale={locale}
      eyebrow={c.eyebrow}
      title={`${c.anomalyTitle} · ${anomaly.mesa_id}`}
      synthetic={false}
      releaseStatus={selected.status}
    >
      <nav aria-label={c.back}>
        <Link
          className="inline-flex min-h-11 items-center underline underline-offset-4"
          href={`/${locale}/analitica?${query}`}
        >
          {c.back}
        </Link>
      </nav>
      {anomaly.research_preview || anomaly.ineligible_reasons.length ? (
        <ResearchGate locale={locale} reasons={anomaly.ineligible_reasons} />
      ) : null}
      <div className="mt-6">
        <ReleaseRail
          locale={locale}
          selected={selected}
          summary={{
            data_version: anomaly.provenance.data_version,
            methodology_version: anomaly.methodology_version,
          }}
          analysisRelease={anomaly.analysis_release}
        />
      </div>
      <section className="mt-6 grid border border-ink lg:grid-cols-12">
        <div className="p-5 sm:p-7 lg:col-span-8">
          <div className="flex flex-wrap gap-2">
            <StatusBadge
              tone={anomaly.research_preview ? "fixture" : "neutral"}
            >
              {anomaly.research_preview
                ? c.researchCandidate
                : anomaly.is_anomaly
                  ? c.detected
                  : c.notDetected}
            </StatusBadge>
            {anomaly.anomaly_types.map((type) => (
              <StatusBadge key={type}>
                {anomalyTypeLabels[type][locale]}
              </StatusBadge>
            ))}
          </div>
          <h2 className="mt-5 font-display text-2xl font-bold uppercase sm:text-4xl">
            {explanationLabels[anomaly.explanation.status]?.[locale] ??
              anomaly.explanation.status}
          </h2>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">
            {c.explanationMeaning}
          </p>
          <EvidenceState
            locale={locale}
            tier={anomaly.evidence_tier}
            status={anomaly.evaluability}
            reasons={anomaly.ineligible_reasons}
          />
        </div>
        <aside className="border-t border-ink bg-ink p-5 text-paper sm:p-7 lg:col-span-4 lg:border-t-0 lg:border-l">
          <p className="font-display text-5xl font-bold tabular-nums">
            {anomaly.audit_priority_score}
            <span className="text-base">/100</span>
          </p>
          <p className="mt-2 text-xs text-[#9B9B9B]">{c.priority}</p>
          <p className="mt-5 text-xs leading-5 text-[#9B9B9B]">
            {reviewDisclosure[locale]}
          </p>
        </aside>
      </section>
      <p className="border-x border-b border-ink p-5 text-sm leading-6 sm:p-6">
        {anomaly.disclosure[locale]}
      </p>

      <section
        className="border-x border-b border-ink p-5 sm:p-7"
        aria-labelledby="explanation-review"
      >
        <h2
          id="explanation-review"
          className="font-display text-2xl font-bold uppercase"
        >
          {c.explanationReview}
        </h2>
        <dl className="mt-6 grid gap-5 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="font-bold">{c.explanation}</dt>
            <dd className="mt-1 text-muted">
              {explanationLabels[anomaly.explanation.status]?.[locale] ??
                anomaly.explanation.status}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.effect}</dt>
            <dd className="mt-1 text-muted">
              {signalDisplay(anomaly.explanation.quantitative_effect, locale)}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.pValue}</dt>
            <dd className="mt-1 text-muted">
              {signalDisplay(anomaly.explanation.quantitative_p_value, locale)}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.reviewedAt}</dt>
            <dd className="mt-1 text-muted">
              {anomaly.explanation.reviewed_at
                ? formatDate(anomaly.explanation.reviewed_at, locale)
                : c.unavailable}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.preregistration}</dt>
            <dd className="mt-1 break-all font-mono text-xs text-muted">
              {anomaly.explanation.preregistration_hash ?? c.unavailable}
            </dd>
          </div>
          <div>
            <dt className="font-bold">{c.availableData}</dt>
            <dd className="mt-1 break-all font-mono text-xs text-muted">
              {anomaly.explanation.available_data_hash ?? c.unavailable}
            </dd>
          </div>
        </dl>
        <p className="mt-5 border-l-4 border-neon pl-4 text-sm leading-6">
          {notes || c.noNotes}
        </p>
      </section>

      <section
        className="border-x border-b border-ink p-5 sm:p-7"
        aria-labelledby="ballot-edits"
      >
        <h2
          id="ballot-edits"
          className="font-display text-2xl font-bold uppercase"
        >
          {c.ballotEdits}
        </h2>
        <p className="mt-3 text-sm leading-6 text-muted">
          {c.ballotEditsMeaning}
        </p>
        <p className="mt-5 font-display text-4xl font-bold tabular-nums">
          {signalDisplay(anomaly.minimum_ballot_edits, locale)}
        </p>
        <p className="mt-2 font-mono text-xs uppercase text-muted">
          {signalStatusLabel(anomaly.minimum_ballot_edits_status, locale)}
        </p>
        {anomaly.minimum_ballot_edits_reason ? (
          <p className="mt-4 text-sm text-muted">
            {readableCode(anomaly.minimum_ballot_edits_reason, locale)}
          </p>
        ) : null}
      </section>

      <section
        className="border-x border-b border-ink p-5 sm:p-7"
        aria-labelledby="anomaly-components"
      >
        <h2
          id="anomaly-components"
          className="font-display text-2xl font-bold uppercase"
        >
          {c.components}
        </h2>
        <div className="mt-5">
          {anomaly.components.map((component, index) => (
            <ComponentEvidence
              locale={locale}
              component={component}
              index={index}
              key={`${component.component_type}-${index}`}
            />
          ))}
        </div>
      </section>

      <section className="border-x border-b border-ink bg-ink p-5 text-paper sm:p-7">
        <p className="text-sm leading-6">{anomaly.disclosure[locale]}</p>
        <dl className="mt-5 grid gap-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-[#9B9B9B]">{c.source}</dt>
            <dd className="mt-1">
              {sourceTypeLabel(locale, anomaly.provenance.source_type)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.legal}</dt>
            <dd className="mt-1">
              {legalStatusLabel(locale, anomaly.provenance.legal_status)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.retrievedAt}</dt>
            <dd className="mt-1">
              {formatDate(anomaly.provenance.retrieved_at, locale)}
            </dd>
          </div>
          <div>
            <dt className="text-[#9B9B9B]">{c.hash}</dt>
            <dd className="mt-1 break-all font-mono">
              {anomaly.provenance.content_hash}
            </dd>
          </div>
        </dl>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row">
          <Link
            className="inline-flex min-h-11 items-center justify-center border border-neon bg-neon px-4 font-mono text-xs font-bold uppercase text-ink"
            href={`/${locale}/resultados/mesa/${encodeURIComponent(anomaly.mesa_id)}?${query}`}
          >
            {c.result}
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center border border-paper px-4 font-mono text-xs font-bold uppercase"
            href={`/${locale}/analitica?${query}`}
          >
            {c.back}
          </Link>
        </div>
      </section>
    </Page>
  );
}
