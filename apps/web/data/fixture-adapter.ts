import type { components } from "@elecciones/contracts";
import { readFile } from "node:fs/promises";
import path from "node:path";

import type { ResultFilters } from "@/lib/result-filters";

type S = components["schemas"];

export type EvidenceIndexDocument = {
  id: string;
  mesa_id: string;
  document_type: "e14_delegate" | "e14_transmission";
  official_url: string;
  source_index_url: string;
  source_index_hash: string;
  indexed_at: string;
  index_status: "indexed" | "unavailable";
  provenance: S["Provenance"];
};

export type DepartmentRollup = {
  id: string;
  code: string | null;
  name: string;
  valid_votes: number | null;
  candidates: Record<string, number | null>;
  mesas_reported: number | null;
};

export type SampleMesa = {
  mesa_id: string;
  department: string | null;
  valid_votes: number;
  /** valid_votes INCLUDES blanks (valid = Σcandidates + blank), so the figure
   * needs this explicitly or it draws blank ballots as candidate votes. */
  blank_votes: number;
  candidates: Record<string, number>;
};

export type ReleaseView = {
  fixture_notice: Record<"es" | "en", string>;
  department_rollup?: DepartmentRollup[];
  sample_mesa?: SampleMesa | null;
  release: {
    release_id: string;
    data_version: string;
    status: string;
    synthetic: boolean;
    created_at: string;
    methodology_version: string;
  };
  election: {
    slug: string;
    name: S["LocalizedText"];
    round: number;
    election_date: string;
    candidates: S["Candidate"][];
  };
  provenance: S["Provenance"];
  summary: S["ElectionSummary"];
  geographies: S["Geography"][];
  mesas: {
    id: string;
    display_number: string;
    polling_place_id: string;
    municipality_id: string;
    department_id: string;
  }[];
  results: S["ResultFact"][];
  result_page?: S["CursorMeta"];
  bulletins: Array<S["Bulletin"] & { candidate_votes: Record<string, number> }>;
  evidence: EvidenceIndexDocument[];
  comparisons: Record<string, S["ComparisonItem"][]>;
  review_signals: S["ReviewSignal"][];
  review_page?: S["CursorMeta"];
  datasets: S["Dataset"][];
};

export type FixtureRelease = ReleaseView;

type ReleaseOptions = {
  include?:
    "all" | "results" | "review" | "bulletins" | "datasets" | "analytics";
  filters?: ResultFilters;
  cursor?: string;
  reviewCursor?: string;
  reviewMinimumScore?: number;
  reviewTier?: string;
};

export interface DataAdapter {
  getRelease(options?: ReleaseOptions): Promise<ReleaseView>;
  getNationalSummary(): Promise<ReleaseView>;
  getMesa(mesaId: string): Promise<S["MesaDetail"] | null>;
  getEvidence(mesaId: string): Promise<EvidenceIndexDocument[]>;
  getComparisons(mesaId: string): Promise<S["ComparisonItem"][]>;
}

export type PublicExplorerFilters = {
  release?: string;
  election?: string;
  source?: string;
  geography?: string;
  geographyPath?: string;
  level?: string;
  category?: string;
  status?: "observed" | "unavailable";
  cursor?: string;
  baselineRelease?: string;
  baselineElection?: string;
  comparisonGrain?: string;
};

export type PublicReleaseRef = {
  release_id: string;
  election_slug: string;
  name_es: string;
  name_en: string;
  round: number;
  election_date: string;
  /** Was a literal "published". A preliminary pre-count is a `candidate`
   * release, and typing it as published made every consumer state something
   * untrue about it. */
  status: "published" | "candidate" | "withdrawn";
  /** Which door authorised the read. `preliminary` must never render as
   * published; a certified release has no preliminary grant and vice versa. */
  exposure_class?: "certified" | "preliminary";
  methodology_version: string | null;
  release_manifest_hash: string;
  /** Null for a preliminary grant: a candidate release has no certified
   * approval, and claiming one would be the mislabel this guards against. */
  exposure_approved_at: string | null;
  sources: Array<{
    id: string;
    source_type: S["Provenance"]["source_type"];
    legal_status: S["Provenance"]["legal_status"];
    source_url: string;
    content_hash: string;
  }>;
};

export type ScopedGeography = {
  id: string;
  level: S["Geography"]["level"];
  code: string;
  name: string;
  parent_id: string | null;
  canonical_path?: string;
  has_published_facts?: boolean;
};

export type GeographyChildPage = {
  items: ScopedGeography[];
  page: S["CursorMeta"];
  data_version: string;
};

export type ScopedMesa = {
  id: string;
  display_number: string;
  polling_place_id: string;
  municipality_id: string;
  department_id: string;
  geography_path: ScopedGeography[];
  results: S["ResultFact"][];
  data_version: string;
};

export type PublicGeographyView = {
  releases: PublicReleaseRef[];
  selected?: PublicReleaseRef;
  geographyId: string;
  path: ScopedGeography[];
  children: GeographyChildPage;
};

export type PublicMesaView = {
  releases: PublicReleaseRef[];
  selected?: PublicReleaseRef;
  mesa?: ScopedMesa;
};

export type HistoricalComparison =
  | {
      comparison_status: "not_comparable";
      reason:
        | "missing_geography_crosswalk"
        | "geography_crosswalk_unapproved"
        | "missing_semantic_crosswalk"
        | "semantic_crosswalk_unapproved"
        | "no_compatible_facts";
      data_version: string;
      baseline_data_version: string;
      geography_id: string;
      requested_grain: string;
    }
  | {
      comparison_status: "comparable" | "descriptive_context_only";
      eligible_for_integrity_analysis: boolean;
      comparison_key: string;
      geography_crosswalk_version: string;
      geography_approved_at: string;
      baseline_geography_id: string;
      items: Array<{
        category_key: string;
        semantic_crosswalk_version: string;
        current_value: number | null;
        current_status: S["MetricValue"]["status"];
        baseline_value: number | null;
        baseline_status: S["MetricValue"]["status"];
      }>;
      data_version: string;
      baseline_data_version: string;
      geography_id: string;
      requested_grain: string;
    };

export type PublicExplorer = {
  kind: "normalized" | "fixture";
  releases: PublicReleaseRef[];
  selected?: PublicReleaseRef;
  filters: PublicExplorerFilters;
  results: S["ResultPage"];
  geographyPath: ScopedGeography[];
  /** Only a comparison request explicitly present in the URL is fetched. */
  comparison?: HistoricalComparison;
  error?: { status?: number; message: string };
};

/**
 * Sensitivity is intentionally scoped to the public release/election pair. A
 * missing endpoint or unpublished pair is represented as unavailable, never as
 * a zero-valued calculation.
 */
export async function getPublicOutcomeSensitivity(
  filters: PublicExplorerFilters = {},
): Promise<S["OutcomeSensitivity"] | null> {
  if (!apiBase()) return null;
  try {
    const { selected } = await publicSelection(filters);
    if (!selected) return null;
    return await apiJson<S["OutcomeSensitivity"]>(
      `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}/outcome-sensitivity`,
    );
  } catch (error) {
    if (error instanceof PublicApiError && error.status === 404) return null;
    return null;
  }
}

type FixtureWireRelease = Omit<ReleaseView, "evidence" | "comparisons"> & {
  evidence?: unknown[];
  comparisons?: unknown;
};

/**
 * A fixture can retain older, richer evidence bytes for reproducibility, but
 * the web layer only projects immutable index metadata. This boundary is also
 * applied to API responses so an unexpected extra field can never reach a
 * reader-facing view.
 */
function projectEvidenceIndex(value: unknown): EvidenceIndexDocument {
  const record = value as Record<string, unknown>;
  const provenance = record.provenance as S["Provenance"];
  const sourceIndexUrl =
    (record.source_index_url as string | undefined) ?? provenance.source_url;
  const sourceIndexHash =
    (record.source_index_hash as string | undefined) ?? provenance.content_hash;
  const indexedAt =
    (record.indexed_at as string | undefined) ?? provenance.retrieved_at;

  if (
    typeof record.id !== "string" ||
    typeof record.mesa_id !== "string" ||
    (record.document_type !== "e14_delegate" &&
      record.document_type !== "e14_transmission") ||
    typeof record.official_url !== "string"
  ) {
    throw new Error("Fixture evidence is missing required index metadata.");
  }

  return {
    id: record.id,
    mesa_id: record.mesa_id,
    document_type: record.document_type,
    official_url: record.official_url,
    source_index_url: sourceIndexUrl,
    source_index_hash: sourceIndexHash,
    indexed_at: indexedAt,
    index_status:
      record.index_status === "unavailable" ? "unavailable" : "indexed",
    provenance: {
      ...provenance,
      source_url: sourceIndexUrl,
      content_hash: sourceIndexHash,
    },
  };
}

async function readFixture(): Promise<ReleaseView> {
  // The preliminary preconteo is served through the same file channel as the
  // synthetic fixture, but it is real data — the file and the release_framing
  // disclosure carry that distinction, never a mislabel.
  const fixtureFile =
    process.env.NEXT_PUBLIC_PRELIMINARY_RELEASE === "true"
      ? "preliminary-release.json"
      : "fixture-release.json";
  const fixturePath = path.resolve(
    process.cwd(),
    `../../data/fixtures/${fixtureFile}`,
  );
  const wire = JSON.parse(
    await readFile(fixturePath, "utf8"),
  ) as FixtureWireRelease & {
    department_rollup?: ReleaseView["department_rollup"];
    sample_mesa?: ReleaseView["sample_mesa"];
  };

  return {
    fixture_notice: wire.fixture_notice,
    department_rollup: wire.department_rollup,
    sample_mesa: wire.sample_mesa,
    release: wire.release,
    election: wire.election,
    provenance: wire.provenance,
    summary: wire.summary,
    geographies: wire.geographies,
    mesas: wire.mesas,
    results: wire.results,
    result_page: wire.result_page,
    bulletins: wire.bulletins,
    evidence: (wire.evidence ?? []).map(projectEvidenceIndex),
    // Document comparisons can include transcribed or extracted vote fields.
    // The public evidence surface is deliberately index-only.
    comparisons: {},
    review_signals: wire.review_signals,
    review_page: wire.review_page,
    datasets: wire.datasets,
  };
}

async function fixtureMesa(mesaId: string): Promise<S["MesaDetail"] | null> {
  const release = await readFixture();
  const mesa = release.mesas.find((item) => item.id === mesaId);
  const result = release.results.find((item) => item.mesa_id === mesaId);
  const geography = release.geographies.find(
    (item) => item.id === mesa?.municipality_id,
  );
  const pollingPlace = release.geographies.find(
    (item) => item.id === mesa?.polling_place_id,
  );
  if (!mesa || !result || !geography || !pollingPlace) return null;
  return {
    id: mesa.id,
    display_number: mesa.display_number,
    geography,
    polling_place: pollingPlace,
    available_source_types: [
      ...new Set(
        release.results
          .filter((item) => item.mesa_id === mesaId)
          .map((item) => item.provenance.source_type),
      ),
    ],
    result,
    data_version: release.release.data_version,
  };
}

/** Explicit development adapter. It is never consulted after a live API is selected. */
export const fixtureAdapter: DataAdapter = {
  getRelease: readFixture,
  getNationalSummary: readFixture,
  getMesa: fixtureMesa,
  async getEvidence(mesaId) {
    return (await readFixture()).evidence.filter(
      (document) => document.mesa_id === mesaId,
    );
  },
  async getComparisons(mesaId) {
    void mesaId;
    return [];
  },
};

const fixtureAllowed =
  process.env.NODE_ENV !== "production" ||
  process.env.NEXT_PUBLIC_SYNTHETIC_FIXTURE === "true";
const electionSlug =
  process.env.NEXT_PUBLIC_ELECTION_SLUG ?? "presidencia-2026-segunda-vuelta";

function apiBase(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (!configured) return null;
  const url = new URL(configured);
  const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
  if (url.protocol !== "https:" && !(local && url.protocol === "http:")) {
    throw new Error(
      "The public API URL must use HTTPS outside local development.",
    );
  }
  return url.toString().replace(/\/$/, "");
}

export function publicNormalizedApiConfigured() {
  return Boolean(apiBase());
}

export class PublicApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PublicApiError";
  }
}

export async function publicApiJson<T>(pathname: string): Promise<T> {
  const base = apiBase();
  if (!base) throw new Error("A public API URL is required.");
  const response = await fetch(`${base}${pathname}`, {
    next: { revalidate: 3600 },
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new PublicApiError(
      response.status,
      problem?.detail ??
        `Public API request failed (${response.status}) for ${pathname}.`,
    );
  }
  return (await response.json()) as T;
}

// Keep the historical local name so the existing adapter surface remains
// unchanged while frozen, release-scoped readers can share the same transport.
const apiJson = publicApiJson;

function queryPath(pathname: string, query: URLSearchParams) {
  const suffix = query.toString();
  return `${pathname}${suffix ? `?${suffix}` : ""}`;
}

function pickPublicRelease(
  releases: PublicReleaseRef[],
  filters: PublicExplorerFilters,
) {
  if (filters.release && filters.election) {
    return releases.find(
      (item) =>
        item.release_id === filters.release &&
        item.election_slug === filters.election,
    );
  }
  if (filters.release) {
    return releases.find((item) => item.release_id === filters.release);
  }
  if (filters.election) {
    return releases.find((item) => item.election_slug === filters.election);
  }
  const activeRelease = process.env.NEXT_PUBLIC_ACTIVE_RELEASE;
  if (activeRelease) {
    const selected = releases.find(
      (item) => item.release_id === activeRelease,
    );
    if (selected) return selected;
  }
  return releases[0];
}

/**
 * The normalized explorer deliberately starts with references plus one keyset
 * page. Candidate/internal releases are absent because the API endpoint only
 * exposes approved published pairs.
 */
export async function getPublicExplorer(
  filters: PublicExplorerFilters = {},
): Promise<PublicExplorer> {
  if (!apiBase()) {
    const legacy = await fixtureAdapter.getRelease({
      include: "results",
      filters: {
        source: filters.source,
        geography: filters.geography,
      },
      cursor: filters.cursor,
    });
    return {
      kind: "fixture",
      releases: [],
      filters,
      results: {
        items: legacy.results,
        page: legacy.result_page ?? {
          next_cursor: null,
          has_more: false,
          limit: 50,
        },
        data_version: legacy.release.data_version,
      },
      geographyPath: [],
    };
  }
  try {
    const releases = await apiJson<PublicReleaseRef[]>(
      "/api/v1/release-elections",
    );
    const selected = pickPublicRelease(releases, filters);
    if (!selected) {
      return {
        kind: "normalized",
        releases,
        filters,
        results: {
          items: [],
          page: { next_cursor: null, has_more: false, limit: 50 },
          data_version: "",
        },
        geographyPath: [],
      };
    }
    const query = new URLSearchParams({ limit: "50" });
    if (filters.cursor) query.set("cursor", filters.cursor);
    if (filters.source) query.set("source_type", filters.source);
    if (filters.geography) query.set("geography_id", filters.geography);
    if (filters.geographyPath)
      query.set("geography_path", filters.geographyPath);
    if (filters.level) query.set("geography_level", filters.level);
    if (filters.category) query.set("category_key", filters.category);
    if (filters.status) query.set("status", filters.status);
    const prefix = `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
    const results = await apiJson<S["ResultPage"]>(
      queryPath(`${prefix}/results`, query),
    );
    const pathId = filters.geography ?? results.items[0]?.geography_id;
    const geographyPath = pathId
      ? await apiJson<{ items: ScopedGeography[]; data_version: string }>(
          `${prefix}/geographies/${encodeURIComponent(pathId)}/path`,
        ).then((value) => value.items)
      : [];
    let comparison: HistoricalComparison | undefined;
    if (
      filters.baselineRelease &&
      filters.baselineElection &&
      filters.geography &&
      filters.comparisonGrain
    ) {
      const comparisonQuery = new URLSearchParams({
        baseline_release_id: filters.baselineRelease,
        baseline_election_slug: filters.baselineElection,
        geography_id: filters.geography,
        grain: filters.comparisonGrain,
      });
      if (filters.category)
        comparisonQuery.set("category_key", filters.category);
      comparison = await apiJson<HistoricalComparison>(
        queryPath(`${prefix}/historical-comparison`, comparisonQuery),
      );
    }
    return {
      kind: "normalized",
      releases,
      selected,
      filters,
      results,
      geographyPath,
      comparison,
    };
  } catch (error) {
    return {
      kind: "normalized",
      releases: [],
      filters,
      results: {
        items: [],
        page: { next_cursor: null, has_more: false, limit: 50 },
        data_version: "",
      },
      geographyPath: [],
      error: {
        status: error instanceof PublicApiError ? error.status : undefined,
        message:
          error instanceof Error
            ? error.message
            : "The public release service is unavailable.",
      },
    };
  }
}

export async function getPublicReleaseSelection(
  filters: PublicExplorerFilters,
) {
  const releases = await apiJson<PublicReleaseRef[]>(
    "/api/v1/release-elections",
  );
  return { releases, selected: pickPublicRelease(releases, filters) };
}

const publicSelection = getPublicReleaseSelection;

export async function getPublicGeography(
  geographyId: string,
  filters: PublicExplorerFilters,
): Promise<PublicGeographyView> {
  const { releases, selected } = await publicSelection(filters);
  if (!selected) {
    return {
      releases,
      selected,
      geographyId,
      path: [],
      children: {
        items: [],
        page: { next_cursor: null, has_more: false, limit: 50 },
        data_version: "",
      },
    };
  }
  const prefix = `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
  const query = new URLSearchParams({ limit: "50" });
  if (filters.cursor) query.set("cursor", filters.cursor);
  if (filters.level) query.set("level", filters.level);
  const [pathResponse, children] = await Promise.all([
    apiJson<{ items: ScopedGeography[]; data_version: string }>(
      `${prefix}/geographies/${encodeURIComponent(geographyId)}/path`,
    ),
    apiJson<GeographyChildPage>(
      queryPath(
        `${prefix}/geographies/${encodeURIComponent(geographyId)}/children`,
        query,
      ),
    ),
  ]);
  return {
    releases,
    selected,
    geographyId,
    path: pathResponse.items,
    children,
  };
}

/** One child geography with its vote totals. Field names are deliberately
 * short: this shape is fetched a page at a time while drilling through 122,020
 * mesas, and the long form costs ~15x more bytes for the same information. */
export type LeanChildResult = {
  /** geography id */ i: string;
  /** level */ l: string;
  /** code */ c: string;
  /** name */ n: string;
  /** voters */ t: number | null;
  /** valid votes (INCLUDES blanks) */ v: number | null;
  /** blank */ b: number | null;
  /** null */ x: number | null;
  /** unmarked */ u: number | null;
  /** candidate votes, positional against `candidates` */ k: (number | null)[];
};

export type ChildrenResultsPage = {
  items: LeanChildResult[];
  /** Candidate ids, in the order `k` is indexed by. */
  candidates: string[];
  page: S["CursorMeta"];
  data_version: string;
  exposure_class?: "certified" | "preliminary";
  preliminary?: boolean;
  preliminary_caveat?: Record<"es" | "en", string> | null;
};

/**
 * Children plus their totals in one request. The alternative -- `/results`
 * followed by a per-fact categories call -- costs up to 228 round trips for a
 * single polling place, which is why drill-down needs its own read.
 */
export async function getPublicChildrenResults(
  geographyId: string,
  filters: PublicExplorerFilters & { level?: string } = {},
): Promise<ChildrenResultsPage | null> {
  if (!apiBase()) return null;
  const { selected } = await publicSelection(filters);
  if (!selected) return null;
  const query = new URLSearchParams({ limit: "50" });
  if (filters.cursor) query.set("cursor", filters.cursor);
  if (filters.level) query.set("level", filters.level);
  const prefix = `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
  return await apiJson<ChildrenResultsPage>(
    queryPath(
      `${prefix}/geographies/${encodeURIComponent(geographyId)}/children-results`,
      query,
    ),
  );
}

export async function getPublicMesa(
  mesaId: string,
  filters: PublicExplorerFilters & { sourceId?: string },
): Promise<PublicMesaView> {
  const { releases, selected } = await publicSelection(filters);
  if (!selected) return { releases, selected };
  const query = new URLSearchParams();
  if (filters.source) query.set("source_type", filters.source);
  if (filters.sourceId) query.set("source_id", filters.sourceId);
  const prefix = `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
  return {
    releases,
    selected,
    mesa: await apiJson<ScopedMesa>(
      queryPath(`${prefix}/mesas/${encodeURIComponent(mesaId)}`, query),
    ),
  };
}

function releaseQuery(): string | undefined {
  return process.env.NEXT_PUBLIC_ACTIVE_RELEASE || undefined;
}

function withVersion(query: URLSearchParams): URLSearchParams {
  const version = releaseQuery();
  if (version) query.set("data_version", version);
  return query;
}

async function apiRelease(options: ReleaseOptions = {}): Promise<ReleaseView> {
  const summaryQuery = withVersion(new URLSearchParams());
  const summary = await apiJson<S["ElectionSummary"]>(
    `/api/v1/elections/${electionSlug}/summary?${summaryQuery}`,
  );
  const include = options.include ?? "all";
  const wantsResults = include === "all" || include === "results";
  const wantsReview =
    include === "all" ||
    include === "review" ||
    include === "datasets" ||
    include === "analytics";
  const wantsBulletins =
    include === "all" || include === "bulletins" || include === "analytics";
  const wantsDatasets = include === "all" || include === "datasets";
  const resultQuery = withVersion(new URLSearchParams({ limit: "50" }));
  const filters = options.filters;
  if (options.cursor) resultQuery.set("cursor", options.cursor);
  if (filters?.source) resultQuery.set("source_type", filters.source);
  if (filters?.geography) resultQuery.set("geography_id", filters.geography);
  if (filters?.candidate) resultQuery.set("candidate_id", filters.candidate);
  if (filters?.ballot && !filters.candidate) {
    const candidate = summary.candidates.find(
      (item) => String(item.candidate.ballot_number) === filters.ballot,
    );
    if (candidate) resultQuery.set("candidate_id", candidate.candidate.id);
  }
  const commonQuery = withVersion(
    new URLSearchParams({ election_slug: electionSlug }),
  );
  const reviewQuery = withVersion(
    new URLSearchParams({
      election_slug: electionSlug,
      limit: include === "datasets" ? "1" : "50",
    }),
  );
  // The summary selects the immutable version for every dependent read. This
  // remains required when no active release was configured before the request.
  reviewQuery.set("data_version", summary.data_version);
  if (options.reviewCursor) reviewQuery.set("cursor", options.reviewCursor);
  if (options.reviewMinimumScore !== undefined) {
    reviewQuery.set("minimum_score", String(options.reviewMinimumScore));
  }
  if (options.reviewTier) reviewQuery.set("tier", options.reviewTier);
  const [resultPage, bulletins, reviewPage, datasets] = await Promise.all([
    wantsResults
      ? apiJson<S["ResultPage"]>(
          `/api/v1/elections/${electionSlug}/results?${resultQuery}`,
        )
      : Promise.resolve({
          items: [],
          page: { next_cursor: null, has_more: false, limit: 50 },
          data_version: summary.data_version,
        } satisfies S["ResultPage"]),
    wantsBulletins
      ? apiJson<S["Bulletin"][]>(`/api/v1/bulletins?${commonQuery}`)
      : Promise.resolve([]),
    wantsReview
      ? apiJson<S["ReviewSignalPage"]>(`/api/v1/review-signals?${reviewQuery}`)
      : Promise.resolve({
          items: [],
          page: { next_cursor: null, has_more: false, limit: 50 },
          data_version: summary.data_version,
          methodology_version:
            summary.provenance.methodology_version ?? "unavailable",
          disclosure: { es: "No disponible", en: "Unavailable" },
        } satisfies S["ReviewSignalPage"]),
    wantsDatasets
      ? apiJson<S["Dataset"][]>(`/api/v1/datasets?${commonQuery}`)
      : Promise.resolve([]),
  ]);

  if (wantsReview && reviewPage.data_version !== summary.data_version) {
    throw new Error(
      `Review response version ${reviewPage.data_version} does not match summary version ${summary.data_version}.`,
    );
  }

  const bulletinResults = wantsBulletins
    ? await Promise.all(
        bulletins.map((bulletin) =>
          apiJson<S["BulletinResult"]>(
            `/api/v1/bulletins/${encodeURIComponent(bulletin.id)}/results?${withVersion(new URLSearchParams())}`,
          ),
        ),
      )
    : [];

  const geographyById = new Map<string, S["Geography"]>();
  const pending = new Set(resultPage.items.map((item) => item.geography_id));
  while (pending.size > 0) {
    const identifiers = [...pending];
    pending.clear();
    const geographies = await Promise.all(
      identifiers.map((identifier) =>
        apiJson<S["Geography"]>(
          `/api/v1/geographies/${encodeURIComponent(identifier)}?${summaryQuery}`,
        ),
      ),
    );
    for (const geography of geographies) {
      geographyById.set(geography.id, geography);
      if (geography.parent_id && !geographyById.has(geography.parent_id)) {
        pending.add(geography.parent_id);
      }
    }
  }

  const mesas = resultPage.items.flatMap((result) => {
    if (!result.mesa_id) return [];
    const place = geographyById.get(result.geography_id);
    const municipality = place?.parent_id
      ? geographyById.get(place.parent_id)
      : undefined;
    const department = municipality?.parent_id
      ? geographyById.get(municipality.parent_id)
      : undefined;
    return [
      {
        id: result.mesa_id,
        display_number: result.mesa_id,
        polling_place_id: place?.id ?? result.geography_id,
        municipality_id: municipality?.id ?? "",
        department_id: department?.id ?? "",
      },
    ];
  });
  const candidates = summary.candidates.map((item) => item.candidate);
  const fixtureNotice = summary.synthetic
    ? {
        es: "Datos sintéticos de desarrollo; no representan resultados electorales reales.",
        en: "Synthetic development data; these are not real election results.",
      }
    : {
        es: "Datos del release inmutable indicado en la página.",
        en: "Data from the immutable release shown on this page.",
      };
  return {
    fixture_notice: fixtureNotice,
    release: {
      release_id: summary.data_version,
      data_version: summary.data_version,
      status: summary.release_status,
      synthetic: summary.synthetic,
      created_at: summary.provenance.retrieved_at,
      methodology_version: reviewPage.methodology_version,
    },
    election: {
      slug: summary.election_slug,
      name: summary.election_name,
      round: summary.round,
      election_date: summary.election_date,
      candidates,
    },
    provenance: summary.provenance,
    summary,
    geographies: [...geographyById.values()],
    mesas,
    results: resultPage.items,
    result_page: resultPage.page,
    bulletins: bulletins.map((item, index) => ({
      ...item,
      candidate_votes: Object.fromEntries(
        (bulletinResults[index]?.result.candidates ?? []).flatMap(
          (candidate) =>
            candidate.votes.status === "observed" &&
            candidate.votes.value !== null
              ? [[candidate.candidate_id, candidate.votes.value]]
              : [],
        ),
      ),
    })),
    evidence: [],
    comparisons: {},
    review_signals: reviewPage.items,
    review_page: reviewPage.page,
    datasets,
  };
}

/**
 * Read the national summary through the release-scoped route.
 *
 * The legacy `/elections/{slug}/summary` route is certified-only by design, so
 * it refuses a preliminary release — correctly, but that would leave the home
 * page with no figures at all while the same numbers are being served one route
 * over. This resolves the release from the catalogue and reads the normalized
 * summary, which carries the preliminary label with it.
 */
async function normalizedSummaryRelease(): Promise<ReleaseView | null> {
  const releases = await apiJson<PublicReleaseRef[]>(
    "/api/v1/release-elections",
  );
  const selected =
    releases.find((item) => item.election_slug === electionSlug) ?? releases[0];
  if (!selected) return null;
  const summary = await apiJson<
    S["ElectionSummary"] & {
      preliminary?: boolean;
      preliminary_caveat?: Record<"es" | "en", string>;
    }
  >(
    `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}/summary`,
  );
  const prefix = `/api/v1/releases/${encodeURIComponent(selected.release_id)}/elections/${encodeURIComponent(selected.election_slug)}`;
  const departmentResults = await apiJson<ChildrenResultsPage>(
    `${prefix}/geographies/CO/children-results?level=department&limit=50`,
  );
  if (departmentResults.data_version !== summary.data_version) {
    throw new Error(
      `Department response version ${departmentResults.data_version} does not match summary version ${summary.data_version}.`,
    );
  }
  const candidateIds = departmentResults.candidates.map((candidate) =>
    candidate.replace(/^candidate:/, ""),
  );
  const departmentRollup = departmentResults.items.map((department) => ({
    id: department.i,
    code: department.c || null,
    name: department.n,
    valid_votes: department.v,
    candidates: Object.fromEntries(
      candidateIds.map((candidate, index) => [
        candidate,
        department.k[index] ?? null,
      ]),
    ),
    mesas_reported: null,
  }));
  const notice = summary.preliminary_caveat ?? {
    es: "Datos del release inmutable indicado en la página.",
    en: "Data from the immutable release shown on this page.",
  };
  return {
    fixture_notice: notice,
    department_rollup: departmentRollup,
    release: {
      release_id: selected.release_id,
      data_version: summary.data_version,
      status: selected.status,
      synthetic: summary.synthetic,
      created_at: summary.provenance.retrieved_at,
      methodology_version:
        summary.provenance.methodology_version ?? "unavailable",
    },
    election: {
      slug: summary.election_slug,
      name: summary.election_name,
      round: summary.round,
      election_date: summary.election_date,
      candidates: summary.candidates.map((item) => item.candidate),
    },
    provenance: summary.provenance,
    summary,
    geographies: [],
    mesas: [],
    results: [],
    bulletins: [],
    evidence: [],
    comparisons: {},
    review_signals: [],
    datasets: [],
  };
}

async function apiSummaryRelease(): Promise<ReleaseView> {
  const query = withVersion(new URLSearchParams());
  const summary = await apiJson<S["ElectionSummary"]>(
    `/api/v1/elections/${electionSlug}/summary?${query}`,
  );
  return {
    fixture_notice: summary.synthetic
      ? {
          es: "Datos sintéticos de desarrollo; no representan resultados electorales reales.",
          en: "Synthetic development data; these are not real election results.",
        }
      : {
          es: "Datos del release inmutable indicado en la página.",
          en: "Data from the immutable release shown on this page.",
        },
    release: {
      release_id: summary.data_version,
      data_version: summary.data_version,
      status: summary.release_status,
      synthetic: summary.synthetic,
      created_at: summary.provenance.retrieved_at,
      methodology_version:
        summary.provenance.methodology_version ?? "unavailable",
    },
    election: {
      slug: summary.election_slug,
      name: summary.election_name,
      round: summary.round,
      election_date: summary.election_date,
      candidates: summary.candidates.map((item) => item.candidate),
    },
    provenance: summary.provenance,
    summary,
    geographies: [],
    mesas: [],
    results: [],
    bulletins: [],
    evidence: [],
    comparisons: {},
    review_signals: [],
    datasets: [],
  };
}

/**
 * Prefer the legacy contract, fall back to the release-scoped read.
 *
 * A certified release answers on both. A preliminary one is refused by the
 * legacy route by design, and falling back keeps the reader seeing real figures
 * — labelled preliminary — instead of an unavailable state that would be
 * indistinguishable from the API being down.
 */
async function releaseWithNormalizedFallback(
  legacy: () => Promise<ReleaseView>,
): Promise<ReleaseView> {
  try {
    return await legacy();
  } catch (error) {
    if (!(error instanceof PublicApiError) || error.status !== 404) throw error;
    const normalized = await normalizedSummaryRelease();
    if (!normalized) throw error;
    return normalized;
  }
}

const liveAdapter: DataAdapter = {
  getRelease: (options) =>
    releaseWithNormalizedFallback(() => apiRelease(options)),
  getNationalSummary: () => releaseWithNormalizedFallback(apiSummaryRelease),
  async getMesa(mesaId) {
    try {
      return await apiJson<S["MesaDetail"]>(
        `/api/v1/mesas/${encodeURIComponent(mesaId)}?${withVersion(new URLSearchParams())}`,
      );
    } catch (error) {
      if (error instanceof Error && error.message.includes("(404)"))
        return null;
      throw error;
    }
  },
  async getEvidence(mesaId) {
    const response = await apiJson<S["EvidenceResponse"]>(
      `/api/v1/mesas/${encodeURIComponent(mesaId)}/evidence?${withVersion(new URLSearchParams())}`,
    );
    return response.documents.map(projectEvidenceIndex);
  },
  async getComparisons(mesaId) {
    void mesaId;
    return [];
  },
};

/** Select exactly one layer. A configured live API never falls back to fixture rows. */
export const dataAdapter: DataAdapter = apiBase()
  ? liveAdapter
  : fixtureAllowed
    ? fixtureAdapter
    : {
        async getRelease() {
          throw new Error(
            "A public API URL or explicit synthetic fixture mode is required.",
          );
        },
        async getNationalSummary() {
          throw new Error(
            "A public API URL or explicit synthetic fixture mode is required.",
          );
        },
        async getMesa() {
          throw new Error("A public API URL is required.");
        },
        async getEvidence() {
          throw new Error("A public API URL is required.");
        },
        async getComparisons() {
          throw new Error("A public API URL is required.");
        },
      };
