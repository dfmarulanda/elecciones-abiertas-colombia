import Link from "next/link";
import React from "react";

import { Page, Section } from "@/components/page-primitives";
import type {
  PublicGeographyView,
  PublicMesaView,
} from "@/data/fixture-adapter";
import { geographyRoute, mesaRoute } from "@/lib/explorer-routing";
import { formatMetricValue } from "@/lib/metric-value";
import {
  directChildrenLabel,
  geographyLevelLabel,
  legalStatusLabel,
  sourceTypeLabel,
} from "@/lib/public-labels";
import {
  serializeResultFilters,
  type ResultFilters,
} from "@/lib/result-filters";

type Locale = "es" | "en";

const copy = (locale: Locale, es: string, en: string) =>
  locale === "es" ? es : en;

function routeFilters(
  view: Pick<PublicGeographyView, "selected">,
  filters: ResultFilters,
): ResultFilters {
  return {
    release: view.selected?.release_id,
    election: view.selected?.election_slug,
    source: filters.source,
    sourceId: filters.sourceId,
  };
}

export function NormalizedGeographyView({
  view,
  locale,
  filters,
}: {
  view: PublicGeographyView;
  locale: Locale;
  filters: ResultFilters;
}) {
  const selected = view.selected;
  const scoped = routeFilters(view, filters);
  const current = view.path.at(-1);
  const nextBase = geographyRoute(locale, view.geographyId, {
    ...scoped,
    level: filters.level,
  });
  const nextHref = view.children.page.next_cursor
    ? `${nextBase}${nextBase.includes("?") ? "&" : "?"}cursor=${encodeURIComponent(view.children.page.next_cursor)}`
    : null;
  return (
    <Page
      locale={locale}
      synthetic={false}
      releaseStatus={view.selected?.status ?? "published"}
      eyebrow={copy(
        locale,
        "Exploración territorial",
        "Territorial exploration",
      )}
      title={
        current?.name ??
        copy(locale, "Geografía publicada", "Published geography")
      }
    >
      <nav
        aria-label={copy(locale, "Ruta geográfica", "Geography path")}
        className="mb-7 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
      >
        <Link
          className="inline-flex min-h-11 items-center underline"
          href={`/${locale}/resultados?${serializeResultFilters(scoped)}`}
        >
          {copy(locale, "Resultados", "Results")}
        </Link>
        {view.path.map((item) => (
          <span
            className="inline-flex items-center gap-2 whitespace-nowrap"
            key={item.id}
          >
            <span aria-hidden="true">/</span>
            <Link
              className="inline-flex min-h-11 items-center underline decoration-ink underline-offset-4"
              href={geographyRoute(locale, item.id, scoped)}
              aria-current={item.id === current?.id ? "page" : undefined}
            >
              {item.name}
            </Link>
          </span>
        ))}
      </nav>
      <section
        className="grid border border-ink bg-ink text-paper sm:grid-cols-3 sm:divide-x sm:divide-paper/20"
        aria-label={copy(
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
            {selected?.release_id ?? "—"}
          </p>
        </div>
        <div className="border-b border-paper/20 p-4 sm:border-b-0">
          <p className="font-mono text-xs font-bold uppercase text-paper/60">
            {copy(locale, "Nivel actual", "Current level")}
          </p>
          <p className="mt-1 font-semibold">
            {current ? geographyLevelLabel(locale, current.level) : "—"}
          </p>
        </div>
        <div className="p-4">
          <p className="font-mono text-xs font-bold uppercase text-paper/60">
            {copy(locale, "Página", "Page")}
          </p>
          <p className="mt-1 font-semibold">
            {directChildrenLabel(locale, view.children.items.length)}
          </p>
        </div>
      </section>
      <Section title={copy(locale, "Siguiente nivel", "Next level")}>
        <p>
          {copy(
            locale,
            "La tabla contiene únicamente unidades hijas publicadas para esta ruta. Cada paso conserva release, elección y fuente en la URL.",
            "The table contains only published direct children for this path. Every step preserves release, election, and source in the URL.",
          )}
        </p>
        {view.children.items.length ? (
          <>
            <p className="mt-5 text-xs leading-5 text-muted md:hidden">
              {copy(
                locale,
                "Deslice horizontalmente la tabla para ver todas las columnas.",
                "Scroll the table horizontally to view every column.",
              )}
            </p>
            <div
              className="mt-2 overflow-x-auto border border-ink bg-paper text-ink md:mt-5"
              role="region"
              aria-label={copy(
                locale,
                "Tabla de unidades geográficas desplazable horizontalmente",
                "Horizontally scrollable geographic-units table",
              )}
              tabIndex={0}
            >
              <table className="w-full min-w-[640px] text-left text-sm">
                <caption className="sr-only">
                  {copy(
                    locale,
                    "Unidades geográficas hijas",
                    "Child geographic units",
                  )}
                </caption>
                <thead className="bg-ink text-xs uppercase tracking-[.08em] text-paper">
                  <tr>
                    <th className="px-4 py-3">
                      {copy(locale, "Unidad", "Unit")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Abrir", "Open")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Nivel", "Level")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Código", "Code")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Datos", "Data")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {view.children.items.map((child) => {
                    const href =
                      child.level === "mesa"
                        ? mesaRoute(locale, child.id, scoped)
                        : geographyRoute(locale, child.id, scoped);
                    return (
                      <tr
                        className="border-t border-ink hover:bg-neon/15"
                        key={child.id}
                      >
                        <th className="px-4 py-4" scope="row">
                          {child.name}
                        </th>
                        <td className="px-4 py-4">
                          <Link
                            className="inline-flex min-h-11 items-center font-bold underline decoration-ink underline-offset-4"
                            href={href}
                          >
                            {child.level === "mesa"
                              ? copy(locale, "Abrir mesa", "Open mesa")
                              : copy(
                                  locale,
                                  "Ver siguiente nivel",
                                  "View next level",
                                )}
                          </Link>
                        </td>
                        <td className="px-4 py-4">
                          {geographyLevelLabel(locale, child.level)}
                        </td>
                        <td className="px-4 py-4 font-mono text-xs">
                          {child.code}
                        </td>
                        <td className="px-4 py-4">
                          {child.has_published_facts
                            ? copy(locale, "Hecho publicado", "Published fact")
                            : copy(
                                locale,
                                "Sin hecho en esta unidad",
                                "No fact at this unit",
                              )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="mt-5 border border-ink bg-paper p-4 text-ink">
            {copy(
              locale,
              "No hay unidades hijas publicadas. Este estado no representa un conteo de cero.",
              "There are no published child units. This state does not represent a zero count.",
            )}
          </p>
        )}
        {nextHref ? (
          <nav
            className="mt-5 flex justify-end"
            aria-label={copy(
              locale,
              "Paginación geográfica",
              "Geography pagination",
            )}
          >
            <Link
              className="inline-flex min-h-11 items-center border border-ink px-4 font-bold"
              href={nextHref}
            >
              {copy(locale, "Siguiente página", "Next page")}
            </Link>
          </nav>
        ) : null}
      </Section>
    </Page>
  );
}

export function NormalizedMesaView({
  view,
  locale,
  filters,
}: {
  view: PublicMesaView;
  locale: Locale;
  filters: ResultFilters;
}) {
  const mesa = view.mesa;
  const selected = view.selected;
  if (!mesa) return null;
  const scoped: ResultFilters = {
    release: selected?.release_id,
    election: selected?.election_slug,
    source: filters.source,
    sourceId: filters.sourceId,
  };
  const metricLabels = {
    observed: copy(locale, "Observado", "Observed"),
    unknown: copy(locale, "Desconocido", "Unknown"),
    unavailable: copy(locale, "No disponible", "Unavailable"),
    not_applicable: copy(locale, "No aplica", "Not applicable"),
  };
  const sources = [
    ...new Set(selected?.sources.map((item) => item.source_type) ?? []),
  ];
  return (
    <Page
      locale={locale}
      synthetic={false}
      releaseStatus={view.selected?.status ?? "published"}
      eyebrow={copy(locale, "Ruta canónica de mesa", "Canonical mesa route")}
      title={`${copy(locale, "Mesa", "Mesa")} ${mesa.display_number}`}
    >
      <nav
        aria-label={copy(locale, "Ruta geográfica", "Geography path")}
        className="mb-7 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
      >
        <Link
          className="inline-flex min-h-11 items-center underline"
          href={`/${locale}/resultados?${serializeResultFilters(scoped)}`}
        >
          {copy(locale, "Resultados", "Results")}
        </Link>
        {mesa.geography_path.map((item) => (
          <span
            className="inline-flex items-center gap-2 whitespace-nowrap"
            key={item.id}
          >
            <span aria-hidden="true">/</span>
            {item.level === "mesa" ? (
              <span aria-current="page" className="font-bold">
                {item.name}
              </span>
            ) : (
              <Link
                className="inline-flex min-h-11 items-center underline decoration-ink underline-offset-4"
                href={geographyRoute(locale, item.id, scoped)}
              >
                {item.name}
              </Link>
            )}
          </span>
        ))}
      </nav>
      <form
        className="grid gap-px border border-ink bg-ink p-px sm:grid-cols-[1fr_auto]"
        aria-label={copy(
          locale,
          "Filtrar fuentes de mesa",
          "Filter mesa sources",
        )}
      >
        <input
          type="hidden"
          name="release"
          value={selected?.release_id ?? ""}
        />
        <input
          type="hidden"
          name="election"
          value={selected?.election_slug ?? ""}
        />
        <label className="bg-paper p-3 text-sm font-bold">
          {copy(locale, "Fuente", "Source")}
          <select
            className="mt-2 min-h-11 w-full border border-ink bg-paper px-3"
            name="source"
            defaultValue={filters.source ?? ""}
          >
            <option value="">
              {copy(locale, "Todas las publicadas", "All published")}
            </option>
            {sources.map((source) => (
              <option key={source} value={source}>
                {sourceTypeLabel(locale, source)}
              </option>
            ))}
          </select>
        </label>
        <button
          className="min-h-11 self-stretch border border-ink bg-ink px-5 text-sm font-bold text-paper hover:bg-neon hover:text-ink sm:self-auto"
          type="submit"
        >
          {copy(locale, "Aplicar", "Apply")}
        </button>
      </form>
      <Section
        title={copy(locale, "Resultados por fuente", "Results by source")}
      >
        <p>
          {copy(
            locale,
            "Cada fila es un hecho publicado para esta mesa. Los estados desconocido y no disponible permanecen explícitos.",
            "Each row is a published fact for this mesa. Unknown and unavailable states remain explicit.",
          )}
        </p>
        {mesa.results.length ? (
          <>
            <p className="mt-5 text-xs leading-5 text-muted md:hidden">
              {copy(
                locale,
                "Deslice horizontalmente la tabla para ver todas las columnas.",
                "Scroll the table horizontally to view every column.",
              )}
            </p>
            <div
              className="mt-2 overflow-x-auto border border-ink bg-paper text-ink md:mt-5"
              role="region"
              aria-label={copy(
                locale,
                "Tabla de resultados por fuente desplazable horizontalmente",
                "Horizontally scrollable results-by-source table",
              )}
              tabIndex={0}
            >
              <table className="w-full min-w-[720px] text-left text-sm">
                <caption className="sr-only">
                  {copy(
                    locale,
                    "Resultados de mesa por fuente",
                    "Mesa results by source",
                  )}
                </caption>
                <thead className="bg-ink text-xs uppercase tracking-[.08em] text-paper">
                  <tr>
                    <th className="px-4 py-3">
                      {copy(locale, "Fuente", "Source")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Votantes", "Voters")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Votos válidos", "Valid votes")}
                    </th>
                    <th className="px-4 py-3">
                      {copy(locale, "Estado jurídico", "Legal status")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {mesa.results.map((fact) => (
                    <tr
                      className="border-t border-ink hover:bg-neon/15"
                      key={fact.id}
                    >
                      <td className="px-4 py-4">
                        {sourceTypeLabel(locale, fact.provenance.source_type)}
                      </td>
                      <td className="px-4 py-4">
                        {
                          formatMetricValue(fact.voters, locale, metricLabels)
                            .display
                        }
                      </td>
                      <td className="px-4 py-4">
                        {
                          formatMetricValue(
                            fact.valid_votes,
                            locale,
                            metricLabels,
                          ).display
                        }
                      </td>
                      <td className="px-4 py-4">
                        {legalStatusLabel(locale, fact.provenance.legal_status)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="mt-5 border border-ink bg-paper p-4 text-ink">
            {copy(
              locale,
              "No hay un hecho publicado para esta fuente. No se muestra cero ni se sustituye otra capa.",
              "There is no published fact for this source. Zero is not shown and another layer is not substituted.",
            )}
          </p>
        )}
      </Section>
      <Section title={copy(locale, "Profundizar", "Go deeper")}>
        <p>
          {copy(
            locale,
            "La procedencia siguiente pertenece exactamente a cada hecho visible; no describe otras fuentes ni otros releases.",
            "The provenance below belongs exactly to each visible fact; it does not describe other sources or releases.",
          )}
        </p>
        <div className="mt-4 border-t border-ink text-paper">
          {mesa.results.map((fact) => (
            <details
              className="border-x border-b border-ink bg-ink px-4 py-2"
              key={fact.id}
            >
              <summary className="min-h-11 cursor-pointer py-2 font-bold">
                {copy(locale, "Procedencia", "Provenance")} ·{" "}
                {fact.provenance.source_type}
              </summary>
              <dl className="grid gap-x-4 gap-y-2 border-t border-paper/20 pb-3 pt-3 text-sm text-paper/75 sm:grid-cols-[auto_minmax(0,1fr)]">
                <dt>Release</dt>
                <dd className="break-all">{fact.provenance.data_version}</dd>
                <dt>Hash</dt>
                <dd className="break-all font-mono text-xs">
                  {fact.provenance.content_hash}
                </dd>
                <dt>Parser</dt>
                <dd>{fact.provenance.parser_version}</dd>
                <dt>Transform</dt>
                <dd>{fact.provenance.transform_version}</dd>
                <dt>{copy(locale, "Fuente", "Source")}</dt>
                <dd>
                  <a
                    className="inline-flex min-h-11 items-center text-paper underline decoration-neon underline-offset-4"
                    href={fact.provenance.source_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {copy(
                      locale,
                      "Abrir documento publicado",
                      "Open published document",
                    )}
                  </a>
                </dd>
              </dl>
            </details>
          ))}
        </div>
      </Section>
    </Page>
  );
}

export function NormalizedUnavailable({
  locale,
  kind,
  status,
}: {
  locale: Locale;
  kind: "mesa" | "geography";
  status?: number;
}) {
  return (
    <Page
      locale={locale}
      synthetic={false}
      eyebrow={copy(locale, "Estado de la ruta", "Route status")}
      title={copy(
        locale,
        kind === "mesa" ? "Mesa no disponible" : "Geografía no disponible",
        kind === "mesa" ? "Mesa unavailable" : "Geography unavailable",
      )}
    >
      <section role="alert" className="border border-ink bg-paper p-4">
        <p className="font-bold">
          {status === 404 ? "404 · " : ""}
          {copy(
            locale,
            "No existe una publicación para esta selección.",
            "No publication exists for this selection.",
          )}
        </p>
        <p className="mt-2 text-sm">
          {copy(
            locale,
            "No se sustituye con otro release, otra fuente ni un valor cero. Regrese al selector público y elija una ruta publicada.",
            "It is not replaced with another release, source, or zero value. Return to the public selector and choose a published path.",
          )}
        </p>
        <Link
          className="mt-4 inline-flex min-h-11 items-center border border-ink px-4 font-bold hover:bg-neon"
          href={`/${locale}/resultados`}
        >
          {copy(locale, "Volver a resultados", "Back to results")}
        </Link>
      </section>
    </Page>
  );
}
