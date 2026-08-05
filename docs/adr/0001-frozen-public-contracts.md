# ADR 0001: Frozen provenance-first public contracts

- Status: accepted
- Date: 2026-08-03

## Decision

The checked-in OpenAPI document, TypeScript schemas, and JSON Schemas are the shared boundary for the web application, API, pipeline releases, and downloads. Changes require a reviewed contract version and regenerated client; implementation packages do not change the contract independently.

Every public result fact carries one explicit source layer and complete provenance. A `MetricValue` pairs a nullable value with an availability state so that observed zero, unknown, unavailable, and not-applicable remain distinguishable.

All releases are immutable. `current-release.json` is the only mutable selection pointer and may target a release only after that manifest passes the gates appropriate to its status. Fixture releases remain visibly synthetic.

Review signals use a deterministic cap of 100, a methodology version, visible components and limitations, source links, an affected-vote estimate when available, and the permanent neutral disclosure in both languages.

## Consequences

- Scrutiny values cannot be coerced to mesa grain when the source does not publish that grain.
- Preliminary, documentary, legally controlling, and historical-context facts can coexist but cannot be merged without an explicit comparison.
- A parser, transform, source object, or methodology change creates new versioned output rather than overwriting existing facts.
- Web filters and CSV exports can be reproduced against a named immutable data version.
