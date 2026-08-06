#!/usr/bin/env python3
"""Run the 2026 comparison statistics over 2018 and 2022 with the same rules.

The point of the comparison section is that a single year's number means
nothing: the same code has to run over earlier elections so a reader can see
whether 2026 looks like what came before. Computing 2026 alone cannot carry
that argument, so this extends the same two statistics to the two historical
releases.

WHAT BOUNDS THIS COMPARISON, and it must travel with every figure:

  * 2026 is the PRECONTEO -- the election-night preliminary count. 2018 and
    2022 are the MMV mesa annex, a different stage of the count. These are not
    the same instrument measured twice.
  * findings-ledger.md 2.12: the 2018 exterior is short 13-17 mesas against the
    official installed universe.
  * findings-ledger.md 2.7: the 2022 MMV exterior carries 2,552 mesa identities
    against 1,343 census-installed exterior mesas.

Both anomalies are unresolved and bound the series rather than being corrected
here. Neither statistic is evidence of irregularity in any year; both are
descriptive, and the last-digit test in particular exceeds its critical value
in elections nobody disputes -- which is the entire reason all three years are
shown together.
"""

import collections
import hashlib
import json
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/derived/comparison-statistics-historical.json"

SOURCES = {
    "2018": (
        ROOT
        / "data/releases/historical-2018-mmv-context-v2-c456aeb032917d5c/historical-2018-mmv.parquet",
        "presidencia-2018-round-2",
    ),
    "2022": (
        ROOT
        / "data/releases/historical-2022-mmv-context-v2-288e9b41c14730e9/historical-2022-mmv.parquet",
        "presidencia-2022-round-2",
    ),
}

#: Candidate categories. 996/997/998 are blank, null and unmarked ballots --
#: they are not votes for a candidate and take no part in either statistic.
CANDIDATE_CODES = {"001", "002"}

#: Matches the 2026 run: a last digit only carries information once the count is
#: large enough for all ten digits to be reachable.
MIN_COUNT_FOR_LAST_DIGIT = 10

CRITICAL_CHI_SQUARE_9DF_005 = 16.918977604620444


def mesa_key(row: dict[str, object]) -> tuple[str, ...]:
    """Mesa identity. The code alone is not unique across places."""
    return tuple(
        str(row[part])
        for part in ("dep_code", "mun_code", "zona_code", "puesto_code", "mesa_code")
    )


def collect(path: Path, slug: str) -> dict[tuple[str, ...], dict[str, int]]:
    table = pq.read_table(
        path,
        columns=[
            "election_slug",
            "corporation_name",
            "category_code",
            "votes",
            "dep_code",
            "mun_code",
            "zona_code",
            "puesto_code",
            "mesa_code",
        ],
    )
    table = table.filter(pc.equal(table["election_slug"], slug))
    table = table.filter(pc.equal(table["corporation_name"], "PRESIDENTE"))

    per_mesa: dict[tuple[str, ...], dict[str, int]] = collections.defaultdict(dict)
    for row in table.to_pylist():
        code = str(row["category_code"])
        if code not in CANDIDATE_CODES:
            continue
        per_mesa[mesa_key(row)][code] = int(row["votes"] or 0)
    return per_mesa


def last_digit_chi_square(counts: list[int]) -> dict[str, object]:
    observed = [0] * 10
    for value in counts:
        observed[value % 10] += 1
    total = sum(observed)
    expected = total / 10
    statistic = sum((seen - expected) ** 2 / expected for seen in observed)
    return {
        "chi_square": statistic,
        "degrees_of_freedom": 9,
        "critical_value_alpha_0_05": CRITICAL_CHI_SQUARE_9DF_005,
        "exceeds_critical_value": statistic > CRITICAL_CHI_SQUARE_9DF_005,
        "input_rows": total,
        "expected_count_per_digit": expected,
        "observed_counts": observed,
    }


def analyse(year: str, path: Path, slug: str) -> dict[str, object]:
    per_mesa = collect(path, slug)

    digits: list[int] = []
    per_candidate: dict[str, list[int]] = {code: [] for code in sorted(CANDIDATE_CODES)}
    unanimous = 0
    considered = 0
    excluded_zero = 0

    for votes in per_mesa.values():
        values = [votes.get(code, 0) for code in sorted(CANDIDATE_CODES)]
        for code, value in zip(sorted(CANDIDATE_CODES), values, strict=True):
            if value >= MIN_COUNT_FOR_LAST_DIGIT:
                digits.append(value)
                per_candidate[code].append(value)
        if sum(values) == 0:
            excluded_zero += 1
            continue
        considered += 1
        if any(value == 0 for value in values):
            unanimous += 1

    return {
        "election_slug": slug,
        "mesas_in_source": len(per_mesa),
        "last_digit_uniformity": {
            "combined": last_digit_chi_square(digits),
            "per_candidate": {
                code: last_digit_chi_square(values)
                for code, values in per_candidate.items()
            },
            "minimum_count_for_inclusion": MIN_COUNT_FOR_LAST_DIGIT,
            "note": (
                "The two candidates' counts within a mesa are bounded by the same "
                "valid-vote total and are therefore not independent, so the pooled "
                "statistic understates its own variance. Per-candidate figures are "
                "the primary reading."
            ),
        },
        "unanimous_mesas": {
            "unanimous_mesas": unanimous,
            "input_rows": considered,
            "share": (unanimous / considered) if considered else None,
            "percent": (100 * unanimous / considered) if considered else None,
            "excluded_zero_candidate_vote_mesas": excluded_zero,
            "definition": (
                "A mesa where one candidate received exactly zero. Blank, null and "
                "unmarked ballots are not candidate votes and are excluded."
            ),
        },
        "provenance": {
            "artifact": str(path.relative_to(ROOT)),
            "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    }


def main() -> None:
    document: dict[str, object] = {
        "schema": "comparison-statistics-historical-v1",
        "statistic_definitions_match": "comparison-statistics-2026.json",
        "comparability": {
            "stage_mismatch": (
                "2026 is the preconteo (election-night preliminary count); 2018 and "
                "2022 are the MMV mesa annex. Different stages of the count, not the "
                "same instrument measured three times."
            ),
            "known_release_anomalies": [
                "2018 exterior is short 13-17 mesas against the official installed "
                "universe (findings-ledger.md 2.12).",
                "2022 MMV exterior carries 2,552 mesa identities against 1,343 "
                "census-installed exterior mesas (findings-ledger.md 2.7).",
            ],
            "reading": (
                "Neither statistic is evidence of irregularity in any year. The "
                "last-digit test exceeds its critical value in elections nobody "
                "disputes, which is why all three years are published together."
            ),
        },
        "years": {},
    }
    for year, (path, slug) in SOURCES.items():
        print(f"computing {year} ({slug}) ...")
        result = analyse(year, path, slug)
        document["years"][year] = result  # type: ignore[index]
        chi = result["last_digit_uniformity"]["combined"]["chi_square"]  # type: ignore[index]
        pct = result["unanimous_mesas"]["percent"]  # type: ignore[index]
        print(f"   mesas={result['mesas_in_source']:,}  chi2={chi:.2f}  unanimous={pct:.3f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True)
    document["document_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
