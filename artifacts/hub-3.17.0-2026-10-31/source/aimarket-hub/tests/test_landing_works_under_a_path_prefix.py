"""The landing must localise when the hub is mounted under a path prefix.

`independentai.network/hub/` runs the same hub, and its whole UI rendered as raw keys —
NAV_DEVS, S_INV, PENDING_TITLE, ASSAY_FAIL — because the page fetched the dictionary from
the absolute `/hub-ui-i18n.json`. Under a prefix that is a 404, the fetch fails, and every
`data-i18n` element keeps its placeholder. It was invisible on modelmarket.dev, which serves
the hub at the apex where the absolute path happens to resolve — a bug only the second
deployment could show.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "terminal-home.html"


def _page() -> str:
    return PAGE.read_text(errors="ignore")


def _code_only() -> str:
    """The page with // comments blanked.

    Without this the assertions match the old path quoted in the comment that explains the
    fix — a source-inspection test passing or failing on its own prose. Block comments and
    URLs are left alone: only a `//` that starts a line is a comment here.
    """
    out = []
    for line in _page().splitlines():
        out.append("" if line.lstrip().startswith("//") else line)
    return "\n".join(out)


def test_the_dictionary_is_not_fetched_from_the_site_root():
    assert "'/hub-ui-i18n.json'" not in _code_only(), (
        "an absolute path 404s for every hub mounted under a prefix, and the page then "
        "renders its i18n keys instead of text"
    )


def test_the_dictionary_is_resolved_against_the_document():
    t = _page()
    assert "new URL('hub-ui-i18n.json', document.baseURI)" in t, (
        "resolve the dictionary against document.baseURI so it works at the apex and under "
        "a prefix alike"
    )


def test_no_other_same_origin_asset_is_pinned_to_the_root():
    """Any other absolute-root asset would break the same way under a prefix.

    The API paths are deliberately excluded: those are proxied at the root on every
    deployment we run, and are verified separately.
    """
    t = _code_only()
    absolute = set(re.findall(r"""fetchJson\(\s*['"](/[^'"]+)['"]""", t))
    absolute |= set(re.findall(r"""fetch\(\s*['"](/[^'"]+)['"]""", t))
    offenders = sorted(
        p for p in absolute
        if not p.startswith(("/ai-market/", "/api/", "/.well-known/"))
    )
    assert not offenders, (
        f"these are pinned to the site root and would 404 under a path prefix: {offenders}"
    )


def test_every_data_i18n_key_the_page_uses_exists_in_the_dictionary():
    """The other way this renders as keys: a template key with no translation."""
    import json

    dictionary = json.loads((PAGE.parent / "hub-ui-i18n.json").read_text())
    ui = dictionary.get("ui") or {}
    en = ui.get("en") or {}
    used = set(re.findall(r'data-i18n(?:-html)?="([a-z0-9_]+)"', _page()))
    assert used, "no data-i18n keys found — the scan is looking at the wrong markup"
    missing = sorted(used - set(en))
    assert not missing, f"used in the page but absent from ui.en: {missing}"


# ── White-labelling ─────────────────────────────────────────────────────────────────────

def test_a_third_party_hub_does_not_show_our_brand(tmp_path, monkeypatch):
    """`independentai.network/hub/` rendered OUR wordmark in the hero, twice the size of its
    own name, and its tab title said modelmarket.dev.

    Two separate leaks. The hero wordmark is split across spans —
    `<span class="grad">model</span>market<span class="grad">.dev</span>` — so it survived
    every brand rewrite. And the client-side translator sets document.title from the
    dictionary, whose `page_title` carries the reference brand, so the page re-branded itself
    back a moment after loading and undid the server's <title> rewrite.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "wl.db"))
    monkeypatch.setenv("AIMARKET_HUB_NAME", "Independent AI Hub")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://independentai.network/hub")

    from aimarket_hub.api import create_app

    html = TestClient(create_app()).get("/").text

    assert "<title>Independent AI Hub — AI Economy Protocol</title>" in html
    assert '<h1 id="hero-brand"><span class="grad">Independent AI Hub</span></h1>' in html, (
        "the hero still carries the reference wordmark"
    )
    assert 'window.__HUB_BRAND = "Independent AI Hub";' in html, (
        "the client-side title would re-brand the page back from the dictionary"
    )
    assert '<span class="grad">model</span>market' not in html, "split wordmark survived"


def test_the_reference_deployment_is_untouched(tmp_path, monkeypatch):
    """modelmarket.dev must keep its own wordmark exactly as designed."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "ref.db"))
    monkeypatch.setenv("AIMARKET_HUB_NAME", "modelmarket.dev")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://modelmarket.dev")

    from aimarket_hub.api import create_app

    html = TestClient(create_app()).get("/").text
    assert '<span class="grad">model</span>market<span class="grad">.dev</span>' in html
    assert 'window.__HUB_BRAND = "modelmarket.dev";' in html


def test_every_stylesheet_the_landing_links_is_served(monkeypatch, tmp_path):
    """Fetch the served page's stylesheets and the fonts inside them, as a browser would.

    The self-hosted fonts were linked as `fonts/fonts.css`: relative, which is right under a
    prefix, but aimed at a copy beside the source file that no route serves. Every hub drew
    its landing in fallback faces behind a 404 while the source checks above all passed.
    A relative href resolves the same at the apex and under a prefix the proxy strips, so
    checking it against `/` covers both.
    """
    from urllib.parse import urljoin

    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        page = client.get("/").text
        links = [tag for tag in re.findall(r"<link\b[^>]*>", page) if 'rel="stylesheet"' in tag]
        hrefs = [re.search(r'href="([^"]+)"', tag).group(1) for tag in links]
        local = [h for h in hrefs if not h.startswith(("http://", "https://", "//"))]
        assert local, "the landing links no stylesheet of its own — the scan is reading the wrong page"
        for href in local:
            assert not href.startswith("/"), f"{href} is pinned to the site root and 404s under a prefix"
            css = client.get(urljoin("/", href))
            assert css.status_code == 200, f"{href} -> {css.status_code}"
            assert "text/css" in css.headers.get("content-type", ""), f"{href} is not served as CSS"
            fonts = sorted(set(re.findall(r"url\(\s*['\"]?([^'\")]+\.woff2)", css.text)))
            if "fonts" in href:
                assert fonts, f"{href} names no .woff2 face — the page would fall back silently"
            for font in fonts:
                got = client.get(urljoin(urljoin("/", href), font))
                assert got.status_code == 200, f"font {font} from {href} -> {got.status_code}"


# ── A dictionary that does not arrive ───────────────────────────────────────────────────
#
# On 2026-10-24 modelmarket.dev showed its tab as "page_title" and the page as NAV_WIDGET,
# SEARCH_BTN, badge_federation, S_CAPS: the dictionary fetch had failed (it had 4 s), the
# loader then installed an empty dictionary, and t() fell back to the KEY, overwriting the
# English the server had already rendered.

def test_the_served_page_carries_english_inline(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    monkeypatch.setenv("AIMARKET_DB_PATH", str(tmp_path / "en.db"))
    monkeypatch.setenv("AIMARKET_HUB_NAME", "modelmarket.dev")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://modelmarket.dev")

    from aimarket_hub.api import create_app

    html = TestClient(create_app()).get("/").text
    m = re.search(r'<script type="application/json" id="hub-ui-en">(.*?)</script>', html, re.S)
    assert m, "no inline English dictionary"
    inline = json.loads(m.group(1))
    en = json.loads((PAGE.parent / "hub-ui-i18n.json").read_text())["ui"]["en"]
    assert inline == en
    assert inline["page_title"] and inline["nav_widget"] and inline["s_caps"]


def _t_under_node(prelude: str, calls: list) -> list:
    import json
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node not installed")
    match = re.search(r"^  function t\(.*?^  }$", _page(), re.S | re.M)
    assert match, "t() not found in terminal-home.html"
    script = (prelude + "\n" + match.group(0) + "\nconsole.log(JSON.stringify(["
              + ",".join(calls) + "]));")
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_no_dictionary_means_english_not_keys():
    # No fetched dictionary, no inline pack (a page served as a bare file): the markup's own
    # text is what shows.
    got = _t_under_node(
        "let UI = null; let hubLang = 'ru'; const UI_EN = {};",
        ["t('nav_widget', null, 'Widget')", "t('page_title', null, 'Hub — AI Economy')"],
    )
    assert got == ["Widget", "Hub — AI Economy"]


def test_inline_english_covers_strings_made_at_run_time():
    got = _t_under_node(
        "let UI = null; let hubLang = 'fr'; const UI_EN = {conn_connecting: 'Connecting…'};",
        ["t('conn_connecting')"],
    )
    assert got == ["Connecting…"]


def test_a_loaded_dictionary_still_wins():
    got = _t_under_node(
        "let UI = {ru: {nav_widget: 'Виджет'}, en: {nav_widget: 'Widget'}}; let hubLang = 'ru';"
        " const UI_EN = {nav_widget: 'Widget'};",
        ["t('nav_widget', null, 'Widget')"],
    )
    assert got == ["Виджет"]


def test_a_failed_load_never_installs_an_empty_dictionary():
    code = _code_only()
    assert "UI = { en: {} }" not in code, (
        "an empty dictionary makes every lookup miss, and the page turns into its keys"
    )
