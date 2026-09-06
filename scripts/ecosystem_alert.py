#!/usr/bin/env python3
"""Wake a human when the ecosystem stops earning, and stay quiet otherwise.

`payment_canary.py` already knows how to tell whether the hub still charges. What it
cannot do is get anyone's attention: it writes JSON to a status page and a line to a log,
so the two silent payment regressions it was built for would today be caught by it and
still go unnoticed until someone opened a browser. This is the part that pushes.

Three design choices, all of them about not being ignored:

* **It runs on the OTHER host.** The canary runs on the hub's own machine, which means it
  is blind to exactly the failure that matters most — that machine being gone. This runs
  on the second host, reaches the hub the way a customer does, and checks the local escrow
  signer over loopback while it is there.

* **It alerts on state CHANGE, not on state.** Two consecutive failures before the first
  message (a deploy restarts things; one bad poll is not an incident), one message when it
  breaks, one when it recovers, nothing in between. An alerter that repeats itself every
  ten minutes gets muted, and a muted alerter is worse than none because it looks alive.

* **It sends a heartbeat.** Once a day when everything is fine. Without it, silence means
  either "healthy" or "the alerter died", and those must not look the same.

    scripts/ecosystem_alert.py --dry-run          # print what would be sent, send nothing
    scripts/ecosystem_alert.py                    # quick probes (no invoke traffic)
    scripts/ecosystem_alert.py --mode full        # + the paywall probes from the canary
    scripts/ecosystem_alert.py --send-test        # one message, to prove the wiring

Environment (values never come from argv — argv is world-readable in `ps`):

    AICOM_ALERT_TELEGRAM_TOKEN   bot token; falls back to TELEGRAM_BOT_TOKEN
    AICOM_ALERT_TELEGRAM_CHAT    chat id;   falls back to TELEGRAM_CHAT_ID
    AICOM_ALERT_STATE            state file (default /var/lib/aicom-alert/state.json)
    AICOM_ALERT_SIGNER_URL       escrow signer base URL (default http://127.0.0.1:9500)
    AICOM_ALERT_HUB_URL          hub base URL (default https://modelmarket.dev)
    AICOM_ALERT_SELLER_URLS      comma-separated seller base URLs whose credit rail
                                 is watched, e.g. https://independentai.network/aegis
    AICOM_ALERT_STATUS_URL       the canary's published status.json
    AICOM_ALERT_SETTLEMENT_URL   the settlement sweep's published settlement.json
    AICOM_ALERT_HEARTBEAT_HOURS  digest interval when all is well (default 24)
    AICOM_ALERT_FLAP             consecutive failures before paging (default 2)

Stdlib only: this has to run from a bare systemd timer on a host with no venv, and an
alerter that depends on a package index is an alerter that stops working during an outage.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "aicom-ecosystem-alert/1.0 (+https://modelmarket.dev)"

DEFAULT_STATE = "/var/lib/aicom-alert/state.json"
DEFAULT_SIGNER = "http://127.0.0.1:9500"
DEFAULT_HUB = "https://modelmarket.dev"
DEFAULT_STATUS = "https://verify.modelmarket.dev/status.json"
DEFAULT_SETTLEMENT = "https://verify.modelmarket.dev/settlement.json"

# How stale the canary's published status may get before that itself is the incident.
# The cron runs daily, so 36h means one missed run is tolerated and two are not.
STATUS_STALE_HOURS = 36.0

# The sweep runs every 15 minutes. Two hours means eight consecutive misses before anyone
# is woken — long enough to survive a deploy, short enough that a dead collector is caught
# inside the 24h a payment channel lives.
SETTLEMENT_STALE_HOURS = 2.0

TELEGRAM_TIMEOUT = 15.0


# ── probes ───────────────────────────────────────────────────────────────────────────────

class Check:
    """One assertion, its evidence, and whether it is worth waking someone for."""

    def __init__(self, name: str, ok: bool, detail: str, critical: bool = True):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.critical = critical

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail,
                "critical": self.critical}


def _get(url: str, timeout: float, headers: dict[str, str] | None = None
         ) -> tuple[int, Any, str]:
    """(status, parsed-or-None, error). Never raises: a probe that crashes is a probe
    that reports nothing, and reporting nothing is the failure mode this file exists to
    remove."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json",
                                               **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(1_000_000).decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw), ""
            except ValueError:
                return resp.status, None, ""
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except Exception as exc:  # socket, DNS, TLS, timeout
        return 0, None, f"{type(exc).__name__}: {exc}"[:200]


def _hours_since_iso(ts: str, now: float) -> float | None:
    """Age of an ISO-8601 Z timestamp in hours, or None if it cannot be read.

    `time.strptime` rather than `datetime.fromisoformat`, because the canary writes a
    trailing Z and Python 3.9 (the interpreter on one of these hosts) rejects it.
    """
    try:
        parsed = time.strptime(ts.strip().replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    except (ValueError, TypeError):
        try:
            parsed = time.strptime(ts.strip()[:19], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            return None
        return (now - time.mktime(parsed) + time.timezone) / 3600.0
    return (now - time.mktime(parsed) + time.timezone) / 3600.0


def probe_signer(base: str, timeout: float = 8.0) -> list[Check]:
    """The signer is the only thing here holding a key that can move money."""
    status, body, err = _get(f"{base.rstrip('/')}/status", timeout)
    if status != 200 or not isinstance(body, dict):
        return [Check("signer_reachable", False,
                      f"{base}/status -> {err or status}")]
    checks = [Check("signer_reachable", True, f"{base}/status -> 200")]
    checks.append(Check("signer_ready", bool(body.get("ready")),
                        f"ready={body.get('ready')}"))
    halted = str(body.get("ledger", {}).get("halted") or "")
    checks.append(Check("signer_not_halted", halted == "",
                        "not halted" if halted == "" else f"HALTED: {halted}"))
    return checks


def _tls_failure(host: str, ip: str, timeout: float) -> str:
    """"" if this address serves a valid certificate for `host`, else why it does not."""
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as raw:
            raw.settimeout(timeout)
            raw.connect((ip, 443))
            with ssl.create_default_context().wrap_socket(
                    raw, server_hostname=host) as tls:
                tls.getpeercert()
        return ""
    except ssl.SSLCertVerificationError as exc:
        # "Hostname mismatch" and "certificate has expired" call for completely different
        # responses — one is a DNS record that should not exist, the other is our own
        # renewal failing — so the reason has to survive into the message.
        reason = str(getattr(exc, "verify_message", "") or exc.reason
                     or "certificate not valid").strip()
    except Exception as exc:
        return type(exc).__name__

    # Whose host is it? The certificate's subject is not readable from the stdlib once
    # verification is off, but an unverified host will happily say who it thinks it is:
    # ask it over plain HTTP with our Host header and read the redirect it answers with.
    hint = ""
    try:
        conn = http.client.HTTPConnection(ip, 80, timeout=min(timeout, 6.0))
        conn.request("GET", "/", headers={"Host": host, "User-Agent": USER_AGENT})
        resp = conn.getresponse()
        location = resp.getheader("Location") or ""
        conn.close()
        if location:
            hint = f", answers http with a redirect to {location[:80]}"
    except Exception:
        pass
    return f"{reason}{hint}"


def probe_dns(hub: str, timeout: float = 8.0) -> list[Check]:
    """Every address the domain resolves to must serve OUR certificate.

    Found live on 2026-08-25: modelmarket.dev had two A records, and one of them belonged
    to a host that presents a certificate for someone else's domain and redirects
    http://modelmarket.dev/ to it. Half of all requests from a client that does not retry
    across addresses failed TLS — measured 10 of 20 from the second host — while every
    single-request health check kept passing, because whichever address answered first was
    usually the right one. A monitor that probes "the hub" through one connection cannot
    see this: it has to look at each address separately.
    """
    host = hub.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        return [Check("hub_dns_resolves", False, f"{host}: {type(exc).__name__}: {exc}"[:180])]
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        return [Check("hub_dns_resolves", False, f"{host} resolves to nothing")]

    bad = [f"{ip} ({reason})" for ip, reason in
           ((ip, _tls_failure(host, ip, timeout)) for ip in addresses) if reason]

    detail = f"{len(addresses)} address(es): " + ", ".join(addresses)
    if bad:
        detail = (f"{len(bad)}/{len(addresses)} address(es) do NOT serve a valid "
                  f"{host} certificate: " + "; ".join(bad))
    return [Check("hub_dns_all_addresses_valid", not bad, detail)]


def probe_hub(hub: str, timeout: float = 20.0) -> list[Check]:
    """What a customer sees: the catalogue, and whether it still says it takes money."""
    base = hub.rstrip("/")
    status, body, err = _get(f"{base}/ai-market/v2/manifest", timeout)
    if status != 200 or not isinstance(body, dict):
        return [Check("hub_manifest", False, f"{base}/ai-market/v2/manifest -> {err or status}")]
    caps = body.get("total_capabilities")
    checks = [Check("hub_manifest", True, f"manifest served, {caps} capabilities")]
    # A catalogue that empties itself is the shape federation failures take: every peer
    # unreachable looks exactly like a hub with nothing to sell.
    checks.append(Check("hub_catalogue_not_empty", bool(caps),
                        f"total_capabilities={caps}"))

    status, body, err = _get(f"{base}/ai-market/v2/stats/live?limit=1", timeout)
    ok = status == 200 and isinstance(body, dict)
    checks.append(Check("hub_stats_live", ok,
                        "stats/live answered" if ok else f"stats/live -> {err or status}",
                        critical=False))
    return checks


def _federation_label(hub: str) -> str:
    """Stable, readable suffix identifying which hub a federation check is about."""
    netloc = urllib.parse.urlsplit(hub if "://" in hub else f"https://{hub}").netloc
    return (netloc or hub.strip()).strip("/")


def _split_hub_entry(entry: str) -> tuple[str, str]:
    """``label=url`` -> (label, url); a bare url -> (host, url).

    An alias is how a hub is named on a page. The Independent AI Hub is a deliberately
    independent node of an open federation, and reading "@independent" on an alert says
    that; reading a bare hostname does not. Naming, not filtering — it is watched exactly
    like every other hub.
    """
    text = (entry or "").strip()
    label, sep, url = text.partition("=")
    label, url = label.strip(), url.strip()
    if not sep or "//" in label or not url:
        return _federation_label(text), text
    if "://" not in url:
        url = f"https://{url}"
    return label, url.rstrip("/")


def probe_federation(hub: str, timeout: float = 20.0, now: float | None = None,
                     stale_hours: float | None = None, label: str = "") -> list[Check]:
    """Is every peer still being indexed, or has one quietly frozen?

    ``probe_hub`` catches a catalogue that empties itself. It cannot catch the
    partial version, which is the one that actually happened: ATLAS rotated its
    signing key, the Hub rejected the new one fail-closed as a possible takeover,
    and kept serving its last-indexed ATLAS catalogue — six of seven capabilities,
    the $0.12 SKU simply absent. Nothing went red. Two Hubs stayed that way for
    five days, and the only symptom anywhere was a bar on an analytics dashboard.

    Both signals come off the public peers endpoint, so this works from a host that
    holds no admin token.

    ``label`` suffixes the check names so several hubs can be watched at once. Every
    hub keeps its own peer index, and one hub's index being healthy says nothing about
    another's: Signal Hunt sat with two peers un-recrawled for 21 days while the apex
    hub was fine. The primary hub passes no label, so its check names — and the state
    history keyed on them — stay exactly as they were.
    """
    now = time.time() if now is None else now
    if stale_hours is None:
        stale_hours = float(os.environ.get("AICOM_ALERT_PEER_STALE_HOURS", "26") or 26)
    base = hub.rstrip("/")
    tag = f"@{label}" if label else ""
    status, body, err = _get(f"{base}/ai-market/v2/federation/peers", timeout)
    if status != 200 or not isinstance(body, dict):
        return [Check(f"hub_federation_peers{tag}", False,
                      f"{base}/ai-market/v2/federation/peers -> {err or status}")]
    peers = body.get("peers")
    if not isinstance(peers, list):
        return [Check(f"hub_federation_peers{tag}", False,
                      "peers endpoint returned no peer list")]

    checks = [Check(f"hub_federation_peers{tag}", True, f"{len(peers)} peer(s) listed")]

    rejected = [
        str(p.get("name") or p.get("url") or "?")
        for p in peers
        if isinstance(p, dict) and str(p.get("status") or "") == "key_mismatch"
    ]
    # Name them: the reason field is not always populated, and an operator who has to
    # go find out which peer is rejected loses the head start this check exists to give.
    checks.append(Check(
        f"hub_federation_pins_accepted{tag}", not rejected,
        "no rejected key pins" if not rejected
        else f"key pin rejected for: {', '.join(sorted(rejected))} "
             f"(re-pin after a legitimate rotation, POST /federation/peers/repin)",
    ))

    stalest_name, stalest_hours = "", None
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        age = _hours_since_iso(str(peer.get("last_crawl") or ""), now)
        if age is None:
            continue
        if stalest_hours is None or age > stalest_hours:
            stalest_hours, stalest_name = age, str(peer.get("name") or peer.get("url") or "?")
    if stalest_hours is None:
        # No parseable crawl stamp anywhere is itself a finding, not a pass: it is what a
        # crawler that has never run looks like.
        checks.append(Check(f"hub_federation_crawl_fresh{tag}", False,
                            "no peer reports a parseable last_crawl"))
    else:
        checks.append(Check(
            f"hub_federation_crawl_fresh{tag}", stalest_hours <= stale_hours,
            f"stalest peer crawl: {stalest_name} {stalest_hours:.1f}h ago "
            f"(threshold {stale_hours:.0f}h)",
        ))
    return checks


def discover_federation_hubs(hub: str, timeout: float = 20.0) -> list[str]:
    """Every hub in this federation that keeps a peer index of its own.

    Derived from the federation, not from a list somebody maintains. A hand-kept list
    has the failure mode it is meant to fix: two hubs kept their own indexes, both went
    21 days without re-crawling a peer, and the only reason nobody knew is that nobody
    had listed them. An earlier version of this file tried to patch that with a check
    that the list was complete, plus an "ignore" list for hubs someone had decided were
    not ours to watch. Both were wrong. The federation is open — hubs join it without
    asking, exactly as intended — so "ours" is not a property this alerter can read, and
    the one hub that got classified as somebody else's turned out to be ours and to have
    a real rejected key pin at that moment. Nothing is classified now, and nothing is
    silenced: a frozen index degrades the catalogue every hub in the federation serves,
    whoever runs the box.

    Costs one request per peer, so this runs in ``full`` mode. A satellite publishes no
    peer list and so never appears.
    """
    status, body, err = _get(f"{hub.rstrip('/')}/ai-market/v2/federation/peers", timeout)
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("peers"), list):
        return []
    found: list[str] = []
    for peer in body["peers"]:
        if not isinstance(peer, dict):
            continue
        url = str(peer.get("url") or "").strip().rstrip("/")
        if not url:
            continue
        pstatus, pbody, _ = _get(f"{url}/ai-market/v2/federation/peers", min(timeout, 10.0))
        if pstatus != 200 or not isinstance(pbody, dict):
            continue
        peers = pbody.get("peers")
        if isinstance(peers, list) and peers:
            found.append(url)
    return found


def probe_status_page(url: str, timeout: float = 20.0, now: float | None = None
                      ) -> list[Check]:
    """Is the daily canary still running at all? Its own silence is invisible otherwise."""
    now = time.time() if now is None else now
    status, body, err = _get(url, timeout)
    if status != 200 or not isinstance(body, dict):
        return [Check("canary_status_published", False, f"{url} -> {err or status}")]
    age = _hours_since_iso(str(body.get("checked_at", "")), now)
    if age is None:
        return [Check("canary_status_published", False,
                      f"unreadable checked_at: {body.get('checked_at')!r}")]
    fresh = age <= STATUS_STALE_HOURS
    checks = [Check("canary_status_fresh", fresh,
                    f"published {age:.1f}h ago" if fresh
                    else f"STALE: published {age:.1f}h ago (cron dead?)")]
    failed = [c.get("name") for c in body.get("checks", [])
              if not c.get("ok") and c.get("critical")]
    checks.append(Check("canary_verdict_ok", not failed,
                        "all canary checks green" if not failed
                        else "canary failing: " + ", ".join(str(f) for f in failed[:6])))
    return checks


def probe_settlement(url: str, timeout: float = 20.0, now: float | None = None
                     ) -> list[Check]:
    """Is the collector still collecting?

    Submission used to be a human habit: a buyer's signed authorization sat in the hub
    until somebody ran the CLI. `escrow_settlement_sweep.py` now does it on a timer and
    publishes the result next to the canary's status. Automating a manual step without
    watching it just moves the silence — so the sweep going quiet, or leaving money
    unsubmitted, is a paging condition in its own right.
    """
    now = time.time() if now is None else now
    status, body, err = _get(url, timeout)
    if status != 200 or not isinstance(body, dict):
        # Not critical: the report is young, and a hub that has never swept yet must not
        # page anyone at 3am. The staleness check below is the one that matters.
        return [Check("settlement_report_published", False,
                      f"{url} -> {err or status}", critical=False)]
    age = _hours_since_iso(str(body.get("checked_at", "")), now)
    if age is None:
        return [Check("settlement_report_published", False,
                      f"unreadable checked_at: {body.get('checked_at')!r}", critical=False)]
    fresh = age <= SETTLEMENT_STALE_HOURS
    checks = [Check("settlement_sweep_fresh", fresh,
                    f"swept {age:.1f}h ago" if fresh
                    else f"STALE: last sweep {age:.1f}h ago (timer dead?)")]
    # Money already debited on chain that no transaction has swept out of escrow yet.
    # Nothing can lose it — `expireChannel` is permissionless and pays the hub the same
    # amount — so this is a nudge, not an incident, and it must never page at 3am.
    unc = body.get("uncollected") or {}
    expired_usd = float(unc.get("expired_usd") or 0)
    if expired_usd > 0:
        checks.append(Check("settlement_nothing_expired_uncollected", False,
                            f"${expired_usd:.6f} sits in expired channels "
                            f"({unc.get('expired_uncollected')} of them) — anyone can "
                            f"call expireChannel to collect it",
                            critical=False))
    pending = float(body.get("pending_usd_after") or 0)
    checks.append(Check("settlement_nothing_stuck", bool(body.get("ok")) and pending == 0,
                        "queue empty" if pending == 0 and body.get("ok")
                        else f"${pending:.6f} still unsubmitted"
                             + (f"; errors: {'; '.join(body.get('errors') or [])[:120]}"
                                if body.get("errors") else "")))
    return checks


def _seller_label(url: str) -> str:
    """Host AND path: two sellers can share one domain under different prefixes
    (independentai.network/aegis and /kova do), and a label that dropped the path
    would collapse their checks into one name in the state file."""
    split = urllib.parse.urlsplit(url if "://" in url else f"https://{url}")
    return ((split.netloc or url.strip()) + split.path.rstrip("/")).strip("/")


def probe_credit_rail(sellers: list[str], timeout: float = 10.0) -> list[Check]:
    """Can a seller still turn a paid top-up into Hub credit?

    A seller reaches the Hub ledger with the operator's admin token, and the Hub
    enforces that on exactly one call — the one that runs after a buyer has paid.
    Everything else a seller does (publishing capabilities, opening accounts)
    works with a lesser credential, so a wrong or rotated token is healthy right
    up to the first payment, and the first payment is where it must not be found.
    So each seller re-verifies the admin leg on its own beat and publishes the
    verdict; this reads it and needs no secret to do so.
    """
    checks: list[Check] = []
    for entry in sellers:
        base = entry.strip().rstrip("/")
        if not base:
            continue
        label = _seller_label(base)
        status, body, err = _get(f"{base}/health", timeout)
        if err or status != 200 or not isinstance(body, dict):
            checks.append(Check(f"credit_rail_reachable[{label}]", False,
                                f"{base}/health -> {err or status}"))
            continue
        rail = body.get("credit_rail")
        if not isinstance(rail, dict):
            # An older build that does not publish the verdict is not a pass. It
            # is a seller whose money path nobody can see.
            checks.append(Check(f"credit_rail_published[{label}]", False,
                                f"{base} serves no credit_rail verdict"))
            continue
        if not rail.get("enabled"):
            # Selling is switched off here on purpose; nothing to page about.
            checks.append(Check(f"credit_rail_enabled[{label}]", True,
                                "top-up desk is off on this seller", critical=False))
            continue
        state = str(rail.get("hub_credit_admin") or "unknown")
        detail = str(rail.get("detail") or "")[:160]
        checks.append(Check(f"credit_rail_can_credit[{label}]", state == "ok",
                            f"{state}: {detail}" if detail else state,
                            critical=state == "denied"))
        checks.append(Check(f"credit_rail_verdict_fresh[{label}]",
                            _hours_since_iso(str(rail.get("checked_at") or ""), time.time())
                            is not None,
                            f"checked_at={rail.get('checked_at')}", critical=False))
    return checks


def probe_paywall(hub: str, timeout: float) -> list[Check]:
    """The expensive probes: real unpaid invokes that must be refused.

    Delegated to payment_canary.py, which is deployed next to this file — the paywall
    logic must not exist in two places that can disagree. Absent canary, absent checks:
    a missing dependency is reported as one failed check, not as silence.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import payment_canary  # type: ignore
    except Exception as exc:
        return [Check("paywall_probe_available", False,
                      f"payment_canary.py not importable: {type(exc).__name__}")]
    try:
        seen = payment_canary.observe(hub.rstrip("/"), timeout)
        canary_checks = payment_canary.evaluate(
            seen.get("manifest"), seen.get("probes"), seen.get("mcp_info"),
            seen.get("peers"),
        )
    except Exception as exc:
        return [Check("paywall_probe_ran", False,
                      f"canary raised {type(exc).__name__}: {exc}"[:180])]
    out = []
    for c in canary_checks:
        d = c.as_dict() if hasattr(c, "as_dict") else dict(c)
        out.append(Check(str(d.get("name")), bool(d.get("ok")), str(d.get("detail", ""))[:200],
                         bool(d.get("critical", True))))
    return out


# ── state: the difference between an alerter and a spammer ────────────────────────────────

def load_state(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError):
        return {"checks": {}, "last_heartbeat": "", "last_alert": ""}
    state.setdefault("checks", {})
    state.setdefault("last_heartbeat", "")
    state.setdefault("last_alert", "")
    return state


def save_state(path: str, state: dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        # A state file we cannot write means every run looks like the first one, which
        # means an alert every ten minutes. Say so on stderr; the caller decides.
        print(f"warning: cannot persist state to {path}: {exc}", file=sys.stderr)


def decide(checks: list[Check], state: dict[str, Any], *, flap: int,
           heartbeat_hours: float, now: float) -> tuple[list[str], list[str], bool]:
    """Pure: (newly broken, newly recovered, heartbeat due). Mutates `state` in place.

    `flap` consecutive failures are required before a check is considered broken, so a
    restart mid-poll does not page anyone. Recovery is immediate — being told too early
    that something came back costs nothing, being told too early that it broke costs
    trust in every later message.
    """
    broke: list[str] = []
    fixed: list[str] = []
    seen = set()

    for check in checks:
        seen.add(check.name)
        row = state["checks"].setdefault(check.name, {"failures": 0, "alerted": False})
        if check.ok:
            if row.get("alerted"):
                fixed.append(check.name)
            row["failures"] = 0
            row["alerted"] = False
        else:
            row["failures"] = int(row.get("failures", 0)) + 1
            if not row.get("alerted") and row["failures"] >= flap and check.critical:
                row["alerted"] = True
                broke.append(check.name)
    # A check that stopped being produced (mode changed, probe removed) must not stay
    # "alerted" forever, or its recovery can never be reported.
    for name in list(state["checks"]):
        if name not in seen:
            state["checks"].pop(name, None)

    if broke or fixed:
        state["last_alert"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    age = _hours_since_iso(state.get("last_heartbeat") or "", now)
    quiet = not broke and not fixed and all(c.ok for c in checks if c.critical)
    due = quiet and (age is None or age >= heartbeat_hours)
    if due:
        state["last_heartbeat"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    return broke, fixed, due


# ── message ──────────────────────────────────────────────────────────────────────────────

def format_message(checks: list[Check], broke: list[str], fixed: list[str],
                   heartbeat: bool, *, host: str, hub: str, when: str) -> str:
    """One screen on a phone: what broke, what the evidence was, what to run next."""
    by_name = {c.name: c for c in checks}
    down = [c for c in checks if not c.ok and c.critical]
    warnings = [c for c in checks if not c.ok and not c.critical]
    lines: list[str] = []

    if broke:
        lines.append(f"\U0001F534 AIMarket: {len(broke)} check(s) FAILING")
    elif fixed:
        lines.append(f"\U0001F7E2 AIMarket: recovered ({len(fixed)})")
    elif down:
        # Below the flap threshold, so nobody is being paged yet — but a headline claiming
        # everything is green while a critical check is red is the one thing a monitor may
        # never print. This branch exists because it did print it once.
        lines.append(f"\U0001F7E0 AIMarket: {len(down)} critical check(s) failing "
                     f"(below alert threshold, not paged)")
    else:
        lines.append("\U0001F7E2 AIMarket: all critical checks green"
                     + (f" ({len(warnings)} warning(s))" if warnings else ""))

    lines.append(f"{hub} · watched from {host} · {when}")
    lines.append("")

    for name in broke:
        c = by_name.get(name)
        lines.append(f"✖ {name}")
        if c and c.detail:
            lines.append(f"   {c.detail[:200]}")
    for name in fixed:
        lines.append(f"✔ {name} — back to normal")

    if heartbeat or (not broke and not fixed):
        ok = sum(1 for c in checks if c.ok)
        lines.append(f"{ok}/{len(checks)} checks ok")
        # A critical failure that has not yet crossed the flap threshold still belongs in
        # the body — the reader must be able to see what the headline is counting.
        for c in down[:4]:
            lines.append(f"✖ {c.name}: {c.detail[:160]}")
        for c in warnings[:4]:
            lines.append(f"⚠ {c.name}: {c.detail[:120]}")

    if broke:
        lines.append("")
        lines.append("next: scripts/ecosystem_alert.py --mode full --dry-run")
        lines.append("      curl -s https://verify.modelmarket.dev/status.json | head")
    return "\n".join(lines)


# ── delivery ─────────────────────────────────────────────────────────────────────────────

def send_telegram(token: str, chat_id: str, text: str, *, timeout: float = TELEGRAM_TIMEOUT
                  ) -> tuple[bool, str]:
    """Plain text on purpose: Markdown/HTML parse modes reject messages containing the
    very characters a failure detail is full of, and a dropped alert is unacceptable."""
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text[:4000],
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    last = ""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read(100_000).decode("utf-8", "replace"))
                if body.get("ok"):
                    return True, str(body.get("result", {}).get("message_id", ""))
                last = str(body.get("description", "unknown error"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(2000).decode("utf-8", "replace")
            last = f"HTTP {exc.code}: {detail[:160]}"
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"[:160]
        if attempt == 0:
            time.sleep(2)
    return False, last


# ── orchestration ────────────────────────────────────────────────────────────────────────

def federation_hubs_from_env(primary: str, raw: str | None = None) -> list[str]:
    """Extra hubs whose own peer index should be watched, primary excluded.

    Each hub keeps its own index and re-crawls on its own schedule, so watching the
    apex says nothing about the others. Deduplicated against the primary and against
    each other by label, because two spellings of one host (trailing slash, http vs
    https) would otherwise produce two checks with the same name and the second would
    overwrite the first's state silently.
    """
    if raw is None:
        raw = os.environ.get("AICOM_ALERT_FEDERATION_HUBS", "")
    seen = {_federation_label(primary)}
    out: list[str] = []
    for entry in (raw or "").replace(";", ",").split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        _label, url = _split_hub_entry(candidate)
        if "://" not in url:
            url = f"https://{url}"
        host = _federation_label(url)
        # Deduplicated by HOST, not by label: the same hub under two aliases would
        # otherwise be probed twice under two check names.
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(candidate if "=" in candidate else url.rstrip("/"))
    return out


def sellers_from_env() -> list[str]:
    """Sellers whose money path is watched. Empty by default: a node with no seller
    must not carry a check that fails forever and mutes the alerter."""
    raw = os.environ.get("AICOM_ALERT_SELLER_URLS", "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def collect(mode: str, *, hub: str, signer: str, status_url: str, settlement_url: str,
            timeout: float, federation_hubs: list[str] | None = None,
            sellers: list[str] | None = None) -> list[Check]:
    checks: list[Check] = []
    checks += probe_credit_rail(sellers if sellers is not None else sellers_from_env(),
                                min(timeout, 10.0))
    checks += probe_dns(hub)
    checks += probe_hub(hub, timeout)
    checks += probe_federation(hub, timeout)
    watched = (federation_hubs if federation_hubs is not None
               else federation_hubs_from_env(hub))
    watched_pairs = [_split_hub_entry(entry) for entry in watched]
    for label, url in watched_pairs:
        checks += probe_federation(url, timeout, label=label)
    # The signer answers on loopback only, so an instance running anywhere else must be
    # able to opt out (AICOM_ALERT_SIGNER_URL=""). Otherwise that one check fails forever
    # and the alerter it belongs to gets muted for being wrong, not for being noisy.
    if signer.strip():
        checks += probe_signer(signer, min(timeout, 10.0))
    checks += probe_status_page(status_url, timeout)
    checks += probe_settlement(settlement_url, timeout)
    if mode == "full":
        checks += probe_paywall(hub, timeout)
        # Every hub the federation knows about, on top of the configured ones. Configured
        # entries stay because a hub of ours need not be a peer of this one (the UNI bubble
        # is not), and quick mode has no discovery.
        seen = {_federation_label(hub)} | {_federation_label(u) for _l, u in watched_pairs}
        for found in discover_federation_hubs(hub, timeout):
            label = _federation_label(found)
            if label in seen:
                continue
            seen.add(label)
            checks += probe_federation(found, timeout, label=label)
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--mode", choices=("quick", "full"), default="quick",
                        help="quick: no invoke traffic. full: also probe the paywall.")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the message and the decision, send nothing, "
                             "and leave the state file untouched")
    parser.add_argument("--send-test", action="store_true",
                        help="send one message proving the wiring, then exit")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--state", default=os.environ.get("AICOM_ALERT_STATE", DEFAULT_STATE))
    args = parser.parse_args(argv)

    token = (os.environ.get("AICOM_ALERT_TELEGRAM_TOKEN")
             or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("AICOM_ALERT_TELEGRAM_CHAT")
            or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    hub = os.environ.get("AICOM_ALERT_HUB_URL", DEFAULT_HUB)
    signer = os.environ.get("AICOM_ALERT_SIGNER_URL", DEFAULT_SIGNER)
    status_url = os.environ.get("AICOM_ALERT_STATUS_URL", DEFAULT_STATUS)
    settlement_url = os.environ.get("AICOM_ALERT_SETTLEMENT_URL", DEFAULT_SETTLEMENT)
    heartbeat_hours = float(os.environ.get("AICOM_ALERT_HEARTBEAT_HOURS", "24") or 24)
    flap = max(1, int(os.environ.get("AICOM_ALERT_FLAP", "2") or 2))
    host = socket.gethostname()
    now = time.time()
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now))

    if args.send_test:
        if not token or not chat:
            print("no token/chat configured — set AICOM_ALERT_TELEGRAM_TOKEN and "
                  "AICOM_ALERT_TELEGRAM_CHAT", file=sys.stderr)
            return 2
        ok, info = send_telegram(token, chat,
                                 f"\U0001F7E1 AIMarket alerter wired up on {host}\n{when}\n"
                                 f"watching {hub}\nThis is the only message you should "
                                 f"see until something breaks.")
        print(f"send: {'ok' if ok else 'FAILED'} {info}")
        return 0 if ok else 1

    checks = collect(args.mode, hub=hub, signer=signer, status_url=status_url,
                     settlement_url=settlement_url, timeout=args.timeout,
                     federation_hubs=federation_hubs_from_env(hub))
    state = load_state(args.state)
    heartbeat_before = state.get("last_heartbeat", "")
    broke, fixed, heartbeat = decide(checks, state, flap=flap,
                                     heartbeat_hours=heartbeat_hours, now=now)
    message = format_message(checks, broke, fixed, heartbeat,
                             host=host, hub=hub, when=when)
    should_send = bool(broke or fixed or heartbeat)

    if args.json:
        print(json.dumps({
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "mode": args.mode,
            "checks": [c.as_dict() for c in checks],
            "broke": broke, "fixed": fixed, "heartbeat": heartbeat,
            "would_send": should_send,
        }, indent=1))
    else:
        failing = [c.name for c in checks if not c.ok]
        print(f"{args.mode}: {len(checks) - len(failing)}/{len(checks)} ok"
              + (f" | failing: {', '.join(failing)}" if failing else "")
              + f" | send={should_send}")
        if should_send or args.dry_run:
            print("-" * 60)
            print(message)
            print("-" * 60)

    if args.dry_run:
        return 0

    if should_send:
        if not token or not chat:
            print("would alert, but no Telegram token/chat configured", file=sys.stderr)
            return 2
        ok, info = send_telegram(token, chat, message)
        if not ok:
            # Do NOT persist anything the failed message was supposed to deliver, or the
            # next run will think the human already knows.
            for name in broke:
                state["checks"].get(name, {})["alerted"] = False
            # The heartbeat stamp is set by decide() BEFORE the send. Keeping it after a
            # failure suppresses the digest for a full interval — the alerter would go
            # quiet precisely because it could not reach anyone, which is the one failure
            # the heartbeat exists to make visible.
            if heartbeat:
                state["last_heartbeat"] = heartbeat_before
            print(f"telegram send failed: {info}", file=sys.stderr)
            save_state(args.state, state)
            return 1
        print(f"telegram: sent (message {info})")

    save_state(args.state, state)
    # Exit non-zero while a critical check is down, so `systemctl status` and any
    # future supervisor see it too.
    return 1 if any(not c.ok and c.critical for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
