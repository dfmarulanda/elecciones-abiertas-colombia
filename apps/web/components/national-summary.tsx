import Link from "next/link";
import type { components } from "@elecciones/contracts";
import React from "react";

import {
  OutcomeSensitivityPanel,
  ReviewSignalDetails,
} from "@/components/investigation-details";
import type { ReleaseView } from "@/data/fixture-adapter";
import { reviewDisclosure } from "@/lib/review-disclosure";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";
import { formatMetricValue, type MetricStatusLabels } from "@/lib/metric-value";

type Locale = "es" | "en";
type Text = (key: string) => string;
type Signal = components["schemas"]["ReviewSignal"];
type SignalComponent = Signal["components"][number];

const copy = (locale: Locale, es: string, en: string) =>
  locale === "es" ? es : en;

const isStatisticalComponent = (component: SignalComponent) =>
  component.component_type === "peer_distribution" ||
  component.component_type === "spatial_cluster";

function MetricValue({
  metric,
  locale,
  labels,
}: {
  metric: components["schemas"]["MetricValue"];
  locale: Locale;
  labels: MetricStatusLabels;
}) {
  const formattingLocale = locale === "es" ? "es-CO" : locale;
  return <>{formatMetricValue(metric, formattingLocale, labels).display}</>;
}

function Module({
  number,
  title,
  conclusion,
  means,
  doesNotMean,
  children,
  locale,
}: {
  number: string;
  title: string;
  conclusion: string;
  means: string;
  doesNotMean: string;
  children: React.ReactNode;
  locale: Locale;
}) {
  return (
    <section className="border-x border-b border-ink px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
      <div className="grid gap-6 lg:grid-cols-12">
        <header className="lg:col-span-4">
          <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
            {number}
          </p>
          <h2 className="mt-3 font-display text-2xl font-bold leading-tight tracking-[-.04em] uppercase sm:text-3xl">
            {title}
          </h2>
        </header>
        <div className="min-w-0 lg:col-span-8">
          <p className="text-base font-bold leading-7">{conclusion}</p>
          <dl className="mt-5 grid gap-4 border-y border-ink py-4 text-sm leading-6 sm:grid-cols-2">
            <div>
              <dt className="font-mono text-[11px] font-bold tracking-[.1em] text-muted uppercase">
                {copy(locale, "Qué significa", "What this means")}
              </dt>
              <dd className="mt-1">{means}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-bold tracking-[.1em] text-muted uppercase">
                {copy(locale, "Qué no significa", "What this does not mean")}
              </dt>
              <dd className="mt-1">{doesNotMean}</dd>
            </div>
          </dl>
          {children}
        </div>
      </div>
    </section>
  );
}

function SignalWindow({
  signals,
  locale,
  kind,
  hasMore,
  withheld,
}: {
  signals: Signal[];
  locale: Locale;
  kind: "documentary" | "statistical";
  hasMore?: boolean;
  withheld?: boolean;
}) {
  if (withheld) {
    return (
      <p className="mt-5 border border-ink bg-ink p-4 text-sm leading-6 text-paper">
        {copy(
          locale,
          "Las filas de revisión no se muestran: una versión real debe estar publicada y tener conciliación verificada antes de exponerlas aquí.",
          "Review rows are withheld: a real release must be published and have passed reconciliation before they can be shown here.",
        )}
      </p>
    );
  }
  const selected = signals.flatMap((signal) => {
    const visibleComponents = signal.components.filter((component) =>
      kind === "statistical"
        ? isStatisticalComponent(component)
        : !isStatisticalComponent(component),
    );
    return visibleComponents.length ? [{ signal, visibleComponents }] : [];
  });
  if (!selected.length) {
    return (
      <p className="mt-5 border border-line p-4 text-sm leading-6 text-muted">
        {copy(
          locale,
          "No hay registros de este tipo en la ventana de revisión cargada. Esto no equivale a una cuenta nacional de ausencia.",
          "There are no records of this kind in the loaded review window. This is not a national count of absence.",
        )}
      </p>
    );
  }
  return (
    <ol className="mt-5 border-t border-ink">
      {selected.map(({ signal, visibleComponents }) => (
        <li className="border-b border-ink py-5" key={signal.id}>
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
            <p className="font-bold">Mesa {signal.mesa_id}</p>
            <p className="text-sm tabular-nums">
              {copy(
                locale,
                "Prioridad de revisión general (todos los componentes)",
                "Overall audit-priority score (all components)",
              )}
              : {signal.score}/100
            </p>
            {kind === "documentary" && (
              <p className="text-sm tabular-nums">
                {copy(
                  locale,
                  "Estimación de votos afectados",
                  "Affected-vote estimate",
                )}
                :{" "}
                {signal.affected_vote_estimate === null
                  ? copy(locale, "No disponible", "Unavailable")
                  : formatNumber(signal.affected_vote_estimate, locale)}
              </p>
            )}
          </div>
          <p className="mt-3 border-l-2 border-neon pl-3 text-xs leading-5 text-muted">
            {reviewDisclosure[locale]}
          </p>
          <ReviewSignalDetails
            signal={signal}
            locale={locale}
            components={visibleComponents}
          />
        </li>
      ))}
      {hasMore && (
        <li className="pt-5 text-sm leading-6 text-muted">
          {copy(
            locale,
            "Hay más registros fuera de esta ventana paginada; no se agregan aquí como un total nacional.",
            "More records are outside this paginated window; they are not added here as a national total.",
          )}
        </li>
      )}
    </ol>
  );
}

export function NationalSummary({
  release,
  locale,
  t,
  outcomeSensitivity,
}: {
  release: ReleaseView;
  locale: Locale;
  t: Text;
  outcomeSensitivity: components["schemas"]["OutcomeSensitivity"] | null;
}) {
  const data = release.summary;
  const href = (path: string) => `/${locale}${path}`;
  const labels: MetricStatusLabels = {
    observed: t("common.metricObserved"),
    unknown: t("common.metricUnknown"),
    unavailable: t("common.metricUnavailable"),
    not_applicable: t("common.metricNotApplicable"),
  };
  const formattingLocale = locale === "es" ? "es-CO" : locale;
  const nullablePercent = (value: number | null) =>
    value === null ? labels.unavailable : formatPercent(value, locale);
  const turnoutDisplay = nullablePercent(data.turnout);
  const turnoutStatus =
    data.turnout === null ? labels.unavailable : labels.observed;
  const votersDisplay = formatMetricValue(
    data.voters,
    formattingLocale,
    labels,
  );
  const registeredDisplay = formatMetricValue(
    data.registered_electors,
    formattingLocale,
    labels,
  );
  const turnoutAccessibleLabel = `${t("home.turnout")}: ${turnoutDisplay}. ${turnoutStatus}. ${t("home.voters")} / ${t("home.registered")}: ${votersDisplay.display} / ${registeredDisplay.display}. ${votersDisplay.statusLabel} / ${registeredDisplay.statusLabel}.`;
  const releaseLabel = data.synthetic
    ? t("common.fixture")
    : data.release_status === "published"
      ? t("common.published")
      : data.release_status === "candidate"
        ? t("common.candidateRelease")
        : t("common.withdrawn");
  const sourceLabel =
    data.provenance.source_type === "pre_count"
      ? t("home.sourcePrecount")
      : data.provenance.source_type === "final_declaration"
        ? t("home.sourceFinal")
        : data.provenance.source_type === "scrutiny"
          ? t("home.sourceScrutiny")
          : data.provenance.source_type;
  const legalLabel =
    data.provenance.legal_status === "preliminary"
      ? t("home.preliminary")
      : data.provenance.legal_status === "controlling_final"
        ? t("home.legalFinal")
        : data.provenance.legal_status === "official_scrutiny"
          ? t("home.legalScrutiny")
          : data.provenance.legal_status;
  const reconciliation =
    data.reconciliation.status === "passed"
      ? t("home.passed")
      : data.reconciliation.status === "not_run"
        ? t("common.notRun")
        : t("common.blocked");
  const candidates = [...data.candidates].sort(
    (a, b) =>
      (a.candidate.ballot_number ?? Number.MAX_SAFE_INTEGER) -
      (b.candidate.ballot_number ?? Number.MAX_SAFE_INTEGER),
  );
  const hasMore = release.review_page?.has_more;
  const reviewRowsAllowed =
    data.synthetic ||
    (data.release_status === "published" &&
      data.reconciliation.status === "passed");

  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] px-gutter py-4 sm:py-12"
    >
      {/* The synthetic disclosure lives once in the site shell, above every
          page. A second banner here put two identical bands above the fold —
          anxious, not careful — so it was removed. The shell band is canonical
          (id="synthetic-disclosure"). */}
      <section className="border border-ink" aria-labelledby="page-title">
        <div className="grid lg:grid-cols-12">
          <header className="px-4 py-3 sm:px-6 sm:py-7 lg:col-span-8 lg:px-8">
            <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
              {t("home.eyebrow")}
            </p>
            <h1
              id="page-title"
              className="mt-2 font-display text-xl font-bold leading-[.95] tracking-[-.05em] uppercase sm:mt-3 sm:text-5xl"
            >
              {data.election_name[locale]}
            </h1>
          </header>
          <dl className="grid grid-cols-2 border-t border-ink text-xs lg:col-span-4 lg:border-t-0 lg:border-l lg:text-sm">
            <div className="border-r border-ink p-3 lg:p-4">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.status")}
              </dt>
              <dd className="mt-1 font-bold">{releaseLabel}</dd>
              <dt className="mt-2 border-t border-line pt-2 font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.received")}
              </dt>
              <dd className="mt-1 font-bold">
                {formatDate(data.provenance.retrieved_at, locale)}
              </dd>
            </div>
            <div className="p-3 lg:p-4">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.source")} · {t("home.legal")}
              </dt>
              <dd className="mt-1 font-bold">
                {sourceLabel} · {legalLabel}
              </dd>
            </div>
          </dl>
        </div>

        <div className="border-t border-ink px-4 py-4 sm:px-6 sm:py-7 lg:px-8">
          <p className="font-mono text-[11px] font-bold tracking-[.14em] text-muted uppercase">
            00 / {t("home.summary")}
          </p>
          <h2 className="mt-2 font-display text-xl font-bold leading-[1.05] tracking-[-.04em] uppercase sm:mt-3 sm:text-3xl">
            {t("home.candidates")}
          </h2>
          <ol className="mt-4 grid border-t border-ink sm:mt-5 md:grid-cols-2">
            {candidates.map((candidate) => (
              <li
                className="min-w-0 border-b border-ink py-4 sm:py-5 md:px-5 md:first:pl-0 md:last:border-l md:last:pr-0"
                key={candidate.candidate.id}
              >
                <p className="font-mono text-xs font-bold tracking-[.1em] text-muted uppercase">
                  {t("common.candidate")}{" "}
                  {candidate.candidate.ballot_number ?? "—"}
                </p>
                <h3 className="mt-2 text-lg font-bold">
                  {candidate.candidate.name[locale]}
                </h3>
                <p className="mt-3 font-display text-3xl font-bold tabular-nums sm:mt-4">
                  <MetricValue
                    metric={candidate.votes}
                    locale={locale}
                    labels={labels}
                  />{" "}
                  <span className="text-base">{t("home.votes")}</span>
                </p>
                <p className="mt-1 text-sm tabular-nums">
                  <MetricValue
                    metric={candidate.votes}
                    locale={locale}
                    labels={labels}
                  />{" "}
                  {copy(locale, "de", "of")}{" "}
                  <MetricValue
                    metric={data.valid_votes}
                    locale={locale}
                    labels={labels}
                  />{" "}
                  {t("home.valid").toLowerCase()} ={" "}
                  {nullablePercent(candidate.share)}
                </p>
              </li>
            ))}
          </ol>
          <dl className="grid border-b border-ink text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div className="border-t border-ink py-4 sm:px-4 sm:first:pl-0">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.completion")}
              </dt>
              <dd className="mt-2 leading-5 tabular-nums">
                {formatPercent(data.completion.percent, locale)} ·{" "}
                {formatNumber(data.completion.reported, locale)} /{" "}
                {formatNumber(data.completion.expected, locale)}
              </dd>
            </div>
            <div className="border-t border-ink py-4 sm:border-l sm:px-4">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.turnout")}
              </dt>
              <dd
                className="mt-2 leading-5 tabular-nums"
                aria-label={turnoutAccessibleLabel}
              >
                {turnoutDisplay} · {votersDisplay.display} /{" "}
                {registeredDisplay.display}
              </dd>
            </div>
            <div className="border-t border-ink py-4 sm:px-4 lg:border-l">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.reconciliation")}
              </dt>
              <dd className="mt-2 leading-5 tabular-nums">
                {reconciliation} ·{" "}
                {formatNumber(data.reconciliation.checked_facts, locale)}{" "}
                {t("home.factsChecked")} ·{" "}
                {formatNumber(data.reconciliation.exceptions, locale)}{" "}
                {t("home.exceptions")}
              </dd>
            </div>
            <div className="border-t border-ink py-4 sm:border-l sm:px-4">
              <dt className="font-mono text-[10px] font-bold tracking-[.1em] text-muted uppercase">
                {t("home.ballot")}
              </dt>
              <dd className="mt-2">
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2 tabular-nums">
                  {[
                    [t("home.valid"), data.valid_votes],
                    [t("home.blank"), data.blank_votes],
                    [t("home.null"), data.null_votes],
                    [t("home.unmarked"), data.unmarked_votes],
                  ].map(([label, metric]) => (
                    <div key={label as string}>
                      <dt className="text-xs text-muted">{label as string}</dt>
                      <dd className="font-bold">
                        <MetricValue
                          metric={
                            metric as components["schemas"]["MetricValue"]
                          }
                          locale={locale}
                          labels={labels}
                        />
                      </dd>
                    </div>
                  ))}
                </dl>
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <Module
        number="01"
        title={copy(locale, "Qué se está leyendo", "What is being read")}
        locale={locale}
        conclusion={`${releaseLabel}: ${sourceLabel} · ${legalLabel}.`}
        means={copy(
          locale,
          "Estas cifras pertenecen a una sola versión; la fuente y la condición jurídica delimitan la lectura.",
          "These figures belong to one version; source and legal condition bound the reading.",
        )}
        doesNotMean={copy(
          locale,
          "No cambia la condición jurídica de la fuente ni completa valores no publicados.",
          "It does not change the source's legal condition or fill in unpublished values.",
        )}
      >
        <details className="group mt-5 border border-ink px-4 text-sm">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-mono text-xs font-bold uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
            {copy(
              locale,
              "Fuente, alcance y versión",
              "Source, scope, and version",
            )}
          </summary>
          <dl className="mt-4 grid gap-3 pb-4 sm:grid-cols-2">
            <div>
              <dt className="font-bold">{t("home.release")}</dt>
              <dd>{data.data_version}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Alcance de la vista", "View scope")}
              </dt>
              <dd>{copy(locale, "Resumen nacional", "National summary")}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(
                  locale,
                  "Grano de los hechos fuente",
                  "Source fact grain",
                )}
              </dt>
              <dd>
                {copy(
                  locale,
                  "No disponible en esta respuesta",
                  "Unavailable in this response",
                )}
              </dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Comparador", "Comparator")}
              </dt>
              <dd>{copy(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Cálculo", "Calculation")}
              </dt>
              <dd>{copy(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-bold">{t("home.source")}</dt>
              <dd>
                <a
                  className="break-all underline"
                  href={data.provenance.source_url}
                  rel="noreferrer"
                >
                  {data.provenance.source_url}
                </a>
              </dd>
            </div>
            <div>
              <dt className="font-bold">{t("home.hash")}</dt>
              <dd className="break-all font-mono text-xs">
                {data.provenance.content_hash}
              </dd>
            </div>
          </dl>
        </details>
      </Module>

      <Module
        number="02"
        title={copy(
          locale,
          "¿Las cifras de esta versión concilian?",
          "Do the figures in this version reconcile?",
        )}
        locale={locale}
        conclusion={`${t("home.reconciliation")}: ${reconciliation}.`}
        means={copy(
          locale,
          "La comprobación incluida informa si los hechos revisados pasan las reglas de conciliación de esta versión.",
          "The included check reports whether reviewed facts pass this version's reconciliation rules.",
        )}
        doesNotMean={copy(
          locale,
          "No certifica una elección ni sustituye la revisión de documentos.",
          "It does not certify an election or replace document review.",
        )}
      >
        <details className="group mt-5 border border-ink px-4 text-sm">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 font-mono text-xs font-bold uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
            {copy(
              locale,
              "Cálculo, cobertura y límites",
              "Calculation, coverage, and limits",
            )}
          </summary>
          <dl className="mt-4 grid gap-3 pb-4 sm:grid-cols-2">
            <div>
              <dt className="font-bold">{t("home.completion")}</dt>
              <dd>
                {formatNumber(data.completion.reported, locale)} /{" "}
                {formatNumber(data.completion.expected, locale)}
              </dd>
            </div>
            <div>
              <dt className="font-bold">{t("home.sourceCoverage")}</dt>
              <dd>
                {formatNumber(data.coverage.parsed, locale)} /{" "}
                {formatNumber(data.coverage.expected, locale)}
              </dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Comparador", "Comparator")}
              </dt>
              <dd>{copy(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Cálculo", "Calculation")}
              </dt>
              <dd>{copy(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(
                  locale,
                  "Fuente / condición jurídica",
                  "Source / legal status",
                )}
              </dt>
              <dd className="font-mono text-xs">
                {data.provenance.source_type} / {data.provenance.legal_status}
              </dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Alcance de la vista", "View scope")}
              </dt>
              <dd>{copy(locale, "Resumen nacional", "National summary")}</dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(
                  locale,
                  "Grano de los hechos fuente",
                  "Source fact grain",
                )}
              </dt>
              <dd>
                {copy(
                  locale,
                  "No disponible en esta respuesta",
                  "Unavailable in this response",
                )}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-bold">source_url</dt>
              <dd>
                <a
                  className="break-all underline"
                  href={data.provenance.source_url}
                  rel="noreferrer"
                >
                  {data.provenance.source_url}
                </a>
              </dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(
                  locale,
                  "Faltantes / ambiguos / excluidos",
                  "Missing / ambiguous / excluded",
                )}
              </dt>
              <dd>
                {formatNumber(data.coverage.missing, locale)} /{" "}
                {formatNumber(data.coverage.ambiguous, locale)} /{" "}
                {formatNumber(data.coverage.excluded, locale)}
              </dd>
            </div>
            <div>
              <dt className="font-bold">
                {copy(locale, "Hechos / excepciones", "Facts / exceptions")}
              </dt>
              <dd>
                {formatNumber(data.reconciliation.checked_facts, locale)} /{" "}
                {formatNumber(data.reconciliation.exceptions, locale)}
              </dd>
            </div>
            <div>
              <dt className="font-bold">{copy(locale, "Límites", "Limits")}</dt>
              <dd>
                {copy(
                  locale,
                  "Faltantes, ambiguos o excluidos permanecen visibles.",
                  "Missing, ambiguous, or excluded records remain visible.",
                )}
              </dd>
            </div>
          </dl>
        </details>
      </Module>

      <Module
        number="03"
        title={copy(
          locale,
          "Diferencias documentales",
          "Documentary differences",
        )}
        locale={locale}
        conclusion={copy(
          locale,
          "La lista siguiente contiene solo señales documentales de la ventana cargada.",
          "The list below contains only documentary signals from the loaded window.",
        )}
        means={copy(
          locale,
          "Cada estimación de votos afectados se muestra por registro exactamente como fue suministrada en esta versión.",
          "Each affected-vote estimate is shown per record exactly as supplied in this version.",
        )}
        doesNotMean={copy(
          locale,
          "No es una suma ni una estimación nacional, y una señal no prueba su causa.",
          "It is not a sum or a national estimate, and a signal does not prove its cause.",
        )}
      >
        <SignalWindow
          signals={release.review_signals}
          locale={locale}
          kind="documentary"
          hasMore={hasMore}
          withheld={!reviewRowsAllowed}
        />
      </Module>

      <Module
        number="04"
        title={copy(
          locale,
          "Señales entre pares y espacio",
          "Peer and spatial signals",
        )}
        locale={locale}
        conclusion={copy(
          locale,
          "Las señales estadísticas mostradas pertenecen solo a la ventana cargada y pueden ser no elegibles.",
          "The statistical signals shown belong only to the loaded window and may be ineligible.",
        )}
        means={copy(
          locale,
          "Sus detalles muestran el comparador, umbral, elegibilidad y limitaciones suministrados para cada registro.",
          "Their details show the comparator, threshold, eligibility, and limitations supplied for each record.",
        )}
        doesNotMean={copy(
          locale,
          "No son probabilidades, conclusiones jurídicas ni conteos nacionales.",
          "They are not probabilities, legal conclusions, or national counts.",
        )}
      >
        <SignalWindow
          signals={release.review_signals}
          locale={locale}
          kind="statistical"
          hasMore={hasMore}
          withheld={!reviewRowsAllowed}
        />
      </Module>

      <Module
        number="05"
        title={copy(
          locale,
          "¿Podría la evidencia cambiar el resultado?",
          "Could the evidence change the outcome?",
        )}
        locale={locale}
        conclusion={
          outcomeSensitivity?.evaluable
            ? copy(
                locale,
                "La sensibilidad compara el margen observado con los límites documentales suministrados en esta versión.",
                "Sensitivity compares the observed margin with documentary bounds supplied in this version.",
              )
            : outcomeSensitivity
              ? copy(
                  locale,
                  "Esta versión informa que la sensibilidad no es evaluable y no puede publicar límites de decisión.",
                  "This version reports that sensitivity is not evaluable and cannot publish decision bounds.",
                )
              : copy(
                  locale,
                  "La sensibilidad no está disponible para esta versión y elección.",
                  "Outcome sensitivity is unavailable for this version and election.",
                )
        }
        means={
          outcomeSensitivity && !outcomeSensitivity.evaluable
            ? copy(
                locale,
                "Las condiciones bloqueantes indican qué entradas o compuertas impiden evaluar los límites.",
                "The blocking conditions identify which inputs or gates prevent the bounds from being evaluated.",
              )
            : copy(
                locale,
                "Describe límites evaluados cuando están disponibles.",
                "It describes evaluated bounds when they are available.",
              )
        }
        doesNotMean={copy(
          locale,
          "No establece por sí sola una conclusión jurídica ni transforma señales estadísticas en votos afectados.",
          "It does not itself establish a legal conclusion or turn statistical signals into affected votes.",
        )}
      >
        <div className="mt-5">
          <OutcomeSensitivityPanel
            outcome={outcomeSensitivity}
            locale={locale}
          />
        </div>
      </Module>

      <section className="border-x border-b border-ink px-4 py-8 sm:px-6 lg:px-8">
        <p className="max-w-2xl text-sm leading-6 text-muted">
          {t(
            data.synthetic ? "home.apiBoundary" : "home.publicReleaseBoundary",
          )}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href={href("/resultados")}
            className="inline-flex min-h-11 items-center border border-ink bg-ink px-4 font-mono text-xs font-bold tracking-[.08em] text-paper uppercase hover:bg-neon hover:text-ink"
          >
            {t("home.openResults")}
          </Link>
          <Link
            href={href("/revision")}
            className="inline-flex min-h-11 items-center border border-ink px-4 font-mono text-xs font-bold tracking-[.08em] uppercase hover:bg-neon"
          >
            {t("nav.review")}
          </Link>
          <Link
            href={href("/analitica")}
            className="inline-flex min-h-11 items-center border border-ink px-4 font-mono text-xs font-bold tracking-[.08em] uppercase hover:bg-neon"
          >
            {t("nav.analytics")}
          </Link>
        </div>
      </section>
    </main>
  );
}
