"""Launch a detached Railway SSH loopback forward with a durable PID."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from pathlib import Path


class ForwardLaunchError(RuntimeError):
    """The private SSH forward could not be launched safely."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--local-port", type=int, required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.pid_file.exists():
            raise ForwardLaunchError("SSH forward PID file already exists")
        for path in (args.config, args.identity, args.known_hosts):
            if not path.is_file():
                raise ForwardLaunchError("SSH forward input file is missing")
        with args.log_file.open("ab", buffering=0) as log_file:
            process = subprocess.Popen(  # noqa: S603 - reviewed fixed ssh executable/options
                [
                    "/usr/bin/ssh",
                    "-F",
                    str(args.config),
                    "-i",
                    str(args.identity),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ExitOnForwardFailure=yes",
                    "-o",
                    "StrictHostKeyChecking=yes",
                    "-o",
                    f"UserKnownHostsFile={args.known_hosts}",
                    "-N",
                    "-L",
                    f"127.0.0.1:{args.local_port}:127.0.0.1:{args.remote_port}",
                    args.alias,
                ],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        args.pid_file.write_text(f"{process.pid}\n", encoding="ascii")
        args.pid_file.chmod(0o600)
        deadline = time.monotonic() + 5
        while True:
            if process.poll() is not None:
                raise ForwardLaunchError("SSH forward exited during launch")
            try:
                with socket.create_connection(
                    ("127.0.0.1", args.local_port), timeout=0.5
                ):
                    break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    process.terminate()
                    process.wait(timeout=3)
                    args.pid_file.unlink(missing_ok=True)
                    raise ForwardLaunchError(
                        "SSH forward did not become ready within 5 seconds"
                    ) from exc
                time.sleep(0.1)
        print(
            json.dumps(
                {
                    "local_bind": f"127.0.0.1:{args.local_port}",
                    "pid": process.pid,
                    "pid_file": str(args.pid_file),
                    "state": "ssh_forward_running",
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ForwardLaunchError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "state": "ssh_forward_failed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
