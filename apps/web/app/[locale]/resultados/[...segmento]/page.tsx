import Link from "next/link";
import { notFound } from "next/navigation";
import { setRequestLocale } from "next-intl/server";
import {
  dataAdapter,
  getPublicChildrenResults,
  getPublicGeography,
  getPublicMesa,
  PublicApiError,
  publicNormalizedApiConfigured,
} from "@/data/fixture-adapter";
import { Page, Section } from "@/components/page-primitives";
import {
  NormalizedGeographyView,
  NormalizedMesaView,
  NormalizedUnavailable,
} from "@/components/normalized-geography-view";
import { formatMetricValue } from "@/lib/metric-value";
import { sourceTypeLabel } from "@/lib/public-labels";
import { readResultFilters } from "@/lib/result-filters";
import { breadcrumbJsonLd, releaseMetadata } from "@/lib/seo";
import { SeoStructuredData } from "@/components/seo-structured-data";
import type { Metadata } from "next";
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en"; segmento: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}): Promise<Metadata> {
  const { locale, segmento } = await params;
  const filters = readResultFilters(await searchParams);
  const identifier = segmento.at(-1);
  const mesa = segmento[0] === "mesa";
  const basePathname = mesa
    ? `/resultados/mesa/${encodeURIComponent(identifier ?? "")}`
    : `/resultados/geografia/${encodeURIComponent(identifier ?? "")}`;
  const scope = new URLSearchParams();
  if (filters.release) scope.set("release", filters.release);
  if (filters.election) scope.set("election", filters.election);
  const pathname = `${basePathname}${scope.size ? `?${scope}` : ""}`;
  if (!identifier) {
    return releaseMetadata({
      locale,
      pathname,
      title: locale === "es" ? "Resultados" : "Results",
      description: "Published geographic result is unavailable.",
      page: mesa ? "mesa" : "geography",
    });
  }
  try {
    const summary = await dataAdapter.getNationalSummary();
    if (publicNormalizedApiConfigured()) {
      if (mesa) {
        const view = await getPublicMesa(identifier, filters);
        return releaseMetadata({
          locale,
          pathname,
          title:
            view.mesa?.display_number ??
            (locale === "es" ? "Resultado de mesa" : "Mesa result"),
          description:
            locale === "es"
              ? "Resultados, procedencia y cobertura de una mesa publicada."
              : "Results, provenance and coverage for a published mesa.",
          release:
            view.selected?.release_id === summary.release.release_id &&
            (!filters.election || filters.election === summary.election.slug)
              ? summary
              : null,
          page: "mesa",
          hasPublishedFacts: Boolean(view.mesa?.results.length),
          uniqueProvenance: Boolean(view.mesa?.results.length),
        });
      }
      const view = await getPublicGeography(identifier, filters);
      const current = view.path.at(-1);
      return releaseMetadata({
        locale,
        pathname,
        title:
          current?.name ??
          (locale === "es" ? "Resultado geográfico" : "Geographic result"),
        description:
          locale === "es"
            ? "Resultados, procedencia y cobertura de una unidad geográfica publicada."
            : "Results, provenance and coverage for a published geographic unit.",
        release:
          view.selected?.release_id === summary.release.release_id &&
          (!filters.election || filters.election === summary.election.slug)
            ? summary
            : null,
        page: "geography",
        hasPublishedFacts: Boolean(current?.has_published_facts),
      });
    }
    const detail = mesa ? await dataAdapter.getMesa(identifier) : null;
    return releaseMetadata({
      locale,
      pathname,
      title: detail
        ? `${locale === "es" ? "Mesa" : "Mesa"} ${detail.display_number}`
        : locale === "es"
          ? "Resultados geográficos"
          : "Geographic results",
      description:
        locale === "es"
          ? "Resultados y procedencia territorial publicados."
          : "Published territorial results and provenance.",
      release: summary,
      page: mesa ? "mesa" : "geography",
      hasPublishedFacts: Boolean(detail?.result),
      uniqueProvenance: Boolean(detail?.result?.provenance),
    });
  } catch {
    return releaseMetadata({
      locale,
      pathname,
      title: locale === "es" ? "Resultados geográficos" : "Geographic results",
      description: "Published geographic result is unavailable.",
      page: mesa ? "mesa" : "geography",
    });
  }
}

export default async function GeographicResultsPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en"; segmento: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { locale, segmento } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const mesaId = segmento.at(-1);
  const isMesaRoute = segmento[0] === "mesa";
  const filters = readResultFilters(query);
  const cursor = typeof query.cursor === "string" ? query.cursor : undefined;
  if (publicNormalizedApiConfigured() && mesaId) {
    try {
      if (isMesaRoute) {
        const view = await getPublicMesa(mesaId, {
          ...filters,
          sourceId: filters.sourceId,
        });
        if (!view.selected || !view.mesa) {
          return (
            <NormalizedUnavailable locale={locale} kind="mesa" status={404} />
          );
        }
        return (
          <>
            <SeoStructuredData
              value={breadcrumbJsonLd(locale, [
                { name: "Resultados", pathname: "/resultados" },
                ...view.mesa.geography_path.map((item) => ({
                  name: item.name,
                  pathname:
                    item.level === "mesa"
                      ? `/resultados/mesa/${encodeURIComponent(item.id)}`
                      : `/resultados/geografia/${encodeURIComponent(item.id)}`,
                })),
              ])}
            />
            <NormalizedMesaView view={view} locale={locale} filters={filters} />
          </>
        );
      }
      const view = await getPublicGeography(mesaId, {
        ...filters,
        cursor,
      });
      if (!view.selected) {
        return (
          <NormalizedUnavailable
            locale={locale}
            kind="geography"
            status={404}
          />
        );
      }
      // Vote totals for the same children, in one extra request rather than a
      // per-child fetch. A failure here must not take the page down: the
      // breadcrumb and child list are the navigation, the fields are an
      // enrichment, so this degrades to the list alone.
      const childResults = await getPublicChildrenResults(mesaId, {
        ...filters,
        cursor,
      }).catch(() => null);
      return (
        <>
          <SeoStructuredData
            value={breadcrumbJsonLd(locale, [
              { name: "Resultados", pathname: "/resultados" },
              ...view.path.map((item) => ({
                name: item.name,
                pathname: `/resultados/geografia/${encodeURIComponent(item.id)}`,
              })),
            ])}
          />
          <NormalizedGeographyView
            view={view}
            locale={locale}
            filters={filters}
            results={childResults}
          />
        </>
      );
    } catch (error) {
      const status = error instanceof PublicApiError ? error.status : undefined;
      return (
        <NormalizedUnavailable
          locale={locale}
          kind={isMesaRoute ? "mesa" : "geography"}
          status={status}
        />
      );
    }
  }
  const detail =
    isMesaRoute && mesaId ? await dataAdapter.getMesa(mesaId) : null;
  const es = locale === "es";
  if (isMesaRoute && !detail) notFound();
  const release = isMesaRoute
    ? null
    : await dataAdapter.getRelease({
        include: "results",
        filters: mesaId ? { geography: mesaId } : undefined,
      });
  const summaryRelease = isMesaRoute
    ? await dataAdapter.getNationalSummary()
    : release;
  const mesa = release?.mesas.find((item) => item.id === mesaId);
  const geographies = release?.geographies ?? [
    ...(detail ? [detail.geography, detail.polling_place] : []),
  ];
  const geo = new Map(geographies.map((item) => [item.id, item]));
  const crumbs = detail
    ? [
        detail.geography.name,
        detail.polling_place.name,
        `Mesa ${detail.display_number}`,
      ]
    : mesa
      ? ([
          geo.get(mesa.department_id)?.name,
          geo.get(mesa.municipality_id)?.name,
          geo.get(mesa.polling_place_id)?.name,
          `Mesa ${mesa.display_number}`,
        ].filter(Boolean) as string[])
      : segmento.map((part) => geo.get(part)?.name ?? part);
  const targetGeography = segmento.at(-1);
  const descendantIds = new Set(targetGeography ? [targetGeography] : []);
  let expanded = true;
  while (expanded) {
    expanded = false;
    for (const geography of geographies) {
      if (
        geography.parent_id &&
        descendantIds.has(geography.parent_id) &&
        !descendantIds.has(geography.id)
      ) {
        descendantIds.add(geography.id);
        expanded = true;
      }
    }
  }
  const facts = detail
    ? [detail.result]
    : (release?.results ?? []).filter((result) => {
        const rowMesa = release?.mesas.find(
          (item) => item.id === result.mesa_id,
        );
        return [
          result.geography_id,
          rowMesa?.polling_place_id,
          rowMesa?.municipality_id,
          rowMesa?.department_id,
        ].some((identifier) => identifier && descendantIds.has(identifier));
      });
  return (
    <Page
      locale={locale}
      synthetic={summaryRelease?.release.synthetic}
      releaseStatus={summaryRelease?.release.status}
      eyebrow={
        es ? "Ruta canónica y proveniencia" : "Canonical route and provenance"
      }
      title={
        detail
          ? `${es ? "Mesa" : "Mesa"} ${detail.display_number}`
          : `${es ? "Resultados geográficos" : "Geographic results"}`
      }
    >
      <nav
        aria-label={es ? "Miga de pan" : "Breadcrumb"}
        className="mb-7 flex flex-wrap gap-2 text-sm"
      >
        <Link className="underline" href={`/${locale}/resultados`}>
          {es ? "Resultados" : "Results"}
        </Link>
        {crumbs.map((crumb) => (
          <span className="whitespace-nowrap" key={crumb}>
            / {crumb}
          </span>
        ))}
      </nav>
      {detail && (
        <Link
          className="mb-7 inline-flex min-h-11 items-center border border-ink px-4 text-sm font-bold hover:bg-neon"
          href={`/${locale}/actas/${detail.id}`}
        >
          {es ? "Actas de mesa" : "Mesa records"}
        </Link>
      )}
      <Section title={es ? "Lectura de la ruta" : "Route reading"}>
        <p>
          {es
            ? "Esta ruta identifica de forma estable el nivel solicitado. No infiere una geografía ni crea coordenadas: los datos conservan la cadena departamento, municipio, puesto y mesa cuando está disponible."
            : "This route stably identifies the requested level. It does not infer geography or create coordinates: data retains department, municipality, polling place, and mesa when available."}
        </p>
      </Section>
      <Section
        title={es ? "Resultados y capa de fuente" : "Results and source layer"}
      >
        {facts.length ? (
          <div className="overflow-x-auto border border-ink">
            <table className="w-full min-w-96 text-left text-sm">
              <thead className="bg-ink font-mono text-xs tracking-[.08em] text-paper uppercase">
                <tr>
                  <th className="px-3 py-3">{es ? "Mesa" : "Mesa"}</th>
                  <th className="px-3 py-3">{es ? "Votantes" : "Voters"}</th>
                  <th className="px-3 py-3">{es ? "Fuente" : "Source"}</th>
                  <th className="px-3 py-3">Hash</th>
                </tr>
              </thead>
              <tbody>
                {facts.map((fact) => (
                  <tr
                    className="border-t border-ink hover:bg-neon/15"
                    key={fact.id}
                  >
                    <th className="px-3 py-3">{fact.mesa_id ?? "—"}</th>
                    <td className="px-3 py-3">
                      {
                        formatMetricValue(fact.voters, locale, {
                          observed: es ? "Observado" : "Observed",
                          unknown: es ? "Desconocido" : "Unknown",
                          unavailable: es ? "No disponible" : "Unavailable",
                          not_applicable: es ? "No aplica" : "Not applicable",
                        }).display
                      }
                    </td>
                    <td className="px-3 py-3">
                      {sourceTypeLabel(locale, fact.provenance.source_type)}
                    </td>
                    <td
                      className="max-w-44 truncate px-3 py-3"
                      title={fact.provenance.content_hash}
                    >
                      {fact.provenance.content_hash}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>
            {es
              ? "No hay un registro publicado para esta ruta en la fijación sintética."
              : "No record is published for this route in the synthetic fixture."}
          </p>
        )}
      </Section>
      <Section title={es ? "Proveniencia" : "Provenance"}>
        <p>
          {es
            ? "La fuente, estado jurídico y huella corresponden al registro mostrado. El preconteo es preliminar; esta página no declara resultados oficiales."
            : "Source, legal status, and digest belong to the displayed record. Pre-count is preliminary; this page does not declare official results."}
        </p>
      </Section>
    </Page>
  );
}
