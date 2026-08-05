export type PublicLocale = "es" | "en";

type PublicLabels = Record<string, readonly [es: string, en: string]>;

export type PublicResultLabels = {
  geography: Record<string, string>;
  source: Record<string, string>;
  unknown: string;
};

const geographyLabels: PublicLabels = {
  national: ["Nacional", "National"],
  department: ["Departamento", "Department"],
  municipality: ["Municipio", "Municipality"],
  zone: ["Zona", "Zone"],
  polling_place: ["Puesto de votación", "Polling place"],
  mesa: ["Mesa", "Mesa"],
};

const sourceLabels: PublicLabels = {
  final_declaration: ["Declaratoria final", "Final declaration"],
  scrutiny: ["Escrutinio", "Scrutiny"],
  e14_delegate: ["E-14 de delegados", "Delegate E-14"],
  e14_transmission: ["E-14 de transmisión", "Transmission E-14"],
  pre_count: ["Preconteo", "Pre-count"],
  contextual_baseline: ["Contexto histórico", "Historical context"],
};

const legalLabels: PublicLabels = {
  controlling_final: ["Final vinculante", "Controlling final"],
  official_scrutiny: ["Escrutinio oficial", "Official scrutiny"],
  documentary_evidence: ["Evidencia documental", "Documentary evidence"],
  preliminary: ["Preliminar", "Preliminary"],
  context_only: ["Sólo contexto", "Context only"],
};

function publicLabel(
  labels: PublicLabels,
  locale: PublicLocale,
  value: string,
) {
  return (
    labels[value]?.[locale === "es" ? 0 : 1] ??
    (locale === "es" ? "No clasificado" : "Unclassified")
  );
}

export const geographyLevelLabel = (locale: PublicLocale, value: string) =>
  publicLabel(geographyLabels, locale, value);

export const sourceTypeLabel = (locale: PublicLocale, value: string) =>
  publicLabel(sourceLabels, locale, value);

export const legalStatusLabel = (locale: PublicLocale, value: string) =>
  publicLabel(legalLabels, locale, value);

export function publicResultLabels(locale: PublicLocale): PublicResultLabels {
  const index = locale === "es" ? 0 : 1;
  return {
    geography: Object.fromEntries(
      Object.entries(geographyLabels).map(([value, labels]) => [
        value,
        labels[index],
      ]),
    ),
    source: Object.fromEntries(
      Object.entries(sourceLabels).map(([value, labels]) => [
        value,
        labels[index],
      ]),
    ),
    unknown: locale === "es" ? "No clasificado" : "Unclassified",
  };
}

export function directChildrenLabel(locale: PublicLocale, count: number) {
  if (locale === "es")
    return count === 1 ? "1 unidad hija" : `${count} unidades hijas`;
  return count === 1 ? "1 direct child" : `${count} direct children`;
}
