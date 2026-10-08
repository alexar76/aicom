#!/usr/bin/env python3
"""Kill abandoned `docker logs` CLI clients before they cost dockerd a core each, forever.

Why: on admin-vps (Docker 29.1.3) three `docker logs --tail N` clients left behind by ssh sessions
that had long since died (25 and 66 days old) each kept a tailfile scanner spinning inside dockerd —
~3 cores for weeks, found 2026-10-08 with a CPU profile from /debug/pprof on docker.sock. Killing the
client cancels the request and the scanner stops; nothing else in dockerd needed touching.

Rule: a `docker logs` / `docker container logs` / `docker compose logs` / `docker-compose logs` /
`docker service logs` process WITHOUT -f/--follow that has lived longer than --max-age seconds gets
SIGTERM, then SIGKILL after a grace period. A non-following logs call finishes in seconds; ten
minutes is never legitimate. Followers are left alone — they are meant to live long.

Stdlib only, reads /proc. Runs from deploy/docker-logs-reaper.timer every 5 minutes; every kill is
one line in the journal. `--dry-run` lists what it would kill.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time

DOCKER_BINS = {"docker", "docker-compose"}
# docker global options that take a separate value (`docker -H unix:///x logs ...`)
GLOBAL_VALUE_OPTS = {"-H", "--host", "-c", "--context", "--config", "-l", "--log-level",
                     "--tlscacert", "--tlscert", "--tlskey"}
# compose options that take a separate value (`docker compose -f a.yml logs ...`) — note -f is NOT follow here
COMPOSE_VALUE_OPTS = {"-f", "--file", "-p", "--project-name", "--project-directory", "--env-file",
                      "--profile", "--ansi", "--progress", "--parallel"}
PARENTS = {"container", "service"}


def _subcommand_args(argv: list[str]) -> list[str] | None:
    """Arguments after the `logs` subcommand, or None when argv is not a docker logs call."""
    if not argv or os.path.basename(argv[0]) not in DOCKER_BINS:
        return None
    compose = os.path.basename(argv[0]) == "docker-compose"
    i = 1
    while i < len(argv):
        tok = argv[i]
        if tok == "compose":  # also the plugin's own argv: docker-compose compose logs ...
            compose = True
        elif tok in PARENTS and not compose:
            pass
        elif tok == "logs":
            return argv[i + 1:]
        elif tok.startswith("-"):
            if "=" not in tok and (tok in (COMPOSE_VALUE_OPTS if compose else GLOBAL_VALUE_OPTS)):
                i += 1  # skip the option's value
        else:
            return None  # first positional is some other subcommand
        i += 1
    return None


def is_follow(args: list[str]) -> bool:
    for tok in args:
        if tok in ("-f", "--follow") or tok.startswith("--follow="):
            return tok != "--follow=false"
        if tok.startswith("-") and not tok.startswith("--") and tok[1:].isalpha() and "f" in tok[1:]:
            return True  # combined short flags, e.g. -tf
    return False


def is_stale_logs_call(argv: list[str]) -> bool:
    args = _subcommand_args(argv)
    return args is not None and not is_follow(args)


def _proc_age_s(pid: int, uptime_s: float, hz: int) -> float | None:
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except OSError:
        return None
    # comm may contain spaces/parens: fields after the last ')' start at field 3
    fields = stat[stat.rindex(")") + 2:].split()
    return uptime_s - int(fields[19]) / hz  # field 22 = starttime


def candidates(max_age: float) -> list[tuple[int, float, list[str]]]:
    hz = os.sysconf("SC_CLK_TCK")
    uptime_s = float(open("/proc/uptime").read().split()[0])
    found = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            raw = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            continue
        argv = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        if not is_stale_logs_call(argv):
            continue
        age = _proc_age_s(pid, uptime_s, hz)
        if age is not None and age > max_age:
            found.append((pid, age, argv))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--max-age", type=float, default=600, help="seconds a non-following call may live")
    ap.add_argument("--grace", type=float, default=5, help="seconds between SIGTERM and SIGKILL")
    ap.add_argument("--dry-run", action="store_true")
    opts = ap.parse_args()

    stale = candidates(opts.max_age)
    for pid, age, argv in stale:
        verb = "would kill" if opts.dry_run else "killing"
        print(f"{verb} pid={pid} age={age / 3600:.1f}h: {' '.join(argv)[:200]}", flush=True)
        if not opts.dry_run:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    if stale and not opts.dry_run:
        time.sleep(opts.grace)
        for pid, _, _ in stale:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"pid={pid} ignored SIGTERM, sent SIGKILL", flush=True)
            except ProcessLookupError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
