# 2018–2022 geography crosswalk: evidence

**Audit snapshot:** 2026-08-05 (UTC). Read-only. This is evidence gathered for
the `verified_geography_crosswalk_required` blocker in
`analytics/longitudinal.py`. It is **not** an approval, and it does not lift
that blocker.

## Why the DANE DIVIPOLA 2018 capture cannot fill the gap

`.pipeline/research/longitudinal/source-discovery/dane-divipola-2018-capture.json`
holds an official DANE 2018 municipality catalogue (1,122 municipalities plus
20 non-municipalised areas). All seven captured assets verify against their
recorded SHA-256 and byte sizes.

It cannot supply 2018 election labels. The capture says so itself — *"not a
Registraduría electoral-code crosswalk"* — and the join confirms it
empirically: **0 of 308 sampled 2018 election municipality codes appear in the
DANE catalogue**.

The two systems are unrelated numberings. DANE encodes Medellín as `05001`
(department `05`, municipality `001`). The election data encodes departments as
`01`, `03`, `05`, `07`… and municipalities as `001`, `004`, `007`… — a
Registraduría numbering in which `01` is not DANE's `01`. Bridging them needs
an official DANE↔Registraduría mapping, which this repository does not hold.

## What the election releases actually share

All three elections use the **same Registraduría code system**:

| election | department codes | municipality codes | labels |
| --- | --- | --- | --- |
| 2018 | `01`, `03`, `05`, `07`… | `001`, `004`, `007`… | **absent** (generated placeholders) |
| 2022 | `07`=BOYACA, `24`=RISARALDA, `88`=CONSULADOS | `001`=BUCARAMANGA, `325`=VILLAPINZON | present |
| 2026 pre-count | `01` … | place scope `010010101` | n/a at this grain |

Round-1 municipality identity, compared as `(department_code, municipality_code)`:

| | count |
| --- | ---: |
| 2018 pairs | 1,191 |
| 2022 pairs | 1,188 |
| **shared** | **1,187 (99.7% of 2018)** |
| only 2018 | 4 |
| only 2022 | 1 |

## The five exceptions

| direction | department | municipality | note |
| --- | --- | --- | --- |
| 2018 only | `50` GUAINIA | `050` | **the only domestic exception** |
| 2018 only | `88` CONSULADOS | `320` | extraterritorial |
| 2018 only | `88` CONSULADOS | `405` | extraterritorial |
| 2018 only | `88` CONSULADOS | `415` | extraterritorial |
| 2022 only | `88` CONSULADOS | `445` HUNGRIA | extraterritorial |

Four of the five are consulates, which `build_municipality_crosswalk` already
classifies `extraterritorial` and excludes. **One domestic code — Guainía
`050` — is the entire domestic residual.**

## What this does and does not establish

It establishes that the structural gap between 2018 and 2022 is one domestic
municipality code, not a systemic mismatch.

It does **not** establish municipality identity. A shared code is not proof
that code `05`/`001` denoted the same municipality in both years; codes are
reused and reassigned, which is exactly why
`historical_geography_adapter_contract` sets `code_only_bridge_allowed: false`
and `2022_or_2026_labels_may_backfill_2018: false`. Backfilling 2018 from 2022
labels would assume the conclusion.

## What would lift the blocker

One of:

1. An official **2018-vintage Registraduría** municipality catalogue carrying
   labels against the Registraduría codes — this is the direct fix, and it is
   the artifact currently missing.
2. An official **DANE↔Registraduría** code crosswalk, which would make the
   already-captured DANE 2018 catalogue usable.

Either way, Guainía `050` needs an explicit disposition, and the four
consulate changes need recording as extraterritorial open/close rather than
municipal split/merge.
