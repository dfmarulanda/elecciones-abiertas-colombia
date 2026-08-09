import { serializeResultFilters, type ResultFilters } from "./result-filters";

export function decodeRouteIdentifier(identifier: string | undefined) {
  if (!identifier) return identifier;
  try {
    return decodeURIComponent(identifier);
  } catch {
    return identifier;
  }
}

export function mesaRoute(
  locale: "es" | "en",
  mesaId: string,
  filters: ResultFilters = {},
) {
  const query = serializeResultFilters(filters);
  return `/${locale}/resultados/mesa/${encodeURIComponent(mesaId)}${query ? `?${query}` : ""}`;
}

export function geographyRoute(
  locale: "es" | "en",
  geographyId: string,
  filters: ResultFilters = {},
) {
  const query = serializeResultFilters(filters);
  return `/${locale}/resultados/geografia/${encodeURIComponent(geographyId)}${query ? `?${query}` : ""}`;
}

export function isCanonicalMesaSegment(segments: string[]) {
  return (
    segments.length === 2 && segments[0] === "mesa" && Boolean(segments[1])
  );
}
