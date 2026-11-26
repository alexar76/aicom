#!/usr/bin/env python3
"""Self-heal for WARDEN's weekly ERC-8004 feedback refresh on admin-vps.

systemd warden-feedback.timer still fires next Monday after a failed oneshot
(Persistent=true). This watchdog covers the gap: if last-run.json is missing,
older than STALE_S, or status != ok after a cooldown, it starts
warden-feedback.service. Starts are rate-limited so a stuck failure cannot
spam Base transactions.

  /opt/warden-feedback/warden_feedback_watchdog.py           # check + maybe start
  /opt/warden-feedback/warden_feedback_watchdog.py --dry-run # print decision only

Installed by deploy/erc-8004/install_refresh.sh; timer: warden-feedback-watch.timer.
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import subprocess
import sys
import time

LAST_RUN = os.environ.get("WARDEN_FB_LAST_RUN", "/var/www/warden-feedback/last-run.json")
STATE = os.environ.get("WARDEN_FB_WATCH_STATE", "/var/lib/warden-feedback/watchdog-state.json")
UNIT = os.environ.get("WARDEN_FB_UNIT", "warden-feedback.service")
# Heal before the 8-day Telegram page in scripts/warden_feedback_notify.py.
STALE_S = int(os.environ.get("WARDEN_FB_STALE_S", str(7 * 86400)))
# After a failed run (or a watchdog start), wait before trying again.
RETRY_S = int(os.environ.get("WARDEN_FB_RETRY_S", str(6 * 3600)))
COOLDOWN_S = int(os.environ.get("WARDEN_FB_COOLDOWN_S", str(6 * 3600)))


def parse_ran_at(ran: str) -> int | None:
    if not ran or not isinstance(ran, str):
        return None
    try:
        return calendar.timegm(time.strptime(ran, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


def load_json(path: str) -> dict:
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def unit_busy(unit: str = UNIT) -> bool:
    """True when the oneshot is already running (active or activating)."""
    try:
        out = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=15, check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out in ("active", "activating", "reloading")


def decide(last_run: dict | None, state: dict, now: float,
           *, busy: bool = False,
           stale_s: int = STALE_S, retry_s: int = RETRY_S,
           cooldown_s: int = COOLDOWN_S) -> tuple[bool, str]:
    """Return (should_start, reason). Pure — used by tests and the live runner."""
    if busy:
        return False, "service already running"
    last_start = float(state.get("lastStartAt") or 0)
    if last_start and now - last_start < cooldown_s:
        return False, f"watchdog cooldown ({int(cooldown_s / 3600)}h)"

    if not last_run:
        return True, "last-run.json missing or unreadable"

    ran_ts = parse_ran_at(str(last_run.get("ranAt") or ""))
    if ran_ts is None:
        return True, "last-run.json has no usable ranAt"

    age = now - ran_ts
    status = str(last_run.get("status") or "")
    if status != "ok":
        if age < retry_s:
            return False, f"failed run still inside retry window ({int(retry_s / 3600)}h)"
        return True, f"last run status={status!r} ({int(age / 3600)}h ago)"
    if age > stale_s:
        return True, f"last ok run stale ({int(age / 86400)}d > {int(stale_s / 86400)}d)"
    return False, "last run ok and fresh"


def start_unit(unit: str = UNIT, dry_run: bool = False) -> None:
    if dry_run:
        print(f"would: systemctl start --no-block {unit}")
        return
    subprocess.run(["systemctl", "start", "--no-block", unit], check=True, timeout=60)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the decision; do not start the service or write state")
    ap.add_argument("--last-run", default=LAST_RUN)
    ap.add_argument("--state", default=STATE)
    args = ap.parse_args(argv)

    now = time.time()
    if not os.path.exists(args.last_run):
        last_run = None
    else:
        last_run = load_json(args.last_run)
    state = load_json(args.state)
    busy = unit_busy()
    start, reason = decide(last_run, state, now, busy=busy)
    print(f"warden-feedback-watch: start={start} reason={reason}")
    if not start:
        return 0
    start_unit(dry_run=args.dry_run)
    if not args.dry_run:
        state = {**state, "lastStartAt": now, "lastReason": reason,
                 "lastStartAtIso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))}
        os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
        with open(args.state, "w") as f:
            json.dump(state, f, indent=1)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
