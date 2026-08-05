"""Deterministic hierarchical empirical-Bayes reference calculations.

This module is deliberately *not* a full Bayesian hierarchical inference
engine.  It provides a small, inspectable research reference based on a
beta-binomial hyperprior fitted by marginal likelihood and conjugate nested
updates.  It is useful for validating a future MCMC/PSIS implementation, but
must not be used to assign production priority points.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import exp, log

import numpy as np
from scipy.optimize import minimize  # type: ignore[import-untyped]
from scipy.special import betaln, digamma  # type: ignore[import-untyped]
from scipy.stats import betabinom  # type: ignore[import-untyped]

_LOG_PARAMETER_BOUNDS = (log(1e-3), log(1e6))
_CHILD_SHRINKAGE_MESAS = 8.0


@dataclass(frozen=True)
class BinomialPeerObservation:
    """An already eligibility-filtered binomial observation."""

    observation_id: str
    department_id: str
    municipality_id: str
    polling_place_id: str
    successes: int
    trials: int


@dataclass(frozen=True)
class ReferenceFit:
    alpha: float
    beta: float
    converged: bool
    boundary: bool
    method: str


@dataclass(frozen=True)
class ReferencePrediction:
    """One conditional beta-binomial posterior-predictive calculation."""

    expected_rate: float
    interval_low: float
    interval_high: float
    discrete_two_sided_p_value: float
    predictive_variance: float
    hierarchy_level: str
    department_peers: int
    municipality_peers: int
    polling_place_peers: int
    loo_refit_status: str
    convergence_status: str
    influence_diagnostic: str


@dataclass(frozen=True)
class MunicipalReferencePrediction:
    """LOMO municipal aggregate estimand, retained as research-only output."""

    municipality_id: str
    mesas: int
    expected_count: float
    predictive_variance: float
    observed_count: int
    standardized_residual: float | None
    approximate_two_sided_p_value: float | None
    loo_refit_status: str
    inference_status: str
    alpha: float
    beta: float
    total_trials: int


def _fit_beta_binomial(observations: tuple[BinomialPeerObservation, ...]) -> ReferenceFit:
    """Fit an exchangeable beta-binomial hyperprior using weighted MLE."""
    if len(observations) < 2:
        raise ValueError("at least two peers are required to fit the reference hyperprior")
    counts = Counter((item.successes, item.trials) for item in observations)
    y = np.fromiter((pair[0] for pair in counts), dtype=float)
    n = np.fromiter((pair[1] for pair in counts), dtype=float)
    weights = np.fromiter(counts.values(), dtype=float)
    total_n = float(np.sum(n * weights))
    total_y = float(np.sum(y * weights))
    mean = min(max((total_y + 0.5) / (total_n + 1), 1e-6), 1 - 1e-6)
    rates = y / n
    variance = float(np.average((rates - mean) ** 2, weights=weights))
    concentration = min(max(mean * (1 - mean) / max(variance, 1e-9) - 1, 1e-3), 1e6)
    start = np.asarray((log(mean * concentration), log((1 - mean) * concentration)))

    def objective(parameters: np.ndarray) -> tuple[float, np.ndarray]:
        alpha, beta = exp(float(parameters[0])), exp(float(parameters[1]))
        likelihood = np.sum(weights * (betaln(y + alpha, n - y + beta) - betaln(alpha, beta)))
        alpha_gradient = np.sum(
            weights
            * (
                digamma(y + alpha)
                - digamma(n + alpha + beta)
                - digamma(alpha)
                + digamma(alpha + beta)
            )
        )
        beta_gradient = np.sum(
            weights
            * (
                digamma(n - y + beta)
                - digamma(n + alpha + beta)
                - digamma(beta)
                + digamma(alpha + beta)
            )
        )
        return -float(likelihood), -np.asarray((alpha_gradient * alpha, beta_gradient * beta))

    result = minimize(
        objective,
        start,
        jac=True,
        method="L-BFGS-B",
        bounds=(_LOG_PARAMETER_BOUNDS, _LOG_PARAMETER_BOUNDS),
        options={"maxiter": 80, "ftol": 1e-10, "gtol": 1e-7},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return ReferenceFit(
            alpha=mean * concentration,
            beta=(1 - mean) * concentration,
            converged=False,
            boundary=False,
            method="smoothed-moment-fallback",
        )
    alpha, beta = exp(float(result.x[0])), exp(float(result.x[1]))
    boundary = any(
        abs(float(value) - bound) < 1e-5 for value in result.x for bound in _LOG_PARAMETER_BOUNDS
    )
    return ReferenceFit(alpha, beta, converged=not boundary, boundary=boundary, method="mle")


def _shrink(parent: ReferenceFit, child: ReferenceFit, child_mesas: int) -> ReferenceFit:
    """Pool fitted *mesa-level* distributions, never vote-count aggregates."""
    weight = child_mesas / (child_mesas + _CHILD_SHRINKAGE_MESAS)
    parent_mean = parent.alpha / (parent.alpha + parent.beta)
    child_mean = child.alpha / (child.alpha + child.beta)
    mean = weight * child_mean + (1 - weight) * parent_mean
    parent_strength = parent.alpha + parent.beta
    child_strength = child.alpha + child.beta
    strength = float(np.exp(weight * log(child_strength) + (1 - weight) * log(parent_strength)))
    return ReferenceFit(
        alpha=mean * strength,
        beta=(1 - mean) * strength,
        converged=parent.converged and child.converged,
        boundary=parent.boundary or child.boundary,
        method="mesa-level-beta-binomial-shrinkage",
    )


def beta_binomial_variance(total_trials: int, alpha: float, beta: float) -> float:
    """Variance after integrating one shared beta latent probability.

    For a municipal total ``Y = sum_i Y_i`` with conditionally independent
    ``Y_i | theta ~ Binomial(n_i, theta)`` and one shared
    ``theta ~ Beta(alpha, beta)``, ``Y`` is beta-binomial with
    ``N = sum_i n_i``.  The ``N²`` contribution retains all cross-mesa latent
    covariance that a sum of marginal variances would omit.
    """
    if type(total_trials) is not int or total_trials < 0:
        raise ValueError("total_trials must be a nonnegative integer")
    if alpha <= 0 or beta <= 0:
        raise ValueError("beta-binomial parameters must be positive")
    concentration = alpha + beta
    return (
        total_trials
        * alpha
        * beta
        * (concentration + total_trials)
        / (concentration**2 * (concentration + 1))
    )


class HierarchicalBetaBinomialReference:
    """Mesa-level beta-binomial hierarchy with target-excluded fitting.

    The previous preview converted each geography into one pooled success / trial
    row.  That removes the mesa overdispersion beta-binomial is intended to
    model.  This reference instead fits each level to the individual mesa
    likelihoods and shrinks fitted distributions by number of mesas only.
    """

    def __init__(self, observations: tuple[BinomialPeerObservation, ...]) -> None:
        if len(observations) < 2:
            raise ValueError("at least two observations are required")
        self._observations = observations
        self._department: dict[str, tuple[int, ...]] = {}
        self._municipality: dict[tuple[str, str], tuple[int, ...]] = {}
        self._place: dict[tuple[str, str, str], tuple[int, ...]] = {}
        for index, item in enumerate(observations):
            self._department[item.department_id] = self._department.get(item.department_id, ()) + (
                index,
            )
            municipality_key = (item.department_id, item.municipality_id)
            self._municipality[municipality_key] = self._municipality.get(municipality_key, ()) + (
                index,
            )
            place_key = (item.department_id, item.municipality_id, item.polling_place_id)
            self._place[place_key] = self._place.get(place_key, ()) + (index,)
        self._prediction_cache: dict[
            int, tuple[ReferenceFit, ReferenceFit, ReferenceFit, ReferenceFit]
        ] = {}

    @property
    def size(self) -> int:
        return len(self._observations)

    def _fit_indices(
        self, indexes: tuple[int, ...], excluded: int, parent: ReferenceFit
    ) -> ReferenceFit:
        peers = tuple(self._observations[item] for item in indexes if item != excluded)
        if len(peers) < 2:
            return parent
        return _shrink(parent, _fit_beta_binomial(peers), len(peers))

    def _fits_without(
        self, index: int
    ) -> tuple[ReferenceFit, ReferenceFit, ReferenceFit, ReferenceFit]:
        cached = self._prediction_cache.get(index)
        if cached is not None:
            return cached
        target = self._observations[index]
        global_fit = _fit_beta_binomial(
            self._observations[:index] + self._observations[index + 1 :]
        )
        department = self._fit_indices(self._department[target.department_id], index, global_fit)
        municipality = self._fit_indices(
            self._municipality[(target.department_id, target.municipality_id)], index, department
        )
        place = self._fit_indices(
            self._place[(target.department_id, target.municipality_id, target.polling_place_id)],
            index,
            municipality,
        )
        result = (global_fit, department, municipality, place)
        self._prediction_cache[index] = result
        return result

    def predict(self, index: int) -> ReferencePrediction:
        target = self._observations[index]
        _global_fit, department_fit, municipality_fit, place_fit = self._fits_without(index)
        department = self._department[target.department_id]
        municipality_key = (target.department_id, target.municipality_id)
        municipality = self._municipality[municipality_key]
        place_key = (target.department_id, target.municipality_id, target.polling_place_id)
        place = self._place[place_key]
        department_peers = len(department) - 1
        municipality_peers = len(municipality) - 1
        place_peers = len(place) - 1
        if place_peers >= 9:
            fit, level = place_fit, "polling_place"
        elif municipality_peers >= 1:
            fit, level = municipality_fit, "municipality"
        else:
            fit, level = department_fit, "department"
        alpha, beta = fit.alpha, fit.beta
        expected = alpha / (alpha + beta)
        variance = (
            target.trials
            * alpha
            * beta
            * (alpha + beta + target.trials)
            / ((alpha + beta) ** 2 * (alpha + beta + 1))
        )
        lower = float(betabinom.cdf(target.successes, target.trials, alpha, beta))
        upper = float(betabinom.sf(target.successes - 1, target.trials, alpha, beta))
        p_value = min(1.0, 2 * min(lower, upper))
        interval_low, interval_high = betabinom.ppf((0.025, 0.975), target.trials, alpha, beta)
        status = "target-excluded-hierarchical-refit"
        convergence = "converged" if fit.converged else f"{fit.method}-not-converged"
        influence = 1 / max(1, self.size - 1)
        influence_status = (
            "high-exposure-influence" if influence >= 0.01 else "low-exposure-influence"
        )
        return ReferencePrediction(
            expected_rate=expected,
            interval_low=float(interval_low / target.trials),
            interval_high=float(interval_high / target.trials),
            discrete_two_sided_p_value=p_value,
            predictive_variance=variance,
            hierarchy_level=level,
            department_peers=department_peers,
            municipality_peers=municipality_peers,
            polling_place_peers=place_peers,
            loo_refit_status=status,
            convergence_status=convergence,
            influence_diagnostic=influence_status,
        )

    def predict_municipality(
        self, department_id: str, municipality_id: str
    ) -> MunicipalReferencePrediction:
        """Predict one municipality after removing *all* of its mesas.

        The target municipality shares one beta latent probability, so its
        total variance is the N-level beta-binomial variance.  A plug-in EB fit
        still omits hyperparameter-estimation uncertainty; therefore z and p
        are deliberately not evaluable.
        """
        indexes = self._municipality.get((department_id, municipality_id), ())
        if not indexes:
            raise ValueError("municipality is not present in the reference")
        excluded = set(indexes)
        peers = tuple(
            item for index, item in enumerate(self._observations) if index not in excluded
        )
        if len(peers) < 2:
            raise ValueError("leave-one-municipality-out needs at least two outside mesas")
        fit = _fit_beta_binomial(peers)
        mean = fit.alpha / (fit.alpha + fit.beta)
        total_trials = sum(
            item.trials for index, item in enumerate(self._observations) if index in excluded
        )
        variance = beta_binomial_variance(total_trials, fit.alpha, fit.beta)
        observed = sum(
            item.successes for index, item in enumerate(self._observations) if index in excluded
        )
        expected = total_trials * mean
        return MunicipalReferencePrediction(
            municipality_id=municipality_id,
            mesas=len(indexes),
            expected_count=expected,
            predictive_variance=variance,
            observed_count=observed,
            standardized_residual=None,
            approximate_two_sided_p_value=None,
            loo_refit_status="leave-one-municipality-out-mesa-level-beta-binomial",
            inference_status="not_evaluable_hyperparameter_uncertainty",
            alpha=fit.alpha,
            beta=fit.beta,
            total_trials=total_trials,
        )
