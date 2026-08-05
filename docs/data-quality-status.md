# Estado de calidad de datos / Data-quality status

**Audit snapshot / corte de auditoría:** `2026-08-04T05:14:02Z` (UTC). This is a
read-only, point-in-time audit; it is not a release approval and it never means
that a crawl is complete.

## Resultado / outcome

| Área / area                            | Resultado                    | Evidencia breve / short evidence                                                                                                                                                    |
| -------------------------------------- | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Historical 2022 v2 immutable candidate | PASS (candidate only)        | Raw source and all four generated files matched their recorded SHA-256 and byte sizes; a separate rebuild was byte-identical and its second invocation was `no_op: true`.           |
| Historical expected coverage           | CAVEAT                       | `103364` mesas per round is the observed ZIP snapshot scope, **not** an independently verified national expected-mesa denominator.                                                  |
| Manifest schema and pointer            | PASS                         | 9 repository `data/manifests/*.json` files (including pointer) and 2 local R1 candidates validate; active pointer is the synthetic fixture.                                         |
| R1 scrutiny raw classification         | COMPLETE (metadata only)     | Exact official manifest retrieval is `23,828/23,828`, with zero missing/quarantined. The offline schema classification has zero result facts; it is not a legal/final result parse. |
| R1/R2 pre-count and R2 scrutiny        | IN PROGRESS                  | R1/R2 mesa plans and the R2 scrutiny ledger remain incomplete at this point-in-time snapshot.                                                                                       |
| Public wording / wording público       | PASS                         | Node 22 gate checked 115 reader-facing files and found no prohibited fraud-probability wording.                                                                                     |
| Repository hygiene / higiene           | PASS*, but non-authoritative | Existing gate exited 0, but `git ls-files` is empty in this checkout: the entire worktree is untracked, so its tracked-file check is vacuous.                                       |

## 2022 historical candidate v2

Release: `historical-2022-mmv-context-v2-705d3d71523003b8` (`candidate`,
non-active, non-synthetic, `contextual_baseline` / `context_only`). It must not
be represented as pre-count, scrutiny, or a final declaration.

| Item                    | SHA-256                                                            |     Bytes |          Rows |
| ----------------------- | ------------------------------------------------------------------ | --------: | ------------: |
| Raw ZIP round 1         | `52443174bbe5c09d73a1b0538a1a9ae5f78afb934c7b8f98f93ea52b41872769` | 5,064,481 | source object |
| Raw ZIP round 2         | `175ad5884ee6aceb9fb36782990c2bbabb0a4f2c84e41dbbcc74c824816c1b61` | 2,933,014 | source object |
| MMV Parquet             | `85065bec750991d1fbff47eb02372b9b7e23fa4110e2088287e1cdda561f0d69` | 7,031,308 |     1,125,896 |
| Derived rollups Parquet | `4d599c00310b2174476066335cc684a8c15b0d8920a335d1ce969ff007b4098b` | 4,783,526 |     1,349,277 |
| Geography Parquet       | `7b8eab28da2027f23f7247f5a7dc90c3c4df6d08c9b06f07f0c59a55853744e4` | 1,040,721 |       241,652 |

Footer counts and frozen national controls agree: round 1 has 727,510 rows,
103,364 distinct mesas and 21,442,300 votes; round 2 has 398,386 rows,
103,364 mesas and 22,689,034 votes. Geography per round is 34
department/exterior codes, 1,188 municipalities, 2,978 zones, 13,261 polling
places, and 103,364 mesas (plus one national node). Categories are sparse: R1
has 11 categories and R2 has 5; absent category rows mean unavailable/unknown,
never inferred zero. The corresponding 2022 source coverage is one reviewed
ZIP per round (`expected=retrieved=parsed=1`); it deliberately does **not**
turn the observed mesa count into expected national coverage.

The rebuild used the frozen raw object store, `git_commit`
`frozen-control-2026-08-04`, and a separate `/tmp` destination. All existing
v2 outputs and manifest compared identical; the second build reported
`installed:false, no_op:true`. Deterministic behavior is also covered by the
historical ingest test suite.

### 2022 mesa-count caveat

A read-only comparison of the preserved MMV ZIPs to Registraduría's
[pre-election census](https://www.registraduria.gov.co/La-Registraduria-Nacional-entrega-detalles-del-censo-electoral-en-Colombia-y-en)
finds 103,364 distinct five-code MMV identities in each round, versus the
census's 102,152 installed mesas. The exact split is 100,812 domestic and 2,552
exterior MMV identities, versus 100,809 and 1,343 in the census; the 1,212
difference is three Bogotá identities plus 1,209 Consulados identities. Raw and
Parquet identity counts agree, zero-padding creates no collisions, and there
are no `000` or non-decimal mesa codes or duplicate semantic facts. The rounds
share 103,295 identities and each has 69 exterior-only differences. This found
no parser defect, but it does **not** establish extra physical mesas or a
coverage denominator: the published MMV exterior hierarchy is not one-to-one
with the census hierarchy. See [the complete audit](2022-source-completeness-audit.md).

## Manifests, pointer, and retention

All repository manifests and both local R1 candidates conform to
`release-manifest.schema.json` using a local offline schema registry; the
pointer requires `release_id`, `manifest_path`, `activated_at`, and `synthetic`
and resolves to the matching `fixture-2026-round2-v1.json`. The active pointer
is therefore a synthetic fixture, explicitly not an election-data publication.

The six R2 candidates are `candidate-2026-r2-{18fd226ffeac1607,
516ac54cfa725ff7,6d0f82df48439229,7dcb23d2e13b626a,b657eb58e613516a,
bfbf46cb23cb57a3}`. Each is a stale/incomplete national-pre-count snapshot:
three datasets with one record each, `aggregate_reconciled=false`,
`statistical_validation_passed=false`, `wording_validation_passed=false`,
scrutiny `1/22876` parsed and final declaration excluded (`1` excluded).
They are not referenced by `current-release.json`; each has a same-named local
`data/releases/.../api-snapshot.json` only. **Recommendation:** retain as
immutable forensic candidates but quarantine from any release-selection/UI
inventory until regenerated from a completed ledger; do not delete or activate.

Two R1 candidates reside only under
`.pipeline/official-2026-round1/candidate-manifests/`:
`candidate-2026-r1-3ba1fd6266c2c8a2` and
`candidate-2026-r1-ade35bb72db8c17d`. Both contain only the national pre-count
ACT (one record per dataset), state that mesa/scrutiny/final work is incomplete,
and are unreferenced by the active pointer. **Recommendation:** retain and
quarantine alongside the R2 candidates; they are stale relative to the active
R1 crawl.

The old `historical-2022-mmv-context-v1` is schema-valid, locally present, and
superseded/unreferenced by the hardened v2 identity. Retain/quarantine it as
legacy provenance; do not activate or rebuild into its fixed path.

## Collection ledgers / libros de recolección

Counts below are snapshots at the audit timestamp. `planned` is the plan
denominator; `parsed` is only what has completed so far. `pending` and
`unclassified` are explicitly not completion states.

| Round / source                 | Planned | Parsed / retrieved | Missing | Ambiguous | Quarantined |                                Pending / unclassified |
| ------------------------------ | ------: | -----------------: | ------: | --------: | ----------: | ----------------------------------------------------: |
| R1 pre-count national (sample) |       1 |                  1 |       0 |         0 |           0 |                                                     0 |
| R1 pre-count places            |  14,438 |             14,438 |       0 |         0 |           0 |                                                     0 |
| R1 pre-count mesas             | 122,020 |             13,835 |       0 |         0 |           0 |                  108,185 expected URLs not yet parsed |
| R2 pre-count national          |       1 |                  1 |       0 |         0 |           0 |                                                     0 |
| R2 pre-count places            |  14,438 |             14,438 |       0 |         0 |           0 |                                                     0 |
| R2 pre-count mesas             | 122,020 |             19,904 |       0 |         2 |           0 |                  102,114 expected URLs not yet parsed |
| R1 scrutiny (raw retrieval)    |  23,828 |         0 / 23,828 |       0 |         0 |           0 | 23,828 schema-classified; **0** election-result facts |
| R2 scrutiny                    |  22,876 |         0 / 13,314 |       0 |         0 |           1 |                                         9,561 pending |

Known R2 mesa defects are exactly two reused official objects that could not be
decoded: `.../ACT/PR/010011802000033.json` (at `02:39:52Z`) and
`.../ACT/PR/010013103000003.json` (at `02:56:52Z`). The R2 scrutiny quarantine
still contains one transient `HTTP 503` object (attempt 1, `03:51:39Z`):
`.../actas_documentos_001_25_001_07_04_mesas_20260621_210037_946.json`.

R1 scrutiny is the exception: its completed raw crawl was classified offline
into immutable snapshot `scrutiny-classified-6055c63044595e4f` at
`scrutiny-classification@2`. Its 13 observed schema variants had zero unknown
keys. The classifier safely retained 118,343 explicit acta document references
with source URL/path/content-hash provenance; it neither fetched those
references nor OCRed E-14s, and it emitted **zero** vote/result facts. The
remaining seven published acta rows had an empty document reference and were
not indexed. This is a document/operational-metadata classification, not a
parsed scrutiny result, final declaration, or legal publication.

At this timestamp R2 pre-count is still incomplete: its full mesa plan has
19,904 parsed items, 2 ambiguous reused objects, and 102,114 remaining expected
URLs. Its places and national plans are complete, but that does not complete the
round. R2 scrutiny is also live and incomplete: 13,314 raw JSON objects are
unclassified, 9,561 entries are pending, and one object remains quarantined for
retry. These are read-only status counts, not a completion declaration.

For the mesa plans, `Missing=0` means only that no URL has a terminal
`missing` classification yet. It does **not** mean complete coverage: 108,185
R1 and 102,114 R2 expected mesa URLs had not yet parsed at this snapshot (the
R2 remainder excludes its two already-classified ambiguous JSON objects).

## Provenance and legal-role separation

Both source catalogs exist with HTTPS allowlists, conditional/raw-before-parse
policy, configuration+nomenclator+nation/mesa pre-count entrypoints, scrutiny
index, E14 evidence endpoints, and CNE declaration entries. Root source-object
evidence is preserved: R2 config `6cf568…d7ab5` (931 B), nomenclator
`5bcced…24f5a` (2,561,335 B), and scrutiny index `051e54…9c423` (2,668,746 B);
R1 reports record its config/nomenclator roots as well. The manifest validator
maps legal status strictly: `pre_count→preliminary`,
`scrutiny→official_scrutiny`, `final_declaration→controlling_final`, and
`contextual_baseline→context_only`. No inspected manifest promotes pre-count,
scrutiny, or historical context into another legal role.

## Commands run / comandos ejecutados

```sh
uv run elecciones-pipeline historical-2022-build \
  --state-dir .pipeline/historical-2022 \
  --release-root /tmp/elecciones-historical-audit.YzRV8J/releases \
  --manifest-dir /tmp/elecciones-historical-audit.YzRV8J/manifests \
  --git-commit frozen-control-2026-08-04
# byte comparison of all four outputs and manifest; repeat returned no_op:true

mise x node@22 -- pnpm check:manifests
mise x node@22 -- pnpm check:wording
mise x node@22 -- pnpm check:repository-hygiene
uv run pytest -q pipeline/tests/ingest/test_historical_2022.py \
  pipeline/tests/ingest/test_precount.py pipeline/tests/ingest/test_precount_crawl.py \
  pipeline/tests/ingest/test_scrutiny.py pipeline/tests/ingest/test_scrutiny_crawl.py \
  pipeline/tests/releases/test_release_exports.py \
  pipeline/tests/releases/test_candidate_release.py pipeline/tests/releases/test_snapshot.py
# 97 passed, 5 third-party deprecation warnings
```

The three Node gates passed under `mise x node@22` (`v22.23.1`). A direct PII-like scan of
the public data/docs/web-output scope found no email, Colombian phone, or
identifier-like matches; the only regex hit was the non-PII decimal
`completion_percent`. The wording gate found no prohibited probability-or-finding
phrases under its bilingual policy.

## Remaining release blockers / bloqueadores

1. Finish and reconcile R1/R2 mesa and scrutiny crawls; resolve the two R2
   malformed mesa JSONs and retry/classify the R2 503 object.
2. Complete human double entry/verification of the CNE final declaration and
   include it only with its controlling-final role.
3. Produce a fresh candidate from the completed immutable ledgers; run aggregate,
   statistical, wording, and independent pass-B release gates before any activation.
4. Restore a real Git index/commit before relying on repository-hygiene as a
   checked-in-artifact control.
