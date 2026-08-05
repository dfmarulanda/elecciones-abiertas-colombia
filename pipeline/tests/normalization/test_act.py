# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from elecciones_pipeline.normalization import (
    ActSchemaError,
    SourceSnapshot,
    aggregate_complete_mesa_facts,
    canonical_mesa_id,
    parse_localized_integer,
    parse_localized_percentage,
    parse_precount_act,
)


def snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        source_id="precount",
        source_type="pre_count",
        legal_status="preliminary",
        source_url="https://official.example.co/act",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="a" * 64,
        parser_version="act-v1",
        transform_version="normal-v1",
        data_version="r1",
    )


def payload() -> dict[str, object]:
    return {
        "totales": {"act": {"votes": "1.234", "share": "12,5 %"}},
        "camaras": [{"partotabla": [{"id": "P1", "act": {"votes": "0"}}]}],
    }


def identity(mesa: str = "0001") -> dict[str, str]:
    return {"department": "11", "municipality": "001", "place": "01", "mesa": mesa}


def mesa_id(mesa: str = "0001") -> str:
    return f"11:001:01:{mesa}"


def expected_mesas(*mesas: str) -> dict[str, dict[str, str]]:
    return {mesa_id(mesa): identity(mesa) for mesa in mesas}


def test_localized_values_and_zero_are_distinct_from_unknown() -> None:
    assert parse_localized_integer("1.234") == 1234
    assert str(parse_localized_percentage("12,5 %")) == "12.5"
    rows = parse_precount_act(
        payload(),
        snapshot=snapshot(),
        identity=identity(),
        total_fields={"votes": "votes"},
        party_fields={"votes": "votes"},
        verified_mesa_ids={mesa_id()},
    )
    assert [row["value"] for row in rows] == [1234, 0]
    assert {row["value_state"] for row in rows} == {"observed"}
    changed = payload()
    changed["totales"] = {"act": {"votes": "pendiente", "share": "12,5 %"}}
    rows = parse_precount_act(
        changed,
        snapshot=snapshot(),
        identity=identity(),
        total_fields={"votes": "votes"},
        party_fields={"votes": "votes"},
        verified_mesa_ids={mesa_id()},
    )
    assert rows[0]["value"] is None and rows[0]["value_state"] == "unknown"


def test_act_shape_and_official_identity_are_strict() -> None:
    with pytest.raises(ActSchemaError, match="totales.act"):
        parse_precount_act(
            {"totales": {}, "camaras": []},
            snapshot=snapshot(),
            identity=identity(),
            total_fields={"votes": "votes"},
            party_fields={},
            verified_mesa_ids={mesa_id()},
        )
    with pytest.raises(ActSchemaError, match="declared"):
        canonical_mesa_id(verified_mesa_id="invented", verified_ids={"official"})
    assert (
        canonical_mesa_id(
            department="11", municipality="001", place="01", mesa="0001", verified_ids={mesa_id()}
        )
        == mesa_id()
    )
    with pytest.raises(ActSchemaError, match="verified manifest"):
        canonical_mesa_id(department="11", municipality="001", place="01", mesa="0001")


def test_each_fact_keeps_provenance_and_source_layers_never_merge() -> None:
    rows = parse_precount_act(
        payload(),
        snapshot=snapshot(),
        identity=identity(),
        total_fields={"votes": "votes"},
        party_fields={"votes": "votes"},
        verified_mesa_ids={mesa_id()},
    )
    assert all(
        row["source_layer"] == "pre_count" and row["content_hash"] == "a" * 64 for row in rows
    )
    assert {row["record_type"] for row in rows} == {"total", "party"}


def test_aggregation_remains_source_local_and_skips_incomplete_groups() -> None:
    rows = list(
        parse_precount_act(
            payload(),
            snapshot=snapshot(),
            identity=identity(),
            verified_mesa_ids={mesa_id()},
            total_fields={"votes": "votes"},
            party_fields={"votes": "votes"},
        )
    )
    rows[0]["value_state"] = "unavailable"
    rows[0]["value"] = None
    assert aggregate_complete_mesa_facts(
        rows, level="place", expected_mesa_hierarchy=expected_mesas("0001")
    )
    assert not [
        row
        for row in aggregate_complete_mesa_facts(
            rows, level="place", expected_mesa_hierarchy=expected_mesas("0001")
        )
        if row["record_type"] == "total"
    ]


def test_rejects_naive_timestamp_and_non_precount_snapshot() -> None:
    with pytest.raises(ActSchemaError, match="timezone-aware"):
        SourceSnapshot(**{**snapshot().__dict__, "retrieved_at": datetime(2026, 1, 1)})
    with pytest.raises(ActSchemaError, match="source_type=pre_count"):
        parse_precount_act(
            payload(),
            snapshot=SourceSnapshot(**{**snapshot().__dict__, "source_layer": "final"}),
            identity=identity(),
            total_fields={"votes": "votes"},
            party_fields={"votes": "votes"},
            verified_mesa_ids={mesa_id()},
        )


def test_rollup_requires_every_expected_mesa_and_keeps_all_raw_provenance() -> None:
    first = list(
        parse_precount_act(
            payload(),
            snapshot=snapshot(),
            identity=identity("0001"),
            total_fields={"votes": "votes"},
            party_fields={},
            verified_mesa_ids={mesa_id("0001")},
        )
    )
    second_snapshot = SourceSnapshot(
        **{
            **snapshot().__dict__,
            "source_url": "https://official.example.co/act/2",
            "content_hash": "b" * 64,
        }
    )
    second = list(
        parse_precount_act(
            payload(),
            snapshot=second_snapshot,
            identity=identity("0002"),
            total_fields={"votes": "votes"},
            party_fields={},
            verified_mesa_ids={mesa_id("0002")},
        )
    )
    assert not aggregate_complete_mesa_facts(
        first, level="place", expected_mesa_hierarchy=expected_mesas("0001", "0002")
    )
    result = aggregate_complete_mesa_facts(
        first + second, level="place", expected_mesa_hierarchy=expected_mesas("0001", "0002")
    )
    assert result[0]["value"] == 2468
    assert "source_url" not in result[0] and "content_hash" not in result[0]
    assert result[0]["raw_provenance"] == (
        {
            "source_url": "https://official.example.co/act",
            "content_hash": "a" * 64,
            "retrieved_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "source_url": "https://official.example.co/act/2",
            "content_hash": "b" * 64,
            "retrieved_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_rollup_completeness_is_scoped_to_each_verified_geography() -> None:
    first = list(
        parse_precount_act(
            payload(),
            snapshot=snapshot(),
            identity=identity("0001"),
            total_fields={"votes": "votes"},
            party_fields={},
            verified_mesa_ids={mesa_id("0001")},
        )
    )
    other_identity = {"department": "11", "municipality": "002", "place": "01", "mesa": "0001"}
    other_mesa_id = "11:002:01:0001"
    second = list(
        parse_precount_act(
            payload(),
            snapshot=snapshot(),
            identity=other_identity,
            total_fields={"votes": "votes"},
            party_fields={},
            verified_mesa_ids={other_mesa_id},
        )
    )
    inventory = {mesa_id("0001"): identity("0001"), other_mesa_id: other_identity}
    result = aggregate_complete_mesa_facts(
        first + second, level="place", expected_mesa_hierarchy=inventory
    )
    assert [(row["identity_key"], row["value"]) for row in result] == [
        (("11", "001", "01"), 1234),
        (("11", "002", "01"), 1234),
    ]
