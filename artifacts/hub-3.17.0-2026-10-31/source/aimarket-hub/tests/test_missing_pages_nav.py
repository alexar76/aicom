"""A hub links only the pages it ships.

operator.html, plugins-demo.html, the widget bundle and the studio build sit beside the package,
so a pip-installed hub has none of them; its nav linked all four anyway (three 404s and a 503 on
independentai.network/hub).
"""

from aimarket_hub import landing, theme


def _with_missing(hrefs, fn):
    saved = set(theme.MISSING_PAGES)
    theme.set_missing_pages(hrefs)
    try:
        return fn()
    finally:
        theme.set_missing_pages(saved)


def test_nav_leaves_out_pages_that_are_not_shipped():
    nav = _with_missing({"/operator", "/studio/"}, lambda: theme.nav_html("live"))
    assert 'href="/operator"' not in nav and 'href="/studio/"' not in nav
    assert 'href="/widget/demo"' in nav and 'href="/developers"' in nav


def test_pages_drop_plain_links_but_not_script_strings():
    html = (
        '<p>See <a class="btn" href="/widget/demo">Widget gallery</a> and '
        '<a href="/examples">Embed snippet</a>.</p>'
        "<script>x = '<a href=\"/widget/demo\">' + label + '</a>';</script>"
    )
    out = _with_missing({"/widget/demo"}, lambda: theme.drop_missing_links(html))
    assert "Widget gallery" not in out and 'href="/examples"' in out
    assert "x = '<a href=\"/widget/demo\">' + label" in out


def test_developer_pages_follow_the_same_rule():
    page = _with_missing({"/widget/demo", "/plugins/demo"},
                         lambda: landing.integration_examples_html("https://hub.example"))
    assert 'href="/widget/demo"' not in page and 'href="/plugins/demo"' not in page


def test_a_hub_with_every_page_changes_nothing():
    html = '<a href="/operator">Operator</a>'
    assert _with_missing(set(), lambda: theme.drop_missing_links(html)) == html


def test_the_app_itself_drops_what_it_did_not_ship(monkeypatch, tmp_path):
    """The developer pages are rendered inside create_app before the missing set is known —
    the unit tests above passed while /developers still linked the absent widget gallery."""
    import os
    import re

    from fastapi.testclient import TestClient

    from aimarket_hub import api
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    real_isfile = os.path.isfile
    monkeypatch.setattr(api.os.path, "isfile",
                        lambda p: False if str(p).endswith(("operator.html", "plugins-demo.html"))
                        else real_isfile(p))
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = api.create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    try:
        with TestClient(app) as client:
            for page in ("/", "/developers", "/examples"):
                # Markup only: the home page's knock queue assembles its operator link in script.
                body = re.sub(r"<script\b.*?</script>", "", client.get(page).text, flags=re.S)
                assert 'href="/operator"' not in body and 'href="/plugins/demo"' not in body, page
            assert 'href="/developers"' in client.get("/").text
    finally:
        theme.set_missing_pages(())


def test_a_hub_without_the_terminal_home_serves_the_developer_page(monkeypatch, tmp_path):
    """terminal-home.html sits beside the package, so an installed wheel has none. The home
    page fell back to a DOCS_HTML constant that no longer existed: a NameError, so "/" was a
    500 on every pip-installed hub."""
    import os

    from fastapi.testclient import TestClient

    from aimarket_hub import api
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    real_isfile = os.path.isfile
    monkeypatch.setattr(api.os.path, "isfile",
                        lambda p: False if str(p).endswith("terminal-home.html") else real_isfile(p))
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = api.create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    try:
        with TestClient(app) as client:
            home = client.get("/")
            assert home.status_code == 200
            assert home.text == client.get("/developers").text
    finally:
        theme.set_missing_pages(())
