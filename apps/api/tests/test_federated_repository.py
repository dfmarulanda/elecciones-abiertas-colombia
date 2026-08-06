"""Configuring Postgres must not silently stop serving the historical releases.

``select_repository`` returns exactly one repository and ``DATABASE_URL`` wins,
so before federation the 2026 deployment would have dropped 2018 and 2022 from
the catalogue with no error raised anywhere. These tests pin that behaviour,
because the failure is invisible: the API keeps working and simply knows about
fewer elections.
"""

from typing import Any

import pytest
from elecciones_api.federated_repository import FederatedRepository
from elecciones_api.historical_repository import HistoricalDuckDBRepository
from elecciones_api.repository import (
    PostgresReadRepository,
    ReleaseNotFoundError,
    RepositoryUnavailableError,
)


# ``data_version`` and ``is_fixture`` are properties on every real backend and
# on ``ReadRepository``. Earlier fakes declared them as plain methods, which is
# why a FederatedRepository that also declared them as methods looked correct
# under test while the routes received a bound method object in production.
class _FakeHistorical:
    is_fixture = False

    def __init__(self, release_ids: list[str]) -> None:
        self._releases = {release_id: {} for release_id in release_ids}

    def public_elections(self) -> list[dict[str, object]]:
        return [
            {"release_id": release_id, "election_slug": "hist"}
            for release_id in self._releases
        ]

    def normalized_summary(self, release_id: str, *_: Any, **__: Any) -> dict[str, object]:
        return {"served_by": "duckdb", "release_id": release_id}

    @property
    def data_version(self) -> str:
        return next(iter(self._releases))


class _FakePostgres:
    is_fixture = False

    def __init__(self, data_version_error: Exception | None = None) -> None:
        self._data_version_error = data_version_error

    def public_elections(self) -> list[dict[str, object]]:
        return [{"release_id": "candidate-2026", "election_slug": "presidencia"}]

    def normalized_summary(self, release_id: str, *_: Any, **__: Any) -> dict[str, object]:
        return {"served_by": "postgres", "release_id": release_id}

    def normalized_children_results(self, release_id: str, *_: Any, **__: Any) -> dict[str, object]:
        return {"served_by": "postgres", "release_id": release_id}

    @property
    def data_version(self) -> str:
        if self._data_version_error is not None:
            raise self._data_version_error
        return "candidate-2026"

    def summary(self, *_: Any, **__: Any) -> str:
        """A legacy, non-release-scoped read."""
        return "legacy-postgres"


def _federated(postgres: _FakePostgres | None = None) -> FederatedRepository:
    return FederatedRepository(
        postgres or _FakePostgres(),  # type: ignore[arg-type]
        _FakeHistorical(["historical-2018", "historical-2022"]),  # type: ignore[arg-type]
    )


def test_catalogue_keeps_all_three_elections() -> None:
    """The regression this class exists for."""
    catalogue = _federated().public_elections()
    assert {row["release_id"] for row in catalogue} == {
        "historical-2018",
        "historical-2022",
        "candidate-2026",
    }


@pytest.mark.parametrize(
    ("release_id", "backend"),
    [
        ("historical-2018", "duckdb"),
        ("historical-2022", "duckdb"),
        ("candidate-2026", "postgres"),
    ],
)
def test_release_scoped_reads_route_by_release_id(release_id: str, backend: str) -> None:
    result = _federated().normalized_summary(release_id, "slug")
    assert result["served_by"] == backend
    assert result["release_id"] == release_id


def test_children_results_refuses_a_compact_context_release() -> None:
    """The lean projection has no compact-model equivalent; it must not fall
    through to Postgres and answer about a release Postgres does not hold."""
    with pytest.raises(ReleaseNotFoundError):
        _federated().normalized_children_results("historical-2018", "slug", "CO", None, None, 50)


def test_unknown_release_falls_to_postgres_not_duckdb() -> None:
    """An id neither backend declares must not be answered by DuckDB, which
    would report a historical release for an arbitrary identifier."""
    assert _federated().normalized_summary("unknown", "slug")["served_by"] == "postgres"


def test_legacy_reads_go_to_the_active_backend() -> None:
    assert _federated().summary("slug", None) == "legacy-postgres"


def test_data_version_is_a_string_attribute_not_a_bound_method() -> None:
    """The routes read ``repository.data_version`` as a plain attribute and put
    the value straight into JSON responses and cursor scopes. A method here
    yields an unserialisable bound method rather than the release id."""
    assert _federated().data_version == "candidate-2026"


@pytest.mark.parametrize(
    "error",
    [
        ReleaseNotFoundError("not loaded yet"),
        RepositoryUnavailableError("read model unreachable"),
    ],
)
def test_data_version_falls_back_to_duckdb_when_postgres_cannot_name_it(
    error: Exception,
) -> None:
    federated = _federated(_FakePostgres(data_version_error=error))
    assert federated.data_version == "historical-2018"


def test_data_version_does_not_mask_defects_as_a_stale_release() -> None:
    """Answering an arbitrary bug with a historical release id would report the
    wrong election as the site's active data version."""
    federated = _federated(_FakePostgres(data_version_error=TypeError("defect")))
    with pytest.raises(TypeError):
        _ = federated.data_version


def test_is_fixture_is_falsey() -> None:
    """As a method this was a bound method: always truthy, which routed the
    production dataset download into the synthetic-fixture branch."""
    assert _federated().is_fixture is False
    assert not _federated().is_fixture


@pytest.mark.parametrize("name", ["data_version", "is_fixture"])
def test_shape_matches_the_backends_the_routes_already_serve(name: str) -> None:
    """Pins the attribute shape the HTTP layer depends on: whatever these are on
    a real backend, they must be the same kind of thing on the federation."""
    federated = getattr(FederatedRepository, name)
    postgres = getattr(PostgresReadRepository, name)
    historical = getattr(HistoricalDuckDBRepository, name)
    assert callable(federated) is callable(postgres)
    assert callable(federated) is callable(historical)
