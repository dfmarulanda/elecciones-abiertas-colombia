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
| 2026 pre-count collection | 122,020 distinct mesas, observed in both rounds = 244,040 mesa-round records, SHA-256 per object | A |
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
14. Said "244,040 mesas" throughout. The R1 and R2 scope-code sets are
    **identical** — symmetric difference 0. There are 122,020 distinct mesas,
    each observed twice: 244,040 mesa-**round records**. The count was right and
    the sentence doubled the universe. Found by the fact-check pass.
15. Wrote an E-14 PDF to disk (`e14_sample.pdf`, 2,093,173 bytes) while testing
    a parser, violating the handling rule stated in this same document. E-14
    forms carry jurado signatures and cedula numbers. Removed; no PDF remains in
    the workspace. Found by the fact-check pass, not by the investigator.
16. **RETRACTED — the exterior-margin finding.** Reported that the consular
    department (88) carrying 70.9% of the national second-round margin on 2.33%
    of ballots was the investigation's most important result. The comparison set
    was never computed. Measured across all 34 departments, the exterior ranks
    **10th of 34** on share of the national margin and **10th of 34** on
    internal margin rate; department 01 alone accounts for 419.5% of the margin,
    and four of the nine departments exceeding the exterior internally have
    comparable or larger ballot counts. In a race decided by 0.95% of ballots
    every department is arithmetically decisive, so the figure is selection on
    the outcome and does not survive.
    A historical control (exterior across 2018/2022/2026) *was* run and produced
    false confidence: the control required was other strata **within** 2026, not
    the same stratum across time. Running the wrong control is worse than
    running none. Found by the publication council, which computed the
    distribution the investigation had not.

**Corrections originating from agents, applied to the investigator's own claims:**
items 10, 12, and the understatement of ballot-identity coverage (reported as
4,000 sampled; actually verified across all 244,040 mesa-round records).

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

---

## 7. The codebase under review

Everything measured above ran on infrastructure this investigation did not
write. The repository — pipeline, API, web application, contracts and test
suite — was produced by an AI agent (Codex, GPT-5) acting as orchestrator over
roughly two days, before any of the work recorded in sections 1–6 began.

| | |
| --- | ---: |
| Codex sessions touching this repository | 112 |
| of which subagent sessions | 108 |
| distinct agent roles | 107 |
| production source (Python + TypeScript) | 57,405 lines |
| test source | 11,863 lines |

Roles were named per task — `wave1_collector`, `stats_ultra_review`,
`evidence_integrity`, `spatial_simulation_validation`, `adversarial_final_audit`
and a hundred more — each a separate context with its own brief.

**The material fact for anyone weighing these findings: none of it had been
reviewed by a human, and the first release-gate execution happened during this
investigation, not during construction.**

### 7.1 What holds up

Independently verified during this work, and better than the norm for
production election analytics:

- **Beta-binomial rather than binomial** peer modelling, so overdispersion is
  modelled rather than assumed away; exact discrete tails via `betabinom`
  instead of Wald approximations.
- **Benjamini–Yekutieli rather than Benjamini–Hochberg** — the correct choice
  under arbitrary dependence in clustered data. Replayed against
  `statsmodels.multipletests(method='fdr_by')` on 2,000 p-values: **maximum
  absolute difference 0.0**.
- **Non-circular calibration.** The null arm is generated from a model
  deliberately misspecified relative to the detector's own — hierarchical random
  effects, Student-t tails, a 10% out-of-model mixture. This is the correct way
  to gate type-I error, and it means FDR control was already tested under
  clustered, non-exchangeable data.
- **Honest abstention.** `hierarchical_reference` returns
  `inference_status="not_evaluable_hyperparameter_uncertainty"` and withholds z
  and p rather than emitting numbers it cannot stand behind.
- **No Benford test anywhere in the repository** — correct, and unusual.
  Benford is invalid for vote counts with heterogeneous precinct sizes and is
  the most misused instrument in election forensics.
- **Structural refusals that survived adversarial review:** exact integer sums
  with no float in reconciliation; `outcome_sensitivity` making a national
  "the election could flip" figure impossible to emit by construction;
  index-only E-14 handling refusing retrieval, OCR and derivatives at the type
  level; a wording gate blocking fraud-probability language on reader-facing
  pages; and the unknown / unavailable / zero distinction enforced through the
  contract.

Two adversarial review rounds attacked this work. Round two **refuted 11 of 12**
findings against it. The design is substantially sound.

### 7.2 What was wrong

Defects found and fixed during this investigation. Several were latent — real,
but not yet reachable by a production caller.

| defect | consequence |
| --- | --- |
| Unguarded division by zero in `power_by_family` | The release verifier raised instead of failing closed. ~63% probability across a 1,000-run alternative arm. |
| Release gate mathematically unsatisfiable | A hand-written literal required one shape while a byte-exact replay of the analyzer required another. **No artifact could ever pass**, so ~120 lines of verification had never executed. |
| Clopper–Pearson bound duplicated in two modules | `0.025` vs `(1-0.95)/2` differ by one ULP and disagree on **27,931 of ~80,000** (events, trials) pairs. An exact artifact comparison reads that as a forged artifact. Masked by the dead gate above. |
| Power gate computed from the wrong quantity | Per-family counts compared against a per-stratum figure. |
| Permutation seed accepted from the caller, unrecorded | Every reported p-value moved with it while code, method and cohort hashes stayed identical — seed-shopping would have been untraceable. |
| API listing returned a cross product | The 2018 release advertised 2022 elections and vice versa; eight entries where four were correct. |
| Website returned HTTP 500 on five routes | Every deployed build. The pages crashed when no standard release was readable instead of representing that state. |
| Railway service config path never valid | Every deployment failed during initialization, before any build, producing no logs. |
| `data-quality-status.md` stale by ~21 hours | Reported the crawl at a sixth of its actual completion. |
| Test suite red at HEAD | Six failures, from a helper overriding a frozen simulation seed. |

### 7.3 What was not wrong, but was unmeasured

The most consequential result is not a defect. The mesa-level peer screen has
**0.000 power against a shifted whole polling place** — 5,010 injections, zero
detections. It would miss an entire manipulated puesto every time.

That was not a coding error. It is a property of leave-one-mesa-out comparison
that had simply never been measured, because the gate that would have reported
it could not execute. The construction phase built the instrument and the
harness to measure it, and stopped one step short of reading the result.

A replacement cluster-level detector was built during this investigation. On
synthetic tests it is decisively better (0.920 vs 0.620 at 25pp). On real
Antioquia data it fails differently: 70% of polling places have no comparable
peers, so it measures political geography rather than anomalies. Both outcomes
are recorded in the module's own limitations.

### 7.4 Assessment

The construction phase produced a system whose statistical choices are careful
and whose refusals are principled — several of which actively prevented this
investigation from overclaiming. It also produced a governance gate that could
never run, and shipped a detector with zero power against the manipulation class
that matters, without measuring it.

Both facts are the same fact: **the work was rigorous about what it built and
never checked what it had.** That is the specific failure mode of unreviewed
autonomous construction, and it is why the first execution of a release gate
belongs at the start of a review, not the end of a build.
