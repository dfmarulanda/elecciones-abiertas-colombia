export type ResultFilters = {
  release?: string;
  election?: string;
  source?: string;
  sourceId?: string;
  geography?: string;
  geographyPath?: string;
  level?: string;
  category?: string;
  status?: "observed" | "unavailable";
  baselineRelease?: string;
  baselineElection?: string;
  comparisonGrain?: string;
  candidate?: string;
  ballot?: string;
};

export type FixtureResultCsvRow = {
  mesa: string;
  geography: string;
  department: string;
  source: string;
  candidateId: string;
  candidate: string;
  ballot: string;
  votes: number | null;
  votesStatus: "observed" | "unknown" | "unavailable" | "not_applicable";
  hash: string;
};

const keys = [
  "release",
  "election",
  "source",
  "sourceId",
  "geography",
  "geographyPath",
  "level",
  "category",
  "status",
  "baselineRelease",
  "baselineElection",
  "comparisonGrain",
  "candidate",
  "ballot",
] as const;

export function readResultFilters(
  params: Record<string, string | string[] | undefined>,
): ResultFilters {
  const parsed = Object.fromEntries(
    keys.flatMap((key) => {
      const value = params[key];
      return typeof value === "string" && value.trim()
        ? [[key, value.trim()]]
        : [];
    }),
  ) as ResultFilters;
  // Public URLs use Spanish names. Keep the original compact keys so existing
  // fixture links and bookmarked development routes remain valid.
  const aliases: Array<[keyof ResultFilters, string]> = [
    ["source", "fuente"],
    ["sourceId", "source_id"],
    ["level", "nivel"],
    ["geography", "geografia"],
    ["category", "categoria"],
    ["baselineRelease", "baseline_release"],
    ["baselineElection", "baseline_eleccion"],
  ];
  for (const [key, alias] of aliases) {
    const value = params[alias];
    if (!parsed[key] && typeof value === "string" && value.trim()) {
      parsed[key] = value.trim() as never;
    }
  }
  return parsed;
}

export function serializeResultFilters(filters: ResultFilters, format?: "csv") {
  const query = new URLSearchParams();
  const publicKeys: Array<[keyof ResultFilters, string]> = [
    ["release", "release"],
    ["election", "election"],
    ["source", "source"],
    ["sourceId", "source_id"],
    ["level", "level"],
    ["geography", "geography"],
    ["geographyPath", "geography_path"],
    ["category", "category"],
    ["status", "status"],
    ["baselineRelease", "baseline_release"],
    ["baselineElection", "baseline_eleccion"],
    ["comparisonGrain", "comparison_grain"],
    ["candidate", "candidate"],
    ["ballot", "ballot"],
  ];
  for (const [key, publicKey] of publicKeys)
    if (filters[key]) query.set(publicKey, filters[key]!);
  if (format) query.set("format", format);
  return query.toString();
}

export function serializeApiResultFilters(
  filters: ResultFilters,
  ballotCandidateId?: string,
  dataVersion?: string,
) {
  const query = new URLSearchParams({ format: "csv" });
  if (filters.source) query.set("source_type", filters.source);
  if (filters.geography) query.set("geography_id", filters.geography);
  if (filters.candidate) query.set("candidate_id", filters.candidate);
  else if (ballotCandidateId) query.set("candidate_id", ballotCandidateId);
  else if (filters.ballot)
    query.set("candidate_id", "__no_candidate_for_ballot__");
  if (dataVersion) query.set("data_version", dataVersion);
  return query.toString();
}

export function resultHref(
  locale: string,
  filters: ResultFilters,
  format?: "csv",
) {
  const query = serializeResultFilters(filters, format);
  return `/${locale}/resultados${query ? `?${query}` : ""}`;
}

function csvCell(value: string | number | null): string {
  const raw = value === null ? "" : String(value);
  // Prevent downloaded official labels from becoming spreadsheet formulas.
  const safe = /^[=+\-@\t\r]/.test(raw) ? `'${raw}` : raw;
  return `"${safe.replaceAll('"', '""')}"`;
}

export function fixtureResultCsv(
  rows: readonly FixtureResultCsvRow[],
  dataVersion: string,
): string {
  const columns = [
    "mesa_id",
    "geography",
    "department",
    "source_type",
    "candidate_id",
    "candidate",
    "ballot_number",
    "votes_value",
    "votes_status",
    "data_version",
    "content_hash",
  ];
  const body = rows.map((row) =>
    [
      row.mesa,
      row.geography,
      row.department,
      row.source,
      row.candidateId,
      row.candidate,
      row.ballot,
      row.votes,
      row.votesStatus,
      dataVersion,
      row.hash,
    ]
      .map(csvCell)
      .join(","),
  );
  return [columns.join(","), ...body].join("\r\n") + "\r\n";
}

export function fixtureResultCsvUrl(
  rows: readonly FixtureResultCsvRow[],
  dataVersion: string,
): string {
  return `data:text/csv;charset=utf-8,${encodeURIComponent(
    fixtureResultCsv(rows, dataVersion),
  )}`;
}
