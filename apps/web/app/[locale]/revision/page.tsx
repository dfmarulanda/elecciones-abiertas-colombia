import Link from "next/link";
import { Info } from "lucide-react";
import { setRequestLocale } from "next-intl/server";

import { Page, Section } from "@/components/page-primitives";
import { ReviewSignalDetails } from "@/components/investigation-details";
import { dataAdapter } from "@/data/fixture-adapter";
import { reviewDisclosure } from "@/lib/review-disclosure";

export const dynamic = "force-dynamic";

const tiers = [
  "documentary_review_prioritized",
  "documentary_comparison_recommended",
  "statistical_or_coverage_issue",
  "no_review_signals",
] as const;

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
    es: "Señal estadística experimental o asunto de cobertura (15–44)",
    en: "Experimental statistical signal or coverage issue (15–44)",
  },
  no_review_signals: {
    es: "Sin señales de revisión en los datos disponibles (0–14)",
    en: "No review signals detected in available data (0–14)",
  },
} as const;

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: "es" | "en" }>;
  searchParams: Promise<{ min?: string; tier?: string; cursor?: string }>;
}) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const es = locale === "es";
  const parsedMinimum = Number(query.min ?? 0);
  const minimum = Number.isFinite(parsedMinimum)
    ? Math.min(100, Math.max(0, parsedMinimum))
    : 0;
  const selectedTier = tiers.includes(query.tier as (typeof tiers)[number])
    ? (query.tier as (typeof tiers)[number])
    : undefined;
  const release = await dataAdapter.getRelease({
    include: "review",
    reviewCursor: query.cursor,
    reviewMinimumScore: minimum,
    reviewTier: selectedTier,
  });
  const signals = release.review_signals
    .filter(
      (signal) =>
        signal.score >= minimum &&
        (!selectedTier || signal.tier === selectedTier),
    )
    .sort(
      (left, right) =>
        right.score - left.score || left.id.localeCompare(right.id),
    );
  const permanent = reviewDisclosure[locale];
  const municipalityByMesa = new Map(
    release.mesas.map((mesa) => [
      mesa.id,
      release.geographies.find((item) => item.id === mesa.municipality_id)
        ?.name ?? (es ? "Municipio no disponible" : "Municipality unavailable"),
    ]),
  );
  const nextQuery = new URLSearchParams();
  if (minimum) nextQuery.set("min", String(minimum));
  if (selectedTier) nextQuery.set("tier", selectedTier);
  if (release.review_page?.next_cursor) {
    nextQuery.set("cursor", release.review_page.next_cursor);
  }

  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Prioridad de auditoría" : "Audit priority"}
      title={es ? "Señales para revisión" : "Review signals"}
    >
      <Section title={es ? "Metodología y límites" : "Methodology and limits"}>
        <p>{permanent}</p>
        <p className="mt-3">
          {es ? "Versión de metodología:" : "Methodology version:"}{" "}
          <code>{release.release.methodology_version}</code>.{" "}
          {es
            ? "Los componentes estadísticos de la demostración sintética son experimentales. Las publicaciones reales no están disponibles hasta validación independiente; nunca sustituyen la revisión del documento."
            : "Statistical components in the synthetic demonstration are experimental. Real releases are unavailable pending independent validation; they never replace document review."}
        </p>
      </Section>

      <Section
        title={
          es ? "Qué puede concluir una señal" : "What a signal can conclude"
        }
      >
        <ul className="list-disc space-y-2 pl-5">
          <li>
            {es
              ? "Una discrepancia documental puede confirmarse al contrastar registros y fuentes oficiales compatibles."
              : "A documentary discrepancy can be confirmed by comparing records and compatible official sources."}
          </li>
          <li>
            {es
              ? "Una señal estadística solo prioriza una revisión; no demuestra un error ni una causa."
              : "A statistical signal only prioritizes review; it does not prove an error or its cause."}
          </li>
          <li>
            {es
              ? "Ni el puntaje ni las matemáticas concluyen fraude, intención o responsabilidad."
              : "Neither the score nor the mathematics concludes fraud, intent, or responsibility."}
          </li>
        </ul>
      </Section>

      <form
        className="my-8 grid border border-ink bg-ink p-4 text-paper sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] lg:items-end"
        aria-label={es ? "Filtrar señales" : "Filter signals"}
      >
        <label className="grid min-w-0 gap-2 border-b border-[#9B9B9B] pb-4 font-mono text-[11px] font-bold tracking-[.08em] uppercase sm:border-r sm:border-b-0 sm:pr-4 lg:pb-0">
          <span>{es ? "Puntaje mínimo" : "Minimum score"}</span>
          <select
            className="min-h-11 w-full min-w-0 max-w-full border border-paper bg-paper px-3 text-ink"
            defaultValue={String(minimum)}
            name="min"
          >
            {[0, 10, 45, 70].map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="grid min-w-0 gap-2 border-b border-[#9B9B9B] py-4 font-mono text-[11px] font-bold tracking-[.08em] uppercase sm:border-b-0 sm:py-0 sm:pl-4 lg:border-r lg:pr-4">
          <span>{es ? "Nivel" : "Tier"}</span>
          <select
            className="min-h-11 w-full min-w-0 border border-paper bg-paper px-3 text-ink"
            defaultValue={selectedTier ?? ""}
            name="tier"
          >
            <option value="">{es ? "Todos" : "All"}</option>
            {tiers.map((tier) => (
              <option value={tier} key={tier}>
                {tierLabels[tier][locale]}
              </option>
            ))}
          </select>
        </label>
        <button className="min-h-11 border border-neon bg-neon px-5 font-mono text-xs font-bold tracking-[.08em] text-ink uppercase hover:bg-paper lg:ml-4">
          {es ? "Aplicar" : "Apply"}
        </button>
      </form>

      <div className="border-t border-ink">
        {signals.map((signal) => (
          <article className="border-b border-ink py-7" key={signal.id}>
            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
              <div>
                <p className="text-sm font-bold">
                  {municipalityByMesa.get(signal.mesa_id)}
                </p>
                <h2 className="mt-1 font-display text-2xl font-bold tracking-[-0.035em] uppercase">
                  <Link
                    className="underline"
                    href={`/${locale}/actas/${signal.mesa_id}`}
                  >
                    {es ? "Ver mesa" : "View mesa"} {signal.mesa_id}
                  </Link>
                </h2>
              </div>
              <span className="border border-ink bg-ink px-3 py-2 font-mono text-xs font-bold tracking-[.04em] text-paper uppercase sm:text-right">
                {es ? "Puntaje de prioridad" : "Priority score"} {signal.score}
                /100
              </span>
            </div>
            <p className="mt-4 flex items-start gap-2 border-l-4 border-neon pl-3 text-sm font-semibold">
              <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {tierLabels[signal.tier][locale]}
            </p>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="font-bold">
                  {es
                    ? "Votos con base documental verificada"
                    : "Votes with verified documentary basis"}
                </dt>
                <dd>
                  {signal.affected_vote_estimate ??
                    (es ? "No disponible" : "Unavailable")}
                </dd>
              </div>
              <div>
                <dt className="font-bold">{es ? "Método" : "Method"}</dt>
                <dd>
                  <code>{signal.methodology_version}</code>
                </dd>
              </div>
            </dl>
            <p className="mt-4 border-l-2 border-neon pl-3 text-sm leading-6 text-muted">
              {permanent}
            </p>
            <ReviewSignalDetails signal={signal} locale={locale} />
          </article>
        ))}
      </div>

      {!signals.length && (
        <p className="border border-ink p-4 text-sm">
          {release.release.status !== "published" ||
          release.summary.reconciliation.status !== "passed"
            ? es
              ? "El análisis de señales no se ha publicado para esta versión. Una lista vacía no significa que no existan anomalías."
              : "Signal analysis has not been published for this release. An empty list does not mean that no anomalies exist."
            : es
              ? "No hay señales para este filtro. Esto no prueba ausencia de errores."
              : "There are no signals for this filter. This does not prove absence of errors."}
        </p>
      )}
      {release.review_page?.has_more && release.review_page.next_cursor && (
        <nav
          className="mt-6 flex justify-end"
          aria-label={es ? "Paginación" : "Pagination"}
        >
          <Link
            className="inline-flex min-h-11 items-center border border-ink bg-ink px-4 font-mono text-xs font-bold tracking-[.08em] text-paper uppercase hover:bg-neon hover:text-ink"
            href={`/${locale}/revision?${nextQuery}`}
          >
            {es ? "Siguiente página" : "Next page"}
          </Link>
        </nav>
      )}
    </Page>
  );
}
