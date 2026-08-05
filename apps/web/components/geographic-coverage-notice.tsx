import type { components } from "@elecciones/contracts";
import React from "react";

import { formatNumber } from "@/lib/utils";

type Coverage = components["schemas"]["GeographicCollectionCoverage"];

export function GeographicCoverageNotice({
  coverage,
  locale,
}: {
  coverage: Coverage | undefined;
  locale: "es" | "en";
}) {
  if (!coverage || coverage.status === "full_scope") return null;
  const es = locale === "es";
  const places = `${formatNumber(coverage.retrieved_polling_places, locale)} / ${formatNumber(coverage.expected_polling_places, locale)}`;
  const mesas = `${formatNumber(coverage.retrieved_mesas, locale)} / ${formatNumber(coverage.expected_mesas, locale)}`;
  const body =
    coverage.status === "sample_limited"
      ? es
        ? `La geografía disponible es una muestra, no una cobertura nacional: ${places} puestos de votación y ${mesas} mesas recolectadas. La fuente oficial consultada no publica el censo electoral por mesa; no se infiere ni reparte. No use las vistas territoriales para inferir resultados nacionales.`
        : `The available geography is a sample, not national coverage: ${places} polling places and ${mesas} mesas collected. The official source used here does not publish a mesa-level electorate; none is inferred or apportioned. Do not use territorial views to infer national results.`
      : es
        ? "Esta versión solo incluye el agregado nacional; todavía no hay recolección geográfica para interpretar mapas o resultados por mesa."
        : "This release includes only the national aggregate; geographic collection is not yet available for interpreting maps or mesa-level results.";
  return (
    <aside
      className="border border-ink bg-ink px-4 py-4 text-sm leading-6 text-paper"
      aria-label={
        es ? "Límite de cobertura geográfica" : "Geographic coverage limit"
      }
    >
      <p className="inline-block bg-neon px-2 py-1 font-mono text-xs font-bold tracking-[.08em] text-ink uppercase">
        {es ? "Cobertura geográfica limitada" : "Limited geographic coverage"}
      </p>
      <p className="mt-1">{body}</p>
    </aside>
  );
}
