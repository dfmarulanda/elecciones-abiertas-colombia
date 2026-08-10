"use client";

import { SOURCE_TYPES } from "@elecciones/contracts/enums";
import Link from "next/link";
import { ArrowUpDown, Download, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import React from "react";
import type { components } from "@elecciones/contracts";
import type {
  FixtureRelease,
  HistoricalComparison,
  PublicExplorer,
} from "@/data/fixture-adapter";
import {
  fixtureResultCsvUrl,
  resultHref,
  serializeApiResultFilters,
  serializeResultFilters,
  type ResultFilters,
} from "@/lib/result-filters";
import { formatNumber } from "@/lib/utils";
import { geographyRoute, mesaRoute } from "@/lib/explorer-routing";
import type { PublicResultLabels } from "@/lib/public-labels";
import { GeographicCoverageNotice } from "./geographic-coverage-notice";
import { MapLauncher } from "./map-launcher";

type Row = {
  mesa: string;
  geography: string;
  department: string;
  geographyId: string;
  municipalityId: string;
  departmentId: string;
  source: string;
  candidate: string;
  candidateId: string;
  ballot: string;
  votes: number | null;
  votesStatus: "observed" | "unknown" | "unavailable" | "not_applicable";
  voters: number | null;
  hash: string;
};
type SortKey = "mesa" | "geography" | "candidate" | "votes" | "source";
const label = (locale: "es" | "en", es: string, en: string) =>
  locale === "es" ? es : en;
const filterGridClass =
  "mt-8 grid gap-px border border-ink bg-ink p-px sm:grid-cols-2 lg:grid-cols-4";
const filterFieldClass = "bg-paper p-3 text-sm font-bold";
const filterControlClass =
  "mt-2 min-h-11 w-full border border-ink bg-paper px-3 text-sm";
const kickerClass =
  "inline-flex bg-neon px-2 py-1 font-mono text-xs font-bold tracking-[.14em] text-ink uppercase";

function LegacyResultsExplorer({
  release,
  locale,
  filters,
  enumLabels,
}: {
  release: FixtureRelease;
  locale: "es" | "en";
  filters: ResultFilters;
  enumLabels: PublicResultLabels;
}) {
  const names = new Map(
    release.election.candidates.map((candidate) => [candidate.id, candidate]),
  );
  const geo = new Map(release.geographies.map((item) => [item.id, item]));
  const [sort, setSort] = useState<{
    key: SortKey;
    descending: boolean;
  } | null>(null);
  const rows = useMemo(
    () =>
      release.results.flatMap((result) =>
        result.candidates.map((entry) => {
          const candidate = names.get(entry.candidate_id);
          const mesa = release.mesas.find((item) => item.id === result.mesa_id);
          const department = geo.get(mesa?.department_id ?? "")?.name ?? "—";
          const geography =
            geo.get(mesa?.municipality_id ?? "")?.name ??
            geo.get(result.geography_id)?.name ??
            "—";
          return {
            mesa: result.mesa_id ?? "—",
            geography,
            department,
            geographyId: result.geography_id,
            municipalityId: mesa?.municipality_id ?? "",
            departmentId: mesa?.department_id ?? "",
            source: result.provenance.source_type,
            candidate: candidate?.name[locale] ?? entry.candidate_id,
            candidateId: entry.candidate_id,
            ballot: String(candidate?.ballot_number ?? "—"),
            votes: entry.votes.value,
            votesStatus: entry.votes.status,
            voters: result.voters.value,
            hash: result.provenance.content_hash,
          };
        }),
      ),
    [release, locale],
  );
  const filtered = useMemo(
    () =>
      rows.filter(
        (row) =>
          (!filters.source || row.source === filters.source) &&
          (!filters.geography ||
            [
              row.geographyId,
              row.municipalityId,
              row.departmentId,
              row.mesa,
            ].includes(filters.geography)) &&
          (!filters.candidate || row.candidateId === filters.candidate) &&
          (!filters.ballot || row.ballot === filters.ballot),
      ),
    [filters, rows],
  );
  const sortedRows = useMemo(() => {
    if (!sort) return filtered;
    return [...filtered].sort((left, right) => {
      const leftValue = left[sort.key];
      const rightValue = right[sort.key];
      const comparison =
        typeof leftValue === "number" && typeof rightValue === "number"
          ? leftValue - rightValue
          : String(leftValue ?? "").localeCompare(
              String(rightValue ?? ""),
              locale,
            );
      return sort.descending ? -comparison : comparison;
    });
  }, [filtered, locale, sort]);
  const toggleSort = (key: SortKey) =>
    setSort((current) => ({
      key,
      descending: current?.key === key ? !current.descending : false,
    }));
  const columns: Array<{ key: SortKey; text: string }> = [
    { key: "mesa", text: label(locale, "Mesa", "Mesa") },
    { key: "geography", text: label(locale, "Geografía", "Geography") },
    {
      key: "candidate",
      text: label(locale, "Candidatura / tarjeta", "Candidate / ballot"),
    },
    { key: "votes", text: label(locale, "Votos", "Votes") },
    { key: "source", text: label(locale, "Capa", "Layer") },
  ];
  const voteDisplay = (row: Row) =>
    row.votesStatus === "observed"
      ? formatNumber(row.votes, locale)
      : {
          unknown: label(locale, "Desconocido", "Unknown"),
          unavailable: label(locale, "No disponible", "Unavailable"),
          not_applicable: label(locale, "No aplica", "Not applicable"),
        }[row.votesStatus];
  const geographyRows = [
    ...new Map(
      release.mesas.map((mesa) => [
        mesa.department_id,
        geo.get(mesa.department_id)?.name ?? mesa.department_id,
      ]),
    ).entries(),
  ].map(([id, name]) => ({
    geographyId: id,
    label: name,
    value: String(
      release.mesas.filter((mesa) => mesa.department_id === id).length,
    ),
    href: geographyRoute(locale, id, filters),
  }));
  const current = (next: Partial<ResultFilters>) =>
    resultHref(locale, { ...filters, ...next });
  const ballotCandidateId = release.election.candidates.find(
    (candidate) => String(candidate.ballot_number) === filters.ballot,
  )?.id;
  const csvQuery = serializeApiResultFilters(
    filters,
    ballotCandidateId,
    release.release.data_version,
  );
  const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";
  const csv = release.release.synthetic
    ? fixtureResultCsvUrl(filtered, release.release.data_version)
    : `${apiBase}/api/v1/elections/${release.election.slug}/results?${csvQuery}`;
  const nextPage = release.result_page?.next_cursor
    ? `${resultHref(locale, filters)}${serializeResultFilters(filters) ? "&" : "?"}cursor=${encodeURIComponent(release.result_page.next_cursor)}`
    : null;
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] px-4 py-8 sm:px-8 sm:py-12 xl:px-20"
    >
      <div
        className="border border-ink bg-paper px-4 py-3 text-sm leading-6"
        role="status"
      >
        <strong className="mr-2 inline-block bg-ink px-2 py-1 font-mono text-xs tracking-[.08em] text-paper uppercase">
          {release.release.synthetic
            ? label(locale, "FIJACIÓN SINTÉTICA.", "SYNTHETIC FIXTURE.")
            : release.release.status === "candidate"
              ? label(
                  locale,
                  "RELEASE CANDIDATO · LECTURA PRELIMINAR.",
                  "CANDIDATE RELEASE · PRELIMINARY READING.",
                )
              : release.release.status === "withdrawn"
                ? label(locale, "RELEASE RETIRADO.", "WITHDRAWN RELEASE.")
                : label(locale, "RELEASE INMUTABLE.", "IMMUTABLE RELEASE.")}
        </strong>{" "}
        {release.fixture_notice[locale]}
      </div>
      <div className="mt-4">
        <GeographicCoverageNotice
          coverage={release.summary.geographic_collection_coverage ?? undefined}
          locale={locale}
        />
      </div>
      <div className="mt-8 border-b border-ink pb-8 sm:pb-10">
        <div className="flex min-w-0 flex-wrap items-end justify-between gap-5">
          <div className="min-w-0 max-w-full flex-1 basis-[32rem]">
            <p className={kickerClass}>
              {label(locale, "Explorador público", "Public explorer")}
            </p>
            <h1 className="mt-4 min-w-0 max-w-full font-display text-[clamp(2rem,6vw,4.5rem)] font-normal leading-[.95]">
              {label(locale, "Resultados por mesa", "Mesa-level results")}
            </h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              {label(
                locale,
                release.release.synthetic
                  ? "Filtros en la URL, lectura por tabla primero y trazabilidad por registro. Los valores son sintéticos."
                  : "Filtros en la URL, lectura por tabla primero y trazabilidad por registro.",
                release.release.synthetic
                  ? "URL-addressable filters, table-first reading, and record-level provenance. Values are synthetic."
                  : "URL-addressable filters, table-first reading, and record-level provenance.",
              )}
            </p>
          </div>
          <div className="flex min-w-0 max-w-full flex-wrap gap-2">
            <MapLauncher locale={locale} rows={geographyRows} />
            <a
              className="inline-flex min-h-11 items-center gap-2 border border-ink bg-ink px-4 text-sm font-bold text-paper hover:bg-neon hover:text-ink"
              href={csv}
              download={
                release.release.synthetic
                  ? `resultados-${release.release.data_version}.csv`
                  : undefined
              }
            >
              <Download className="size-4" />
              CSV {label(locale, "con estos filtros", "with these filters")}
            </a>
          </div>
        </div>
      </div>
      <form
        className={filterGridClass}
        aria-label={label(locale, "Filtros de resultados", "Result filters")}
      >
        <label className={filterFieldClass}>
          {label(locale, "Fuente", "Source")}
          <select
            className={filterControlClass}
            value={filters.source ?? ""}
            onChange={(event) =>
              location.assign(
                current({ source: event.target.value || undefined }),
              )
            }
          >
            <option value="">{label(locale, "Todas", "All")}</option>
            {SOURCE_TYPES.map((sourceType) => (
              <option value={sourceType} key={sourceType}>
                {enumLabels.source[sourceType] ?? enumLabels.unknown}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Geografía", "Geography")}
          <select
            className={filterControlClass}
            value={filters.geography ?? ""}
            onChange={(event) =>
              location.assign(
                current({ geography: event.target.value || undefined }),
              )
            }
          >
            <option value="">{label(locale, "Todas", "All")}</option>
            {[
              ...new Map(
                rows.map((row) => [row.geographyId, row.geography]),
              ).entries(),
            ].map(([identifier, name]) => (
              <option value={identifier} key={identifier}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Candidatura", "Candidate")}
          <select
            className={filterControlClass}
            value={filters.candidate ?? ""}
            onChange={(event) =>
              location.assign(
                current({ candidate: event.target.value || undefined }),
              )
            }
          >
            <option value="">{label(locale, "Todas", "All")}</option>
            {release.election.candidates.map((candidate) => (
              <option value={candidate.id} key={candidate.id}>
                {candidate.name[locale]} · {candidate.ballot_number}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Tarjeta", "Ballot")}
          <select
            className={filterControlClass}
            value={filters.ballot ?? ""}
            onChange={(event) =>
              location.assign(
                current({ ballot: event.target.value || undefined }),
              )
            }
          >
            <option value="">{label(locale, "Todas", "All")}</option>
            {release.election.candidates.map((candidate) => (
              <option
                value={String(candidate.ballot_number)}
                key={candidate.id}
              >
                {candidate.ballot_number}
              </option>
            ))}
          </select>
        </label>
      </form>
      <p className="mt-4 text-sm text-muted" aria-live="polite">
        {filtered.length}{" "}
        {label(
          locale,
          "filas de candidatura; cada una identifica nombre y tarjeta.",
          "candidate rows; each identifies name and ballot.",
        )}
      </p>
      <p className="mt-4 text-xs leading-5 text-muted md:hidden">
        {label(
          locale,
          "Deslice horizontalmente la tabla para ver todas las columnas.",
          "Scroll the table horizontally to view every column.",
        )}
      </p>
      <div
        className="mt-2 overflow-x-auto border border-ink bg-paper md:mt-4"
        role="region"
        aria-label={label(
          locale,
          "Tabla de resultados desplazable horizontalmente",
          "Horizontally scrollable results table",
        )}
        tabIndex={0}
      >
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">
            {label(
              locale,
              "Resultados filtrados por mesa",
              "Filtered mesa results",
            )}
          </caption>
          <thead className="bg-ink text-xs tracking-[.08em] text-paper uppercase">
            <tr>
              {columns.map((column) => (
                <th
                  className="px-4 py-3"
                  key={column.key}
                  aria-sort={
                    sort?.key === column.key
                      ? sort.descending
                        ? "descending"
                        : "ascending"
                      : "none"
                  }
                >
                  <button
                    type="button"
                    className="inline-flex min-h-11 items-center gap-1 font-bold"
                    onClick={() => toggleSort(column.key)}
                  >
                    {column.text}
                    <ArrowUpDown className="size-3" aria-hidden="true" />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row) => (
              <tr
                className="border-t border-ink hover:bg-neon/15"
                key={`${row.hash}-${row.candidateId}`}
              >
                <td className="px-4 py-4">
                  <Link
                    className="font-mono text-xs underline decoration-ink underline-offset-4"
                    href={`/${locale}/resultados/mesa/${row.mesa}`}
                  >
                    {row.mesa}
                  </Link>
                </td>
                <td className="px-4 py-4">{row.geography}</td>
                <td className="px-4 py-4">
                  <strong>{row.candidate}</strong> ·{" "}
                  {label(locale, "Tarjeta", "Ballot")} {row.ballot}
                </td>
                <td className="px-4 py-4">{voteDisplay(row)}</td>
                <td className="px-4 py-4">
                  {enumLabels.source[row.source] ?? enumLabels.unknown}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && (
        <p className="mt-4 border border-ink p-4 text-sm">
          {label(
            locale,
            "No hay registros para esta combinación. Un valor cero, desconocido o no disponible se conserva cuando exista en el release.",
            "There are no records for this combination. A zero, unknown, or unavailable value is retained when present in the release.",
          )}
        </p>
      )}
      {release.result_page?.has_more && nextPage && (
        <nav
          className="mt-6 flex justify-end"
          aria-label={label(locale, "Paginación", "Pagination")}
        >
          <Link
            className="inline-flex min-h-11 items-center border border-ink px-4 text-sm font-bold hover:bg-ink hover:text-paper"
            href={nextPage}
          >
            {label(locale, "Siguiente página", "Next page")}
          </Link>
        </nav>
      )}
      <section
        className="mt-10 border-y border-ink py-7 sm:py-9"
        aria-labelledby="historical-comparison"
      >
        <p className={kickerClass}>
          {label(locale, "Comparación histórica", "Historical comparison")}
        </p>
        <div className="mt-3 grid gap-6 lg:grid-cols-[1.15fr_.85fr] lg:items-end">
          <div>
            <h2
              id="historical-comparison"
              className="font-display text-3xl font-normal leading-tight"
            >
              {label(
                locale,
                "Cambios comparables, cuando la evidencia lo permita",
                "Comparable changes, only when the evidence allows",
              )}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
              {label(
                locale,
                "La comparación estará disponible para 2026 segunda y primera vuelta, y 2022 segunda y primera vuelta. Solo mostrará una lectura cuando código, geografía, capa de fuente y nivel territorial estén conciliados; una coincidencia de nombre entre años no prueba que sea la misma unidad.",
                "Comparison will be available for the 2026 second and first rounds, and the 2022 second and first rounds. It will show a reading only when code, geography, source layer, and territorial grain are reconciled; a matching name across years does not prove it is the same unit.",
              )}
            </p>
          </div>
          <div className="border border-ink bg-paper px-4 py-4 text-sm leading-6">
            <p className="font-bold">
              {label(locale, "Aún no disponible", "Not yet available")}
            </p>
            <p className="mt-1 text-muted">
              {label(
                locale,
                "No hay valores históricos inventados en esta versión. El adaptador publicará únicamente pares reconciliados y su proveniencia.",
                "This release contains no invented historical values. The adapter will publish reconciled pairs and their provenance only.",
              )}
            </p>
          </div>
        </div>
        <div
          className="mt-6 grid gap-px border border-ink bg-ink sm:grid-cols-2 lg:grid-cols-4"
          aria-label={label(
            locale,
            "Contextos de comparación pendientes",
            "Pending comparison contexts",
          )}
        >
          {[
            label(locale, "2026 · segunda vuelta", "2026 · second round"),
            label(locale, "2026 · primera vuelta", "2026 · first round"),
            label(locale, "2022 · segunda vuelta", "2022 · second round"),
            label(locale, "2022 · primera vuelta", "2022 · first round"),
          ].map((election) => (
            <div className="bg-paper px-4 py-3" key={election}>
              <p className="font-mono text-xs font-bold tracking-[.08em] text-ink uppercase">
                {election}
              </p>
              <p className="mt-1 text-xs text-muted">
                {label(
                  locale,
                  "Pendiente de fuente y grano compatible",
                  "Awaiting compatible source and grain",
                )}
              </p>
            </div>
          ))}
        </div>
        <details className="mt-5 border-t border-ink pt-3">
          <summary className="min-h-11 cursor-pointer py-2 text-sm font-bold">
            {label(
              locale,
              "Ver requisito de compatibilidad",
              "View compatibility requirement",
            )}
          </summary>
          <p className="max-w-3xl pb-2 text-sm leading-6 text-muted">
            {label(
              locale,
              "Las comparaciones municipales o por mesa requerirán identificadores estables reconciliados y procedencia verificable en ambos años. Si falta cualquiera de esas condiciones, el estado será ‘no disponible’, no cero ni una estimación.",
              "Municipal or mesa comparisons will require reconciled stable identifiers and verifiable provenance in both years. If either condition is missing, the state will be ‘unavailable,’ not zero or an estimate.",
            )}
          </p>
        </details>
      </section>
      <section
        className="mt-10 border-t border-ink pt-7"
        aria-labelledby="drilldown"
      >
        <h2 id="drilldown" className="font-display text-2xl font-normal">
          {label(locale, "Profundizar por geografía", "Geography drill-down")}
        </h2>
        <p className="mt-2 text-sm text-muted">
          {label(
            locale,
            "Elija departamento, municipio, puesto y mesa mediante rutas permanentes; la vista de mesa conserva su fuente y huella.",
            "Use permanent department, municipality, polling-place, and mesa routes; the mesa view retains its source and hash.",
          )}
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          {release.geographies
            .filter((item) => item.level === "department")
            .map((item) => (
              <Link
                className="inline-flex min-h-11 items-center gap-2 border border-ink px-4 text-sm font-semibold hover:bg-neon"
                href={`/${locale}/resultados/departamento/${item.id}`}
                key={item.id}
              >
                {item.name}
                <ExternalLink className="size-3" />
              </Link>
            ))}
        </div>
      </section>
    </main>
  );
}

type NormalizedFact = components["schemas"]["ResultFact"];
type CategoryPage = {
  items: Array<{
    category_key: string;
    category_name: string;
    votes: number | null;
    status: NormalizedFact["voters"]["status"];
  }>;
  sparse_category_semantics: string;
};

function apiUrl(pathname: string) {
  const base = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  return base ? `${base}${pathname}` : pathname;
}

function metricDisplay(metric: NormalizedFact["voters"], locale: "es" | "en") {
  if (metric.status === "observed") return formatNumber(metric.value, locale);
  return {
    unknown: label(locale, "Desconocido", "Unknown"),
    unavailable: label(locale, "No disponible", "Unavailable"),
    not_applicable: label(locale, "No aplica", "Not applicable"),
  }[metric.status];
}

function FactDepth({
  fact,
  explorer,
  locale,
}: {
  fact: NormalizedFact;
  explorer: PublicExplorer;
  locale: "es" | "en";
}) {
  const selected = explorer.selected;
  const endpoint = selected
    ? `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}/result-facts/${encodeURIComponent(fact.id)}/categories?limit=50`
    : null;
  const [open, setOpen] = useState(false);
  const [categories, setCategories] = useState<{
    state: "idle" | "loading" | "error" | "ready";
    data?: CategoryPage;
  }>({ state: "idle" });
  const requestedEndpoint = useRef<string | null>(null);
  useEffect(() => {
    if (!open || !endpoint || requestedEndpoint.current === endpoint) return;
    requestedEndpoint.current = endpoint;
    let active = true;
    setCategories({ state: "loading" });
    void fetch(apiUrl(endpoint), { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`${response.status}`);
        return (await response.json()) as CategoryPage;
      })
      .then((data) => active && setCategories({ state: "ready", data }))
      .catch(() => active && setCategories({ state: "error" }));
    return () => {
      active = false;
    };
  }, [endpoint, open]);
  return (
    <details
      className="border-t border-ink bg-ink px-4 py-2 text-paper"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="min-h-11 cursor-pointer py-2 text-sm font-bold">
        {label(
          locale,
          "Profundizar: categorías y procedencia",
          "Go deeper: categories and provenance",
        )}
      </summary>
      <div className="grid gap-px border-t border-paper/20 bg-paper/20 pb-px pt-px text-sm leading-6 lg:grid-cols-2">
        <div className="bg-ink p-4">
          <p className="font-bold">
            {label(locale, "Procedencia exacta", "Exact provenance")}
          </p>
          <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 break-words text-paper/70">
            <dt>{label(locale, "Fuente", "Source")}</dt>
            <dd>{fact.provenance.source_type}</dd>
            <dt>{label(locale, "Estado jurídico", "Legal status")}</dt>
            <dd>{fact.provenance.legal_status}</dd>
            <dt>Hash</dt>
            <dd className="font-mono text-xs">
              {fact.provenance.content_hash}
            </dd>
            <dt>Parser</dt>
            <dd>{fact.provenance.parser_version}</dd>
            <dt>Transform</dt>
            <dd>{fact.provenance.transform_version}</dd>
            <dt>{label(locale, "Versión", "Version")}</dt>
            <dd>{fact.provenance.data_version}</dd>
          </dl>
          <a
            className="mt-3 inline-flex min-h-11 items-center underline decoration-neon underline-offset-4"
            href={fact.provenance.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {label(locale, "Abrir fuente publicada", "Open published source")}
          </a>
        </div>
        <div className="bg-ink p-4">
          <p className="font-bold">
            {label(locale, "Categorías de fuente", "Source categories")}
          </p>
          {categories.state === "loading" ? (
            <p className="mt-2 text-paper/70">
              {label(locale, "Cargando categorías…", "Loading categories…")}
            </p>
          ) : null}
          {categories.state === "error" ? (
            <p className="mt-2 border border-paper/30 p-3 text-paper/70">
              {label(
                locale,
                "Las categorías no están disponibles ahora. Ninguna ausencia se interpreta como cero.",
                "Categories are unavailable right now. An absence is never interpreted as zero.",
              )}
            </p>
          ) : null}
          {categories.data ? (
            <>
              <p className="mt-2 text-xs text-paper/70">
                {categories.data.sparse_category_semantics}
              </p>
              <ul className="mt-2 divide-y divide-paper/20 border-y border-paper/20">
                {categories.data.items.map((category) => (
                  <li className="py-2" key={category.category_key}>
                    <span className="font-semibold">
                      {category.category_name}
                    </span>
                    <span className="ml-2 tabular-nums">
                      {category.status === "observed"
                        ? formatNumber(category.votes, locale)
                        : metricDisplay(
                            { value: category.votes, status: category.status },
                            locale,
                          )}
                    </span>
                    <span className="ml-2 text-xs text-paper/70">
                      {category.category_key}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      </div>
    </details>
  );
}

function comparisonText(comparison: HistoricalComparison, locale: "es" | "en") {
  if (comparison.comparison_status === "not_comparable") {
    const reasons = {
      missing_geography_crosswalk: label(
        locale,
        "Falta la tabla de equivalencia geográfica.",
        "The geography crosswalk is missing.",
      ),
      geography_crosswalk_unapproved: label(
        locale,
        "La equivalencia geográfica no está aprobada.",
        "The geography crosswalk is not approved.",
      ),
      missing_semantic_crosswalk: label(
        locale,
        "Falta la equivalencia de categorías.",
        "The category crosswalk is missing.",
      ),
      semantic_crosswalk_unapproved: label(
        locale,
        "La equivalencia de categorías no está aprobada.",
        "The category crosswalk is not approved.",
      ),
      no_compatible_facts: label(
        locale,
        "No hay hechos publicados compatibles para este par.",
        "There are no compatible published facts for this pair.",
      ),
    };
    return reasons[comparison.reason];
  }
  return comparison.comparison_status === "descriptive_context_only"
    ? label(
        locale,
        "Contexto descriptivo únicamente: no es elegible para análisis de integridad.",
        "Descriptive context only: it is not eligible for integrity analysis.",
      )
    : label(
        locale,
        "Pares comparables aprobados.",
        "Approved comparable pairs.",
      );
}

function NormalizedResultsExplorer({
  explorer,
  locale,
  filters,
  enumLabels,
}: {
  explorer: PublicExplorer;
  locale: "es" | "en";
  filters: ResultFilters;
  enumLabels: PublicResultLabels;
}) {
  const selected = explorer.selected;
  const preliminary =
    selected?.exposure_class === "preliminary" ||
    selected?.status === "candidate";
  const current = (next: Partial<ResultFilters>) =>
    resultHref(locale, {
      ...filters,
      ...next,
      cursor: undefined,
    } as ResultFilters);
  const nextPage = explorer.results.page.next_cursor
    ? `${resultHref(locale, filters)}${serializeResultFilters(filters) ? "&" : "?"}cursor=${encodeURIComponent(explorer.results.page.next_cursor)}`
    : null;
  const csvQuery = new URLSearchParams({ format: "csv" });
  if (filters.source) csvQuery.set("source_type", filters.source);
  if (filters.geography) csvQuery.set("geography_id", filters.geography);
  if (filters.geographyPath)
    csvQuery.set("geography_path", filters.geographyPath);
  if (filters.level) csvQuery.set("geography_level", filters.level);
  if (filters.category) csvQuery.set("category_key", filters.category);
  if (filters.status) csvQuery.set("status", filters.status);
  const csv = selected
    ? apiUrl(
        `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}/results?${csvQuery}`,
      )
    : undefined;
  const sourceTypes = [
    ...new Set(selected?.sources.map((source) => source.source_type) ?? []),
  ];
  const levels = [
    ...new Set(explorer.results.items.map((fact) => fact.geography_level)),
  ];
  const scopedFilters: ResultFilters = {
    release: selected?.release_id,
    election: selected?.election_slug,
    source: filters.source,
    sourceId: filters.sourceId,
  };
  const historicalReleases = explorer.releases.filter(
    (item) =>
      item.release_id !== selected?.release_id ||
      item.election_slug !== selected?.election_slug,
  );
  const selectedBaseline = historicalReleases.find(
    (item) =>
      item.release_id === filters.baselineRelease &&
      item.election_slug === filters.baselineElection,
  );
  const baselineValue = (item: (typeof explorer.releases)[number]) =>
    `${item.release_id}::${item.election_slug}`;
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="mx-auto max-w-[1440px] px-4 py-8 sm:px-8 sm:py-12 xl:px-20"
    >
      <header className="border-b border-ink pb-8 sm:pb-10">
        <p className={kickerClass}>
          {label(locale, "Explorador público", "Public explorer")}
        </p>
        <h1 className="mt-4 min-w-0 max-w-full font-display text-[clamp(2rem,6vw,4.5rem)] font-normal leading-[.95]">
          {preliminary
            ? label(locale, "Resultados preliminares", "Preliminary results")
            : label(locale, "Resultados publicados", "Published results")}
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          {label(
            locale,
            "Lea esta página de resultados antes de profundizar. La cobertura y la fuente pertenecen al release seleccionado; los valores no publicados no se completan.",
            "Read this results page before going deeper. Coverage and source belong to the selected release; unpublished values are never filled in.",
          )}
        </p>
      </header>
      {explorer.error ? (
        <section className="mt-6 border border-ink bg-paper p-4" role="alert">
          <p className="font-bold">
            {label(
              locale,
              "La fuente pública no responde",
              "The public source is unavailable",
            )}
          </p>
          <p className="mt-1 text-sm">
            {label(
              locale,
              "No se muestran resultados almacenados ni se sustituye la falta por cero. Revise su conexión o vuelva a intentar.",
              "No stored results are shown and the absence is not replaced with zero. Check your connection or try again.",
            )}
          </p>
        </section>
      ) : null}
      <form
        className={filterGridClass}
        aria-label={label(
          locale,
          "Selector y filtros públicos",
          "Public selector and filters",
        )}
      >
        <label className={filterFieldClass}>
          {label(locale, "Release", "Release")}
          <select
            className={filterControlClass}
            value={selected?.release_id ?? ""}
            onChange={(event) =>
              location.assign(
                current({ release: event.target.value, election: undefined }),
              )
            }
          >
            {!selected ? (
              <option value="">
                {label(
                  locale,
                  "Selección no publicada",
                  "Unpublished selection",
                )}
              </option>
            ) : null}
            {[...new Set(explorer.releases.map((item) => item.release_id))].map(
              (release) => (
                <option key={release} value={release}>
                  {release}
                </option>
              ),
            )}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Elección", "Election")}
          <select
            className={filterControlClass}
            value={selected?.election_slug ?? ""}
            onChange={(event) =>
              location.assign(current({ election: event.target.value }))
            }
          >
            {!selected ? (
              <option value="">
                {label(
                  locale,
                  "Elección no disponible",
                  "Election unavailable",
                )}
              </option>
            ) : null}
            {(filters.release
              ? explorer.releases.filter(
                  (item) => item.release_id === filters.release,
                )
              : explorer.releases
            ).map((item) => (
              <option
                key={`${item.release_id}:${item.election_slug}`}
                value={item.election_slug}
              >
                {locale === "es" ? item.name_es : item.name_en} ·{" "}
                {item.election_date}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Fuente", "Source")}
          <select
            className={filterControlClass}
            value={filters.source ?? ""}
            onChange={(event) =>
              location.assign(
                current({ source: event.target.value || undefined }),
              )
            }
          >
            <option value="">
              {preliminary
                ? label(
                    locale,
                    "Todas las fuentes disponibles",
                    "All available sources",
                  )
                : label(locale, "Todas las publicadas", "All published")}
            </option>
            {sourceTypes.map((source) => (
              <option key={source} value={source}>
                {enumLabels.source[source] ?? enumLabels.unknown}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Nivel", "Level")}
          <select
            className={filterControlClass}
            value={filters.level ?? ""}
            onChange={(event) =>
              location.assign(
                current({ level: event.target.value || undefined }),
              )
            }
          >
            <option value="">{label(locale, "Todos", "All")}</option>
            {levels.map((level) => (
              <option key={level} value={level}>
                {enumLabels.geography[level] ?? enumLabels.unknown}
              </option>
            ))}
          </select>
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Geografía (código)", "Geography (code)")}
          <input
            className={filterControlClass}
            defaultValue={filters.geography ?? ""}
            name="geografia"
          />
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Categoría", "Category")}
          <input
            className={filterControlClass}
            defaultValue={filters.category ?? ""}
            name="categoria"
          />
        </label>
        <label className={filterFieldClass}>
          {label(locale, "Estado", "Status")}
          <select
            className={filterControlClass}
            name="status"
            defaultValue={filters.status ?? ""}
          >
            <option value="">{label(locale, "Cualquiera", "Any")}</option>
            <option value="observed">
              {label(locale, "Observado", "Observed")}
            </option>
            <option value="unavailable">
              {label(locale, "No disponible", "Unavailable")}
            </option>
          </select>
        </label>
        <div className="flex items-end bg-paper p-3">
          <button
            className="min-h-11 w-full border border-ink bg-ink px-4 text-sm font-bold text-paper hover:bg-neon hover:text-ink"
            type="submit"
          >
            {label(locale, "Aplicar filtros", "Apply filters")}
          </button>
        </div>
      </form>
      {selected ? (
        <section
          className="mt-5 grid border border-ink bg-ink text-paper sm:grid-cols-3 sm:divide-x sm:divide-paper/20"
          aria-label={label(
            locale,
            "Contexto de publicación",
            "Publication context",
          )}
        >
          <div className="border-b border-paper/20 p-4 sm:border-b-0">
            <p className="font-mono text-xs font-bold uppercase text-paper/60">
              Release
            </p>
            <p className="mt-1 break-all font-mono text-sm">
              {selected.release_id}
            </p>
          </div>
          <div className="border-b border-paper/20 p-4 sm:border-b-0">
            <p className="font-mono text-xs font-bold uppercase text-paper/60">
              {label(locale, "Estado", "Status")}
            </p>
            <p className="mt-1 font-semibold">
              {label(locale, "Publicado", "Published")}
            </p>
          </div>
          <div className="p-4">
            <p className="font-mono text-xs font-bold uppercase text-paper/60">
              {label(
                locale,
                "Cobertura de esta página",
                "This page's coverage",
              )}
            </p>
            <p className="mt-1 text-sm">
              {explorer.results.items.length}{" "}
              {label(
                locale,
                "hechos; navegación por keyset",
                "facts; keyset navigation",
              )}
            </p>
          </div>
        </section>
      ) : null}
      {explorer.geographyPath.length ? (
        <nav
          aria-label={label(locale, "Ruta geográfica", "Geography path")}
          className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
        >
          <span className="font-semibold">
            {label(locale, "Ruta:", "Path:")}
          </span>
          {explorer.geographyPath.map((item) => (
            <span
              className="inline-flex items-center gap-2 whitespace-nowrap"
              key={item.id}
            >
              <span aria-hidden="true">/</span>
              <Link
                className="inline-flex min-h-11 items-center underline decoration-ink underline-offset-4"
                href={geographyRoute(locale, item.id, scopedFilters)}
              >
                {item.name}{" "}
                <span className="ml-1 text-muted">
                  ({enumLabels.geography[item.level] ?? enumLabels.unknown})
                </span>
              </Link>
            </span>
          ))}
        </nav>
      ) : null}
      <div className="mt-6 flex flex-wrap gap-3">
        {csv ? (
          <a
            className="inline-flex min-h-11 items-center border border-ink bg-ink px-4 text-sm font-bold text-paper hover:bg-neon hover:text-ink"
            href={csv}
          >
            {label(locale, "CSV con estos filtros", "CSV with these filters")}
          </a>
        ) : null}
        <MapLauncher
          locale={locale}
          rows={explorer.results.items
            .filter((fact) => fact.geography_level === "department")
            .map((fact) => ({
              geographyId: fact.geography_id,
              label: fact.geography_id,
              value: metricDisplay(fact.voters, locale),
              href: geographyRoute(locale, fact.geography_id, scopedFilters),
            }))}
        />
      </div>
      <p className="mt-6 text-xs leading-5 text-muted md:hidden">
        {label(
          locale,
          "Deslice horizontalmente la tabla para ver todas las columnas.",
          "Scroll the table horizontally to view every column.",
        )}
      </p>
      <section
        className="mt-2 overflow-x-auto border border-ink bg-paper md:mt-6"
        aria-labelledby="facts-title"
        tabIndex={0}
      >
        <h2 id="facts-title" className="sr-only">
          {label(locale, "Hechos de resultados", "Result facts")}
        </h2>
        <table className="w-full min-w-[760px] text-left text-sm">
          <caption className="sr-only">
            {preliminary
              ? label(
                  locale,
                  "Resultados preliminares, paginados por keyset",
                  "Preliminary results, keyset paginated",
                )
              : label(
                  locale,
                  "Resultados publicados, paginados por keyset",
                  "Published results, keyset paginated",
                )}
          </caption>
          <thead className="bg-ink text-xs tracking-[.08em] text-paper uppercase">
            <tr>
              <th className="px-4 py-3">
                {label(locale, "Geografía", "Geography")}
              </th>
              <th className="px-4 py-3">{label(locale, "Nivel", "Level")}</th>
              <th className="px-4 py-3">{label(locale, "Mesa", "Mesa")}</th>
              <th className="px-4 py-3">
                {label(locale, "Votantes", "Voters")}
              </th>
              <th className="px-4 py-3">{label(locale, "Fuente", "Source")}</th>
            </tr>
          </thead>
          <tbody>
            {explorer.results.items.map((fact) => (
              <React.Fragment key={fact.id}>
                <tr className="border-t border-ink hover:bg-neon/15">
                  <td className="px-4 py-4">
                    <Link
                      className="font-mono text-xs underline decoration-ink underline-offset-4"
                      href={geographyRoute(
                        locale,
                        fact.geography_id,
                        scopedFilters,
                      )}
                    >
                      {fact.geography_id}
                    </Link>
                  </td>
                  <td className="px-4 py-4">
                    {enumLabels.geography[fact.geography_level] ??
                      enumLabels.unknown}
                  </td>
                  <td className="px-4 py-4">
                    {fact.mesa_id ? (
                      <Link
                        className="font-mono text-xs underline decoration-ink underline-offset-4"
                        href={mesaRoute(locale, fact.mesa_id, {
                          ...scopedFilters,
                          source: fact.provenance.source_type,
                        })}
                      >
                        {fact.mesa_id}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-4">
                    {metricDisplay(fact.voters, locale)}
                  </td>
                  <td className="px-4 py-4">
                    {enumLabels.source[fact.provenance.source_type] ??
                      enumLabels.unknown}
                  </td>
                </tr>
                <tr>
                  <td colSpan={5} className="p-0">
                    <FactDepth
                      fact={fact}
                      explorer={explorer}
                      locale={locale}
                    />
                  </td>
                </tr>
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </section>
      {explorer.results.items.length === 0 && !explorer.error ? (
        <p className="mt-5 border border-ink bg-paper p-4 text-sm">
          {preliminary
            ? label(
                locale,
                "No hay hechos preliminares disponibles para esta selección. Esto no significa cero ni ausencia de una candidatura.",
                "There are no preliminary facts available for this selection. This does not mean zero or absence of a candidate.",
              )
            : label(
                locale,
                "No hay hechos publicados para esta selección. Esto no significa cero ni ausencia de una candidatura.",
                "There are no published facts for this selection. This does not mean zero or absence of a candidate.",
              )}
        </p>
      ) : null}
      {nextPage ? (
        <nav
          className="mt-6 flex justify-end"
          aria-label={label(locale, "Paginación", "Pagination")}
        >
          <Link
            className="inline-flex min-h-11 items-center border border-ink px-4 text-sm font-bold hover:bg-ink hover:text-paper"
            href={nextPage}
          >
            {label(locale, "Siguiente página", "Next page")}
          </Link>
        </nav>
      ) : null}
      <section
        className="mt-10 border-y border-ink py-7"
        aria-labelledby="historical-comparison"
      >
        <p className={kickerClass}>
          {label(locale, "Comparación histórica", "Historical comparison")}
        </p>
        <h2
          id="historical-comparison"
          className="mt-3 font-display text-3xl font-normal"
        >
          {label(locale, "Sólo pares aprobados", "Approved pairs only")}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-muted">
          {label(
            locale,
            "Los contextos históricos se derivan de los releases publicados que entrega la API. Los candidatos no publicados —incluidos contextos 2018— no aparecen en esta lista ni adquieren elegibilidad de integridad. Una coincidencia de nombre no crea una equivalencia territorial o de candidatura.",
            "Historical contexts are derived from the published releases delivered by the API. Unpublished candidates —including 2018 contexts— do not appear in this list and never gain integrity eligibility. A matching name never creates a territorial or candidate equivalence.",
          )}
        </p>
        <div className="mt-5 grid gap-px border border-ink bg-ink sm:grid-cols-2">
          <label className="bg-paper p-3 text-sm font-bold">
            {label(locale, "Baseline histórico publicado", "Published historical baseline")}
            <select
              aria-label={label(
                locale,
                "Baseline histórico publicado",
                "Published historical baseline",
              )}
              className={filterControlClass}
              value={selectedBaseline ? baselineValue(selectedBaseline) : ""}
              onChange={(event) => {
                const next = historicalReleases.find(
                  (item) => baselineValue(item) === event.target.value,
                );
                location.assign(
                  current({
                    baselineRelease: next?.release_id,
                    baselineElection: next?.election_slug,
                  }),
                );
              }}
            >
              <option value="">
                {label(locale, "Sin baseline", "No baseline")}
              </option>
              {historicalReleases.map((item) => (
                <option key={baselineValue(item)} value={baselineValue(item)}>
                  {locale === "es" ? item.name_es : item.name_en} · {item.election_date}
                </option>
              ))}
            </select>
          </label>
          <label className="bg-paper p-3 text-sm font-bold">
            {label(locale, "Grano de comparación", "Comparison grain")}
            <select
              aria-label={label(
                locale,
                "Grano de comparación",
                "Comparison grain",
              )}
              className={filterControlClass}
              value={filters.comparisonGrain ?? ""}
              onChange={(event) =>
                location.assign(
                  current({
                    comparisonGrain: event.target.value || undefined,
                  }),
                )
              }
            >
              <option value="">
                {label(locale, "Seleccione un grano", "Choose a grain")}
              </option>
              <option value="municipality">
                {label(locale, "Municipio", "Municipality")}
              </option>
              <option value="mesa">Mesa</option>
            </select>
          </label>
        </div>
        {historicalReleases.length ? (
          <ul
            className="mt-4 grid gap-px border border-ink bg-ink sm:grid-cols-2 lg:grid-cols-3"
            aria-label={label(
              locale,
              "Contextos históricos publicados disponibles",
              "Available published historical contexts",
            )}
          >
            {historicalReleases.map((item) => (
              <li className="bg-paper px-4 py-3" key={baselineValue(item)}>
                <p className="text-sm font-bold">
                  {locale === "es" ? item.name_es : item.name_en}
                </p>
                <p className="mt-1 font-mono text-xs text-muted">
                  {item.release_id} · {item.election_date}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-4 border border-ink bg-paper p-4 text-sm">
            {label(
              locale,
              "La API no entregó otro release publicado para comparación. Esto no representa cero ni una ausencia histórica.",
              "The API did not deliver another published release for comparison. This does not represent zero or a historical absence.",
            )}
          </p>
        )}
        <p className="mt-4 max-w-3xl text-sm leading-6 text-muted">
          {label(
            locale,
            "Las comparaciones por municipio y mesa sólo se habilitan con crosswalk geográfico aprobado; las categorías requieren además crosswalk semántico aprobado. Sin ello, la respuesta es ‘no comparable’, nunca cero ni una estimación.",
            "Municipality and mesa comparisons are enabled only with an approved geography crosswalk; categories also require an approved semantic crosswalk. Without them, the response is ‘not comparable,’ never zero or an estimate.",
          )}
        </p>
        {explorer.comparison ? (
          <div className="mt-4 border border-ink bg-paper p-4 text-sm">
            <p className="font-bold">
              {comparisonText(explorer.comparison, locale)}
            </p>
            {explorer.comparison.comparison_status !== "not_comparable" ? (
              <>
                <p className="mt-2 text-muted">
                  {explorer.comparison.eligible_for_integrity_analysis
                    ? label(
                        locale,
                        "Elegible para análisis de integridad según la publicación.",
                        "Eligible for integrity analysis according to the publication.",
                      )
                    : label(
                        locale,
                        "eligible_for_integrity_analysis: false",
                        "eligible_for_integrity_analysis: false",
                      )}
                </p>
                <ul className="mt-3 divide-y divide-ink border-y border-ink">
                  {explorer.comparison.items.map((item) => (
                    <li className="py-2" key={item.category_key}>
                      <strong>{item.category_key}</strong>:{" "}
                      {metricDisplay(
                        {
                          value: item.current_value,
                          status: item.current_status,
                        },
                        locale,
                      )}{" "}
                      /{" "}
                      {metricDisplay(
                        {
                          value: item.baseline_value,
                          status: item.baseline_status,
                        },
                        locale,
                      )}{" "}
                      <span className="text-xs text-muted">
                        {item.semantic_crosswalk_version}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : (
          <p className="mt-4 border border-ink bg-paper p-4 text-sm">
            {label(
              locale,
              "Elija geografía, baseline y grano en la URL para solicitar una comparación. Si no hay crosswalk aprobado, se mostrará la razón; no se inventan pares.",
              "Choose geography, baseline, and grain in the URL to request a comparison. If no crosswalk is approved, its reason is shown; pairs are never invented.",
            )}
          </p>
        )}
      </section>
    </main>
  );
}

export function ResultsExplorer({
  release,
  explorer,
  locale,
  filters,
  enumLabels,
}: {
  release?: FixtureRelease;
  explorer?: PublicExplorer;
  locale: "es" | "en";
  filters: ResultFilters;
  enumLabels: PublicResultLabels;
}) {
  if (explorer?.kind === "normalized") {
    return (
      <NormalizedResultsExplorer
        explorer={explorer}
        locale={locale}
        filters={filters}
        enumLabels={enumLabels}
      />
    );
  }
  if (!release) throw new Error("A legacy fixture release is required.");
  return (
    <LegacyResultsExplorer
      release={release}
      locale={locale}
      filters={filters}
      enumLabels={enumLabels}
    />
  );
}
