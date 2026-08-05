import Link from "next/link";
import { setRequestLocale } from "next-intl/server";
import {
  dataAdapter,
  type EvidenceIndexDocument,
} from "@/data/fixture-adapter";
import { Page, Section } from "@/components/page-primitives";
import { releaseMetadata } from "@/lib/seo";
import type { Metadata } from "next";
export const dynamic = "force-dynamic";

type EvidenceDocument = EvidenceIndexDocument;

const documentTypeLabels: Record<
  EvidenceDocument["document_type"],
  Record<"es" | "en", string>
> = {
  e14_delegate: { es: "E-14 de delegados", en: "Delegate E-14" },
  e14_transmission: { es: "E-14 de transmisión", en: "Transmission E-14" },
};

function sourceHost(url: string) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: "es" | "en"; mesaId: string }>;
}): Promise<Metadata> {
  const { locale, mesaId } = await params;
  const canonicalMesa = `/resultados/mesa/${encodeURIComponent(mesaId)}`;
  try {
    await dataAdapter.getNationalSummary();
    // The E-14 screen is an index of outbound official links, not a result or
    // document copy. Search engines should consolidate it to the mesa result.
    return releaseMetadata({
      locale,
      pathname: `/actas/${encodeURIComponent(mesaId)}`,
      canonicalPathname: canonicalMesa,
      title:
        locale === "es" ? `Índice E-14 · ${mesaId}` : `E-14 index · ${mesaId}`,
      description:
        locale === "es"
          ? "Índice de enlaces oficiales E-14 para una mesa electoral."
          : "Index of official E-14 links for an electoral mesa.",
      release: null,
      page: "mesa",
    });
  } catch {
    return releaseMetadata({
      locale,
      pathname: `/actas/${encodeURIComponent(mesaId)}`,
      canonicalPathname: canonicalMesa,
      title: locale === "es" ? "Índice E-14" : "E-14 index",
      description: "Official document links require an available release.",
      page: "mesa",
    });
  }
}

export default async function RecordPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en"; mesaId: string }>;
}) {
  const { locale, mesaId } = await params;
  setRequestLocale(locale);
  const es = locale === "es";
  const [docs, release] = await Promise.all([
    dataAdapter.getEvidence(mesaId),
    dataAdapter.getNationalSummary(),
  ]);
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Evidencia documental" : "Documentary evidence"}
      title={`${es ? "Actas de mesa" : "Mesa records"} · ${mesaId}`}
    >
      <p className="mb-6 text-sm text-muted">
        <Link
          className="underline"
          href={`/${locale}/resultados/mesa/${mesaId}`}
        >
          {es
            ? "Volver a la ruta canónica de resultados"
            : "Back to canonical results route"}
        </Link>
      </p>
      <Section
        title={
          es
            ? "Índice de E-14 y enlace oficial"
            : "E-14 index and official link"
        }
      >
        <p className="max-w-3xl">
          {es
            ? "Este visor solo indexa metadatos y enlaces oficiales. No descarga, conserva en caché, copia, redacta, procesa con OCR ni transcribe actas. El documento oficial permanece en su sitio de origen."
            : "This viewer only indexes metadata and official links. It does not download, cache, copy, redact, OCR, or transcribe records. The official document remains at its source site."}
        </p>
        {docs.length ? (
          <div className="border-t border-ink">
            {docs.map((document) => (
              <article
                className="border-x border-b border-ink p-5"
                key={document.id}
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h3 className="font-bold">
                    {documentTypeLabels[document.document_type][locale]}
                  </h3>
                  <span className="border border-ink px-3 py-1 font-mono text-xs font-bold uppercase">
                    {es
                      ? "Indexado · No solicitada por el visor"
                      : "Indexed · Not requested by the viewer"}
                  </span>
                </div>
                <p className="mt-3">
                  {es
                    ? "El enlace apunta al documento oficial. Su presencia en este índice no confirma contenido, resultados ni una revisión documental."
                    : "The link points to the official document. Its presence in this index does not confirm content, results, or a documentary review."}
                </p>
                <p className="mt-2 text-xs text-muted">
                  {es
                    ? "Host oficial verificado: "
                    : "Verified official host: "}
                  <span className="font-semibold text-ink">
                    {sourceHost(document.official_url)}
                  </span>
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <a
                    className="inline-flex min-h-11 items-center border border-ink bg-ink px-4 text-sm font-bold text-paper hover:bg-neon hover:text-ink"
                    href={document.official_url}
                    rel="noreferrer"
                  >
                    {es ? "Abrir enlace oficial" : "Open official link"}
                  </a>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p>
            {es
              ? "No hay documento indexado para esta mesa sintética. Eso no implica que exista o no exista un acta real."
              : "No document is indexed for this synthetic mesa. That does not imply whether a real record exists."}
          </p>
        )}
      </Section>
      <Section title={es ? "Cobertura del índice" : "Index coverage"}>
        <p>
          {es
            ? `${docs.length} documento${docs.length === 1 ? "" : "s"} indexado${docs.length === 1 ? "" : "s"} para esta mesa en esta versión. Los campos de votos, comparaciones, transcripciones y cualquier derivado no se publican en esta vista.`
            : `${docs.length} document${docs.length === 1 ? "" : "s"} indexed for this mesa in this version. Vote fields, comparisons, transcriptions, and any derivatives are not published in this view.`}
        </p>
      </Section>
    </Page>
  );
}
