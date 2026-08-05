# Deployment readiness audit

This is a configuration guide, not evidence of a live deployment. No Vercel, Railway, Neon, or R2 deployment was performed for this handoff. Do not activate a release, create a cloud project, or put secret values in this file.

## Vercel web deployment

The web app is a Next.js app in a pnpm workspace and imports the local `@elecciones/contracts` package. Vercel detects pnpm workspaces from the root `pnpm-workspace.yaml`, root `pnpm-lock.yaml`, and root `packageManager` field (`pnpm@11.1.3`); do not replace that workspace metadata with an app-local lockfile or package-manager setting. See Vercel's [monorepo requirements](https://vercel.com/docs/monorepos).

Recommended Vercel project settings:

| Setting          | Value                                                                              |
| ---------------- | ---------------------------------------------------------------------------------- |
| Framework preset | Next.js                                                                            |
| Root Directory   | `apps/web`                                                                         |
| Package manager  | pnpm 11 (the root declares `pnpm@11.1.3`)                                          |
| Node.js          | 22.x (pinned by `.nvmrc`, `.node-version`, and package engines)                    |
| Install Command  | `pnpm install --frozen-lockfile`                                                   |
| Build Command    | `pnpm --filter @elecciones/contracts build && pnpm --filter @elecciones/web build` |
| Output Directory | Leave Vercel's Next.js default; do not set a static export directory               |

In **Settings → Build and Deployment → Root Directory**, explicitly check that **Include source files outside of the Root Directory** is enabled. This is required because `apps/web` imports `@elecciones/contracts` from `packages/contracts`, outside `apps/web`. Vercel enables this by default for newer projects, but it is a project setting worth verifying. See [Vercel's monorepo FAQ](https://vercel.com/docs/monorepos/monorepo-faq#can-i-share-source-files-between-projects-are-shared-packages-supported).

The explicit contracts build is required because the web app consumes the workspace package's generated `dist` declarations. Keep the repository `pnpm-lock.yaml`, `pnpm-workspace.yaml`, and root package metadata available to the Vercel build. Vercel's workspace/package-manager detection and the outside-root source setting must both be intact before relying on the build command.

Set these Vercel environment variables by name:

| Variable                          | Required                             | Notes                                                                                       |
| --------------------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`             | Yes for real data                    | HTTPS Railway API origin, without relying on a trailing slash.                              |
| `NEXT_PUBLIC_ELECTION_SLUG`       | Usually                              | Election selected by the web adapter; defaults only for local development.                  |
| `NEXT_PUBLIC_ACTIVE_RELEASE`      | Yes for a selected immutable release | Exact release ID; changing it is a deployment configuration change, not release activation. |
| `NEXT_PUBLIC_SYNTHETIC_FIXTURE`   | No                                   | Set only for an intentional synthetic demonstration; never use as a real-data fallback.     |
| `NEXT_PUBLIC_SENTRY_DSN`          | Optional                             | Public browser DSN only.                                                                    |
| `SENTRY_DSN`, `SENTRY_AUTH_TOKEN` | Optional                             | Server/upload configuration; keep secret.                                                   |

The client-error relay is deliberately not an analytics endpoint. Configure a Vercel WAF/rate-limit rule for `POST /api/_monitoring/client-error` before enabling a Sentry DSN: allow only same-origin traffic, set a small per-IP quota (for example 12 requests/minute), cap body size at 4 KiB, and return `429` when exceeded. The handler also applies an ephemeral, size-capped in-process quota, bounded body reader, JSON content type, Origin, and Fetch Metadata checks; this is defence in depth, not a substitute for edge limiting across Vercel instances. The edge/proxy must remove client-supplied forwarding headers and set the trusted visitor-address header itself; it is a throttling key, never authentication. Set Sentry inbound filtering/quota alerts so telemetry spikes cannot exhaust the project quota.

## Railway API boundary

Use the **repository root** as Railway's build context/root directory. Do not set `apps/api` as the Railway Root Directory: the Dockerfile copies `apps/api`, `data`, and `packages/contracts/openapi.json` relative to the repository root. Configure the Railway config file as the absolute repository path `/apps/api/railway.toml` (or set the equivalent service setting) and the Dockerfile path as `/apps/api/Dockerfile`. The checked-in `apps/api/railway.toml` currently names `apps/api/Dockerfile`, which is correct only with the repository-root build context. Railway documents that its config-file path is absolute and does not follow the Root Directory; see [Deploying a Monorepo](https://docs.railway.com/deployments/monorepo) and [custom Dockerfile paths](https://docs.railway.com/builds/dockerfiles).

The Vercel origin must be listed exactly in Railway's `ALLOWED_ORIGINS` (or `ELECCIONES_CORS_ORIGINS`); include the production domain and any intentional preview domain separately. The API permits only `GET` and `OPTIONS`, has no credentialed CORS, and accepts `Accept`, `Content-Type`, and `If-None-Match` headers.

For a database-backed Railway deployment, set `DATABASE_URL`, a non-development `CURSOR_SECRET`, and either `ACTIVE_RELEASE` or a valid `ACTIVE_RELEASE_POINTER`. The Dockerfile's fixture path is appropriate only for intentional fixture previews. Configure `ARTIFACT_HOSTS` with the exact HTTPS hosts used by immutable dataset redirects, `TRUSTED_HOSTS` with the exact Railway/custom API hostnames, and `OFFICIAL_DOCUMENT_HOSTS` with every exact document/derivative hostname approved for that release. `example.invalid` is only the synthetic-fixture default and must not be used for a real release.

The image runs as an unprivileged `elecciones` user. Set Railway service CPU and memory limits based on measured CSV streaming load, an ingress/request-body cap, request timeouts, and an edge rate limit before production; these are platform settings and cannot be reliably encoded in `railway.toml` without fixing a paid-plan-specific size. Run collectors/document workers in a separate network segment with an egress allowlist: DNS is rechecked for every URL and redirect, but network egress policy is still required to reduce DNS time-of-check/time-of-use exposure.

Before routing Vercel traffic, check Railway `/healthz`, `/readyz`, and a versioned summary response. Verify the frozen `/api/v1/openapi.json`, `ETag`, expected `data_version`, CORS response for the Vercel origin, and that a candidate release remains labelled candidate/preliminary.

The architecture is deployment-ready only after credentials, domains, and edge controls are supplied and reviewed: platform secret stores, DNS/custom domains, Vercel WAF/rate limits, Railway ingress limits, and the required egress policy remain external operator gates. None is implied by the checked-in configuration.
