# Analytics v2 Visual Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `/analitica` state visually congruent with the shipped v2 homepage while preserving the immutable statistical, routing, authorization, localization, and SEO contracts.

**Architecture:** Load the already-scoped v2 stylesheet at the locale layout, opt analytics routes into it through a small shared shell, and restyle the existing analytics data composition rather than duplicating its adapter logic. Keep all analytics semantics in `analysis-workspace.tsx`; share only structural shell, section-header, and state-band primitives across success, detail, loading, error, and unavailable states.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript 5.9, Tailwind CSS 4, scoped CSS, next-intl catalogs, Vitest/Testing Library, Playwright, axe-core, pnpm 11 through Node 22.23.1 and mise.

## Global Constraints

- Preserve the current election and analysis release IDs, methodology, canonical input hash, manifest hash, provenance hash, exposure tier, and API contracts.
- Preserve the three reconciliation exceptions and every observed, unknown, unavailable, not-applicable, and non-evaluable distinction.
- Keep peer-distribution evidence labelled research preview with zero public statistical-priority contribution.
- Keep mesa turnout, spatial analysis, and outcome sensitivity non-evaluable whenever their existing prerequisites are absent.
- Preserve the eight-section evidence order and render the permanent anti-fraud disclosure before specialist metrics.
- Keep one URL-addressable release-election-analysis selector with cursor and filter pinning.
- Keep ES and EN copy in the existing standard catalogs or existing localized analytics dictionaries.
- Keep preliminary analytics `noindex, nofollow, nocache`, canonicalized to results, and excluded from the sitemap.
- Do not add dependencies, modify backend contracts, fabricate charts or coordinates, add Benford analysis, or expose official document bytes.
- Every interactive target remains at least 44 px, keyboard operable, visibly focused, reflow-safe at 320 px and 200% zoom, and motion-safe under `prefers-reduced-motion`.
- Use `mise exec node@22.23.1 -- pnpm` for Node commands.

---

### Task 1: Shared analytics v2 shell and stylesheet ownership

**Files:**
- Create: `apps/web/components/analysis-v2-primitives.tsx`
- Create: `apps/web/components/analysis-v2-primitives.test.tsx`
- Modify: `apps/web/app/[locale]/layout.tsx`
- Modify: `apps/web/app/[locale]/page.tsx`
- Modify: `apps/web/app/[locale]/design.css`

**Interfaces:**
- Consumes: the existing `.eac-design`, `.eac-gutter`, `.mark`, `.head`, `.mono`, and `.fig` rules.
- Produces: `AnalysisV2Shell`, `AnalysisV2Section`, and `AnalysisV2StateBand` for all analytics route states.

- [ ] **Step 1: Write the failing primitive tests**

```tsx
render(
  <AnalysisV2Shell ariaLabel="Analytics">
    <p>Body</p>
  </AnalysisV2Shell>,
)
expect(screen.getByRole('main', { name: 'Analytics' })).toHaveAttribute(
  'data-design-version',
  'v2',
)
expect(screen.getByRole('main')).toHaveClass('eac-design', 'eac-analysis')

render(
  <AnalysisV2Section
    number="02"
    eyebrow="Coverage"
    title="Release status"
    tone="ink"
  >
    <p>Evidence</p>
  </AnalysisV2Section>,
)
expect(screen.getByRole('heading', { name: 'Release status' })).toBeVisible()
expect(screen.getByText('02')).toBeVisible()
```

- [ ] **Step 2: Run the new test and confirm the missing module failure**

Run: `mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-v2-primitives.test.tsx`

Expected: FAIL because `analysis-v2-primitives.tsx` does not exist.

- [ ] **Step 3: Implement the structural primitives**

```tsx
type AnalysisV2SectionTone = 'paper' | 'ink'

export function AnalysisV2Shell({
  children,
  ariaLabel,
  busy = false,
}: {
  children: ReactNode
  ariaLabel?: string
  busy?: boolean
}) {
  return (
    <main
      id="main-content"
      tabIndex={-1}
      className="eac-design eac-analysis"
      data-design-version="v2"
      aria-label={ariaLabel}
      aria-busy={busy || undefined}
    >
      {children}
    </main>
  )
}

export function AnalysisV2Section({
  number,
  eyebrow,
  title,
  intro,
  tone = 'paper',
  id,
  children,
}: {
  number: string
  eyebrow: string
  title: string
  intro?: string
  tone?: AnalysisV2SectionTone
  id?: string
  children: ReactNode
}) {
  return (
    <section id={id} className={`eac-analysis-section eac-analysis-section--${tone}`}>
      <div className="eac-gutter eac-analysis-section__inner">
        <header className="eac-section-header eac-analysis-section__header">
          <p className="mono eac-analysis-section__number">{number}</p>
          <div>
            <p className="mark eac-analysis-section__eyebrow">{eyebrow}</p>
            <h2 className="head">{title}</h2>
            {intro ? <p className="eac-analysis-section__intro">{intro}</p> : null}
          </div>
        </header>
        {children}
      </div>
    </section>
  )
}
```

`AnalysisV2StateBand` receives `tier`, `status`, and `reasons`, renders text labels supplied by the caller, and uses `role="status"` only for transient status; permanent evidence bands are ordinary labelled regions.

- [ ] **Step 4: Move the scoped stylesheet import without changing homepage output**

Add `import './design.css'` beside `../globals.css` in `apps/web/app/[locale]/layout.tsx`. Remove `import './design.css'` from the homepage. Keep every stylesheet selector below `.eac-design`.

- [ ] **Step 5: Add the base analytics rules**

```css
.eac-design.eac-analysis {
  min-width: 0;
  overflow: clip;
}
.eac-design .eac-analysis-section {
  border-bottom: 1px solid #211e1e;
}
.eac-design .eac-analysis-section--ink {
  background: #151312;
  color: #f4f1ea;
}
.eac-design .eac-analysis-section__inner {
  padding-top: clamp(3rem, 7vw, 7rem);
  padding-bottom: clamp(3rem, 7vw, 7rem);
}
.eac-design .eac-analysis-section__intro {
  max-width: 46rem;
  margin-top: 1rem;
  color: #928979;
}
.eac-design .eac-analysis-section--ink .eac-analysis-section__intro {
  color: #cfc8bc;
}
```

- [ ] **Step 6: Run primitive, homepage, lint, and type checks**

Run:

```bash
mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-v2-primitives.test.tsx components/conteo-hero.test.tsx components/narrative-sections.test.tsx
mise exec node@22.23.1 -- pnpm --filter @elecciones/web lint
mise exec node@22.23.1 -- pnpm --filter @elecciones/web typecheck
```

Expected: all commands exit 0.

### Task 2: Main analytics workspace and eight evidence sections

**Files:**
- Modify: `apps/web/components/analysis-workspace.test.tsx`
- Modify: `apps/web/components/analysis-workspace.tsx`
- Modify: `apps/web/app/[locale]/design.css`

**Interfaces:**
- Consumes: `AnalysisV2Shell`, `AnalysisV2Section`, `AnalysisV2StateBand`, `PublicAnalysisReady`, and the existing adapter responses.
- Produces: a v2 workspace with unchanged forms, URLs, API-derived copy, evidence order, reports, and downloads.

- [ ] **Step 1: Add failing consumer-visible tests**

```tsx
const { container } = render(<AnalysisWorkspace locale="en" analysis={state} />)
const main = screen.getByRole('main')
expect(main).toHaveAttribute('data-design-version', 'v2')
expect(main).toHaveClass('eac-analysis')
expect(container.querySelector('[data-analysis-section="conclusion"]')).toBeTruthy()
expect(container.querySelector('[data-analysis-section="expert"]')).toBeTruthy()
expect(screen.getByText('A signal does not prove fraud or affected votes.')).toBeVisible()
expect(screen.getByLabelText('Release, election, and analysis')).toHaveAttribute(
  'name',
  'context',
)
```

Add an unpublished-peer fixture and assert that its unavailable reason is visible while the page does not state that zero peer anomalies were found.

- [ ] **Step 2: Run the workspace tests and confirm the v2 root/section failures**

Run: `mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-workspace.test.tsx`

Expected: FAIL on the new v2 root and section markers.

- [ ] **Step 3: Replace the legacy Page wrapper with the v2 shell and hero**

Remove the `Page` import. Render `AnalysisV2Shell`, then an ink `eac-analysis-hero` containing the eyebrow, API-derived status, title, intro, plain conclusion, anti-fraud disclosure, composite context selector, release tuple, methodology, and short hashes. Keep the form action, `context` field name, selected option value, and URL query construction unchanged.

- [ ] **Step 4: Port each evidence section without changing its data branch**

Map the existing content to exact markers in this order:

| Marker | Number | Tone | Existing content retained |
| --- | --- | --- | --- |
| `conclusion` | `01` | ink hero | `PlainConclusion`, disclosure, research gate, context selector, release rail |
| `coverage` | `02` | paper | coverage heading, coverage intro, `CoverageTable`, missingness |
| `descriptive` | `03` | ink | evaluated count, qualifying count, deterministic breakdown |
| `deterministic` | `04` | paper | anomaly filters, cards, empty state, pagination |
| `peer` | `05` | paper | peer eligibility, status, reasons, diagnostics if published |
| `spatial` | `06` | ink | spatial eligibility, status, reasons, diagnostics if published |
| `outcome` | `07` | paper | outcome eligibility, issues, `OutcomeSensitivityPanel` |
| `expert` | `08` | ink | reports, artifact downloads, provenance |

Keep `CoverageTable`, `PlainConclusion`, `AnomalyCard`, `ExpectedEvidence`, `ExpertReport`, `ArtifactDownloads`, and `OutcomeSensitivityPanel` behavior. Restyle their DOM with v2 class names and semantic lists/tables instead of bordered dashboard cards.

- [ ] **Step 5: Port state bands, filters, cards, tables, reports, and downloads**

Use `.mark` for tier/status labels, `.mono` for IDs/hashes/metrics, `.fig` for primary counts, and `.claim`/`.head` for editorial headings. Retain table captions, form accessible names, select labels, detail-link labels, download URLs, cursor links, `rel="noreferrer"`, and exact allowlisted HTTP URL validation.

- [ ] **Step 6: Add responsive analytics rules**

Create rules for the hero grid, release tuple, metric grid, coverage table, filters, anomaly rows, evidence bands, report tables, artifact list, and provenance footer. Use `minmax(0, 1fr)` for all grid tracks and `.eac-table-scroll` for wide tables.

- [ ] **Step 7: Run focused workspace and related semantic tests**

Run:

```bash
mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-workspace.test.tsx components/investigation-details.test.tsx data/analysis-adapter.test.ts
```

Expected: all tests pass with unchanged evidence values and URLs.

### Task 3: Anomaly detail and all non-happy route states

**Files:**
- Modify: `apps/web/components/analysis-workspace.test.tsx`
- Modify: `apps/web/components/analysis-workspace.tsx`
- Modify: `apps/web/app/[locale]/analitica/loading.tsx`
- Modify: `apps/web/app/[locale]/analitica/error.tsx`
- Modify: `apps/web/app/[locale]/design.css`

**Interfaces:**
- Consumes: the v2 primitives, `PublicAnomalyDetailState`, localized analysis messages, and existing route error/reset behavior.
- Produces: consistent v2 detail, unavailable, not-found, loading, error, and empty-filter experiences.

- [ ] **Step 1: Add failing tests for unavailable and detail shells**

```tsx
const unavailable = render(
  <AnalysisUnavailable locale="en" status="unavailable" selected={state.selected} />,
)
expect(unavailable.getByRole('main')).toHaveAttribute('data-design-version', 'v2')
expect(unavailable.getByRole('alert')).toHaveTextContent(
  'Missing resources are not replaced with sample data or zeros',
)
```

For the existing normalized anomaly fixture, assert the v2 root, back link with `analysis_release`, typed component evidence, mechanical-bound disclaimer, and provenance hash.

- [ ] **Step 2: Run the detail/unavailable tests and confirm the legacy-shell failures**

Run: `mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-workspace.test.tsx`

Expected: FAIL because these states still render `Page`.

- [ ] **Step 3: Port AnalysisUnavailable**

Render `AnalysisV2Shell` with an ink hero containing the API/source-derived title and a paper alert section containing the no-substitution rule. Preserve `fixture`, `published`, `candidate`, `not_found`, `no_release`, `unavailable`, and `error` title branches. Technical detail remains inside a keyboard-operable disclosure.

- [ ] **Step 4: Port AnalysisAnomalyDetail**

Remove the legacy wrapper and render these alternating fields:

| Field | Number | Tone | Content retained |
| --- | --- | --- | --- |
| `eac-analysis-detail-hero` | unnumbered | ink | back link, release rail, score, evidence tier, disclosure |
| explanation review | `01` | paper | status, effect, p-value, review time, hashes, notes |
| minimum ballot edits | `02` | ink | value, state, mechanical-bound disclaimer, reason |
| component evidence | `03` | paper | eligibility, observed/comparator, calculations, limitations, sources, replay |
| `eac-analysis-provenance` | unnumbered | ink | source, legal status, retrieval, hash, result and back actions |

Keep the audit score, research-preview gate, evidence tier, component eligibility, calculations, sources, replay JSON, minimum-ballot-edit state, result link, back link, and source/release/analysis binding unchanged.

- [ ] **Step 5: Port loading and error boundaries**

Loading uses `AnalysisV2Shell` with `busy`, a localized title, three semantic skeleton regions, and `role="status"`. Error uses `AnalysisV2Shell`, `role="alert"`, existing localized title/body, and a 44 px retry button calling the supplied `reset` callback.

- [ ] **Step 6: Add reduced-motion and small-screen state rules**

```css
@media (prefers-reduced-motion: reduce) {
  .eac-design .eac-analysis-loading__bar {
    animation: none;
  }
}
@media (max-width: 720px) {
  .eac-design .eac-analysis-detail-hero__grid,
  .eac-design .eac-analysis-state__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

- [ ] **Step 7: Run focused route-state tests, lint, and typecheck**

Run:

```bash
mise exec node@22.23.1 -- pnpm --filter @elecciones/web exec vitest run components/analysis-workspace.test.tsx
mise exec node@22.23.1 -- pnpm --filter @elecciones/web lint
mise exec node@22.23.1 -- pnpm --filter @elecciones/web typecheck
```

Expected: all commands exit 0.

### Task 4: Browser contracts, responsive behavior, and accessibility

**Files:**
- Modify: `apps/web/e2e/normalized-public.spec.ts`
- Modify: `apps/web/e2e/product-qa.spec.ts`
- Modify: `apps/web/app/[locale]/design.css`

**Interfaces:**
- Consumes: the normalized API server, existing scoped release fixture, and v2 DOM markers.
- Produces: browser-level proof for the complete responsive and localized analytics experience.

- [ ] **Step 1: Add browser assertions that fail on the legacy design**

```ts
await expect(page.locator('#main-content')).toHaveAttribute(
  'data-design-version',
  'v2',
)
await expect(page.locator('[data-analysis-section]')).toHaveCount(8)
await expect(page.locator('[data-analysis-section="conclusion"]')).toContainText(
  /fraude|fraud/i,
)
```

On the detail and not-found routes, assert the same design-version marker. Add a reduced-motion context and assert that computed animation duration on the loading indicator is `0s` or its animation name is `none`.

- [ ] **Step 2: Run normalized Playwright and confirm the new legacy-design failures**

Run: `mise exec node@22.23.1 -- pnpm --filter @elecciones/web test:e2e:normalized`

Expected: the new v2 marker assertions fail before the final DOM port is present.

- [ ] **Step 3: Correct any browser-discovered overflow, focus, or localization defects**

Use CSS changes under `.eac-design .eac-analysis-*` only. Do not weaken existing axe, URL, content, SEO, filter, pagination, download, or provenance assertions.

- [ ] **Step 4: Capture final visual evidence**

Retain and refresh:

- `output/playwright/analysis-public-desktop.png`
- `output/playwright/analysis-public-mobile-320.png`
- `output/playwright/analysis-public-es-zoom-200.png`
- `output/playwright/analysis-public-en-zoom-200.png`

Add a homepage desktop capture in the same viewport so palette, typography, gutter, and section rhythm can be compared directly.

- [ ] **Step 5: Run complete web verification**

Run:

```bash
mise exec node@22.23.1 -- pnpm --filter @elecciones/web test
mise exec node@22.23.1 -- pnpm --filter @elecciones/web lint
mise exec node@22.23.1 -- pnpm --filter @elecciones/web typecheck
mise exec node@22.23.1 -- pnpm --filter @elecciones/web build
mise exec node@22.23.1 -- pnpm --filter @elecciones/web test:e2e:normalized
```

Expected: 0 failures, 0 lint warnings, successful typecheck/build, no serious or critical axe violations, and no horizontal page overflow.

### Task 5: Straggler audit and repository verification

**Files:**
- Inspect: every changed file
- Inspect: `apps/web/components/page-primitives.tsx`
- Inspect: `packages/contracts/openapi.json`

**Interfaces:**
- Consumes: the completed port.
- Produces: a clean, reproducible change set with no accidental backend or contract drift.

- [ ] **Step 1: Search for legacy analytics wrappers and incomplete work**

Run:

```bash
rg -n 'from "@/components/page-primitives"|<Page|ec-page-content' apps/web/app/'[locale]'/analitica apps/web/components/analysis-workspace.tsx apps/web/components/analysis-v2-primitives.tsx
```

Expected: no `Page` import/render in analytics and no incomplete-work markers. Any `ec-*` occurrence must be a shared accessibility/global utility with an explicit reason.

- [ ] **Step 2: Confirm contract files and backend are unchanged**

Run: `git diff --name-only 349ebce..HEAD`

Expected product files are limited to documentation and `apps/web`; no API, pipeline, migration, or generated contract file changes.

- [ ] **Step 3: Run formatting and root verification**

Run:

```bash
mise exec node@22.23.1 -- pnpm exec prettier --check apps/web docs/superpowers
mise exec node@22.23.1 -- pnpm verify
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit the verified port**

```bash
git add apps/web docs/superpowers
git commit -m "Port analytics portal to design v2"
```

### Task 6: Production deployment and live proof

**Files:**
- No source files expected.
- Inspect: Vercel deployment metadata and live HTTP/browser output.

**Interfaces:**
- Consumes: verified `main` commit and existing Vercel project/environment binding.
- Produces: a promoted production web deployment with the immutable API and analysis release pairing unchanged.

- [ ] **Step 1: Push the verified main branch**

Run: `git push origin main`

Expected: the remote advances to the verified analytics v2 commit without force push.

- [ ] **Step 2: Deploy the web project through the existing Vercel binding**

Run the repository's linked Vercel production deployment from `apps/web` and record the deployment ID, immutable deployment URL, alias, and final `READY` state. Do not redeploy Railway because this change is web-only.

- [ ] **Step 3: Probe production HTTP metadata and API pairing**

Verify HTTP 200 for `/es/analitica`, `/en/analitica`, and one deterministic anomaly detail route. Verify robots and canonical metadata, the exact source release ID, the exact analysis release ID, preliminary exposure text, three reconciliation records, spatial/outcome non-evaluable reasons, and no failed analytics requests.

- [ ] **Step 4: Verify production visually at desktop and 320 px**

Capture homepage and analytics at the same desktop viewport, then analytics at 320 px. Confirm the v2 marker, shared palette/typography/gutter/section rhythm, keyboard skip behavior, no horizontal page overflow, ES/EN copy, and no browser console errors.

- [ ] **Step 5: Report exact deployment and verification evidence**

Report the commit SHA, Vercel deployment ID and URL, production alias, HTTP probes, browser routes/viewports, test counts, and any residual limitation. Do not describe the deployment as complete without live evidence.
