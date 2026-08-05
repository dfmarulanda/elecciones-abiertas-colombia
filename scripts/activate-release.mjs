import { readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const manifestsDirectory = path.resolve(root, "data/manifests");
const pointerPath = path.join(manifestsDirectory, "current-release.json");
const argumentsList = process.argv.slice(2);
const releaseFlag = argumentsList.indexOf("--release");
const releaseId = releaseFlag >= 0 ? argumentsList[releaseFlag + 1] : undefined;
const allowFixture = argumentsList.includes("--allow-fixture");

if (!releaseId || !/^[a-zA-Z0-9._-]+$/.test(releaseId)) {
  throw new Error(
    "Usage: pnpm release:activate -- --release <immutable-release-id> [--allow-fixture]",
  );
}

const manifestPath = path.join(manifestsDirectory, `${releaseId}.json`);
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));

if (manifest.release_id !== releaseId || manifest.data_version !== releaseId) {
  throw new Error(
    "Manifest identity does not match the requested immutable release",
  );
}

if (manifest.synthetic && !allowFixture) {
  throw new Error(
    "Refusing to activate synthetic data without --allow-fixture",
  );
}

if (manifest.status === "published") {
  const gates = [
    manifest.aggregate_reconciled,
    manifest.statistical_validation_passed,
    manifest.wording_validation_passed,
  ];
  if (!gates.every(Boolean))
    throw new Error(
      "Refusing to activate a published release with failed gates",
    );
} else if (!manifest.synthetic) {
  throw new Error(
    "A real-data release must be marked published before activation",
  );
}

const pointer = {
  release_id: releaseId,
  manifest_path: path.relative(root, manifestPath),
  activated_at: new Date().toISOString(),
  synthetic: Boolean(manifest.synthetic),
};

const temporaryPath = `${pointerPath}.next`;
await writeFile(temporaryPath, `${JSON.stringify(pointer, null, 2)}\n`, {
  flag: "wx",
});
await rename(temporaryPath, pointerPath);
console.log(`Activated immutable release ${releaseId}`);
