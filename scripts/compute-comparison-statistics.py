#!/usr/bin/env python3
"""Compute the descriptive statistics behind the site's comparison section.

The section's argument is that a single year's number means nothing: the same
code has to run over earlier elections before a reader can tell whether 2026
looks like what came before. So the two mesa-grain statistics -- last-digit
uniformity and the unanimous-mesa rate -- are computed for 2018 round 2, 2022
round 2 and 2026 round 2 through one identical code path, and emitted in one
document.

Sources:
  2026  the 172MB candidate api-snapshot (preconteo, 122,020 mesa result facts)
  2022  historical-2022-mmv.parquet (MMV mesa annex)
  2018  historical-2018-mmv.parquet (MMV mesa annex)

Output: data/derived/comparison-statistics-2026.json

Every statistic carries the exact input row count it was computed over, plus a
sha256 of each input artifact and of the emitted document, so any number here
can be reproduced from the releases alone.

None of these statistics is a test for fraud, and the last-digit statistic
exceeds its critical value in all three years -- which is precisely why all
three are published together. See docs/research/comparison-statistics-method.md
for what each one can and cannot indicate, and for why no Benford statistic is
computed.
"""

import collections
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq
from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/releases/candidate-2026-r2-dacb28aa766eec87/api-snapshot.json"
OUT = ROOT / "data/derived/comparison-statistics-2026.json"

RELEASES = ROOT / "data/releases"
HISTORICAL = {
    "2018-r2": {
        "path": RELEASES
        / "historical-2018-mmv-context-v2-c456aeb032917d5c/historical-2018-mmv.parquet",
        "election_slug": "presidencia-2018-round-2",
    },
    "2022-r2": {
        "path": RELEASES
        / "historical-2022-mmv-context-v2-288e9b41c14730e9/historical-2022-mmv.parquet",
        "election_slug": "presidencia-2022-round-2",
    },
}

#: MMV long-format category codes. 996/997/998 are blank, null and unmarked
#: ballots -- not votes for a candidate, and no part of either statistic.
CANDIDATE_CATEGORY_CODES = ("001", "002")
PRESIDENTIAL_CORPORATION_CODE = "01"

# Below 10 a count's last digit IS the count, so the digit distribution is the
# distribution of small precinct totals and is non-uniform by construction --
# a mesa with 3 votes can never show last digit 7. The floor is the smallest
# value at which all ten digits are attainable. 100 is reported alongside it as
# a sensitivity check, not as the headline.
DIGIT_FLOOR = 10
DIGIT_FLOOR_SENSITIVITY = 100
ALPHA = 0.05
DIGIT_DF = 9

# Derived once, in one place. A duplicated literal for this bound would be a
# repeat of the Clopper-Pearson defect in method-record.md 7.2, where the same
# constant written two ways differed by one ULP and made two modules disagree.
CRITICAL_VALUE = float(chi2.ppf(1 - ALPHA, DIGIT_DF))

COMBINED_NOTE = (
    "The two candidates' counts within a mesa are not independent -- they are "
    "bounded by the same valid-vote total -- so the pooled statistic "
    "understates its own variance. The per-candidate statistics are the "
    "primary reading; this pooled figure is descriptive only."
)
FLOOR_RATIONALE = (
    "Only mesa candidate counts of at least this value are included. Below 10 "
    "the last digit is the count itself, so the digit distribution is the "
    "distribution of small mesa totals and is non-uniform by construction."
)
UNANIMOUS_DEFINITION = (
    "Two-candidate second round, so a unanimous mesa is one where the other "
    "candidate received exactly zero. Blank, null and unmarked ballots are not "
    "candidate votes and are excluded from both sides of the ratio."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def observed(field: dict | None) -> int | None:
    """Return an integer only when the release marks the cell as observed.

    unknown / unavailable / absent are all None. They are never coerced to 0.
    """
    if not field or field.get("status") != "observed":
        return None
    return field.get("value")


# --------------------------------------------------------------------------
# The two statistics. Both take the same shape for every year: a list of
# per-mesa {series_key: candidate votes} dicts. 2026 and the two MMV years
# differ only in how that list is built, never in how it is measured.
# --------------------------------------------------------------------------


def last_digit_chi_square(counts: list[int]) -> dict:
    """Pearson chi-square of last digits against the uniform 1/10 expectation."""
    tally = [0] * 10
    for value in counts:
        tally[value % 10] += 1
    n = len(counts)
    if n == 0:
        return {"input_rows": 0, "status": "not_evaluable_no_rows"}
    expected = n / 10
    statistic = sum((seen - expected) ** 2 / expected for seen in tally)
    return {
        "input_rows": n,
        "observed_counts": tally,
        "expected_count_per_digit": expected,
        "chi_square": statistic,
        "degrees_of_freedom": DIGIT_DF,
        "critical_value_alpha_0_05": CRITICAL_VALUE,
        "p_value": float(chi2.sf(statistic, DIGIT_DF)),
        "exceeds_critical_value": bool(statistic > CRITICAL_VALUE),
        "max_digit_share_deviation_percentage_points": max(
            abs(100 * seen / n - 10) for seen in tally
        ),
    }


def digit_block(
    mesa_votes: list[dict[str, int]], labels: dict[str, str], floor: int
) -> dict:
    per_series = {}
    pooled: list[int] = []
    for key, label in labels.items():
        counts = [votes[key] for votes in mesa_votes]
        eligible = [v for v in counts if v >= floor]
        pooled.extend(eligible)
        per_series[key] = {
            "candidate_name": label,
            "mesa_counts_available": len(counts),
            **last_digit_chi_square(eligible),
        }
    return {
        "denominator_floor": floor,
        "floor_rationale": FLOOR_RATIONALE,
        "per_candidate": per_series,
        "combined": {"note": COMBINED_NOTE, **last_digit_chi_square(pooled)},
    }


def last_digit_uniformity(mesa_votes: list[dict[str, int]], labels: dict[str, str]) -> dict:
    return {
        "statistic": "Pearson chi-square of the last digit of mesa-level candidate "
        "vote counts against a uniform 1/10 expectation",
        "primary": digit_block(mesa_votes, labels, DIGIT_FLOOR),
        "sensitivity": digit_block(mesa_votes, labels, DIGIT_FLOOR_SENSITIVITY),
    }


def unanimous_mesas(mesa_votes: list[dict[str, int]]) -> dict:
    unanimous = 0
    considered = 0
    excluded_zero = 0
    for votes in mesa_votes:
        total = sum(votes.values())
        if total == 0:
            excluded_zero += 1
            continue
        considered += 1
        if max(votes.values()) == total:
            unanimous += 1
    return {
        "statistic": "share of mesas where one candidate received every candidate "
        "vote cast in that mesa",
        "definition": UNANIMOUS_DEFINITION,
        "input_rows": considered,
        "excluded_zero_candidate_vote_mesas": excluded_zero,
        "unanimous_mesas": unanimous,
        "share": unanimous / considered if considered else None,
        "percent": 100 * unanimous / considered if considered else None,
    }


# --------------------------------------------------------------------------
# Per-year loaders. Each returns (mesa_votes, labels, scope).
# --------------------------------------------------------------------------


def load_2026(snapshot: dict) -> tuple[list[dict[str, int]], dict[str, str], dict, list]:
    candidates = {c["id"]: c for c in snapshot["election"]["candidates"]}
    labels = {cid: c["short_name"]["es"] for cid, c in candidates.items()}
    mesa_facts = [r for r in snapshot["results"] if r["geography_level"] == "mesa"]

    mesa_votes: list[dict[str, int]] = []
    skipped = 0
    for fact in mesa_facts:
        votes = {c["candidate_id"]: observed(c["votes"]) for c in fact["candidates"]}
        if any(v is None for v in votes.values()):
            skipped += 1
            continue
        mesa_votes.append(votes)

    scope = {
        "mesa_result_facts_in_release": len(mesa_facts),
        "mesa_facts_with_all_candidate_cells_observed": len(mesa_facts) - skipped,
        "mesa_facts_skipped_unobserved": skipped,
        "zero_encoding": (
            "Every candidate cell in this release is explicitly present with "
            "status observed, including zeros. Nothing is inferred from absence."
        ),
    }
    return mesa_votes, labels, scope, mesa_facts


def load_mmv(path: Path, election_slug: str) -> tuple[list[dict[str, int]], dict[str, str], dict]:
    """Build the same per-mesa candidate-vote list from the MMV long format.

    The MMV annex is sparse: a (mesa, category) pair with zero votes is
    generally not written as a row at all. Absence of a candidate row therefore
    means zero votes recorded for that candidate, and the mesa universe is the
    union of mesas appearing under any category. This differs from 2026, where
    zero is explicit, and it is what makes the unanimous-mesa numerator
    reachable at all in these years -- a unanimous mesa is precisely one whose
    losing candidate has no row.
    """
    table = pq.read_table(
        path,
        columns=[
            "election_slug",
            "corporation_code",
            "category_code",
            "category_name",
            "votes",
            "dep_code",
            "mun_code",
            "zona_code",
            "puesto_code",
            "mesa_code",
        ],
    )
    table = table.filter(pc.equal(table["election_slug"], election_slug))
    table = table.filter(
        pc.equal(table["corporation_code"], PRESIDENTIAL_CORPORATION_CODE)
    )
    rows = table.to_pylist()

    labels: dict[str, str] = {}
    per_mesa: dict[tuple, dict[str, int]] = collections.defaultdict(dict)
    explicit_zero_rows = 0
    universe: set[tuple] = set()

    for row in rows:
        key = (
            row["dep_code"],
            row["mun_code"],
            row["zona_code"],
            row["puesto_code"],
            row["mesa_code"],
        )
        universe.add(key)
        code = row["category_code"]
        if code not in CANDIDATE_CATEGORY_CODES:
            continue
        value = int(row["votes"])
        if value == 0:
            explicit_zero_rows += 1
        if code in per_mesa[key]:
            raise ValueError(f"duplicate (mesa, category) row for {key} {code}")
        per_mesa[key][code] = value
        labels.setdefault(code, row["category_name"])

    # Absence means zero recorded votes for that candidate in this encoding.
    mesa_votes = [
        {code: per_mesa[key].get(code, 0) for code in CANDIDATE_CATEGORY_CODES}
        for key in sorted(universe)
    ]

    scope = {
        "source_rows_after_filter": len(rows),
        "distinct_mesa_identities": len(universe),
        "mesas_with_both_candidate_rows": sum(
            1 for key in universe if len(per_mesa.get(key, {})) == 2
        ),
        "mesas_with_one_candidate_row": sum(
            1 for key in universe if len(per_mesa.get(key, {})) == 1
        ),
        "mesas_with_no_candidate_row": sum(
            1 for key in universe if not per_mesa.get(key)
        ),
        "explicit_zero_vote_candidate_rows": explicit_zero_rows,
        "zero_encoding": (
            "Sparse long format: a candidate with zero votes is generally not "
            "written as a row. A missing candidate row is read as zero recorded "
            "votes. This is an encoding assumption that does NOT apply to the "
            "2026 snapshot, where every cell is explicit and observed."
        ),
    }
    return mesa_votes, {code: labels[code] for code in CANDIDATE_CATEGORY_CODES}, scope


def year_block(
    mesa_votes: list[dict[str, int]], labels: dict[str, str], scope: dict
) -> dict:
    return {
        "scope": scope,
        "last_digit_uniformity": last_digit_uniformity(mesa_votes, labels),
        "unanimous_mesas": unanimous_mesas(mesa_votes),
    }


# --------------------------------------------------------------------------


def margin_decomposition(snapshot: dict, mesa_facts: list) -> dict:
    """2026 only. See `not_computed` for why this is not extended backwards."""
    candidates = {c["id"]: c for c in snapshot["election"]["candidates"]}
    department_of_mesa = {m["id"]: m["department_id"] for m in snapshot["mesas"]}
    geographies = {g["id"]: g for g in snapshot["geographies"]}
    national = next(r for r in snapshot["results"] if r["geography_level"] == "national")

    department_totals: dict[str, dict] = {}
    for fact in mesa_facts:
        votes = {c["candidate_id"]: observed(c["votes"]) for c in fact["candidates"]}
        if any(v is None for v in votes.values()):
            continue
        department_id = department_of_mesa[fact["mesa_id"]]
        bucket = department_totals.setdefault(
            department_id,
            {
                "geography_id": department_id,
                "code": geographies[department_id]["code"],
                "name": geographies[department_id]["name"],
                "mesa_facts": 0,
                "valid_votes": 0,
                "candidate_votes": dict.fromkeys(candidates, 0),
            },
        )
        bucket["mesa_facts"] += 1
        valid = observed(fact["valid_votes"])
        if valid is not None:
            bucket["valid_votes"] += valid
        for cid, value in votes.items():
            bucket["candidate_votes"][cid] += value

    national_votes = {c["candidate_id"]: observed(c["votes"]) for c in national["candidates"]}
    winner_id, runner_id = sorted(national_votes, key=lambda cid: national_votes[cid], reverse=True)
    published_margin = national_votes[winner_id] - national_votes[runner_id]

    derived_national = {
        cid: sum(d["candidate_votes"][cid] for d in department_totals.values())
        for cid in candidates
    }
    derived_margin = derived_national[winner_id] - derived_national[runner_id]
    derived_valid_votes = sum(d["valid_votes"] for d in department_totals.values())

    rows = []
    for bucket in department_totals.values():
        winner_votes = bucket["candidate_votes"][winner_id]
        runner_votes = bucket["candidate_votes"][runner_id]
        internal_margin = abs(winner_votes - runner_votes)
        signed_contribution = winner_votes - runner_votes
        rows.append(
            {
                "geography_id": bucket["geography_id"],
                "code": bucket["code"],
                "name": bucket["name"],
                "mesa_facts": bucket["mesa_facts"],
                "valid_votes": bucket["valid_votes"],
                "candidate_votes": bucket["candidate_votes"],
                "internal_winner": winner_id if winner_votes >= runner_votes else runner_id,
                "internal_margin": internal_margin,
                "internal_margin_share_of_own_valid_votes": (
                    internal_margin / bucket["valid_votes"] if bucket["valid_votes"] else None
                ),
                "signed_contribution_to_national_margin": signed_contribution,
                "percent_of_national_margin": 100 * signed_contribution / derived_margin,
                "share_of_national_valid_votes": bucket["valid_votes"] / derived_valid_votes,
            }
        )

    # Two defensible orderings. Signed ranks departments by how far they push the
    # national result toward the national winner, so departments the runner-up
    # carried sort to the bottom. Absolute ranks by the size of the contribution
    # regardless of direction, which is what "share of the national margin"
    # ordinarily means. They disagree, so both are emitted.
    by_absolute = sorted(rows, key=lambda r: abs(r["percent_of_national_margin"]), reverse=True)
    for rank, row in enumerate(by_absolute, start=1):
        row["rank_by_absolute_contribution_to_national_margin"] = rank

    by_signed = sorted(rows, key=lambda r: r["percent_of_national_margin"], reverse=True)
    for rank, row in enumerate(by_signed, start=1):
        row["rank_by_signed_contribution_to_national_margin"] = rank

    by_internal_rate = sorted(
        rows, key=lambda r: r["internal_margin_share_of_own_valid_votes"] or 0, reverse=True
    )
    for rank, row in enumerate(by_internal_rate, start=1):
        row["rank_by_internal_margin_rate"] = rank

    exterior = next(r for r in rows if r["code"] == "88")
    antioquia = next(r for r in rows if r["code"] == "01")

    exceeding_exterior_internally = [
        r
        for r in rows
        if (r["internal_margin_share_of_own_valid_votes"] or 0)
        > (exterior["internal_margin_share_of_own_valid_votes"] or 0)
    ]
    exceeding_and_at_least_as_large = [
        r for r in exceeding_exterior_internally if r["valid_votes"] >= exterior["valid_votes"]
    ]

    return {
        "statistic": "decomposition of the national second-round margin across all 34 departments",
        "election": "2026-r2",
        "derivation": (
            "Department totals are sums of the release's own mesa-level result "
            "facts. They are a derived rollup, not a figure published at "
            "department grain -- this release publishes result facts at mesa, "
            "polling-place and national grain only."
        ),
        "input_rows": sum(d["mesa_facts"] for d in department_totals.values()),
        "departments_covered": len(rows),
        "national_published": {
            "source": "release result fact " + national["id"],
            "candidate_votes": national_votes,
            "valid_votes": observed(national["valid_votes"]),
            "winner": winner_id,
            "runner_up": runner_id,
            "margin": published_margin,
        },
        "national_derived_from_mesas": {
            "candidate_votes": derived_national,
            "margin": derived_margin,
            "margin_delta_vs_published": derived_margin - published_margin,
            "valid_votes": derived_valid_votes,
            "valid_votes_delta_vs_published": derived_valid_votes
            - observed(national["valid_votes"]),
        },
        "departments": by_absolute,
        "retraction_checks": {
            "source": "docs/research/method-record.md item 16",
            "exterior_rank_by_share_of_national_margin": {
                "claimed": 10,
                "measured_by_absolute_contribution": exterior[
                    "rank_by_absolute_contribution_to_national_margin"
                ],
                "measured_by_signed_contribution": exterior[
                    "rank_by_signed_contribution_to_national_margin"
                ],
                "confirms": exterior["rank_by_absolute_contribution_to_national_margin"] == 10,
                "note": (
                    "The claim holds when departments are ranked by the size of "
                    "their contribution regardless of direction. Ranked by signed "
                    "contribution -- counting only the departments that pushed "
                    "toward the national winner -- the exterior places 4th. The "
                    "retraction's conclusion does not turn on which ordering is "
                    "used; the exterior is mid-pack under one and behind three "
                    "larger contributors under the other."
                ),
            },
            "exterior_rank_by_internal_margin_rate": {
                "claimed": 10,
                "measured": exterior["rank_by_internal_margin_rate"],
                "confirms": exterior["rank_by_internal_margin_rate"] == 10,
            },
            "exterior_percent_of_national_margin": exterior["percent_of_national_margin"],
            "exterior_share_of_national_valid_votes_percent": 100
            * exterior["share_of_national_valid_votes"],
            "department_01_percent_of_national_margin": {
                "claimed": 419.5,
                "measured": antioquia["percent_of_national_margin"],
                "confirms": round(antioquia["percent_of_national_margin"], 1) == 419.5,
            },
            "departments_exceeding_exterior_internal_margin_rate": {
                "claimed": 9,
                "measured": len(exceeding_exterior_internally),
                "confirms": len(exceeding_exterior_internally) == 9,
                "codes": [r["code"] for r in exceeding_exterior_internally],
            },
            "of_those_with_valid_votes_at_least_the_exterior": {
                "claimed": 4,
                "measured": len(exceeding_and_at_least_as_large),
                "confirms": len(exceeding_and_at_least_as_large) == 4,
                "codes": [r["code"] for r in exceeding_and_at_least_as_large],
                "note": (
                    "The retraction says four of the nine have comparable or "
                    "larger ballot counts. Five of the nine have strictly more "
                    "valid votes than the exterior. The direction of the "
                    "retraction's argument is unaffected."
                ),
            },
            "reading": (
                "In a race decided by a margin this small relative to ballots "
                "cast, many departments individually exceed the national "
                "margin. A single department's share of that margin is "
                "therefore not a distinguishing property of that department."
            ),
        },
    }


def main() -> int:
    snapshot = json.loads(SRC.read_text())
    release = snapshot["release"]

    years: dict[str, dict] = {}

    for key, config in HISTORICAL.items():
        path: Path = config["path"]
        mesa_votes, labels, scope = load_mmv(path, config["election_slug"])
        block = year_block(mesa_votes, labels, scope)
        block["election"] = {
            "election_slug": config["election_slug"],
            "round": 2,
            "corporation": "PRESIDENTE",
        }
        block["provenance"] = {
            "artifact": str(path.relative_to(ROOT)),
            "artifact_sha256": sha256_file(path),
            "source_type": "contextual_baseline",
            "legal_status": "context_only",
            "stage": "MMV mesa annex",
        }
        years[key] = block

    mesa_votes_2026, labels_2026, scope_2026, mesa_facts = load_2026(snapshot)
    block_2026 = year_block(mesa_votes_2026, labels_2026, scope_2026)
    block_2026["election"] = {
        "election_slug": snapshot["election"]["slug"],
        "round": snapshot["election"]["round"],
        "corporation": "PRESIDENTE",
    }
    block_2026["provenance"] = {
        "artifact": str(SRC.relative_to(ROOT)),
        "artifact_sha256": sha256_file(SRC),
        "source_type": "pre_count",
        "legal_status": "preliminary",
        "stage": "preconteo (election-night preliminary count)",
        "release_id": release["release_id"],
    }
    years["2026-r2"] = block_2026

    cross_year = [
        {
            "year": key,
            "election_slug": block["election"]["election_slug"],
            "stage": block["provenance"]["stage"],
            "last_digit_chi_square_combined": block["last_digit_uniformity"]["primary"][
                "combined"
            ]["chi_square"],
            "last_digit_input_rows_combined": block["last_digit_uniformity"]["primary"][
                "combined"
            ]["input_rows"],
            "last_digit_exceeds_critical_value": block["last_digit_uniformity"]["primary"][
                "combined"
            ]["exceeds_critical_value"],
            "unanimous_percent": block["unanimous_mesas"]["percent"],
            "unanimous_mesas": block["unanimous_mesas"]["unanimous_mesas"],
            "unanimous_input_rows": block["unanimous_mesas"]["input_rows"],
        }
        for key, block in sorted(years.items())
    ]

    document = {
        "schema": "comparison-statistics/2",
        "generated_from": {
            "release_id": release["release_id"],
            "data_version": release["data_version"],
            "release_status": release["status"],
            "script": "scripts/compute-comparison-statistics.py",
            "critical_value_alpha_0_05": CRITICAL_VALUE,
            "artifacts": {
                key: {
                    "path": block["provenance"]["artifact"],
                    "sha256": block["provenance"]["artifact_sha256"],
                }
                for key, block in sorted(years.items())
            },
        },
        "comparability": {
            "identical_code_path": (
                "All three years are measured by the same functions over the "
                "same per-mesa candidate-vote structure. Only the loader "
                "differs, because the sources differ in format."
            ),
            "stage_mismatch": (
                "2026 is the PRECONTEO, the election-night preliminary count. "
                "2018 and 2022 are the MMV mesa annex, a later and different "
                "stage of the count. These are not the same instrument measured "
                "three times, and this bounds every cross-year reading here."
            ),
            "legal_status_mismatch": (
                "The 2018 and 2022 artifacts are marked source_type "
                "contextual_baseline and legal_status context_only. They are "
                "context for the 2026 preliminary figures, not a certified "
                "series."
            ),
            "zero_encoding_mismatch": (
                "2026 records every candidate cell explicitly, including zeros. "
                "The MMV annex omits zero-vote rows, so a unanimous mesa in "
                "2018/2022 is identified by the absence of the losing "
                "candidate's row rather than by an explicit zero. The two "
                "encodings resolve to the same quantity but not by the same "
                "evidence, and the unanimous-mesa rate is the statistic this "
                "affects."
            ),
            "known_release_anomalies": [
                "findings-ledger.md 2.12: the 2018 MMV exterior is short 13-17 "
                "mesas against the official installed universe (R1 exterior "
                "2,423 vs 2,436 official; R2 exterior 2,419). Any longitudinal "
                "exterior series must carry a +/-13-17 mesa band on the 2018 "
                "points.",
                "findings-ledger.md 2.7 / 2.12: the 2022 MMV exterior carries "
                "2,552 mesa identities against 1,343 census-installed exterior "
                "mesas reported at the time.",
                "Both are unresolved release-level anomalies. They bound this "
                "series and are not corrected here.",
            ],
            "reading": (
                "Neither statistic is evidence of irregularity in any year. The "
                "last-digit statistic exceeds its critical value in all three "
                "years, including two elections whose outcomes are not in "
                "dispute -- which is the entire reason the three are published "
                "together rather than one alone."
            ),
        },
        "years": years,
        "cross_year": cross_year,
        "margin_decomposition": margin_decomposition(snapshot, mesa_facts),
        "not_computed": {
            "turnout_below_national_grain": (
                "registered_electors is unavailable on 122,008 of 122,020 mesa "
                "facts in 2026, and the MMV annex carries no elector column at "
                "all. No per-mesa or per-department turnout denominator exists "
                "in any of the three sources, so none is computed at those "
                "grains."
            ),
            "margin_decomposition_for_2018_and_2022": (
                "Not computed. Candidate identity in the MMV annex is "
                "unambiguous -- exactly two candidate categories, 001 and 002, "
                "in both years -- so the arithmetic is available. It is "
                "withheld because a cross-stage margin decomposition between "
                "the preconteo and the MMV annex, over department universes "
                "carrying the unresolved exterior anomalies above, is the same "
                "kind of under-specified comparison that produced the "
                "retraction in method-record.md item 16. The 2026 "
                "decomposition stands alone and is labelled as such."
            ),
            "benford": (
                "No Benford statistic is computed for any year. Benford's law "
                "does not hold for vote counts drawn from precincts of "
                "heterogeneous size; see "
                "docs/research/comparison-statistics-method.md."
            ),
        },
    }

    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    document["document_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  critical value (9 df, alpha 0.05) {CRITICAL_VALUE!r}")
    for row in cross_year:
        print(
            f"  {row['year']}  chi2(combined)={row['last_digit_chi_square_combined']:8.3f}"
            f"  n={row['last_digit_input_rows_combined']:7d}"
            f"  unanimous={row['unanimous_percent']:.4f}%"
            f"  ({row['unanimous_mesas']}/{row['unanimous_input_rows']})"
        )
    print(f"  document_sha256 {document['document_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
