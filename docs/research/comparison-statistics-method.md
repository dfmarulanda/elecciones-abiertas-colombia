# Comparison statistics — method

What the comparison section publishes, how each number is produced, and what
each one can and cannot support.

Producer: `scripts/compute-comparison-statistics.py`
Output: `data/derived/comparison-statistics-2026.json`

Inputs — all three second rounds, measured through one identical code path:

| year | artifact | rows | stage |
| --- | --- | --- | --- |
| 2018 r2 | `historical-2018-mmv-context-v2-…/historical-2018-mmv.parquet` | 383,131 | MMV mesa annex |
| 2022 r2 | `historical-2022-mmv-context-v2-…/historical-2022-mmv.parquet` | 398,386 | MMV mesa annex |
| 2026 r2 | `candidate-2026-r2-dacb28aa766eec87/api-snapshot.json` | 122,020 mesa facts | preconteo |

Every statistic in the output document carries the exact number of input rows it
was computed over. The document also carries a `sha256` of each input artifact
and of its own payload, so any figure can be recomputed from the releases alone.

**None of these statistics is a test for fraud, and none is presented as one.**
They are descriptive properties of a published tally. Each has a null
distribution that ordinary elections violate for ordinary reasons.

---

## 0. Why three years, and what bounds the comparison

A single year's value for either statistic is uninterpretable: there is no
published reference distribution for "what the last-digit χ² of a clean
presidential second round should be". The only usable reference is the same
measurement, by the same code, on earlier elections. So both mesa-grain
statistics are computed for 2018 r2, 2022 r2 and 2026 r2 and emitted together.

Only the loader differs between years, because the sources differ in format. The
statistic functions are shared, take the same per-mesa candidate-vote structure,
and are applied to all three years without branching.

Four things bound every cross-year reading, and they travel with the numbers in
the JSON's `comparability` block:

- **Stage mismatch.** 2026 is the **preconteo** — the election-night preliminary
  count. 2018 and 2022 are the **MMV mesa annex**, a later and different stage.
  These are not the same instrument measured three times.
- **Legal status mismatch.** The 2018 and 2022 artifacts are marked
  `source_type: contextual_baseline` and `legal_status: context_only`. They are
  context for the 2026 preliminary figures, not a certified series.
- **Zero-encoding mismatch.** 2026 records every candidate cell explicitly,
  including zeros. The MMV annex is sparse: a candidate with zero votes generally
  has no row at all (2018 contains **no** explicit zero candidate rows in 383,131
  rows; 2022 contains 89). A unanimous mesa in 2018/2022 is therefore identified
  by the *absence* of the losing candidate's row rather than by an explicit zero.
  The two encodings resolve to the same quantity but not on the same evidence,
  and the unanimous-mesa rate is the statistic this affects.
- **Unresolved release anomalies on the exterior.** `findings-ledger.md` §2.12
  records that the 2018 MMV exterior is short 13–17 mesas against the official
  installed universe (R1 exterior 2,423 vs 2,436 official; R2 exterior 2,419), so
  any longitudinal exterior series must carry a ±13–17 mesa band on the 2018
  points. §2.7/§2.12 record that the 2022 MMV exterior carries 2,552 mesa
  identities against the 1,343 census-installed exterior mesas reported at the
  time. **Neither anomaly is resolved**, and neither is corrected here.

---

## 1. Last-digit uniformity

**What it is.** A Pearson chi-square of the last decimal digit of each mesa's
per-candidate vote count against a uniform 1/10 expectation. Nine degrees of
freedom; the critical value at α = 0.05 is 16.919.

**Denominator.** Only mesa candidate counts of **at least 10**. Below 10 the
last digit *is* the count, so the digit distribution is the distribution of very
small mesa totals and is non-uniform by construction — a mesa with 3 votes can
never show last digit 7. Ten is the smallest floor at which all ten digits are
attainable. A floor of 100 is computed alongside it as a sensitivity check, not
as the headline.

The two candidates' counts within one mesa are bounded by the same valid-vote
total and are therefore not independent. The per-candidate statistics are the
primary reading; the pooled figure understates its own variance and is
descriptive only.

**Measured, floor of 10, pooled across both candidates:**

| year | rows | χ² | exceeds 16.919 | largest digit-share deviation |
| --- | --- | --- | --- | --- |
| 2018 r2 | 189,132 | 30.174 | yes | 0.20 pp |
| 2022 r2 | 199,999 | 55.718 | yes | 0.25 pp |
| 2026 r2 | 237,753 | 35.518 | yes | 0.27 pp |

**This is the single most important row in this document: the statistic exceeds
its critical value in all three years, including two elections whose outcomes are
not in dispute.** 2026 falls between 2018 and 2022. Per candidate, the one series
that does *not* exceed the threshold is Duque in 2018 (χ² 10.068, p = 0.345),
while his opponent's series in the same undisputed election reaches χ² 35.406 —
a spread within one election larger than the spread across the three.

**What it can indicate.** Whether the recorded counts' terminal digits depart
from uniform. That is all.

**What it cannot indicate.** It cannot indicate that a departure is
irregular, and it cannot indicate that its absence means the counts are correct.
Two limits dominate here:

- **Power, not effect size.** At roughly 118,000 rows per candidate the test
  resolves deviations far too small to interpret. In this release the largest
  single-digit deviation at the floor of 10 is **0.27 percentage points** — every
  digit share falls between 9.7% and 10.3% — and the statistic still exceeds the
  critical value. A significant result at this sample size is a statement about
  the number of rows, not about the size of the departure.
- **Support boundaries.** Uniformity of the last digit requires the count
  distribution to span whole decades. Mesa sizes are capped by law and cluster in
  a narrow band, so the support ends mid-decade and low digits are structurally
  over-represented. This is visible in the output: at the floor of 100 the
  deviations form a monotone gradient from digit 0 downward to digit 9, which is
  the signature of a truncated support, not of the counts themselves.

Read together, this statistic is reported for completeness and for the reader who
would otherwise compute it themselves. It carries no finding. The three-year
table is the point: a reader shown only 2026's "χ² 35.5, above the 16.9
threshold" would draw a conclusion that the 2018 and 2022 rows immediately
dissolve.

---

## 2. Unanimous-mesa rate

**What it is.** The share of mesas in which one candidate received every
candidate vote cast in that mesa. This is a two-candidate second round, so a
unanimous mesa is one where the other candidate received exactly zero.

**Denominator.** Mesas with at least one candidate vote. Mesas where no
candidate received a vote are excluded — the ratio is undefined there. Blank,
null and unmarked ballots are not candidate votes and are excluded from both the
numerator and the denominator; note that `valid_votes` in this release
**includes** blanks, so it is not the denominator here.

**Measured:**

| year | unanimous | denominator | rate | excluded (zero candidate votes) |
| --- | --- | --- | --- | --- |
| 2018 r2 | 346 | 97,644 | 0.3543% | 1 |
| 2022 r2 | 521 | 103,319 | 0.5043% | 45 |
| 2026 r2 | 765 | 122,006 | 0.6270% | 14 |

Unlike the last-digit statistic, **2026 does not fall between the two earlier
years here** — the rate rises across all three. This is stated rather than
smoothed: the series is monotone increasing over three points. It should not be
read as a trend in anything but itself. The number of mesas grew in each period,
the mesa-size distribution is not held constant across the three, and the
2018/2022 numerators are reached through the sparse-encoding convention above
while 2026's is not. No denominator available here separates those causes.

**What it can indicate.** How often a mesa's candidate votes are concentrated
entirely on one side.

**What it cannot indicate.** Unanimity is an expected outcome of small mesas and
homogeneous localities, not a departure from one. A mesa with four candidate
votes is unanimous under a wide range of ordinary conditions. The rate is not
comparable across elections with different mesa-size distributions, and no
threshold on it separates ordinary from irregular. It is a shape statistic about
the distribution of mesa sizes and local homogeneity.

---

## 3. Margin decomposition across departments — 2026 only

**Not computed for 2018 or 2022, deliberately.** Candidate identity in the MMV
annex is unambiguous — exactly two candidate categories, `001` and `002`, in both
years — so the arithmetic is available. It is withheld because a *cross-stage*
margin decomposition, between the preconteo and the MMV annex, over department
universes carrying the unresolved exterior anomalies in §0, is the same kind of
under-specified comparison that produced the retraction recorded in
`method-record.md` item 16. The 2026 decomposition stands alone and is labelled
as such in the JSON.

**What it is.** For all 34 departments: valid votes, each candidate's votes, the
department's internal margin (winner minus runner-up within that department),
that margin as a share of the department's own valid votes, and the department's
contribution to the national margin as a percentage. All 34 are then ranked.

**Denominator and derivation.** Department totals are **sums of the release's own
mesa-level result facts**. This release publishes result facts at mesa,
polling-place and national grain only — there is no department-grain published
figure, and these rollups must never be presented as one. The derived national
totals reconcile exactly with the published national result fact
(`precount-national-00`): delta of 0 on both candidates and on the margin.

Two rankings are emitted because two are defensible and they disagree. Ranking
by **absolute** contribution orders departments by the size of their
contribution regardless of direction. Ranking by **signed** contribution counts
only movement toward the national winner, sending the departments the runner-up
carried to the bottom. Both are in the output; neither is privileged.

**What it can indicate.** That in a race decided by a margin small relative to
ballots cast, a large number of departments individually exceed the national
margin. Naming any one of them as decisive is selection on the outcome.

**What it cannot indicate.** Nothing in this decomposition speaks to how any vote
was cast or recorded. A department's share of the national margin is a property
of the national margin's size, not of that department.

**Turnout is not computed at department or mesa grain, in any year.**
`registered_electors` is `unavailable` on 122,008 of the 122,020 2026 mesa facts,
and the MMV annex carries no elector column at all. No denominator exists at
those grains in any of the three sources, so none is published. The national
turnout figure comes from the 2026 national result fact, which does carry an
observed elector count.

---

## 4. Why no Benford statistic is computed

`docs/research/method-record.md` §7.1 records the absence of any Benford test in
this repository as a deliberate and correct choice. This section states the
reason so the absence is not read as an oversight.

Benford's law describes the leading digits of quantities spanning several orders
of magnitude with a scale-invariant distribution. Vote counts per precinct do not
have that shape. Mesa sizes here are administratively bounded and concentrated in
a narrow band, so the leading digit is determined mostly by where that band sits
relative to the nearest power of ten. A conforming result and a non-conforming
result would both be artifacts of the mesa-size distribution, and the same tally
partitioned at a different grain would give a different answer.

Benford is the most misused instrument in election forensics precisely because it
produces a confident-looking number on data that does not satisfy its
assumptions. Publishing one here would put a statistic in front of readers that
cannot bear the interpretation its presence invites. It is therefore not
computed, not stored, and not displayed — for 2018 and 2022 either. Running it
across three years would not rescue it: a three-year table of a statistic whose
assumptions none of the three satisfy is three invalid numbers, not a control.

---

## Reproducing

```
.venv/bin/python scripts/compute-comparison-statistics.py
```

The script reads only the three pinned release artifacts and writes only
`data/derived/comparison-statistics-2026.json`. Re-running against the same
artifacts reproduces the same `document_sha256`.

The critical value is derived once from `scipy.stats.chi2.ppf(0.95, 9)` and
referenced everywhere it is needed, rather than written as a literal in more than
one place. `method-record.md` §7.2 records what the duplicated-constant pattern
cost the last time: the same bound written two ways differed by one ULP and made
two modules disagree on 27,931 of ~80,000 pairs.
