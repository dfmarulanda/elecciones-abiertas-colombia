#!/usr/bin/env python3
"""Compute the descriptive statistics behind the site's comparison section.

Source: the 172MB candidate api-snapshot (real per-mesa preconteo, 122,020
mesa result facts). Output: data/derived/comparison-statistics-2026.json.

Every statistic carries the exact input row count it was computed over, plus a
sha256 of the input snapshot and of the emitted document, so any number here can
be reproduced from the release alone.

None of these statistics is a test for fraud. See
docs/research/comparison-statistics-method.md for what each one can and cannot
indicate, and for why no Benford statistic is computed.
"""

import hashlib
import json
import sys
from pathlib import Path

from scipy.stats import chi2

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/releases/candidate-2026-r2-dacb28aa766eec87/api-snapshot.json"
OUT = ROOT / "data/derived/comparison-statistics-2026.json"

# Below 10 a count's last digit IS the count, so the digit distribution is the
# distribution of small precinct totals and is non-uniform by construction --
# a mesa with 3 votes can never show last digit 7. The floor is the smallest
# value at which all ten digits are attainable. 100 is reported alongside it as
# a sensitivity check, not as the headline.
DIGIT_FLOOR = 10
DIGIT_FLOOR_SENSITIVITY = 100
ALPHA = 0.05
DIGIT_DF = 9


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
        "critical_value_alpha_0_05": chi2.ppf(1 - ALPHA, DIGIT_DF),
        "p_value": float(chi2.sf(statistic, DIGIT_DF)),
        "exceeds_critical_value": bool(statistic > chi2.ppf(1 - ALPHA, DIGIT_DF)),
    }


def main() -> int:
    snapshot = json.loads(SRC.read_text())

    release = snapshot["release"]
    candidates = {c["id"]: c for c in snapshot["election"]["candidates"]}
    department_of_mesa = {m["id"]: m["department_id"] for m in snapshot["mesas"]}
    geographies = {g["id"]: g for g in snapshot["geographies"]}

    mesa_facts = [r for r in snapshot["results"] if r["geography_level"] == "mesa"]
    national = next(r for r in snapshot["results"] if r["geography_level"] == "national")

    # --- collect per-mesa candidate counts, keyed by candidate ------------------
    per_candidate_counts: dict[str, list[int]] = {cid: [] for cid in candidates}
    unanimous = 0
    mesas_with_candidate_votes = 0
    mesas_skipped_unobserved = 0
    department_totals: dict[str, dict] = {}

    for fact in mesa_facts:
        votes = {c["candidate_id"]: observed(c["votes"]) for c in fact["candidates"]}
        if any(v is None for v in votes.values()):
            mesas_skipped_unobserved += 1
            continue

        for cid, value in votes.items():
            per_candidate_counts[cid].append(value)

        total_candidate_votes = sum(votes.values())
        if total_candidate_votes > 0:
            mesas_with_candidate_votes += 1
            if max(votes.values()) == total_candidate_votes:
                unanimous += 1

        department_id = department_of_mesa[fact["mesa_id"]]
        bucket = department_totals.setdefault(
            department_id,
            {
                "geography_id": department_id,
                "code": geographies[department_id]["code"],
                "name": geographies[department_id]["name"],
                "mesa_facts": 0,
                "valid_votes": 0,
                "candidate_votes": {cid: 0 for cid in candidates},
            },
        )
        bucket["mesa_facts"] += 1
        valid = observed(fact["valid_votes"])
        if valid is not None:
            bucket["valid_votes"] += valid
        for cid, value in votes.items():
            bucket["candidate_votes"][cid] += value

    # --- (a) last-digit uniformity --------------------------------------------
    def digit_block(floor: int) -> dict:
        per_candidate = {}
        pooled: list[int] = []
        for cid, counts in per_candidate_counts.items():
            eligible = [v for v in counts if v >= floor]
            pooled.extend(eligible)
            per_candidate[cid] = {
                "candidate_name": candidates[cid]["short_name"]["es"],
                "mesa_counts_available": len(counts),
                **last_digit_chi_square(eligible),
            }
        return {
            "denominator_floor": floor,
            "floor_rationale": (
                "Only mesa candidate counts of at least this value are included. "
                "Below 10 the last digit is the count itself, so the digit "
                "distribution is the distribution of small mesa totals and is "
                "non-uniform by construction."
            ),
            "per_candidate": per_candidate,
            "combined": {
                "note": (
                    "The two candidates' counts within a mesa are not "
                    "independent -- they are bounded by the same valid-vote "
                    "total -- so the pooled statistic understates its own "
                    "variance. The per-candidate statistics are the primary "
                    "reading; this pooled figure is descriptive only."
                ),
                **last_digit_chi_square(pooled),
            },
        }

    last_digit = {
        "statistic": "Pearson chi-square of the last digit of mesa-level candidate "
        "vote counts against a uniform 1/10 expectation",
        "primary": digit_block(DIGIT_FLOOR),
        "sensitivity": digit_block(DIGIT_FLOOR_SENSITIVITY),
    }

    # --- (b) unanimous mesas ---------------------------------------------------
    unanimous_block = {
        "statistic": "share of mesas where one candidate received every "
        "candidate vote cast in that mesa",
        "definition": (
            "Two-candidate second round, so a unanimous mesa is one where the "
            "other candidate received exactly zero. Blank, null and unmarked "
            "ballots are not candidate votes and are excluded from both sides "
            "of the ratio."
        ),
        "input_rows": mesas_with_candidate_votes,
        "excluded_zero_candidate_vote_mesas": len(mesa_facts)
        - mesas_skipped_unobserved
        - mesas_with_candidate_votes,
        "unanimous_mesas": unanimous,
        "share": unanimous / mesas_with_candidate_votes
        if mesas_with_candidate_votes
        else None,
        "percent": 100 * unanimous / mesas_with_candidate_votes
        if mesas_with_candidate_votes
        else None,
    }

    # --- (c) margin decomposition ---------------------------------------------
    national_votes = {
        c["candidate_id"]: observed(c["votes"]) for c in national["candidates"]
    }
    winner_id, runner_id = sorted(
        national_votes, key=lambda cid: national_votes[cid], reverse=True
    )
    published_margin = national_votes[winner_id] - national_votes[runner_id]

    derived_national = {
        cid: sum(d["candidate_votes"][cid] for d in department_totals.values())
        for cid in candidates
    }
    derived_margin = derived_national[winner_id] - derived_national[runner_id]

    rows = []
    for bucket in department_totals.values():
        winner_votes = bucket["candidate_votes"][winner_id]
        runner_votes = bucket["candidate_votes"][runner_id]
        internal_margin = abs(winner_votes - runner_votes)
        internal_winner = winner_id if winner_votes >= runner_votes else runner_id
        signed_contribution = winner_votes - runner_votes
        rows.append(
            {
                "geography_id": bucket["geography_id"],
                "code": bucket["code"],
                "name": bucket["name"],
                "mesa_facts": bucket["mesa_facts"],
                "valid_votes": bucket["valid_votes"],
                "candidate_votes": bucket["candidate_votes"],
                "internal_winner": internal_winner,
                "internal_margin": internal_margin,
                "internal_margin_share_of_own_valid_votes": (
                    internal_margin / bucket["valid_votes"]
                    if bucket["valid_votes"]
                    else None
                ),
                "signed_contribution_to_national_margin": signed_contribution,
                "percent_of_national_margin": 100 * signed_contribution / derived_margin,
                "share_of_national_valid_votes": (
                    bucket["valid_votes"] / sum(d["valid_votes"] for d in department_totals.values())
                ),
            }
        )

    # Two defensible orderings. Signed ranks departments by how far they push the
    # national result toward the national winner, so departments the runner-up
    # carried sort to the bottom. Absolute ranks by the size of the contribution
    # regardless of direction, which is what "share of the national margin"
    # ordinarily means. They disagree, so both are emitted.
    by_absolute = sorted(
        rows, key=lambda r: abs(r["percent_of_national_margin"]), reverse=True
    )
    for rank, row in enumerate(by_absolute, start=1):
        row["rank_by_absolute_contribution_to_national_margin"] = rank

    by_signed = sorted(
        rows, key=lambda r: r["percent_of_national_margin"], reverse=True
    )
    for rank, row in enumerate(by_signed, start=1):
        row["rank_by_signed_contribution_to_national_margin"] = rank

    by_internal_rate = sorted(
        rows,
        key=lambda r: r["internal_margin_share_of_own_valid_votes"] or 0,
        reverse=True,
    )
    for rank, row in enumerate(by_internal_rate, start=1):
        row["rank_by_internal_margin_rate"] = rank

    exterior = next(r for r in rows if r["code"] == "88")
    antioquia = next(r for r in rows if r["code"] == "01")

    margin_block = {
        "statistic": "decomposition of the national second-round margin across "
        "all 34 departments",
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
        },
        "departments": by_contribution,
        "retraction_checks": {
            "source": "docs/research/method-record.md item 16",
            "exterior_rank_by_contribution_to_national_margin": {
                "claimed": 10,
                "measured": exterior["rank_by_contribution_to_national_margin"],
                "confirms": exterior["rank_by_contribution_to_national_margin"] == 10,
            },
            "exterior_rank_by_internal_margin_rate": {
                "claimed": 10,
                "measured": exterior["rank_by_internal_margin_rate"],
                "confirms": exterior["rank_by_internal_margin_rate"] == 10,
            },
            "exterior_percent_of_national_margin": exterior[
                "percent_of_national_margin"
            ],
            "exterior_share_of_national_valid_votes_percent": 100
            * exterior["share_of_national_valid_votes"],
            "department_01_percent_of_national_margin": {
                "claimed": 419.5,
                "measured": antioquia["percent_of_national_margin"],
                "confirms": round(antioquia["percent_of_national_margin"], 1) == 419.5,
            },
            "departments_exceeding_exterior_internal_margin_rate": sum(
                1
                for r in rows
                if (r["internal_margin_share_of_own_valid_votes"] or 0)
                > (exterior["internal_margin_share_of_own_valid_votes"] or 0)
            ),
            "reading": (
                "In a race decided by a margin this small relative to ballots "
                "cast, many departments individually exceed the national "
                "margin. A single department's share of that margin is "
                "therefore not a distinguishing property of that department."
            ),
        },
    }

    document = {
        "schema": "comparison-statistics/1",
        "generated_from": {
            "release_id": release["release_id"],
            "data_version": release["data_version"],
            "release_status": release["status"],
            "legal_status": "preliminary",
            "election_slug": snapshot["election"]["slug"],
            "source_snapshot": str(SRC.relative_to(ROOT)),
            "source_snapshot_sha256": sha256_file(SRC),
            "script": "scripts/compute-comparison-statistics.py",
        },
        "scope": {
            "mesa_result_facts_in_release": len(mesa_facts),
            "mesa_facts_with_all_candidate_cells_observed": len(mesa_facts)
            - mesas_skipped_unobserved,
            "mesa_facts_skipped_unobserved": mesas_skipped_unobserved,
        },
        "not_computed": {
            "turnout_below_national_grain": (
                "registered_electors is unavailable on 122,008 of 122,020 mesa "
                "facts, so no per-mesa or per-department turnout denominator "
                "exists in this release. None is computed at those grains."
            ),
            "benford": (
                "No Benford statistic is computed. Benford's law does not hold "
                "for vote counts drawn from precincts of heterogeneous size; "
                "see docs/research/comparison-statistics-method.md."
            ),
        },
        "last_digit_uniformity": last_digit,
        "unanimous_mesas": unanimous_block,
        "margin_decomposition": margin_block,
    }

    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
    document["document_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  document_sha256 (over the payload without this field) "
          f"{document['document_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
