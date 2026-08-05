# Hierarchical peer reference (research preview)

`hierarchical_peer_signals_research_preview` is a deterministic research
artifact for comparing one mesa's binomial metric with nested geographic peers.
It is deliberately separate from `peer_signals` and can never create public
priority points.

## What it calculates

For each metric/candidate family it uses the correct binomial denominator:

| Metric | Numerator | Denominator |
| --- | --- | --- |
| turnout | ballots | registered electors |
| candidate share | candidate votes | valid votes |
| blank | blank votes | valid votes |
| null/unmarked | null/unmarked votes | ballots |

Rows need at least 80 denominator units. A department needs at least 30 other
eligible mesas before the model returns a reviewable prediction. A polling
place effect is used only if the polling place has at least 10 eligible mesas;
otherwise the prediction ends at municipality (or department when it has no
municipal peer).

The family-wide beta-binomial hyperprior is fit by SciPy marginal-likelihood
MLE. Its mean is then carried down as a bounded-strength beta prior through
department, municipality, and, where allowed, polling place. At each level,
only the child evidence is added; parent-child overlap is excluded so votes
are not counted twice. Integrating the final beta posterior produces a
beta-binomial predictive distribution. The output contains its expected rate,
95% discrete interval, two-sided discrete tail probability, standardized
predictive residual, and absolute effect in percentage points.

## Leave-one-out and diagnostics

The target mesa is removed from all local evidence. A scalable first pass uses
a fixed full-family hyperprior but LOO local sufficient statistics. Cases with
screening p <= 0.01, an effect above the metric gate (8pp for turnout/candidate
share; 3pp otherwise), or at least 1% exposure influence receive an exact
hyperprior MLE refit with the target removed. `loo_refit_status`,
`convergence_status`, and `influence_diagnostic` state which path was used.

Only exact, converged reference cases can become `research_flag=true`; they
also need p <= 0.001, BY q <= 0.05, absolute standardized residual >= 3.5, and
the applicable effect gate. This is a reproducible review lead, not a finding
of an anomaly or an estimate of affected votes.

## Why this is not a production hierarchical model

The installed NumPy/SciPy stack supports beta-binomial MLE. `statsmodels`
offers a binomial mixed model, but not a beta-binomial nested model with
validated posterior predictive checks, PSIS-LOO, or scalable posterior-chain
diagnostics. This reference therefore uses empirical-Bayes hyperparameters and
does not claim full Bayesian hierarchical inference. It has no PSIS Pareto-k,
chain ESS, or R-hat values.

Before any publication or production use, the project needs a Python 3.13
compatible probabilistic backend, a pre-registered generative model and prior
predictive checks, calibrated simulations using withheld official data, exact
or validated PSIS-LOO diagnostics, and an independent replay/validation path.
Until then its `publication_status` remains
`research_preview_not_for_public_priority` and `public_point_eligible` is
always false.
