import { createServer } from "node:http";
import process from "node:process";
import { URL } from "node:url";

const port = Number(process.env.NORMALIZED_MOCK_PORT ?? 3210);
const releaseId = "release-2026-r2-public";
const election = "presidencia-2026-segunda-vuelta";
const hash = "a".repeat(64);
// This real historical candidate is intentionally not returned by
// /release-elections: it is context_only and has not been published. It is
// retained here only to prove that a URL cannot turn it into a public baseline
// or a comparable pair.
const unpublished2018Contexts = [
  {
    release_id: "historical-2018-r1-candidate",
    election_slug: "presidencia-2018-primera-vuelta",
  },
  {
    release_id: "historical-2018-r2-candidate",
    election_slug: "presidencia-2018-segunda-vuelta",
  },
].map((context) => ({
  ...context,
  status: "candidate",
  source_type: "contextual_baseline",
  legal_status: "context_only",
  eligible_for_integrity_analysis: false,
}));

const releases = [
  [
    releaseId,
    election,
    "Presidencia 2026 · segunda vuelta",
    "2026 presidency · second round",
    2,
    "2026-06-21",
  ],
  [
    "release-2026-r1-public",
    "presidencia-2026-primera-vuelta",
    "Presidencia 2026 · primera vuelta",
    "2026 presidency · first round",
    1,
    "2026-05-31",
  ],
  [
    "historical-2022-r2-public",
    "presidencia-2022-segunda-vuelta",
    "Presidencia 2022 · segunda vuelta",
    "2022 presidency · second round",
    2,
    "2022-06-19",
  ],
  [
    "historical-2022-r1-public",
    "presidencia-2022-primera-vuelta",
    "Presidencia 2022 · primera vuelta",
    "2022 presidency · first round",
    1,
    "2022-05-29",
  ],
].map(
  ([release_id, election_slug, name_es, name_en, round, election_date]) => ({
    release_id,
    election_slug,
    name_es,
    name_en,
    round,
    election_date,
    status: "published",
    methodology_version: "method-v1",
    release_manifest_hash: hash,
    exposure_approved_at: "2026-08-03T12:00:00Z",
    sources: [
      {
        id: "source-scrutiny",
        source_type: "scrutiny",
        legal_status: "official_scrutiny",
        source_url: "https://example.test/e24",
        content_hash: hash,
      },
      {
        id: "source-context",
        source_type: "contextual_baseline",
        legal_status: "context_only",
        source_url: "https://example.test/context",
        content_hash: hash,
      },
    ],
  }),
);

const geography = {
  CO: {
    id: "CO",
    level: "national",
    code: "CO",
    name: "Colombia",
    parent_id: null,
    canonical_path: "CO",
    has_published_facts: true,
  },
  "DEP-11": {
    id: "DEP-11",
    level: "department",
    code: "11",
    name: "Bogotá D.C.",
    parent_id: "CO",
    canonical_path: "CO/DEP-11",
    has_published_facts: true,
  },
  "MUN-001": {
    id: "MUN-001",
    level: "municipality",
    code: "001",
    name: "Bogotá",
    parent_id: "DEP-11",
    canonical_path: "CO/DEP-11/MUN-001",
    has_published_facts: true,
  },
  "PLACE-01": {
    id: "PLACE-01",
    level: "polling_place",
    code: "01",
    name: "Colegio Central",
    parent_id: "MUN-001",
    canonical_path: "CO/DEP-11/MUN-001/PLACE-01",
    has_published_facts: false,
  },
  "MESA-001": {
    id: "MESA-001",
    level: "mesa",
    code: "001",
    name: "Mesa 001",
    parent_id: "PLACE-01",
    canonical_path: "CO/DEP-11/MUN-001/PLACE-01/MESA-001",
    has_published_facts: true,
  },
};
const chain = [
  geography.CO,
  geography["DEP-11"],
  geography["MUN-001"],
  geography["PLACE-01"],
  geography["MESA-001"],
];
const children = {
  CO: [geography["DEP-11"]],
  "DEP-11": [geography["MUN-001"]],
  "MUN-001": [geography["PLACE-01"]],
  "PLACE-01": [geography["MESA-001"]],
  "MESA-001": [],
};
const metric = (
  value,
  status = value === null ? "unavailable" : "observed",
) => ({ value, status });
const provenance = (sourceType = "scrutiny") => ({
  data_version: releaseId,
  source_type: sourceType,
  legal_status:
    sourceType === "contextual_baseline" ? "context_only" : "official_scrutiny",
  source_url:
    sourceType === "contextual_baseline"
      ? "https://example.test/context"
      : "https://example.test/e24",
  retrieved_at: "2026-08-03T12:00:00Z",
  content_hash: hash,
  parser_version: "parser-v1",
  transform_version: "transform-v1",
  methodology_version: "method-v1",
});
const fact = (
  id,
  geographyId,
  level,
  mesaId = null,
  sourceType = "scrutiny",
) => ({
  id,
  election_slug: election,
  geography_id: geographyId,
  geography_level: level,
  mesa_id: mesaId,
  registered_electors: metric(300),
  voters: metric(240),
  valid_votes: metric(232),
  blank_votes: metric(null),
  null_votes: metric(null),
  unmarked_votes: metric(null),
  candidates: [],
  provenance: provenance(sourceType),
});

const analysisDisclosure = {
  es: "Una anomalía prioriza revisión y no es una probabilidad ni un hallazgo de fraude. Una explicación posterior no elimina la anomalía detectada; la ausencia de explicación en los datos disponibles tampoco prueba fraude ni error.",
  en: "An anomaly prioritizes review and is not a probability or finding of fraud. A later explanation does not erase the detected anomaly; absence of an explanation in available data does not prove fraud or error.",
};
const coverage = {
  expected: 2,
  retrieved: 2,
  parsed: 2,
  missing: 0,
  ambiguous: 0,
  excluded: 0,
};
const documentaryComponent = {
  component_type: "documentary_difference_major",
  points: 70,
  observed_value: 6,
  comparator: "Official compatible source: 120 votes",
  calculation: "126 − 120 = 6 votes",
  peer_definition: null,
  limitations: {
    es: "La diferencia documental requiere verificación humana de doble entrada.",
    en: "The documentary difference requires human double-entry verification.",
  },
  source_links: ["https://example.test/e24"],
  evidence_artifact_hash: hash,
  evidence_artifact_kind: "reconciliation_result",
  analyzer_output_hash: null,
  family_id: null,
  expected_family_count: null,
  expected_family_digest: null,
  cohort_hash: null,
  input_artifact_hash: hash,
  code_hash: hash,
  method_hash: hash,
  p_value: null,
  q_value: null,
  family_rank: null,
  family_size: null,
  adjustment_method: null,
  analysis: {
    kind: "documentary",
    eligibility: "eligible",
    reason: null,
    evidence_artifact_hash: hash,
    evidence_artifact_kind: "reconciliation_result",
  },
};
const peerComponent = {
  ...documentaryComponent,
  component_type: "peer_distribution",
  points: 10,
  observed_value: 0.62,
  comparator: "Leave-one-out municipality peers: 0.48",
  calculation: "Posterior-predictive peer comparison",
  peer_definition: "Eligible mesas in the same municipality",
  evidence_artifact_hash: null,
  evidence_artifact_kind: null,
  analyzer_output_hash: hash,
  family_id: "turnout:municipality",
  expected_family_count: 30,
  expected_family_digest: hash,
  cohort_hash: hash,
  p_value: 0.0008,
  q_value: 0.04,
  family_rank: 1,
  family_size: 30,
  adjustment_method: "benjamini-yekutieli",
  analysis: {
    kind: "peer_distribution",
    eligibility: "ineligible",
    reason: "independent_simulation_validation_artifact_not_published",
  },
};
const anomalyBase = {
  is_anomaly: true,
  explanation: {
    status: "non_evaluable",
    preregistration_hash: null,
    available_data_hash: null,
    reviewed_at: null,
    quantitative_effect: metric(null, "unknown"),
    quantitative_p_value: metric(null, "unknown"),
    notes: null,
  },
  minimum_ballot_edits: metric(null, "unknown"),
  minimum_ballot_edits_status: "not_evaluable",
  minimum_ballot_edits_reason:
    "complete_mutually_exclusive_ballot_categories_not_published",
  research_preview: true,
  methodology_version: "method-v1",
  disclosure: analysisDisclosure,
  provenance: provenance(),
};
const analysisAnomalies = [
  {
    ...anomalyBase,
    id: "analysis-anomaly-001",
    mesa_id: "MESA-001",
    anomaly_types: ["cross_source_documentary"],
    audit_priority_score: 70,
    components: [documentaryComponent],
    ineligible_reasons: [
      "legacy_release_has_no_preregistered_explanation_artifact",
      "complete_ballot_vector_not_published",
    ],
  },
  {
    ...anomalyBase,
    id: "analysis-anomaly-002",
    mesa_id: "MESA-002",
    anomaly_types: ["peer_distribution"],
    audit_priority_score: 10,
    components: [peerComponent],
    ineligible_reasons: [
      "independent_simulation_validation_artifact_not_published",
    ],
  },
];
const analysisSummary = {
  election_slug: election,
  data_version: releaseId,
  methodology_version: "method-v1",
  total_records_evaluated: metric(2),
  anomaly_count: metric(2),
  anomaly_counts: {
    structural_arithmetic: metric(0),
    identity_coverage: metric(0),
    cross_source_documentary: metric(1),
    peer_distribution: metric(1),
    spatial: metric(0),
  },
  missingness: coverage,
  research_preview: true,
  ineligible_reasons: [
    "independent_simulation_validation_artifacts_not_published",
    "hierarchical_and_psis_validation_not_implemented",
  ],
  disclosure: analysisDisclosure,
  provenance: provenance(),
};
const report = (report_kind) => ({
  report_kind,
  status: "research_preview",
  research_preview: true,
  ineligible_reasons:
    report_kind === "validation"
      ? ["independent_simulation_artifacts_not_published"]
      : report_kind === "local_sensitivity"
        ? ["complete_ballot_vector_not_published"]
        : [
            "hierarchical_model_not_implemented",
            "psis_diagnostics_not_implemented",
          ],
  methodology_version: "method-v1",
  artifact_hash: null,
  missingness: coverage,
  provenance: provenance(),
  disclosure: analysisDisclosure,
  metrics:
    report_kind === "validation" ? { false_discovery_rate: metric(0) } : {},
});
const outcomeSensitivity = {
  release_id: releaseId,
  election_slug: election,
  data_version: releaseId,
  margin_shift_factor: 2,
  status: "not_evaluable",
  evaluable: false,
  issues: [
    {
      code: "missing_compatible_outcome_source",
      record_ids: ["fact-municipality"],
    },
  ],
  scope: null,
  outcome_source: null,
  leader_id: null,
  runner_up_id: null,
  leader_votes: null,
  runner_up_votes: null,
  observed_margin_votes: null,
  verified_record_ids: null,
  unresolved_record_ids: null,
  verified_affected_votes: null,
  verified_margin_shift_bound: null,
  unresolved_affected_vote_upper_bound: null,
  unresolved_margin_shift_upper_bound: null,
  combined_affected_vote_upper_bound: null,
  combined_margin_shift_upper_bound: null,
  verified_margin_headroom: null,
  combined_margin_headroom: null,
  tie_possible_from_verified: null,
  lead_change_possible_from_verified: null,
  tie_possible_including_unresolved: null,
  lead_change_possible_including_unresolved: null,
  source_links: [],
  evidence_hash: null,
  output_hash: hash,
  methodology_version: "outcome-sensitivity-v3.0.0",
  calculation: "Documentary bounds only.",
  limitations: ["No statistical signal is treated as affected votes."],
};

function send(response, status, payload) {
  response.writeHead(status, {
    "Access-Control-Allow-Origin": "*",
    "Cache-Control": "no-store",
    "Content-Type": "application/json",
  });
  response.end(JSON.stringify(payload));
}

createServer((request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  if (url.pathname === "/healthz") return send(response, 200, { status: "ok" });
  if (url.pathname === "/api/v1/release-elections")
    return send(response, 200, releases);
  const prefix = `/api/v1/releases/${releaseId}/elections/${election}`;
  if (url.pathname === `${prefix}/analysis/summary`)
    return send(response, 200, analysisSummary);
  if (url.pathname === `${prefix}/analysis/anomalies`) {
    const type = url.searchParams.get("anomaly_type");
    const items = analysisAnomalies.filter(
      (item) => !type || item.anomaly_types.includes(type),
    );
    return send(response, 200, {
      items: url.searchParams.has("cursor") ? [] : items,
      page: {
        next_cursor:
          !type && !url.searchParams.has("cursor") ? "analysis-next" : null,
        has_more: !type && !url.searchParams.has("cursor"),
        limit: 25,
      },
      data_version: releaseId,
      methodology_version: "method-v1",
      disclosure: analysisDisclosure,
    });
  }
  const anomalyMatch = url.pathname.match(
    new RegExp(`^${prefix}/analysis/anomalies/([^/]+)$`),
  );
  if (anomalyMatch) {
    const item = analysisAnomalies.find(
      (candidate) => candidate.id === decodeURIComponent(anomalyMatch[1]),
    );
    return item
      ? send(response, 200, item)
      : send(response, 404, { detail: "Analysis anomaly was not found." });
  }
  const reportMatch = url.pathname.match(
    new RegExp(
      `^${prefix}/analysis/(model_diagnostics|validation|local_sensitivity)$`,
    ),
  );
  if (reportMatch) return send(response, 200, report(reportMatch[1]));
  if (url.pathname === `${prefix}/outcome-sensitivity`)
    return send(response, 200, outcomeSensitivity);
  if (url.pathname === `${prefix}/historical-comparison`) {
    const baselineReleaseId = url.searchParams.get("baseline_release_id");
    const baselineElection = url.searchParams.get("baseline_election_slug");
    const geographyId = url.searchParams.get("geography_id") ?? "";
    const requestedGrain = url.searchParams.get("grain") ?? "";
    const unpublished2018Context = unpublished2018Contexts.find(
      (context) =>
        context.release_id === baselineReleaseId &&
        context.election_slug === baselineElection,
    );
    if (unpublished2018Context) {
      return send(response, 200, {
        comparison_status: "not_comparable",
        reason: "missing_geography_crosswalk",
        data_version: releaseId,
        baseline_data_version: unpublished2018Context.release_id,
        geography_id: geographyId,
        requested_grain: requestedGrain,
      });
    }
    return send(response, 200, {
      comparison_status: "not_comparable",
      reason: "missing_geography_crosswalk",
      data_version: releaseId,
      baseline_data_version: baselineReleaseId ?? "",
      geography_id: geographyId,
      requested_grain: requestedGrain,
    });
  }
  if (url.pathname === `${prefix}/results`) {
    return send(response, 200, {
      data_version: releaseId,
      page: { next_cursor: null, has_more: false, limit: 50 },
      items: [
        fact("fact-municipality", "MUN-001", "municipality"),
        fact("fact-mesa", "MESA-001", "mesa", "MESA-001"),
      ],
    });
  }
  const pathMatch = url.pathname.match(
    new RegExp(`^${prefix}/geographies/([^/]+)/path$`),
  );
  if (pathMatch) {
    const id = decodeURIComponent(pathMatch[1]);
    const index = chain.findIndex((item) => item.id === id);
    return index < 0
      ? send(response, 404, {
          status: 404,
          detail: `Geography '${id}' was not found.`,
        })
      : send(response, 200, {
          items: chain.slice(0, index + 1),
          data_version: releaseId,
        });
  }
  const childMatch = url.pathname.match(
    new RegExp(`^${prefix}/geographies/([^/]+)/children$`),
  );
  if (childMatch) {
    const id = decodeURIComponent(childMatch[1]);
    if (!(id in children))
      return send(response, 404, {
        status: 404,
        detail: `Geography '${id}' was not found.`,
      });
    const firstMunicipalityPage =
      id === "MUN-001" && !url.searchParams.has("cursor");
    return send(response, 200, {
      items: children[id],
      page: {
        next_cursor: firstMunicipalityPage ? "geo-next" : null,
        has_more: firstMunicipalityPage,
        limit: 50,
      },
      data_version: releaseId,
    });
  }
  const mesaMatch = url.pathname.match(new RegExp(`^${prefix}/mesas/([^/]+)$`));
  if (mesaMatch) {
    const id = decodeURIComponent(mesaMatch[1]);
    if (id !== "MESA-001")
      return send(response, 404, {
        status: 404,
        detail: `Mesa '${id}' was not found.`,
      });
    const source = url.searchParams.get("source_type");
    const results =
      source === "pre_count"
        ? []
        : [
            fact(
              "fact-mesa",
              "MESA-001",
              "mesa",
              "MESA-001",
              source || "scrutiny",
            ),
          ];
    return send(response, 200, {
      id,
      display_number: "001",
      polling_place_id: "PLACE-01",
      municipality_id: "MUN-001",
      department_id: "DEP-11",
      geography_path: chain,
      results,
      data_version: releaseId,
    });
  }
  const categoryMatch = url.pathname.match(
    new RegExp(`^${prefix}/result-facts/([^/]+)/categories$`),
  );
  if (categoryMatch)
    return send(response, 200, {
      items: [
        {
          category_key: "valid_votes",
          category_code: "VV",
          category_name: "Votos válidos",
          category_kind: "aggregate",
          votes: 232,
          status: "observed",
          provenance: provenance(),
        },
      ],
      page: { next_cursor: null, has_more: false, limit: 50 },
      data_version: releaseId,
      sparse_category_semantics:
        "absent categories are unavailable; they are never inferred as zero",
    });
  return send(response, 404, {
    status: 404,
    detail: "Mock public resource not found.",
  });
}).listen(port, "127.0.0.1", () => {
  process.stdout.write(`normalized mock listening on ${port}\n`);
});
