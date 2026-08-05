import { setRequestLocale } from "next-intl/server";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";

import { Page, Section } from "@/components/page-primitives";
import { legalStatusLabel } from "@/lib/public-labels";
import { dataAdapter } from "@/data/fixture-adapter";
import { loadSourceCatalog } from "@/data/source-catalog";

export const dynamic = "force-dynamic";

export default async function SourcesPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const guard = await loadReleaseOrUnavailable(locale, () =>
    dataAdapter.getNationalSummary(),
  );
  if (guard.fallback) return guard.fallback;
  const release = guard.release;
  const catalog = await loadSourceCatalog();
  const es = locale === "es";
  const awaitingFinal =
    catalog.publication_state === "awaiting_verified_final_declaration";
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Catálogo oficial revisado" : "Reviewed official catalogue"}
      title={es ? "Fuentes" : "Sources"}
    >
      <Section title={es ? "Estado de la publicación" : "Publication state"}>
        <p>
          {es
            ? awaitingFinal
              ? "El catálogo registra puntos de entrada verificados, no resultados incorporados automáticamente. La declaración final de segunda vuelta todavía figura como pendiente de verificación; por eso este repositorio no publica un release electoral real."
              : "El catálogo contiene una declaración final verificada como fuente candidata. Eso no publica el release automáticamente: todavía deben superar todos los gates de conciliación, cobertura, método, redacción y producto."
            : awaitingFinal
              ? "The catalogue records verified entry points, not results incorporated automatically. The second-round final declaration is still awaiting verification, so this repository does not publish a real election release."
              : "The catalogue contains a verified final declaration as a candidate source. That does not publish a release automatically: every reconciliation, coverage, methodology, wording, and product gate must still pass."}
        </p>
        <p className="mt-3">
          <a
            className="inline-flex min-h-11 items-center border-b border-ink font-semibold underline-offset-4 hover:bg-neon"
            href={catalog.official_hub}
            rel="noreferrer"
          >
            {es ? "Portal oficial de la elección" : "Official election portal"}
          </a>{" "}
          ·{" "}
          <code className="font-mono text-xs">{catalog.publication_state}</code>{" "}
          · {catalog.verified_at}
        </p>
      </Section>

      <div className="border-y border-ink">
        {catalog.sources.map((source, index) => (
          <article
            className="border-b border-ink py-6 last:border-b-0"
            key={source.id}
          >
            <p className="break-all font-mono text-xs font-bold tracking-[.1em] text-muted uppercase">
              <span aria-hidden="true" className="mr-3 text-ink">
                {String(index + 1).padStart(2, "0")}
              </span>
              {source.role}
            </p>
            <h2 className="mt-2 break-all font-mono text-base font-bold tracking-[-0.02em]">
              {source.id}
            </h2>
            <p className="mt-2 text-sm text-muted">
              {legalStatusLabel(locale, source.legal_status)}
              {source.status ? ` · ${source.status}` : ""}
            </p>
            <ul className="mt-4 space-y-3 text-sm">
              {Object.entries(source.entrypoints).map(([name, url]) => (
                <li key={name}>
                  <strong>{name}:</strong>{" "}
                  {url.includes("{") ? (
                    <code className="break-all font-mono text-xs">{url}</code>
                  ) : (
                    <a
                      className="break-all font-mono text-xs underline"
                      href={url}
                      rel="noreferrer"
                    >
                      {url}
                    </a>
                  )}
                </li>
              ))}
            </ul>
            {source.notes && (
              <p className="mt-4 break-words text-sm text-muted">
                {source.notes}
              </p>
            )}
          </article>
        ))}
      </div>

      <Section title={es ? "Contexto, no señal" : "Context, not a signal"}>
        <ul className="list-disc space-y-2 pl-5">
          {catalog.contextual_sources.map((source) => (
            <li key={source.id}>
              <a className="underline" href={source.url} rel="noreferrer">
                {source.id}
              </a>{" "}
              — {es ? "solo contexto histórico" : "historical context only"}
            </li>
          ))}
        </ul>
      </Section>

      <Section
        title={es ? "Fuente de esta pantalla" : "Source for this screen"}
      >
        <p>
          <code className="font-mono text-xs">
            {release.provenance.source_type}
          </code>{" "}
          ·{" "}
          <code className="font-mono text-xs">
            {release.provenance.legal_status}
          </code>{" "}
          ·{" "}
          <code className="break-all font-mono text-xs">
            {release.provenance.content_hash}
          </code>
        </p>
      </Section>
    </Page>
  );
}
