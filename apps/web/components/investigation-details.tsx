import type { components } from "@elecciones/contracts";
import React from "react";

import { formatNumber } from "@/lib/utils";
import { legalStatusLabel, sourceTypeLabel } from "@/lib/public-labels";

type Locale = "es" | "en";
type Signal = components["schemas"]["ReviewSignal"];
type SignalComponent = Signal["components"][number];
type SignalNumber = components["schemas"]["SignalNumber"];
type Outcome = components["schemas"]["OutcomeSensitivity"];
type Metric = components["schemas"]["MetricValue"];

const t = (locale: Locale, es: string, en: string) =>
  locale === "es" ? es : en;

const componentLabel = (
  component: Signal["components"][number]["component_type"],
  locale: Locale,
) =>
  ({
    verified_accounting_failure: t(
      locale,
      "Falla aritmética verificada",
      "Verified accounting failure",
    ),
    conflicting_official_records: t(
      locale,
      "Registros oficiales en conflicto",
      "Conflicting official records",
    ),
    documentary_difference_major: t(
      locale,
      "Diferencia documental mayor",
      "Major documentary difference",
    ),
    documentary_difference_minor: t(
      locale,
      "Diferencia documental menor",
      "Minor documentary difference",
    ),
    document_missing_duplicated_ambiguous: t(
      locale,
      "Documento faltante, duplicado o ambiguo",
      "Missing, duplicate, or ambiguous document",
    ),
    peer_distribution: t(locale, "Comparación con pares", "Peer comparison"),
    spatial_cluster: t(locale, "Patrón espacial", "Spatial pattern"),
  })[component];

function publishedReason(reason: string, locale: Locale) {
  return reason.includes("_")
    ? reason.split("_").join(" ")
    : reason || t(locale, "No disponible", "Not available");
}

function value(value: Metric | SignalNumber, locale: Locale) {
  if (value.status === "observed") return formatNumber(value.value, locale);
  return {
    unknown: t(locale, "Desconocido", "Unknown"),
    unavailable: t(locale, "No disponible", "Unavailable"),
    not_applicable: t(locale, "No aplica", "Not applicable"),
  }[value.status];
}

function Hashes({
  values,
  inverse = false,
}: {
  values: Array<[string, string | null | undefined]>;
  inverse?: boolean;
}) {
  const present = values.filter(([, item]) => item);
  if (!present.length) return null;
  return (
    <dl className="mt-4 grid gap-3 text-xs sm:grid-cols-2">
      {present.map(([name, item]) => (
        <div key={name}>
          <dt className="font-semibold">{name}</dt>
          <dd
            className={`mt-1 break-all font-mono ${inverse ? "text-[#9B9B9B]" : "text-muted"}`}
          >
            {item}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function SignalProvenance({
  signal,
  locale,
}: {
  signal: Signal;
  locale: Locale;
}) {
  const provenance = signal.provenance;
  return (
    <section className="border-t border-ink py-5 text-sm">
      <h3 className="font-bold">
        {t(locale, "Procedencia exacta de la señal", "Exact signal provenance")}
      </h3>
      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2 [&_dd]:break-words">
        <div>
          <dt className="font-semibold">data_version</dt>
          <dd className="font-mono text-xs">{provenance.data_version}</dd>
        </div>
        <div>
          <dt className="font-semibold">source_type / legal_status</dt>
          <dd className="font-mono text-xs">
            {provenance.source_type} / {provenance.legal_status}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="font-semibold">source_url</dt>
          <dd>
            <a
              className="break-all underline"
              href={provenance.source_url}
              rel="noreferrer"
            >
              {provenance.source_url}
            </a>
          </dd>
        </div>
        <div>
          <dt className="font-semibold">retrieved_at</dt>
          <dd className="font-mono text-xs">{provenance.retrieved_at}</dd>
        </div>
        <div>
          <dt className="font-semibold">content_hash</dt>
          <dd className="break-all font-mono text-xs">
            {provenance.content_hash}
          </dd>
        </div>
        <div>
          <dt className="font-semibold">parser_version</dt>
          <dd className="font-mono text-xs">{provenance.parser_version}</dd>
        </div>
        <div>
          <dt className="font-semibold">transform_version</dt>
          <dd className="font-mono text-xs">{provenance.transform_version}</dd>
        </div>
        <div>
          <dt className="font-semibold">methodology_version</dt>
          <dd className="font-mono text-xs">{signal.methodology_version}</dd>
        </div>
      </dl>
    </section>
  );
}

export function ReviewSignalDetails({
  signal,
  locale,
  components,
}: {
  signal: Signal;
  locale: Locale;
  components?: SignalComponent[];
}) {
  const visibleComponents = components ?? signal.components;
  return (
    <details className="group mt-5 border border-ink">
      <summary className="flex min-h-12 cursor-pointer list-none items-center justify-between gap-4 bg-ink px-4 py-2 font-mono text-xs font-bold tracking-[.08em] text-paper uppercase after:text-lg after:content-['+'] group-open:after:content-['−']">
        {t(
          locale,
          "Cómo se calculó, evidencia y límites",
          "How calculated, evidence, and limits",
        )}
      </summary>
      <div className="px-4 sm:px-5">
        {visibleComponents.map((component) => {
          const analysis = component.analysis;
          if (!analysis) {
            return (
              <section
                className="border-t border-ink py-5 text-sm first:border-t-0"
                key={component.component_type}
              >
                <h3 className="font-bold">
                  {componentLabel(component.component_type, locale)} ·{" "}
                  {component.points} {t(locale, "puntos", "points")}
                </h3>
                <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Observado", "Observed")}
                    </dt>
                    <dd>
                      {component.observed_value ??
                        t(locale, "No disponible", "Unavailable")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Comparador", "Comparator")}
                    </dt>
                    <dd>{component.comparator}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="font-semibold">
                      {t(locale, "Cálculo", "Calculation")}
                    </dt>
                    <dd>{component.calculation}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="font-semibold">
                      {t(locale, "Limitaciones", "Limitations")}
                    </dt>
                    <dd>{component.limitations[locale]}</dd>
                  </div>
                </dl>
                <p className="mt-3 text-xs text-muted">
                  {t(
                    locale,
                    "El detalle analítico tipado no está disponible para este registro; su elegibilidad, compuertas y umbrales tampoco están disponibles.",
                    "Typed analytical detail is unavailable for this record; its eligibility, gates, and thresholds are also unavailable.",
                  )}
                </p>
              </section>
            );
          }
          return (
            <section
              className="border-t border-ink py-5 text-sm first:border-t-0"
              key={component.component_type}
            >
              <h3 className="font-bold">
                {componentLabel(component.component_type, locale)} ·{" "}
                {component.points} {t(locale, "puntos", "points")}
              </h3>
              <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <div>
                  <dt className="font-semibold">
                    {t(locale, "Observado", "Observed")}
                  </dt>
                  <dd>
                    {component.observed_value ??
                      t(locale, "No disponible", "Unavailable")}
                  </dd>
                </div>
                <div>
                  <dt className="font-semibold">
                    {t(locale, "Comparador", "Comparator")}
                  </dt>
                  <dd>{component.comparator}</dd>
                </div>
                <div>
                  <dt className="font-semibold">
                    {t(locale, "Cálculo", "Calculation")}
                  </dt>
                  <dd>{component.calculation}</dd>
                </div>
                <div>
                  <dt className="font-semibold">
                    {t(locale, "Elegibilidad", "Eligibility")}
                  </dt>
                  <dd>
                    {analysis.eligibility === "eligible"
                      ? t(locale, "Elegible", "Eligible")
                      : t(locale, "No elegible", "Ineligible")}
                    {analysis.reason
                      ? ` · ${publishedReason(analysis.reason, locale)}`
                      : ""}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="font-semibold">
                    {t(locale, "Limitaciones", "Limitations")}
                  </dt>
                  <dd>{component.limitations[locale]}</dd>
                </div>
              </dl>
              {analysis.kind === "peer_distribution" && (
                <dl className="mt-4 grid gap-x-6 gap-y-3 border-t border-line pt-4 sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold">
                      {t(
                        locale,
                        "Tasa observada / esperada",
                        "Observed / expected rate",
                      )}
                    </dt>
                    <dd>
                      {value(analysis.observed_rate, locale)} /{" "}
                      {value(analysis.expected_rate, locale)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Pares", "Peers")}
                    </dt>
                    <dd>
                      {analysis.peer_definition} ·{" "}
                      {value(analysis.peer_count, locale)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Residual / efecto", "Residual / effect")}
                    </dt>
                    <dd>
                      {value(analysis.standardized_residual, locale)} /{" "}
                      {value(analysis.effect_pp, locale)} pp
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">p / q / ajuste</dt>
                    <dd>
                      {value(analysis.raw_p, locale)} /{" "}
                      {value(analysis.adjusted_q, locale)} ·{" "}
                      {component.adjustment_method ??
                        t(locale, "No disponible", "Unavailable")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Ajuste", "Fit")}
                    </dt>
                    <dd>{analysis.fit_method}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Punto público", "Public point")}
                    </dt>
                    <dd>
                      {analysis.public_point_eligible
                        ? t(locale, "Elegible", "Eligible")
                        : t(locale, "No elegible", "Ineligible")}
                      {analysis.analyzer_reason
                        ? ` · ${publishedReason(analysis.analyzer_reason, locale)}`
                        : ""}
                    </dd>
                  </div>
                </dl>
              )}
              {analysis.kind === "spatial_cluster" && (
                <dl className="mt-4 grid gap-x-6 gap-y-3 border-t border-line pt-4 sm:grid-cols-2">
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Unidad / grano", "Unit / grain")}
                    </dt>
                    <dd>
                      {analysis.analysis_unit_id} · {analysis.analysis_grain}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Vecinos", "Neighbours")}
                    </dt>
                    <dd>
                      {analysis.neighbor_ids.length
                        ? analysis.neighbor_ids.join(", ")
                        : t(locale, "No disponible", "Unavailable")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(
                        locale,
                        "Estadístico / residual",
                        "Statistic / residual",
                      )}
                    </dt>
                    <dd>
                      {value(analysis.local_statistic, locale)} /{" "}
                      {value(analysis.local_residual, locale)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      p / q / {t(locale, "permutaciones", "permutations")}
                    </dt>
                    <dd>
                      {value(analysis.raw_p, locale)} /{" "}
                      {value(analysis.adjusted_q, locale)} /{" "}
                      {value(analysis.permutations, locale)}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">Seed</dt>
                    <dd>
                      {analysis.seed ??
                        t(locale, "No disponible", "Unavailable")}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-semibold">
                      {t(locale, "Geocódigo", "Geocode")}
                    </dt>
                    <dd>
                      <a
                        className="underline"
                        href={analysis.geocode_source_url}
                        rel="noreferrer"
                      >
                        {t(
                          locale,
                          "Fuente de coordenadas",
                          "Coordinate source",
                        )}
                      </a>
                    </dd>
                  </div>
                </dl>
              )}
              <Hashes
                values={[
                  ["Familia", component.family_id],
                  ["Cohorte", component.cohort_hash],
                  ["Entrada", component.input_artifact_hash],
                  ["Salida", component.analyzer_output_hash],
                  ["Código", component.code_hash],
                  ["Método", component.method_hash],
                  ["Residual de pares", component.peer_residual_artifact_hash],
                  ["Fuente de coordenadas", component.coordinate_source_hash],
                ]}
              />
              <ul className="mt-4 list-disc pl-5 text-xs">
                {component.source_links.map((source) => (
                  <li key={source}>
                    <a
                      className="break-all underline"
                      href={source}
                      rel="noreferrer"
                    >
                      {source}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
        <SignalProvenance signal={signal} locale={locale} />
      </div>
    </details>
  );
}

export function OutcomeSensitivityPanel({
  outcome,
  locale,
}: {
  outcome: Outcome | null;
  locale: Locale;
}) {
  if (!outcome) {
    return (
      <aside className="h-full border border-ink bg-ink p-5 text-paper sm:p-6">
        <p className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase">
          {t(locale, "Sensibilidad del resultado", "Outcome sensitivity")}
        </p>
        <p className="mt-4 text-sm leading-6 text-[#9B9B9B]">
          {t(
            locale,
            "No disponible para esta versión pública. La ausencia no equivale a cero ni permite una conclusión sobre el resultado.",
            "Not available for this public release. Its absence is not zero and does not support a conclusion about the outcome.",
          )}
        </p>
        <details className="group mt-5 border-t border-[#9B9B9B] pt-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 font-mono text-xs font-bold tracking-[.06em] uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
            {t(locale, "Fuente, grano y límites", "Source, grain, and limits")}
          </summary>
          <dl className="mt-2 grid gap-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="font-semibold">{t(locale, "Fuente", "Source")}</dt>
              <dd>{t(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-semibold">{t(locale, "Grano", "Grain")}</dt>
              <dd>{t(locale, "No disponible", "Unavailable")}</dd>
            </div>
            <div>
              <dt className="font-semibold">
                {t(locale, "Límites", "Limits")}
              </dt>
              <dd>{t(locale, "No disponible", "Unavailable")}</dd>
            </div>
          </dl>
        </details>
      </aside>
    );
  }
  if (!outcome.evaluable) {
    return (
      <aside
        className="h-full border border-ink bg-ink p-5 text-paper sm:p-6"
        aria-labelledby="outcome-sensitivity-title"
      >
        <p
          id="outcome-sensitivity-title"
          className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase"
        >
          {t(locale, "Sensibilidad del resultado", "Outcome sensitivity")}
        </p>
        <p className="mt-3 font-display text-xl font-bold leading-tight tracking-[-0.035em] uppercase sm:text-2xl">
          {t(locale, "No evaluable", "Not evaluable")}
        </p>
        <p className="mt-3 text-sm leading-6 text-[#9B9B9B]">
          {t(
            locale,
            "Esta versión no puede evaluar ni publicar límites de decisión porque faltan entradas compatibles o no se cumplieron sus compuertas.",
            "This version cannot evaluate or publish decision bounds because compatible inputs are missing or their gates were not met.",
          )}
        </p>
        <div className="mt-5 border border-[#9B9B9B] p-4">
          <h3 className="font-mono text-[11px] font-bold tracking-[.06em] text-[#9B9B9B] uppercase">
            {t(locale, "Condiciones que bloquean", "Blocking conditions")}
          </h3>
          {outcome.issues.length ? (
            <ul className="mt-3 list-disc space-y-2 pl-5 text-sm">
              {outcome.issues.map((item) => (
                <li key={`${item.code}-${item.record_ids.join("-")}`}>
                  {publishedReason(item.code, locale)}
                  {item.record_ids.length
                    ? ` · ${item.record_ids.join(", ")}`
                    : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#9B9B9B]">
              {t(
                locale,
                "No se suministró una condición bloqueante tipada; el estado permanece no evaluable.",
                "No typed blocking condition was supplied; the status remains not evaluable.",
              )}
            </p>
          )}
        </div>
        <details className="group mt-5 border-t border-[#9B9B9B] pt-3">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 font-mono text-xs font-bold tracking-[.06em] uppercase after:text-lg after:content-['+'] group-open:after:content-['−'] [&::-webkit-details-marker]:hidden">
            {t(
              locale,
              "Cálculo, límites y procedencia",
              "Calculation, limits, and provenance",
            )}
          </summary>
          <p className="mt-2 text-sm text-[#9B9B9B]">{outcome.calculation}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
            {outcome.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <ul className="mt-3 list-disc pl-5 text-xs">
            {outcome.source_links.map((source) => (
              <li key={source}>
                <a
                  className="break-all text-neon underline"
                  href={source}
                  rel="noreferrer"
                >
                  {source}
                </a>
              </li>
            ))}
          </ul>
          <Hashes
            inverse
            values={[
              [t(locale, "Evidencia", "Evidence"), outcome.evidence_hash],
              [t(locale, "Salida", "Output"), outcome.output_hash],
            ]}
          />
        </details>
      </aside>
    );
  }
  const status = {
    not_evaluable: t(locale, "No evaluable", "Not evaluable"),
    robust_within_evaluated_bounds: t(
      locale,
      "Robusto dentro de los límites evaluados",
      "Robust within evaluated bounds",
    ),
    tie_within_verified_bound: t(
      locale,
      "Empate posible dentro del límite verificado",
      "Tie possible within verified bound",
    ),
    lead_change_within_verified_bound: t(
      locale,
      "Cambio de liderazgo posible dentro del límite verificado",
      "Lead change possible within verified bound",
    ),
    tie_only_with_unresolved_bound: t(
      locale,
      "Empate posible solo al incluir registros no resueltos",
      "Tie possible only including unresolved records",
    ),
    lead_change_only_with_unresolved_bound: t(
      locale,
      "Cambio de liderazgo posible solo al incluir registros no resueltos",
      "Lead change possible only including unresolved records",
    ),
  }[outcome.status];
  const count = (item: number | null) =>
    item === null
      ? t(locale, "No disponible", "Not available")
      : formatNumber(item, locale);
  return (
    <aside
      className="h-full border border-ink border-t-4 border-t-neon bg-ink p-5 text-paper sm:p-6"
      aria-labelledby="outcome-sensitivity-title"
    >
      <p
        id="outcome-sensitivity-title"
        className="font-mono text-[11px] font-bold tracking-[.1em] text-[#9B9B9B] uppercase"
      >
        {t(locale, "Sensibilidad del resultado", "Outcome sensitivity")}
      </p>
      <p className="mt-3 break-words font-display text-xl font-bold leading-tight tracking-[-0.035em] uppercase sm:text-2xl">
        {status}
      </p>
      <p className="mt-3 text-sm leading-6 text-[#9B9B9B]">
        {t(
          locale,
          "Compara el margen observado con cotas de evidencia documental autenticada. No establece por sí sola una conclusión jurídica; los datos estadísticos e históricos no son votos afectados.",
          "It compares the observed margin with bounds from authenticated documentary evidence. It does not itself establish a legal conclusion; statistical and historical data are not affected votes.",
        )}
      </p>
      <dl className="mt-5 grid border border-[#9B9B9B] text-sm">
        <div className="border-b border-[#9B9B9B] p-3">
          <dt className="font-mono text-[11px] font-semibold tracking-[.06em] text-[#9B9B9B] uppercase">
            {t(locale, "Margen observado", "Observed margin")}
          </dt>
          <dd>{count(outcome.observed_margin_votes)}</dd>
        </div>
        <div className="border-b border-[#9B9B9B] p-3">
          <dt className="font-mono text-[11px] font-semibold tracking-[.06em] text-[#9B9B9B] uppercase">
            {t(
              locale,
              "Cota verificada de cambio de margen",
              "Verified margin-shift bound",
            )}
          </dt>
          <dd>{count(outcome.verified_margin_shift_bound)}</dd>
        </div>
        <div className="border-b border-[#9B9B9B] p-3">
          <dt className="font-mono text-[11px] font-semibold tracking-[.06em] text-[#9B9B9B] uppercase">
            {t(
              locale,
              "Cota no resuelta de cambio de margen",
              "Unresolved margin-shift bound",
            )}
          </dt>
          <dd>{count(outcome.unresolved_margin_shift_upper_bound)}</dd>
        </div>
        <div className="p-3">
          <dt className="font-mono text-[11px] font-semibold tracking-[.06em] text-[#9B9B9B] uppercase">
            {t(
              locale,
              "Margen restante: verificado / combinado",
              "Headroom: verified / combined",
            )}
          </dt>
          <dd>
            {count(outcome.verified_margin_headroom)} /{" "}
            {count(outcome.combined_margin_headroom)}
          </dd>
        </div>
      </dl>
      <details className="group mt-5 border-t border-[#9B9B9B] pt-3">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 font-mono text-xs font-bold tracking-[.06em] uppercase after:text-lg after:content-['+'] group-open:after:content-['−']">
          {t(
            locale,
            "Alcance, supuestos y procedencia",
            "Scope, assumptions, and provenance",
          )}
        </summary>
        <dl className="mt-2 grid gap-3 text-sm sm:grid-cols-2 [&_dd]:break-words">
          <div>
            <dt className="font-semibold">{t(locale, "Alcance", "Scope")}</dt>
            <dd>
              {outcome.scope
                ? `${outcome.scope.level}: ${outcome.scope.key.join(" / ")}`
                : t(locale, "No disponible", "Not available")}
            </dd>
          </div>
          <div>
            <dt className="font-semibold">
              {t(locale, "Fuente del resultado", "Outcome source")}
            </dt>
            <dd>
              {outcome.outcome_source
                ? `${sourceTypeLabel(locale, outcome.outcome_source.source_type)} · ${legalStatusLabel(locale, outcome.outcome_source.legal_status)} · ${outcome.outcome_source.fact_grain}`
                : t(locale, "No disponible", "Not available")}
            </dd>
          </div>
          <div>
            <dt className="font-semibold">
              {t(locale, "Factor de cambio de margen", "Margin-shift factor")}
            </dt>
            <dd>{outcome.margin_shift_factor}</dd>
          </div>
          <div>
            <dt className="font-semibold">
              {t(
                locale,
                "Registros verificados / no resueltos",
                "Verified / unresolved records",
              )}
            </dt>
            <dd>
              {outcome.verified_record_ids?.length ??
                t(locale, "No disponible", "Not available")}{" "}
              /{" "}
              {outcome.unresolved_record_ids?.length ??
                t(locale, "No disponible", "Not available")}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-[#9B9B9B]">{outcome.calculation}</p>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
          {outcome.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
          {outcome.issues.map((item) => (
            <li key={item.code}>
              {t(locale, "Condición reportada", "Reported condition")}:{" "}
              {publishedReason(item.code, locale)}
              {item.record_ids.length ? ` · ${item.record_ids.join(", ")}` : ""}
            </li>
          ))}
        </ul>
        <ul className="mt-3 list-disc pl-5 text-xs">
          {outcome.source_links.map((source) => (
            <li key={source}>
              <a
                className="break-all text-neon underline"
                href={source}
                rel="noreferrer"
              >
                {source}
              </a>
            </li>
          ))}
        </ul>
        <Hashes
          inverse
          values={[
            [t(locale, "Evidencia", "Evidence"), outcome.evidence_hash],
            [t(locale, "Salida", "Output"), outcome.output_hash],
          ]}
        />
      </details>
    </aside>
  );
}
