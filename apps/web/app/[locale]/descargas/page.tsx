import { setRequestLocale } from "next-intl/server";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";
import { dataAdapter } from "@/data/fixture-adapter";
import { Page, Section } from "@/components/page-primitives";
import { formatNumber } from "@/lib/utils";
export const dynamic = "force-dynamic";
export default async function DownloadsPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const guard = await loadReleaseOrUnavailable(locale, () =>
    dataAdapter.getRelease({ include: "datasets" }),
  );
  if (guard.fallback) return guard.fallback;
  const release = guard.release;
  const es = locale === "es";
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Releases inmutables" : "Immutable releases"}
      title={es ? "Descargas" : "Downloads"}
    >
      <Section
        title={
          es
            ? release.release.synthetic
              ? "Contenido sintético con trazabilidad"
              : "Artefactos publicados con trazabilidad"
            : release.release.synthetic
              ? "Synthetic content with traceability"
              : "Published artifacts with traceability"
        }
      >
        <p>
          {es
            ? release.release.synthetic
              ? "Cada tarjeta declara formato, conteo, hash y esquema. Esta fijación no ofrece descargas públicas porque sus rutas son solo demostrativas."
              : "Cada tarjeta declara formato, conteo, tamaño, hash, esquema y filtros de su artefacto inmutable."
            : release.release.synthetic
              ? "Each card declares format, count, hash, and schema. This fixture offers no public downloads because its routes are demonstrations only."
              : "Each card declares its immutable artifact format, count, size, hash, schema, and filters."}
        </p>
      </Section>
      <div className="grid gap-px border border-ink bg-ink md:grid-cols-3">
        {release.datasets.map((dataset, index) => (
          <article className="bg-paper p-5 sm:p-6" key={dataset.id}>
            <p className="font-mono text-xs font-bold tracking-[.14em] text-muted uppercase">
              <span aria-hidden="true" className="mr-3 text-ink">
                {String(index + 1).padStart(2, "0")}
              </span>
              {dataset.format}
            </p>
            <h2 className="mt-2 font-display text-xl font-bold tracking-[-0.035em] uppercase">
              {dataset.title[locale]}
            </h2>
            <dl className="mt-5 space-y-3 text-sm">
              <div>
                <dt className="font-bold">{es ? "Registros" : "Records"}</dt>
                <dd>{formatNumber(dataset.record_count, locale)}</dd>
              </div>
              <div>
                <dt className="font-bold">{es ? "Tamaño" : "Size"}</dt>
                <dd>{formatNumber(dataset.byte_size, locale)} bytes</dd>
              </div>
              <div>
                <dt className="font-bold">Hash SHA-256</dt>
                <dd className="break-all font-mono text-xs">
                  {dataset.content_hash}
                </dd>
              </div>
              <div>
                <dt className="font-bold">{es ? "Esquema" : "Schema"}</dt>
                <dd>
                  <a
                    className="break-all font-mono text-xs underline"
                    href={dataset.schema_url}
                    rel="noreferrer"
                  >
                    {dataset.schema_url}
                  </a>
                </dd>
              </div>
            </dl>
            {release.release.synthetic ? (
              <span className="mt-6 inline-flex min-h-11 items-center text-sm font-bold text-muted">
                {es
                  ? "Descarga deshabilitada para la fijación"
                  : "Download disabled for fixture"}
              </span>
            ) : (
              <a
                className="mt-6 inline-flex min-h-11 items-center border border-ink bg-ink px-4 text-sm font-bold text-paper hover:bg-neon hover:text-ink"
                href={dataset.url}
                rel="noreferrer"
              >
                {es ? "Abrir descarga" : "Open download"}
              </a>
            )}
          </article>
        ))}
      </div>
      <Section title={es ? "Manifiesto" : "Manifest"}>
        <p>
          {es ? "Release: " : "Release: "}
          <code className="font-mono text-xs">
            {release.release.release_id}
          </code>{" "}
          · {es ? "Estado:" : "Status:"}{" "}
          <code className="font-mono text-xs">{release.release.status}</code> ·{" "}
          {release.release.methodology_version !== "unavailable" && (
            <>
              {es ? "Método:" : "Method:"}{" "}
              <code className="font-mono text-xs">
                {release.release.methodology_version}
              </code>
              .
            </>
          )}
        </p>
      </Section>
    </Page>
  );
}
