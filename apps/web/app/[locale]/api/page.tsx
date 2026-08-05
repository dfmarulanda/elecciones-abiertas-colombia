import { setRequestLocale } from "next-intl/server";
import { Page, Section } from "@/components/page-primitives";
export default async function ApiPage({
  params,
}: {
  params: Promise<{ locale: "es" | "en" }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const es = locale === "es";
  const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  const routes = [
    "GET /api/v1/elections/{slug}/summary",
    "GET /api/v1/elections/{slug}/results",
    "GET /api/v1/geographies/{id}",
    "GET /api/v1/mesas/{id}",
    "GET /api/v1/mesas/{id}/evidence",
    "GET /api/v1/mesas/{id}/comparisons",
    "GET /api/v1/bulletins",
    "GET /api/v1/bulletins/{id}/results",
    "GET /api/v1/review-signals",
    "GET /api/v1/datasets",
    "GET /api/v1/datasets/{id}/download",
    "GET /api/v1/openapi.json",
  ];
  return (
    <Page
      locale={locale}
      eyebrow="OpenAPI"
      title={es ? "API pública" : "Public API"}
    >
      <Section title={es ? "Contrato y versiones" : "Contract and versions"}>
        <p>
          {es
            ? "La interfaz se apoya en tipos generados del contrato OpenAPI. Las respuestas versionadas usan data_version y una huella de contenido; clientes deben tratar los valores desconocidos o no disponibles como estados, no como ceros."
            : "The interface relies on types generated from the OpenAPI contract. Versioned responses use data_version and a content digest; clients must treat unknown or unavailable values as states, not zeroes."}
        </p>
      </Section>
      <Section title={es ? "Rutas principales" : "Main routes"}>
        <ul className="mt-5 divide-y divide-ink border-y border-ink">
          {routes.map((route) => (
            <li className="py-3" key={route}>
              <code className="break-all font-mono text-xs text-ink">
                {route}
              </code>
            </li>
          ))}
        </ul>
        <p className="mt-4">
          {apiBase ? (
            <a
              className="inline-flex min-h-11 items-center border-b border-ink font-semibold underline-offset-4 hover:bg-neon"
              href={`${apiBase}/api/v1/openapi.json`}
              rel="noreferrer"
            >
              {es ? "Abrir contrato OpenAPI" : "Open the OpenAPI contract"}
            </a>
          ) : es ? (
            "Configure NEXT_PUBLIC_API_URL para enlazar un despliegue del API."
          ) : (
            "Configure NEXT_PUBLIC_API_URL to link an API deployment."
          )}
        </p>
      </Section>
      <Section title={es ? "Uso responsable" : "Responsible use"}>
        <p>
          {es
            ? "Compruebe data_version, estado jurídico, URL oficial y huella en cada respuesta. Cuando se use la fijación sintética, sus endpoints y valores siguen siendo solo demostrativos."
            : "Check data_version, legal status, official URL, and digest in every response. When synthetic fixture mode is used, its endpoints and values remain demonstrations only."}
        </p>
      </Section>
    </Page>
  );
}
