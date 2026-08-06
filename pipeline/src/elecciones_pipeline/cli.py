"""Command-line entrypoints for deliberately gated pipeline operations."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Annotated, Literal

import httpx
import typer

from .catalog import CatalogError, load_source_catalog
from .ingest.historical_2018 import (
    Historical2018Error,
    build_historical_2018_release,
    fetch_historical_2018,
    import_historical_2018_archives,
)
from .ingest.historical_2022 import (
    Historical2022Error,
    build_historical_2022_release,
    fetch_historical_2022,
)
from .ingest.precount_crawl import PrecountCrawlError, PrecountCrawlReport, crawl_precount
from .ingest.relay_smoke import RelaySmokeError, smoke_relay_resume
from .ingest.relay_transport import (
    PrecountRelayTransport,
    RelayTransportError,
    load_relay_token,
)
from .releases.candidate import CandidateBuildError, build_national_precount_candidate
from .releases.compact_postgres_loader import load_historical_context_release
from .releases.postgres_loader import ReleaseLoadError
from .releases.snapshot_parquet import snapshot_to_parquet
from .releases.standard_postgres_loader import load_standard_2026_release
from .source_check import check_official_manifests

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
ROOT = Path(__file__).resolve().parents[3]


def _trees_are_identical(left: Path, right: Path) -> bool:
    left_files = {path.relative_to(left) for path in left.rglob("*") if path.is_file()}
    right_files = {path.relative_to(right) for path in right.rglob("*") if path.is_file()}
    return left_files == right_files and all(
        (left / relative).read_bytes() == (right / relative).read_bytes() for relative in left_files
    )


def _install_candidate_manifest(staged: Path, target: Path) -> bool:
    """Atomically install new immutable bytes, or report an exact no-op."""
    payload = staged.read_bytes()
    if target.exists():
        if target.read_bytes() != payload:
            raise Historical2022Error(
                f"refusing to overwrite non-identical immutable manifest {target.name}"
            )
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("wb", dir=target.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, target)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return True


@app.callback()
def main() -> None:
    """Operate the source and release pipeline through explicit gated commands."""


@app.command("source-check")
def source_check(
    catalog_path: Annotated[
        Path,
        typer.Option("--catalog", help="Checked-in reviewed official-source catalog."),
    ] = ROOT / "config/sources/presidencia-2026-segunda-vuelta.json",
    state_directory: Annotated[
        Path,
        typer.Option("--state-dir", help="Durable checkpoint and content-addressed object state."),
    ] = ROOT / ".pipeline/source-check",
    output: Annotated[
        Path | None,
        typer.Option("--output", help="Optional path for the machine-readable report."),
    ] = None,
    manifest_only: Annotated[
        bool,
        typer.Option("--manifest-only/--full-crawl", help="Only inspect reviewed root manifests."),
    ] = True,
    publish: Annotated[
        bool,
        typer.Option(
            "--publish/--no-publish", help="Publication is never allowed by this command."
        ),
    ] = False,
) -> None:
    """Check source roots; never create or activate a release."""
    if publish:
        raise typer.BadParameter(
            "source-check cannot publish; use the separately gated release workflow"
        )
    try:
        catalog = load_source_catalog(catalog_path)
        report = asyncio.run(
            check_official_manifests(catalog, state_directory, manifest_only=manifest_only)
        )
    except (CatalogError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Source check failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    rendered = report.to_json()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"{rendered}\n", encoding="utf-8")
    typer.echo(rendered)


@app.command("historical-2022-fetch")
def historical_2022_fetch(
    state_directory: Annotated[
        Path, typer.Option("--state-dir", help="Isolated immutable 2022 raw-object state.")
    ] = ROOT / ".pipeline/historical-2022",
    recheck: Annotated[
        bool,
        typer.Option("--recheck/--resume", help="Use conditional GET, or resume stored bytes."),
    ] = False,
) -> None:
    """Fetch only the two reviewed Observatory MMV ZIPs; never publish a release."""
    try:
        snapshots = asyncio.run(fetch_historical_2022(state_directory, recheck=recheck))
    except (Historical2022Error, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2022 fetch failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    payload = {str(key): value.model_dump(mode="json") for key, value in snapshots.items()}
    typer.echo(json.dumps(payload, sort_keys=True))


@app.command("historical-2018-fetch")
def historical_2018_fetch(
    state_directory: Annotated[
        Path, typer.Option("--state-dir", help="Isolated immutable 2018 raw-object state.")
    ] = ROOT / ".pipeline/historical-2018",
    recheck: Annotated[
        bool,
        typer.Option("--recheck/--resume", help="Use conditional GET, or resume stored bytes."),
    ] = False,
) -> None:
    """Fetch only the two reviewed 2018 MMV ZIPs; never publish a release."""
    try:
        snapshots = asyncio.run(fetch_historical_2018(state_directory, recheck=recheck))
    except (Historical2018Error, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2018 fetch failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    payload = {str(key): value.model_dump(mode="json") for key, value in snapshots.items()}
    typer.echo(json.dumps(payload, sort_keys=True))


@app.command("historical-2018-import")
def historical_2018_import(
    round_1_archive: Annotated[
        Path,
        typer.Option("--round-1-archive", help="Verified ZIP from the approved private relay."),
    ],
    round_2_archive: Annotated[
        Path,
        typer.Option("--round-2-archive", help="Verified ZIP from the approved private relay."),
    ],
    state_directory: Annotated[
        Path, typer.Option("--state-dir", help="Isolated immutable 2018 raw-object state.")
    ] = ROOT / ".pipeline/historical-2018",
) -> None:
    """Import pre-transferred ZIPs only; never use this command to publish."""
    try:
        snapshots = import_historical_2018_archives(
            state_directory, {1: round_1_archive, 2: round_2_archive}
        )
    except (Historical2018Error, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2018 import failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {str(key): value.model_dump(mode="json") for key, value in snapshots.items()},
            sort_keys=True,
        )
    )


@app.command("historical-2022-build")
def historical_2022_build(
    state_directory: Annotated[
        Path, typer.Option("--state-dir", help="Isolated immutable 2022 raw-object state.")
    ] = ROOT / ".pipeline/historical-2022",
    release_root: Annotated[
        Path,
        typer.Option(
            "--release-root",
            "--output-dir",
            help="Ignored root for deterministic v2 candidate directories; never activates them.",
        ),
    ] = ROOT / "data/releases",
    manifest_directory: Annotated[
        Path, typer.Option("--manifest-dir", help="Versioned non-active candidate manifests.")
    ] = ROOT / "data/manifests",
    git_commit: Annotated[
        str, typer.Option("--git-commit", help="Exact build commit or local worktree label.")
    ] = "uncommitted-worktree",
) -> None:
    """Atomically stage an immutable v2 historical candidate; never activate or publish it."""
    try:
        release_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".historical-2022-staging-", dir=release_root) as temporary:
            staging = Path(temporary)
            staged_release = staging / "artifacts"
            build = build_historical_2022_release(
                state_directory, staged_release, staging / "manifests", git_commit=git_commit
            )
            target_release = release_root / build.release_id
            target_manifest = manifest_directory / f"{build.release_id}.json"
            if build.manifest_path.name != target_manifest.name:
                raise Historical2022Error("builder returned a manifest filename unlike release_id")
            if target_release.exists() and not _trees_are_identical(staged_release, target_release):
                raise Historical2022Error(
                    f"refusing to overwrite non-identical immutable release {build.release_id}"
                )
            if target_manifest.exists() and (
                target_manifest.read_bytes() != build.manifest_path.read_bytes()
            ):
                raise Historical2022Error(
                    f"refusing to overwrite non-identical immutable manifest {target_manifest.name}"
                )
            installed_release = False
            if not target_release.exists():
                os.replace(staged_release, target_release)
                installed_release = True
            installed_manifest = _install_candidate_manifest(build.manifest_path, target_manifest)
    except (Historical2022Error, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2022 build failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "release_id": build.release_id,
                "status": "candidate_non_active",
                "manifest": str(target_manifest),
                "metadata": str(target_release / build.metadata_path.name),
                "rows": str(target_release / build.rows_path.name),
                "rollups": str(target_release / build.rollups_path.name),
                "geography": str(target_release / build.geography_path.name),
                "rows_by_round": build.row_counts,
                "mesas_by_round": build.mesa_counts,
                "installed": installed_release or installed_manifest,
                "no_op": not installed_release and not installed_manifest,
            },
            sort_keys=True,
        )
    )


@app.command("historical-2018-build")
def historical_2018_build(
    state_directory: Annotated[
        Path, typer.Option("--state-dir", help="Isolated immutable 2018 raw-object state.")
    ] = ROOT / ".pipeline/historical-2018",
    release_root: Annotated[
        Path,
        typer.Option(
            "--release-root",
            "--output-dir",
            help="Ignored root for deterministic 2018 candidate directories; never activates them.",
        ),
    ] = ROOT / "data/releases",
    manifest_directory: Annotated[
        Path, typer.Option("--manifest-dir", help="Versioned non-active candidate manifests.")
    ] = ROOT / "data/manifests",
    git_commit: Annotated[
        str, typer.Option("--git-commit", help="Exact build commit or local worktree label.")
    ] = "uncommitted-worktree",
) -> None:
    """Atomically stage an immutable context-only candidate; never activate or publish it."""
    try:
        release_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".historical-2018-staging-", dir=release_root) as temporary:
            staging = Path(temporary)
            staged_release = staging / "artifacts"
            build = build_historical_2018_release(
                state_directory, staged_release, staging / "manifests", git_commit=git_commit
            )
            target_release = release_root / build.release_id
            target_manifest = manifest_directory / f"{build.release_id}.json"
            if build.manifest_path.name != target_manifest.name:
                raise Historical2018Error("builder returned a manifest filename unlike release_id")
            if target_release.exists() and not _trees_are_identical(staged_release, target_release):
                raise Historical2018Error(
                    f"refusing to overwrite non-identical immutable release {build.release_id}"
                )
            if target_manifest.exists() and (
                target_manifest.read_bytes() != build.manifest_path.read_bytes()
            ):
                raise Historical2018Error(
                    f"refusing to overwrite non-identical immutable manifest {target_manifest.name}"
                )
            installed_release = False
            if not target_release.exists():
                os.replace(staged_release, target_release)
                installed_release = True
            installed_manifest = _install_candidate_manifest(build.manifest_path, target_manifest)
    except (Historical2018Error, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2018 build failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "release_id": build.release_id,
                "release_class": "context_only",
                "status": "candidate_non_active",
                "manifest": str(target_manifest),
                "metadata": str(target_release / build.metadata_path.name),
                "rows": str(target_release / build.rows_path.name),
                "rollups": str(target_release / build.rollups_path.name),
                "geography": str(target_release / build.geography_path.name),
                "rows_by_round": build.row_counts,
                "mesas_by_round": build.mesa_counts,
                "installed": installed_release or installed_manifest,
                "no_op": not installed_release and not installed_manifest,
                "publication_performed": False,
            },
            sort_keys=True,
        )
    )


@app.command("historical-2022-load-postgres")
def historical_2022_load_postgres(
    database_url: Annotated[str, typer.Option("--database-url", help="PostgreSQL/Neon URL.")],
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", help="Explicit non-active v2 candidate manifest."),
    ],
    release_directory: Annotated[
        Path,
        typer.Option("--release-dir", help="Matching immutable v2 candidate directory."),
    ],
) -> None:
    """Load a validated 2022 candidate internally; this never exposes or activates it."""
    from sqlalchemy import create_engine

    try:
        outcome = load_historical_context_release(
            create_engine(database_url),
            manifest_path,
            release_directory,
            year=2022,
        )
    except (ReleaseLoadError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2022 load failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(outcome)


@app.command("historical-2018-load-postgres")
def historical_2018_load_postgres(
    database_url: Annotated[str, typer.Option("--database-url", help="PostgreSQL URL.")],
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", help="Explicit non-active context-only manifest."),
    ],
    release_directory: Annotated[
        Path,
        typer.Option("--release-dir", help="Matching immutable candidate directory."),
    ],
) -> None:
    """Load validated 2018 context internally; never expose or activate it."""
    from sqlalchemy import create_engine

    try:
        outcome = load_historical_context_release(
            create_engine(database_url),
            manifest_path,
            release_directory,
            year=2018,
        )
    except (ReleaseLoadError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Historical 2018 load failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(outcome)


@app.command("standard-2026-snapshot-parquet")
def standard_2026_snapshot_parquet(
    snapshot_path: Annotated[
        Path,
        typer.Option("--snapshot", help="Immutable api-snapshot.json for the standard release."),
    ],
    output_directory: Annotated[
        Path,
        typer.Option("--out", help="Directory receiving the Parquet artifacts and load manifest."),
    ],
) -> None:
    """Stream a 172 MB standard snapshot into four bounded Parquet artifacts."""
    try:
        load_manifest = snapshot_to_parquet(snapshot_path, output_directory)
    except (ReleaseLoadError, OSError, ValueError) as exc:
        typer.echo(f"Standard 2026 snapshot conversion failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "release_id": load_manifest["release_id"],
                "artifacts": load_manifest["artifacts"],
                "sources": [source["id"] for source in load_manifest["sources"]],
            },
            sort_keys=True,
        )
    )


@app.command("standard-2026-load-postgres")
def standard_2026_load_postgres(
    database_url: Annotated[str, typer.Option("--database-url", help="PostgreSQL URL.")],
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", help="Release manifest for the standard candidate."),
    ],
    artifact_directory: Annotated[
        Path,
        typer.Option("--artifact-dir", help="Directory written by standard-2026-snapshot-parquet."),
    ],
) -> None:
    """Load the standard 2026 release internally; this never exposes or activates it."""
    from sqlalchemy import create_engine

    try:
        outcome = load_standard_2026_release(
            create_engine(database_url), manifest_path, artifact_directory
        )
    except (ReleaseLoadError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Standard 2026 load failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(outcome)


@app.command("precount-crawl")
def precount_crawl(
    stage: Annotated[
        Literal["national", "aggregates", "places", "mesas"],
        typer.Option(
            "--stage",
            help=(
                "Explicit crawl stage; aggregates uses published nomenclator scopes; "
                "mesas first enumerates places."
            ),
        ),
    ],
    catalog_path: Annotated[
        Path,
        typer.Option("--catalog", help="Checked-in reviewed official-source catalog."),
    ] = ROOT / "config/sources/presidencia-2026-segunda-vuelta.json",
    state_directory: Annotated[
        Path,
        typer.Option("--state-dir", help="Durable raw objects, checkpoints, and crawl ledger."),
    ] = ROOT / ".pipeline/official-2026-round2",
    requests_per_second: Annotated[
        float,
        typer.Option("--rate", min=2.0, max=5.0, help="Per-host request rate."),
    ] = 5.0,
    refresh_existing: Annotated[
        bool,
        typer.Option(
            "--refresh-existing/--resume",
            help="Conditionally recheck existing URLs, or resume from immutable local bytes.",
        ),
    ] = False,
    retry_nonparsed_only: Annotated[
        bool,
        typer.Option(
            "--retry-nonparsed-only",
            help="Resume only non-parsed rows from one existing, identical immutable plan.",
        ),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            min=1,
            help="Create an explicitly sample-limited smoke-test plan.",
        ),
    ] = None,
    relay_base_url: Annotated[
        str | None,
        typer.Option(
            "--relay-base-url",
            help="Optional loopback-only private relay, for example http://127.0.0.1:18787.",
        ),
    ] = None,
    relay_token_file: Annotated[
        Path | None,
        typer.Option(
            "--relay-token-file",
            help="Owner-only file containing the private relay bearer token.",
        ),
    ] = None,
) -> None:
    """Collect reviewed Registraduría pre-count stages; never publish a release."""
    try:
        catalog = load_source_catalog(catalog_path)

        async def run() -> PrecountCrawlReport:
            relay_requested = relay_base_url is not None or relay_token_file is not None
            if relay_requested and (relay_base_url is None or relay_token_file is None):
                raise RelayTransportError(
                    "relay base URL and owner-only token file must be supplied together"
                )
            if relay_base_url is not None and relay_token_file is not None:
                transport = PrecountRelayTransport(
                    relay_base_url,
                    load_relay_token(relay_token_file),
                )
                async with httpx.AsyncClient(
                    transport=transport,
                    follow_redirects=False,
                    timeout=60,
                    trust_env=False,
                ) as relay_client:
                    return await crawl_precount(
                        catalog,
                        state_directory,
                        stage=stage,
                        requests_per_second=requests_per_second,
                        refresh_existing=refresh_existing,
                        retry_nonparsed_only=retry_nonparsed_only,
                        limit=limit,
                        progress=lambda message: typer.echo(message, err=True),
                        http_client=relay_client,
                    )
            return await crawl_precount(
                catalog,
                state_directory,
                stage=stage,
                requests_per_second=requests_per_second,
                refresh_existing=refresh_existing,
                retry_nonparsed_only=retry_nonparsed_only,
                limit=limit,
                progress=lambda message: typer.echo(message, err=True),
            )

        report = asyncio.run(run())
    except (
        CatalogError,
        OSError,
        PrecountCrawlError,
        RelayTransportError,
        RuntimeError,
        ValueError,
    ) as exc:
        typer.echo(f"Pre-count crawl failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(report.to_json())


@app.command("precount-relay-smoke")
def precount_relay_smoke(
    round_number: Annotated[
        int,
        typer.Option("--round", min=1, max=2, help="Reviewed 2026 presidential round."),
    ],
    state_directory: Annotated[
        Path,
        typer.Option("--state-dir", help="Existing stopped local crawl state."),
    ],
    relay_base_url: Annotated[
        str,
        typer.Option("--relay-base-url", help="Loopback SSH-forwarded relay base URL."),
    ],
    relay_token_file: Annotated[
        Path,
        typer.Option("--relay-token-file", help="Owner-only relay token file."),
    ],
) -> None:
    """Gate resume with 10 unchanged mesas and one retryable missing mesa."""
    try:
        report = asyncio.run(
            smoke_relay_resume(
                state_directory,
                round_number=round_number,
                relay_base_url=relay_base_url,
                relay_token_file=relay_token_file,
            )
        )
    except (OSError, RelaySmokeError, RelayTransportError, RuntimeError, ValueError) as exc:
        typer.echo(f"Pre-count relay smoke failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(report.to_json())


@app.command("release-build-candidate")
def release_build_candidate(
    plan_id: Annotated[
        str,
        typer.Option("--plan-id", help="Completed immutable national crawl plan id."),
    ],
    catalog_path: Annotated[
        Path,
        typer.Option("--catalog", help="Checked-in reviewed official-source catalog."),
    ] = ROOT / "config/sources/presidencia-2026-segunda-vuelta.json",
    state_directory: Annotated[
        Path,
        typer.Option("--state-dir", help="Durable official crawl state."),
    ] = ROOT / ".pipeline/official-2026-round2",
    output_directory: Annotated[
        Path,
        typer.Option("--output-dir", help="Local immutable candidate artifacts."),
    ] = ROOT / "data/releases",
    manifest_directory: Annotated[
        Path,
        typer.Option("--manifest-dir", help="Small versioned candidate manifests."),
    ] = ROOT / "data/manifests",
    git_commit: Annotated[
        str,
        typer.Option("--git-commit", help="Exact build commit, or uncommitted-worktree locally."),
    ] = "uncommitted-worktree",
    places_plan_id: Annotated[
        str | None,
        typer.Option("--places-plan-id", help="Optional completed polling-place crawl plan id."),
    ] = None,
    mesas_plan_id: Annotated[
        str | None,
        typer.Option("--mesas-plan-id", help="Optional completed canonical mesa crawl plan id."),
    ] = None,
) -> None:
    """Materialize a real, non-active candidate release; never publish or switch the pointer."""
    try:
        build = build_national_precount_candidate(
            catalog=load_source_catalog(catalog_path),
            state_directory=state_directory,
            plan_id=plan_id,
            output_directory=output_directory,
            manifest_directory=manifest_directory,
            git_commit=git_commit,
            places_plan_id=places_plan_id,
            mesas_plan_id=mesas_plan_id,
        )
    except (CandidateBuildError, CatalogError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Candidate release build failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(
        json.dumps(
            {
                "release_id": build.release_id,
                "manifest_path": str(build.manifest_path),
                "snapshot_path": str(build.snapshot_path),
                "snapshot_hash": build.snapshot_hash,
                "datasets": [artifact.manifest_item() for artifact in build.dataset_artifacts],
                "publication_performed": False,
                "publication_blockers": list(build.publication_blockers),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    app()
