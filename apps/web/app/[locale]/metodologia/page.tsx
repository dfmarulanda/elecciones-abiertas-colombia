import { setRequestLocale } from "next-intl/server";

import { Page, Section } from "@/components/page-primitives";
import { dataAdapter } from "@/data/fixture-adapter";
import { loadReleaseOrUnavailable } from "@/lib/release-guard";
import { reviewDisclosure } from "@/lib/review-disclosure";

export const dynamic = "force-dynamic";

const points = [
  [
    "100",
    "Falla contable E-14 con doble verificación o registros oficiales en conflicto",
    "Double-verified E-14 accounting failure or conflicting official records",
  ],
  [
    "70",
    "Diferencia documental de al menos 5 votos o 2 puntos porcentuales",
    "Documentary difference of at least 5 votes or 2 percentage points",
  ],
  [
    "45",
    "Diferencia documental de 1–4 votos y menos de 2 puntos porcentuales",
    "Documentary difference of 1–4 votes and below 2 percentage points",
  ],
  [
    "25",
    "Documento oficial esperado faltante, duplicado o ambiguo",
    "Missing, duplicated, or ambiguous expected official document",
  ],
  [
    "10",
    "Señal independiente en la distribución de pares",
    "Independent peer-distribution signal",
  ],
  [
    "10",
    "Señal independiente de agrupación espacial",
    "Independent spatial-cluster signal",
  ],
] as const;

export default async function MethodologyPage({
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
      eyebrow={es ? "Método reproducible" : "Reproducible method"}
      title={es ? "Metodología" : "Methodology"}
    >
      <Section
        title={es ? "Capas que nunca se mezclan" : "Layers that never merge"}
      >
        <ol className="list-decimal space-y-2 pl-5">
          <li>
            {es
              ? "La declaración final del CNE controla los totales finales cuando esté verificada."
              : "The verified CNE final declaration controls final totals."}
          </li>
          <li>
            {es
              ? "El escrutinio controla únicamente la granularidad que publica."
              : "Scrutiny controls only the grain it explicitly publishes."}
          </li>
          <li>
            {es
              ? "El índice E-14 enlaza documentos oficiales y conserva solo sus metadatos de índice; el visor no descarga, copia, procesa con OCR ni transcribe actas."
              : "The E-14 index links official documents and keeps only index metadata; the viewer does not download, copy, OCR, or transcribe records."}
          </li>
          <li>
            {es
              ? "El preconteo es preliminar e informativo."
              : "Pre-count is preliminary and informational."}
          </li>
          <li>
            {es
              ? "2026 primera vuelta y 2022 son contexto, nunca una señal de integridad."
              : "The 2026 first round and 2022 are context, never integrity signals."}
          </li>
        </ol>
      </Section>

      <Section
        title={
          es ? "Conciliación determinista" : "Deterministic reconciliation"
        }
      >
        <p>
          {es
            ? "Antes de cualquier modelo se validan enteros no negativos, identidades canónicas, reglas aritméticas propias de cada fuente, límites de electores solo cuando el campo existe, cobertura y agregación exacta. Las comparaciones requieren la misma granularidad. Una corrección oficial se etiqueta como corrección."
            : "Before any model, the pipeline validates nonnegative integers, canonical identities, source-specific arithmetic, elector bounds only when the field exists, coverage, and exact aggregation. Comparisons require the same grain. An official correction remains labelled as a correction."}
        </p>
        <p className="mt-3">
          {release.release.synthetic
            ? es
              ? "Las señales de pares, espaciales y de sensibilidad de esta demostración sintética son experimentales. Nunca convierten una señal estadística en votos afectados."
              : "Peer, spatial, and outcome-sensitivity signals in this synthetic demonstration are experimental. They never turn a statistical signal into affected votes."
            : es
              ? "El release público actual contiene un preconteo preliminar real y no publica señales de prioridad de auditoría. Las tres excepciones de conciliación se conservan explícitamente; una señal estadística nunca equivale a votos afectados."
              : "The current public release contains a real preliminary pre-count and publishes no audit-priority signals. Its three reconciliation exceptions remain explicit; a statistical signal never equals affected votes."}
        </p>
      </Section>

      <Section
        title={
          es ? "Puntaje de prioridad de auditoría" : "Audit-priority score"
        }
      >
        <p className="mb-4">{reviewDisclosure[locale]}</p>
        <div className="overflow-x-auto border border-ink">
          <table className="w-full min-w-[620px] text-left text-sm">
            <caption className="sr-only">
              {es
                ? "Tabla de componentes del puntaje"
                : "Score component table"}
            </caption>
            <thead className="bg-ink font-mono text-xs uppercase text-paper">
              <tr>
                <th className="px-3 py-3">{es ? "Evidencia" : "Evidence"}</th>
                <th className="px-3 py-3">{es ? "Puntos" : "Points"}</th>
              </tr>
            </thead>
            <tbody>
              {points.map(([score, spanish, english]) => (
                <tr className="border-t border-ink" key={score + spanish}>
                  <td className="px-3 py-3">{es ? spanish : english}</td>
                  <td className="px-3 py-3">
                    <span className="inline-flex min-h-7 items-center border border-ink bg-neon px-2 font-mono text-xs font-bold text-ink">
                      {score}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4">
          {es
            ? "Se usa el componente determinista más alto, más un máximo de 20 puntos estadísticos, con tope total de 100. Los rangos públicos son 70–100, 45–69, 15–44 y 0–14. Un componente de 10 puntos puede figurar en el detalle aun si el puntaje total queda bajo el nivel de revisión. Una versión nueva de metodología recalcula todos los puntajes."
            : "The highest deterministic component is used, plus at most 20 statistical points, capped at 100. Public tier ranges are 70–100, 45–69, 15–44, and 0–14. A 10-point component may appear in detail even when the total stays below the review tier. A new methodology version recomputes every score."}
        </p>
      </Section>

      <Section title={es ? "Reglas estadísticas" : "Statistical rules"}>
        <ul className="list-disc space-y-2 pl-5">
          <li>
            {es
              ? "Modelo beta-binomial empírico-bayesiano con conteos enteros y sin la mesa evaluada: cada métrica exige su propio denominador de al menos 80 y el primer grupo disponible de 30 pares (puesto, municipio o departamento)."
              : "Leave-one-out empirical-Bayes beta-binomial model on integer counts: each metric needs its own denominator of at least 80 and the first available 30-peer pool (place, municipality, or department)."}
          </li>
          <li>
            {es
              ? "Se calculan todos los valores p de una familia inmutable antes de una única corrección conservadora Benjamini–Yekutieli. Se requieren simultáneamente: cola predictiva EB ≤ 0,001, q BY ≤ 0,05, residuo absoluto ≥ 3,5 y efecto mínimo."
              : "Every p value in one immutable family is calculated before a single conservative Benjamini–Yekutieli adjustment. All are required: EB predictive tail ≤ 0.001, BY q ≤ 0.05, absolute residual ≥ 3.5, and the minimum effect."}
          </li>
          <li>
            {es
              ? "La señal espacial se vincula al artefacto hasheado de residuales. Agrupa coordenadas de puesto antes de analizar, exige 100 unidades municipales, hasta cinco vecinas dentro de 20 km, al menos tres y 9.999 permutaciones condicionales con semilla estable; corrige toda la familia con BY."
              : "The spatial signal binds the hashed residual artifact. It collapses polling-place coordinates before analysis, requires 100 municipal units, up to five neighbours within 20 km, at least three, and 9,999 seeded conditional permutations; it corrects the full family with BY."}
          </li>
          <li>
            {es
              ? "No se usa la ley de Benford. El orden de reporte y los cambios históricos son descriptivos y puntúan cero."
              : "Benford’s law is not used. Reporting order and historical changes are descriptive and score zero."}
          </li>
        </ul>
      </Section>

      <Section title={es ? "Puertas de publicación" : "Publication gates"}>
        <p>
          {es
            ? "No se publica un release con señales hasta que pasen cobertura, conciliación agregada, trazabilidad, un artefacto de validación estadística hasheado (100 o más corridas, cota binomial unilateral y FDR empírico), revisión de redacción y controles de datos personales. El preconteo actual se expone mediante una vía preliminar separada: es público e inmutable, pero no está certificado y no habilita señales de revisión."
            : "A release with signals is not published until coverage, aggregate reconciliation, traceability, a hashed statistical-validation artifact (100+ runs, one-sided binomial bound, and empirical FDR), wording review, and personal-data controls pass. The current pre-count uses a separate preliminary exposure path: it is public and immutable, but not certified and does not enable review signals."}
        </p>
      </Section>
    </Page>
  );
}
