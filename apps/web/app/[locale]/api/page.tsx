import { setRequestLocale } from "next-intl/server";
import { dataAdapter } from "@/data/fixture-adapter";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";
import { Page, Section } from "@/components/page-primitives";

export const dynamic = "force-dynamic";

export default async function ApiPage({
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
  const apiBase = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  const routes = [
    "GET /api/v1/release-elections",
    "GET /api/v1/releases/{release}/elections/{election}/summary",
    "GET /api/v1/releases/{release}/elections/{election}/results",
    "GET /api/v1/releases/{release}/elections/{election}/geographies/{id}",
    "GET /api/v1/releases/{release}/elections/{election}/geographies/{id}/children",
    "GET /api/v1/releases/{release}/elections/{election}/geographies/{id}/children-results",
    "GET /api/v1/releases/{release}/elections/{election}/mesas/{id}",
    "GET /api/v1/releases/{release}/elections/{election}/historical-comparison",
    "GET /api/v1/openapi.json",
  ];
  return (
    <Page
      locale={locale}
      synthetic={release.release.synthetic}
      releaseStatus={release.release.status}
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
          {release.release.synthetic
            ? es
              ? "Compruebe data_version, estado jurídico, URL oficial y huella en cada respuesta. Los endpoints y valores de esta fijación sintética son solo demostrativos."
              : "Check data_version, legal status, official URL, and digest in every response. The endpoints and values in this synthetic fixture are demonstrations only."
            : es
              ? "Compruebe data_version, estado jurídico, URL oficial, huella y X-Election-Data-Class en cada respuesta. El release activo es un preconteo preliminar: no lo trate como escrutinio certificado."
              : "Check data_version, legal status, official URL, digest, and X-Election-Data-Class in every response. The active release is a preliminary pre-count: do not treat it as certified scrutiny."}
        </p>
      </Section>
    </Page>
  );
}
