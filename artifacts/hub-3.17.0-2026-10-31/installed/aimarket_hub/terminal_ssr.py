"""Seed terminal-home.html with live ticker numbers before JavaScript runs.

The page ships with `0 / $0.00 / 0` in the hero so a local file preview still
renders. Crawlers (Google, Bing, social unfurlers) do not execute the poll to
`/ai-market/v2/stats/live`, so they indexed those placeholders as the market.
This module writes the same public summary into the HTML the hub actually serves.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

from aimarket_hub import ecosystem
from aimarket_hub.consumer_labels import public_consumer_label
from aimarket_hub.models import normalize_purpose

_STAT_VAL = re.compile(r'(id="(?P<id>s-inv|s-rev|s-hubs|s-caps)">)(?P<val>[^<]*)(</div>)')
_JSON_MARK = '<script type="application/json" id="hub-ssr-live">{}</script>'
_NOSCRIPT_RE = re.compile(
    r'(<noscript id="hub-ssr-noscript">).*?(</noscript>)',
    re.DOTALL,
)
_DESC_RE = re.compile(r'(<meta name="description" content=")[^"]*(")')
_OG_DESC_RE = re.compile(r'(<meta property="og:description" content=")[^"]*(")')
_FEED_RE = re.compile(
    r'(<div id="feed">).*?(</div>\s*</div>\s*<div class="card market-pulse">)',
    re.DOTALL,
)
_TOP_RE = re.compile(
    r'(<ul class="lb" id="top-caps">).*?(</ul>)',
    re.DOTALL,
)
_INV_SUB_RE = re.compile(
    r'<div class="stat-sub" id="s-inv-sub"[^>]*>.*?</div>',
    re.DOTALL,
)
_HUBS_SUB_RE = re.compile(r'(id="s-hubs-sub">)[^<]*(</div>)')
_CAPS_SUB_RE = re.compile(r'(id="s-caps-sub">)[^<]*(</div>)')


def _literal(text: str):
    """A ``re.sub`` replacement that inserts ``text`` verbatim.

    A replacement *string* is a template: ``re`` expands ``\\g<1>``, ``\\1`` and — the one
    that bites — OCTAL escapes, so ``\\074`` becomes ``<``. ``html.escape`` does not touch
    backslashes, so a capability id of ``\\074script\\076alert(1)\\074/script\\076`` survived
    escaping and was expanded into real ``<script>`` tags in the served page. A callable
    replacement is used as-is, with no template pass, which closes that hole for good.
    """
    return lambda _m: text


def _group_wrap(text: str):
    """Same, for the ``(prefix)…(suffix)`` patterns: keeps both groups, inserts literally."""
    return lambda m: m.group(1) + text + m.group(2)


def _usd_hour(rev: float) -> str:
    if rev == 0:
        return "$0.00"
    sign = "-" if rev < 0 else ""
    if abs(rev) < 0.000001:
        return f"{sign}<$0.000001"
    # Match the browser's usd(): retain sub-cent digits even above one cent.
    whole, fraction = f"{abs(rev):.6f}".rstrip("0").split(".")
    return f"{sign}${whole}.{fraction.ljust(2, '0')}"


def public_events(rows: list[dict[str, Any]], hub_url: str,
                  policy: ecosystem.EcosystemPolicy | None = None) -> list[dict[str, Any]]:
    """Classify and pseudonymize recent rows exactly as /stats/live does (one implementation).

    ``traffic_class`` is ``operator_self`` (SELF) or ``external`` (EXT); ``traffic_basis``
    says why (ecosystem.py). The stored ``caller_class`` is an internal verdict and does not
    leave the hub; the consumer id is pseudonymized.
    """
    if policy is None:
        policy = ecosystem.current()
    out: list[dict[str, Any]] = []
    for row in rows:
        ev = dict(row)
        ch = str(ev.get("consumer_hub") or "")
        cls, basis = policy.classify(ch, str(ev.pop("caller_class", "") or ""), hub_url)
        ev["traffic_class"] = cls
        ev["traffic_basis"] = basis
        ev["consumer_hub"] = public_consumer_label(ch)
        out.append(ev)
    return out


def snapshot(db: Any, *, hub_url: str = "", event_limit: int = 12,
             policy: ecosystem.EcosystemPolicy | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Public ticker numbers + a short event page. Never raises on an empty db."""
    if policy is None:
        policy = ecosystem.current()
    summary = dict(db.stats_summary())
    events = public_events(db.recent_stats(limit=event_limit), hub_url, policy=policy)
    split = db.consumer_traffic_totals(policy=policy, hub_url=hub_url)
    summary["external_invocations"] = split["external"]
    summary["operator_self_invocations"] = split["operator_self"]
    return summary, events


def _feed_html(events: list[dict[str, Any]]) -> str:
    rows = []
    for e in events[:8]:
        cap = html.escape(str(e.get("capability_id") or "?"))
        hub = html.escape(str(e.get("source_hub") or "local"))
        purpose = normalize_purpose(e.get("purpose"))
        purpose_html = f'<span class="purpose">{html.escape(purpose)}</span>' if purpose else ""
        outcome = str(e.get("outcome") or ("ok" if e.get("success") else "fail"))
        if outcome == "ok":
            cls, mark = "ok", "✓"
        elif outcome == "incomplete":
            cls, mark = "partial", "⋯"
        elif outcome == "refused":
            cls, mark = "skip", "⊘"
        else:
            cls, mark = "bad", "✗"
        price = _usd_hour(float(e.get("price_usd") or 0))
        lat = e.get("latency_ms")
        lat_s = f"{int(lat)}ms" if lat is not None else "—"
        tc = "ext" if e.get("traffic_class") == "external" else "self"
        rows.append(
            f'<div class="row-feed">'
            f'<span>🤖</span>'
            f'<span class="cap-cell"><span class="cap-id">{cap}</span>'
            f'{purpose_html}'
            f'<div class="hub-via"><span class="host">{hub}</span></div></span>'
            f'<span class="tc {tc}">{tc}</span>'
            f'<span class="usd">{html.escape(price)}</span>'
            f'<span class="lat">{html.escape(lat_s)}</span>'
            f'<span class="{cls}">{mark}</span></div>'
        )
    return "".join(rows)


def _top_html(events: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for e in events:
        cap = str(e.get("capability_id") or "?")
        counts[cap] = counts.get(cap, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    if not ranked:
        return '<li><span>—</span><span style="color:var(--faint)">collecting…</span><span class="cnt">0</span></li>'
    items = []
    for i, (cap, n) in enumerate(ranked, 1):
        items.append(
            f'<li><span>{i}</span><span class="cap-id">{html.escape(cap)}</span>'
            f'<span class="cnt">{n}</span></li>'
        )
    return "".join(items)


def seed_terminal_home(page: str, summary: dict[str, Any], events: list[dict[str, Any]]) -> str:
    """Rewrite the static shell so a crawler sees the live ticker."""
    inv = int(summary.get("total_invocations") or 0)
    rev = float(summary.get("revenue_per_hour_usd") or 0)
    hubs = int(summary.get("peers_count") or 0)
    caps = int(
        summary.get("offerable_capabilities_count")
        or summary.get("capabilities_count")
        or 0
    )
    fed = int(summary.get("federated_capabilities_count") or 0)
    ext = int(summary.get("external_invocations") or 0)
    own = int(summary.get("operator_self_invocations") or 0)
    rate = float(summary.get("success_rate") or 0)

    values = {
        "s-inv": str(inv),
        "s-rev": _usd_hour(rev),
        "s-hubs": str(hubs),
        "s-caps": str(caps),
    }

    def _stat(m: re.Match[str]) -> str:
        return m.group(1) + values[m.group("id")] + m.group(4)

    out = _STAT_VAL.sub(_stat, page)

    if inv > 0:
        pct = f"{rate * 100:.1f}%"
        sub = f"{pct} success · {ext} external / {own} self"
        incomplete = int(summary.get("incomplete_invocations") or 0)
        if incomplete > 0:
            sub += f" · ⋯ {incomplete} incomplete input"
        refused = int(summary.get("refused_invocations") or 0)
        if refused > 0:
            sub += f" · ⊘ {refused} refused"
        out = _INV_SUB_RE.sub(
            _literal(f'<div class="stat-sub" id="s-inv-sub">{html.escape(sub)}</div>'),
            out,
            count=1,
        )
    if hubs > 0:
        out = _HUBS_SUB_RE.sub(_group_wrap(f"{hubs} peers online"), out, count=1)
    if caps > 0:
        cap_sub = f"{fed} federated" if fed else "indexed tools"
        out = _CAPS_SUB_RE.sub(_group_wrap(html.escape(cap_sub)), out, count=1)

    desc = (
        f"Live AIMarket hub: {inv} invocations, {hubs} federation peers, {caps} capabilities. "
        "Discovery, HTTP 402 payments, safety-gated invoke."
    )
    out = _DESC_RE.sub(_group_wrap(html.escape(desc, quote=True)), out, count=1)
    og = (
        f"{inv} invocations · {hubs} federation peers · {caps} capabilities — "
        "live AI-to-AI commerce ticker."
    )
    out = _OG_DESC_RE.sub(_group_wrap(html.escape(og, quote=True)), out, count=1)

    noscript = (
        f"<p>Live: {inv} invocations · {hubs} federation peers · {caps} capabilities · "
        f"{_usd_hour(rev)}/hour. JSON: /ai-market/v2/stats/live</p>"
    )
    out = _NOSCRIPT_RE.sub(_group_wrap(noscript), out, count=1)

    if events:
        feed = _feed_html(events)
        out = _FEED_RE.sub(
            _literal(
                f'<div id="feed">{feed}</div></div>\n      '
                '<div class="card market-pulse">'
            ),
            out,
            count=1,
        )
        out = _TOP_RE.sub(_group_wrap(_top_html(events)), out, count=1)

    payload = {"summary": summary, "events": events}
    blob = json.dumps(payload, separators=(",", ":"), default=str).replace("<", "\\u003c")
    if _JSON_MARK in out:
        out = out.replace(_JSON_MARK, f'<script type="application/json" id="hub-ssr-live">{blob}</script>', 1)
    return out
