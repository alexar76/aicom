#!/usr/bin/env python3
"""Keep competing-lab nginx edge up after apt reloads or transient config/DNS blips.

Stdlib only — safe to run from a bare systemd timer (no venv).
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime, timezone


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except OSError:
        return False


def main() -> int:
    when = datetime.now(timezone.utc).isoformat()
    nginx_active = _run(["systemctl", "is-active", "--quiet", "nginx"]).returncode == 0
    https_up = _listening(443)
    out: dict[str, object] = {
        "ok": True,
        "when": when,
        "nginx_active": nginx_active,
        "https_listening": https_up,
        "action": "none",
    }

    if nginx_active and https_up:
        print(json.dumps(out))
        return 0

    test = _run(["nginx", "-t"])
    if test.returncode != 0:
        out.update(
            {
                "ok": False,
                "action": "nginx_t_failed",
                "nginx_t": (test.stderr or test.stdout)[-500:],
            }
        )
        print(json.dumps(out))
        return 1

    for action, cmd in (
        ("start", ["systemctl", "start", "nginx"]),
        ("restart", ["systemctl", "restart", "nginx"]),
    ):
        proc = _run(cmd)
        if proc.returncode == 0 and _listening(443):
            out.update({"action": action, "ok": True, "https_listening": True})
            print(json.dumps(out))
            return 0

    out.update(
        {
            "ok": False,
            "action": "start_and_restart_failed",
            "https_listening": _listening(443),
        }
    )
    print(json.dumps(out))
    return 1


if __name__ == "__main__":
    sys.exit(main())
