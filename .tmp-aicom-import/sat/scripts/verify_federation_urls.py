#!/usr/bin/env python3
"""Check that a hub and its seeds advertise URLs a stranger can actually reach.

    python3 scripts/verify_federation_urls.py                       # prod defaults
    python3 scripts/verify_federation_urls.py --hub http://127.0.0.1:9083
    python3 scripts/verify_federation_urls.py --seeds a.json,b.json  # override seed list

Why this exists: on 2026-07-31 modelmarket.dev served an empty catalogue for a day with
every component reporting healthy. Three URLs were wrong and nothing looked at them:

  * the factory advertised ``manifest_url: http://localhost:9080`` in its own
    ``.well-known`` — correct from inside its container, unreachable from the hub's;
  * the oracle host advertised ``http://<raw-ip>/ai-market/v2/manifest``, which 404s,
    because ``PLATON_PUBLIC_URL`` was never set to the public origin;
  * the committed seed list pointed at one oracle's well-known (11 capabilities) while
    its own note described the family aggregate (42).

Each failure is invisible from the outside: the hub answers 200, the peer row is written
*before* the manifest fetch, so ``peers_count`` and the peer's advertised
``capabilities_count`` both look right while ``federated_capabilities_count`` stays 0.

Exit status is 1 when any check fails, so ``deploy_hub.sh`` and CI can gate on it.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

TIMEOUT = 15
DEFAULT_HUB = os.environ.get("AIMARKET_HUB_URL", "https://modelmarket.dev")
SEEDS_FILE = Path(__file__).resolve().parents[1] / "aimarket-hub" / "aimarket_hub" / "federation_seeds.json"

# A URL only these can reach is not an advertisement, it is a note-to-self.
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}

ok_count = 0
fail_count = 0
warn_count = 0


def check(passed: bool, message: str, detail: str = "", *, soft: bool = False) -> bool:
    """`soft` reports a state that is legitimate but worth seeing — an empty peer, say.

    Kept out of the exit status on purpose: a deploy that fails because a correctly
    configured peer has nothing to sell teaches operators to ignore this script.
    """
    global ok_count, fail_count, warn_count
    if passed:
        ok_count += 1
        print(f"  \033[32m✓\033[0m {message}")
    elif soft:
        warn_count += 1
        print(f"  \033[33m!\033[0m {message}" + (f"\n      {detail}" if detail else ""))
    else:
        fail_count += 1
        print(f"  \033[31m✗\033[0m {message}" + (f"\n      {detail}" if detail else ""))
    return passed


def get_json(url: str) -> tuple[dict | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "aimarket-federation-check/1"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read()), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # DNS, TLS, timeout, invalid JSON
        return None, f"{type(e).__name__}: {e}"


def url_is_public(url: str) -> tuple[bool, str]:
    """Reject loopback names, raw IP literals and plain HTTP for advertised URLs."""
    if not url:
        return False, "empty"
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False, f"unparseable: {url}"
    if host in LOOPBACK_HOSTS:
        return False, f"loopback host — only the advertiser itself can reach {url}"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        pass  # a name, which is what we want
    else:
        kind = "private" if ip.is_private else "public"
        return False, f"raw {kind} IP literal instead of a hostname: {url}"
    if urlparse(url).scheme != "https":
        return False, f"not https: {url}"
    return True, ""


def check_advertised(label: str, doc: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        value = doc.get(key)
        if value is None:
            continue
        good, why = url_is_public(str(value))
        check(good, f"{label} {key} is publicly reachable", why)


def check_manifest(label: str, manifest_url: str, pinned_key: str | None) -> int:
    """Fetch the advertised manifest. Returns its capability count (0 on failure)."""
    good, why = url_is_public(manifest_url)
    if not check(good, f"{label} manifest_url is publicly reachable", why):
        return 0
    manifest, err = get_json(manifest_url)
    if not check(manifest is not None, f"{label} manifest fetches", f"{manifest_url} → {err}"):
        return 0
    count = int(manifest.get("capabilities_count") or manifest.get("total_capabilities") or 0)
    check(
        count > 0,
        f"{label} manifest lists capabilities",
        f"capabilities_count={count} — the node is reachable and correct, it simply has nothing "
        "to sell (for the factory: no product in a shipped state carries an invoke_url)",
        soft=True,
    )
    base = str(manifest.get("base_url") or "")
    if base:
        good, why = url_is_public(base)
        check(good, f"{label} manifest base_url is publicly reachable", why)
    if pinned_key:
        actual = ((manifest.get("signature") or {}).get("public_key") or "").strip()
        check(
            actual == pinned_key,
            f"{label} signs with the pinned key",
            f"seed pins {pinned_key[:16]}… but the manifest is signed by {actual[:16] or '(none)'}… "
            "— a pin mismatch means untrusted-first-contact, so nothing is indexed on this crawl",
        )
    return count


def load_seeds(override: str | None) -> list[dict]:
    if override:
        return [{"name": u, "well_known_url": u, "public_key": None} for u in override.split(",") if u.strip()]
    env = os.environ.get("AIMARKET_SEED_LIST", "").strip()
    if env:
        pins = [p for p in os.environ.get("AIMARKET_SEED_PUBKEYS", "").split(",") if p.strip()]
        seeds = []
        for i, u in enumerate(x.strip() for x in env.split(",") if x.strip()):
            seeds.append({"name": u, "well_known_url": u, "public_key": pins[i] if i < len(pins) else None})
        return seeds
    if SEEDS_FILE.is_file():
        return json.loads(SEEDS_FILE.read_text()).get("seeds", [])
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default=DEFAULT_HUB, help=f"hub base URL (default {DEFAULT_HUB})")
    ap.add_argument("--seeds", help="comma-separated well-known URLs (default: env AIMARKET_SEED_LIST, else the committed seeds file)")
    ap.add_argument("--skip-hub", action="store_true", help="only check the seeds")
    args = ap.parse_args()

    hub = args.hub.rstrip("/")
    peer_advertised = 0

    if not args.skip_hub:
        print(f"\n\033[1mHub {hub}\033[0m")
        wk, err = get_json(f"{hub}/.well-known/ai-market.json")
        if check(wk is not None, "hub .well-known fetches", err):
            check_advertised("hub", wk, ("manifest_url", "mcp_endpoint", "hub_url"))
            check_manifest("hub", str(wk.get("manifest_url") or ""), None)

    for seed in load_seeds(args.seeds):
        wk_url = seed.get("well_known_url") or ""
        print(f"\n\033[1mSeed {seed.get('name') or wk_url}\033[0m")
        good, why = url_is_public(wk_url)
        if not check(good, "seed well-known URL is publicly reachable", why):
            continue
        wk, err = get_json(wk_url)
        if not check(wk is not None, "seed .well-known fetches", f"{wk_url} → {err}"):
            continue
        check_advertised("seed", wk, ("manifest_url", "mcp_endpoint", "hub_url"))
        count = check_manifest("seed", str(wk.get("manifest_url") or ""), seed.get("public_key"))
        own = int(wk.get("capabilities_count") or 0)
        # An aggregator hub splits the two numbers: `capabilities_count` is what it
        # provides itself and `federated_capabilities_count` is what it re-exports,
        # while its manifest serves both. Comparing the manifest against `own` alone
        # reported the Signal Hunt Hub as broken for advertising 5 + 112 against a
        # 112-tool manifest — a correct aggregator failing a check meant for a leaf.
        federated = int(wk.get("federated_capabilities_count") or 0)
        advertised = own + federated
        check(
            advertised == count or count == 0 or (federated and own <= count <= advertised),
            "seed's advertised count matches its manifest",
            f".well-known says {advertised}"
            + (f" ({own} own + {federated} re-exported)" if federated else "")
            + f", manifest lists {count} — the hub writes the peer row from "
            "the well-known and the capabilities from the manifest, so a gap here is exactly the "
            "'peer with N capabilities, 0 federated' symptom",
        )
        peer_advertised += count

    if not args.skip_hub and peer_advertised:
        print(f"\n\033[1mIndexed catalogue\033[0m")
        stats, err = get_json(f"{hub}/ai-market/v2/stats/live?limit=1")
        if check(stats is not None, "hub live stats fetch", err):
            s = stats.get("summary") or {}
            federated = int(s.get("federated_capabilities_count") or 0)
            check(
                federated > 0,
                f"hub indexed federated capabilities ({federated} of {peer_advertised} advertised)",
                "peers advertise capabilities the hub has not indexed — check the crawler log for "
                "'Invalid manifest signature' (canonical drift) or an unreachable manifest_url",
            )

    tail = f", {warn_count} warned" if warn_count else ""
    print(f"\n{ok_count} passed, {fail_count} failed{tail}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
