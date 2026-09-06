"""Human-readable factory agent roster at /agents (nginx proxies here before Next).

Server-renders a styled shell + first paint from the registry, then the page polls
``/api/agents`` so new heartbeats appear without a redeploy or hard refresh.

Prod used to attach ``Content-Security-Policy: default-src 'none'`` to this HTML
(API-wide middleware). That blocked inline CSS/JS and Google Fonts — visitors saw
an unstyled document stuck on ``loading…`` forever while ``/api/agents`` was fine.
"""

from __future__ import annotations

import html
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from web.backend.services.agent_registry import list_agents, registry_summary

router = APIRouter(tags=["agents"])

_POLL_MS = 15_000

# Inline CSS/JS + fonts + same-origin fetch. Frame ancestors none (not an embed).
AGENTS_PAGE_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "img-src 'self' data:; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "form-action 'self'"
)


def _initial_payload() -> dict[str, Any]:
    return {
        "agents": list_agents(include_offline=True),
        "summary": registry_summary(),
    }


def _esc(value: Any) -> str:
    return html.escape(str("" if value is None else value), quote=True)


def _money(usd: Any) -> str:
    n = float(usd or 0)
    if not n:
        return "$0"
    if n < 0.01:
        return f"${n:.4f}"
    return f"${n:.2f}"


def _age(sec: Any) -> str:
    s = max(0, int(round(float(sec or 0))))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{round(s / 60)}m"
    if s < 86400:
        return f"{round(s / 3600)}h"
    return f"{round(s / 86400)}d"


def _rank(status: str) -> int:
    return 0 if status == "live" else 1 if status == "stale" else 2


def _render_stats_html(summary: dict[str, Any], agent_count: int) -> str:
    live = summary.get("agents_live") or 0
    total = summary.get("agents_total") or agent_count
    invokes = int(summary.get("invokes_total") or 0)
    return (
        f'<div class="stat"><div class="label">Live</div><div class="value">{_esc(live)}/{_esc(total)}</div></div>'
        f'<div class="stat"><div class="label">Invokes</div><div class="value">{_esc(f"{invokes:,}")}</div></div>'
        f'<div class="stat"><div class="label">Spent</div><div class="value">{_esc(_money(summary.get("spend_usd_total")))}</div></div>'
        f'<div class="stat"><div class="label">Agents</div><div class="value">{_esc(agent_count)}</div></div>'
    )


def _render_chips_html(summary: dict[str, Any]) -> str:
    sdks = summary.get("sdks") if isinstance(summary.get("sdks"), dict) else {}
    return "".join(
        f'<span class="chip">{_esc(k)} · {_esc(v)}</span>' for k, v in sdks.items()
    )


def _render_list_html(agents: list[dict[str, Any]]) -> str:
    if not agents:
        return (
            '<div class="empty"><p>No agents registered yet.</p>'
            '<a class="cta" href="/">Start a build</a></div>'
        )
    ordered = sorted(
        agents,
        key=lambda a: (
            _rank(str(a.get("status") or "offline")),
            -float((a.get("stats") or {}).get("spend_usd_total") or 0),
        ),
    )
    cards: list[str] = []
    for a in ordered:
        stats = a.get("stats") if isinstance(a.get("stats"), dict) else {}
        status = str(a.get("status") or "offline")
        caps = a.get("capabilities_used") if isinstance(a.get("capabilities_used"), list) else []
        pid = str(a.get("product_id") or "")
        product = (
            f'<a href="/product/{_esc(pid)}">{_esc(pid)}</a>' if pid else ""
        )
        pub_url = str(a.get("public_url") or "")
        pub = (
            f'<a href="{_esc(pub_url)}" target="_blank" rel="noopener noreferrer">{_esc(pub_url)}</a>'
            if pub_url
            else ""
        )
        cap_html = "".join(
            f'<span class="cap">{_esc(c)}</span>' for c in caps[:12]
        )
        cards.append(
            '<article class="card">'
            '<div class="card-top"><div>'
            f'<h2 class="name">{_esc(a.get("name") or a.get("agent_id") or "Agent")}</h2>'
            f'<div class="aid">{_esc(a.get("agent_id") or "")}</div>'
            "</div>"
            f'<span class="badge {_esc(status)}">{_esc(status)} · {_esc(_age(a.get("age_sec")))} ago</span>'
            "</div>"
            '<div class="row">'
            + (f"<span>{product}</span>" if product else "")
            + (f'<span>sdk {_esc(a.get("sdk"))}</span>' if a.get("sdk") else "")
            + (f'<span>v{_esc(a.get("version"))}</span>' if a.get("version") else "")
            + f'<span>{_esc(int(stats.get("invokes_total") or 0))} invokes</span>'
            + f'<span>{_esc(_money(stats.get("spend_usd_total")))}</span>'
            + (f"<span>{pub}</span>" if pub else "")
            + "</div>"
            + (f'<div class="caps">{cap_html}</div>' if cap_html else "")
            + "</article>"
        )
    return "".join(cards)


@router.get("/agents", response_class=HTMLResponse)
async def agents_roster_page() -> HTMLResponse:
    payload = _initial_payload()
    agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    # Safe embed: json.dumps escapes <>& so </script> cannot break out.
    boot = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    html_out = (
        _PAGE.replace("__BOOT__", boot)
        .replace("__POLL_MS__", str(_POLL_MS))
        .replace("__STATS__", _render_stats_html(summary, len(agents)))
        .replace("__CHIPS__", _render_chips_html(summary))
        .replace("__LIST__", _render_list_html(agents))
        .replace(
            "__META__",
            f"synced · {len(agents)} agent{'s' if len(agents) != 1 else ''}",
        )
    )
    return HTMLResponse(
        content=html_out,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": AGENTS_PAGE_CSP,
        },
    )


_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="dark" />
  <title>Factory agents · AI-Factory</title>
  <meta name="description" content="Autonomous agents the factory built and shipped — SDK, mesh capabilities, invoke and spend counters." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Syne:wght@600;700;800&display=swap" rel="stylesheet" />
  <style>
    :root {
      color-scheme: dark;
      --bg0: #071018;
      --bg1: #0c1824;
      --glass: rgba(255,255,255,0.045);
      --glass-border: rgba(148, 197, 210, 0.14);
      --accent: #3ecfbf;
      --accent-2: #7dd3c7;
      --text: #e7eef2;
      --muted: #8fa3b0;
      --dim: #5f7382;
      --live: #3ecf8e;
      --stale: #e0b35a;
      --offline: #7a8d9a;
      --card-radius: 18px;
      --shadow: 0 18px 50px rgba(0,0,0,0.35);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", system-ui, sans-serif;
      color: var(--text);
      background:
        radial-gradient(1000px 520px at 8% -8%, rgba(62,207,191,0.14), transparent 55%),
        radial-gradient(800px 480px at 92% 4%, rgba(56,120,140,0.18), transparent 50%),
        linear-gradient(165deg, var(--bg0), var(--bg1) 42%, #060e14);
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { color: var(--accent-2); text-decoration: underline; }
    .shell { max-width: 980px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }
    .nav {
      display: flex; align-items: center; justify-content: space-between;
      gap: 1rem; margin-bottom: 2.25rem; flex-wrap: wrap;
    }
    .nav a.brand {
      font-family: Syne, "IBM Plex Sans", sans-serif;
      font-weight: 700; font-size: 1.05rem; color: var(--text);
      text-decoration: none; letter-spacing: -0.03em;
    }
    .nav a.brand span { color: var(--accent); }
    .nav-links { display: flex; gap: 1.1rem; font-size: 0.88rem; }
    .nav-links a { color: var(--muted); text-decoration: none; }
    .nav-links a:hover { color: var(--text); }
    .hero { margin-bottom: 1.85rem; }
    .hero-kicker {
      display: inline-flex; align-items: center; gap: 0.45rem;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--accent); margin-bottom: 0.8rem;
    }
    .hero-kicker i {
      width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
      box-shadow: 0 0 12px var(--accent); animation: pulse 2s ease infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.35; }
    }
    h1 {
      font-family: Syne, "IBM Plex Sans", sans-serif;
      font-size: clamp(2rem, 4.5vw, 2.65rem);
      font-weight: 800; letter-spacing: -0.04em;
      margin: 0 0 0.65rem; line-height: 1.08;
    }
    .lede {
      margin: 0; max-width: 38rem;
      color: var(--muted); font-size: 1rem; line-height: 1.6;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.25rem;
    }
    .stat {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: 14px;
      padding: 1rem 1.05rem;
      backdrop-filter: blur(12px);
      box-shadow: var(--shadow);
    }
    .stat .label {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.68rem; letter-spacing: 0.06em; text-transform: uppercase;
      color: var(--dim); margin-bottom: 0.35rem;
    }
    .stat .value {
      font-family: Syne, "IBM Plex Sans", sans-serif;
      font-size: 1.45rem; font-weight: 700; letter-spacing: -0.03em;
    }
    .toolbar {
      display: flex; align-items: center; justify-content: space-between;
      gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .chip {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.7rem;
      padding: 0.28rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--glass-border);
      background: rgba(0,0,0,0.22);
      color: var(--muted);
    }
    .meta {
      display: inline-flex; align-items: center; gap: 0.45rem;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.72rem; color: var(--dim);
    }
    .meta .dot {
      width: 6px; height: 6px; border-radius: 50%; background: var(--live);
      box-shadow: 0 0 8px var(--live);
    }
    .meta.err { color: #f0a0a0; }
    .meta.err .dot { background: #f0a0a0; box-shadow: none; }
    .list { display: flex; flex-direction: column; gap: 0.85rem; }
    .card {
      background: var(--glass);
      border: 1px solid var(--glass-border);
      border-radius: var(--card-radius);
      padding: 1.15rem 1.2rem 1.05rem;
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow);
      transition: border-color 0.2s ease, transform 0.2s ease;
    }
    .card:hover {
      border-color: rgba(62,207,191,0.35);
      transform: translateY(-1px);
    }
    .card-top {
      display: flex; justify-content: space-between; gap: 1rem;
      align-items: flex-start; margin-bottom: 0.75rem;
    }
    .name {
      font-family: Syne, "IBM Plex Sans", sans-serif;
      font-size: 1.15rem; font-weight: 700; margin: 0 0 0.2rem;
      letter-spacing: -0.02em;
    }
    .aid {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.72rem; color: var(--dim);
    }
    .badge {
      flex-shrink: 0;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.04em;
      padding: 0.28rem 0.55rem; border-radius: 999px;
      border: 1px solid transparent;
    }
    .badge.live { color: var(--live); border-color: rgba(62,207,142,0.4); background: rgba(62,207,142,0.1); }
    .badge.stale { color: var(--stale); border-color: rgba(224,179,90,0.4); background: rgba(224,179,90,0.1); }
    .badge.offline { color: var(--offline); border-color: rgba(122,141,154,0.35); background: rgba(122,141,154,0.08); }
    .row {
      display: flex; flex-wrap: wrap; gap: 0.75rem 1.25rem;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.75rem; color: var(--muted); margin-bottom: 0.65rem;
    }
    .caps { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    .cap {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.68rem;
      padding: 0.15rem 0.45rem;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.08);
      background: rgba(0,0,0,0.25);
      color: var(--muted);
    }
    .empty {
      text-align: center; padding: 3rem 1.5rem;
      border: 1px dashed var(--glass-border);
      border-radius: var(--card-radius);
      color: var(--muted);
    }
    .empty a.cta {
      display: inline-block; margin-top: 1rem;
      padding: 0.7rem 1.25rem; border-radius: 12px;
      background: var(--accent); color: #041016; font-weight: 600;
      text-decoration: none;
    }
    .empty a.cta:hover { background: var(--accent-2); }
    footer {
      margin-top: 2.5rem; padding-top: 1.25rem;
      border-top: 1px solid var(--glass-border);
      font-size: 0.8rem; color: var(--dim);
      display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem;
      justify-content: space-between;
    }
  </style>
</head>
<body>
  <div class="shell">
    <nav class="nav" aria-label="Site">
      <a class="brand" href="/">AI-<span>Factory</span></a>
      <div class="nav-links">
        <a href="/">Home</a>
        <a href="/monitor/">Monitor</a>
        <a href="/api/agents">JSON</a>
      </div>
    </nav>

    <header class="hero">
      <div class="hero-kicker"><i></i> Live roster</div>
      <h1>Factory agents</h1>
      <p class="lede">
        Autonomous products that keep running after release — they invoke mesh
        capabilities, heartbeat counters here, and show up as the
        <strong style="color:#d5e4ea;font-weight:600">Agents</strong> ball on Alien Monitor.
      </p>
    </header>

    <div class="stats" id="stats" aria-live="polite">__STATS__</div>
    <div class="toolbar">
      <div class="chips" id="chips">__CHIPS__</div>
      <div class="meta" id="meta"><span class="dot"></span><span id="meta-text">__META__</span></div>
    </div>
    <div class="list" id="list" aria-live="polite">__LIST__</div>

    <footer>
      <span>JSON API · <a href="/api/agents">/api/agents</a></span>
      <span>Auto-refreshes every 15s</span>
    </footer>
  </div>

  <script id="boot" type="application/json">__BOOT__</script>
  <script>
(function () {
  const POLL_MS = __POLL_MS__;
  const listEl = document.getElementById("list");
  const statsEl = document.getElementById("stats");
  const chipsEl = document.getElementById("chips");
  const metaEl = document.getElementById("meta");
  const metaText = document.getElementById("meta-text");
  let lastSig = "";
  let lastOkAt = Date.now();

  function money(usd) {
    const n = Number(usd) || 0;
    if (!n) return "$0";
    if (n < 0.01) return "$" + n.toFixed(4);
    return "$" + n.toFixed(2);
  }
  function age(sec) {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    if (s < 60) return s + "s";
    if (s < 3600) return Math.round(s / 60) + "m";
    if (s < 86400) return Math.round(s / 3600) + "h";
    return Math.round(s / 86400) + "d";
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function rank(status) {
    return status === "live" ? 0 : status === "stale" ? 1 : 2;
  }
  function signature(data) {
    const agents = Array.isArray(data.agents) ? data.agents : [];
    const sum = data.summary || {};
    const parts = [
      sum.agents_total, sum.agents_live, sum.invokes_total, sum.spend_usd_total,
      agents.length,
    ];
    for (const a of agents) {
      const st = a.stats || {};
      parts.push(
        a.agent_id, a.status, a.age_sec,
        st.invokes_total, st.spend_usd_total,
        (a.capabilities_used || []).join(",")
      );
    }
    return parts.join("|");
  }
  function render(data) {
    const summary = data.summary || {};
    const agents = Array.isArray(data.agents) ? data.agents.slice() : [];
    agents.sort(function (a, b) {
      const rs = rank(a.status) - rank(b.status);
      if (rs) return rs;
      const sa = Number((a.stats || {}).spend_usd_total || 0);
      const sb = Number((b.stats || {}).spend_usd_total || 0);
      return sb - sa;
    });

    statsEl.innerHTML =
      '<div class="stat"><div class="label">Live</div><div class="value">' +
      esc(summary.agents_live || 0) + "/" + esc(summary.agents_total || agents.length) +
      '</div></div>' +
      '<div class="stat"><div class="label">Invokes</div><div class="value">' +
      esc(Number(summary.invokes_total || 0).toLocaleString()) +
      '</div></div>' +
      '<div class="stat"><div class="label">Spent</div><div class="value">' +
      esc(money(summary.spend_usd_total)) +
      '</div></div>' +
      '<div class="stat"><div class="label">Agents</div><div class="value">' +
      esc(agents.length) +
      '</div></div>';

    const sdks = summary.sdks && typeof summary.sdks === "object" ? summary.sdks : {};
    chipsEl.innerHTML = Object.keys(sdks).map(function (k) {
      return '<span class="chip">' + esc(k) + " · " + esc(sdks[k]) + "</span>";
    }).join("");

    if (!agents.length) {
      listEl.innerHTML =
        '<div class="empty"><p>No agents registered yet.</p>' +
        '<a class="cta" href="/">Start a build</a></div>';
      return;
    }

    listEl.innerHTML = agents.map(function (a) {
      const stats = a.stats || {};
      const status = a.status || "offline";
      const caps = Array.isArray(a.capabilities_used) ? a.capabilities_used : [];
      const pid = a.product_id || "";
      const product = pid
        ? '<a href="/product/' + esc(pid) + '">' + esc(pid) + "</a>"
        : "";
      const pub = a.public_url
        ? '<a href="' + esc(a.public_url) + '" target="_blank" rel="noopener noreferrer">' +
          esc(a.public_url) + "</a>"
        : "";
      return (
        '<article class="card">' +
          '<div class="card-top">' +
            '<div>' +
              '<h2 class="name">' + esc(a.name || a.agent_id || "Agent") + "</h2>" +
              '<div class="aid">' + esc(a.agent_id || "") + "</div>" +
            "</div>" +
            '<span class="badge ' + esc(status) + '">' +
              esc(status) + " · " + esc(age(a.age_sec)) + " ago" +
            "</span>" +
          "</div>" +
          '<div class="row">' +
            (product ? "<span>" + product + "</span>" : "") +
            (a.sdk ? "<span>sdk " + esc(a.sdk) + "</span>" : "") +
            (a.version ? "<span>v" + esc(a.version) + "</span>" : "") +
            "<span>" + esc(Number(stats.invokes_total || 0)) + " invokes</span>" +
            "<span>" + esc(money(stats.spend_usd_total)) + "</span>" +
            (pub ? "<span>" + pub + "</span>" : "") +
          "</div>" +
          (caps.length
            ? '<div class="caps">' +
              caps.slice(0, 12).map(function (c) {
                return '<span class="cap">' + esc(c) + "</span>";
              }).join("") +
              "</div>"
            : "") +
        "</article>"
      );
    }).join("");
  }

  function setMeta(ok, msg) {
    metaEl.classList.toggle("err", !ok);
    metaText.textContent = msg;
  }

  function apply(data, source) {
    const sig = signature(data);
    if (sig !== lastSig) {
      lastSig = sig;
      render(data);
    }
    lastOkAt = Date.now();
    setMeta(true, source === "poll" ? "live · updated just now" : "live · synced");
  }

  async function poll() {
    try {
      const res = await fetch("/api/agents?include_offline=true", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      apply(data, "poll");
    } catch (err) {
      const ago = lastOkAt ? Math.round((Date.now() - lastOkAt) / 1000) + "s ago" : "never";
      setMeta(false, "refresh failed · last ok " + ago);
    }
  }

  try {
    const boot = JSON.parse(document.getElementById("boot").textContent || "{}");
    apply(boot, "boot");
  } catch (e) {
    setMeta(false, "boot parse failed");
  }

  poll();
  setInterval(poll, POLL_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") poll();
  });
})();
  </script>
</body>
</html>
"""
