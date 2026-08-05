from __future__ import annotations

import pytest
from elecciones_pipeline.ingest.scrutiny import (
    ScrutinyManifestError,
    ScrutinyPlanEntry,
    plan_scrutiny_manifest,
)


def test_plans_the_real_prefix_to_filename_index_shape_deterministically() -> None:
    index = {
        "data/esc/v1/municipios/11/001/": "resultados.json",
        "data/esc/v1/departamentos/11/": "totales.json",
    }

    assert plan_scrutiny_manifest("https://official.gov.co/", index) == (
        ScrutinyPlanEntry(
            source_url="https://official.gov.co/data/esc/v1/departamentos/11/totales.json",
            source_path="data/esc/v1/departamentos/11/totales.json",
            category="departamentos",
        ),
        ScrutinyPlanEntry(
            source_url="https://official.gov.co/data/esc/v1/municipios/11/001/resultados.json",
            source_path="data/esc/v1/municipios/11/001/resultados.json",
            category="municipios",
        ),
    )


@pytest.mark.parametrize(
    ("base_url", "index"),
    [
        ("http://official.gov.co/", {}),
        ("https://official.gov.co/?next=https://attacker.invalid", {}),
        ("https://official.gov.co/data/index.json", {}),
        ("https://official.gov.co/", {"../data/esc/v1/x/": "file.json"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "../file.json"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "file.json?next=bad"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "file.json#fragment"}),
        ("https://official.gov.co/", {"https://attacker.invalid/data/esc/v1/x/": "file.json"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "//attacker.invalid/file.json"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "%2e%2e.json"}),
        ("https://official.gov.co/", {"data/esc/v1/x/": "/file.json"}),
    ],
)
def test_rejects_malicious_or_non_normalized_manifest_inputs(base_url: str, index: object) -> None:
    with pytest.raises(ScrutinyManifestError):
        plan_scrutiny_manifest(base_url, index)  # type: ignore[arg-type]


def test_rejects_non_pair_index_values_and_wrong_scrutiny_prefix() -> None:
    with pytest.raises(ScrutinyManifestError, match="single filenames"):
        plan_scrutiny_manifest("https://official.gov.co/", {"data/esc/v1/x/": "nested/file.json"})
    with pytest.raises(ScrutinyManifestError, match="data/esc/v1"):
        plan_scrutiny_manifest("https://official.gov.co/", {"data/other/x/": "file.json"})


class _RepeatedPairs(dict[str, object]):
    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        self._pairs = pairs

    def items(self):  # type: ignore[override]
        return iter(self._pairs)


def test_duplicate_and_conflicting_pairs_fail_closed() -> None:
    duplicate = _RepeatedPairs([("data/esc/v1/x/", "file.json"), ("data/esc/v1/x/", "file.json")])
    conflict = _RepeatedPairs([("data/esc/v1/x/", "one.json"), ("data/esc/v1/x/", "two.json")])

    with pytest.raises(ScrutinyManifestError, match="duplicate"):
        plan_scrutiny_manifest("https://official.gov.co/", duplicate)
    with pytest.raises(ScrutinyManifestError, match="conflicting"):
        plan_scrutiny_manifest("https://official.gov.co/", conflict)
