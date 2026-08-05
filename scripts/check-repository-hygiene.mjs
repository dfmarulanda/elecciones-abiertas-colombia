import { execFileSync } from "node:child_process";

const tracked = execFileSync("git", ["ls-files", "-z"], { encoding: "utf8" })
  .split("\0")
  .filter(Boolean);
const forbidden = [
  /^\.state\//,
  /^\.pipeline\//,
  /^data\/raw\//,
  /^data\/releases\//,
  /(?:^|\/)(?:checkpoint|crawl)\.(?:sqlite3|db)(?:-|$)/i,
  /(?:^|\/)[^/]+\.(?:sqlite3|sqlite|db)-(?:wal|shm)$/i,
];
const violations = tracked.filter((file) =>
  forbidden.some((rule) => rule.test(file)),
);
if (violations.length) {
  console.error(
    "Refusing tracked crawl state, raw objects, release artifacts, or checkpoint databases:",
  );
  for (const file of violations) console.error(` - ${file}`);
  process.exit(1);
}
