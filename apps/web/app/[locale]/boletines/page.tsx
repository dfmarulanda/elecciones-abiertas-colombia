import { setRequestLocale } from "next-intl/server";
import { dataAdapter } from "@/data/fixture-adapter";
import { Page, Section } from "@/components/page-primitives";
import { formatDate, formatNumber, formatPercent } from "@/lib/utils";
export const dynamic = "force-dynamic";
export default async function BulletinsPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const release = await dataAdapter.getRelease({ include: "bulletins" });
  const es = locale === "es";
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Progresión descriptiva" : "Descriptive progression"}
      title={es ? "Boletines preliminares" : "Preliminary bulletins"}
    >
      <Section
        title={
          es ? "Cómo leer esta línea de tiempo" : "How to read this timeline"
        }
      >
        <p>
          {es
            ? "Cada hito muestra lo reportado en ese corte. El orden, los cambios tardíos y el momento de una revisión son descriptivos, puntúan cero y no estiman tendencia, resultado final ni certeza electoral."
            : "Each point shows what was reported at that cut. Reporting order, late changes, and revision timing are descriptive, score zero, and do not estimate a trend, final result, or electoral certainty."}
        </p>
      </Section>
      <ol
        className="border-t border-ink"
        aria-label={es ? "Línea de tiempo de boletines" : "Bulletin timeline"}
      >
        {release.bulletins.map((bulletin) => (
          <li className="border-x border-b border-ink" key={bulletin.id}>
            <div className="flex flex-wrap items-baseline justify-between gap-3 bg-ink px-4 py-4 text-paper sm:px-5">
              <h2 className="font-display text-2xl font-bold tracking-[-0.035em] uppercase">
                {es ? "Boletín" : "Bulletin"} {bulletin.sequence}
              </h2>
              <time className="font-mono text-xs text-[#9B9B9B]">
                {formatDate(bulletin.published_at, locale)}
              </time>
            </div>
            <dl className="grid sm:grid-cols-3">
              <div className="border-b border-ink p-4 sm:border-r sm:border-b-0 sm:p-5">
                <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
                  {es ? "Avance reportado" : "Reported progress"}
                </dt>
                <dd className="mt-2 font-display text-2xl font-bold tabular-nums">
                  {formatPercent(bulletin.completion_percent, locale)}
                </dd>
              </div>
              <div className="border-b border-ink p-4 sm:border-r sm:border-b-0 sm:p-5">
                <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
                  {es ? "Mesas" : "Mesas"}
                </dt>
                <dd className="mt-2 font-display text-2xl font-bold tabular-nums">
                  {bulletin.reported_mesas} / {bulletin.expected_mesas}
                </dd>
              </div>
              <div className="min-w-0 p-4 sm:p-5">
                <dt className="font-mono text-[11px] font-bold tracking-[.08em] text-muted uppercase">
                  Hash
                </dt>
                <dd className="mt-2 break-all font-mono text-xs">
                  {bulletin.content_hash}
                </dd>
              </div>
            </dl>
            {Object.keys(bulletin.candidate_votes).length > 0 && (
              <p className="border-t border-ink px-4 py-4 text-sm text-muted sm:px-5">
                {release.election.candidates
                  .filter(
                    (candidate) => candidate.id in bulletin.candidate_votes,
                  )
                  .map(
                    (candidate) =>
                      `${candidate.name[locale]} · ${formatNumber(bulletin.candidate_votes[candidate.id], locale)}`,
                  )
                  .join(" · ")}
              </p>
            )}
            <p className="border-t border-ink px-4 py-4 text-xs text-muted sm:px-5">
              <a
                className="underline underline-offset-4"
                href={bulletin.source_url}
                rel="noreferrer"
              >
                {es
                  ? "Fuente oficial del corte"
                  : "Official source for this cut"}
              </a>{" "}
              · <code>{bulletin.data_version}</code>
            </p>
          </li>
        ))}
      </ol>
    </Page>
  );
}
