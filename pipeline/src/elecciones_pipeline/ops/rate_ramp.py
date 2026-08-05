"""Fail-closed, single-writer rate-ramp supervisor for reviewed mesa crawls.

This is deliberately an operator command, not a scheduler.  It only moves one
already-running, checkpointed crawler to the next reviewed rate after a fixed
canary.  Any integrity or upstream-health delta restores the prior rate.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from elecciones_pipeline.ingest.relay_transport import load_relay_token, validate_relay_base_url

from .launch_relay_resume import ROOT, ROUND_CONFIG, LaunchError, _pid_is_running

_CANARY_MINUTES = 3
_CANARY_MAX_MINUTES = 5
_RATES = (2.0, 3.0, 4.0, 5.0)


@dataclass(frozen=True)
class CrawlSnapshot:
    parsed: int
    fetched: int
    reused: int
    failed: int
    missing: int
    quarantine: int
    http_403: int
    http_429: int
    http_5xx: int
    raw_http_5xx: int
    timeouts: int
    changed_source_urls: int
    latest_update: str | None


class RateRampError(RuntimeError):
    """A ramp precondition or canary invariant failed."""


def snapshot(state_directory: Path) -> CrawlSnapshot:
    """Read durable health/provenance counters without changing a crawl."""
    crawl = sqlite3.connect(f"file:{state_directory / 'crawl.sqlite3'}?mode=ro", uri=True)
    checkpoints = sqlite3.connect(
        f"file:{state_directory / 'checkpoints.sqlite3'}?mode=ro", uri=True
    )
    try:
        row = crawl.execute(
            """SELECT
            SUM(parse_status='parsed'), SUM(network_status='fetched'), SUM(network_status='reused'),
            SUM(network_status='failed'), SUM(parse_status='missing'),
            SUM(error LIKE '%HTTP 403%'), SUM(error LIKE '%HTTP 429%'),
            SUM(error GLOB '*HTTP 5[0-9][0-9]*'), SUM(error LIKE '%Timeout%'), MAX(updated_at)
            FROM items"""
        ).fetchone()
        changed = checkpoints.execute(
            """SELECT count(*) FROM (SELECT url FROM snapshots GROUP BY url
            HAVING count(DISTINCT content_hash)>1)"""
        ).fetchone()[0]
        quarantined = checkpoints.execute("SELECT count(*) FROM quarantine").fetchone()[0]
        raw_5xx = 0
        has_retry_audit = crawl.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'retryable_responses'"
        ).fetchone()
        if has_retry_audit is not None:
            raw_5xx = int(crawl.execute(
                "SELECT count(*) FROM retryable_responses WHERE status_code BETWEEN 500 AND 599"
            ).fetchone()[0])
        values = [int(0 if value is None else value) for value in row[:-1]]
        return CrawlSnapshot(
            parsed=values[0], fetched=values[1], reused=values[2], failed=values[3],
            missing=values[4], quarantine=int(quarantined), http_403=values[5],
            http_429=values[6], http_5xx=values[7], timeouts=values[8],
            raw_http_5xx=raw_5xx, changed_source_urls=int(changed), latest_update=row[-1],
        )
    finally:
        crawl.close()
        checkpoints.close()


def _delta(before: CrawlSnapshot, after: CrawlSnapshot) -> tuple[str, ...]:
    violations: list[str] = []
    for field in (
        "http_403", "http_429", "http_5xx", "raw_http_5xx", "timeouts", "quarantine",
        "changed_source_urls",
    ):
        if getattr(after, field) > getattr(before, field):
            violations.append(field)
    if after.failed > before.failed or after.missing > before.missing:
        violations.append("failed_or_missing")
    return tuple(violations)


def _command(round_number: int, rate: float, relay_base_url: str, token_file: Path) -> list[str]:
    catalog, state_directory = ROUND_CONFIG[round_number]
    return [
        str(ROOT / ".venv/bin/elecciones-pipeline"), "precount-crawl", "--stage", "mesas",
        "--catalog", str(catalog), "--state-dir", str(state_directory), "--rate", str(rate),
        "--resume", "--relay-base-url", relay_base_url, "--relay-token-file", str(token_file),
    ]


def _read_pid(pid_path: Path) -> int:
    try:
        return int(pid_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError) as exc:
        raise RateRampError("crawler PID file is invalid") from exc


def _running_rate(pid: int) -> float:
    output = subprocess.run(  # noqa: S603,S607 - fixed local system binary and validated PID
        ["/bin/ps", "-p", str(pid), "-o", "command="], check=True, capture_output=True, text=True
    ).stdout.split()
    try:
        return float(output[output.index("--rate") + 1])
    except (IndexError, ValueError) as exc:
        raise RateRampError("existing writer has no verifiable --rate argument") from exc


def _await_exit(pid: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while _pid_is_running(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _pid_is_running(pid):
        raise RateRampError("crawler did not drain after SIGINT; refusing forced termination")


def _stop_single_writer(pid_path: Path, timeout_seconds: float = 30) -> int:
    pid = _read_pid(pid_path)
    if not _pid_is_running(pid):
        raise RateRampError("crawler PID file is stale; refusing ownership handoff")
    os.kill(pid, signal.SIGINT)
    _await_exit(pid, timeout_seconds)
    # The old process is proven absent before this removal and before any new
    # writer is started.  This is the handoff's no-overlap invariant.
    if _pid_is_running(pid):
        raise RateRampError("old writer is still alive")
    pid_path.unlink()
    return pid


def _start_single_writer(
    round_number: int, rate: float, relay_base_url: str, token_file: Path
) -> tuple[int, Path]:
    _catalog, state_directory = ROUND_CONFIG[round_number]
    pid_path = state_directory / "mesas-relay-resume.pid"
    if pid_path.exists():
        raise RateRampError("PID file exists; refusing a second writer")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = state_directory / "logs" / f"mesas-rate-ramp-{rate:g}-{timestamp}.log"
    with log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(  # noqa: S603 - reviewed, fixed local command construction
            _command(round_number, rate, relay_base_url, token_file), cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=log_file, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )
    time.sleep(0.5)
    if process.poll() is not None:
        raise RateRampError(f"replacement crawler exited with status {process.returncode}")
    # Atomic durable writer identity installation after the process is live.
    replacement = pid_path.with_suffix(".pid.new")
    replacement.write_text(f"{process.pid}\n", encoding="ascii")
    replacement.chmod(0o600)
    os.replace(replacement, pid_path)
    return process.pid, log_path


def ramp(
    round_number: int, target_rate: float, relay_base_url: str, token_file: Path,
    *, canary_minutes: int = _CANARY_MINUTES,
) -> dict[str, object]:
    """Move one crawler one rate step, automatically restoring its prior rate on failure."""
    if target_rate not in _RATES or target_rate == 2.0:
        raise RateRampError("target rate must be one of 3, 4, or 5 requests/second")
    if canary_minutes < _CANARY_MINUTES or canary_minutes > _CANARY_MAX_MINUTES:
        raise RateRampError("canary must be between three and five minutes")
    previous_rate = _RATES[_RATES.index(target_rate) - 1]
    _catalog, state_directory = ROUND_CONFIG[round_number]
    base_url = validate_relay_base_url(relay_base_url)
    load_relay_token(token_file)
    pid_path = state_directory / "mesas-relay-resume.pid"
    before = snapshot(state_directory)
    current_pid = _read_pid(pid_path)
    if _running_rate(current_pid) != previous_rate:
        raise RateRampError(
            f"target {target_rate:g} requires a clean prior {previous_rate:g} rps stage"
        )
    prior_pid = _stop_single_writer(pid_path)
    new_pid, log_path = _start_single_writer(round_number, target_rate, base_url, token_file)
    time.sleep(canary_minutes * 60)
    after = snapshot(state_directory)
    violations = _delta(before, after)
    if not violations and _pid_is_running(new_pid) and _read_pid(pid_path) == new_pid:
        return {"state": "canary_passed", "round": round_number, "prior_pid": prior_pid,
                "pid": new_pid, "rate": target_rate, "before": asdict(before),
                "after": asdict(after), "log_path": str(log_path)}
    # Circuit breaker: stop the failed candidate, prove absence, then resume at
    # the last reviewed stable rate.  If this fails we leave no overlapping writer.
    _stop_single_writer(pid_path)
    rollback_pid, rollback_log = _start_single_writer(
        round_number, previous_rate, base_url, token_file
    )
    return {"state": "rolled_back", "round": round_number, "prior_pid": prior_pid,
            "failed_pid": new_pid, "pid": rollback_pid, "rate": previous_rate,
            "violations": violations or ("writer_not_healthy",), "before": asdict(before),
            "after": asdict(after), "log_path": str(rollback_log)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=(1, 2), required=True)
    parser.add_argument("--target-rate", type=float, choices=(3.0, 4.0, 5.0), required=True)
    parser.add_argument("--relay-base-url", required=True)
    parser.add_argument("--relay-token-file", type=Path, required=True)
    parser.add_argument("--canary-minutes", type=int, default=_CANARY_MINUTES)
    args = parser.parse_args()
    try:
        result = ramp(
            args.round, args.target_rate, args.relay_base_url, args.relay_token_file,
            canary_minutes=args.canary_minutes,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (LaunchError, OSError, RateRampError, ValueError) as exc:
        print(json.dumps({"state": "ramp_failed", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
