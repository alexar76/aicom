"""Shared chrome for every HTML page the hub serves.

`terminal-home.html` is the design of record for modelmarket.dev: Orbitron/Rajdhani/JetBrains
Mono on a near-black field, cyan→violet accents, glass panels over a nebula. Every other page
(`/developers`, `/examples`, `/plugins/demo`) used to carry its own private Inter + #6c5ce7
stylesheet, so following a link from the home page looked like leaving the site.

This module is the single source for those tokens. `SITE_CSS` is served at `/assets/site.css`
(one cached request shared by all pages) and the two helpers below emit the same nav and footer
everywhere, so a link added here appears on every page instead of on whichever page someone
remembered to edit.
"""

from __future__ import annotations

import os
import re

#: Every page in the site nav: (href, label, key). ``key`` marks the active item.
#: Relative hrefs only — a link to another operator's site does not belong in a nav bar
#: that a stranger is serving under their own domain. Off-site items live in
#: ``ECOSYSTEM_NAV_ITEMS`` and appear only when this deployment IS the reference one.
NAV_ITEMS = (
    ("/", "Live", "live"),
    ("/start", "Start", "start"),
    ("/developers", "Developers", "developers"),
    ("/examples", "Integrate", "examples"),
    ("/studio/", "Studio", "studio"),
    ("/operator", "Operator", "operator"),
    ("/widget/demo", "Widget", "widget"),
    ("/plugins/demo", "Plugins", "plugins"),
)

#: Pages of ``NAV_ITEMS`` this deployment does not ship, set by ``create_app`` once it has looked.
#: operator.html, plugins-demo.html, the widget bundle and the studio build sit BESIDE the package,
#: so a pip-installed hub has none of them — and its nav still linked all four:
#: independentai.network/hub answered three 404s and a 503 from its own header.
MISSING_PAGES: set[str] = set()


def set_missing_pages(hrefs) -> None:
    MISSING_PAGES.clear()
    MISSING_PAGES.update(hrefs)


def drop_missing_links(html: str) -> str:
    """Remove plain links to pages this hub does not serve (labels without markup or quotes,
    so a link assembled inside a script string is left alone)."""
    for href in MISSING_PAGES:
        html = re.sub(r'\s*<a\b[^>]*\bhref="' + re.escape(href) + r'"[^>]*>[^<"\']*</a>', "", html)
    return html


#: Nav items pointing at the reference ecosystem's other properties.
ECOSYSTEM_NAV_ITEMS = (
    ("https://modelmarket.dev/tools/", "Free tools", "tools"),
    ("https://modelmarket.dev/blog/", "Blog", "blog"),
    ("https://edu.modelmarket.dev/", "Learn", "learn"),
    ("https://use.modelmarket.dev/#onboard", "Use cases", "usecases"),
)

#: Who is serving this page. Everything here used to be a literal in the markup, which meant
#: rebranding the hub was a source edit — and a stranger's deployment shipped with another
#: operator's name in the header, that operator's escrow contract in the footer, and links
#: to their satellites in the nav. ``configure`` is called once from ``create_app``.
BRAND: dict[str, object] = {
    "name": "modelmarket.dev",
    "hub_url": "",
    "source_url": "https://github.com/alexar76/aimarket-hub",
    "escrow_url": "",
    "ecosystem_links": True,
}


def configure(
    *,
    name: str = "",
    hub_url: str = "",
    source_url: str = "",
    escrow_url: str = "",
    ecosystem_links: bool | None = None,
) -> None:
    """Point the shared chrome at whoever is actually running this hub."""
    if name:
        BRAND["name"] = name
    if hub_url:
        BRAND["hub_url"] = hub_url.rstrip("/")
    if source_url:
        BRAND["source_url"] = source_url
    BRAND["escrow_url"] = escrow_url or ""
    if ecosystem_links is not None:
        BRAND["ecosystem_links"] = bool(ecosystem_links)

# Served by this app from aimarket_hub/assets/fonts (mounted in api.py), not by Google. The
# preconnect hints that used to sit here went with it: they opened a TLS connection to Google
# on every page load, which is the same disclosure as the font request without the font.
FONTS_LINK = '<link href="/assets/fonts/fonts.css" rel="stylesheet">'

SITE_CSS = """/* modelmarket.dev — shared page chrome. Source: aimarket_hub/theme.py */
:root {
  --bg: #02030a;
  --panel: rgba(8, 14, 30, 0.72);
  --panel-solid: rgba(8, 14, 30, 0.92);
  --brd: rgba(80, 130, 200, 0.22);
  --brd-hot: rgba(56, 224, 255, 0.55);
  --ink: #cfe3ff;
  --muted: #7e9fd0;
  --faint: #56739f;
  --cyan: #38e0ff;
  --violet: #7b5cff;
  --good: #38ffa6;
  --amber: #ffcc4d;
  --pink: #ff5d8a;
  --mono: "JetBrains Mono", ui-monospace, monospace;
  --head: "Orbitron", system-ui, sans-serif;
  --body: "Rajdhani", system-ui, sans-serif;
  --radius: 14px;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: var(--body); font-size: 16px; color: var(--ink);
  background: var(--bg); min-height: 100vh; overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}
.sr-only { position: absolute !important; width: 1px; height: 1px; padding: 0; margin: -1px;
           overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

/* Background layers — the home page paints an animated galaxy behind these; the document
   pages keep the same field without the canvas so they stay cheap to render. */
.nebula {
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    radial-gradient(50vw 50vw at 10% -5%, rgba(56,224,255,0.12), transparent 55%),
    radial-gradient(46vw 46vw at 95% 8%, rgba(123,92,255,0.14), transparent 55%),
    radial-gradient(55vw 55vw at 50% 110%, rgba(255,93,138,0.08), transparent 60%);
  mix-blend-mode: screen;
}
.scan {
  position: fixed; inset: 0; z-index: 1; pointer-events: none; opacity: .32;
  background: repeating-linear-gradient(0deg, rgba(56,224,255,0.035) 0 1px, transparent 1px 3px);
}
.vignette { position: fixed; inset: 0; z-index: 1; pointer-events: none;
            box-shadow: inset 0 0 200px 30px rgba(0,0,0,0.88); }

.shell { position: relative; z-index: 2; max-width: 1180px; margin: 0 auto; padding: 0 20px 56px; }
.shell-wide { max-width: 1320px; }

/* Nav */
nav {
  position: sticky; top: 0; z-index: 100;
  backdrop-filter: blur(14px);
  background: linear-gradient(180deg, rgba(2,3,10,0.92), rgba(2,3,10,0.55));
  border-bottom: 1px solid var(--brd);
}
nav .nav-inner {
  max-width: 1320px; margin: 0 auto; width: 100%; padding: 10px 20px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  min-height: 52px; flex-wrap: wrap;
}
.brand {
  display: inline-flex; align-items: center; gap: 11px; line-height: 1;
  font-family: var(--head); font-weight: 900; letter-spacing: 2px; font-size: 15px;
  text-decoration: none; color: var(--ink);
}
.brand .core {
  width: 13px; height: 13px; border-radius: 50%;
  background: radial-gradient(circle at 32% 30%, #d6fbff, var(--cyan) 45%, var(--violet));
  box-shadow: 0 0 14px var(--cyan), 0 0 34px rgba(123,92,255,.55);
  animation: corepulse 3s ease-in-out infinite;
}
@keyframes corepulse { 0%,100%{ transform: scale(1); } 50%{ transform: scale(1.2); } }
.nav-links { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; }
.nav-links a {
  display: inline-flex; align-items: center; justify-content: center;
  line-height: 1; min-height: 32px;
  color: var(--muted); text-decoration: none; font-family: var(--head);
  font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; font-weight: 600;
  transition: color .2s, text-shadow .2s;
}
.nav-links a:hover { color: var(--cyan); text-shadow: 0 0 12px rgba(56,224,255,.55); }
.nav-links a.on { color: var(--ink); text-shadow: 0 0 14px rgba(56,224,255,.35); }
.nav-live {
  display: inline-flex; align-items: center; gap: 8px;
  color: var(--good) !important; border: 1px solid rgba(56,255,166,.35);
  padding: 6px 12px; border-radius: 999px;
  box-shadow: 0 0 18px rgba(56,255,166,.12) inset;
}
.nav-live:hover { color: var(--good) !important; }
.pip {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--good);
  box-shadow: 0 0 0 0 rgba(56,255,166,.6); animation: ping 2.2s infinite;
}
@keyframes ping {
  0%{ box-shadow:0 0 0 0 rgba(56,255,166,.55);} 70%{ box-shadow:0 0 0 10px rgba(56,255,166,0);}
  100%{ box-shadow:0 0 0 0 rgba(56,255,166,0);}
}

/* Hero */
.hero { padding: 48px 0 26px; }
.hero.center { text-align: center; }
.eyebrow {
  display: inline-flex; align-items: center; gap: 9px; font-family: var(--head);
  font-size: 10.5px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--cyan);
  border: 1px solid var(--brd); background: var(--panel); backdrop-filter: blur(8px);
  padding: 7px 16px; border-radius: 999px; margin-bottom: 20px; text-decoration: none;
}
.eyebrow:hover { border-color: var(--brd-hot); }
.hero h1 {
  font-family: var(--head); font-weight: 900;
  font-size: clamp(32px, 6vw, 64px); line-height: 1.04; letter-spacing: -1px;
  text-shadow: 0 0 50px rgba(56,224,255,.28); margin-bottom: 14px;
}
.grad {
  background: linear-gradient(100deg, var(--cyan), #aef3ff 35%, var(--violet) 88%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.hero .tagline { color: var(--muted); font-size: clamp(15px, 2vw, 19px); max-width: 720px; line-height: 1.5; }
.hero.center .tagline { margin-left: auto; margin-right: auto; }
.hero .tagline a { color: var(--cyan); text-decoration: none; font-weight: 600; }
.hero .tagline a:hover { text-decoration: underline; }
.proto-badges { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 22px; }
.hero.center .proto-badges { justify-content: center; }
.badge {
  font-family: var(--mono); font-size: 11px; letter-spacing: .5px;
  padding: 6px 12px; border-radius: 8px;
  background: var(--panel); border: 1px solid var(--brd); color: var(--muted);
}
.badge strong { color: var(--cyan); }

/* Section headers */
.section { margin-top: 44px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 14px;
                flex-wrap: wrap; margin-bottom: 16px; }
.section-title {
  font-family: var(--head); font-size: 12px; letter-spacing: 2.4px; text-transform: uppercase;
  color: var(--faint);
}
.section-title b { color: var(--cyan); font-weight: 700; }
.section-note { color: var(--muted); font-size: 14px; line-height: 1.55; max-width: 760px; }
.section-note a { color: var(--cyan); text-decoration: none; font-weight: 600; }
.section-note a:hover { text-decoration: underline; }

/* Tabs */
.tabs { display: flex; gap: 4px; flex-wrap: wrap; border-bottom: 1px solid var(--brd); margin-top: 8px; }
.tab {
  background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -1px;
  cursor: pointer; padding: 11px 18px;
  font-family: var(--head); font-size: 11px; letter-spacing: 1.4px; text-transform: uppercase;
  font-weight: 600; color: var(--faint); transition: color .2s, border-color .2s;
}
.tab:hover { color: var(--ink); }
.tab.active { color: var(--cyan); border-bottom-color: var(--cyan); text-shadow: 0 0 14px rgba(56,224,255,.4); }

/* Panels / cards */
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.card {
  background: var(--panel); backdrop-filter: blur(10px);
  border: 1px solid var(--brd); border-radius: var(--radius); padding: 18px;
  display: flex; flex-direction: column; gap: 10px;
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.card:hover { border-color: rgba(56,224,255,.34); box-shadow: 0 10px 40px rgba(0,0,0,.35); }
.card h3 { font-family: var(--head); font-size: 14px; font-weight: 700; letter-spacing: .6px; }
.card p { color: var(--muted); font-size: 14px; line-height: 1.55; }
.card .cat {
  font-family: var(--mono); font-size: 9.5px; color: var(--faint);
  text-transform: uppercase; letter-spacing: 1.2px;
}
.card a, .card a:visited {
  color: var(--cyan); text-decoration: underline; text-underline-offset: 2px;
  text-decoration-thickness: 1px;
}
.card a:hover { color: #9af0ff; text-shadow: 0 0 10px rgba(56,224,255,.35); }
.card a.btn, .card a.btn:visited { text-decoration: none; }
.card-links { margin-top: auto; font-size: 13px; color: var(--faint); }
.card-links a { margin-right: 10px; }
/* A pill is a label, not a banner — in a flex column it would stretch edge to edge. */
.card > .pill { align-self: flex-start; }
/* Snippets inside a card wrap instead of scrolling: a card is too narrow for a scrollbar to
   read as anything but clipped text. Full-width code blocks keep their horizontal scroll. */
.card pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.card.step { border-top: 1px solid rgba(56,224,255,.28); }
.step-n {
  display: inline-flex; align-items: center; gap: 8px;
  font-family: var(--head); font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--violet);
}
.step-n b { color: var(--cyan); font-size: 15px; font-weight: 900; letter-spacing: 1px; }
.pill {
  display: inline-block; font-family: var(--mono); font-size: 9px; letter-spacing: 1px;
  text-transform: uppercase; padding: 3px 8px; border-radius: 999px;
  border: 1px solid var(--brd); color: var(--muted); background: rgba(2,3,10,.5);
}
.pill.live { color: var(--good); border-color: rgba(56,255,166,.34); }
.pill.ready { color: var(--cyan); border-color: rgba(56,224,255,.34); }
.pill.free { color: var(--amber); border-color: rgba(255,204,77,.34); }

code, .mono { font-family: var(--mono); }
p code, td code, li code, .card code {
  font-family: var(--mono); font-size: 12px; color: var(--cyan);
  background: rgba(56,224,255,.08); border: 1px solid rgba(56,224,255,.14);
  padding: 1px 6px; border-radius: 5px;
}
pre {
  position: relative;
  background: rgba(2,3,10,.72); border: 1px solid var(--brd); border-radius: 10px;
  padding: 14px 16px; overflow-x: auto;
  font-family: var(--mono); font-size: 12px; line-height: 1.6; color: var(--ink);
}
pre .c { color: var(--faint); } pre .k { color: var(--violet); }
pre .s { color: var(--good); } pre .n { color: var(--cyan); }
.pre-wrap { position: relative; }
.pre-wrap .copy {
  position: absolute; top: 8px; right: 8px; z-index: 1;
  font-family: var(--mono); font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
  color: var(--faint); background: rgba(2,3,10,.8); border: 1px solid var(--brd);
  border-radius: 6px; padding: 4px 8px; cursor: pointer; opacity: 0; transition: opacity .18s, color .18s;
}
.pre-wrap:hover .copy, .pre-wrap .copy:focus-visible { opacity: 1; }
.pre-wrap .copy:hover { color: var(--cyan); border-color: var(--brd-hot); }
.pre-wrap .copy.done { color: var(--good); border-color: rgba(56,255,166,.4); opacity: 1; }

/* Buttons */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  font-family: var(--head); font-size: 10.5px; letter-spacing: 1.4px; text-transform: uppercase;
  font-weight: 700; padding: 10px 16px; border-radius: 9px; cursor: pointer;
  border: 1px solid transparent; text-decoration: none;
  color: #021018; background: linear-gradient(100deg, var(--cyan), var(--violet));
  transition: filter .2s, transform .2s;
}
.btn:hover { filter: brightness(1.12); transform: translateY(-1px); }
.btn-ghost {
  background: rgba(56,224,255,.07); border-color: var(--brd); color: var(--cyan);
}
.btn-ghost:hover { background: rgba(56,224,255,.16); border-color: var(--brd-hot); }
.btn-row { display: flex; gap: 10px; flex-wrap: wrap; }

/* Stat tiles */
.stats { display: flex; gap: 14px; flex-wrap: wrap; }
.stat {
  background: var(--panel); border: 1px solid var(--brd); border-radius: var(--radius);
  padding: 14px 20px; min-width: 150px;
}
.stat .n { font-family: var(--head); font-size: 28px; font-weight: 900; color: var(--cyan);
           text-shadow: 0 0 24px rgba(56,224,255,.35); }
.stat .l { font-family: var(--mono); font-size: 9.5px; color: var(--faint);
           text-transform: uppercase; letter-spacing: 1.2px; margin-top: 6px; }

/* Tables */
/* A table of paths is wider than a phone; it scrolls inside its own box rather than
   pushing the whole document sideways. */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 12.5px; }
th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--brd); }
th { font-family: var(--head); color: var(--faint); font-weight: 600; text-transform: uppercase;
     font-size: 10px; letter-spacing: 1.4px; }
tbody tr:hover { background: rgba(56,224,255,.04); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 9.5px;
       font-weight: 700; letter-spacing: .8px; font-family: var(--mono); }
.tag-get { background: rgba(56,255,166,.12); color: var(--good); border: 1px solid rgba(56,255,166,.3); }
.tag-post { background: rgba(56,224,255,.12); color: var(--cyan); border: 1px solid rgba(56,224,255,.3); }

/* Footer */
footer {
  position: relative; z-index: 2; max-width: 1320px; margin: 48px auto 0;
  padding: 20px; border-top: 1px solid var(--brd);
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;
  font-family: var(--mono); font-size: 11px; color: var(--faint);
}
footer a { color: var(--cyan); text-decoration: none; }
footer a:hover { text-decoration: underline; }

@media (max-width: 720px) {
  /* Wrapped, the nav grew to three stacked rows and ate the whole first screen. One row
     that scrolls sideways keeps the page below it visible. */
  .nav-inner { gap: 8px; padding: 8px 14px; }
  .nav-links {
    width: 100%; gap: 16px; flex-wrap: nowrap; overflow-x: auto;
    scrollbar-width: none; -webkit-overflow-scrolling: touch;
  }
  .nav-links::-webkit-scrollbar { display: none; }
  .nav-links a { flex: 0 0 auto; font-size: 10px; letter-spacing: 1px; }
  .nav-live { padding: 5px 10px; }
  .hero { padding: 28px 0 18px; }
  .hero .tagline { font-size: 16px; }
  .btn-row .btn { flex: 1 1 auto; }
}
@media (prefers-reduced-motion: reduce) {
  .core, .pip { animation: none !important; }
  .card, .btn { transition: none !important; }
}
"""


#: Adds a hover "copy" button to every ``<pre>`` on the page. The snippets are the point of
#: these pages — a visitor who has to hand-select six lines of shell out of a code block is a
#: visitor who tries one door instead of three.
COPY_JS = """
(function () {
  document.querySelectorAll("pre").forEach(function (pre) {
    if (pre.parentElement && pre.parentElement.classList.contains("pre-wrap")) return;
    var wrap = document.createElement("div");
    wrap.className = "pre-wrap";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy";
    btn.textContent = "copy";
    btn.addEventListener("click", function () {
      var text = pre.innerText;
      var done = function () {
        btn.textContent = "copied";
        btn.classList.add("done");
        setTimeout(function () { btn.textContent = "copy"; btn.classList.remove("done"); }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      }
    });
    wrap.appendChild(btn);
  });
})();
"""


def ga_head_html() -> str:
    """Google tags are not injected. Env leftover is ignored."""
    return ""


def head_html(title: str, description: str) -> str:
    """The `<head>` every page shares — fonts, the one stylesheet, and social cards."""
    return (
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{title}</title>"
        f'<meta name="description" content="{description}">'
        f'<meta property="og:title" content="{title}">'
        f'<meta property="og:description" content="{description}">'
        f"{FONTS_LINK}"
        '<link rel="stylesheet" href="/assets/site.css">'
        f"{ga_head_html()}"
    )


def backdrop_html() -> str:
    """The three fixed background layers the home page uses, minus its animated canvas."""
    return '<div class="nebula"></div><div class="scan"></div><div class="vignette"></div>'


def nav_html(active: str = "") -> str:
    """Site nav. `active` is the key of the current page, from `NAV_ITEMS`."""
    links = []
    items = tuple(NAV_ITEMS)
    if BRAND.get("ecosystem_links"):
        items += ECOSYSTEM_NAV_ITEMS
    for href, label, key in items:
        if href in MISSING_PAGES:
            continue
        if key == "live":
            links.append(
                f'<a class="nav-live" href="{href}"><span class="pip"></span> {label}</a>'
            )
            continue
        cls = ' class="on"' if key == active else ""
        # Another site opens in a new tab; this hub's own pages (the reference deployment's
        # /tools/ is an ecosystem item with an absolute URL) stay in this one.
        own = BRAND.get("hub_url") and href.startswith(f'{BRAND["hub_url"]}/')
        ext = ' target="_blank" rel="noopener"' if href.startswith("http") and not own else ""
        links.append(f'<a href="{href}"{cls}{ext}>{label}</a>')
    if BRAND.get("source_url"):
        links.append(
            f'<a href="{BRAND["source_url"]}" target="_blank" rel="noopener">Source</a>'
        )
    return (
        "<nav><div class=\"nav-inner\">"
        f'<a class="brand" href="/"><span class="core"></span> {BRAND["name"]}</a>'
        f'<div class="nav-links">{"".join(links)}</div>'
        "</div></nav>"
    )


def footer_html() -> str:
    """The footer names THIS operator's contract, or none.

    It used to hard-code one escrow address on Basescan. On anyone else's deployment that is
    a link to a stranger's contract presented as the page's own settlement proof, which is
    worse than having no link at all — so it is emitted only when this hub actually has an
    escrow configured.
    """
    left = [
        "AIMarket Protocol v2",
        '<a href="/developers">API docs</a>',
        '<a href="/examples">Integration</a>',
        # On every hub's every page: the way to the next hub (hubs_page.py).
        '<a href="/hubs#run-your-own">Hubs · run your own</a>',
    ]
    if BRAND.get("ecosystem_links"):
        left.append('<a href="https://modelmarket.dev/tools/">Free x402 and MCP checks</a>')
        left.append('<a href="https://modelmarket.dev/blog/">Blog</a>')
        left.append(
            '<a href="https://use.modelmarket.dev/#onboard" target="_blank" rel="noopener">'
            "Use cases</a>"
        )
    if BRAND.get("escrow_url"):
        left.append(
            f'<a href="{BRAND["escrow_url"]}" target="_blank" rel="noopener">Escrow (Basescan)</a>'
        )
    right = []
    if BRAND.get("source_url"):
        right.append(
            f'<a href="{BRAND["source_url"]}" target="_blank" rel="noopener">Source</a> · '
        )
    return (
        "<footer>"
        f"<div>{' · '.join(left)}</div>"
        f'<div>{"".join(right)}<a href="/.well-known/ai-market.json">Discovery manifest</a></div>'
        "</footer>"
    )


def apply_shell(html: str, title: str, description: str, active: str = "") -> str:
    """Fill the chrome placeholders in a static page served by the hub.

    `plugins-demo.html` is a real file (it is easier to work on a playground you can open in an
    editor than one that lives inside a Python string), but its nav and footer must be the same
    ones every other page shows. It carries `<!--HEAD-->`, `<!--BACKDROP-->`, `<!--NAV-->` and
    `<!--FOOTER-->` markers, and this fills them in on the way out. Opened straight from disk the
    markers stay inert HTML comments, so the file is still readable without the hub.
    """
    return drop_missing_links(
        html.replace("<!--HEAD-->", head_html(title, description))
        .replace("<!--BACKDROP-->", backdrop_html())
        .replace("<!--NAV-->", nav_html(active))
        .replace("<!--FOOTER-->", footer_html())
    )
