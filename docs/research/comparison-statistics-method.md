# Comparison statistics — method

What the comparison section publishes, how each number is produced, and what
each one can and cannot support.

Producer: `scripts/compute-comparison-statistics.py`
Output: `data/derived/comparison-statistics-2026.json`
Input: `data/releases/candidate-2026-r2-dacb28aa766eec87/api-snapshot.json`
(122,020 mesa-level result facts, preliminary preconteo, release status
`candidate`)

Every statistic in the output document carries the exact number of input rows it
was computed over. The document also carries a `sha256` of the input snapshot
and of its own payload, so any figure can be recomputed from the release alone.

**None of these statistics is a test for fraud, and none is presented as one.**
They are descriptive properties of a published tally. Each has a null
distribution that ordinary elections violate for ordinary reasons.

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
would otherwise compute it themselves. It carries no finding.

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

**What it can indicate.** How often a mesa's candidate votes are concentrated
entirely on one side.

**What it cannot indicate.** Unanimity is an expected outcome of small mesas and
homogeneous localities, not a departure from one. A mesa with four candidate
votes is unanimous under a wide range of ordinary conditions. The rate is not
comparable across elections with different mesa-size distributions, and no
threshold on it separates ordinary from irregular. It is a shape statistic about
the distribution of mesa sizes and local homogeneity.

---

## 3. Margin decomposition across departments

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

**Turnout is not computed at department or mesa grain.** `registered_electors` is
`unavailable` on 122,008 of the 122,020 mesa facts. No denominator exists at
those grains, so none is published. The national turnout figure comes from the
national result fact, which does carry an observed elector count.

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
computed, not stored, and not displayed.

---

## Reproducing

```
.venv/bin/python scripts/compute-comparison-statistics.py
```

The script reads only the pinned release snapshot and writes only
`data/derived/comparison-statistics-2026.json`. Re-running against the same
snapshot reproduces the same `document_sha256`.
