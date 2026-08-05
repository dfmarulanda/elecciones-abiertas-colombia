# Method record

How the findings in this directory were produced: what was run, how many times,
who checked it, and what was found to be wrong.

This document exists because a finding about a real election is only as good as
the account of how it was obtained. A reader who distrusts the conclusions should
be able to reconstruct or attack every step from here.

**Nothing in this investigation asserts fraud, or its absence.** Anomaly is not
evidence. Absent provenance is not alteration. A negative result from a weak
instrument is weak evidence.

---

## 1. Evidence tiers

Every claim in `findings-ledger.md` carries one of these. They are not
interchangeable.

| tier | meaning |
| --- | --- |
| **A — directly re-derived** | Measured from the primary artifact by a query written for that purpose, then re-run independently by a fact-checking agent that did not see the first query. |
| **B — measured once** | Measured from the primary artifact, not yet independently re-derived. |
| **C — relayed** | Produced by an analysis agent and not independently reproduced. Carries the least weight and is always marked. |

A tier-C claim has never been treated as established, however confident its
phrasing in an agent's report.

---

## 2. Multi-agent review

Eight orchestrated workflows, run in parallel where independent. Each spawned
agents with distinct analytical lenses, and the adversarial phases were
instructed to **refute** rather than improve — defaulting to "refuted" when a
defect could not be concretely traced.

| workflow | agents | purpose | outcome |
| --- | ---: | --- | --- |
| stats-council-review | 16 | statistical system, 5 lenses + adversarial verify | 4 of 10 findings survived refutation |
| stats-council-round-2 | 19 | modules round 1 under-examined | 1 of 12 survived; 11 refuted |
| claims-register-design | 6 | how to answer a public claims document | corrected 4 briefing errors |
| public-claims-harvest | 5 | neutral harvest of public claims | 63 claims; corrected 3 premises |
| fraud-question-design | 13 | research design for the fraud question | 43 proposals, 6 attacked |
| e14-deep-forensics | 6 | PDF forensics (Fable) | identified toolchain; found the `/ID` timestamp |
| ultracode-factcheck | — | independent re-derivation of every claim | in progress |
| historical-artifact-hunt | — | acquire 2018/2022 controls | in progress |

**65 agents completed** across the six finished workflows, ~5.4M subagent tokens
and ~1,790 tool calls. Agent count is a measure of scrutiny applied, not of
confidence: the two councils exist because the *first* answers were wrong often
enough to justify them.

Refutation rates matter more than totals. Round 2 killed **11 of 12** findings.
A review process that confirms everything it is shown is not a review process.

---

## 3. Measurements performed

| measurement | scale | tier |
| --- | --- | --- |
| 2026 pre-count collection | 244,040 / 244,040 mesas, both rounds, SHA-256 per object | A |
| Mesa→place reconciliation, ballot quantities | 14,438 / 14,438 places, both rounds | A |
| Mesa→place reconciliation, candidate votes | 14,438 / 14,438 places | A |
| Exterior stratum (dept 88 = CONSULADOS) | 3,670 mesas, 614,095 voters, margin 177,809 | A |
| E-14 index coverage | 118,343 R1 / 118,308 R2; 33 dept codes; **no dept 88** | A |
| E-14 PDF metadata probe | 100 documents, `pypdf`, positive control | A |
| E-14 deep forensics | ~138 documents, 5 angles | B/C |
| `/ID` → epoch-ms timestamp inversion | agents: 45; **independently reproduced by hand: 1** | B |
| Forensic screens, 3 elections, identical code | 323,027 mesas total | B |
| Tail calibration under a correct null | 300,000 replications per cell | A |
| Full release simulation profile | 2,000 runs | A |
| Historical exterior comparison | 2018 and 2022, both rounds | A |

Sampling limits that bound every PDF statement: **100 of 236,651 documents
(~0.04%)**, drawn from the auditor/bulk channel only. The citizen-viewer channel
— where the disputed "candado hash" is generated — was never tested.

---

## 4. Corrections

Errors found and fixed during the work. This section is the most important one in
the document; an investigation that reports no self-corrections has not looked.

**Method errors caught before they reached a conclusion**

1. Summed a not-available sentinel (`absten = 0`) as an observed zero, producing
   4,392 phantom "mismatches" — the precise error this project's architecture
   exists to prevent, committed by its own investigator.
2. Double-counted mesas from a stale 36-mesa sample plan left in the round-2 store.
3. Sliced geography with a `[:9]` prefix, silently skipping 10,044 places with
   variable-length codes.
4. Detected PDF metadata by raw byte scan; `%PDF-1.6` object streams can hide
   `/Info`. Re-done with `pypdf` — the finding held, the method had not.
5. Wrote a regression test whose scenario never fired (the spatial family was
   never flagged), so it passed vacuously. Rewritten to force the condition.
6. Reported route fixes against a build that a Turbo cache hit had never rebuilt,
   and against a stale server holding port 3000.
7. Computed the exterior's share of the national margin from absolute values,
   concealing that in 2022 it ran **opposite** to the national winner (−10.3%,
   not +8.5%).

**Wrong conclusions stated to the owner, then corrected**

8. Attributed a Railway deploy failure to vendor infrastructure. It was
   `service config at '/railway.toml' not found` — a config error in this repo,
   found only when the owner supplied a dashboard screenshot.
9. Stated the 2018 municipality catalogue "does not exist". It exists, at a known
   Registraduría URL, on a host already allowlisted in the relay.
10. Said mesa→place reconciliation might miss candidate-level movement. It does
    not — candidate votes reconcile too. The real limitation is different and
    worse: both layers derive from one publisher ledger, so power against
    transcription-layer alteration is **0.000**, not merely low.
11. Called the `centota` sentinel handling "a real defect" and changed the ingest
    layer. A test documented the opposite intent — faithful ingest, interpretation
    downstream. Reverted.
12. Stated there was "no registered-voter denominator at any grain". One exists at
    municipal grain (pinned Registraduría census, 41,421,973).
13. Wrote "Launching the deep research" and ended the turn without launching
    anything. Caught by the owner.

**Corrections originating from agents, applied to the investigator's own claims:**
items 10, 12, and the understatement of ballot-identity coverage (reported as
4,000 sampled; actually verified across all 244,040).

---

## 5. What the method cannot reach

- **The transcription link.** Nothing here compares a published number to the
  number written on the corresponding E-14. That comparison requires reading the
  forms; no OCR or human entry has been done. It is the single most important
  unmeasured link.
- **The physical link.** Ballots, custody records, and any recount are outside
  reach entirely.
- **The 2018/2022 document control.** Direct access blocked; no static paths on
  the 2022 host; zero PDF captures in Wayback; the query form is CAPTCHA-gated
  and was deliberately not circumvented.
- **Turnout-based screens.** No registered-voter denominator exists at mesa
  grain, which excludes the more informative forensic family.

---

## 6. Reproducibility

All code is committed. Every measurement above can be re-run from the primary
stores in this repository, except the live PDF probes, which depend on the
Registraduría hosts remaining reachable. Test suite: **391 tests**, `ruff` and
`mypy` clean. 17 commits.

Third-party network access is recorded, including a route through the project's
own Railway relay used to reach hosts unreachable from the workstation. No access
control was bypassed at any point.
