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

* **It sends a digest once a day, green or not.** Without it, silence means either
  "healthy" or "the alerter died", and those must not look the same. It used to be sent
  only while everything was green, so an incident that stayed open made the alerter go
  quiet for as long as it lasted: one page on day one, then eight days in which silence
  meant "still broken" and "dead" alike. Now the digest names what is still open and for
  how long.

    scripts/ecosystem_alert.py --dry-run          # print what would be sent, send nothing
    scripts/ecosystem_alert.py                    # quick probes (no invoke traffic)
    scripts/ecosystem_alert.py --mode full        # + the paywall probes from the canary
    scripts/ecosystem_alert.py --send-test        # one message, to prove the wiring

It watches the alexar76 ecosystem only (see `Scope`), and every digest says what it
deliberately does not watch.

Environment (values never come from argv — argv is world-readable in `ps`):

    AICOM_ALERT_SCOPE            watched domains, comma-separated, subdomains included
                                 (default modelmarket.dev,magic-ai-factory.com; * = all)
    AICOM_ALERT_LANG             message language: en (default) or ru
    AICOM_ALERT_HOST_LABEL       how the watching host is named on a page (default hostname)
    AICOM_ALERT_TELEGRAM_TOKEN   bot token; falls back to TELEGRAM_BOT_TOKEN
    AICOM_ALERT_TELEGRAM_CHAT    chat id;   falls back to TELEGRAM_CHAT_ID
    AICOM_ALERT_EMAIL_TO         comma-separated recipients; e-mail is off while empty
    AICOM_ALERT_SMTP_HOST        SMTP server; port from AICOM_ALERT_SMTP_PORT (587 =
                                 STARTTLS, 465 = implicit TLS; plaintext is never used)
    AICOM_ALERT_SMTP_USER        login, and the From address unless AICOM_ALERT_EMAIL_FROM
    AICOM_ALERT_SMTP_PASSWORD    password (an app password where the provider has them)
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
import datetime
import email.utils
import http.client
import ipaddress
import json
import os
import re
import smtplib
import socket
import ssl
import sys
import time
from email.message import EmailMessage
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
EMAIL_TIMEOUT = 20.0

# The owner's call, 2026-09-24: the alexar76 ecosystem and nothing else.
DEFAULT_SCOPE = ("modelmarket.dev", "magic-ai-factory.com")

# Admin tokens printed in this repository — as defaults, examples or bubble constants. A hub
# that accepts one has an operator door anybody who read the source can open. UNI ran on the
# first of these from 2026-09-16 to 2026-09-24, after a stale deploy script was re-run.
PUBLISHED_ADMIN_TOKENS = (
    "uni-admin-token-not-a-secret-in-a-bubble",
    "platon-ecosystem-admin",
    "ci-compose-admin-token-not-a-secret",
    "replace-with-at-least-32-random-bytes",
    "replace-with-a-random-64-hex-secret",
)


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


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class Scope:
    """Which part of the federation this alerter answers for.

    The owner's call, 2026-09-24: the alexar76 ecosystem and nothing else — not the
    Independent node (independentai.network), not Attested (attestedmemory.net and
    Emberline), not PingBlip. The federation cannot tell whose a hub is: it is open, hubs
    join without asking. This file once tried to guess with an ignore list and guessed
    wrong (see `discover_federation_hubs`). A scope is not a guess — the owner declares
    it, as a list of domains — and whatever it leaves out is named in every digest instead
    of vanishing without a trace.

    A domain covers its subdomains. ``AICOM_ALERT_SCOPE=*`` watches everything.
    """

    def __init__(self, domains: tuple[str, ...] | None):
        self.domains = domains
        self.excluded: set[str] = set()

    @classmethod
    def from_env(cls) -> "Scope":
        raw = os.environ.get("AICOM_ALERT_SCOPE")
        if raw is None or not raw.strip():
            return cls(DEFAULT_SCOPE)
        if raw.strip() == "*":
            return cls(None)
        return cls(tuple(p.strip().lower().strip(".") for p in raw.split(",") if p.strip()))

    def allows(self, url: str) -> bool:
        """True if `url` (or a bare host) is ours to watch. Records what it turns away."""
        if self.domains is None:
            return True
        text = (url or "").strip()
        if not text or text == "local":
            return True  # the hub's own capabilities
        host = (urllib.parse.urlsplit(text if "://" in text else f"https://{text}")
                .hostname or "").lower()
        if _is_loopback(host) or any(host == d or host.endswith("." + d)
                                     for d in self.domains):
            return True
        self.excluded.add(host or text)
        return False


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


def _post(url: str, payload: dict[str, Any], timeout: float,
          headers: dict[str, str] | None = None) -> tuple[int, Any, str]:
    """`_get`'s twin for a JSON POST; the body of an error answer is kept, because the
    detail is what tells two 503s apart."""
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"User-Agent": USER_AGENT,
                                          "Content-Type": "application/json",
                                          "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200_000).decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(200_000).decode("utf-8", "replace"), exc.code
    except Exception as exc:
        return 0, None, f"{type(exc).__name__}: {exc}"[:200]
    try:
        return status, json.loads(raw), ""
    except ValueError:
        return status, None, ""


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
                     stale_hours: float | None = None, label: str = "",
                     scope: Scope | None = None) -> list[Check]:
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

    With a ``scope``, peers outside it do not count towards the pin and freshness verdicts:
    a hub of ours that stops re-crawling somebody else's node is that node's operator's
    business. They are still counted in the detail, so the number never looks smaller
    than the list.
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

    listed = len(peers)
    peers = [p for p in peers if isinstance(p, dict)
             and (scope is None or scope.allows(str(p.get("url") or "")))]
    outside = listed - len(peers)
    checks = [Check(f"hub_federation_peers{tag}", True,
                    f"{listed} peer(s) listed"
                    + (f", {outside} outside the watched scope" if outside else ""))]

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


def discover_federation_hubs(hub: str, timeout: float = 20.0,
                             scope: Scope | None = None) -> list[str]:
    """Every hub in this federation that keeps a peer index of its own.

    Derived from the federation, not from a list somebody maintains. A hand-kept list
    has the failure mode it is meant to fix: two hubs kept their own indexes, both went
    21 days without re-crawling a peer, and the only reason nobody knew is that nobody
    had listed them. An earlier version of this file tried to patch that with a check
    that the list was complete, plus an "ignore" list for hubs someone had decided were
    not ours to watch. Both were wrong. The federation is open — hubs join it without
    asking, exactly as intended — so "ours" is not a property this alerter can read, and
    the one hub that got classified as somebody else's turned out to be ours and to have
    a real rejected key pin at that moment.

    So the alerter still classifies nothing. The owner does, through `Scope`: a list of
    domains that are this ecosystem, declared rather than inferred. A new hub under one of
    them is watched the hour it appears, with nobody editing a config; one outside them is
    named in the digest as not watched, never dropped silently.

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
        if not url or (scope is not None and not scope.allows(url)):
            continue
        pstatus, pbody, _ = _get(f"{url}/ai-market/v2/federation/peers", min(timeout, 10.0))
        if pstatus != 200 or not isinstance(pbody, dict):
            continue
        peers = pbody.get("peers")
        if isinstance(peers, list) and peers:
            found.append(url)
    return found


def _check_target(name: str) -> str:
    """The URL or host a check is about, if its name carries one (`x[url]`, `x@label`)."""
    match = re.match(r"^[A-Za-z0-9_]+\[(.+)\]$", name)
    if match:
        return match.group(1)
    if name.startswith("tls_expiry:"):
        return name.split(":", 1)[1]
    return name.split("@", 1)[1] if "@" in name else ""


def probe_status_page(url: str, timeout: float = 20.0, now: float | None = None,
                      scope: Scope | None = None) -> list[Check]:
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
    # The canary on the hub's host probes every provider the hub sells, other ecosystems'
    # included; only failures about ours may turn this check red.
    failed = [c.get("name") for c in body.get("checks", [])
              if not c.get("ok") and c.get("critical")
              and (scope is None or not _check_target(str(c.get("name") or ""))
                   or scope.allows(_check_target(str(c.get("name") or ""))))]
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


def _publicly_reachable(url: str) -> bool:
    """https to a name or address that is not the reader's own machine or a private net."""
    split = urllib.parse.urlsplit(url)
    host = (split.hostname or "").lower()
    if split.scheme != "https" or not host or host == "localhost":
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (addr.is_loopback or addr.is_private or addr.is_link_local)


# `_require_admin` answers 503 with this detail when no admin token is set at all: the door
# is shut, not open. Any other 503 comes from after the token was accepted.
_ADMIN_UNSET = "AIMARKET_ADMIN_TOKEN not configured"


def probe_hub_identity(hub: str, timeout: float = 10.0, label: str = "") -> list[Check]:
    """Has a redeploy quietly put back what a fix took out?

    UNI went public on 2026-08-28 with three fixes: its public name instead of loopback, a
    rotated admin token instead of the constant this repository prints, and auto-crawl. On
    2026-09-16 somebody re-ran the host's stale copy of the deploy script, and all three
    were undone — plus the seed list, the seed pins and AIMARKET_SELLS_FOR — for eight days.
    The container was healthy the whole time; only the crawl-freshness check noticed, and
    only the symptom. These two look at the causes, from outside and without a secret:

    * the address the hub hands to the federation, which must be one somebody else can
      reach — ``http://127.0.0.1:9183`` sends every reader to their own machine;
    * whether the operator door opens to a token published in this repository. The probe
      is the one AEGIS uses on itself: a credit to an account that does not exist, with an
      amount that is not a number. The hub checks the token first, so 403 means refused,
      and an accepted token still dies on the amount — nothing is ever written.
    """
    base = hub.rstrip("/")
    tag = f"@{label}" if label else ""
    checks: list[Check] = []

    status, body, err = _get(f"{base}/.well-known/ai-market.json", timeout)
    if status == 200 and isinstance(body, dict):
        bad = [f"{key}={body.get(key)}" for key in ("hub_url", "manifest_url", "mcp_endpoint")
               if body.get(key) and not _publicly_reachable(str(body.get(key)))]
        checks.append(Check(
            f"hub_advertises_public_url{tag}", not bad,
            "advertises public https addresses" if not bad
            else "advertises an address nobody else can reach: " + ", ".join(bad)[:180]))
    else:
        # Reachability is the federation checks' job; here it only means "not measured".
        checks.append(Check(f"hub_advertises_public_url{tag}", True,
                            f"not measured (well-known -> {err or status})", critical=False))

    accepted: list[str] = []
    measured = 0
    for token in PUBLISHED_ADMIN_TOKENS:
        status, body, err = _post(
            f"{base}/ai-market/v2/accounts/acct_0000000000000000/credit",
            {"amount_usd": "probe-not-a-number"}, timeout,
            headers={"Authorization": f"Bearer {token}"})
        detail = str(body.get("detail") or "") if isinstance(body, dict) else ""
        if status in (401, 403) or (status == 503 and _ADMIN_UNSET in detail):
            measured += 1
        elif status in (200, 400, 503):
            measured += 1
            accepted.append(token)
        # 404/405/0: no such route on this build, or no answer — that proves nothing.
    if accepted:
        checks.append(Check(
            f"hub_refuses_published_admin_tokens{tag}", False,
            f"operator door OPENS to a token published in the repository: "
            f"{', '.join(t[:18] + '…' for t in accepted)} — rotate AIMARKET_ADMIN_TOKEN"))
    elif measured:
        checks.append(Check(f"hub_refuses_published_admin_tokens{tag}", True,
                            f"refuses all {measured} published tokens"))
    else:
        checks.append(Check(f"hub_refuses_published_admin_tokens{tag}", True,
                            "not measured (credit route absent or unreachable)",
                            critical=False))
    return checks


def probe_paywall(hub: str, timeout: float, scope: Scope | None = None) -> list[Check]:
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
        import inspect
        # The canary skips out-of-scope providers before contacting them. An older canary
        # without `allow` still works: its results are narrowed below either way.
        narrow = (scope is not None
                  and "allow" in inspect.signature(payment_canary.observe).parameters)
        seen = (payment_canary.observe(hub.rstrip("/"), timeout, allow=scope.allows)
                if narrow else payment_canary.observe(hub.rstrip("/"), timeout))
        manifest, probes, peers = seen.get("manifest"), seen.get("probes"), seen.get("peers")
        if scope is not None:
            # Narrowed before evaluate() so its own "every priced provider probed"
            # arithmetic is done over ours alone, not patched up afterwards.
            if isinstance(probes, dict):
                probes = [probes]
            probes = [p for p in probes or []
                      if scope.allows(str(p.get("source_hub") or "local"))]
            peers = [p for p in peers or [] if scope.allows(str(p.get("url") or ""))]
            if isinstance(manifest, dict) and manifest.get("_priced_providers"):
                manifest = dict(manifest, _priced_providers=[
                    u for u in manifest["_priced_providers"] if scope.allows(str(u))])
        canary_checks = payment_canary.evaluate(manifest, probes, seen.get("mcp_info"), peers)
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


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def decide(checks: list[Check], state: dict[str, Any], *, flap: int,
           heartbeat_hours: float, now: float) -> tuple[list[str], list[str], bool]:
    """Pure: (newly broken, newly recovered, digest due). Mutates `state` in place.

    `flap` consecutive failures are required before a check is considered broken, so a
    restart mid-poll does not page anyone. Recovery is immediate — being told too early
    that something came back costs nothing, being told too early that it broke costs
    trust in every later message.

    Each failing row remembers when its run of failures began (`since`), so a digest can
    say how long an incident has been open and a recovery how long it lasted.
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
                lasted = _hours_since_iso(str(row.get("since") or ""), now)
                if lasted is not None:
                    row["last_outage_hours"] = round(lasted, 2)
            row["failures"] = 0
            row["alerted"] = False
            row.pop("since", None)
        else:
            if not int(row.get("failures", 0)):
                row["since"] = _iso(now)
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
        state["last_alert"] = _iso(now)

    # Due on its clock whatever the state — green or red. A run that already carries an
    # alert or a recovery leaves the digest to the next run instead of sending two.
    age = _hours_since_iso(state.get("last_heartbeat") or "", now)
    due = not broke and not fixed and (age is None or age >= heartbeat_hours)
    if due:
        state["last_heartbeat"] = _iso(now)
    return broke, fixed, due


# ── message ──────────────────────────────────────────────────────────────────────────────

# Plain-language wording, so a page at 3am says what broke and why it matters without the
# reader having to know what `hub_federation_crawl_fresh@uni.modelmarket.dev` means.
# base check name -> (when failing, when recovered, what it costs). `{t}` is the hub, host or
# URL the check is about. English is the default (AICOM_ALERT_LANG=ru switches).
_EN: dict[str, tuple[str, str, str]] = {
    "hub_dns_resolves": (
        "DNS name {t} does not resolve", "DNS name {t} resolves again",
        "the hub cannot be reached by name"),
    "hub_dns_all_addresses_valid": (
        "not every DNS address of {t} serves our certificate",
        "every DNS address of {t} serves our certificate again",
        "some clients get a TLS error or land on a stranger's server"),
    "hub_manifest": (
        "hub {t} is not serving its catalogue", "hub {t} is serving its catalogue again",
        "buyers and agents cannot see the storefront"),
    "hub_catalogue_not_empty": (
        "the catalogue of hub {t} is empty", "the catalogue of hub {t} is filled again",
        "an empty storefront — usually what a federation failure looks like"),
    "hub_stats_live": (
        "live stats of hub {t} are not answering", "live stats of hub {t} answer again",
        "dashboard counters stop updating; sales are not affected"),
    "hub_federation_peers": (
        "hub {t} is not serving its peer list", "hub {t} is serving its peer list again",
        "nobody can see what it indexes; usually means the hub is down"),
    "hub_federation_pins_accepted": (
        "hub {t} rejected a peer's key", "hub {t} accepts every peer's key again",
        "it treats the key change as a possible takeover and keeps that peer's catalogue frozen"),
    "hub_federation_crawl_fresh": (
        "hub {t} stopped refreshing its peers", "hub {t} is refreshing its peers again",
        "its catalogue shows stale capabilities and prices"),
    "hub_advertises_public_url": (
        "hub {t} advertises an address nobody outside can reach",
        "hub {t} advertises its public address again",
        "agents and other hubs follow its links into nowhere — the shape of a redeploy "
        "that undid a fix"),
    "hub_refuses_published_admin_tokens": (
        "the admin door of hub {t} opens to a token printed in the repository",
        "the admin door of hub {t} is shut to published tokens again",
        "anyone who read the source can manage this hub's peers and balances"),
    "signer_reachable": (
        "the escrow signer is not answering", "the escrow signer answers again",
        "escrow payments are not being signed"),
    "signer_ready": (
        "the escrow signer is not ready", "the escrow signer is ready again",
        "escrow payments are not being signed"),
    "signer_not_halted": (
        "the escrow signer halted itself", "the escrow signer is running again",
        "it stopped on purpose — read its journal for the reason before restarting it"),
    "canary_status_published": (
        "the payment canary is not publishing its report",
        "the payment canary publishes its report again",
        "nobody is checking that the hub takes money"),
    "canary_status_fresh": (
        "the daily payment canary has not run", "the payment canary runs again",
        "nobody is checking that the hub takes money"),
    "canary_verdict_ok": (
        "the payment canary found a problem", "the payment canary is green again",
        "something in payment intake is broken — details in its report"),
    "settlement_report_published": (
        "the settlement sweep is not publishing its report",
        "the settlement sweep publishes its report again",
        "nobody can see whether payments reach the chain"),
    "settlement_sweep_fresh": (
        "the settlement sweep has not run", "the settlement sweep runs again",
        "payments buyers signed are not being submitted to the chain"),
    "settlement_nothing_stuck": (
        "there are unsubmitted payments", "no unsubmitted payments left",
        "buyers' money is stuck and not reaching the hub"),
    "settlement_nothing_expired_uncollected": (
        "money is sitting in expired payment channels", "expired channels are collected",
        "not urgent: anyone can collect it by calling expireChannel"),
    "credit_rail_reachable": (
        "seller {t} is not answering", "seller {t} answers again",
        "nobody can top up a balance there"),
    "credit_rail_published": (
        "seller {t} does not report its checkout state",
        "seller {t} reports its checkout state again",
        "nobody can see whether a buyer's payment would reach their balance"),
    "credit_rail_enabled": (
        "seller {t} has its checkout switched off", "seller {t} has its checkout on again", ""),
    "credit_rail_can_credit": (
        "seller {t} cannot credit payments", "seller {t} credits payments again",
        "a buyer would pay and receive no balance"),
    "credit_rail_verdict_fresh": (
        "seller {t} has not re-checked its checkout for a while",
        "seller {t} re-checks its checkout again", ""),
    "tls_expiry": (
        "the certificate for {t} expires soon", "the certificate for {t} was renewed",
        "automatic renewal is not working; there is still time to renew by hand"),
    "manifest_served": (
        "the hub does not serve its manifest to the payment check",
        "the hub serves its manifest again", ""),
    "payment_configured": (
        "payment intake on the hub is switched off", "payment intake is on again",
        "the hub takes no money"),
    "mainnet": (
        "the hub accepts payment on a testnet", "payment is on mainnet again",
        "testnet money is worth nothing"),
    "every_priced_provider_probed": (
        "the paywall was not checked for every priced provider",
        "the paywall is checked for every provider again",
        "for some providers nobody knows whether they charge"),
    "priced_capability_gated": (
        "paid access to {t} misbehaves", "paid access to {t} requires payment again",
        "paid work may be going out for free, or failing for buyers"),
    "mcp_endpoint_live": (
        "the hub's MCP endpoint is not answering", "the MCP endpoint answers again",
        "agents cannot connect to the hub over MCP"),
    "mcp_trial_per_caller": (
        "the MCP trial is shared by everyone", "the MCP trial is per caller again",
        "new agents hit 402 straight away"),
    "peer_alive": (
        "service {t} is not answering calls", "service {t} answers again",
        "its capabilities fail for every buyer"),
    "peer_endpoint_routable": (
        "service {t} advertises an internal address",
        "service {t} advertises an external address again",
        "hubs cannot forward calls to it"),
    "mcp_advertised": (
        "the hub does not advertise its MCP server", "the hub advertises its MCP server again",
        "agents have a harder time finding the way in"),
    "paywall_probe_available": (
        "the paywall check did not start", "the paywall check starts again",
        "this run did not check that the hub charges"),
    "paywall_probe_ran": (
        "the paywall check crashed", "the paywall check passes again",
        "this run did not check that the hub charges"),
}

# Fixed phrases of the page, per language.
_PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "broke": "\U0001F534 alexar76: {n} broken", "broke_total": ", {m} open in total",
        "fixed": "\U0001F7E2 alexar76: {n} recovered", "fixed_open": ", {m} still open",
        "digest_open": "\U0001F7E0 alexar76: daily digest — {n} open",
        "digest_ok": "\U0001F7E2 alexar76: daily digest — all good",
        "digest_warn": " ({w} warning(s))", "watcher": "{when} · watcher on {host}",
        "impact": "   Impact: ", "evidence": "   Evidence: ",
        "lasted": " (was broken for {d})", "still_open": "Still open:", "open": "Open:",
        "open_for": "open for {d}", "in_a_row": "{n} checks in a row",
        "since_now": "since this run", "unconfirmed": " (not yet confirmed by a second run)",
        "more": "…and {n} more", "warnings": "Warnings (these never page):",
        "ok_count": "{ok} of {total} checks OK.",
        "subdomains": " (incl. subdomains)", "everything": "everything the federation shows",
        "watching": "Watching: {w} — {c}; plus the escrow signer, the payment canary and "
                    "the settlement sweep.",
        "hubs": "hubs: {n}", "providers": "priced providers: {n}", "certs": "certificates: {n}",
        "not_watched": "Not watched (other ecosystems, owner's decision): ",
        "and_more": " and {n} more",
        "delivery": "Delivery: ", "email": "e-mail", "not_configured": "{c} — not configured",
        "no_sends": "{c} — no sends yet", "failing": "{c} ✗ (since {s}: {e})",
        "next_digest": "Next digest in {d}. If it does not arrive, the watcher is down.",
        "by_hand": "Check by hand: ssh not-my-vps, then",
        "back_suffix": "{n} — back to normal", "min": "{n} min", "h": "{n}h",
        "dh": "{d}d {h}h", "d": "{d}d",
    },
    "ru": {
        "broke": "\U0001F534 alexar76: сломалось — {n}", "broke_total": ", всего открыто — {m}",
        "fixed": "\U0001F7E2 alexar76: починилось — {n}", "fixed_open": ", ещё открыто — {m}",
        "digest_open": "\U0001F7E0 alexar76: сводка — открыто проблем: {n}",
        "digest_ok": "\U0001F7E2 alexar76: сводка — всё в порядке",
        "digest_warn": " (предупреждений: {w})", "watcher": "{when} · сторож на {host}",
        "impact": "   Чем грозит: ", "evidence": "   Факт: ",
        "lasted": " (было сломано {d})", "still_open": "Ещё открыто:", "open": "Открыто:",
        "open_for": "уже {d}", "in_a_row": "{n} проверок подряд",
        "since_now": "с этой проверки", "unconfirmed": " (ещё не подтверждено повтором)",
        "more": "…и ещё {n}", "warnings": "Предупреждения (не будят):",
        "ok_count": "В норме {ok} из {total} проверок.",
        "subdomains": " (с поддоменами)", "everything": "всё, что видно из федерации",
        "watching": "Наблюдаю: {w} — {c}; плюс escrow-подписант, платёжная канарейка и "
                    "сборщик оплат.",
        "hubs": "хабов: {n}", "providers": "платных поставщиков: {n}",
        "certs": "сертификатов: {n}",
        "not_watched": "Не наблюдаю (другие экосистемы, по решению владельца): ",
        "and_more": " и ещё {n}",
        "delivery": "Доставка: ", "email": "почта", "not_configured": "{c} — не настроена",
        "no_sends": "{c} — ещё не было отправок", "failing": "{c} ✗ (с {s}: {e})",
        "next_digest": "Следующая сводка — через {d}. Не пришла — значит, сторож не работает.",
        "by_hand": "Проверить руками: ssh not-my-vps, затем",
        "back_suffix": "{n} — снова в норме", "min": "{n} мин", "h": "{n} ч",
        "dh": "{d} сут {h} ч", "d": "{d} сут",
    },
}


_RU: dict[str, tuple[str, str, str]] = {
    "hub_dns_resolves": (
        "DNS-имя {t} не резолвится", "DNS-имя {t} снова резолвится",
        "хаб недоступен по имени"),
    "hub_dns_all_addresses_valid": (
        "не все DNS-адреса {t} отдают наш сертификат", "все DNS-адреса {t} снова отдают наш сертификат",
        "часть клиентов получает ошибку TLS или попадает на чужой сервер"),
    "hub_manifest": (
        "хаб {t} не отдаёт каталог", "хаб {t} снова отдаёт каталог",
        "покупатели и агенты не видят витрину"),
    "hub_catalogue_not_empty": (
        "каталог хаба {t} пуст", "каталог хаба {t} снова не пуст",
        "витрина пустая — обычно так выглядит отказ федерации"),
    "hub_stats_live": (
        "живая статистика хаба {t} не отвечает", "живая статистика хаба {t} снова отвечает",
        "не обновляются счётчики на дашбордах; продажам не мешает"),
    "hub_federation_peers": (
        "хаб {t} не отдаёт список пиров", "хаб {t} снова отдаёт список пиров",
        "не видно, кого он индексирует; обычно это значит, что хаб лежит"),
    "hub_federation_pins_accepted": (
        "хаб {t} отверг ключ пира", "хаб {t} снова принимает ключи всех пиров",
        "смену ключа хаб считает возможным захватом и держит каталог этого пира замороженным"),
    "hub_federation_crawl_fresh": (
        "хаб {t} перестал обновлять данные пиров", "хаб {t} снова обновляет данные пиров",
        "в его каталоге устаревшие возможности и цены"),
    "hub_advertises_public_url": (
        "хаб {t} объявляет адрес, до которого снаружи не достучаться",
        "хаб {t} снова объявляет публичный адрес",
        "агенты и другие хабы идут по его ссылкам в никуда — так выглядит откат настроек при передеплое"),
    "hub_refuses_published_admin_tokens": (
        "админка хаба {t} открывается токеном из репозитория",
        "админка хаба {t} снова закрыта для публичных токенов",
        "любой, кто читал репозиторий, может управлять пирами и балансами этого хаба"),
    "signer_reachable": (
        "escrow-подписант не отвечает", "escrow-подписант снова отвечает",
        "оплаты через escrow не подписываются"),
    "signer_ready": (
        "escrow-подписант не готов", "escrow-подписант снова готов",
        "оплаты через escrow не подписываются"),
    "signer_not_halted": (
        "escrow-подписант остановил сам себя", "escrow-подписант снова работает",
        "он остановился намеренно — сначала причина в его журнале, потом перезапуск"),
    "canary_status_published": (
        "платёжная канарейка не публикует отчёт", "платёжная канарейка снова публикует отчёт",
        "никто не проверяет, что хаб берёт деньги"),
    "canary_status_fresh": (
        "ежедневная платёжная канарейка не запускалась", "платёжная канарейка снова запускается",
        "никто не проверяет, что хаб берёт деньги"),
    "canary_verdict_ok": (
        "платёжная канарейка нашла проблему", "платёжная канарейка снова зелёная",
        "что-то в приёме оплаты сломано — подробности в её отчёте"),
    "settlement_report_published": (
        "сборщик оплат не публикует отчёт", "сборщик оплат снова публикует отчёт",
        "не видно, уходят ли оплаты в сеть"),
    "settlement_sweep_fresh": (
        "сборщик оплат не запускался", "сборщик оплат снова работает",
        "подписанные покупателями оплаты не отправляются в сеть"),
    "settlement_nothing_stuck": (
        "есть неотправленные оплаты", "неотправленных оплат больше нет",
        "деньги покупателей висят и не доходят до хаба"),
    "settlement_nothing_expired_uncollected": (
        "деньги лежат в истёкших платёжных каналах", "истёкшие каналы собраны",
        "не срочно: забрать их может кто угодно вызовом expireChannel"),
    "credit_rail_reachable": (
        "продавец {t} не отвечает", "продавец {t} снова отвечает",
        "у него нельзя пополнить баланс"),
    "credit_rail_published": (
        "продавец {t} не сообщает состояние кассы", "продавец {t} снова сообщает состояние кассы",
        "не видно, дойдёт ли оплата покупателя до баланса"),
    "credit_rail_enabled": (
        "у продавца {t} выключена касса", "у продавца {t} снова включена касса", ""),
    "credit_rail_can_credit": (
        "продавец {t} не может зачислять оплаты", "продавец {t} снова зачисляет оплаты",
        "покупатель заплатит и не получит баланс"),
    "credit_rail_verdict_fresh": (
        "продавец {t} давно не проверял свою кассу", "продавец {t} снова проверяет кассу", ""),
    "tls_expiry": (
        "сертификат {t} скоро истечёт", "сертификат {t} продлён",
        "автопродление не срабатывает; есть время продлить вручную"),
    "manifest_served": (
        "хаб не отдаёт манифест проверке оплаты", "хаб снова отдаёт манифест", ""),
    "payment_configured": (
        "на хабе выключен приём оплаты", "приём оплаты снова включён", "хаб не берёт деньги"),
    "mainnet": (
        "хаб принимает оплату в тестовой сети", "оплата снова в основной сети",
        "тестовые деньги ничего не стоят"),
    "every_priced_provider_probed": (
        "пейвол проверен не у всех платных поставщиков", "пейвол снова проверен у всех",
        "у части поставщиков неизвестно, берут ли они деньги"),
    "priced_capability_gated": (
        "платный доступ к {t} работает неправильно", "платный доступ к {t} снова требует оплату",
        "платная работа может уходить бесплатно или ломаться у покупателей"),
    "mcp_endpoint_live": (
        "MCP-эндпоинт хаба не отвечает", "MCP-эндпоинт снова отвечает",
        "агенты не могут подключиться к хабу по MCP"),
    "mcp_trial_per_caller": (
        "пробный доступ по MCP общий на всех", "пробный доступ по MCP снова у каждого свой",
        "новые агенты сразу упираются в 402"),
    "peer_alive": (
        "сервис {t} не отвечает на вызовы", "сервис {t} снова отвечает",
        "его возможности отдают ошибку всем покупателям"),
    "peer_endpoint_routable": (
        "сервис {t} объявляет внутренний адрес", "сервис {t} снова объявляет внешний адрес",
        "хабы не могут переслать ему вызов"),
    "mcp_advertised": (
        "хаб не объявляет свой MCP-сервер", "хаб снова объявляет MCP-сервер",
        "агентам сложнее найти вход"),
    "paywall_probe_available": (
        "проверка пейвола не запустилась", "проверка пейвола снова запускается",
        "в этом прогоне не проверено, берёт ли хаб деньги"),
    "paywall_probe_ran": (
        "проверка пейвола упала", "проверка пейвола снова проходит",
        "в этом прогоне не проверено, берёт ли хаб деньги"),
}


_WORDING = {"en": _EN, "ru": _RU}


def _host_of(hub: str) -> str:
    return hub.split("://", 1)[-1].split("/", 1)[0].split(":")[0]


def _describe(name: str, hub: str, lang: str = "en") -> tuple[str, str, str]:
    """(failing, recovered, impact) for one check, in words; unknown names fall back to
    themselves rather than to nothing."""
    target = _check_target(name)
    base = re.split(r"[@\[]|:(?=.)", name, maxsplit=1)[0]
    wording = _WORDING.get(lang, _EN).get(base)
    if wording is None:
        return name, _PHRASES[lang]["back_suffix"].format(n=name), ""
    shown = target.split("://", 1)[-1].rstrip("/") if target else _host_of(hub)
    fail, back, impact = wording
    return fail.format(t=shown), back.format(t=shown), impact


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _duration(hours: float | None, lang: str = "en") -> str:
    p = _PHRASES[lang]
    if hours is None:
        return "?"
    if hours < 1:
        return p["min"].format(n=max(1, round(hours * 60)))
    if hours < 48:
        return p["h"].format(n=round(hours))
    days, rest = divmod(round(hours), 24)
    return p["dh"].format(d=days, h=rest) if rest else p["d"].format(d=days)


def _open_for(row: dict[str, Any] | None, now: float, lang: str = "en") -> str:
    p, row = _PHRASES[lang], row or {}
    hours = _hours_since_iso(str(row.get("since") or ""), now)
    if hours is not None:
        return p["open_for"].format(d=_duration(hours, lang))
    failures = int(row.get("failures") or 0)
    return p["in_a_row"].format(n=failures) if failures else p["since_now"]


def _coverage(checks: list[Check], hub: str) -> tuple[int, int, int]:
    """(hubs, priced providers, certificates) this run actually looked at."""
    hubs = {n.split("@", 1)[1] if "@" in n else _host_of(hub)
            for n in (c.name for c in checks) if n.startswith("hub_federation_peers")}
    providers = sum(1 for c in checks if c.name.startswith("priced_capability_gated["))
    certs = sum(1 for c in checks if c.name.startswith("tls_expiry:"))
    return len(hubs), providers, certs


def _delivery_line(delivery: dict[str, Any] | None, lang: str = "en") -> str:
    """How the last messages actually went out, per channel — including a channel that is
    failing, which is the one thing the failing channel itself cannot report."""
    p = _PHRASES[lang]
    parts = []
    for channel, label in (("telegram", "Telegram"), ("email", p["email"])):
        row = (delivery or {}).get(channel)
        if row is None:
            parts.append((p["not_configured"] if channel == "email" else p["no_sends"])
                         .format(c=label))
        elif row.get("ok"):
            parts.append(f"{label} ✓")
        else:
            parts.append(p["failing"].format(
                c=label, s=str(row.get("failing_since") or row.get("at") or "?")[:16],
                e=str(row.get("error") or "")[:80]))
    return p["delivery"] + " · ".join(parts)


def format_message(checks: list[Check], broke: list[str], fixed: list[str],
                   heartbeat: bool, *, host: str, hub: str, when: str, lang: str = "en",
                   state: dict[str, Any] | None = None, scope: Scope | None = None,
                   delivery: dict[str, Any] | None = None, heartbeat_hours: float = 24.0,
                   now: float | None = None) -> str:
    """One screen on a phone: what broke, why it matters, the evidence, how long it has
    been open, and what to run next."""
    now = time.time() if now is None else now
    lang = lang if lang in _PHRASES else "en"
    p = _PHRASES[lang]
    digest = heartbeat
    by_name = {c.name: c for c in checks}
    rows = (state or {}).get("checks", {})
    down = [c for c in checks if not c.ok and c.critical]
    warnings = [c for c in checks if not c.ok and not c.critical]
    still_open = [c for c in down if c.name not in broke]
    lines: list[str] = []

    if broke:
        lines.append(p["broke"].format(n=len(broke))
                     + (p["broke_total"].format(m=len(down)) if len(down) > len(broke) else ""))
    elif fixed:
        lines.append(p["fixed"].format(n=len(fixed))
                     + (p["fixed_open"].format(m=len(down)) if down else ""))
    elif down:
        # A headline claiming everything is green while a critical check is red is the one
        # thing a monitor may never print. It did print it once.
        lines.append(p["digest_open"].format(n=len(down)))
    else:
        lines.append(p["digest_ok"] + (p["digest_warn"].format(w=len(warnings))
                                        if warnings else ""))
    lines.append(p["watcher"].format(when=when, host=host))

    for name in broke:
        c = by_name.get(name)
        fail, _back, impact = _describe(name, hub, lang)
        lines.append("")
        lines.append(f"✖ {_cap(fail)}")
        if impact:
            lines.append(p["impact"] + impact)
        if c and c.detail:
            lines.append(p["evidence"] + c.detail[:200])
    if fixed:
        lines.append("")
    for name in fixed:
        _fail, back, _impact = _describe(name, hub, lang)
        lasted = rows.get(name, {}).get("last_outage_hours")
        lines.append(f"✔ {_cap(back)}"
                     + (p["lasted"].format(d=_duration(lasted, lang))
                        if lasted is not None else ""))

    if still_open:
        # Includes what has not crossed the flap threshold yet: the reader must be able to
        # see what the headline is counting.
        lines.append("")
        lines.append(p["still_open"] if (broke or fixed) else p["open"])
        for c in still_open[:6]:
            fail, _back, impact = _describe(c.name, hub, lang)
            paged = rows.get(c.name, {}).get("alerted")
            lines.append(f"✖ {_cap(fail)} — {_open_for(rows.get(c.name), now, lang)}"
                         + ("" if paged else p["unconfirmed"]))
            if digest and impact:
                lines.append(p["impact"] + impact)
            lines.append(p["evidence"] + c.detail[:160])
        if len(still_open) > 6:
            lines.append(p["more"].format(n=len(still_open) - 6))

    if digest and warnings:
        lines.append("")
        lines.append(p["warnings"])
        for c in warnings[:5]:
            fail, _back, _impact = _describe(c.name, hub, lang)
            lines.append(f"⚠ {_cap(fail)}: {c.detail[:120]}")

    lines.append("")
    lines.append(p["ok_count"].format(ok=sum(1 for c in checks if c.ok), total=len(checks)))
    if digest:
        hubs, providers, certs = _coverage(checks, hub)
        watched = (", ".join(scope.domains) + p["subdomains"]
                   if scope is not None and scope.domains else p["everything"])
        cover = [p["hubs"].format(n=hubs)]
        if providers:
            cover.append(p["providers"].format(n=providers))
        if certs:
            cover.append(p["certs"].format(n=certs))
        lines.append(p["watching"].format(w=watched, c=", ".join(cover)))
        if scope is not None and scope.excluded:
            others = sorted(scope.excluded)
            lines.append(p["not_watched"] + ", ".join(others[:8])
                         + (p["and_more"].format(n=len(others) - 8) if len(others) > 8 else ""))
    if digest or any(not row.get("ok") for row in (delivery or {}).values()):
        lines.append(_delivery_line(delivery, lang))
    if digest:
        lines.append(p["next_digest"].format(d=_duration(heartbeat_hours, lang)))
    if broke:
        lines.append("")
        lines.append(p["by_hand"])
        lines.append("  python3 /usr/local/lib/aicom-alert/ecosystem_alert.py --mode full --dry-run")
    return "\n".join(lines)[:3900]


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


def email_config_from_env() -> dict[str, Any] | None:
    """SMTP settings, or None while e-mail is not wired up (no recipient or no server)."""
    to = [a.strip() for a in os.environ.get("AICOM_ALERT_EMAIL_TO", "").split(",") if a.strip()]
    host = os.environ.get("AICOM_ALERT_SMTP_HOST", "").strip()
    if not to or not host:
        return None
    try:
        port = int(os.environ.get("AICOM_ALERT_SMTP_PORT", "") or 587)
    except ValueError:
        port = 587
    user = os.environ.get("AICOM_ALERT_SMTP_USER", "").strip()
    return {"host": host, "port": port, "user": user,
            "password": os.environ.get("AICOM_ALERT_SMTP_PASSWORD", ""),
            "from": os.environ.get("AICOM_ALERT_EMAIL_FROM", "").strip() or user,
            "to": to}


def send_email(cfg: dict[str, Any], text: str, *, timeout: float = EMAIL_TIMEOUT
               ) -> tuple[bool, str]:
    """The same plain text as the Telegram message; its first line is the subject.

    TLS is not optional: 465 is implicit TLS and every other port must accept STARTTLS
    before the login, or nothing is sent — a mailbox password in the clear would be a
    leak this alerter caused. Never raises, for the same reason `send_telegram` does not.
    """
    msg = EmailMessage()
    msg["Subject"] = (text.splitlines() or ["AIMarket alert"])[0][:200]
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(cfg["to"])
    msg["Date"] = email.utils.formatdate(usegmt=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="aicom-alert.local")
    msg.set_content(text)
    context = ssl.create_default_context()
    server = None
    try:
        if int(cfg["port"]) == 465:
            server = smtplib.SMTP_SSL(cfg["host"], 465, timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=timeout)
            server.starttls(context=context)
        if cfg.get("user"):
            server.login(cfg["user"], cfg.get("password") or "")
        refused = server.send_message(msg)
        if refused:
            return False, ("refused: " + ", ".join(sorted(refused)))[:160]
        return True, "sent"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:160]
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                server.close()


def channels_from_env(token: str, chat: str) -> list[tuple[str, Any]]:
    """(name, send(text) -> (ok, info)) for every channel that is configured."""
    channels: list[tuple[str, Any]] = []
    if token and chat:
        channels.append(("telegram", lambda text: send_telegram(token, chat, text)))
    cfg = email_config_from_env()
    if cfg:
        channels.append(("email", lambda text: send_email(cfg, text)))
    return channels


def deliver(channels: list[tuple[str, Any]], text: str, state: dict[str, Any],
            now: float) -> tuple[bool, dict[str, str]]:
    """Send on every channel; delivered if ANY got through.

    Per-channel outcomes go into ``state["delivery"]``, so a channel that has started
    failing is reported by the ones that still work — a dead mailbox cannot tell anyone
    it is dead.
    """
    rows = state.setdefault("delivery", {})
    results: dict[str, str] = {}
    delivered = False
    for name, send in channels:
        ok, info = send(text)
        results[name] = f"{'ok' if ok else 'FAILED'} {info}".strip()
        row = rows.setdefault(name, {})
        if ok:
            delivered = True
            rows[name] = {"ok": True, "at": _iso(now)}
        else:
            rows[name] = {"ok": False, "at": _iso(now), "error": info,
                          "failing_since": row.get("failing_since") if not row.get("ok", True)
                          else _iso(now)}
    for name in list(rows):
        if name not in {n for n, _ in channels}:
            rows.pop(name)  # a channel that was switched off is not "failing"
    return delivered, results


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


def tls_names_from_env(hub: str) -> list[str]:
    """Names whose certificate EXPIRY is watched, not just its validity.

    Defaults to every public name this estate serves, because the list nobody maintains is
    the list that goes stale exactly when a new name is added. Override with
    ``AICOM_ALERT_TLS_NAMES`` (comma-separated) or set it empty to switch the check off.
    """
    raw = os.environ.get("AICOM_ALERT_TLS_NAMES")
    if raw is not None:
        return [n.strip() for n in raw.split(",") if n.strip()]
    host = hub.split("://", 1)[-1].split("/", 1)[0].split(":")[0]
    # The alexar76 ecosystem's own names (see `Scope`); other ecosystems renew their own.
    return sorted({
        host,
        "modelmarket.dev", "hub.modelmarket.dev", "uni.modelmarket.dev",
        "monitor.modelmarket.dev", "hunt.modelmarket.dev", "themis.modelmarket.dev",
        "atlas.modelmarket.dev", "verify.modelmarket.dev", "oracles.modelmarket.dev",
        "iot.modelmarket.dev", "momus.modelmarket.dev", "skopos.modelmarket.dev",
        "basanos.modelmarket.dev", "hestia.modelmarket.dev", "logos.modelmarket.dev",
        "histor.modelmarket.dev",
        "magic-ai-factory.com",
    })


def probe_tls_expiry(names: list[str], timeout: float = 8.0,
                     warn_days: int = 21) -> list[Check]:
    """How much life is left in each certificate.

    `probe_dns` already refuses a certificate that is expired or names the wrong host — but
    it fires the day the outage starts. Renewal happens 30 days before expiry, so a
    certificate under three weeks old-remaining has missed at least one attempt and is going
    to miss the next one for the same reason. That is the moment worth a message: there is
    still time to fix it by hand.

    Non-critical on purpose. A certificate with 20 days left is not an incident and must not
    wake anyone at 3am; it is a note that renewal has stopped working somewhere.
    """
    checks: list[Check] = []
    for host in names:
        try:
            with socket.create_connection((host, 443), timeout=timeout) as raw:
                with ssl.create_default_context().wrap_socket(
                        raw, server_hostname=host) as tls:
                    cert = tls.getpeercert() or {}
            not_after = str(cert.get("notAfter") or "")
            expires = datetime.datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            days = (expires - now_utc).days
            checks.append(Check(
                f"tls_expiry:{host}", days >= warn_days,
                (f"{days}d left" if days >= warn_days
                 else f"only {days}d left (renewal runs at 30d — it is not running)"),
                critical=False,
            ))
        except Exception as exc:
            # Unreachable or unverifiable is `probe_dns`'s job to shout about; here it means
            # only that the expiry could not be read, which must not masquerade as an
            # expiring certificate.
            checks.append(Check(f"tls_expiry:{host}", True,
                                f"not measured ({type(exc).__name__})", critical=False))
    return checks


def collect(mode: str, *, hub: str, signer: str, status_url: str, settlement_url: str,
            timeout: float, federation_hubs: list[str] | None = None,
            sellers: list[str] | None = None, scope: Scope | None = None) -> list[Check]:
    scope = scope if scope is not None else Scope.from_env()
    checks: list[Check] = []
    sellers = sellers if sellers is not None else sellers_from_env()
    checks += probe_credit_rail([s for s in sellers if scope.allows(s)], min(timeout, 10.0))
    checks += probe_dns(hub)
    checks += probe_tls_expiry([n for n in tls_names_from_env(hub) if scope.allows(n)],
                               min(timeout, 8.0))
    checks += probe_hub(hub, timeout)
    checks += probe_federation(hub, timeout, scope=scope)
    watched = (federation_hubs if federation_hubs is not None
               else federation_hubs_from_env(hub))
    watched_pairs = [pair for pair in (_split_hub_entry(entry) for entry in watched)
                     if scope.allows(pair[1])]
    for label, url in watched_pairs:
        checks += probe_federation(url, timeout, label=label, scope=scope)
    # The signer answers on loopback only, so an instance running anywhere else must be
    # able to opt out (AICOM_ALERT_SIGNER_URL=""). Otherwise that one check fails forever
    # and the alerter it belongs to gets muted for being wrong, not for being noisy.
    if signer.strip():
        checks += probe_signer(signer, min(timeout, 10.0))
    checks += probe_status_page(status_url, timeout, scope=scope)
    checks += probe_settlement(settlement_url, timeout)
    if mode == "full":
        checks += probe_paywall(hub, timeout, scope=scope)
        # Hourly, not every ten minutes: five POSTs per hub, and what it guards against — a
        # redeploy undoing a fix — is a matter of days, not minutes.
        checks += probe_hub_identity(hub, min(timeout, 10.0))
        for label, url in watched_pairs:
            checks += probe_hub_identity(url, min(timeout, 10.0), label=label)
        # Every hub the federation knows about, on top of the configured ones. Configured
        # entries stay because a hub of ours need not be a peer of this one (the UNI bubble
        # is not), and quick mode has no discovery.
        seen = {_federation_label(hub)} | {_federation_label(u) for _l, u in watched_pairs}
        for found in discover_federation_hubs(hub, timeout, scope=scope):
            label = _federation_label(found)
            if label in seen:
                continue
            seen.add(label)
            checks += probe_federation(found, timeout, label=label, scope=scope)
            checks += probe_hub_identity(found, min(timeout, 10.0), label=label)
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
    lang = (os.environ.get("AICOM_ALERT_LANG") or "en").strip().lower()
    # The provider's hostname (78471.koara.live) says nothing to the reader; the name the
    # operator uses for the box does.
    host = os.environ.get("AICOM_ALERT_HOST_LABEL", "").strip() or socket.gethostname()
    now = time.time()
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now))
    channels = channels_from_env(token, chat)

    if args.send_test:
        if not channels:
            print("no delivery channel configured — set AICOM_ALERT_TELEGRAM_TOKEN and "
                  "AICOM_ALERT_TELEGRAM_CHAT, and/or AICOM_ALERT_EMAIL_TO with "
                  "AICOM_ALERT_SMTP_*", file=sys.stderr)
            return 2
        text = (f"\U0001F7E1 Сторож экосистемы alexar76 подключён ({host})\n{when}\n"
                f"Наблюдаю {hub} и всё под {', '.join(Scope.from_env().domains or ('*',))}.\n"
                f"Дальше — сообщение при поломке, при починке и сводка раз в "
                f"{_duration(heartbeat_hours, 'ru')}." if lang == "ru" else
                f"\U0001F7E1 alexar76 ecosystem watcher wired up ({host})\n{when}\n"
                f"Watching {hub} and everything under "
                f"{', '.join(Scope.from_env().domains or ('*',))}.\n"
                f"From now on: a message when something breaks, one when it recovers, and a "
                f"digest every {_duration(heartbeat_hours)}.")
        results = {name: send(text) for name, send in channels}
        for name, (ok, info) in results.items():
            print(f"send[{name}]: {'ok' if ok else 'FAILED'} {info}")
        return 0 if all(ok for ok, _ in results.values()) else 1

    scope = Scope.from_env()
    checks = collect(args.mode, hub=hub, signer=signer, status_url=status_url,
                     settlement_url=settlement_url, timeout=args.timeout,
                     federation_hubs=federation_hubs_from_env(hub), scope=scope)
    state = load_state(args.state)
    heartbeat_before = state.get("last_heartbeat", "")
    broke, fixed, heartbeat = decide(checks, state, flap=flap,
                                     heartbeat_hours=heartbeat_hours, now=now)
    message = format_message(checks, broke, fixed, heartbeat,
                             host=host, hub=hub, when=when, lang=lang, state=state,
                             scope=scope, delivery=state.get("delivery"),
                             heartbeat_hours=heartbeat_hours, now=now)
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
        if not channels:
            print("would alert, but no delivery channel (Telegram or e-mail) is configured",
                  file=sys.stderr)
            return 2
        delivered, results = deliver(channels, message, state, now)
        for name, info in results.items():
            print(f"{name}: {info}", file=sys.stdout if info.startswith("ok") else sys.stderr)
        if not delivered:
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
            save_state(args.state, state)
            return 1

    save_state(args.state, state)
    # Exit non-zero while a critical check is down, so `systemctl status` and any
    # future supervisor see it too.
    return 1 if any(not c.ok and c.critical for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
