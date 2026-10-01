#!/usr/bin/env python3
"""
Health watchdog for AI-Factory + AIMarket stack.

Checks HTTP endpoints and optional on-chain balances; sends Telegram on failure.

Usage:
  python3 scripts/ecosystem_watchdog.py
  python3 scripts/ecosystem_watchdog.py --no-telegram   # cron dry-run / CI

Env (optional overrides):
  WATCHDOG_FACTORY_URL   default https://magic-ai-factory.com/api/health
  WATCHDOG_HUB_URL       default https://modelmarket.dev/health
  WATCHDOG_ORACLES_URL   default https://oracles.modelmarket.dev/health
  WATCHDOG_ARGUS_LANDING default https://magic-ai-factory.com/argus/
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Check:
    name: str
    url: str
    expect_status: int = 200


DEFAULT_CHECKS = (
    Check("factory", os.environ.get("WATCHDOG_FACTORY_URL", "https://magic-ai-factory.com/api/health")),
    Check("hub", os.environ.get("WATCHDOG_HUB_URL", "https://modelmarket.dev/ai-market/v2/health")),
    Check("oracles", os.environ.get("WATCHDOG_ORACLES_URL", "https://oracles.modelmarket.dev/health")),
    Check("argus-landing", os.environ.get("WATCHDOG_ARGUS_LANDING", "https://magic-ai-factory.com/argus/")),
    Check("aicom-landing", os.environ.get("WATCHDOG_LANDING", "https://magic-ai-factory.com/landing-page-generation/")),
)


def probe(check: Check, timeout: float = 12.0) -> tuple[bool, str]:
    req = urllib.request.Request(check.url, method="GET", headers={"User-Agent": "aicom-watchdog/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code != check.expect_status:
                return False, f"HTTP {code} (expected {check.expect_status})"
            return True, f"HTTP {code}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code} {e.reason}"
    except Exception as e:
        return False, str(e)


def notify_telegram(text: str) -> tuple[bool, str]:
    try:
        from web.backend.services.telegram_pipeline_notify import send_telegram_message_sync

        return send_telegram_message_sync(text)
    except Exception as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ecosystem HTTP health watchdog")
    ap.add_argument("--no-telegram", action="store_true", help="Skip Telegram alerts")
    args = ap.parse_args()

    failures: list[str] = []
    for check in DEFAULT_CHECKS:
        ok, detail = probe(check)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {check.name}: {check.url} — {detail}")
        if not ok:
            failures.append(f"• {check.name}: {detail} ({check.url})")

    if not failures:
        print("All checks passed.")
        return 0

    message = "🚨 AICOM watchdog\n\n" + "\n".join(failures)
    print(message, file=sys.stderr)
    if not args.no_telegram:
        sent, info = notify_telegram(message)
        print(f"Telegram: sent={sent} ({info})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
