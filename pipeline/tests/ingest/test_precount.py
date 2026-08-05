from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
from elecciones_pipeline.ingest.precount import (
    PrecountPlanEntry,
    PrecountSchemaError,
    enumerate_mesa_act_urls,
    parse_nomenclator,
    parse_precount_act,
    plan_aggregate_act_urls,
)

ORIGIN = "https://resultadosprecpresidente2026-2v.registraduria.gov.co"


def nomenclator_payload() -> dict[str, object]:
    """Small, shuffled excerpt matching the real indexed graph shape."""
    nodes: list[dict[str, object]] = [
        {
            "i": 8,
            "n": "ABRAHAM LINCOLN",
            "c": "160010603",
            "s": "ABRAHAM-LINCOLN",
            "l": 6,
            "m": 3,
            "p": [{"l": 4, "p": [3]}],
            "r": [8],
            "h": [],
        },
        {
            "i": 0,
            "n": "COLOMBIA",
            "c": "00",
            "s": "COLOMBIA",
            "l": 1,
            "m": 0,
            "p": [],
            "r": [0],
            "h": [{"l": 2, "p": [12]}],
        },
        {
            "i": 3,
            "n": "ZONA06",
            "c": "1600106",
            "s": "ZONA06",
            "l": 4,
            "m": 0,
            "p": [{"l": 3, "p": [4]}],
            "r": [3],
            "h": [{"l": 6, "p": [8]}],
        },
        {
            "i": 12,
            "n": "BOGOTÁ D.C.",
            "c": "16",
            "s": "BOGOTA-DC",
            "l": 2,
            "m": 0,
            "p": [{"l": 1, "p": [0]}],
            "r": [12],
            "h": [{"l": 3, "p": [4]}],
        },
        {
            "i": 4,
            "n": "BOGOTÁ D.C.",
            "c": "16001",
            "s": "BOGOTA-DC",
            "l": 3,
            "m": 0,
            "p": [{"l": 2, "p": [12]}],
            "r": [4],
            "h": [{"l": 4, "p": [3]}],
        },
    ]
    return {"amb": [{"elec": 1, "ambitos": nodes}]}


def nomenclator_with_comuna_payload() -> dict[str, object]:
    """Published-style hierarchy including the optional comuna scope."""
    nodes: list[dict[str, object]] = [
        {"i": 0, "n": "COLOMBIA", "c": "00", "s": "COLOMBIA", "l": 1, "m": 0,
         "p": [], "r": [0], "h": [{"l": 2, "p": [1]}]},
        {"i": 1, "n": "BOGOTÁ D.C.", "c": "16", "s": "BOGOTA-DC", "l": 2, "m": 0,
         "p": [{"l": 1, "p": [0]}], "r": [1], "h": [{"l": 3, "p": [2]}]},
        {"i": 2, "n": "BOGOTÁ D.C.", "c": "16001", "s": "BOGOTA-DC", "l": 3, "m": 0,
         "p": [{"l": 2, "p": [1]}], "r": [2], "h": [{"l": 4, "p": [3]}]},
        {"i": 3, "n": "ZONA 06", "c": "1600106", "s": "ZONA-06", "l": 4, "m": 0,
         "p": [{"l": 3, "p": [2]}], "r": [3], "h": [{"l": 5, "p": [4]}]},
        {"i": 4, "n": "COMUNA 1", "c": "16001061", "s": "COMUNA-1", "l": 5, "m": 0,
         "p": [{"l": 4, "p": [3]}], "r": [4], "h": [{"l": 6, "p": [5]}]},
        {"i": 5, "n": "PUESTO 03", "c": "160010603", "s": "PUESTO-03", "l": 6, "m": 1,
         "p": [{"l": 5, "p": [4]}], "r": [5], "h": []},
    ]
    return {"amb": [{"elec": 1, "ambitos": nodes}]}


def act_payload(
    scope_code: str,
    *,
    department_code: str = "16",
    mesa_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    def party(
        party_code: str,
        candidate_code: str,
        ballot_position: str,
        votes: str,
        share: str,
        given_names: str,
        surnames: str,
        mate_given_names: str,
        mate_surnames: str,
    ) -> dict[str, object]:
        return {
            "act": {
                "codpar": party_code,
                "cam": "0",
                "vot": votes,
                "pvot": share,
                "carg": "0",
                "cargElectos": "0",
                "cargEmpatados": "0",
                "cantotabla": [
                    {
                        "amb": scope_code,
                        "codcan": candidate_code,
                        "sorteo": ballot_position,
                        "cedula": "not-exposed-by-parser",
                        "nomcan": given_names,
                        "apecan": surnames,
                        "nomcan2": mate_given_names,
                        "apecan2": mate_surnames,
                        "vot": votes,
                        "pvot": share,
                        "carg": "0",
                        "pref": "1",
                        "empate": "0",
                    }
                ],
            }
        }

    return {
        "elec": "1",
        "amb": scope_code,
        "tope": "2",
        "numact": "66",
        "numdep": "66",
        "iscircus": "1",
        "mdhm": "06212134",
        "shc": "0",
        "dept": department_code,
        "totales": {
            "act": {
                "metota": "122020",
                "mesesc": "122017",
                "pmesesc": "99,99%",
                "meserr": "0",
                "centota": "41421973",
                "votant": "26345364",
                "pvotant": "63,60%",
                "absten": "15076609",
                "pabsten": "36,39%",
                "votnul": "220763",
                "pvotnul": "0,83%",
                "votnma": "0",
                "pvotnma": "0%",
                "votblan": "426848",
                "pvotblan": "1,63%",
                "votval": "26095102",
                "pvotval": "99,05%",
            }
        },
        "camaras": [
            {
                "cam": "0",
                "cir": "0",
                # The reversed order exercises deterministic candidate output.
                "partotabla": [
                    party(
                        "3",
                        "2",
                        "2",
                        "12959542",
                        "49,66%",
                        "ABELARDO",
                        "DE LA ESPRIELLA",
                        "JOSÉ\u00a0MANUEL",
                        "RESTREPO ABONDANO",
                    ),
                    party(
                        "2",
                        "1",
                        "1",
                        "12708712",
                        "48,70%",
                        "IVÁN",
                        "CEPEDA CASTRO",
                        "AIDA MARINA",
                        "QUILCUE VIVAS",
                    ),
                ],
                "mapagan": [
                    {"amb": mesa_id, "nombre": f"Mesa {position}"}
                    for position, mesa_id in enumerate(mesa_ids, start=1)
                ],
            }
        ],
    }


def planned_entries() -> tuple[PrecountPlanEntry, ...]:
    nomenclator = parse_nomenclator(nomenclator_payload(), election_id=1)
    return plan_aggregate_act_urls(ORIGIN, "PR", nomenclator)


def entry_for(scope_code: str) -> PrecountPlanEntry:
    return next(entry for entry in planned_entries() if entry.scope_code == scope_code)


def test_parses_the_real_indexed_graph_and_plans_only_published_aggregate_codes() -> None:
    nomenclator = parse_nomenclator(nomenclator_payload(), election_id="1")

    assert [scope.index for scope in nomenclator.scopes] == [0, 3, 4, 8, 12]
    assert nomenclator.scope("160010603").parent_indices == (3,)
    assert nomenclator.scope("160010603").mesa_count == 3

    plan = plan_aggregate_act_urls(f"{ORIGIN}/", "PR", nomenclator)
    assert [(entry.grain, entry.scope_code) for entry in plan] == [
        ("national", "00"),
        ("department", "16"),
        ("municipality", "16001"),
        ("zone", "1600106"),
        ("polling_place", "160010603"),
    ]
    assert plan[-1].source_url == f"{ORIGIN}/json/ACT/PR/160010603.json"
    assert all(entry.department_code in {"00", "16"} for entry in plan)
    assert not any(entry.kind == "mesa" for entry in plan)


def test_plans_and_parses_each_published_subnational_aggregate_grain() -> None:
    nomenclator = parse_nomenclator(nomenclator_with_comuna_payload(), election_id=1)
    plan = plan_aggregate_act_urls(ORIGIN, "PR", nomenclator)

    assert [(entry.grain, entry.scope_code) for entry in plan] == [
        ("national", "00"),
        ("department", "16"),
        ("municipality", "16001"),
        ("zone", "1600106"),
        ("comuna", "16001061"),
        ("polling_place", "160010603"),
    ]
    for entry in plan:
        parsed = parse_precount_act(
            act_payload(entry.scope_code, department_code=entry.department_code), expected=entry
        )
        assert (parsed.grain, parsed.scope_code, parsed.department_code) == (
            entry.grain,
            entry.scope_code,
            entry.department_code,
        )


def test_rejects_comuna_schema_drift_instead_of_planning_a_guess() -> None:
    payload = nomenclator_with_comuna_payload()
    nodes = payload["amb"][0]["ambitos"]  # type: ignore[index]
    nodes[4]["c"] = "1600106A"  # type: ignore[index]

    with pytest.raises(PrecountSchemaError, match="canonical decimal"):
        parse_nomenclator(payload, election_id=1)


def test_enumerates_only_fetched_mapagan_mesas_without_filling_nomenclator_gaps() -> None:
    nomenclator = parse_nomenclator(nomenclator_payload(), election_id=1)
    place = nomenclator.scope("160010603")
    payload = act_payload(
        place.code,
        mesa_ids=("160010603000002", "160010603000001"),
    )

    mesas = enumerate_mesa_act_urls(ORIGIN, "PR", place, payload)

    assert place.mesa_count == 3
    assert [entry.scope_code for entry in mesas] == [
        "160010603000001",
        "160010603000002",
    ]
    assert mesas[0] == PrecountPlanEntry(
        source_url=f"{ORIGIN}/json/ACT/PR/160010603000001.json",
        election_id="1",
        election_siglas="PR",
        scope_code="160010603000001",
        scope_level=7,
        grain="mesa",
        kind="mesa",
        department_code="16",
        parent_scope_code="160010603",
    )


def test_accepts_official_alphanumeric_11_character_places_and_17_character_mesas() -> None:
    payload = nomenclator_payload()
    nodes = payload["amb"][0]["ambitos"]  # type: ignore[index]
    codes_by_level = {2: "23", 3: "23139", 4: "2313999", 6: "2313999A900"}
    for node in nodes:
        if node["l"] in codes_by_level:  # type: ignore[index]
            node["c"] = codes_by_level[node["l"]]  # type: ignore[index]
    nomenclator = parse_nomenclator(payload, election_id=1)
    place = nomenclator.scope("2313999A900")

    mesas = enumerate_mesa_act_urls(
        ORIGIN,
        "PR",
        place,
        act_payload(
            place.code,
            department_code="23",
            mesa_ids=("2313999A900000001",),
        ),
    )

    assert mesas[0].scope_code == "2313999A900000001"
    assert mesas[0].source_url.endswith("/json/ACT/PR/2313999A900000001.json")
    parsed = parse_precount_act(
        act_payload(mesas[0].scope_code, department_code="23"),
        expected=mesas[0],
    )
    assert parsed.scope_code == "2313999A900000001"


@pytest.mark.parametrize(
    ("scope_code", "expected_grain"),
    [
        ("00", "national"),
        ("160010603", "polling_place"),
        ("160010603000001", "mesa"),
    ],
)
def test_parses_real_national_place_and_mesa_act_shapes(
    scope_code: str, expected_grain: str
) -> None:
    if expected_grain == "mesa":
        nomenclator = parse_nomenclator(nomenclator_payload(), election_id=1)
        place = nomenclator.scope("160010603")
        expected = enumerate_mesa_act_urls(
            ORIGIN,
            "PR",
            place,
            act_payload(place.code, mesa_ids=(scope_code,)),
        )[0]
    else:
        expected = entry_for(scope_code)
    department_code = "00" if expected_grain == "national" else "16"

    parsed = parse_precount_act(
        act_payload(scope_code, department_code=department_code),
        expected=expected,
    )

    assert parsed.grain == expected_grain
    assert parsed.scope_code == scope_code
    metrics = {metric.name: metric for metric in parsed.totals}
    assert metrics["mesesc"].value == 122017
    assert metrics["pmesesc"].raw == "99,99%"
    assert metrics["pmesesc"].value == Decimal("99.99")
    assert metrics["votnma"].raw == "0"
    assert metrics["votnma"].value == 0
    assert metrics["votnma"].state == "observed"
    assert [candidate.party_code for candidate in parsed.candidates] == ["2", "3"]
    assert parsed.candidates[0].votes.raw == "12708712"
    assert parsed.candidates[0].vote_share.value == Decimal("48.70")
    assert parsed.candidates[1].running_mate_given_names == "JOSÉ\u00a0MANUEL"
    assert not hasattr(parsed.candidates[0], "cedula")


def test_unknown_unavailable_and_zero_remain_distinct_and_keep_raw_source_values() -> None:
    payload = act_payload("00", department_code="00")
    total_act = payload["totales"]["act"]  # type: ignore[index]
    total_act["absten"] = "pendiente"  # type: ignore[index]
    total_act["centota"] = None  # type: ignore[index]

    parsed = parse_precount_act(payload, expected=entry_for("00"))
    metrics = {metric.name: metric for metric in parsed.totals}

    assert (metrics["absten"].raw, metrics["absten"].state, metrics["absten"].value) == (
        "pendiente",
        "unknown",
        None,
    )
    assert (
        metrics["centota"].raw,
        metrics["centota"].state,
        metrics["centota"].value,
    ) == (None, "unavailable", None)
    assert (metrics["votnma"].raw, metrics["votnma"].state, metrics["votnma"].value) == (
        "0",
        "observed",
        0,
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://official.example.co",
        "https://user@official.example.co",
        "https://official.example.co:443",
        "https://official.example.co/json/ACT",
        "https://attacker.invalid",
        "https://official.example.co/?next=https://attacker.invalid",
        "https://official.example.co/#fragment",
    ],
)
def test_rejects_noncanonical_or_unsafe_act_origins(base_url: str) -> None:
    with pytest.raises(PrecountSchemaError, match="HTTPS origin"):
        plan_aggregate_act_urls(
            base_url,
            "PR",
            parse_nomenclator(nomenclator_payload(), election_id=1),
        )


def test_accepts_reviewed_first_round_origin_without_inheriting_second_round_host() -> None:
    first_round_origin = "https://resultadosprecpresidente2026-1v.registraduria.gov.co"
    plan = plan_aggregate_act_urls(
        first_round_origin,
        "PR",
        parse_nomenclator(nomenclator_payload(), election_id=1),
    )
    assert all(entry.source_url.startswith(first_round_origin) for entry in plan)


def test_published_level_seven_nodes_are_validated_but_never_planned_as_mesas() -> None:
    payload = nomenclator_payload()
    nodes = payload["amb"][0]["ambitos"]  # type: ignore[index]
    place = next(node for node in nodes if node["i"] == 8)
    place["h"] = [{"l": 7, "p": [9]}]
    nodes.append(
        {
            "i": 9,
            "n": "Mesa 1",
            "c": "160010603000001",
            "s": "ABRAHAM-LINCOLN-Mesa-1",
            "l": 7,
            "m": 0,
            "p": [{"l": 6, "p": [8]}],
            "r": [9],
            "h": [],
        }
    )
    parsed = parse_nomenclator(payload, election_id=1)
    assert parsed.scope("160010603000001").level == 7
    plan = plan_aggregate_act_urls(ORIGIN, "PR", parsed)
    assert all(entry.grain != "mesa" for entry in plan)


def test_rejects_cross_origin_or_tampered_plan_entry_against_reviewed_origin() -> None:
    expected = replace(
        entry_for("00"),
        source_url="https://resultadosprecpresidente2026-1v.registraduria.gov.co/json/ACT/PR/00.json",
    )
    with pytest.raises(PrecountSchemaError, match="source URL does not match"):
        parse_precount_act(
            act_payload("00", department_code="00"),
            expected=expected,
            reviewed_origin=ORIGIN,
        )

    tampered = replace(entry_for("00"), source_url=f"{ORIGIN}/json/ACT/PR/16.json")
    with pytest.raises(PrecountSchemaError, match="source URL does not match"):
        parse_precount_act(
            act_payload("00", department_code="00"),
            expected=tampered,
            reviewed_origin=ORIGIN,
        )


@pytest.mark.parametrize("siglas", ["pr", "../PR", "PR/../../x", "PR%2Fx", ""])
def test_rejects_unsafe_election_path_segments(siglas: str) -> None:
    with pytest.raises(PrecountSchemaError, match="siglas"):
        plan_aggregate_act_urls(
            ORIGIN,
            siglas,
            parse_nomenclator(nomenclator_payload(), election_id=1),
        )


def test_rejects_duplicate_and_internally_inconsistent_nomenclator_graphs() -> None:
    duplicate_code = nomenclator_payload()
    duplicate_nodes = duplicate_code["amb"][0]["ambitos"]  # type: ignore[index]
    duplicate_nodes[3]["c"] = "00"  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match="duplicate.*scope code"):
        parse_nomenclator(duplicate_code, election_id=1)

    disagreement = nomenclator_payload()
    disagreement_nodes = disagreement["amb"][0]["ambitos"]  # type: ignore[index]
    disagreement_nodes[0]["p"] = [{"l": 4, "p": [4]}]  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match="parent level|references disagree"):
        parse_nomenclator(disagreement, election_id=1)

    ambiguous_election = nomenclator_payload()
    ambiguous_election["amb"].append(deepcopy(ambiguous_election["amb"][0]))  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match="exactly one election"):
        parse_nomenclator(ambiguous_election, election_id=1)


@pytest.mark.parametrize(
    "mesa_code",
    [
        "160010603/../../1",
        "https://evil.invalid",
        "160010604000001",
        "16001060300001",
    ],
)
def test_rejects_malicious_or_cross_place_mapagan_identifiers(mesa_code: str) -> None:
    nomenclator = parse_nomenclator(nomenclator_payload(), election_id=1)
    place = nomenclator.scope("160010603")
    with pytest.raises(PrecountSchemaError):
        enumerate_mesa_act_urls(
            ORIGIN,
            "PR",
            place,
            act_payload(place.code, mesa_ids=(mesa_code,)),
        )


def test_rejects_duplicate_or_mismatched_polling_place_mesa_discovery() -> None:
    nomenclator = parse_nomenclator(nomenclator_payload(), election_id=1)
    place = nomenclator.scope("160010603")
    duplicate = act_payload(
        place.code,
        mesa_ids=("160010603000001", "160010603000001"),
    )
    with pytest.raises(PrecountSchemaError, match="duplicate mapagan"):
        enumerate_mesa_act_urls(ORIGIN, "PR", place, duplicate)

    wrong_scope = act_payload("160010604", mesa_ids=("160010604000001",))
    with pytest.raises(PrecountSchemaError, match="scope identity"):
        enumerate_mesa_act_urls(ORIGIN, "PR", place, wrong_scope)

    alpha_suffix = act_payload(place.code, mesa_ids=("16001060300A001",))
    with pytest.raises(PrecountSchemaError, match="suffix"):
        enumerate_mesa_act_urls(ORIGIN, "PR", place, alpha_suffix)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("votant", "-1", "nonnegative integer string"),
        ("votant", 1, "source string"),
        ("pvotant", "63.60%", "Colombian percentage"),
        ("pvotant", "100,01%", "between 0 and 100"),
    ],
)
def test_rejects_invalid_counts_and_non_colombian_percentages(
    field: str, value: object, message: str
) -> None:
    payload = act_payload("00", department_code="00")
    payload["totales"]["act"][field] = value  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match=message):
        parse_precount_act(payload, expected=entry_for("00"))


def test_rejects_act_candidate_and_source_identity_conflicts() -> None:
    forged_source = replace(entry_for("00"), source_url="https://attacker.invalid/00.json")
    with pytest.raises(PrecountSchemaError, match="source URL"):
        parse_precount_act(act_payload("00", department_code="00"), expected=forged_source)

    scope_mismatch = act_payload("00", department_code="00")
    scope_mismatch["amb"] = "16"
    with pytest.raises(PrecountSchemaError, match="scope identity"):
        parse_precount_act(scope_mismatch, expected=entry_for("00"))

    candidate_mismatch = act_payload("00", department_code="00")
    candidate = candidate_mismatch["camaras"][0]["partotabla"][0]["act"]["cantotabla"][0]  # type: ignore[index]
    candidate["amb"] = "16"  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match="candidate scope identity"):
        parse_precount_act(candidate_mismatch, expected=entry_for("00"))

    vote_mismatch = act_payload("00", department_code="00")
    candidate = vote_mismatch["camaras"][0]["partotabla"][0]["act"]["cantotabla"][0]  # type: ignore[index]
    candidate["vot"] = "1"  # type: ignore[index]
    with pytest.raises(PrecountSchemaError, match="candidate and party"):
        parse_precount_act(vote_mismatch, expected=entry_for("00"))
