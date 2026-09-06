#!/usr/bin/env python3
"""Assert, from outside, that the hub still charges for paid work — and still answers MCP.

Payment enforcement on modelmarket.dev has silently regressed twice (2026-07-31 and
2026-08-04, docs/payment-enable-runbook.md): the hub kept serving, it just stopped
charging, and nothing noticed because nothing was watching. A one-time fix is worth
little against a failure mode that recurs, so this runs on a schedule and fails loudly.

It deliberately checks two independent facts. ``payment_configured: true`` is what the
hub SAYS about itself; a 402 on a real priced capability is what it DOES. Those came
apart once already — the flag was true while forty-two federated capabilities were free
to call — so the flag alone is not evidence.

The MCP checks are here for the same reason: https://modelmarket.dev/mcp is the URL the
registry listings hand to strangers, and an endpoint that quietly stops answering is
indistinguishable from a project nobody uses.

Peer liveness is checked too, and separately, because the payment probes are blind to it:
the hub answers 402 before it ever contacts the provider, so a priced capability looks
perfectly gated while the satellite behind it is in the ground. That happened on
2026-08-16 — GAIA served its manifest with a clean 200 while its invoke endpoint hung, and
this canary reported all-green throughout.

    scripts/payment_canary.py                      # human summary, non-zero exit on failure
    scripts/payment_canary.py --json               # machine-readable
    scripts/payment_canary.py --publish /var/www/verify.modelmarket.dev/status.json

No third-party imports: this has to run from a bare cron on a host that has no venv.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HUB = os.environ.get("AIMARKET_HUB_URL", "https://modelmarket.dev").rstrip("/")
USER_AGENT = "aimarket-payment-canary/1.0 (+https://modelmarket.dev)"


class Check:
    """One assertion, with the evidence that decided it."""

    def __init__(self, name: str, ok: bool, detail: str, critical: bool = True):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.critical = critical

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail, "critical": self.critical}


# ── evaluation: pure, so the interesting cases are testable without a network ────────────

def evaluate(
    manifest: dict[str, Any] | None,
    probes: list[dict[str, Any]] | dict[str, Any] | None,
    mcp_info: dict[str, Any] | None,
    peers: list[dict[str, Any]] | None = None,
) -> list[Check]:
    """Turn the observations into verdicts.

    ``probes`` is one entry per provider probed:
    ``{"status": int, "body": dict, "capability_id": str, "source_hub": str}`` from invoking
    a priced capability with no payment channel and no trial header.
    """
    if isinstance(probes, dict):
        probes = [probes]
    checks: list[Check] = []

    if not manifest:
        return [Check("manifest_served", False, "/.well-known/ai-market.json did not answer")]
    checks.append(Check("manifest_served", True, f"hub {manifest.get('name') or '?'} answered"))

    configured = manifest.get("payment_configured")
    checks.append(Check(
        "payment_configured", configured is True,
        f"manifest says payment_configured={configured!r}",
    ))

    testnet = manifest.get("payment_testnet")
    checks.append(Check(
        "mainnet", testnet is False,
        f"payment_testnet={testnet!r} (must be false — testnet money proves nothing)",
    ))

    if not probes:
        checks.append(Check("priced_capability_gated", False,
                            "no priced capability found to probe — cannot prove the paywall"))

    # Every provider that advertises a price must have been probed. A provider missing from
    # this run is not "fine", it is unproven — and an unproven paywall is how forty-two oracle
    # capabilities stayed free for a month and ATLAS's six for as long as they were listed.
    expected = set(manifest.get("_priced_providers") or [])
    if expected:
        probed = {str(p.get("source_hub") or "local") for p in probes or []}
        unproven = sorted(expected - probed)
        checks.append(Check(
            "every_priced_provider_probed", not unproven,
            f"{len(probed)}/{len(expected)} priced providers probed"
            + (f" — UNPROVEN: {', '.join(unproven)}. Each of these advertises a price the "
               f"paywall was never tested on this run; raise MAX_PROBES or fix the picker."
               if unproven else ""),
        ))
    for probe in probes or []:
        status = probe.get("status")
        body = probe.get("body") or {}
        cap = probe.get("capability_id", "?")
        hub = probe.get("source_hub") or "local"
        price = probe.get("price_usd")
        # One check per provider: enforcement is decided per peer (AIMARKET_SELLS_FOR) and
        # again for local capabilities, so a single verdict would average away a provider
        # whose paid work is being given away.
        name = f"priced_capability_gated[{hub}]"
        if status == 402:
            checks.append(Check(name, True, f"{cap} answered 402 {body.get('error') or ''}".strip()))
        elif status == 200:
            checks.append(Check(
                name, False,
                f"{cap} (${price}/call, provider {hub}) was SERVED FOR FREE (HTTP 200) — "
                f"either enforcement regressed or this provider is missing from "
                f"AIMARKET_SELLS_FOR; see docs/payment-enable-runbook.md",
            ))
        else:
            # Not a pass: an error here means the probe proved nothing either way.
            checks.append(Check(
                name, False,
                f"{cap} answered HTTP {status} — expected 402; {json.dumps(body)[:200]}",
            ))

    if mcp_info is None:
        checks.append(Check("mcp_endpoint_live", False, f"GET /mcp did not answer"))
    else:
        service = mcp_info.get("service")
        checks.append(Check(
            "mcp_endpoint_live", service == "aimarket-hub-mcp",
            f"GET /mcp reports service={service!r} tools={mcp_info.get('tools')}",
        ))
        checks.append(Check(
            "mcp_trial_per_caller", mcp_info.get("trial") == "per-caller",
            f"GET /mcp reports trial={mcp_info.get('trial')!r} — a shared trial identity "
            f"means the endpoint 402s every stranger after the first few",
        ))

    for peer in peers or []:
        url = peer.get("url") or "?"
        # Critical only for peers whose capabilities are sold: those failures cost money and
        # credibility. A free peer going quiet is worth knowing and not worth waking anyone.
        name = f"peer_alive[{url}]"
        critical = bool(peer.get("sells"))
        if peer.get("alive"):
            checks.append(Check(name, True,
                                f"invoke endpoint answered HTTP {peer.get('status')}",
                                critical=critical))
        elif peer.get("manifest_ok"):
            # The exact shape of the 2026-08-16 GAIA outage: manifest served, invoke hung.
            # Checking the manifest alone would have called this healthy.
            checks.append(Check(
                name, False,
                f"manifest is served but the invoke endpoint did not answer "
                f"({peer.get('error') or 'no response'}) — its capabilities 502 for every caller",
                critical=critical))
        else:
            checks.append(Check(name, False,
                                f"unreachable: {peer.get('error') or 'no response'}",
                                critical=critical))
        if not peer.get("endpoint_routable", True):
            # Not an outage, but it makes the peer unusable to anyone who believes its
            # manifest: a routing hub that honours mcp_endpoint dials its own machine.
            checks.append(Check(
                f"peer_endpoint_routable[{url}]", False,
                f"advertises mcp_endpoint={peer.get('advertised_endpoint')!r} — that address "
                f"resolves to the reader's own machine, so no peer can route an invoke to it",
                critical=False))

    servers = manifest.get("mcp_servers") or []
    hosted = [s for s in servers if s.get("transport") == "streamable-http" and s.get("url")]
    checks.append(Check(
        "mcp_advertised", bool(hosted),
        f"manifest lists {len(hosted)} hosted MCP server(s): "
        f"{', '.join(s.get('url', '') for s in hosted) or 'none — only install-it-yourself entries'}",
        critical=False,
    ))

    return checks


# ── observation ──────────────────────────────────────────────────────────────────────────

def _get(url: str, timeout: float) -> tuple[int, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}
    except Exception:
        return 0, None


def _post(url: str, payload: dict, timeout: float) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}
    except Exception:
        return 0, None


# One probe per priced provider, so this has to be at least the number of priced peers. It
# was 4 while six peers advertised prices, which left two paywalls untested on every run —
# and an untested paywall is indistinguishable from a broken one. The denominator check in
# evaluate() makes any future overflow a visible finding instead of a shorter list.
MAX_PROBES = 12


def priced_providers(prices: Any) -> set:
    """Every source_hub that advertises at least one priced capability.

    The canary's job is to prove the paywall holds for all of them, so this is the
    denominator the probe list is checked against.
    """
    providers = set()
    for row in (prices or {}).get("prices") or []:
        try:
            price = float(row.get("price_usd") or 0)
        except (TypeError, ValueError):
            continue
        if price > 0 and row.get("capability_id") and row.get("product_id"):
            providers.add(str(row.get("source_hub") or "local"))
    return providers


def pick_priced_capabilities(prices: Any, limit: int = MAX_PROBES) -> list[dict[str, Any]]:
    """The cheapest priced capability from each provider, cheapest providers first.

    Per provider, because enforcement is not one switch. `AIMARKET_SELLS_FOR` decides it
    per peer, and the local branch has a gate of its own: probing a single capability
    proved only that one peer was still gated while another was being served free. Cheapest
    within a provider, because whatever this picks gets executed for free on every run for
    as long as the regression lasts.
    """
    rows = (prices or {}).get("prices") or []
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    for row in rows:
        cap, product = row.get("capability_id"), row.get("product_id")
        if not cap or not product:
            continue
        try:
            price = float(row.get("price_usd") or 0)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        hub = str(row.get("source_hub") or "local")
        if hub not in best or price < best[hub][0]:
            best[hub] = (price, {"capability_id": cap, "product_id": product,
                                 "source_hub": hub, "price_usd": price})
    ordered = [item for _, item in sorted(best.values(), key=lambda p: p[0])]
    # Deliberately NOT truncated to `limit` silently. With MAX_PROBES=4 and six priced peers,
    # two providers went unprobed on every run — which is exactly the shape of the ATLAS
    # regression this script exists to catch (priced, listed, and served free for a month).
    # The caller compares this list against priced_providers() and fails on any gap, so a
    # ceiling that ever needs to bite becomes a visible finding rather than a shorter list.
    if limit and len(ordered) > limit:
        return ordered[:limit]
    return ordered


def pick_priced_capability(search_result: Any) -> dict[str, Any] | None:
    """Cheapest priced match in a /search response — the fallback when /prices is absent."""
    matches = (search_result or {}).get("matches") or []
    priced = []
    for m in matches:
        try:
            price = float(m.get("price_per_call_usd") or 0)
        except (TypeError, ValueError):
            continue
        if price > 0 and m.get("capability_id") and m.get("product_id"):
            priced.append((price, m))
    if not priced:
        return None
    return min(priced, key=lambda p: p[0])[1]


LIVENESS_TIMEOUT = 12.0

# Hosts that mean "me", wherever the reader happens to be standing. A manifest that
# advertises one of these has published an address no other machine can route to.
_UNROUTABLE_HOSTS = ("localhost", "127.", "0.0.0.0", "[::1]", "::1",
                     "10.", "192.168.", "172.16.", "172.17.", "172.18.", "169.254.")


def _is_unroutable(endpoint: str) -> bool:
    if not endpoint:
        return False
    host = endpoint.split("//", 1)[-1].split("/", 1)[0].split("@")[-1].lower()
    return any(host.startswith(bad) for bad in _UNROUTABLE_HOSTS)


def probe_peer(peer: dict[str, Any], timeout: float = LIVENESS_TIMEOUT,
               attempts: int = 2) -> dict[str, Any]:
    """Is this satellite actually able to serve an invoke?

    Deliberately NOT a manifest check. On 2026-08-16 GAIA served
    ``/.well-known/ai-market.json`` with a clean 200 while its invoke endpoint hung, so every
    one of its capabilities answered 502 through the hub — and a manifest-only check would
    have reported the satellite healthy throughout.

    The probe asks the invoke endpoint for a capability that cannot exist. A live service
    rejects it immediately; what is being measured is that it answered at all, so any HTTP
    status counts as alive. Nothing is executed and nothing is charged.

    Retried once, because a satellite that blinks for one second should not page anyone.
    """
    url = (peer.get("url") or "").rstrip("/")
    well_known = peer.get("well_known_url") or f"{url}/.well-known/ai-market.json"
    out: dict[str, Any] = {"url": url, "sells": bool(peer.get("sells")),
                           "manifest_ok": False, "alive": False, "status": None,
                           "error": None, "advertised_endpoint": None,
                           "endpoint_routable": True}

    status, manifest = _get(well_known, timeout)
    out["manifest_ok"] = status == 200 and isinstance(manifest, dict)
    if isinstance(manifest, dict):
        advertised = str(manifest.get("mcp_endpoint") or "")
        out["advertised_endpoint"] = advertised or None
        out["endpoint_routable"] = not _is_unroutable(advertised)

    # The peer's own v2 invoke path, NOT the mcp_endpoint it advertises. Probing the
    # advertised value reported three healthy peers as dead: magic-ai-factory.com publishes
    # `http://localhost:9080/ai-market/mcp` to the world, so the probe dialled its own
    # machine. Every real peer answers the standard path in well under a second.
    invoke_url = f"{url}/ai-market/v2/invoke"
    body = {"product_id": "canary-liveness", "capability_id": "canary.liveness.probe@v0",
            "input": {}}
    for _ in range(attempts):
        status, _body = _post(invoke_url, body, timeout)
        if status:
            out["alive"] = True
            out["status"] = status
            out["error"] = None
            return out
        out["error"] = "no response within %.0fs" % timeout
    return out


def observe(hub: str, timeout: float,
            capabilities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    _, manifest = _get(f"{hub}/.well-known/ai-market.json", timeout)
    _, mcp_info = _get(f"{hub}/mcp", timeout)

    expected_providers: set = set()
    if capabilities is None:
        _, prices = _get(f"{hub}/ai-market/v2/prices", timeout)
        # The denominator, captured before any truncation: every provider that advertises a
        # price. evaluate() fails the run if one of them ends up unprobed.
        expected_providers = priced_providers(prices)
        capabilities = pick_priced_capabilities(prices)
        if not capabilities:
            _, search = _get(f"{hub}/ai-market/v2/search?intent=oracle&limit=25", timeout)
            one = pick_priced_capability(search)
            capabilities = [one] if one else []

    probes = []
    for capability in capabilities:
        body = {
            "product_id": capability["product_id"],
            "capability_id": capability["capability_id"],
            "input": {},
        }
        source_hub = capability.get("source_hub")
        if source_hub and source_hub != "local":
            body["source_hub"] = source_hub
        # No X-Payment-Channel and deliberately no X-AIMarket-Sandbox-Visitor: the trial
        # tier would answer 200 legitimately, and this probe is about the paywall behind it.
        status, resp_body = _post(f"{hub}/ai-market/v2/invoke", body, timeout)
        probes.append({"status": status,
                       "body": resp_body if isinstance(resp_body, dict) else {},
                       "capability_id": capability["capability_id"],
                       "source_hub": source_hub or "local",
                       "price_usd": capability.get("price_usd")})

    # Peer liveness. The 402 probes above cannot see a dead satellite: the payment gate
    # answers before the hub ever contacts the provider, so an unpaid probe returns a
    # healthy-looking 402 whether the peer is up or in the ground.
    selling = {str(c.get("source_hub") or "").rstrip("/") for c in capabilities}
    _, peer_doc = _get(f"{hub}/ai-market/v2/federation/peers", timeout)
    raw_peers = peer_doc if isinstance(peer_doc, list) else ((peer_doc or {}).get("peers") or [])
    peers = []
    for entry in raw_peers:
        if not isinstance(entry, dict) or not entry.get("url"):
            continue
        entry = dict(entry, sells=str(entry["url"]).rstrip("/") in selling)
        peers.append(probe_peer(entry))

    if isinstance(manifest, dict) and expected_providers:
        # Carried on the manifest dict the evaluator already receives, so no signature changes
        # and an older caller simply skips the check rather than crashing.
        manifest = dict(manifest, _priced_providers=sorted(expected_providers))
    return {"manifest": manifest if isinstance(manifest, dict) else None,
            "mcp_info": mcp_info if isinstance(mcp_info, dict) else None,
            "probes": probes,
            "peers": peers}


def render(checks: list[Check], hub: str, when: str) -> str:
    lines = [f"payment canary — {hub} — {when}", ""]
    for c in checks:
        mark = "PASS" if c.ok else ("FAIL" if c.critical else "warn")
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    failed = [c for c in checks if not c.ok and c.critical]
    lines.append("")
    lines.append("VERDICT: ok" if not failed
                 else f"VERDICT: {len(failed)} critical check(s) failed")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hub", default=DEFAULT_HUB)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--publish", metavar="PATH",
                        help="also write the JSON report here (for a public status page)")
    parser.add_argument("--timestamp", default=os.environ.get("CANARY_TIMESTAMP", ""),
                        help="stamp to record; defaults to UTC now")
    args = parser.parse_args(argv)

    when = args.timestamp or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    seen = observe(args.hub, args.timeout)
    checks = evaluate(seen["manifest"], seen.get("probes"), seen["mcp_info"], seen.get("peers"))
    failed = [c for c in checks if not c.ok and c.critical]

    report = {
        "hub": args.hub,
        "checked_at": when,
        "ok": not failed,
        "checks": [c.as_dict() for c in checks],
        # Per-peer state, separate from the prose checks, so something other than a human
        # can act on it: a dead satellite names exactly one host to restart, which is the
        # shape a node agent's allowlisted command already takes.
        "peers": seen.get("peers") or [],
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(checks, args.hub, when))

    if args.publish:
        # A publish failure must not read like a payment regression: cron sees only the exit
        # code, and exiting 1 for a missing directory would be indistinguishable from the
        # hub giving paid work away.
        try:
            tmp = f"{args.publish}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2)
            os.replace(tmp, args.publish)  # atomic: a reader never sees a half-written status
        except OSError as exc:
            print(f"WARNING: could not publish the status report to {args.publish}: {exc}",
                  file=sys.stderr)
            return 1 if failed else 2

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
