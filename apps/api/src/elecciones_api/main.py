"""FastAPI entry point for immutable, provenance-first election releases."""
# ruff: noqa: E501

import csv
import hashlib
import io
import json
import os
from collections.abc import AsyncIterator, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, TypeVar, cast
from urllib.parse import urlparse

import sentry_sdk
from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel
from sentry_sdk.types import Event, Hint
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .cursor import (
    CursorError,
    decode_cursor,
    decode_keyset_cursor,
    encode_cursor,
    encode_keyset_cursor,
    scope_for,
)
from .federated_repository import FederatedRepository
from .historical_repository import HistoricalDuckDBRepository
from .repository import (
    FixtureRepository,
    PostgresReadRepository,
    ReadRepository,
    ReleaseNotFoundError,
    RepositoryUnavailableError,
    ResourceNotFoundError,
)
from .schemas import (
    AnalysisAnomalyPage,
    AnalysisReport,
    AnalysisSummary,
    Bulletin,
    BulletinResult,
    ComparisonResponse,
    ContextElectionSummary,
    Dataset,
    ElectionSummary,
    EvidenceResponse,
    Geography,
    GeographyChildPage,
    HistoricalComparisonResponse,
    MesaDetail,
    NormalizedCategoryPage,
    OutcomeSensitivity,
    PackagedDataset,
    PreliminaryElectionSummary,
    Provenance,
    ReleaseElectionRef,
    ResultFact,
    ResultPage,
    ReviewSignalPage,
    ScopedGeographyPathResponse,
    ScopedGeographyResponse,
    ScopedMesa,
)

_repository_openapi = Path(__file__).resolve().parents[4] / "packages/contracts/openapi.json"
OPENAPI_PATH = Path(os.environ.get("ELECCIONES_OPENAPI_PATH", _repository_openapi))
FROZEN_OPENAPI = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
HistoricalCache = "public, max-age=3600, stale-while-revalidate=86400"
ImmutableCache = "public, max-age=31536000, immutable"
T = TypeVar("T")


def _scrub_sentry_event(event: Event, _hint: Hint) -> Event:
    """Remove visitor data while retaining exception and release diagnostics."""
    if not isinstance(event, dict):
        return event
    event.pop("user", None)
    request = event.get("request")
    if isinstance(request, dict):
        for field in ("cookies", "data", "env", "headers", "query_string"):
            request.pop(field, None)
        url = request.get("url")
        if isinstance(url, str):
            request["url"] = url.split("?", 1)[0].split("#", 1)[0]
    return event


class APIProblem(Exception):
    def __init__(
        self, status: int, title: str, detail: str, problem_type: str = "about:blank"
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.problem_type = problem_type


def _jsonable(value: object) -> object:
    return jsonable_encoder(value)


def _etag(payload: object) -> str:
    encoded = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":")).encode()
    return f'"{hashlib.sha256(encoded).hexdigest()}"'


def _if_none_match(header: str | None, current: str) -> bool:
    """Apply weak comparison for GET validators as required by If-None-Match."""
    if header is None:
        return False
    if header.strip() == "*":
        return True
    current_opaque = current.removeprefix("W/")
    candidates: list[str] = []
    index = 0
    while index < len(header):
        while index < len(header) and header[index] in " \t":
            index += 1
        if header.startswith("W/", index):
            index += 2
        if index >= len(header) or header[index] != '"':
            return False
        start = index
        index += 1
        while index < len(header) and header[index] != '"':
            value = ord(header[index])
            if value != 0x21 and not (0x23 <= value <= 0x7E or 0x80 <= value <= 0xFF):
                return False
            index += 1
        if index >= len(header):
            return False
        index += 1
        candidates.append(header[start:index])
        while index < len(header) and header[index] in " \t":
            index += 1
        if index == len(header):
            break
        if header[index] != ",":
            return False
        index += 1
        if index == len(header):
            return False
    return current_opaque in candidates


#: Every response carrying preliminary data must say so in a header as well as
#: in its body, so a client that only reads headers — a cache, a proxy, a
#: scraper — cannot mistake a pre-count for a certified result.
DATA_CLASS_HEADER = "X-Election-Data-Class"
PreliminaryCache = "public, max-age=60"


def _cached_json(
    request: Request, payload: object, cache_control: str = HistoricalCache
) -> Response:
    tag = _etag(payload)
    headers = {"ETag": tag, "Cache-Control": cache_control, "Vary": "Origin"}
    # A preliminary payload is short-lived and must never be cached as long as
    # an immutable certified one. The class is read off the payload the
    # repository built, so the label and the grant that authorised it cannot
    # drift apart.
    if isinstance(payload, Mapping) and payload.get("exposure_class") == "preliminary":
        headers[DATA_CLASS_HEADER] = "preliminary"
        headers["Cache-Control"] = PreliminaryCache
    elif isinstance(payload, Mapping) and payload.get("exposure_class") == "certified":
        headers[DATA_CLASS_HEADER] = "certified"
    if _if_none_match(request.headers.get("if-none-match"), tag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(_jsonable(payload), headers=headers)


def _validated_public[M: BaseModel](
    model: type[M], payload: object
) -> dict[str, object]:
    """Validate concrete Response payloads before FastAPI's serializer is bypassed."""
    try:
        return cast(
            dict[str, object],
            model.model_validate(payload).model_dump(mode="json", exclude_unset=True),
        )
    except ValueError as exc:
        raise RepositoryUnavailableError(
            f"A public {model.__name__} payload violates the frozen contract."
        ) from exc


def _problem(
    request: Request, status: int, title: str, detail: str, problem_type: str = "about:blank"
) -> JSONResponse:
    return JSONResponse(
        {
            "type": problem_type,
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.url.path,
        },
        status_code=status,
        media_type="application/problem+json",
    )


def _result_filters(
    results: list[ResultFact],
    source_type: str | None,
    geography_id: str | None,
    geography_level: str | None,
    candidate_id: str | None,
    geography_matches: Callable[[ResultFact, str], bool] | None = None,
) -> list[ResultFact]:
    selected = [
        result
        for result in results
        if (source_type is None or result.provenance.source_type == source_type)
        and (
            geography_id is None
            or result.geography_id == geography_id
            or (geography_matches is not None and geography_matches(result, geography_id))
        )
        and (geography_level is None or result.geography_level == geography_level)
        and (
            candidate_id is None
            or any(item.candidate_id == candidate_id for item in result.candidates)
        )
    ]
    if candidate_id is None:
        return selected
    return [
        result.model_copy(
            update={
                "candidates": [
                    item for item in result.candidates if item.candidate_id == candidate_id
                ]
            }
        )
        for result in selected
    ]


def _csv(results: list[ResultFact]) -> str:
    fields = [
        "id",
        "election_slug",
        "geography_id",
        "geography_level",
        "mesa_id",
        "source_type",
        "legal_status",
        "registered_electors_value",
        "registered_electors_status",
        "voters_value",
        "voters_status",
        "valid_votes_value",
        "valid_votes_status",
        "blank_votes_value",
        "blank_votes_status",
        "null_votes_value",
        "null_votes_status",
        "unmarked_votes_value",
        "unmarked_votes_status",
        "candidates",
        "content_hash",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for result in results:
        row: dict[str, object] = {
            "id": result.id,
            "election_slug": result.election_slug,
            "geography_id": result.geography_id,
            "geography_level": result.geography_level,
            "mesa_id": result.mesa_id or "",
            "source_type": result.provenance.source_type,
            "legal_status": result.provenance.legal_status,
            "candidates": json.dumps(
                [item.model_dump(mode="json") for item in result.candidates], separators=(",", ":")
            ),
            "content_hash": result.provenance.content_hash,
        }
        for metric in (
            "registered_electors",
            "voters",
            "valid_votes",
            "blank_votes",
            "null_votes",
            "unmarked_votes",
        ):
            value = getattr(result, metric)
            row[f"{metric}_value"] = "" if value.value is None else value.value
            row[f"{metric}_status"] = value.status
        writer.writerow(_csv_safe_row(row))
    return output.getvalue()


def _csv_cell(value: object) -> object:
    """Prevent spreadsheet formula evaluation for every textual CSV field."""
    if not isinstance(value, str):
        return value
    return f"'{value}" if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _csv_safe_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _csv_cell(value) for key, value in row.items()}


def _allowlisted_artifact_url(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname.lower() not in allowed_hosts
    ):
        raise APIProblem(
            500,
            "Invalid dataset artifact",
            "The immutable dataset artifact URL is not an allowlisted HTTPS URL.",
        )
    return url


def _allowlisted_document_url(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or not parsed.hostname
        or parsed.hostname.lower().rstrip(".") not in allowed_hosts
    ):
        raise APIProblem(
            503,
            "Invalid document evidence",
            "The release contains a document URL outside the exact official-host policy.",
        )
    return url


def _normalized_fact(
    row: dict[str, object], release_id: str, election_slug: str
) -> dict[str, object]:
    raw_metrics = row["metrics"]
    metrics = (
        json.loads(raw_metrics)
        if isinstance(raw_metrics, str)
        else cast(dict[str, object], raw_metrics)
    )
    fact = {
        "id": row["id"],
        "election_slug": election_slug,
        "geography_id": row["geography_id"],
        "geography_level": row["geography_level"],
        "mesa_id": row["mesa_id"],
        **metrics,
        "candidates": [],
        "provenance": {
            "data_version": release_id,
            "source_type": row["source_type"],
            "legal_status": row["legal_status"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "content_hash": row["content_hash"],
            "parser_version": row["parser_version"],
            "transform_version": row["transform_version"],
            "methodology_version": None,
        },
    }
    # Do not emit partially-imported or malformed public facts.  This also
    # validates source/legal/data-version invariants at the repository boundary.
    try:
        return ResultFact.model_validate(fact).model_dump(mode="json")
    except ValueError as exc:
        raise RepositoryUnavailableError(
            "A normalized public fact violates release invariants."
        ) from exc


def _normalized_csv_row(row: dict[str, object], release_id: str, election_slug: str) -> str:
    """One CSV record with immutable provenance; used by the streaming export."""
    fact = _normalized_fact(row, release_id, election_slug)
    output = io.StringIO(newline="")
    fields = [
        "id",
        "election_slug",
        "data_version",
        "geography_id",
        "geography_level",
        "mesa_id",
        "source_id",
        "source_type",
        "legal_status",
        "source_url",
        "retrieved_at",
        "content_hash",
        "parser_version",
        "transform_version",
        "registered_electors_value",
        "registered_electors_status",
        "voters_value",
        "voters_status",
        "valid_votes_value",
        "valid_votes_status",
        "blank_votes_value",
        "blank_votes_status",
        "null_votes_value",
        "null_votes_status",
        "unmarked_votes_value",
        "unmarked_votes_status",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    provenance = cast(dict[str, object], fact["provenance"])
    values: dict[str, object] = {
        "id": fact["id"],
        "election_slug": fact["election_slug"],
        "data_version": release_id,
        "geography_id": fact["geography_id"],
        "geography_level": fact["geography_level"],
        "mesa_id": fact["mesa_id"] or "",
        "source_id": row["source_id"],
        **{
            key: provenance[key]
            for key in (
                "source_type",
                "legal_status",
                "source_url",
                "retrieved_at",
                "content_hash",
                "parser_version",
                "transform_version",
            )
        },
    }
    for metric in (
        "registered_electors",
        "voters",
        "valid_votes",
        "blank_votes",
        "null_votes",
        "unmarked_votes",
    ):
        metric_value = cast(dict[str, object], fact[metric])
        values[f"{metric}_value"] = "" if metric_value["value"] is None else metric_value["value"]
        values[f"{metric}_status"] = metric_value["status"]
    writer.writerow(_csv_safe_row(values))
    return output.getvalue()


def _normalized_csv_header() -> str:
    # Reuse the row writer so header order cannot silently diverge from data.
    return "id,election_slug,data_version,geography_id,geography_level,mesa_id,source_id,source_type,legal_status,source_url,retrieved_at,content_hash,parser_version,transform_version,registered_electors_value,registered_electors_status,voters_value,voters_status,valid_votes_value,valid_votes_status,blank_votes_value,blank_votes_status,null_votes_value,null_votes_status,unmarked_votes_value,unmarked_votes_status\n"


def _comparison_item(
    row: dict[str, object], current_release: str, baseline_release: str
) -> dict[str, object]:
    def provenance(prefix: str, version: str) -> dict[str, object]:
        return {
            "data_version": version,
            "source_type": row[f"{prefix}_source_type"],
            "legal_status": row[f"{prefix}_legal_status"],
            "source_url": row[f"{prefix}_source_url"],
            "retrieved_at": row[f"{prefix}_retrieved_at"],
            "content_hash": row[f"{prefix}_content_hash"],
            "parser_version": row[f"{prefix}_parser_version"],
            "transform_version": row[f"{prefix}_transform_version"],
            "methodology_version": None,
        }

    return {
        "category_key": row["current_category_key"],
        "baseline_category_key": row["baseline_category_key"],
        "category_kind": row["category_kind"],
        "semantic_crosswalk_version": row["semantic_crosswalk_version"],
        "current_fact_id": row["current_fact_id"],
        "current_value": row["current_value"],
        "current_status": row["current_status"],
        "current_provenance": provenance("current", current_release),
        "baseline_fact_id": row["baseline_fact_id"],
        "baseline_value": row["baseline_value"],
        "baseline_status": row["baseline_status"],
        "baseline_provenance": provenance("baseline", baseline_release),
    }


def _normalized_category(row: dict[str, object], release_id: str) -> dict[str, object]:
    provenance = Provenance.model_validate(
        {
            "data_version": release_id,
            "source_type": row["source_type"],
            "legal_status": row["legal_status"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "content_hash": row["content_hash"],
            "parser_version": row["parser_version"],
            "transform_version": row["transform_version"],
            "methodology_version": None,
        }
    )
    return {
        **{
            key: row[key]
            for key in (
                "category_key",
                "category_code",
                "category_name",
                "category_kind",
                "votes",
                "status",
            )
        },
        "provenance": provenance.model_dump(mode="json"),
    }


def _normalized_summary_payload(
    row: dict[str, object], release_id: str
) -> dict[str, object]:
    raw_categories = row.get("national_categories")
    if not isinstance(raw_categories, list) or not all(
        isinstance(item, dict) for item in raw_categories
    ):
        raise RepositoryUnavailableError(
            "A context summary has malformed national category facts."
        )
    categories = cast(list[dict[str, object]], raw_categories)
    return {
        **row,
        "national_categories": [
            _normalized_category(item, release_id) for item in categories
        ],
    }


type AppRepository = ReadRepository | HistoricalDuckDBRepository | FederatedRepository

# Repositories that can answer release-scoped normalized reads. FederatedRepository
# subclasses neither backend — it delegates to both — so leaving it out of these
# guards did not raise anything: the release-scoped routes simply began 404ing and
# /api/v1/release-elections began returning an empty catalogue, in exactly the
# deployment federation exists to make work.
NORMALIZED_REPOSITORIES = (
    PostgresReadRepository,
    HistoricalDuckDBRepository,
    FederatedRepository,
)


def _release_backend(repository: AppRepository, release_id: str) -> AppRepository:
    """Resolve federation to the concrete backend that owns ``release_id``.

    ``datasets`` and ``dataset_file`` are the two release-scoped reads whose
    names carry no routing prefix, so ``FederatedRepository`` cannot dispatch
    them by release id and they would fall through to Postgres — 404ing every
    packaged dataset of a DuckDB-held historical release.
    """
    if isinstance(repository, FederatedRepository):
        return cast(AppRepository, repository.backend_for(release_id))
    return repository


def _historical_default_release(active_release_id: str, historical_ids: list[str]) -> str:
    """The release the DuckDB half answers for when no release id is supplied.

    ``HistoricalDuckDBRepository`` refuses to start unless its active release is
    one of the releases it verified, which is the right invariant when DuckDB is
    the only backend. Under federation Postgres owns ``ACTIVE_RELEASE`` — a 2026
    id the DuckDB half has never heard of — so passing it through would abort
    startup for the exact configuration federation exists to serve. Every
    release-scoped read reaches this backend with an explicit release id, so its
    default only has to be a release it actually holds; the newest packaged one
    matches what the image builds its read model against. When ``ACTIVE_RELEASE``
    is a rollback to a historical release, that release stays the default.
    """
    if active_release_id in historical_ids:
        return active_release_id
    if not historical_ids:
        raise ValueError("HISTORICAL_RELEASES must list at least one packaged release.")
    return historical_ids[-1]


def select_repository(settings: Settings) -> AppRepository:
    """Use the fixture only when no production PostgreSQL URL is configured."""
    if settings.database_url:
        postgres = PostgresReadRepository(
            settings.database_url,
            settings.selected_release_id(),
            settings.allowed_artifact_hosts,
        )
        # Configuring Postgres must not silently drop the historical releases.
        # Without this branch the catalogue would lose 2018 and 2022 with no
        # error, which is the failure mode most likely to go unnoticed.
        if settings.historical_releases:
            historical_ids = [
                item.strip() for item in settings.historical_releases.split(",") if item.strip()
            ]
            return FederatedRepository(
                postgres,
                HistoricalDuckDBRepository(
                    settings.historical_data_path,
                    historical_ids,
                    _historical_default_release(settings.selected_release_id(), historical_ids),
                ),
            )
        return postgres
    if settings.historical_releases:
        return HistoricalDuckDBRepository(
            settings.historical_data_path,
            [item.strip() for item in settings.historical_releases.split(",") if item.strip()],
            settings.selected_release_id(),
        )
    return FixtureRepository(settings.fixture_path)


def create_app(
    settings: Settings | None = None, repository: AppRepository | None = None
) -> FastAPI:
    settings = settings or Settings()
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.0,
            send_default_pii=False,
            before_send=_scrub_sentry_event,
        )
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            selected = cast(AppRepository, application.state.repository)
            if isinstance(selected, HistoricalDuckDBRepository):
                selected.close()

    app = FastAPI(
        title=FROZEN_OPENAPI["info"]["title"],
        version=FROZEN_OPENAPI["info"]["version"],
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    # The public document is versioned as a release artifact, rather than
    # regenerated from implementation details such as health probes.
    app.openapi_schema = FROZEN_OPENAPI
    app.state.repository = repository or select_repository(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "If-None-Match"],
        max_age=3600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_trusted_hosts)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        return response

    @app.exception_handler(APIProblem)
    async def api_problem_handler(request: Request, exc: APIProblem) -> JSONResponse:
        return _problem(request, exc.status, exc.title, exc.detail, exc.problem_type)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(
            request, 400, "Invalid request", "One or more query or path parameters are invalid."
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem(
            request,
            exc.status_code,
            "Not found" if exc.status_code == 404 else "HTTP error",
            str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        if settings.sentry_dsn:
            sentry_sdk.capture_exception(exc)
        return _problem(
            request,
            500,
            "Internal server error",
            "The request could not be completed.",
        )

    def repo(request: Request) -> AppRepository:
        return cast(AppRepository, request.app.state.repository)

    def require_legacy_contract(request: Request) -> None:
        # Federated: only refuse when the SELECTED release is DuckDB-backed. A
        # Postgres-backed release served alongside historical ones must keep
        # its legacy contract, so this cannot key off the repository class.
        repository = repo(request)
        if isinstance(repository, FederatedRepository):
            if repository.holds_historical(settings.selected_release_id() or ""):
                raise APIProblem(
                    404,
                    "Legacy contract unavailable",
                    (
                        "Historical context releases are served only by the release-scoped "
                        "/api/v1/releases/{release_id}/elections/{election_slug}/ routes. "
                        "The legacy contract cannot represent unknown completion or truthful "
                        "historical dataset metadata without inventing values."
                    ),
                )
            return
        if isinstance(repository, HistoricalDuckDBRepository):
            raise APIProblem(
                404,
                "Legacy contract unavailable",
                (
                    "Historical context releases are served only by the release-scoped "
                    "/api/v1/releases/{release_id}/elections/{election_slug}/ routes. "
                    "The legacy contract cannot represent unknown completion or truthful "
                    "historical dataset metadata without inventing values."
                ),
            )

    def translate(operation: Callable[[], T]) -> T:
        try:
            return operation()
        except (ReleaseNotFoundError, ResourceNotFoundError) as exc:
            raise APIProblem(404, "Resource not found", str(exc)) from exc
        except RepositoryUnavailableError as exc:
            raise APIProblem(503, "Read model unavailable", str(exc)) from exc

    @app.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def ready(request: Request) -> dict[str, str]:
        repository = repo(request)
        _ = translate(lambda: repository.data_version)
        if isinstance(repository, HistoricalDuckDBRepository):
            return {
                "status": "ready",
                "release_status": "candidate",
                "release_class": "context_only",
            }
        return {"status": "ready"}

    @app.get("/api/v1/release-elections", response_model=list[ReleaseElectionRef])
    async def release_elections(request: Request) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            return _cached_json(request, [])
        values = translate(lambda: repository.public_elections())

        def validate_release_elections() -> list[dict[str, object]]:
            return [_validated_public(ReleaseElectionRef, item) for item in values]

        return _cached_json(
            request,
            translate(validate_release_elections),
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/results",
        response_model=ResultPage,
        responses={
            200: {
                "description": "Cursor-paginated JSON facts or a filter-equivalent CSV export.",
                "content": {"text/csv": {"schema": {"type": "string"}}},
            }
        },
    )
    async def normalized_results(
        request: Request,
        release_id: str,
        election_slug: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        geography_id: str | None = None,
        geography_path: str | None = None,
        geography_level: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        category_key: str | None = None,
        status: Literal["observed", "unavailable"] | None = None,
        format: Literal["json", "csv"] = "json",
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        filters: dict[str, object] = {
            "geography_id": geography_id,
            "geography_path": geography_path,
            "geography_level": geography_level,
            "source_type": source_type,
            "source_id": source_id,
            "category_key": category_key,
            "status": status,
        }
        scope = scope_for(
            {
                "release": release_id,
                "election": election_slug,
                **filters,
                "order": "geography_level/geography_id/source/id",
            }
        )
        if format == "csv":
            if cursor is not None:
                raise APIProblem(
                    400, "Invalid cursor", "CSV exports do not accept cursor pagination."
                )
            tag = _etag(
                {
                    "release": release_id,
                    "election": election_slug,
                    "filters": filters,
                    "format": "csv-v2",
                }
            )
            headers = {
                "ETag": tag,
                "Cache-Control": HistoricalCache,
                "Vary": "Origin",
                "Content-Disposition": 'attachment; filename="filtered-results.csv"',
            }
            if _if_none_match(request.headers.get("if-none-match"), tag):
                return Response(status_code=304, headers=headers)

            def csv_stream() -> Iterable[str]:
                yield _normalized_csv_header()
                for row in repository.iter_normalized_results(release_id, election_slug, filters):
                    yield _normalized_csv_row(row, release_id, election_slug)

            return StreamingResponse(csv_stream(), media_type="text/csv", headers=headers)
        try:
            after = (
                None
                if cursor is None
                else decode_keyset_cursor(cursor, scope, settings.cursor_secret)
            )
            if after is not None and len(after) != 4:
                raise CursorError("The cursor position is invalid.")
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        values = translate(
            lambda: repository.normalized_results(release_id, election_slug, filters, after, limit)
        )
        has_more = len(values) > limit
        items = values[:limit]
        next_cursor = (
            encode_keyset_cursor(
                tuple(
                    str(items[-1][key])
                    for key in ("geography_level", "geography_id", "source_id", "id")
                ),
                scope,
                settings.cursor_secret,
            )
            if has_more and items
            else None
        )
        payload = {
                "items": [_normalized_fact(row, release_id, election_slug) for row in items],
                "page": {"next_cursor": next_cursor, "has_more": has_more, "limit": limit},
                "data_version": release_id,
            }
        return _cached_json(
            request, translate(lambda: _validated_public(ResultPage, payload))
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/summary",
        response_model=ContextElectionSummary,
    )
    async def normalized_summary(request: Request, release_id: str, election_slug: str) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        def summary_payload() -> dict[str, object]:
            raw = repository.normalized_summary(release_id, election_slug)
            payload = _normalized_summary_payload(raw, release_id)
            # Each model pins exactly one release class, so the class in the
            # payload selects it. A preliminary release cannot be validated as
            # context-only, nor the reverse.
            model = (
                PreliminaryElectionSummary
                if payload.get("release_class") == "standard"
                else ContextElectionSummary
            )
            validated = _validated_public(model, payload)
            # _validated_public drops unset fields; the exposure class must
            # survive so _cached_json can stamp the transport too.
            if payload.get("exposure_class"):
                validated["exposure_class"] = payload["exposure_class"]
            return validated

        return _cached_json(request, translate(summary_payload))

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/datasets",
        response_model=list[PackagedDataset],
    )
    async def normalized_datasets(
        request: Request, release_id: str, election_slug: str
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        datasets = translate(lambda: repository.datasets(election_slug, release_id))

        def validate_datasets() -> list[dict[str, object]]:
            output: list[dict[str, object]] = []
            for item in datasets:
                value = item if isinstance(item, dict) else item.model_dump(mode="json")
                dataset_id = value.get("id")
                if not isinstance(dataset_id, str):
                    raise RepositoryUnavailableError(
                        "A packaged dataset has no stable identifier."
                    )
                normalized = {
                    **value,
                    "url": (
                        f"/api/v1/releases/{release_id}/elections/{election_slug}"
                        f"/datasets/{dataset_id}/download"
                    ),
                }
                output.append(_validated_public(PackagedDataset, normalized))
            return output

        return _cached_json(
            request,
            translate(validate_datasets),
            ImmutableCache,
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/datasets/{dataset_id}/download",
        response_class=Response,
        responses={
            200: {
                "description": "Exact immutable Parquet bytes declared by the release manifest.",
                "content": {
                    "application/vnd.apache.parquet": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                },
                "headers": {
                    "ETag": {
                        "description": "Quoted SHA-256 content hash.",
                        "schema": {"type": "string"},
                    },
                    "Content-Disposition": {
                        "description": "Attachment filename for the immutable artifact.",
                        "schema": {"type": "string"},
                    },
                },
            },
            307: {
                "description": "Redirect to an allowlisted immutable Parquet artifact.",
                "headers": {
                    "Location": {
                        "description": "Allowlisted HTTPS artifact URL.",
                        "schema": {"type": "string", "format": "uri"},
                    },
                    "ETag": {
                        "description": "Quoted SHA-256 content hash.",
                        "schema": {"type": "string"},
                    },
                },
            },
        },
    )
    async def normalized_dataset_download(
        request: Request, release_id: str, election_slug: str, dataset_id: str
    ) -> Response:
        repository = repo(request)
        if isinstance(repository, HistoricalDuckDBRepository):
            path, dataset = translate(
                lambda: repository.dataset_file(release_id, election_slug, dataset_id)
            )
            return FileResponse(
                path,
                media_type="application/vnd.apache.parquet",
                filename=path.name,
                headers={
                    "Cache-Control": ImmutableCache,
                    "ETag": f'"{dataset["content_hash"]}"',
                    "X-Content-Type-Options": "nosniff",
                },
            )
        if isinstance(repository, (PostgresReadRepository, FederatedRepository)):
            datasets = translate(lambda: repository.datasets(election_slug, release_id))
            selected = next((item for item in datasets if item.id == dataset_id), None)
            if selected is None or selected.format != "parquet":
                raise APIProblem(404, "Resource not found", "Packaged dataset was not found.")

            def validate_selected_dataset() -> dict[str, object]:
                value = selected.model_dump(mode="json")
                value["url"] = (
                    f"/api/v1/releases/{release_id}/elections/{election_slug}"
                    f"/datasets/{dataset_id}/download"
                )
                return _validated_public(PackagedDataset, value)

            validated = translate(validate_selected_dataset)
            location = _allowlisted_artifact_url(
                str(selected.url), settings.allowed_artifact_hosts
            )
            return RedirectResponse(
                location,
                status_code=307,
                headers={
                    "Cache-Control": ImmutableCache,
                    "ETag": f'"{validated["content_hash"]}"',
                },
            )
        raise APIProblem(404, "Resource not found", "Packaged dataset was not found.")

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/outcome-sensitivity",
        response_model=OutcomeSensitivity,
    )
    async def normalized_outcome_sensitivity(
        request: Request, release_id: str, election_slug: str
    ) -> Response:
        """A bounded documentary sensitivity artifact at one public release scope."""
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        return _cached_json(
            request,
            translate(lambda: repository.normalized_outcome_sensitivity(release_id, election_slug)),
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/analysis/summary",
        response_model=AnalysisSummary,
    )
    async def analysis_summary(request: Request, release_id: str, election_slug: str) -> Response:
        return _cached_json(
            request,
            translate(lambda: repo(request).analysis_summary(election_slug, release_id)),
            ImmutableCache,
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/analysis/anomalies",
        response_model=AnalysisAnomalyPage,
    )
    async def analysis_anomalies(
        request: Request,
        release_id: str,
        election_slug: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        anomaly_type: Literal[
            "structural_arithmetic",
            "identity_coverage",
            "cross_source_documentary",
            "peer_distribution",
            "spatial",
        ]
        | None = None,
    ) -> Response:
        values = translate(lambda: repo(request).anomalies(election_slug, release_id))
        filtered = [
            item for item in values if anomaly_type is None or anomaly_type in item.anomaly_types
        ]
        filtered.sort(key=lambda item: (-item.audit_priority_score, item.id))
        scope = scope_for(
            {"release": release_id, "slug": election_slug, "anomaly_type": anomaly_type}
        )
        try:
            offset = 0 if cursor is None else decode_cursor(cursor, scope, settings.cursor_secret)
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        selected = filtered[offset : offset + limit]
        has_more = offset + limit < len(filtered)
        next_cursor = (
            encode_cursor(offset + limit, scope, settings.cursor_secret) if has_more else None
        )
        summary = translate(lambda: repo(request).analysis_summary(election_slug, release_id))
        return _cached_json(
            request,
            {
                "items": selected,
                "page": {"next_cursor": next_cursor, "has_more": has_more, "limit": limit},
                "data_version": release_id,
                "methodology_version": summary.methodology_version,
                "disclosure": summary.disclosure,
            },
            ImmutableCache,
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/analysis/anomalies/{anomaly_id}"
    )
    async def analysis_anomaly_detail(
        request: Request, release_id: str, election_slug: str, anomaly_id: str
    ) -> Response:
        return _cached_json(
            request,
            translate(lambda: repo(request).anomaly(election_slug, anomaly_id, release_id)),
            ImmutableCache,
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/analysis/{report_kind}",
        response_model=AnalysisReport,
    )
    async def analysis_report(
        request: Request,
        release_id: str,
        election_slug: str,
        report_kind: Literal["model_diagnostics", "validation", "local_sensitivity"],
    ) -> Response:
        return _cached_json(
            request,
            translate(
                lambda: repo(request).analysis_report(election_slug, report_kind, release_id)
            ),
            ImmutableCache,
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/geographies/{geography_id}/path",
        response_model=ScopedGeographyPathResponse,
    )
    async def normalized_geography_path(
        request: Request, release_id: str, election_slug: str, geography_id: str
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        payload = {
                "items": translate(
                    lambda: repository.normalized_geography_path(
                        release_id, election_slug, geography_id
                    )
                ),
                "data_version": release_id,
            }
        return _cached_json(
            request,
            translate(lambda: _validated_public(ScopedGeographyPathResponse, payload)),
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/geographies/{geography_id}/children",
        response_model=GeographyChildPage,
    )
    async def normalized_geography_children(
        request: Request,
        release_id: str,
        election_slug: str,
        geography_id: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        level: str | None = None,
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        scope = scope_for(
            {
                "release": release_id,
                "election": election_slug,
                "parent": geography_id,
                "level": level,
                "order": "level/code/id",
            }
        )
        try:
            after = (
                None
                if cursor is None
                else decode_keyset_cursor(cursor, scope, settings.cursor_secret)
            )
            if after is not None and len(after) != 3:
                raise CursorError("The cursor position is invalid.")
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        values = translate(
            lambda: repository.normalized_geography_children(
                release_id, election_slug, geography_id, level, after, limit
            )
        )
        items = values[:limit]
        more = len(values) > limit
        next_cursor = (
            encode_keyset_cursor(
                tuple(str(items[-1][key]) for key in ("level", "code", "id")),
                scope,
                settings.cursor_secret,
            )
            if more and items
            else None
        )
        payload = {
                "items": items,
                "page": {"next_cursor": next_cursor, "has_more": more, "limit": limit},
                "data_version": release_id,
            }
        return _cached_json(
            request, translate(lambda: _validated_public(GeographyChildPage, payload))
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/geographies/{geography_id}/children-results",
    )
    async def normalized_children_results(
        request: Request,
        release_id: str,
        election_slug: str,
        geography_id: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        level: str | None = None,
    ) -> Response:
        """Children plus their vote totals in one request.

        Exists because ``/results`` reaches candidate votes only through a
        per-fact categories call: drilling into one polling place would cost up
        to 228 extra round trips. This is the drill-down read.
        """
        repository = repo(request)
        # Federation answers this too: it refuses DuckDB-held releases itself
        # (there is no compact-model children-with-results projection) rather
        # than refusing every release the moment Postgres gains a companion.
        if not isinstance(repository, (PostgresReadRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        scope = scope_for(
            {
                "release": release_id,
                "election": election_slug,
                "parent": geography_id,
                "level": level,
                "order": "level/code/id",
                "shape": "children-results",
            }
        )
        try:
            after = (
                None
                if cursor is None
                else decode_keyset_cursor(cursor, scope, settings.cursor_secret)
            )
            if after is not None and len(after) != 3:
                raise CursorError("The cursor position is invalid.")
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        result = translate(
            lambda: repository.normalized_children_results(
                release_id, election_slug, geography_id, level, after, limit
            )
        )
        last = cast(tuple[str, ...] | None, result.pop("last", None))
        has_more = bool(result.pop("has_more", False))
        next_cursor = (
            encode_keyset_cursor(last, scope, settings.cursor_secret)
            if has_more and last is not None
            else None
        )
        result["page"] = {
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit,
        }
        return _cached_json(request, result)

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/geographies/{geography_id}",
        response_model=ScopedGeographyResponse,
    )
    async def normalized_geography(
        request: Request, release_id: str, election_slug: str, geography_id: str
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        payload = {
                "item": translate(
                    lambda: repository.normalized_geography(release_id, election_slug, geography_id)
                ),
                "data_version": release_id,
            }
        return _cached_json(
            request, translate(lambda: _validated_public(ScopedGeographyResponse, payload))
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/mesas/{mesa_id}",
        response_model=ScopedMesa,
    )
    async def normalized_mesa(
        request: Request,
        release_id: str,
        election_slug: str,
        mesa_id: str,
        source_id: str | None = None,
        source_type: str | None = None,
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        value = translate(
            lambda: repository.normalized_mesa(
                release_id, election_slug, mesa_id, source_id, source_type
            )
        )
        raw_results = cast(list[dict[str, object]], value["results"])
        payload = {
            **value,
            "results": [_normalized_fact(row, release_id, election_slug) for row in raw_results],
            "data_version": release_id,
        }
        return _cached_json(request, translate(lambda: _validated_public(ScopedMesa, payload)))

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/result-facts/{fact_id}/categories",
        response_model=NormalizedCategoryPage,
    )
    async def normalized_categories(
        request: Request,
        release_id: str,
        election_slug: str,
        fact_id: str,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> Response:
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        scope = scope_for(
            {
                "release": release_id,
                "election": election_slug,
                "fact": fact_id,
                "order": "category_key",
            }
        )
        try:
            position = (
                None
                if cursor is None
                else decode_keyset_cursor(cursor, scope, settings.cursor_secret)
            )
            if position is not None and len(position) != 1:
                raise CursorError("The cursor position is invalid.")
            after = None if position is None else position[0]
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        values = translate(
            lambda: repository.normalized_categories(
                release_id, election_slug, fact_id, after, limit
            )
        )
        items = values[:limit]
        more = len(values) > limit
        next_cursor = (
            encode_keyset_cursor((str(items[-1]["category_key"]),), scope, settings.cursor_secret)
            if more and items
            else None
        )
        payload = {
                "items": [_normalized_category(item, release_id) for item in items],
                "page": {"next_cursor": next_cursor, "has_more": more, "limit": limit},
                "data_version": release_id,
                "sparse_category_semantics": "absent categories are unavailable; they are never inferred as zero",
            }
        return _cached_json(
            request, translate(lambda: _validated_public(NormalizedCategoryPage, payload))
        )

    @app.get(
        "/api/v1/releases/{release_id}/elections/{election_slug}/historical-comparison",
        response_model=HistoricalComparisonResponse,
    )
    async def historical_comparison(
        request: Request,
        release_id: str,
        election_slug: str,
        baseline_release_id: str,
        baseline_election_slug: str,
        geography_id: str,
        grain: str,
        category_key: str | None = None,
    ) -> Response:
        """Comparison authorization is an explicit code crosswalk, never a name match."""
        repository = repo(request)
        if not isinstance(repository, (PostgresReadRepository, HistoricalDuckDBRepository, FederatedRepository)):
            raise APIProblem(
                404, "Resource not found", "Normalized release reads require PostgreSQL."
            )
        crosswalk = translate(
            lambda: repository.normalized_comparison(
                release_id,
                election_slug,
                baseline_release_id,
                baseline_election_slug,
                geography_id,
                grain,
                category_key,
            )
        )
        payload: dict[str, object] = {
            "data_version": release_id,
            "baseline_data_version": baseline_release_id,
            "geography_id": geography_id,
            "requested_grain": grain,
            "comparison_status": "not_comparable",
        }
        payload.update(crosswalk)
        if payload["comparison_status"] in {"comparable", "descriptive_context_only"}:
            raw_items = cast(list[dict[str, object]], payload.pop("items"))
            payload["items"] = [
                _comparison_item(item, release_id, baseline_release_id) for item in raw_items
            ]
        return _cached_json(
            request,
            translate(lambda: _validated_public(HistoricalComparisonResponse, payload)),
        )

    @app.get("/api/v1/elections/{slug}/summary", response_model=ElectionSummary)
    async def election_summary(
        request: Request, slug: str, data_version: str | None = None
    ) -> Response:
        require_legacy_contract(request)
        result = translate(lambda: repo(request).summary(slug, data_version))
        return _cached_json(request, result)

    @app.get("/api/v1/elections/{slug}/results", response_model=ResultPage)
    async def election_results(
        request: Request,
        slug: str,
        data_version: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        source_type: Literal[
            "final_declaration",
            "scrutiny",
            "e14_delegate",
            "e14_transmission",
            "pre_count",
            "contextual_baseline",
        ]
        | None = None,
        geography_id: str | None = None,
        geography_level: Literal[
            "national", "department", "municipality", "zone", "polling_place", "mesa"
        ]
        | None = None,
        candidate_id: str | None = None,
        format: Literal["json", "csv"] = "json",
    ) -> Response:
        require_legacy_contract(request)
        values = translate(lambda: repo(request).results(slug, data_version))
        assert isinstance(values, list)
        filtered = _result_filters(
            values,
            source_type,
            geography_id,
            geography_level,
            candidate_id,
            lambda result, requested: (
                result.mesa_id is not None
                and requested in repo(request).signal_geography_ids(result.mesa_id, data_version)
            ),
        )
        if format == "csv":
            if cursor is not None:
                raise APIProblem(
                    400, "Invalid cursor", "CSV exports do not accept cursor pagination."
                )
            body = _csv(filtered)
            tag = _etag(body)
            headers = {
                "ETag": tag,
                "Cache-Control": HistoricalCache,
                "Vary": "Origin",
                "Content-Disposition": 'attachment; filename="filtered-results.csv"',
            }
            if _if_none_match(request.headers.get("if-none-match"), tag):
                return Response(status_code=304, headers=headers)
            return Response(body, media_type="text/csv", headers=headers)
        version = repo(request).data_version
        scope = scope_for(
            {
                "release": data_version or version,
                "slug": slug,
                "source_type": source_type,
                "geography_id": geography_id,
                "geography_level": geography_level,
                "candidate_id": candidate_id,
            }
        )
        try:
            offset = 0 if cursor is None else decode_cursor(cursor, scope, settings.cursor_secret)
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        page_items = filtered[offset : offset + limit]
        has_more = offset + limit < len(filtered)
        next_cursor = (
            encode_cursor(offset + limit, scope, settings.cursor_secret) if has_more else None
        )
        page = ResultPage.model_validate(
            {
                "items": page_items,
                "page": {"next_cursor": next_cursor, "has_more": has_more, "limit": limit},
                "data_version": version,
            }
        )
        return _cached_json(request, page)

    @app.get("/api/v1/geographies/{id}", response_model=Geography)
    async def get_geography(request: Request, id: str, data_version: str | None = None) -> Response:
        require_legacy_contract(request)
        return _cached_json(request, translate(lambda: repo(request).geography(id, data_version)))

    @app.get("/api/v1/mesas/{id}", response_model=MesaDetail)
    async def get_mesa(
        request: Request,
        id: str,
        data_version: str | None = None,
        source_type: Literal[
            "final_declaration",
            "scrutiny",
            "e14_delegate",
            "e14_transmission",
            "pre_count",
            "contextual_baseline",
        ]
        | None = None,
    ) -> Response:
        require_legacy_contract(request)
        return _cached_json(
            request, translate(lambda: repo(request).mesa(id, data_version, source_type))
        )

    @app.get("/api/v1/mesas/{id}/evidence", response_model=EvidenceResponse)
    async def mesa_evidence(request: Request, id: str, data_version: str | None = None) -> Response:
        require_legacy_contract(request)
        documents = translate(lambda: repo(request).evidence(id, data_version))
        for document in documents:
            _allowlisted_document_url(
                str(document.official_url), settings.allowed_official_document_hosts
            )
            _allowlisted_document_url(
                str(document.source_index_url), settings.allowed_official_document_hosts
            )
        return _cached_json(
            request,
            {"mesa_id": id, "documents": documents, "data_version": repo(request).data_version},
        )

    @app.get("/api/v1/mesas/{id}/comparisons", response_model=ComparisonResponse)
    async def mesa_comparisons(
        request: Request, id: str, data_version: str | None = None
    ) -> Response:
        require_legacy_contract(request)
        items = translate(lambda: repo(request).comparisons(id, data_version))
        return _cached_json(
            request, {"mesa_id": id, "items": items, "data_version": repo(request).data_version}
        )

    @app.get("/api/v1/bulletins", response_model=list[Bulletin])
    async def list_bulletins(
        request: Request, election_slug: str, data_version: str | None = None
    ) -> Response:
        require_legacy_contract(request)
        return _cached_json(
            request, translate(lambda: repo(request).bulletins(election_slug, data_version))
        )

    @app.get("/api/v1/bulletins/{id}/results", response_model=BulletinResult)
    async def bulletin_results(
        request: Request, id: str, data_version: str | None = None
    ) -> Response:
        require_legacy_contract(request)
        return _cached_json(
            request, translate(lambda: repo(request).bulletin_result(id, data_version))
        )

    @app.get("/api/v1/review-signals", response_model=ReviewSignalPage)
    async def list_review_signals(
        request: Request,
        election_slug: str,
        data_version: str | None = None,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        minimum_score: Annotated[int | None, Query(ge=0, le=100)] = None,
        tier: Literal[
            "documentary_review_prioritized",
            "documentary_comparison_recommended",
            "statistical_or_coverage_issue",
            "no_review_signals",
        ]
        | None = None,
        geography_id: str | None = None,
    ) -> Response:
        require_legacy_contract(request)
        values = translate(lambda: repo(request).review_signals(election_slug, data_version))
        assert isinstance(values, list)
        mesa_geographies = {
            item.mesa_id: repo(request).signal_geography_ids(item.mesa_id, data_version)
            for item in values
        }
        filtered = [
            item
            for item in values
            if (minimum_score is None or item.score >= minimum_score)
            and (tier is None or item.tier == tier)
            and (geography_id is None or geography_id in mesa_geographies.get(item.mesa_id, set()))
        ]
        filtered.sort(key=lambda item: (-item.score, item.id))
        version = repo(request).data_version
        scope = scope_for(
            {
                "release": data_version or version,
                "slug": election_slug,
                "minimum_score": minimum_score,
                "tier": tier,
                "geography_id": geography_id,
            }
        )
        try:
            offset = 0 if cursor is None else decode_cursor(cursor, scope, settings.cursor_secret)
        except CursorError as exc:
            raise APIProblem(400, "Invalid cursor", str(exc)) from exc
        selected = filtered[offset : offset + limit]
        has_more = offset + limit < len(filtered)
        next_cursor = (
            encode_cursor(offset + limit, scope, settings.cursor_secret) if has_more else None
        )
        disclosure = translate(lambda: repo(request).review_disclosure(election_slug, data_version))
        methodology = translate(
            lambda: repo(request).review_methodology_version(election_slug, data_version)
        )
        payload = {
            "items": selected,
            "page": {"next_cursor": next_cursor, "has_more": has_more, "limit": limit},
            "data_version": version,
            "methodology_version": methodology,
            "disclosure": disclosure,
        }
        return _cached_json(request, payload)

    @app.get("/api/v1/datasets", response_model=list[Dataset])
    async def list_datasets(
        request: Request, election_slug: str, data_version: str | None = None
    ) -> Response:
        require_legacy_contract(request)
        return _cached_json(
            request,
            translate(lambda: repo(request).datasets(election_slug, data_version)),
            ImmutableCache,
        )

    @app.get("/api/v1/datasets/{id}/download", status_code=302)
    async def download_dataset(
        request: Request, id: str, data_version: str | None = None, raw: bool = False
    ) -> Response:
        require_legacy_contract(request)
        dataset = translate(lambda: repo(request).dataset(id, data_version))
        if repo(request).is_fixture:
            if not raw:
                # Keep this redirect relative: the incoming Host header must never
                # become a public redirect target.
                location = f"{request.url.path}?raw=true"
                return RedirectResponse(
                    url=location,
                    status_code=302,
                    headers={"Cache-Control": ImmutableCache, "ETag": f'"{dataset.content_hash}"'},
                )
            rows = [
                item.model_dump(mode="json")
                for item in repo(request).raw_dataset_rows(id, data_version)
            ]
            body = json.dumps(rows, separators=(",", ":"))
            return Response(
                body,
                media_type="application/json",
                headers={"Cache-Control": ImmutableCache, "ETag": _etag(body)},
            )
        if raw:
            raise APIProblem(
                400,
                "Invalid dataset request",
                "Local raw dataset rendering is available only for synthetic fixtures.",
            )
        location = _allowlisted_artifact_url(
            translate(lambda: repo(request).dataset_artifact_url(id, data_version)),
            settings.allowed_artifact_hosts,
        )
        return RedirectResponse(
            url=location,
            status_code=302,
            headers={"Cache-Control": ImmutableCache, "ETag": f'"{dataset.content_hash}"'},
        )

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    async def openapi_document(request: Request) -> Response:
        return _cached_json(request, FROZEN_OPENAPI, ImmutableCache)

    app.openapi_schema = FROZEN_OPENAPI
    app._openapi_routes_version = app.router._get_routes_version()  # noqa: SLF001
    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("elecciones_api.main:app", host="0.0.0.0", port=8000, reload=False)  # noqa: S104
