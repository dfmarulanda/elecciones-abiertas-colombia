import { setRequestLocale } from "next-intl/server";
import { dataAdapter } from "@/data/fixture-adapter";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";
import { Page, Section } from "@/components/page-primitives";

export const dynamic = "force-dynamic";

export default async function PrivacyPage({
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
  const es = locale === "es";
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
      eyebrow={es ? "Datos y documentos" : "Data and documents"}
      title={es ? "Privacidad" : "Privacy"}
    >
      <Section title={es ? "Principio de minimización" : "Data minimization"}>
        <p>
          {es
            ? "Este visor presenta información de resultados y metadatos de trazabilidad. Para actas, solo indexa metadatos y enlaces oficiales: no descarga, conserva en caché, copia, procesa con OCR ni transcribe documentos."
            : "This viewer presents result information and traceability metadata. For records, it only indexes metadata and official links: it does not download, cache, copy, OCR, or transcribe documents."}
        </p>
      </Section>
      <Section title={es ? "Este entorno" : "This environment"}>
        <p>
          {release.release.synthetic
            ? es
              ? "La fijación actual es sintética. Las URLs son ejemplos y no deben usarse para inferir la existencia de personas, mesas, documentos o resultados reales."
              : "The current fixture is synthetic. URLs are examples and must not be used to infer the existence of real people, mesas, documents, or results."
            : es
              ? "Este entorno presenta un preconteo preliminar real y no lo representa como escrutinio certificado. El visor no conserva documentos de acta ni expone datos personales extraídos de ellos."
              : "This environment presents a real preliminary pre-count and does not represent it as certified scrutiny. The viewer does not retain record documents or expose personal data extracted from them."}
        </p>
      </Section>
      <Section title={es ? "Enlaces externos" : "External links"}>
        <p>
          {es
            ? "Al abrir un original oficial o descarga, aplican las prácticas de privacidad del sitio de destino."
            : "When opening an official original or download, the destination site’s privacy practices apply."}
        </p>
      </Section>
    </Page>
  );
}
