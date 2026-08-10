# Analytics Portal v2 Visual Port Design

Date: 2026-08-10  
Status: approved direction, implementation checkpoint  
Surface: `/es/analitica`, `/en/analitica`, and anomaly detail routes

## Decision

Port the complete analytics experience to the visual language already shipped on the v2 homepage. The analytics portal will share the homepage's paper-and-ink palette, editorial typography, dark narrative fields, neon evidence accents, spacing rhythm, section headers, and data typography. It will remain a public-first explanation of preliminary evidence, with expert detail available progressively.

This is a visual and interaction-system port. It does not change election results, statistical methodology, release identity, evidence hashes, API contracts, exposure authorization, or the meaning of any analytics state.

## Product outcome

The homepage and analytics portal must look and behave as one product. A visitor moving from `/es` to `/es/analitica` should encounter the same visual grammar rather than switching from the v2 editorial experience to the older boxed dashboard system.

The portal still serves two audiences in one page:

- General readers receive the conclusion, disclosure, coverage, and evidence status before specialist metrics.
- Expert readers can inspect filters, anomaly details, diagnostics, validation, provenance, hashes, and downloads without losing reproducibility data.

## Immutable content and data constraints

The port must preserve all existing analytical and publication invariants:

- The current election and analysis releases remain preliminary and immutable.
- The three reconciliation exceptions remain visible.
- Mesa turnout remains non-evaluable when registered-elector coverage is insufficient.
- Spatial analysis remains non-evaluable until authenticated coordinates and deterministic crosswalks exist.
- Outcome sensitivity remains non-evaluable until its documentary, replay, bounds, and methodology prerequisites validate.
- Peer-distribution evidence remains a research preview, and unpublished peer results cannot be presented as zero anomalies.
- Research-preview statistical components contribute zero public audit-priority points.
- No copy may imply fraud, causal attribution, or affected votes without an applicable validated contract.
- Unknown, unavailable, not applicable, not evaluable, preliminary, and independently validated remain distinct states.
- ES and EN content remains sourced from the translation catalog.
- Release, election, and analysis selection remains one exact, URL-addressable context.
- Cursor, filter, pagination, and anomaly-detail routing semantics remain unchanged.
- Preliminary SEO remains `noindex, nofollow, nocache`, with the results page as canonical and no preliminary analytics sitemap entry.

## Visual source of truth

The source of truth is the v2 system in `apps/web/app/[locale]/design.css` and the current localized homepage composition in `apps/web/app/[locale]/page.tsx`.

The port uses these exact foundations:

- Paper: `#f4f1ea`.
- Ink: `#151312` for dark fields and `#211e1e` for primary content.
- Evidence accent: `#c4ff00`.
- Muted text: `#928979` on paper and `#cfc8bc` on ink.
- Editorial headings: the existing v2 heading stack.
- Data and provenance: JetBrains Mono through the existing `.mono` treatment.
- Large evidence figures: the existing `.fig` treatment.
- Small structural labels: the existing uppercase `.mark` treatment.
- Layout: full-width dark and paper sections with the v2 gutter, explicit numbered section headers, and deliberate whitespace instead of stacked bordered cards.

The existing `ec-*` dashboard look is not used inside the redesigned analytics content. Shared global behavior such as focus visibility, font loading, and the site header remains in place.

## Route and file scope

Implementation covers the complete analytics surface, not only the successful main-page response:

- `apps/web/app/[locale]/layout.tsx`: load the scoped v2 stylesheet once for localized routes.
- `apps/web/app/[locale]/page.tsx`: remove its route-local stylesheet import while preserving its current rendered design.
- `apps/web/app/[locale]/design.css`: add analytics-specific v2 classes, responsive rules, and reduced-motion behavior under `.eac-design`.
- `apps/web/app/[locale]/analitica/page.tsx`: render success, unavailable, and not-found states through the v2 analytics shell.
- `apps/web/app/[locale]/analitica/anomalias/[anomalyId]/page.tsx`: render the full detail experience in the same system.
- `apps/web/app/[locale]/analitica/loading.tsx`: use the v2 shell and a motion-safe loading treatment.
- `apps/web/app/[locale]/analitica/error.tsx`: use the v2 shell with a clear localized retry action.
- `apps/web/components/analysis-workspace.tsx`: preserve data composition and routing while replacing the legacy visual structure for the workspace, unavailable state, and anomaly detail.
- `apps/web/components/analysis-v2-primitives.tsx`: hold the small reusable analytics shell, section-heading, evidence-state, and data-display primitives shared by the route states.
- Existing analytics component, adapter, metadata, SEO, and Playwright tests: update visual assertions and add v2 consistency coverage without weakening semantic assertions.

The legacy `Page` primitive remains available to unrelated routes. The analytics port will stop depending on it rather than repainting it globally.

## Stylesheet architecture

`design.css` remains strictly scoped below `.eac-design`. It moves from a homepage-only import to the localized layout so the main analytics route, nested anomaly routes, loading UI, and error boundary can all use it. Because every design rule is scoped, loading it at the layout does not repaint routes that do not opt in with the root class.

Every analytics route state gets one root with:

- `className="eac-design eac-analysis"`
- `data-design-version="v2"`
- a stable skip-link target
- the same page-width and section-boundary behavior as the homepage

Analytics-specific selectors use the `eac-analysis-*` prefix. They reuse v2 tokens and type classes instead of introducing a second palette or component theme.

## Information architecture and composition

The required evidence order remains unchanged. The new composition is:

### 1. Conclusion and permanent disclosure

A full-width ink hero appears immediately below the common site header. It includes:

- A compact evidence-tier and exposure-status line.
- The localized analytics title and plain-language introduction.
- A large conclusion statement that accurately reflects the resolved API metadata.
- The permanent anti-fraud disclosure before any specialist metric.
- The release-election-analysis tuple and short hashes in monospaced text.
- The unified context selector, visually secondary but fully keyboard accessible.

Preliminary status uses the neon accent as a state marker, never as a success or certification signal.

### 2. Release status, coverage, and missingness

A paper section uses the numbered v2 section header followed by an editorial grid of coverage facts. Large values are paired with explicit units and status labels. Missing values are rendered as named states, never coerced to zero. Coverage limitations and the three reconciliation exceptions remain visible in the primary reading path.

### 3. Descriptive insights

An ink section presents national and department-level descriptive evidence through large figures, short explanatory lines, and responsive data tables. Totals, shares, margins, blank/null composition, completion, and margin contribution keep their current data source and definitions.

Historical comparisons remain contextual and clearly separate from anomaly evidence. No Benford content is introduced.

### 4. Deterministic review priorities

A paper section contains the existing anomaly filters, result count, pagination, and detail links. Controls use the v2 form language and retain their current names, query parameters, and cursor behavior. Each record shows its evidence tier, evaluability, priority, explanation, and limitations without turning the list into a dense grid of bordered cards.

The three stored reconciliation exceptions remain discoverable and directly addressable.

### 5. Peer-distribution preview

The peer section presents methodology eligibility before results. If results are not published, the section says so and gives the exact reason. If preliminary results become available, they remain labelled research preview and keep zero public statistical-priority contribution.

The copy keeps the exact-exclusion, peer-count, fallback, correction, residual, and effect-threshold framing already supplied by the API and translations.

### 6. Spatial status or preview

An ink section gives the spatial state substantial visual separation. For the current release it presents `not_evaluable` and the exact missing authenticated-coordinate and crosswalk prerequisites. It must not render a map, score, or empty result that could be read as an executed spatial test.

### 7. Outcome sensitivity

A paper section states the evaluability decision first, then lists unmet prerequisites and the invariant around supported affected-vote bounds. It never converts an unavailable estimate into zero or presents statistical-only signals as affected votes.

### 8. Expert diagnostics, validation, provenance, and downloads

An ink data-room section contains progressively disclosed diagnostics, validation, local sensitivity, artifact statuses, manifest information, hashes, replay metadata, and immutable downloads. Every expected artifact remains represented with its status and reason. Public links expose only non-sensitive artifacts; document bytes and private reviewer contact data remain excluded.

The page ends with a compact monospaced provenance footer pinned to the resolved analysis context.

## Unified context selector

The release-election-analysis selector remains a single control surface. It is placed inside the hero and designed as a labelled v2 field, not a standalone dashboard toolbar.

Changing context continues to:

- Select only a valid release-election-analysis tuple.
- Retain the resolved analysis release in API responses and cursor navigation.
- Derive preliminary, certified, and synthetic framing from API metadata.
- Preserve the localized route.
- Avoid unlocking certified or legacy resources through preliminary exposure.

## Evidence states

Evidence states use a reusable semantic band rather than visually identical cards. Each band contains:

- The evidence tier.
- The availability or evaluability status.
- A plain-language conclusion.
- The exact API-provided reason when one exists.
- Relevant limitations and prerequisites.

Color is supplementary. Text and accessible names carry the state, and no neon-only distinction is required to understand preliminary versus certified evidence.

## Anomaly detail

The detail route receives the complete port:

- Ink introduction field with back navigation, anomaly identity, family, tier, priority, and evaluability.
- Paper evidence section for the explanation and typed components.
- Ink calculations section for raw values and reproducibility data.
- Paper limitations section.
- Ink provenance footer with source and analysis binding.

The typed detail contract remains unchanged. Unknown anomaly responses keep the existing not-found behavior and never fall back to an untyped payload.

## Loading, unavailable, error, and empty states

All non-happy paths use the same v2 shell and page rhythm:

- Loading shows a real title, concise state text, and restrained skeleton fields. Animation is disabled under reduced motion.
- Unavailable shows the source context, status, and exact reason rather than hiding the workspace.
- Error shows a localized explanation and a minimum 44 px retry control.
- Empty anomaly results distinguish an applied filter with no matches from an unpublished or non-evaluable report.
- Not-found behavior remains route-correct and localized.

No state uses placeholder copy, fake metrics, fabricated coordinates, or zero-valued substitutes.

## Responsive and accessible behavior

The port preserves and expands the existing accessibility contract:

- The skip link reaches the analytics main landmark.
- All interactive controls are keyboard reachable with visible focus.
- Controls have a minimum 44 px target size.
- The portal has no horizontal page overflow at 320 px.
- Wide result and evidence tables use an explicitly labelled local scroll region instead of widening the page.
- At 200% zoom, content reflows without overlap, clipping, or lost actions.
- Heading order and landmarks remain semantic across success and error states.
- ES and EN strings fit without fixed-height containers.
- `prefers-reduced-motion` disables decorative entrance, skeleton, and transition motion.
- State and evidence distinctions do not rely on color alone.

## Testing and acceptance

Implementation is accepted only after all of the following pass:

### Focused component and adapter checks

- Existing `analysis-workspace`, investigation-detail, national-summary, result-explorer, and analysis-adapter tests.
- New assertions that every analytics state has `data-design-version="v2"`.
- Semantic assertions for the eight-section order, permanent anti-fraud disclosure, exact non-evaluable reasons, release metadata, filters, pagination, and downloads.
- A regression assertion that unpublished peer results are not rendered as zero anomalies.

### Browser and accessibility checks

- ES and EN desktop flows.
- Main analytics and anomaly-detail routes.
- Loading, unavailable, empty, error, and not-found states.
- Side-by-side desktop captures of the homepage and analytics page showing the shared palette, typography, gutter, and section-header rhythm.
- A 320 px capture with no horizontal page overflow.
- 200% zoom.
- Keyboard navigation, skip link, focus visibility, and 44 px controls.
- Automated accessibility checks.
- Reduced-motion behavior.
- Preliminary robots, canonical, and sitemap behavior.

### Repository verification

- Web lint, typecheck, unit tests, production build, and the focused Playwright suites.
- Deterministic contract generation remains unchanged unless an independently discovered contract defect requires a separate fix.
- Root verification through `mise exec node@22.23.1 -- pnpm verify`.
- A final search confirms the analytics route no longer renders the legacy page primitive or old boxed analytics layout; any retained `ec-*` use must be outside the redesigned surface or explicitly justified.

## Deployment and live proof

After local verification, deploy the complete web port through the repository's existing production workflow. The API and immutable analysis release are not redeployed unless implementation uncovers a real backend defect.

Production acceptance requires live probes for:

- `/es/analitica` and `/en/analitica`.
- At least one deterministic anomaly detail route.
- Release-election-analysis metadata pairing.
- Preliminary disclosure and non-evaluable states.
- Robots and canonical metadata.
- Desktop and 320 px rendered screenshots.
- No runtime console errors or failed analytics requests.

Rollback is the previous web deployment. It does not revoke, relabel, or mutate the election release or analysis exposure.

## Explicit non-goals

This port does not:

- Redesign the homepage again.
- Create a second analytics portal.
- Change statistical thresholds, cohorts, seeds, priorities, validation gates, or artifact contents.
- Certify the current release.
- Add maps without authenticated coordinates.
- Add Benford analysis.
- Download, proxy, cache, OCR, or republish official document bytes.
- Replace reproducibility data with decorative visualization.
- Hide missing reports, prerequisites, reconciliation exceptions, or preliminary caveats.
