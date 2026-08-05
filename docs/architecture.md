# Architecture and release boundaries

## Immutable release flow

1. Collectors discover only from reviewed official entry manifests.
2. Response bytes are hashed and stored before parsing.
3. Normalized facts retain source-layer identity and provenance.
4. Deterministic reconciliation runs before statistical analysis.
5. A candidate manifest records source coverage, artifacts, hashes, and method versions.
6. Maintainers may publish by changing the active pointer only after every release gate passes. Pass B statistical and outcome-authenticity remediation is implemented internally, but candidate and published releases remain deliberately blocked until an independent re-audit accepts it.

The public applications are read-only. Cached historical responses may be served while an official source is unavailable, with the selected release and freshness visible to readers.

## Source precedence

Final declarations and legally valid scrutiny control only the totals and geographic grain they actually publish. E-14 forms remain documentary evidence. Registraduría pre-count data remains preliminary. First-round and historical results are context only.

No final mesa value is inferred from a higher-grain source. Unknown, unavailable, and observed zero values remain distinct through ingestion, storage, API serialization, and rendering.

At this pre-count mesa source, registered electors are unavailable: `centota=0` with positive voters is an unavailable sentinel, not an observed zero. Turnout and an elector bound are therefore never inferred. The full-scope mesa crawl is resumable and runs at 2 requests per second per host, with protocol retries and no keepalive connections. Full scope means each planned identifier is attempted, not that every mesa is retrieved or that coverage is 100%; department, municipality, and zone aggregate collection is implemented but does not run concurrently with it.

Outcome sensitivity requires trusted content-addressed source facts, two registry-authorized and fact-bound reviews for verified affected records, and an observed compatible-grain total. Unresolved records may enter only as explicit authenticated compatible-grain bounds; otherwise the result is `not_evaluable`. A two-vote margin shift per affected vote is the default, and any smaller bound needs authenticated fact support plus a machine-verifiable certificate. Statistical screening never contributes verified affected votes. Peer, spatial, and outcome calculations remain experimental and cannot satisfy candidate or publication gates before the independent re-audit.

## Privacy boundary

Known E-14, E-24, E-26, and CNE declaration references are indexed as official external links only. The release stores canonical identifiers, source-index URL/hash, timestamps, status, and coverage. It never downloads, caches, proxies, OCRs, redacts, extracts, transcribes, or serves election-document bytes. No relative document reference is expanded into a URL.
