# Security best-practices audit — 2026-08-03

## Executive summary

This was a read-only, source-based review of the Next.js public viewer, the
FastAPI read API, the Python collection/document pipeline, deployment and CI
configuration, and locked production dependencies. No application code,
manifest, raw object, or deployment setting was changed.

Two high-severity issues need resolution before a production release: the
locked web dependency graph has three high-severity advisories, and the public
client-error endpoint can be used to generate arbitrary Sentry events without
a rate limit. There are six medium-severity issues at data-ingestion, document,
CSV, host-header, and repository-retention boundaries. No critical issue was
confirmed. The review found strong existing controls for immutable provenance,
parameterized database queries, signed/scope-bound cursors, CORS without
credentials, redacted E-14 derivatives, and Sentry PII scrubbing.

The report deliberately does **not** treat the intentional public OpenAPI
document as a finding.

## Scope and method

- Examined application and deployment source at the current working-tree state.
- Searched for XSS sinks, unsafe navigation, client storage, SSRF, file
  handling, redirects, SQL construction, unsafe subprocess use, CORS, host
  validation, telemetry, and headers.
- Ran focused controls tests: `56 passed` in document fetching, collector, and
  API test modules.
- Ran `pnpm audit --prod --audit-level=high --json`: 3 high, 2 moderate, 0
  critical findings. Ran the locked Python export through `pip-audit 2.10.1`:
  all workspace packages and dependency groups resolve to 78 locked packages,
  with no known vulnerabilities. The audit intentionally uses `--no-deps` and
  an export without hashes; `pip-audit` warns that fully hashed requirements
  are preferable, but the lockfile remains the source of truth and no
  dependency resolution drift is introduced.
- Confirmed the fixture download redirect and document-index behavior with
  local, non-mutating test-client calls. No secrets or raw document contents
  are reproduced here.

## High severity

### H-01 — Production web lockfile contains high-severity vulnerable transitive dependencies

- **Rule IDs:** REACT-SUPPLY-001, NEXT-SUPPLY-001
- **Location:** [apps/web/package.json](../apps/web/package.json#L19),
  [pnpm-lock.yaml](../pnpm-lock.yaml#L3651),
  [pnpm-lock.yaml](../pnpm-lock.yaml#L3849)
- **Evidence:** production `next@16.2.12` resolves `postcss@8.4.31` and
  optional `sharp@0.34.5`. `pnpm audit` reports `GHSA-6g55-p6wh-862q` and
  `GHSA-r28c-9q8g-f849` for PostCSS (both patched at `>=8.5.18`), and
  `GHSA-f88m-g3jw-g9cj` for Sharp (patched at `>=0.35.0`).
- **Impact:** a build or runtime path processing attacker-controlled CSS/source
  map directives may disclose local files; the Sharp advisory affects the
  installed image-processing dependency. This creates an unnecessary
  production supply-chain exposure.
- **Fix:** update Next.js (or add a tested package-manager override) until the
  dependency graph uses patched PostCSS and Sharp versions; regenerate the
  lockfile, run the full test/build suite, and make a production audit a CI
  release gate.
- **Mitigation:** do not process untrusted CSS or source maps; disable or
  tightly constrain image optimization until patched.
- **False-positive notes:** no `next/image` usage was found in `apps/web`, so
  the practical reachability of the Sharp advisory requires confirmation. The
  PostCSS package is nevertheless present in the production dependency graph.

### H-02 — Client-error collection endpoint has no anti-abuse control

- **Rule IDs:** NEXT-DOS-001, NEXT-INPUT-001, NEXT-LOG-001
- **Location:** [apps/web/app/api/_monitoring/client-error/route.ts](../apps/web/app/api/_monitoring/client-error/route.ts#L22)
- **Evidence:** when a Sentry DSN is configured, the endpoint accepts every
  `POST` whose caller-supplied `Origin` host equals the request host
  (lines 23–37), then calls `Sentry.captureMessage` (lines 55–65). A direct
  HTTP client can forge `Origin`; no rate limit, durable nonce, or edge rule is
  visible in the repository.
- **Impact:** an unauthenticated actor can pollute incident telemetry and drive
  Sentry event volume/cost, potentially obscuring real errors. The 4 KiB body
  cap limits each request, but not request rate.
- **Fix:** enforce a Vercel/edge rate limit before the handler and a second
  server-side token-bucket limit keyed by an appropriately privacy-preserving
  request key. Reject requests without a browser-validated signal such as
  `Sec-Fetch-Site: same-origin` as defense in depth; do not rely on `Origin` as
  authentication. Cap Sentry events independently as well.
- **Mitigation:** configure Sentry inbound filters/quotas and alert on event
  spikes until code and edge limits exist.
- **False-positive notes:** the route is inactive when neither DSN variable is
  configured. Production monitoring is expected to configure one, making the
  endpoint live.

## Medium severity

### M-01 — Host header controls a public fixture-download redirect

- **Rule IDs:** FASTAPI-HOST-001, NEXT-HOST-001
- **Location:** [apps/api/src/elecciones_api/main.py](../apps/api/src/elecciones_api/main.py#L938)
- **Evidence:** fixture mode constructs the redirect target from
  `request.url.include_query_params(raw="true")` (line 945). No
  `TrustedHostMiddleware` is registered (the middleware list at lines
  381–400 contains only CORS). A local request with `Host: attacker.example`
  returned `302 Location: http://attacker.example/api/v1/datasets/fixture-results-json/download?raw=true`.
- **Impact:** a link to the fixture download endpoint can be turned into an
  attacker-host redirect, supporting phishing and cache confusion. The route
  serves public synthetic data, so this is not an authenticated data leak.
- **Fix:** use a relative redirect (`?raw=true`) or an explicitly configured
  canonical origin, and add `TrustedHostMiddleware` with the production API
  hostnames. Test requests with untrusted `Host` and forwarded-host headers.
- **Mitigation:** enforce host allowlisting at Railway/reverse-proxy level.
- **False-positive notes:** the affected branch is fixture mode, but it is the
  default whenever `DATABASE_URL` is absent and is included in the API Docker
  image.

### M-02 — Raw crawl state is unignored and currently eligible for an accidental commit

- **Rule IDs:** REACT-SUPPLY-001, FASTAPI-SUPPLY-001
- **Location:** [.gitignore](../.gitignore#L1), repository root `.state/`
- **Evidence:** `.gitignore` ignores `.pipeline/`, `data/raw/`, and `*.sqlite3`,
  but not `.state/`. `git status --short` reports `?? .state/`; the directory
  is approximately 148 MB and contains content-addressed scrutiny objects plus
  crawl WAL/SHM files.
- **Impact:** raw collection artifacts can enter commits, PR uploads, caches,
  or forks despite the documented R2-only raw-data policy. This increases
  repository supply-chain surface, can expose data retained outside the
  intended controlled store, and makes review/deployment unnecessarily heavy.
- **Fix:** add `.state/` to `.gitignore`, remove it from any index before the
  first commit, and use a pre-commit/CI rule that rejects raw objects,
  checkpoint databases, and derivative caches outside approved manifests.
- **Mitigation:** keep the working directory private and avoid `git add -A`
  until the ignore rule is in place.
- **False-positive notes:** this finding does not assert that the current raw
  objects contain PII; it identifies a confirmed retention and accidental
  publication path.

### M-03 — Document indexing accepts external URLs before the later fetch gate

- **Rule IDs:** REACT-URL-001, FASTAPI-SSRF-001
- **Location:** [pipeline/src/elecciones_pipeline/documents/index.py](../pipeline/src/elecciones_pipeline/documents/index.py#L48),
  [apps/web/app/[locale]/actas/[mesaId]/page.tsx](../apps/web/app/%5Blocale%5D/actas/%5BmesaId%5D/page.tsx#L118),
  [apps/api/src/elecciones_api/schemas.py](../apps/api/src/elecciones_api/schemas.py#L207)
- **Evidence:** `index_official_documents()` uses `urljoin(source_index_url,
url)` and creates `DocumentIndexEntry` without applying
  `DocumentURLPolicy` (lines 67–76). A local call accepted
  `https://untrusted.example/f.pdf`. The public schema requires only `HttpUrl`
  (lines 207–220), and the web page renders `document.official_url` directly
  as an anchor `href` (lines 118–124). The later on-demand fetch does enforce
  an exact-host/DNS policy at
  [documents/policy.py](../pipeline/src/elecciones_pipeline/documents/policy.py#L54),
  but that does not validate public indexed links.
- **Impact:** a compromised or malformed official index can introduce an
  arbitrary HTTPS link into evidence records and direct users away from the
  portal. It is not a `javascript:` XSS path because the public contract uses
  `HttpUrl`, and the fetch path rejects unallowlisted hosts.
- **Fix:** validate index URLs against the same exact official-host policy at
  indexing time; reject or quarantine them before materialization. Validate
  `official_url` and cached derivative hosts again at release-publication/API
  boundaries. Render an explicit verified-host label beside external links.
- **Mitigation:** do not publish index entries until host validation is part of
  the release gate.
- **False-positive notes:** verified present fixtures use placeholder HTTPS
  URLs; a real candidate release must still prove that each document host is
  approved.

### M-04 — Generic collector validates host text but not resolved destination IP or HTTPS port

- **Rule IDs:** FASTAPI-SSRF-001, NEXT-SSRF-001
- **Location:** [pipeline/src/elecciones_pipeline/ingest/policy.py](../pipeline/src/elecciones_pipeline/ingest/policy.py#L16),
  [pipeline/src/elecciones_pipeline/ingest/http.py](../pipeline/src/elecciones_pipeline/ingest/http.py#L127)
- **Evidence:** `AllowlistPolicy.permits()` checks HTTPS, user-info, and a
  hostname/suffix match (lines 32–42), but does not resolve DNS, reject private
  addresses, or limit the port. `AsyncOfficialClient` follows redirects after
  that text-only policy check (lines 155–167). The stricter document policy
  does resolve and reject non-public addresses
  ([documents/policy.py](../pipeline/src/elecciones_pipeline/documents/policy.py#L42)),
  demonstrating that this control is absent only from generic ingestion.
- **Impact:** a DNS-rebinding or compromised allowlisted host/subdomain can
  cause collection workers to contact a private service or an unexpected HTTPS
  port. This is a pipeline trust-boundary issue, not a public arbitrary-URL
  endpoint.
- **Fix:** use exact hosts for redirects unless each subdomain is reviewed;
  reject non-443 ports; resolve every initial and redirect target, reject every
  non-public result, and bind the connection to a validated address (or apply
  network egress policy) to close DNS time-of-check/time-of-use gaps.
- **Mitigation:** run collectors in a network segment without access to cloud
  metadata, database, and private administrative services; enforce egress
  allowlists in the runner/network.
- **False-positive notes:** the checked-in catalog validates initial endpoint
  hosts exactly. The gap applies to redirects and future discovered URLs, and
  exploitation requires control of, or a malicious response from, an approved
  host.

### M-05 — PDF rasterization can allocate before a pixel-size check

- **Rule IDs:** FASTAPI-LIMITS-001, FASTAPI-FILES-001
- **Location:** [pipeline/src/elecciones_pipeline/documents/redaction.py](../pipeline/src/elecciones_pipeline/documents/redaction.py#L100)
- **Evidence:** the PDF branch calls `page.get_pixmap()` at line 107 and only
  checks raster dimensions/pixels after converting that pixmap to an image
  (lines 108–111). The fetcher caps input bytes and page count
  ([documents/fetch.py](../pipeline/src/elecciones_pipeline/documents/fetch.py#L142)),
  but a small PDF can describe a very large page.
- **Impact:** a malicious or malformed PDF from an otherwise approved source
  can exhaust worker memory/CPU during redaction before the configured
  `max_raster_pixels` gate runs.
- **Fix:** calculate/limit the rendered page dimensions before `get_pixmap`,
  render with a bounded scale/clip, and run PDF processing in a memory- and
  CPU-limited worker. Add a regression fixture with an oversized PDF page.
- **Mitigation:** retain the existing 20 MiB, four-page, and timeout limits;
  isolate document workers from the public API process.
- **False-positive notes:** this is demand-driven and reviewer-gated, reducing
  exposure, but it remains a realistic robustness issue for untrusted binary
  inputs.

### M-06 — Production CSV exports do not neutralize spreadsheet formulas

- **Rule IDs:** FASTAPI-RESP-001
- **Location:** [apps/api/src/elecciones_api/main.py](../apps/api/src/elecciones_api/main.py#L269)
- **Evidence:** `_normalized_csv_row()` passes `id`, `geography_id`, `mesa_id`,
  and `source_id` directly to `csv.DictWriter` (lines 281–293). The public
  `ResultFact` schema accepts these as unrestricted strings
  ([apps/api/src/elecciones_api/schemas.py](../apps/api/src/elecciones_api/schemas.py#L92)).
  The synthetic CSV path already has a `csvCell()` guard for `=`, `+`, `-`,
  `@`, tab, and carriage-return
  ([apps/web/lib/result-filters.ts](../apps/web/lib/result-filters.ts#L128)),
  but the normalized API export does not.
- **Impact:** if a release contains a maliciously prefixed upstream identifier,
  opening the downloaded CSV in spreadsheet software can evaluate a formula.
- **Fix:** apply one shared CSV cell encoder to every non-numeric exported
  field, prefixing formula-leading values with a single quote before writing;
  add unit tests for both legacy and normalized streams.
- **Mitigation:** publish Parquet and JSON alongside CSV and warn consumers not
  to enable formulas in untrusted CSVs.
- **False-positive notes:** current canonical identifiers may be controlled by
  the pipeline. The schema does not enforce that invariant, so the release
  boundary should defend it.

## Low severity / defense in depth

### L-01 — The web application sets useful headers but no Content Security Policy is visible

- **Rule IDs:** JS-CSP-001, REACT-HEADERS-001, NEXT-CSP-001
- **Location:** [apps/web/next.config.ts](../apps/web/next.config.ts#L5),
  [apps/web/vercel.json](../apps/web/vercel.json#L1)
- **Evidence:** repository configuration sets `nosniff`, `X-Frame-Options`,
  referrer, and permissions headers, but neither file sets
  `Content-Security-Policy` or `frame-ancestors`.
- **Impact:** if an XSS escape hatch or compromised third-party script is ever
  introduced, the browser has less defense in depth. Current search found no
  `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `postMessage`, or client
  credential storage in app code.
- **Fix:** add a tested report-only CSP first, then enforce a narrow policy.
  Account deliberately for Next.js and MapLibre worker/style requirements;
  use `frame-ancestors 'none'` rather than relying only on X-Frame-Options.
- **Mitigation:** preserve React escaping, avoid raw HTML, and keep all scripts
  first-party.
- **False-positive notes:** Vercel or another edge layer may set CSP outside
  this repository; verify deployed response headers before classifying the
  absence as production exposure.

### L-02 — API container runs as root and has no visible resource limits

- **Rule IDs:** FASTAPI-DEPLOY-001, FASTAPI-LIMITS-001
- **Location:** [apps/api/Dockerfile](../apps/api/Dockerfile#L1),
  [apps/api/railway.toml](../apps/api/railway.toml#L1)
- **Evidence:** the Dockerfile has no `USER` instruction and launches Uvicorn
  as the image default root user. The Railway configuration defines a health
  check and restart policy but no resource/request limits.
- **Impact:** a process compromise has unnecessary filesystem/container
  privileges; unbounded public read requests depend on platform defaults.
- **Fix:** create a non-root runtime user, copy only read-only required assets,
  and set platform CPU/memory/request-size/rate controls appropriate to the
  API’s CSV streaming workload.
- **Mitigation:** Railway platform isolation may reduce impact; verify its
  runtime limits and filesystem policy.
- **False-positive notes:** no application-level code execution vulnerability
  was confirmed in this review.

## Positive controls verified

- **Strict provenance and release exposure:** normalized PostgreSQL reads use
  parameterized `text(statement), values` calls and read-only transactions
  ([repository.py](../apps/api/src/elecciones_api/repository.py#L463)); public
  data requires both a published release and a public approved exposure
  ([repository.py](../apps/api/src/elecciones_api/repository.py#L486)).
- **Cursor tamper protection:** cursors are HMAC-SHA-256 signed, length-bounded,
  and bound to normalized filter scope
  ([cursor.py](../apps/api/src/elecciones_api/cursor.py#L14)).
- **Least-privilege CORS:** the API has configured origins, no credentialed
  requests, and only `GET`/`OPTIONS`
  ([main.py](../apps/api/src/elecciones_api/main.py#L381)).
- **API error and Sentry privacy:** generic 500 responses are returned without
  exception details ([main.py](../apps/api/src/elecciones_api/main.py#L423));
  both API and web Sentry hooks remove cookies, request bodies, headers, query
  strings, and user data
  ([main.py](../apps/api/src/elecciones_api/main.py#L64),
  [sentry-privacy.ts](../apps/web/lib/sentry-privacy.ts#L3)).
- **Document safeguards:** on-demand E-14 retrieval is HTTPS/exact-host
  allowlisted, checks public DNS results and redirects, disables automatic
  redirects, enforces byte/page limits, requires a human PII review
  attestation, and stores only a cropped WebP derivative by default
  ([documents/fetch.py](../pipeline/src/elecciones_pipeline/documents/fetch.py#L186),
  [documents/policy.py](../pipeline/src/elecciones_pipeline/documents/policy.py#L54),
  [documents/redaction.py](../pipeline/src/elecciones_pipeline/documents/redaction.py#L86)).
- **Collector safeguards:** generic collection disables automatic redirects,
  rechecks targets against an allowlist, uses bounded per-host rate/concurrency,
  honors conditional requests and `Retry-After`, quarantines permanent
  failures, and persists raw bytes before parsing
  ([ingest/http.py](../pipeline/src/elecciones_pipeline/ingest/http.py#L47)).
- **Public-release safeguards:** release validation checks provenance,
  coverage, exact reconciliation, PII-like public text, and allowlisted public
  manifest URLs ([quality/release.py](../pipeline/src/elecciones_pipeline/quality/release.py#L765),
  [quality/release.py](../pipeline/src/elecciones_pipeline/quality/release.py#L825)).
- **CI security coverage:** PR dependency review and CodeQL for JavaScript/
  TypeScript and Python are enabled. A separate Python audit exports every
  workspace package and dependency group directly from `uv.lock` and scans the
  resulting 78 locked packages without dependency resolution
  ([.github/workflows/security.yml](../.github/workflows/security.yml#L1)).

## Runtime and operational checks not visible in source

Before production activation, verify deployed Vercel and Railway responses for
the final CSP, `frame-ancestors`, host allowlisting, HTTPS redirect behavior,
request/body limits, rate limits, and trusted-proxy/forwarded-header settings.
Also verify R2 bucket policies: raw source objects must remain private; only
reviewed redacted derivatives and immutable public datasets may be publicly
addressable.

## Remediation update — 2026-08-03

The findings above are preserved as the original audit record. The following
implementation changes and local verification evidence update their status;
production activation remains blocked on the listed deployment checks and the
separate data/methodology release gates.

| Finding | Status                                            | Remediation and evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| H-01    | Remediated in repository                          | `pnpm-workspace.yaml` pins transitive PostCSS 8.5.25 and Sharp 0.35.3; the regenerated lock resolves those patched versions. `pnpm audit --prod --audit-level=high` reports 0 vulnerabilities. `.github/workflows/security.yml` makes that audit a PR/push/scheduled CI gate. The same workflow also audits the 78-package Python `uv.lock` export across all workspace packages/groups with pinned `pip-audit 2.10.1`; it reports no known vulnerabilities. The Python export omits hashes and `pip-audit --no-deps` emits its expected fully-hashed-requirements warning. Web lint, typecheck, and production build passed. |
| H-02    | Remediated in repository; deployment gate remains | The relay now has a 4 KiB streaming body cap, JSON content-type, Origin and `Sec-Fetch-Site: same-origin` checks, plus an ephemeral 4,096-entry-capped in-process 12/minute bucket keyed by a per-process salted address hash. Deployment documentation requires Vercel WAF/rate limiting, trusted proxy forwarding headers, and Sentry quotas; that cross-instance edge control must be verified before enabling Sentry in production. Web route tests passed.                                                                                                                                                               |
| M-01    | Remediated                                        | Fixture downloads now redirect with a relative path. `TrustedHostMiddleware` uses configurable exact `TRUSTED_HOSTS` with local-safe defaults. Tests cover an attacker Host rejection and a relative redirect even if such a host is temporarily allowed. Railway host configuration remains a deployment verification item.                                                                                                                                                                                                                                                                                                  |
| M-02    | Remediated                                        | `.state/` is ignored. `scripts/check-repository-hygiene.mjs` and the CI workflow reject tracked crawl state, raw/release artifacts, and checkpoint databases. The checked-in historical manifest policy remains unchanged.                                                                                                                                                                                                                                                                                                                                                                                                    |
| M-03    | Remediated in ingestion/API                       | Document indexing now requires `DocumentURLPolicy` and rejects non-exact approved hosts before materialization. The API rechecks original and derivative URLs against `OFFICIAL_DOCUMENT_HOSTS`; the evidence UI displays the verified host. Tests cover an external index URL and unsafe public evidence. Every real deployment must configure exact official document hosts.                                                                                                                                                                                                                                                |
| M-04    | Remediated in code; network residual remains      | Generic ingestion now accepts exact HTTPS hosts only, requires port 443, forbids IP literals, and resolves/rejects any non-public DNS answer for every initial and redirect target. Tests cover subdomains, user-info, non-443 ports, IP literals, and private DNS. DNS rebinding between check and connection still requires collector network egress isolation/allowlisting, documented in deployment guidance.                                                                                                                                                                                                             |
| M-05    | Remediated                                        | PDF page dimensions are converted into a bounded render matrix before `get_pixmap`; dimensions and total pixels are limited before allocation. The regression test uses a 100,000 × 100,000-point PDF page and verifies the bounded derivative. Document worker CPU/memory isolation remains an operational requirement.                                                                                                                                                                                                                                                                                                      |
| M-06    | Remediated                                        | Both fixture and normalized CSV writers share formula-cell neutralization for `=`, `+`, `-`, `@`, tab, and carriage-return prefixes. API regression coverage checks hostile identifiers.                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| L-01    | Report-only CSP enabled; runtime gate remains     | Next now emits a conservative `Content-Security-Policy-Report-Only` including `frame-ancestors 'none'`; the optimized Next build passed. It does not block MapLibre/Next while reports are observed. Verify deployed CSP reports and MapLibre behavior before enforcing a policy.                                                                                                                                                                                                                                                                                                                                             |
| L-02    | Remediated in image; platform gate remains        | The API Docker image creates and runs as unprivileged `elecciones`; copied application/data files remain root-owned and non-writable by that account, and Python bytecode writing is disabled. Deployment guidance requires Railway CPU/memory/request limits and ingress rate/body controls, which are platform-plan configuration rather than committed defaults.                                                                                                                                                                                                                                                           |

Focused verification after remediation: `67 passed` API/collector/document tests,
`42 passed` web tests, `pnpm --filter @elecciones/web lint`, `typecheck`, and
`build` all passed. Scoped Ruff and MyPy checks passed. Repository-wide migration
Ruff checks now pass after mechanical formatting and migration cleanup.
