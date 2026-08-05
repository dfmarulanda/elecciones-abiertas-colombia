import { setRequestLocale } from "next-intl/server";
import { Page } from "@/components/page-primitives";
export default async function GlossaryPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const es = locale === "es";
  const terms = es
    ? [
        ["Mesa", "Unidad de votación identificada por una ruta estable."],
        ["Preconteo", "Capa preliminar; no es una declaración final."],
        [
          "Proveniencia",
          "Datos para rastrear versión, origen, recuperación y huella.",
        ],
        ["Desconocido", "El valor no se conoce; no equivale a cero."],
        [
          "No disponible",
          "El valor o documento no está publicado o accesible.",
        ],
        [
          "Señal de revisión",
          "Prioridad de revisión documental; no mide ni determina fraude.",
        ],
      ]
    : [
        ["Mesa", "Voting unit identified by a stable route."],
        ["Pre-count", "Preliminary layer; not a final declaration."],
        [
          "Provenance",
          "Fields that trace version, origin, retrieval, and digest.",
        ],
        ["Unknown", "The value is not known; it is not zero."],
        [
          "Unavailable",
          "The value or document is not published or accessible.",
        ],
        [
          "Review signal",
          "A documentary-review priority; it does not measure or determine fraud.",
        ],
      ];
  return (
    <Page
      locale={locale}
      eyebrow={es ? "Términos de lectura" : "Reading terms"}
      title={es ? "Glosario" : "Glossary"}
    >
      <dl className="divide-y divide-ink border-y border-ink">
        {terms.map(([term, definition], index) => (
          <div
            className="grid gap-2 py-5 sm:grid-cols-[5rem_1fr_2fr]"
            key={term}
          >
            <span
              aria-hidden="true"
              className="font-mono text-xs font-bold text-muted"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
            <dt className="font-display text-lg font-bold tracking-[-0.03em] uppercase">
              {term}
            </dt>
            <dd className="sm:col-span-2 text-sm leading-7 text-muted">
              {definition}
            </dd>
          </div>
        ))}
      </dl>
    </Page>
  );
}
