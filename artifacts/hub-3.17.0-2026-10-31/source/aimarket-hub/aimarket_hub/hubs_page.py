"""`/hubs` — the federation as this hub sees it, readable by a person, and the way in.

The JSON was always public (`/ai-market/v2/federation/peers`) and the LIVE map draws every hub
as a planet, but there was no page a person could read or share that answered "who runs a hub,
and how do I run one". Every hub serves this page, so every hub is also a signpost to the next
one — the way a federated server links "run your own".

Everything in the tables was written by somebody else: names, versions and addresses are a
peer's claims, so all of it is escaped, and an address becomes a link only when it is http(s).
"""

from __future__ import annotations

import html
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlparse

from aimarket_hub import __version__

_CSS = """
<style>
  .hubs { max-width: 980px; margin: 0 auto; }
  .hubs table { width: 100%; border-collapse: collapse; font-size: 14px; }
  .hubs th, .hubs td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--brd);
                       vertical-align: top; overflow-wrap: anywhere; }
  .hubs th { font-family: var(--mono); font-size: 11px; letter-spacing: .8px; color: var(--faint);
             text-transform: uppercase; }
  .hubs .mono { font-family: var(--mono); font-size: 12.5px; }
  .hubs .ok { color: var(--good); } .hubs .bad { color: var(--pink); } .hubs .mid { color: var(--amber); }
  .hubs pre { font-family: var(--mono); font-size: 12.5px; white-space: pre-wrap; overflow-wrap: anywhere;
              background: rgba(2,3,10,.6); border: 1px solid var(--brd); border-radius: 9px; padding: 12px; }
  .hubs .card { margin-top: 18px; }
  .hubs .scroll { overflow-x: auto; }
  .hubs td:last-child { white-space: nowrap; }
</style>
"""


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _link(url: str, text: str | None = None) -> str:
    url = str(url or "").strip()
    label = _e(text if text is not None else url)
    if urlparse(url).scheme in ("http", "https"):
        return f'<a href="{_e(url)}" target="_blank" rel="noopener nofollow">{label}</a>'
    return label


def _verdict(verdict: str | None) -> str:
    v = str(verdict or "").strip()
    cls = {"pass": "ok", "fail": "bad", "review": "mid"}.get(v, "")
    return f'<span class="{cls}">{_e(v or "—")}</span>'


def render(
    *,
    hub_name: str,
    hub_url: str,
    source_url: str,
    peers: Iterable[Any],
    pending: Iterable[Any],
    own_count: Callable[[str], int],
    assay: Callable[[str], dict | None],
) -> str:
    """The page body, with the shell markers `apply_shell` fills in."""
    rows = []
    for p in peers:
        status = str(getattr(p, "status", "") or "")
        key = ('<span class="bad">key changed — refused</span>' if status == "key_mismatch"
               else '<span class="ok">pinned</span>')
        rows.append(
            "<tr>"
            f"<td>{_e(getattr(p, 'name', '') or getattr(p, 'url', ''))}</td>"
            f'<td class="mono">{_link(getattr(p, "url", ""))}</td>'
            f'<td class="mono">{_e(getattr(p, "hub_version", "") or "—")}</td>'
            f'<td class="mono">{_e(own_count(getattr(p, "url", "")))}</td>'
            f'<td class="mono">{_e((getattr(p, "last_crawl", "") or "")[:16].replace("T", " ") or "—")}</td>'
            f"<td>{key}</td>"
            "</tr>"
        )
    knocking = []
    for p in pending:
        url = str(getattr(p, "url", "") or "")
        dossier = assay(url) or {}
        knocking.append(
            "<tr>"
            f'<td class="mono">{_link(url)}</td>'
            f'<td class="mono">{_e((getattr(p, "first_seen", "") or "")[:10] or "—")}</td>'
            f"<td>{_verdict(dossier.get('verdict'))} "
            f'<a class="mono" href="/ai-market/v2/federation/assay?url={quote(url, safe="")}">dossier</a></td>'
            "</tr>"
        )
    source = str(source_url or "https://github.com/alexar76/aimarket-hub").rstrip("/")
    guide = f"{source}/blob/main/docs/operator-quickstart.md"
    platforms = f"{source}/blob/main/docs/run-on-a-platform.md"
    node_guide = f"{source}/blob/main/docs/run-a-node.md"
    admitted_table = (
        '<div class="scroll"><table><thead><tr><th>Name (their claim)</th><th>Address</th>'
        "<th>Version</th><th>Indexed here</th><th>Last crawl (UTC)</th><th>Key</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        if rows else "<p>No admitted peers yet.</p>"
    )
    knocking_table = (
        '<div class="scroll"><table><thead><tr><th>Address</th><th>First seen</th>'
        f"<th>Admission</th></tr></thead><tbody>{''.join(knocking)}</tbody></table></div>"
        if knocking else "<p>Nobody is waiting.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<!--HEAD-->
{_CSS}
</head>
<body>
<!--BACKDROP-->
<!--NAV-->
<div class="shell">
<div class="hubs">
  <header class="hero center">
    <div class="eyebrow"><span class="pip"></span> Federation</div>
    <h1>Hubs</h1>
    <p class="tagline">Who {_e(hub_name)} knows, who is knocking, and how to run a hub of your own.
    Admission is decided by a sandbox that runs a hub's own capabilities, not by anyone's say-so.</p>
  </header>

  <section class="card">
    <h3>This hub</h3>
    <p class="mono">{_e(hub_name)} · {_link(hub_url)} · aimarket-hub {_e(__version__)}</p>
  </section>

  <section class="card">
    <h3>Admitted</h3>
    {admitted_table}
    <p class="small">“Indexed here” counts only what each peer sells itself; re-exports are not
    indexed twice. Machine-readable: <a class="mono" href="/ai-market/v2/federation/peers">/ai-market/v2/federation/peers</a></p>
  </section>

  <section class="card">
    <h3>Knocking</h3>
    {knocking_table}
  </section>

  <section class="card" id="run-your-own">
    <h3>Run your own hub</h3>
    <pre>pip install "aimarket-hub[pqc]"          # Python 3.11+
aimarket quickstart --name "My hub"
aimarket serve
aimarket add my.api@v1 --url https://api.example.com/run --price 0.01 --pay-to 0x…
aimarket doctor --url https://your-hub.example</pre>
    <p>Your own API, sold seller-direct to your wallet, with MCP, x402, A2A and signed receipts
    from one command; a free <span class="mono">hub.ping@v1</span> for other hubs' admission
    sandbox; then one <span class="mono">curl</span> to knock.
    <a href="{_e(guide)}" target="_blank" rel="noopener">The whole path</a> ·
    <a href="{_e(platforms)}" target="_blank" rel="noopener">Railway, Render, Fly</a> ·
    <a href="{_e(source)}" target="_blank" rel="noopener">Source</a></p>
    <p><b>Already run an API?</b> <span class="mono">aimarket node</span> makes it a node without a
    hub — signed documents and receipts beside your routes, x402 passed through as it is.
    <a href="{_e(node_guide)}" target="_blank" rel="noopener">Run a node</a></p>
    <p><b>No server at all?</b> Sell one Python function from a hosted sandbox; buyers pay your
    wallet. <a href="https://github.com/alexar76/hestia/blob/main/docs/sell-without-a-server.md"
    target="_blank" rel="noopener">Sell without a server</a></p>
  </section>
</div>
</div>
<!--FOOTER-->
</body>
</html>
"""
