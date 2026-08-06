"""Serve Postgres-backed and DuckDB-backed releases from one origin.

``select_repository`` returns exactly one repository and ``DATABASE_URL`` wins,
so configuring Postgres for the 2026 release would silently stop serving the
2018 and 2022 historical context releases — the catalogue would simply lose two
elections with no error anywhere. Since the whole point of the site is reading
three elections measured by the same code, that failure is invisible in exactly
the way that matters.

This routes every release-scoped call by ``release_id`` to whichever backend
holds that release, and concatenates the catalogue. Legacy ``/elections/*``
routes and anything else that is not release-scoped go to Postgres, which is
the active-release backend.
"""

from collections.abc import Iterable, Iterator
from typing import Any, cast

from .historical_repository import HistoricalDuckDBRepository
from .repository import (
    PostgresReadRepository,
    ReleaseNotFoundError,
    RepositoryUnavailableError,
)


class FederatedRepository:
    """Dispatch by release id; hold no data of its own."""

    def __init__(
        self,
        postgres: PostgresReadRepository,
        historical: HistoricalDuckDBRepository,
    ) -> None:
        self._postgres = postgres
        self._historical = historical

    # ── routing ──────────────────────────────────────────────────────────────

    def holds_historical(self, release_id: str) -> bool:
        """Whether the DuckDB half owns this release."""
        return release_id in getattr(self._historical, "_releases", {})

    def backend_for(self, release_id: str) -> Any:
        """The concrete backend that owns this release.

        Public because a handful of reads are named without a release-routing
        prefix (``datasets``, ``dataset_file``) and so cannot be dispatched by
        the methods below; the routes resolve the backend themselves instead of
        falling through ``__getattr__`` to Postgres for a DuckDB-held release.
        """
        return self._historical if self.holds_historical(release_id) else self._postgres

    def _for(self, release_id: str) -> Any:
        return self.backend_for(release_id)

    # ── whole-repository surface ─────────────────────────────────────────────

    # ``is_fixture`` and ``data_version`` are properties on every backend and on
    # the ``ReadRepository`` protocol, and the HTTP layer reads them as plain
    # attributes. Defining them as methods here handed the routes a bound method
    # instead: truthy for ``is_fixture`` (so production dataset downloads took
    # the synthetic-fixture branch) and unserialisable for ``data_version``.
    @property
    def is_fixture(self) -> bool:
        return False

    @property
    def data_version(self) -> str:
        """The active release. Postgres owns it unless DuckDB declares it."""
        try:
            return self._postgres.data_version
        except (ReleaseNotFoundError, RepositoryUnavailableError):
            # Both mean "Postgres cannot name the active release yet" — the
            # release is not loaded, or the read model is unreachable. Anything
            # else is a defect and must not be answered with a stale version.
            return self._historical.data_version

    def public_elections(self) -> list[dict[str, object]]:
        """One catalogue over both backends, ordered as each already orders."""
        return [*self._historical.public_elections(), *self._postgres.public_elections()]

    # ── release-scoped reads: routed ─────────────────────────────────────────

    def normalized_results(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_results(release_id, *args, **kwargs)

    def iter_normalized_results(
        self, release_id: str, *args: Any, **kwargs: Any
    ) -> Iterator[dict[str, object]]:
        return cast(
            Iterator[dict[str, object]],
            self._for(release_id).iter_normalized_results(release_id, *args, **kwargs),
        )

    def normalized_geography_path(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_geography_path(release_id, *args, **kwargs)

    def normalized_geography_children(
        self, release_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        return self._for(release_id).normalized_geography_children(
            release_id, *args, **kwargs
        )

    def normalized_geography(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_geography(release_id, *args, **kwargs)

    def normalized_mesa(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_mesa(release_id, *args, **kwargs)

    def normalized_categories(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_categories(release_id, *args, **kwargs)

    def normalized_summary(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_summary(release_id, *args, **kwargs)

    def normalized_children_results(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        """Postgres-only: the DuckDB compact model has no such projection."""
        if self.holds_historical(release_id):
            raise ReleaseNotFoundError(
                "Children-with-results is not available for a compact context release."
            )
        return self._postgres.normalized_children_results(release_id, *args, **kwargs)

    def normalized_outcome_sensitivity(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_outcome_sensitivity(
            release_id, *args, **kwargs
        )

    def normalized_comparison(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_comparison(release_id, *args, **kwargs)

    def normalized_datasets(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_datasets(release_id, *args, **kwargs)

    def normalized_dataset_artifact(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).normalized_dataset_artifact(
            release_id, *args, **kwargs
        )

    def analysis_summary_for(self, release_id: str, *args: Any, **kwargs: Any) -> Any:
        return self._for(release_id).analysis_summary_for(release_id, *args, **kwargs)

    # ── legacy-shaped reads that still name a release ────────────────────────
    #
    # These take the release as their ``version`` argument rather than as a
    # leading ``release_id``, so they look non-release-scoped and would fall
    # through ``__getattr__`` to Postgres. The release-scoped dataset routes
    # call them, so leaving them unrouted 404s every historical dataset.

    def datasets(self, slug: str, version: str | None = None, *args: Any, **kwargs: Any) -> Any:
        return self._for(version or "").datasets(slug, version, *args, **kwargs)

    def dataset(self, dataset_id: str, version: str | None = None, *args: Any, **kwargs: Any) -> Any:
        return self._for(version or "").dataset(dataset_id, version, *args, **kwargs)

    def raw_dataset_rows(
        self, dataset_id: str, version: str | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        return self._for(version or "").raw_dataset_rows(dataset_id, version, *args, **kwargs)

    def dataset_artifact_url(
        self, dataset_id: str, version: str | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        return self._for(version or "").dataset_artifact_url(dataset_id, version, *args, **kwargs)

    # ── everything else: the active-release backend ──────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Legacy, non-release-scoped reads go to Postgres.

        Deliberately not a silent catch-all for release-scoped methods: those
        are all named explicitly above, so a new one added upstream fails loudly
        here instead of quietly answering from the wrong backend.
        """
        return getattr(self._postgres, name)

    def close(self) -> None:
        for backend in (self._postgres, self._historical):
            closer = getattr(backend, "close", None)
            if callable(closer):
                closer()

    @property
    def backends(self) -> Iterable[object]:
        return (self._postgres, self._historical)
