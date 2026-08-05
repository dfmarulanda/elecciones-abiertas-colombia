import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const publicRoots = ["apps/web", "docs", "data/manifests", "data/fixtures"];
const publicExtensions = new Set([
  ".ts",
  ".tsx",
  ".json",
  ".md",
  ".mdx",
  ".html",
]);
const forbidden = [
  /fraud probability/iu,
  /fraud risk score/iu,
  /probabilidad de fraude/iu,
  /puntaje de riesgo de fraude/iu,
];
const disclosure =
  "This score prioritizes records for review. It is not a probability or finding of fraud. Absence of a signal does not prove that a mesa was error-free.";
const disclosureEs =
  "Este puntaje prioriza registros para revisión. No es una probabilidad ni un hallazgo de fraude. La ausencia de una señal no demuestra que una mesa estuviera libre de errores.";

const files = [];

const walk = async (directory) => {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      if (!["node_modules", ".next", "dist", "coverage"].includes(entry.name))
        await walk(target);
    } else if (publicExtensions.has(path.extname(entry.name))) {
      files.push(target);
    }
  }
};

for (const publicRoot of publicRoots)
  await walk(path.resolve(root, publicRoot));

const violations = [];
let combined = "";
for (const file of files) {
  const contents = await readFile(file, "utf8");
  combined += contents;
  for (const phrase of forbidden) {
    if (phrase.test(contents))
      violations.push(`${path.relative(root, file)}: ${phrase.source}`);
  }
}

if (!combined.includes(disclosure) || !combined.includes(disclosureEs)) {
  violations.push(
    "the permanent review-score disclosure is missing in Spanish or English",
  );
}

if (violations.length > 0) {
  throw new Error(
    `Public wording validation failed:\n${violations.join("\n")}`,
  );
}

console.log(
  `Checked ${files.length} reader-facing files for neutral review wording`,
);
