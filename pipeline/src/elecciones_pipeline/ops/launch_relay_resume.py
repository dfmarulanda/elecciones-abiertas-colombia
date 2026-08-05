"""Launch one reviewed local pre-count resume with durable PID and logs."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from elecciones_pipeline.ingest.relay_transport import (
    load_relay_token,
    validate_relay_base_url,
)

ROOT = Path(__file__).resolve().parents[4]
ROUND_CONFIG = {
    1: (
        ROOT / "config/sources/presidencia-2026-primera-vuelta.json",
        ROOT / ".pipeline/official-2026-round1",
    ),
    2: (
        ROOT / "config/sources/presidencia-2026-segunda-vuelta.json",
        ROOT / ".pipeline/official-2026-round2",
    ),
}


class LaunchError(RuntimeError):
    """The durable resume process could not be launched safely."""


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def launch(round_number: int, relay_base_url: str, relay_token_file: Path) -> dict[str, object]:
    catalog, state_directory = ROUND_CONFIG[round_number]
    base_url = validate_relay_base_url(relay_base_url)
    load_relay_token(relay_token_file)
    port = int(base_url.rsplit(":", 1)[1])
    with socket.create_connection(("127.0.0.1", port), timeout=3):
        pass
    executable = shutil.which("elecciones-pipeline")
    if executable is None:
        raise LaunchError("elecciones-pipeline executable is unavailable")
    pid_path = state_directory / "mesas-relay-resume.pid"
    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text(encoding="ascii").strip())
        except ValueError as exc:
            raise LaunchError("existing relay-resume PID file is invalid") from exc
        if _pid_is_running(existing_pid):
            raise LaunchError("an existing relay resume process is still running")
        raise LaunchError("a stale relay-resume PID file must be reviewed, not overwritten")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = state_directory / "logs" / f"mesas-relay-resume-{timestamp}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "precount-crawl",
        "--stage",
        "mesas",
        "--catalog",
        str(catalog),
        "--state-dir",
        str(state_directory),
        "--rate",
        "2",
        "--resume",
        "--relay-base-url",
        base_url,
        "--relay-token-file",
        str(relay_token_file),
    ]
    with log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(  # noqa: S603 - fully constructed reviewed local command
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    pid_path.write_text(f"{process.pid}\n", encoding="ascii")
    pid_path.chmod(0o600)
    time.sleep(0.5)
    status = process.poll()
    if status is not None:
        raise LaunchError(f"relay resume exited during launch with status {status}")
    return {
        "crawl_started": True,
        "log_path": str(log_path),
        "pid": process.pid,
        "pid_path": str(pid_path),
        "rate_per_host": 2,
        "round_number": round_number,
        "stage": "mesas",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, choices=(1, 2), required=True)
    parser.add_argument("--relay-base-url", required=True)
    parser.add_argument("--relay-token-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = launch(args.round, args.relay_base_url, args.relay_token_file)
    except (KeyError, OSError, LaunchError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "state": "launch_failed"}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
