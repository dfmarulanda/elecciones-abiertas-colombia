import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const manifestsDirectory = path.resolve(root, "data/manifests");
const pointerPath = path.join(manifestsDirectory, "current-release.json");
const sourceCatalogPath = path.resolve(
  root,
  "config/sources/presidencia-2026-segunda-vuelta.json",
);
const hashPattern = /^[a-f0-9]{64}$/;
const sourceLegalStatus = new Map([
  ["final_declaration", "controlling_final"],
  ["scrutiny", "official_scrutiny"],
  ["e14_delegate", "documentary_evidence"],
  ["e14_transmission", "documentary_evidence"],
  ["pre_count", "preliminary"],
  ["contextual_baseline", "context_only"],
]);

const readJson = async (filePath) =>
  JSON.parse(await readFile(filePath, "utf8"));

const fail = (message) => {
  throw new Error(`Manifest validation failed: ${message}`);
};

const pointer = await readJson(pointerPath);
const sourceCatalog = await readJson(sourceCatalogPath);

if (sourceCatalog.election_slug !== "presidencia-2026-segunda-vuelta") {
  fail("the official source catalog is attached to an unexpected election");
}

if (
  sourceCatalog.collection_policy.maximum_concurrency_per_host > 2 ||
  sourceCatalog.collection_policy.requests_per_second_minimum < 2 ||
  sourceCatalog.collection_policy.requests_per_second_maximum > 5
) {
  fail("the official source catalog exceeds the approved request policy");
}

const allowedHosts = new Set(sourceCatalog.allowed_hosts);
for (const source of [
  ...sourceCatalog.sources,
  ...sourceCatalog.contextual_sources,
]) {
  const entrypoints = source.entrypoints ?? { url: source.url };
  for (const urlValue of Object.values(entrypoints)) {
    const normalized = urlValue.replace("{mesa-id}", "verified-mesa-id");
    const url = new URL(normalized);
    if (url.protocol !== "https:") fail(`source ${source.id} is not HTTPS`);
    if (!allowedHosts.has(url.hostname)) {
      fail(`source ${source.id} uses non-allowlisted host ${url.hostname}`);
    }
  }
}

const finalDeclaration = sourceCatalog.sources.find(
  (source) => source.role === "controlling_final_declaration",
);
if (!finalDeclaration) fail("the final declaration catalog entry is missing");
if (sourceCatalog.publication_state === "awaiting_verified_final_declaration") {
  const pendingStatuses = new Set([
    "not_yet_verified_in_catalog",
    "official_results_page_verified_final_declaration_not_verified",
  ]);
  if (
    !pendingStatuses.has(finalDeclaration.status) ||
    finalDeclaration.entrypoints.declaration
  ) {
    fail("an awaiting catalog must keep the final declaration unverified");
  }
} else if (
  sourceCatalog.publication_state !== "ready_for_candidate_release" ||
  finalDeclaration.status !== "verified" ||
  !finalDeclaration.entrypoints.declaration
) {
  fail(
    "a release-ready catalog needs one explicitly verified final declaration URL",
  );
}

if (!pointer.release_id || !pointer.manifest_path || !pointer.activated_at) {
  fail("current-release.json is missing a required pointer field");
}

const manifestPath = path.resolve(root, pointer.manifest_path);
if (!manifestPath.startsWith(`${manifestsDirectory}${path.sep}`)) {
  fail("the active manifest must remain inside data/manifests");
}

const manifest = await readJson(manifestPath);

if (
  manifest.release_id !== pointer.release_id ||
  manifest.data_version !== pointer.release_id
) {
  fail("release_id, data_version, and active pointer must match");
}

if (path.basename(manifestPath) !== `${manifest.release_id}.json`) {
  fail("immutable manifest filename must match release_id");
}

if (manifest.synthetic !== pointer.synthetic) {
  fail("synthetic state differs between pointer and manifest");
}

for (const source of manifest.sources ?? []) {
  if (!hashPattern.test(source.content_hash ?? "")) {
    fail(`source ${source.id} has an invalid SHA-256 hash`);
  }
  if (sourceLegalStatus.get(source.source_type) !== source.legal_status) {
    fail(
      `source ${source.id} has an incompatible source type and legal status`,
    );
  }
  if (
    !source.source_url?.startsWith("https://") ||
    !source.retrieved_at ||
    !source.media_type ||
    !Number.isInteger(source.byte_size) ||
    source.byte_size < 0 ||
    !source.parser_version ||
    !source.transform_version
  ) {
    fail(`source ${source.id} has incomplete immutable provenance`);
  }

  const coverage = source.coverage;
  const accounted =
    coverage.parsed + coverage.missing + coverage.ambiguous + coverage.excluded;
  if (accounted !== coverage.expected) {
    fail(
      `source ${source.id} coverage does not account for every expected record`,
    );
  }
  if (
    coverage.parsed > coverage.retrieved ||
    coverage.retrieved > coverage.expected
  ) {
    fail(`source ${source.id} coverage counts are not monotonic`);
  }
}

for (const dataset of manifest.datasets ?? []) {
  if (!hashPattern.test(dataset.content_hash ?? "")) {
    fail(`dataset ${dataset.id} has an invalid SHA-256 hash`);
  }
  if (!["csv", "parquet", "json"].includes(dataset.format)) {
    fail(`dataset ${dataset.id} has an unsupported format`);
  }
  if (
    !dataset.url?.startsWith("https://") ||
    !dataset.schema_url?.startsWith("https://") ||
    !Number.isInteger(dataset.record_count) ||
    dataset.record_count < 0 ||
    !Number.isInteger(dataset.byte_size) ||
    dataset.byte_size < 0
  ) {
    fail(`dataset ${dataset.id} has incomplete immutable metadata`);
  }
}

if (manifest.status === "published") {
  const releaseGates = [
    ["aggregate_reconciled", manifest.aggregate_reconciled],
    ["statistical_validation_passed", manifest.statistical_validation_passed],
    ["wording_validation_passed", manifest.wording_validation_passed],
  ];
  const failedGate = releaseGates.find(([, passed]) => !passed);
  if (failedGate) fail(`published release did not pass ${failedGate[0]}`);
  if (manifest.synthetic) fail("synthetic data cannot be marked as published");
  const controllingFinal = manifest.sources.some(
    (source) =>
      source.source_type === "final_declaration" &&
      source.legal_status === "controlling_final",
  );
  if (!controllingFinal)
    fail("published release has no controlling final declaration");
}

console.log(
  `Validated active release ${manifest.release_id} (${manifest.status})`,
);
