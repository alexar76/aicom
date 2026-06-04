#!/usr/bin/env python3
"""
Fill missing production-oriented keys in ``.env`` (append-only, does not overwrite).

Typical automation:
  - ``AIFACTORY_FIREWALL_RULES_FERNET_KEY`` — Fernet key if ``cryptography`` is importable.
  - ``AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION`` — default ``1`` when absent.
  - ``NEXT_PUBLIC_SITE_URL`` + ``AIFACTORY_CORS_ORIGINS`` — when ``--public-url`` is passed
    and those keys are not already set in the file.
  - ``AIFACTORY_DEMO_READONLY=1`` — when ``--public-url`` host is ``magic-ai-factory.com`` (public demo).

Why not always auto-guess CORS? The factory cannot know your real public URL without you
(or reverse-proxy headers at runtime). Passing ``--public-url`` once fixes that.

Usage:
  python3 scripts/fill_production_env.py --env-file .env
  python3 scripts/fill_production_env.py --env-file .env --public-url https://app.example.com
  python3 scripts/fill_production_env.py --env-file .env --dry-run
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 scripts/fill_production_env.py` (documented usage): when run as a
# script, sys.path[0] is the scripts/ dir, so `from core...` below would fail.
# Put the repository root on sys.path so first-party packages import cleanly.
_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _active_keys(env_text: str) -> set[str]:
    """Keys that have a non-comment assignment."""
    keys: set[str] = set()
    for line in env_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def _shell_quote(val: str) -> str:
    if re.search(r"[^\w@%+=:,./-]", val):
        return "'" + val.replace("'", "'\"'\"'") + "'"
    return val


def main() -> int:
    ap = argparse.ArgumentParser(description="Append missing security/deploy keys to .env")
    ap.add_argument("--env-file", type=Path, default=Path(".env"), help="Target env file (default: ./.env)")
    ap.add_argument(
        "--public-url",
        dest="public_url",
        default="",
        help="HTTPS/HTTP site origin (no trailing slash). Sets NEXT_PUBLIC_SITE_URL and AIFACTORY_CORS_ORIGINS if missing.",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    args = ap.parse_args()

    env_path: Path = args.env_file
    public_url = (args.public_url or "").strip().rstrip("/")

    if not env_path.exists():
        print(f"error: {env_path} does not exist — create it first (e.g. cp .env.example .env)", file=sys.stderr)
        return 2

    raw = env_path.read_text(encoding="utf-8")
    keys = _active_keys(raw)
    additions: list[tuple[str, str]] = []

    if public_url:
        if "NEXT_PUBLIC_SITE_URL" not in keys:
            additions.append(("NEXT_PUBLIC_SITE_URL", public_url))
        if "AIFACTORY_CORS_ORIGINS" not in keys:
            additions.append(("AIFACTORY_CORS_ORIGINS", public_url))
        host = public_url.lower().replace("https://", "").replace("http://", "").split("/")[0]
        if "magic-ai-factory.com" in host and "AIFACTORY_DEMO_READONLY" not in keys:
            additions.append(("AIFACTORY_DEMO_READONLY", "1"))
        if "NEXT_PUBLIC_GA_MEASUREMENT_ID" not in keys:
            from core.ga4_defaults import GA4_MEASUREMENT_ID

            additions.append(("NEXT_PUBLIC_GA_MEASUREMENT_ID", GA4_MEASUREMENT_ID))

    if "AIFACTORY_FIREWALL_RULES_FERNET_KEY" not in keys:
        try:
            from cryptography.fernet import Fernet

            additions.append(("AIFACTORY_FIREWALL_RULES_FERNET_KEY", Fernet.generate_key().decode("ascii")))
        except Exception as e:
            print(
                f"warning: could not import cryptography ({e}); skip AIFACTORY_FIREWALL_RULES_FERNET_KEY",
                file=sys.stderr,
            )

    if "AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION" not in keys:
        additions.append(("AIFACTORY_SANDBOX_PREVIEW_NETWORK_ISOLATION", "1"))

    if "AIFACTORY_SANDBOX_REQUIRE_CONTAINER" not in keys:
        additions.append(("AIFACTORY_SANDBOX_REQUIRE_CONTAINER", "1"))

    if "GRAFANA_ADMIN_PASSWORD" not in keys:
        additions.append(("GRAFANA_ADMIN_PASSWORD", secrets.token_urlsafe(24)))

    if "AIFACTORY_SANDBOX_DEMO_PASSWORD" not in keys:
        additions.append(("AIFACTORY_SANDBOX_DEMO_PASSWORD", secrets.token_urlsafe(24)))

    if not additions:
        print("fill_production_env: nothing to add (all keys already present).")
        return 0

    block = (
        f"\n# --- filled by scripts/fill_production_env.py ({datetime.now(timezone.utc).isoformat()}) ---\n"
        + "\n".join(f"{k}={_shell_quote(v)}" for k, v in additions)
        + "\n"
    )

    if args.dry_run:
        print("fill_production_env: dry-run, would append:\n" + block)
        return 0

    env_path.write_text(raw.rstrip() + block, encoding="utf-8")
    print(f"fill_production_env: appended {len(additions)} key(s) to {env_path}")
    for k, _ in additions:
        print(f"  + {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
