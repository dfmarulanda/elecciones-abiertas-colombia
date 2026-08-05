import type { components } from "@elecciones/contracts";
import {
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Database,
  FileSearch,
  Gauge,
} from "lucide-react";
import Link from "next/link";
import React from "react";

import { ReleaseNotice } from "@/components/page-primitives";
import { GeographicCoverageNotice } from "@/components/geographic-coverage-notice";
import {
  OutcomeSensitivityPanel,
  ReviewSignalDetails,
} from "@/components/investigation-details";
import { Dot, StatusBadge } from "@/components/ui";
import type { ReleaseView } from "@/data/fixture-adapter";
import { formatMetricValue, type MetricStatusLabels } from "@/lib/metric-value";
import { reviewDisclosure } from "@/lib/review-disclosure";
import {
  formatCompletionPercent,
  formatDate,
  formatNumber,
  formatPercent,
} from "@/lib/utils";

type Locale = "es" | "en";
type CandidateSummary = components["schemas"]["CandidateSummary"];

const copy = {
  es: {
    eyebrow: "Mesa nacional de análisis",
    title: "Portal de analítica electoral",
    intro:
      "Una lectura compacta de resultados, cobertura, conciliación y evidencia. Cada cifra conserva la versión y la condición jurídica de su fuente.",
    readingBoundary: "Alcance de esta lectura",
    nationalAggregate: "Agregado nacional",
    releaseStatus: "Estado de publicación",
    fixtureRelease: "Fijación sintética",
    candidateRelease: "Release candidato · preliminar",
    publishedRelease: "Publicado",
    withdrawnRelease: "Retirado",
    sourceLayer: "Capa de fuente",
    sourcePrecount: "Preconteo oficial",
    sourceFinal: "Declaración final del CNE",
    sourceScrutiny: "Escrutinio oficial publicado",
    legalStatus: "Condición jurídica",
    legalPreliminary: "Preconteo preliminar",
    legalFinal: "Final controlante",
    legalScrutiny: "Escrutinio oficial",
    dataVersion: "Versión de datos",
    electionDate: "Jornada electoral",
    nationalReading: "Lectura nacional",
    candidateLedger: "Distribución entre candidaturas",
    candidateNote:
      "Las barras comparan participación sobre votos válidos. Nombre y número de tarjeta identifican cada candidatura; el color no codifica identidad.",
    ballotNumber: "Tarjeta",
    votes: "votos",
    turnout: "Participación",
    turnoutContext: "Votantes sobre personas inscritas",
    completion: "Avance reportado",
    completionContext: "Mesas reportadas sobre esperadas",
    leadingMargin: "Diferencia entre las dos primeras",
    percentagePoint: "punto porcentual",
    percentagePoints: "puntos porcentuales",
    marginUnavailable: "No disponible con los valores observados",
    ballotComposition: "Composición del total votante",
    valid: "Votos válidos",
    blank: "Votos en blanco",
    null: "Votos nulos",
    unmarked: "Votos no marcados",
    publicationChain: "Cadena de publicación",
    publicationChainNote:
      "El dato avanza de registro esperado a objeto recuperado, registro interpretado y hecho conciliado. Un cero se muestra como cero; lo desconocido se nombra.",
    expected: "Esperadas",
    retrieved: "Recuperadas",
    parsed: "Interpretadas",
    missing: "Faltantes",
    ambiguous: "Ambiguas",
    excluded: "Excluidas",
    reconciliation: "Conciliación agregada",
    checkedFact: "hecho comprobado",
    checkedFacts: "hechos comprobados",
    exception: "excepción",
    exceptions: "excepciones",
    passed: "Superada",
    blocked: "Bloqueada",
    notRun: "No ejecutada",
    evidenceReading: "Qué puede concluir esta investigación",
    evidenceReadingNote:
      "La evidencia y los modelos responden preguntas distintas. El portal mantiene esas respuestas separadas.",
    documentaryEvidence: "Comprobación documental",
    documentaryEvidenceBody:
      "Puede confirmar fallas aritméticas, registros faltantes o duplicados y diferencias entre fuentes oficiales compatibles.",
    statisticalEvidence: "Señales estadísticas",
    statisticalEvidenceBody:
      "La demostración sintética puede mostrar señales experimentales. Las publicaciones reales permanecen no disponibles hasta validación independiente.",
    fraudConclusion: "Límite de la inferencia",
    fraudConclusionBody:
      "Las matemáticas detectan patrones inusuales y priorizan revisión documental. No establecen intención, fraude ni responsabilidad.",
    analysisDisclosure:
      "Este puntaje prioriza registros para revisión documental; no mide ni determina fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.",
    bulletinProgression: "Progresión de boletines",
    bulletinNote:
      "Cada barra representa el avance reportado en ese corte. La secuencia es descriptiva: no es una proyección, una tendencia ni una medida de certeza.",
    bulletin: "Boletín",
    mesa: "mesa",
    mesas: "mesas",
    noBulletins: "No hay boletines disponibles en esta versión.",
    reviewWindow: "Ventana de revisión cargada",
    reviewWindowNote:
      "Se muestran hasta tres puntajes altos de la página cargada por el API. Este bloque no afirma un conteo nacional de señales.",
    score: "Puntaje de prioridad de auditoría",
    affectedVotes: "Votos con base documental verificada",
    unavailable: "No disponible",
    moreSignals:
      "Hay más registros detrás del cursor; consulte la lista paginada completa.",
    noSignals: "No hay señales en la ventana cargada.",
    analysisUnavailable:
      "El análisis de señales no se ha publicado para esta versión. Una lista vacía no significa que no existan anomalías.",
    methodology: "Metodología",
    openReview: "Abrir revisión",
    provenance: "Trazabilidad de la lectura",
    retrievedAt: "Recuperado",
    hash: "Huella SHA-256",
    parser: "Analizador",
    transform: "Transformación",
    officialSource: "Abrir fuente oficial",
    fixtureSource: "URL demostrativa de la fijación",
    nextSteps: "Continuar la lectura",
    exploreResults: "Explorar resultados",
    inspectSources: "Revisar fuentes",
    reviewMethod: "Leer metodología",
    observed: "Observado",
    unknown: "Desconocido",
    notApplicable: "No aplica",
  },
  en: {
    eyebrow: "National analysis desk",
    title: "Election analytics portal",
    intro:
      "A compact reading of results, coverage, reconciliation, and evidence. Every figure retains its source version and legal status.",
    readingBoundary: "Scope of this reading",
    nationalAggregate: "National aggregate",
    releaseStatus: "Publication status",
    fixtureRelease: "Synthetic fixture",
    candidateRelease: "Candidate release · preliminary",
    publishedRelease: "Published",
    withdrawnRelease: "Withdrawn",
    sourceLayer: "Source layer",
    sourcePrecount: "Official pre-count",
    sourceFinal: "CNE final declaration",
    sourceScrutiny: "Published official scrutiny",
    legalStatus: "Legal status",
    legalPreliminary: "Preliminary pre-count",
    legalFinal: "Controlling final",
    legalScrutiny: "Official scrutiny",
    dataVersion: "Data version",
    electionDate: "Election day",
    nationalReading: "National reading",
    candidateLedger: "Candidate distribution",
    candidateNote:
      "Bars compare shares of valid votes. Name and ballot number identify each ticket; colour does not encode identity.",
    ballotNumber: "Ballot",
    votes: "votes",
    turnout: "Turnout",
    turnoutContext: "Voters over registered electors",
    completion: "Reported completion",
    completionContext: "Reported mesas over expected mesas",
    leadingMargin: "Difference between the top two",
    percentagePoint: "percentage point",
    percentagePoints: "percentage points",
    marginUnavailable: "Unavailable from the observed values",
    ballotComposition: "Composition of all voters",
    valid: "Valid votes",
    blank: "Blank votes",
    null: "Null votes",
    unmarked: "Unmarked votes",
    publicationChain: "Publication chain",
    publicationChainNote:
      "Data moves from an expected record to a retrieved object, an interpreted record, and a reconciled fact. A zero is shown as zero; unknown values are named.",
    expected: "Expected",
    retrieved: "Retrieved",
    parsed: "Interpreted",
    missing: "Missing",
    ambiguous: "Ambiguous",
    excluded: "Excluded",
    reconciliation: "Aggregate reconciliation",
    checkedFact: "fact checked",
    checkedFacts: "facts checked",
    exception: "exception",
    exceptions: "exceptions",
    passed: "Passed",
    blocked: "Blocked",
    notRun: "Not run",
    evidenceReading: "What this investigation can conclude",
    evidenceReadingNote:
      "Evidence and models answer different questions. The portal keeps those answers separate.",
    documentaryEvidence: "Documentary verification",
    documentaryEvidenceBody:
      "It can confirm arithmetic failures, missing or duplicate records, and differences between compatible official sources.",
    statisticalEvidence: "Statistical signals",
    statisticalEvidenceBody:
      "The synthetic demonstration may show experimental signals. Real releases remain unavailable pending independent validation.",
    fraudConclusion: "Inference boundary",
    fraudConclusionBody:
      "Mathematics detects unusual patterns and prioritizes documentary review. It does not establish intent, fraud, or responsibility.",
    analysisDisclosure:
      "This score prioritizes records for documentary review; it does not measure or determine fraud. Absence of a signal does not prove that a mesa was error-free.",
    bulletinProgression: "Bulletin progression",
    bulletinNote:
      "Each bar represents completion reported at that cut. The sequence is descriptive: it is not a projection, trend, or measure of certainty.",
    bulletin: "Bulletin",
    mesa: "mesa",
    mesas: "mesas",
    noBulletins: "No bulletins are available in this version.",
    reviewWindow: "Loaded review window",
    reviewWindowNote:
      "Up to three high scores from the API page currently loaded are shown. This block does not claim a national signal count.",
    score: "Audit-priority score",
    affectedVotes: "Votes with verified documentary basis",
    unavailable: "Unavailable",
    moreSignals:
      "More records exist behind the cursor; use the full paginated list.",
    noSignals: "There are no signals in the loaded window.",
    analysisUnavailable:
      "Signal analysis has not been published for this release. An empty list does not mean that no anomalies exist.",
    methodology: "Methodology",
    openReview: "Open review",
    provenance: "Reading provenance",
    retrievedAt: "Retrieved",
    hash: "SHA-256 digest",
    parser: "Parser",
    transform: "Transform",
    officialSource: "Open official source",
    fixtureSource: "Demonstration fixture URL",
    nextSteps: "Continue reading",
    exploreResults: "Explore results",
    inspectSources: "Inspect sources",
    reviewMethod: "Read methodology",
    observed: "Observed",
    unknown: "Unknown",
    notApplicable: "Not applicable",
  },
} as const;

const tierLabels = {
  documentary_review_prioritized: {
    es: "Revisión documental priorizada (70–100)",
    en: "Documentary review prioritized (70–100)",
  },
  documentary_comparison_recommended: {
    es: "Comparación documental recomendada (45–69)",
    en: "Documentary comparison recommended (45–69)",
  },
  statistical_or_coverage_issue: {
    es: "Señal estadística experimental o cobertura (15–44)",
    en: "Experimental statistical signal or coverage issue (15–44)",
  },
  no_review_signals: {
    es: "Sin señales de revisión en los datos disponibles (0–14)",
    en: "No review signals detected in available data (0–14)",
  },
} as const;

function boundedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, value * 100));
}

export function calculateCandidateMargin(candidates: CandidateSummary[]) {
  const observed = candidates
    .filter(
      (item) =>
        item.votes.status === "observed" &&
        item.votes.value !== null &&
        item.share !== null,
    )
    .sort((left, right) => (right.votes.value ?? 0) - (left.votes.value ?? 0));
  const [first, second] = observed;
  if (!first || !second) return null;
  return {
    votes: Math.abs((first.votes.value ?? 0) - (second.votes.value ?? 0)),
    share: Math.abs((first.share ?? 0) - (second.share ?? 0)),
  };
}

function electionDate(value: string, locale: Locale) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "long",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function AnalyticsPortal({
  locale,
  release,
  outcomeSensitivity = null,
}: {
  locale: Locale;
  release: ReleaseView;
  outcomeSensitivity?: components["schemas"]["OutcomeSensitivity"] | null;
}) {
  const c = copy[locale];
  const summary = release.summary;
  const href = (path: string) => `/${locale}${path}`;
  const metricLabels: MetricStatusLabels = {
    observed: c.observed,
    unknown: c.unknown,
    unavailable: c.unavailable,
    not_applicable: c.notApplicable,
  };
  const displayMetric = (metric: components["schemas"]["MetricValue"]) =>
    formatMetricValue(metric, locale, metricLabels).display;
  const candidates = [...summary.candidates].sort(
    (left, right) =>
      (right.votes.value ?? Number.NEGATIVE_INFINITY) -
      (left.votes.value ?? Number.NEGATIVE_INFINITY),
  );
  const margin = calculateCandidateMargin(candidates);
  const voterDenominator =
    summary.voters.status === "observed" && (summary.voters.value ?? 0) > 0
      ? summary.voters.value
      : null;
  const ballotRows = [
    { label: c.valid, metric: summary.valid_votes },
    { label: c.blank, metric: summary.blank_votes },
    { label: c.null, metric: summary.null_votes },
    { label: c.unmarked, metric: summary.unmarked_votes },
  ];
  const coverage = summary.coverage;
  const coverageStages = [
    { number: "01", label: c.expected, value: coverage.expected },
    { number: "02", label: c.retrieved, value: coverage.retrieved },
    { number: "03", label: c.parsed, value: coverage.parsed },
  ];
  const reconciliationLabel =
    summary.reconciliation.status === "passed"
      ? c.passed
      : summary.reconciliation.status === "blocked"
        ? c.blocked
        : c.notRun;
  const releaseStatusLabel = release.release.synthetic
    ? c.fixtureRelease
    : release.release.status === "candidate"
      ? c.candidateRelease
      : release.release.status === "published"
        ? c.publishedRelease
        : release.release.status === "withdrawn"
          ? c.withdrawnRelease
          : release.release.status;
  const sourceLayerLabel =
    summary.provenance.source_type === "pre_count"
      ? c.sourcePrecount
      : summary.provenance.source_type === "final_declaration"
        ? c.sourceFinal
        : summary.provenance.source_type === "scrutiny"
          ? c.sourceScrutiny
          : summary.provenance.source_type;
  const legalStatusLabel =
    summary.provenance.legal_status === "preliminary"
      ? c.legalPreliminary
      : summary.provenance.legal_status === "controlling_final"
        ? c.legalFinal
        : summary.provenance.legal_status === "official_scrutiny"
          ? c.legalScrutiny
          : summary.provenance.legal_status;
  const bulletins = [...release.bulletins].sort(
    (left, right) => left.sequence - right.sequence,
  );
  const signals = [...release.review_signals]
    .sort(
      (left, right) =>
        right.score - left.score || left.id.localeCompare(right.id),
    )
    .slice(0, 3);
  const municipalityByMesa = new Map(
    release.mesas.map((mesa) => [
      mesa.id,
      release.geographies.find((item) => item.id === mesa.municipality_id)
        ?.name ?? c.unknown,
    ]),
  );
  const nextLinks = [
    ["/resultados", c.exploreResults],
    ["/fuentes", c.inspectSources],
    ["/metodologia", c.reviewMethod],
  ] as const;

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] px-[clamp(1rem,5.55vw,5rem)] py-8 sm:py-12"
    >
      <ReleaseNotice
        locale={locale}
        synthetic={release.release.synthetic}
        releaseStatus={release.release.status}
      />
      <div className="mt-4">
        <GeographicCoverageNotice
          coverage={summary.geographic_collection_coverage ?? undefined}
          locale={locale}
        />
      </div>

      <header className="mt-4 grid border border-ink lg:grid-cols-12">
        <div className="px-4 py-8 sm:px-6 sm:py-12 lg:col-span-8 lg:px-8">
          <p className="font-mono text-[11px] font-bold tracking-[.16em] text-muted uppercase">
            {c.eyebrow}
          </p>
          <h1 className="mt-4 max-w-4xl break-words font-display text-3xl font-bold leading-[.94] tracking-[-0.055em] text-balance uppercase sm:text-6xl xl:text-7xl">
            {c.title}
          </h1>
          <p className="mt-5 max-w-3xl text-base leading-7 text-muted">
            {c.intro}
          </p>
        </div>
        <aside className="order-first border-b border-ink bg-ink px-4 py-6 text-paper sm:px-6 lg:order-last lg:col-span-4 lg:border-b-0 lg:border-l lg:px-7 lg:py-8">
          <p className="font-mono text-[11px] font-bold tracking-[.12em] text-[#9B9B9B] uppercase">
            {c.readingBoundary}
          </p>
          <p className="mt-3 font-display text-2xl font-bold leading-tight tracking-[-0.035em] uppercase">
            {c.nationalAggregate}
          </p>
          <dl className="mt-6 grid gap-px border border-[#9B9B9B] bg-[#9B9B9B] text-sm sm:grid-cols-2 lg:grid-cols-1">
            <div className="min-w-0 bg-ink p-4">
              <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-[#9B9B9B] uppercase">
                {c.releaseStatus}
              </dt>
              <dd className="mt-1">{releaseStatusLabel}</dd>
            </div>
            <div className="min-w-0 bg-ink p-4">
              <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-[#9B9B9B] uppercase">
                {c.dataVersion}
              </dt>
              <dd className="mt-1 break-all">
                <code>{summary.data_version}</code>
              </dd>
            </div>
            <div className="min-w-0 bg-ink p-4">
              <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-[#9B9B9B] uppercase">
                {c.sourceLayer}
              </dt>
              <dd className="mt-1">{sourceLayerLabel}</dd>
            </div>
            <div className="min-w-0 bg-ink p-4">
              <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-[#9B9B9B] uppercase">
                {c.legalStatus}
              </dt>
              <dd className="mt-1">{legalStatusLabel}</dd>
            </div>
          </dl>
        </aside>
      </header>

      <section
        className="grid border-x border-b border-ink lg:grid-cols-12"
        aria-labelledby="national-reading-title"
      >
        <div className="px-4 py-9 sm:px-6 sm:py-12 lg:col-span-8 lg:px-8">
          <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
            <span aria-hidden="true">01 / </span>
            {c.nationalReading}
          </p>
          <h2
            id="national-reading-title"
            className="mt-3 break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-4xl"
          >
            {c.candidateLedger}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
            {c.candidateNote}
          </p>
          <ol className="mt-7 border-t border-line">
            {candidates.map((candidate) => {
              const voteDisplay = displayMetric(candidate.votes);
              const shareDisplay = formatPercent(candidate.share, locale);
              return (
                <li
                  className="grid gap-3 border-b border-line py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end"
                  key={candidate.candidate.id}
                >
                  <div className="min-w-0">
                    <div className="flex items-start gap-3">
                      <span className="grid size-9 shrink-0 place-content-center border border-ink text-sm font-bold tabular-nums">
                        {candidate.candidate.ballot_number ?? "—"}
                      </span>
                      <div className="min-w-0">
                        <p className="font-display text-xl font-bold">
                          {candidate.candidate.name[locale]}
                        </p>
                        <p className="mt-1 text-xs text-muted">
                          {c.ballotNumber}{" "}
                          {candidate.candidate.ballot_number ?? "—"}
                        </p>
                      </div>
                    </div>
                    <div
                      className="mt-4 h-2 bg-[#9B9B9B]/35"
                      aria-hidden="true"
                    >
                      <span
                        className="block h-full bg-ink"
                        style={{ width: `${boundedPercent(candidate.share)}%` }}
                      />
                    </div>
                  </div>
                  <p
                    className="text-left font-bold tabular-nums sm:text-right"
                    aria-label={`${candidate.candidate.name[locale]}: ${voteDisplay} ${c.votes}, ${shareDisplay}`}
                  >
                    <span className="block font-display text-3xl">
                      {shareDisplay}
                    </span>
                    <span className="mt-1 block text-xs text-muted">
                      {voteDisplay} {c.votes}
                    </span>
                  </p>
                </li>
              );
            })}
          </ol>
        </div>

        <dl className="border-t border-ink bg-ink text-paper lg:col-span-4 lg:border-l lg:border-t-0">
          <div className="px-4 py-7 sm:px-6 lg:px-7">
            <dt className="flex items-center gap-2 font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase">
              <span aria-hidden="true">02 /</span>
              <Gauge className="size-4" aria-hidden="true" /> {c.turnout}
            </dt>
            <dd className="mt-2 font-display text-5xl font-bold tabular-nums">
              {formatPercent(summary.turnout, locale)}
            </dd>
            <dd className="mt-2 text-xs leading-5 text-[#9B9B9B]">
              {displayMetric(summary.voters)} /{" "}
              {displayMetric(summary.registered_electors)} · {c.turnoutContext}
            </dd>
          </div>
          <div className="border-t border-[#9B9B9B] px-4 py-7 sm:px-6 lg:px-7">
            <dt className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase">
              {c.completion}
            </dt>
            <dd className="mt-2 font-display text-4xl font-bold tabular-nums">
              {formatCompletionPercent(
                summary.completion.reported,
                summary.completion.expected,
                locale,
              )}
            </dd>
            <dd className="mt-2 text-xs leading-5 text-[#9B9B9B]">
              {formatNumber(summary.completion.reported, locale)} /{" "}
              {formatNumber(summary.completion.expected, locale)} ·{" "}
              {c.completionContext}
            </dd>
          </div>
          <div className="border-t border-[#9B9B9B] px-4 py-7 sm:px-6 lg:px-7">
            <dt className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase">
              {c.leadingMargin}
            </dt>
            <dd className="mt-2 font-display text-3xl font-bold tabular-nums">
              {margin
                ? `${formatNumber(margin.votes, locale)} ${c.votes}`
                : "—"}
            </dd>
            <dd className="mt-2 text-xs leading-5 text-[#9B9B9B]">
              {margin
                ? `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(margin.share * 100)} ${Math.round(margin.share * 1000) / 10 === 1 ? c.percentagePoint : c.percentagePoints}`
                : c.marginUnavailable}
            </dd>
          </div>
        </dl>
      </section>

      <section className="grid border-x border-b border-ink lg:grid-cols-12">
        <div
          className="px-4 py-9 sm:px-6 sm:py-10 lg:col-span-5 lg:px-8"
          aria-labelledby="ballot-composition-title"
        >
          <h2
            id="ballot-composition-title"
            className="break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
          >
            <span
              className="mb-3 block font-mono text-[11px] tracking-[.14em] text-muted"
              aria-hidden="true"
            >
              03
            </span>
            {c.ballotComposition}
          </h2>
          <div className="mt-6 space-y-5">
            {ballotRows.map((row) => {
              const ratio =
                voterDenominator &&
                row.metric.status === "observed" &&
                row.metric.value !== null
                  ? row.metric.value / voterDenominator
                  : null;
              return (
                <div key={row.label}>
                  <div className="flex items-baseline justify-between gap-4 text-sm">
                    <p className="font-bold">{row.label}</p>
                    <p className="tabular-nums">
                      {displayMetric(row.metric)} ·{" "}
                      {formatPercent(ratio, locale)}
                    </p>
                  </div>
                  <div className="mt-2 h-2 bg-[#9B9B9B]/35" aria-hidden="true">
                    <span
                      className="block h-full bg-ink"
                      style={{ width: `${boundedPercent(ratio)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div
          className="border-t border-ink px-4 py-9 sm:px-6 sm:py-10 lg:col-span-7 lg:border-l lg:border-t-0 lg:px-8"
          aria-labelledby="publication-chain-title"
        >
          <div className="flex items-start gap-3">
            <Database className="mt-1 size-5 shrink-0" aria-hidden="true" />
            <div>
              <h2
                id="publication-chain-title"
                className="break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
              >
                <span
                  className="mb-3 block font-mono text-[11px] tracking-[.14em] text-muted"
                  aria-hidden="true"
                >
                  04
                </span>
                {c.publicationChain}
              </h2>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-muted">
                {c.publicationChainNote}
              </p>
            </div>
          </div>
          <ol className="mt-6 grid border border-ink sm:grid-cols-3">
            {coverageStages.map((stage) => (
              <li
                className="border-b border-ink p-5 last:border-b-0 sm:border-r sm:border-b-0 sm:last:border-r-0"
                key={stage.number}
              >
                <p className="font-mono text-[11px] font-bold tracking-[.12em] text-muted">
                  {stage.number}
                </p>
                <p className="mt-6 font-display text-4xl font-bold tabular-nums">
                  {formatNumber(stage.value, locale)}
                </p>
                <p className="mt-1 text-xs font-bold tracking-[.08em] text-muted uppercase">
                  {stage.label}
                </p>
              </li>
            ))}
          </ol>
          <dl className="grid grid-cols-3 border-x border-b border-ink text-sm">
            {[
              [c.missing, coverage.missing],
              [c.ambiguous, coverage.ambiguous],
              [c.excluded, coverage.excluded],
            ].map(([label, value]) => (
              <div
                className="min-w-0 border-r border-ink p-3 last:border-r-0"
                key={label}
              >
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-1 font-bold tabular-nums">
                  {formatNumber(value as number, locale)}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border border-ink bg-ink px-4 py-4 text-paper">
            <div>
              <p className="font-mono text-[11px] font-bold tracking-[.08em] text-[#9B9B9B] uppercase">
                {c.reconciliation}
              </p>
              <p className="mt-1 text-sm">
                {formatNumber(summary.reconciliation.checked_facts, locale)}{" "}
                {summary.reconciliation.checked_facts === 1
                  ? c.checkedFact
                  : c.checkedFacts}{" "}
                · {formatNumber(summary.reconciliation.exceptions, locale)}{" "}
                {summary.reconciliation.exceptions === 1
                  ? c.exception
                  : c.exceptions}
              </p>
            </div>
            <StatusBadge
              tone={
                summary.reconciliation.status === "passed"
                  ? "success"
                  : "neutral"
              }
            >
              {summary.reconciliation.status === "passed" ? (
                <CheckCircle2 className="size-3.5" aria-hidden="true" />
              ) : (
                <CircleDashed className="size-3.5" aria-hidden="true" />
              )}
              {reconciliationLabel}
            </StatusBadge>
          </div>
        </div>
      </section>

      <section
        className="border-x border-b border-ink px-4 py-9 sm:px-6 sm:py-12 lg:px-8"
        aria-labelledby="evidence-reading-title"
      >
        <div className="grid gap-8 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <h2
              id="evidence-reading-title"
              className="break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
            >
              <span
                className="mb-3 block font-mono text-[11px] tracking-[.14em] text-muted"
                aria-hidden="true"
              >
                05
              </span>
              {c.evidenceReading}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              {c.evidenceReadingNote}
            </p>
            <ol className="mt-7 border-y border-ink">
              {[
                ["01", c.documentaryEvidence, c.documentaryEvidenceBody],
                ["02", c.statisticalEvidence, c.statisticalEvidenceBody],
                ["03", c.fraudConclusion, c.fraudConclusionBody],
              ].map(([number, title, body]) => (
                <li
                  className="grid gap-3 border-b border-ink py-5 last:border-b-0 sm:grid-cols-[3rem_minmax(9rem,.7fr)_minmax(0,1.3fr)]"
                  key={number}
                >
                  <p className="font-mono text-[11px] font-bold tracking-[.12em] text-muted">
                    {number}
                  </p>
                  <h3 className="text-base font-bold leading-snug">{title}</h3>
                  <p className="text-sm leading-6 text-muted">{body}</p>
                </li>
              ))}
            </ol>
          </div>

          <div className="lg:col-span-4">
            <OutcomeSensitivityPanel
              outcome={outcomeSensitivity}
              locale={locale}
            />
          </div>
        </div>
        <p className="mt-7 border-l-4 border-neon pl-4 text-sm leading-6 text-muted">
          {c.analysisDisclosure}
        </p>
      </section>

      <section
        className="border-x border-b border-ink px-4 py-9 sm:px-6 sm:py-12 lg:px-8"
        aria-labelledby="bulletins-title"
      >
        <div className="grid gap-4 lg:grid-cols-[minmax(0,.65fr)_minmax(0,1.35fr)]">
          <div>
            <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
              <span aria-hidden="true">06 / </span>
              {c.completion}
            </p>
            <h2
              id="bulletins-title"
              className="mt-3 break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
            >
              {c.bulletinProgression}
            </h2>
          </div>
          <p className="max-w-3xl text-sm leading-6 text-muted lg:justify-self-end">
            {c.bulletinNote}
          </p>
        </div>
        {bulletins.length ? (
          <ol className="mt-7 border-t border-line">
            {bulletins.map((bulletin) => (
              <li
                className="grid gap-3 border-b border-line py-4 sm:grid-cols-[7rem_minmax(0,1fr)_auto] sm:items-center"
                key={bulletin.id}
              >
                <div>
                  <p className="font-bold">
                    {c.bulletin} {bulletin.sequence}
                  </p>
                  <time className="text-xs text-muted">
                    {formatDate(bulletin.published_at, locale)}
                  </time>
                </div>
                <div>
                  <div
                    className="h-2 bg-[#9B9B9B]/35"
                    role="progressbar"
                    aria-label={`${c.bulletin} ${bulletin.sequence}: ${formatPercent(bulletin.completion_percent, locale)}`}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={boundedPercent(bulletin.completion_percent)}
                  >
                    <span
                      className="block h-full bg-ink"
                      style={{
                        width: `${boundedPercent(bulletin.completion_percent)}%`,
                      }}
                    />
                  </div>
                </div>
                <p className="text-sm font-bold tabular-nums sm:text-right">
                  {formatPercent(bulletin.completion_percent, locale)} ·{" "}
                  {formatNumber(bulletin.reported_mesas, locale)} /{" "}
                  {formatNumber(bulletin.expected_mesas, locale)}{" "}
                  {bulletin.expected_mesas === 1 ? c.mesa : c.mesas}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-7 border border-line p-5 text-sm">{c.noBulletins}</p>
        )}
      </section>

      <section
        className="grid border-x border-b border-ink lg:grid-cols-12"
        aria-labelledby="review-window-title"
      >
        <div className="bg-ink px-4 py-8 text-paper sm:px-6 lg:col-span-4 lg:px-7">
          <p
            className="font-mono text-[11px] font-bold tracking-[.14em] text-[#9B9B9B]"
            aria-hidden="true"
          >
            07
          </p>
          <FileSearch className="size-7" aria-hidden="true" />
          <h2
            id="review-window-title"
            className="mt-4 break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
          >
            {c.reviewWindow}
          </h2>
          <p className="mt-3 text-sm leading-6 text-[#9B9B9B]">
            {c.reviewWindowNote}
          </p>
          {release.review_page?.has_more && (
            <p className="mt-4 border-l-2 border-neon pl-3 text-xs leading-5">
              {c.moreSignals}
            </p>
          )}
          <Link
            className="mt-6 inline-flex min-h-11 items-center gap-2 border border-neon bg-neon px-4 font-mono text-xs font-bold tracking-[.08em] text-ink uppercase hover:bg-paper"
            href={href("/revision")}
          >
            {c.openReview} <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>

        {signals.length ? (
          <ol className="border-t border-ink px-4 sm:px-6 lg:col-span-8 lg:border-t-0 lg:border-l lg:px-8">
            {signals.map((signal) => (
              <li className="border-b border-ink py-6" key={signal.id}>
                <article className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <div>
                    <p className="font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
                      {tierLabels[signal.tier][locale]}
                    </p>
                    <p className="mt-2 text-sm font-bold">
                      {municipalityByMesa.get(signal.mesa_id) ?? c.unknown}
                    </p>
                    <h3 className="mt-2 font-display text-xl font-bold">
                      <Link
                        className="underline decoration-line underline-offset-4 hover:decoration-ink"
                        href={href(`/actas/${signal.mesa_id}`)}
                      >
                        Mesa {signal.mesa_id}
                      </Link>
                    </h3>
                    <p className="mt-2 text-sm text-muted">
                      {c.affectedVotes}:{" "}
                      {signal.affected_vote_estimate === null
                        ? c.unavailable
                        : formatNumber(signal.affected_vote_estimate, locale)}
                    </p>
                  </div>
                  <div className="sm:text-right">
                    <p className="font-display text-4xl font-bold tabular-nums">
                      {signal.score}
                      <span className="text-base">/100</span>
                    </p>
                    <p className="mt-1 text-xs text-muted">{c.score}</p>
                  </div>
                </article>
                <p className="mt-4 border-l-2 border-neon pl-3 text-xs leading-5 text-muted">
                  {reviewDisclosure[locale]}
                </p>
                <ReviewSignalDetails signal={signal} locale={locale} />
              </li>
            ))}
          </ol>
        ) : (
          <p className="m-4 border border-ink p-5 text-sm sm:m-6 lg:col-span-8 lg:m-0 lg:border-y-0 lg:border-r-0 lg:border-l">
            {release.release.status !== "published" ||
            summary.reconciliation.status !== "passed"
              ? c.analysisUnavailable
              : c.noSignals}
          </p>
        )}
      </section>

      <section
        className="grid border-x border-b border-ink lg:grid-cols-12"
        aria-labelledby="provenance-title"
      >
        <div className="px-4 py-9 sm:px-6 sm:py-12 lg:col-span-8 lg:px-8">
          <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
            <span aria-hidden="true">08 / </span>
            {c.dataVersion}
          </p>
          <h2
            id="provenance-title"
            className="mt-3 break-words font-display text-2xl font-bold leading-tight tracking-[-0.04em] uppercase sm:text-3xl"
          >
            {c.provenance}
          </h2>
          <dl className="mt-6 grid gap-5 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-bold">{c.retrievedAt}</dt>
              <dd className="mt-1 text-muted">
                {formatDate(summary.provenance.retrieved_at, locale)}
              </dd>
            </div>
            <div>
              <dt className="font-bold">{c.electionDate}</dt>
              <dd className="mt-1 text-muted">
                {electionDate(summary.election_date, locale)}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-bold">{c.hash}</dt>
              <dd className="mt-1 break-all font-mono text-xs text-muted">
                {summary.provenance.content_hash}
              </dd>
            </div>
            <div>
              <dt className="font-bold">{c.parser}</dt>
              <dd className="mt-1 break-all text-muted">
                <code>{summary.provenance.parser_version}</code>
              </dd>
            </div>
            <div>
              <dt className="font-bold">{c.transform}</dt>
              <dd className="mt-1 break-all text-muted">
                <code>{summary.provenance.transform_version}</code>
              </dd>
            </div>
            <div>
              <dt className="font-bold">{c.methodology}</dt>
              <dd className="mt-1 break-all text-muted">
                <code>{release.release.methodology_version}</code>
              </dd>
            </div>
            <div>
              <dt className="font-bold">{c.sourceLayer}</dt>
              <dd className="mt-1 text-muted">
                <code>{summary.provenance.source_type}</code> ·{" "}
                <code>{summary.provenance.legal_status}</code>
              </dd>
            </div>
          </dl>
          <p className="mt-6 text-sm">
            {release.release.synthetic ? (
              <span className="inline-flex min-h-11 items-center gap-2 text-muted">
                <Dot /> {c.fixtureSource}
              </span>
            ) : (
              <a
                className="inline-flex min-h-11 items-center gap-2 font-bold underline underline-offset-4"
                href={summary.provenance.source_url}
                rel="noreferrer"
              >
                {c.officialSource}{" "}
                <ArrowRight className="size-4" aria-hidden="true" />
              </a>
            )}
          </p>
        </div>

        <aside className="border-t border-ink bg-ink px-4 py-8 text-paper sm:px-6 lg:col-span-4 lg:border-t-0 lg:border-l lg:px-7">
          <p className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase">
            {c.nextSteps}
          </p>
          <nav className="mt-4" aria-label={c.nextSteps}>
            <ul className="divide-y divide-[#9B9B9B] border-y border-[#9B9B9B]">
              {nextLinks.map(([path, label]) => (
                <li key={path}>
                  <Link
                    className="flex min-h-12 items-center justify-between gap-3 py-3 font-bold hover:text-neon"
                    href={href(path)}
                  >
                    {label} <ArrowRight className="size-4" aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
      </section>
    </main>
  );
}
