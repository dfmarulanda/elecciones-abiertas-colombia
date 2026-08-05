"""Leave-one-cluster-out peer screening at polling-place grain.

The mesa-level peer screen removes exactly one mesa before fitting its
reference distribution, so every other mesa in the target's own polling place
stays in the pool.  Mesas in a puesto share jurados, ballots, a transmission
batch and a physical queue, so a puesto-wide irregularity contaminates its own
reference and raises the bar that would have caught it.  Measured on the
project's own harness, mesa-level power against clustered alternatives above
25 percentage points is 0.000 across 5,010 injections.

This detector changes the unit of comparison rather than the threshold.  It
aggregates each polling place to a single (numerator, denominator) pair and
compares whole puestos against other puestos, removing the entire target
cluster before fitting.  A puesto-wide shift can no longer hide inside its own
reference.

The same discipline as the mesa screen applies and is not relaxed anywhere:
unknown, unavailable and zero stay distinct; a puesto is evaluable only when
every one of its mesas carries a complete source-joined ballot vector; the
output is a research lead ordered for human review, never a fraud probability,
a finding, or a legal conclusion; and nothing here is eligible for public
audit-priority points.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace

from scipy.stats import betabinom  # type: ignore[import-untyped]

from .peer_signals import (
    MesaMetrics,
    Metric,
    _by_adjust,
    _fit_beta_binomial,
    _numerator_denominator,
)

METHODOLOGY_VERSION = "cluster-leave-one-place-out-v1"

# A reference of whole puestos is coarser than one of mesas, so the same
# nominal pool size buys fewer effective observations.  The mesa screen's
# calibrated floor for the strict tail is 200; the same measurement discipline
# has not been repeated at cluster grain, so this detector publishes its tail
# without a strict endpoint and stays research-only until it has been.
_MIN_CLUSTERS = 30
_TARGET_FDR = 0.05


@dataclass(frozen=True)
class ClusterSignal:
    """One polling place compared against its peer polling places."""

    place_id: str
    municipality_id: str
    department_id: str
    metric: Metric
    family_id: str
    mesas: int
    numerator: int
    denominator: int
    observed_rate: float | None
    expected_rate: float | None
    effect_pp: float | None
    peers: int
    pool_level: str | None
    fit_method: str | None
    tail_probability: float | None
    adjusted_q_value: float | None
    eligible: bool
    reason: str | None
    research_signal: bool
    # Public exposure is refused at the type level, not by configuration.
    signal: bool = False
    public_point_eligible: bool = False
    claim_state: str = "neutral_research_association"
    methodology_version: str = METHODOLOGY_VERSION
    calculation: str = "leave-one-place-out beta-binomial empirical-Bayes predictive tail"
    limitations: tuple[str, ...] = (
        "A cluster-level result is a review lead, not proof, and not a finding of wrongdoing.",
        "Aggregating a polling place hides mesa-level structure; a cluster lead does not "
        "identify which mesa, if any, produced it.",
        "The plug-in predictive tail is not propagated for hyperparameter uncertainty and "
        "has not been calibrated at cluster grain, so no strict endpoint is applied.",
        "A polling place is evaluable only when every one of its mesas carries a complete "
        "source-joined ballot vector; partial places are excluded, not imputed.",
        "Nothing here is eligible for public audit-priority points.",
    )
    output_hash: str = field(default="")

    def with_hash(self) -> ClusterSignal:
        payload = asdict(self)
        payload.pop("output_hash")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return replace(self, output_hash=hashlib.sha256(encoded.encode()).hexdigest())


@dataclass(frozen=True)
class _Cluster:
    place_id: str
    municipality_id: str
    department_id: str
    mesas: int
    numerator: int
    denominator: int


def _aggregate(rows: tuple[MesaMetrics, ...], metric: Metric) -> tuple[_Cluster | None, str | None]:
    """Aggregate one polling place, or refuse to."""
    numerator = 0
    denominator = 0
    for row in rows:
        pair_numerator, pair_denominator = _numerator_denominator(row, metric)
        if (
            row.candidate_total_votes is None
            or row.denominator_provenance != "joined_official"
            or pair_denominator is None
        ):
            # One unavailable mesa makes the place total unknown, not smaller.
            return None, "incomplete_mesa_in_place_not_evaluable"
        numerator += pair_numerator
        denominator += pair_denominator
    if denominator <= 0:
        return None, "place_denominator_unavailable"
    first = rows[0]
    return (
        _Cluster(
            place_id=first.place_id,
            municipality_id=first.municipality_id,
            department_id=first.department_id,
            mesas=len(rows),
            numerator=numerator,
            denominator=denominator,
        ),
        None,
    )


def _family_id(row: MesaMetrics) -> str:
    return "|".join(
        (
            row.data_version,
            row.election_slug,
            row.source_layer,
            row.metric,
            str(row.candidate_id),
        )
    )


def cluster_signals(records: Iterable[MesaMetrics]) -> tuple[ClusterSignal, ...]:
    """Compare whole polling places against their peer polling places."""
    rows = tuple(sorted(records, key=lambda item: item.mesa_id))
    if not rows:
        return ()
    metric = rows[0].metric
    if any(row.metric != metric for row in rows):
        raise ValueError("a cluster family must describe exactly one metric")
    family_id = _family_id(rows[0])

    by_place: dict[str, list[MesaMetrics]] = defaultdict(list)
    for row in rows:
        by_place[row.place_id].append(row)

    clusters: dict[str, _Cluster] = {}
    refusals: dict[str, str] = {}
    for place_id, members in by_place.items():
        cluster, reason = _aggregate(tuple(members), metric)
        if cluster is None:
            refusals[place_id] = reason or "not_evaluable"
        else:
            clusters[place_id] = cluster

    # Reference pools of whole places, narrowest first, exactly as the mesa
    # screen does -- but the unit removed is the entire target cluster.
    pools: dict[tuple[str, str], list[str]] = defaultdict(list)
    for place_id, cluster in clusters.items():
        pools[("municipality", cluster.municipality_id)].append(place_id)
        pools[("department", cluster.department_id)].append(place_id)

    provisional: list[ClusterSignal] = []
    tail_values: list[float] = []
    tail_index: list[int] = []

    for place_id in sorted(by_place):
        members = by_place[place_id]
        first = members[0]
        cluster = clusters.get(place_id)
        if cluster is None:
            provisional.append(
                ClusterSignal(
                    place_id=place_id,
                    municipality_id=first.municipality_id,
                    department_id=first.department_id,
                    metric=metric,
                    family_id=family_id,
                    mesas=len(members),
                    numerator=0,
                    denominator=0,
                    observed_rate=None,
                    expected_rate=None,
                    effect_pp=None,
                    peers=0,
                    pool_level=None,
                    fit_method=None,
                    tail_probability=None,
                    adjusted_q_value=None,
                    eligible=False,
                    reason=refusals.get(place_id, "not_evaluable"),
                    research_signal=False,
                )
            )
            continue

        level: str | None = None
        pool_members: list[str] = []
        for candidate_level, key in (
            ("municipality", cluster.municipality_id),
            ("department", cluster.department_id),
        ):
            candidate = pools.get((candidate_level, key), [])
            # The target cluster is removed whole, so it cannot support itself.
            if len(candidate) - 1 >= _MIN_CLUSTERS:
                level, pool_members = candidate_level, candidate
                break

        if level is None:
            provisional.append(
                ClusterSignal(
                    place_id=place_id,
                    municipality_id=cluster.municipality_id,
                    department_id=cluster.department_id,
                    metric=metric,
                    family_id=family_id,
                    mesas=cluster.mesas,
                    numerator=cluster.numerator,
                    denominator=cluster.denominator,
                    observed_rate=cluster.numerator / cluster.denominator,
                    expected_rate=None,
                    effect_pp=None,
                    peers=max(len(pools.get(("department", cluster.department_id), [])) - 1, 0),
                    pool_level=None,
                    fit_method=None,
                    tail_probability=None,
                    adjusted_q_value=None,
                    eligible=False,
                    reason="fewer_than_30_eligible_peer_places",
                    research_signal=False,
                )
            )
            continue

        counts = Counter(
            (clusters[member].numerator, clusters[member].denominator)
            for member in pool_members
            if member != place_id
        )
        fit = _fit_beta_binomial(counts)
        lower = float(betabinom.cdf(cluster.numerator, cluster.denominator, fit.alpha, fit.beta))
        upper = float(
            betabinom.sf(cluster.numerator - 1, cluster.denominator, fit.alpha, fit.beta)
        )
        tail = 2.0 * min(lower, upper)
        tail = min(1.0, tail)
        expected = fit.alpha / (fit.alpha + fit.beta)
        observed = cluster.numerator / cluster.denominator

        tail_index.append(len(provisional))
        tail_values.append(tail)
        provisional.append(
            ClusterSignal(
                place_id=place_id,
                municipality_id=cluster.municipality_id,
                department_id=cluster.department_id,
                metric=metric,
                family_id=family_id,
                mesas=cluster.mesas,
                numerator=cluster.numerator,
                denominator=cluster.denominator,
                observed_rate=observed,
                expected_rate=expected,
                effect_pp=abs(observed - expected) * 100,
                peers=len(pool_members) - 1,
                pool_level=level,
                fit_method=fit.method,
                tail_probability=tail,
                adjusted_q_value=None,
                eligible=True,
                reason=None,
                research_signal=False,
            )
        )

    # Benjamini-Yekutieli over the evaluable places: valid under arbitrary
    # dependence, which whole-place aggregates certainly have.
    adjusted, _ = _by_adjust(tail_values)
    output = list(provisional)
    for position, index in enumerate(tail_index):
        item = output[index]
        q_value = adjusted[position]
        output[index] = replace(
            item,
            adjusted_q_value=q_value,
            research_signal=bool(
                item.eligible
                and item.fit_method == "leave-one-out-marginal-likelihood-mle"
                and q_value <= _TARGET_FDR
            ),
        )
    return tuple(item.with_hash() for item in output)
