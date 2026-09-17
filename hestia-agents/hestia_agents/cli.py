"""Build the deploy manifests, or deploy them onto a hearth.

    python -m hestia_agents.cli build
    python -m hestia_agents.cli deploy --hearth http://127.0.0.1:9480
    python -m hestia_agents.cli verify --hearth http://127.0.0.1:9480

The deploy token comes from HESTIA_DEPLOY_TOKEN and is never printed, not even
in an error. `announce` stays off unless it is asked for on the command line:
putting a row in the Hub catalogue is an outward-facing act, not a side effect
of deploying.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from hestia_agents.manifests import AGENTS, deploy_body, write_manifests

DEFAULT_HEARTH = "http://127.0.0.1:9480"


def _client():
    try:
        import httpx
    except ImportError:  # pragma: no cover - dev extra not installed
        raise SystemExit("deploy needs httpx: uv sync --extra dev --project .") from None
    return httpx


def _token() -> str:
    token = (os.environ.get("HESTIA_DEPLOY_TOKEN") or "").strip()
    if not token:
        raise SystemExit(
            "HESTIA_DEPLOY_TOKEN is empty. The hearth refuses every write without it — "
            "that is the intended default, not a fault."
        )
    return token


def cmd_build(_args: argparse.Namespace) -> int:
    for path in write_manifests():
        print("wrote", path.relative_to(path.parent.parent.parent))
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    httpx = _client()
    token = _token()
    slugs = args.only or list(AGENTS)
    failures = 0
    for slug in slugs:
        body = deploy_body(slug, announce=args.announce)
        response = httpx.post(
            f"{args.hearth.rstrip('/')}/v1/tenants",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        if response.status_code != 200:
            # Never echo the request: it carries the token header.
            print(f"  {slug}: FAILED {response.status_code} {response.text[:300]}")
            failures += 1
            continue
        out = response.json()
        print(f"  {slug}: {out['status']} -> {out['invoke_url']}")
    return 1 if failures else 0


PROBES: dict[str, dict[str, Any]] = {
    "rules-decide": {
        "policy": {
            "id": "probe@v1",
            "rules": [
                {
                    "id": "R1",
                    "when": [{"fact": "amount", "op": "<=", "value": 100}],
                    "then": {"decision": "approve", "reason": "under the limit"},
                }
            ],
            "default": {"decision": "deny", "reason": "over the limit"},
        },
        "facts": {"amount": 42},
    },
    "json-canonical": {"document": {"b": 1, "a": [1, 2]}},
    "commit-referee": {
        "commitment": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "value": "",
        "layout": "value",
    },
}


def cmd_verify(args: argparse.Namespace) -> int:
    """Invoke each deployed agent twice and prove the answer is reproducible."""
    httpx = _client()
    failures = 0
    for slug in args.only or list(AGENTS):
        url = f"{args.hearth.rstrip('/')}/t/{slug}/invoke"
        seen = []
        for _ in range(2):
            response = httpx.post(url, json=PROBES[slug], timeout=30.0)
            if response.status_code != 200:
                print(f"  {slug}: FAILED {response.status_code} {response.text[:200]}")
                failures += 1
                break
            seen.append(response.json())
        if len(seen) != 2:
            continue
        same_result = seen[0]["result"] == seen[1]["result"]
        same_signature = seen[0]["signature"] == seen[1]["signature"]
        mark = "ok" if same_result and same_signature else "NOT DETERMINISTIC"
        print(f"  {slug}: {mark} (signature repeats: {same_signature})")
        if not (same_result and same_signature):
            failures += 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hestia-agents")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="regenerate agents/*/deploy.json").set_defaults(func=cmd_build)

    for name, func, helptext in (
        ("deploy", cmd_deploy, "deploy every agent onto a hearth"),
        ("verify", cmd_verify, "invoke each agent twice and compare the receipts"),
    ):
        node = sub.add_parser(name, help=helptext)
        node.add_argument("--hearth", default=os.environ.get("HESTIA_PUBLIC_BASE", DEFAULT_HEARTH))
        node.add_argument("--only", action="append", choices=sorted(AGENTS))
        if name == "deploy":
            node.add_argument(
                "--announce",
                action="store_true",
                help="also announce to the Hub catalogue (off by default)",
            )
        node.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
