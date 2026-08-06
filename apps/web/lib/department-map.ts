/**
 * Reviewed, one-way identifiers for the boundary layer.
 *
 * These are deliberately not inferred from a label or a source code at runtime.
 * Election source identifiers use different code systems in the fixture, 2022
 * MMV data, and 2026 pre-count snapshots. A missing entry is therefore omitted.
 */
export type DepartmentMapRow = {
  geographyId: string;
  label: string;
  value: string;
  href?: string;
};

export type ReviewedDepartment = DepartmentMapRow & {
  daneCode: string;
  daneName: string;
};

const daneNames: Record<string, string> = {
  "05": "Antioquia",
  "08": "Atlántico",
  "11": "Bogotá, D. C.",
  "13": "Bolívar",
  "15": "Boyacá",
  "17": "Caldas",
  "18": "Caquetá",
  "19": "Cauca",
  "20": "Cesar",
  "23": "Córdoba",
  "25": "Cundinamarca",
  "27": "Chocó",
  "41": "Huila",
  "44": "La Guajira",
  "47": "Magdalena",
  "50": "Meta",
  "52": "Nariño",
  "54": "Norte de Santander",
  "63": "Quindío",
  "66": "Risaralda",
  "68": "Santander",
  "70": "Sucre",
  "73": "Tolima",
  "76": "Valle del Cauca",
  "81": "Arauca",
  "85": "Casanare",
  "86": "Putumayo",
  "88": "Archipiélago de San Andrés, Providencia y Santa Catalina",
  "91": "Amazonas",
  "94": "Guainía",
  "95": "Guaviare",
  "97": "Vaupés",
  "99": "Vichada",
};

const historicalCodes: Array<[string, string]> = [
  ["01", "05"],
  ["03", "08"],
  ["05", "13"],
  ["07", "15"],
  ["09", "17"],
  ["11", "19"],
  ["12", "20"],
  ["13", "23"],
  ["15", "25"],
  ["16", "11"],
  ["17", "27"],
  ["19", "41"],
  ["21", "47"],
  ["23", "52"],
  ["24", "66"],
  ["25", "54"],
  ["26", "63"],
  ["27", "68"],
  ["28", "70"],
  ["29", "73"],
  ["31", "76"],
  ["40", "81"],
  ["44", "18"],
  ["46", "85"],
  ["48", "44"],
  ["50", "94"],
  ["52", "50"],
  ["54", "95"],
  ["56", "88"],
  ["60", "91"],
  ["64", "86"],
  ["68", "97"],
  ["72", "99"],
];

/**
 * The 2026 release identifies departments as `scope:NN` using the SAME
 * Registraduría code system already reviewed for the historical releases, so
 * these entries reuse that reviewed mapping rather than introducing a second,
 * unreviewed one.
 *
 * Joining on the raw code would be catastrophic and silent: Registraduría `05`
 * is BOLÍVAR while DANE `05` is ANTIOQUIA, Registraduría `13` is CÓRDOBA while
 * DANE `13` is BOLÍVAR, and Registraduría `88` is CONSULADOS while DANE `88`
 * is the San Andrés archipelago — a code join would paint every overseas vote
 * onto an island. Nothing here may be derived from code equality.
 */
export const REVIEWED_DEPARTMENT_CROSSWALK: Record<string, string> = {
  "CO-ANT": "05",
  "CO-DC": "11",
  ...Object.fromEntries(
    historicalCodes.flatMap(([historicalCode, daneCode]) => [
      [`r1:dep:${historicalCode}`, daneCode],
      [`r2:dep:${historicalCode}`, daneCode],
      [`scope:${historicalCode}`, daneCode],
    ]),
  ),
};

/**
 * Departments that exist in the count but have no polygon, by nature rather
 * than by omission. `scope:88` is CONSULADOS — Colombians voting abroad, 3,670
 * mesas and 613,049 valid votes in the 2026 second round. There is no territory
 * to shade.
 *
 * This set exists because `reviewedDepartmentRows` drops anything it cannot
 * map, which would make those 613,049 votes disappear from the map with no
 * notice at all. An off-map entity must be rendered as one, never dropped and
 * never painted onto land.
 */
export const EXTRATERRITORIAL_GEOGRAPHY_IDS: ReadonlySet<string> = new Set([
  "scope:88",
  "r1:dep:88",
  "r2:dep:88",
]);

export type DepartmentPartition = {
  /** Rows with a reviewed polygon. */
  mapped: ReviewedDepartment[];
  /** Real rows that legitimately have no geometry (the exterior). */
  extraterritorial: DepartmentMapRow[];
  /** Rows matching neither — a crosswalk gap, surfaced instead of hidden. */
  unmapped: DepartmentMapRow[];
};

/**
 * Account for every row. Any caller rendering a map must show `mapped`, render
 * `extraterritorial` as an explicit off-map figure, and treat a non-empty
 * `unmapped` as a defect rather than as nothing to draw.
 */
export function partitionDepartments(
  rows: DepartmentMapRow[],
): DepartmentPartition {
  const mapped = reviewedDepartmentRows(rows);
  const claimed = new Set(
    rows
      .filter((row) => REVIEWED_DEPARTMENT_CROSSWALK[row.geographyId])
      .map((row) => row.geographyId),
  );
  const extraterritorial = rows.filter((row) =>
    EXTRATERRITORIAL_GEOGRAPHY_IDS.has(row.geographyId),
  );
  const unmapped = rows.filter(
    (row) =>
      !claimed.has(row.geographyId) &&
      !EXTRATERRITORIAL_GEOGRAPHY_IDS.has(row.geographyId),
  );
  return { mapped, extraterritorial, unmapped };
}

export function reviewedDepartmentRows(
  rows: DepartmentMapRow[],
): ReviewedDepartment[] {
  const byDaneCode = new Map<string, ReviewedDepartment>();

  for (const row of rows) {
    const daneCode = REVIEWED_DEPARTMENT_CROSSWALK[row.geographyId];
    const daneName = daneCode ? daneNames[daneCode] : undefined;
    if (!daneCode || !daneName || byDaneCode.has(daneCode)) continue;
    byDaneCode.set(daneCode, {
      ...row,
      daneCode,
      daneName,
      label: row.label || daneName,
    });
  }

  return [...byDaneCode.values()].sort((left, right) =>
    left.daneName.localeCompare(right.daneName, "es"),
  );
}

export const DANE_DEPARTMENT_BOUNDARY = {
  version: "Territoriales DANE 2025 · department layer 1 · simplified 0.01°",
  retrievedAt: "2026-08-04T03:51:30Z",
  sourceUrl:
    "https://geoportal.dane.gov.co/mparcgis/rest/services/Territoriales_DANE/Serv_Territoriales_DANE_2025/MapServer/1/query?where=1%3D1&outFields=dpto_ccdgo%2Cdpto_cnmbr&returnGeometry=true&f=geojson&outSR=4326&maxAllowableOffset=0.01",
  sourceResponseSha256:
    "7e0566ecaacaa99b616b1f3031cd474270fd0e5211a05a331f4c7bfd7fcca3c3",
  derivativePath: "/maps/dane-departments-2025-simplified.geojson",
  derivativeSha256:
    "a31064525fea7ad70e6cac9cc0a3a5c1d034f4f6b61cd822b9314b09a821083f",
  derivativeTransformVersion:
    "dane-arcgis-max-allowable-offset-0.01/1.0.0+local-final-lf/1.0.0",
  attribution:
    "© DANE — Marco Geoestadístico Nacional, Territoriales DANE 2025",
} as const;
