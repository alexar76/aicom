"""a11y_missing_h1 stayed red on a page whose React tree already had an h1.

The check downloaded the URL with urllib. FastAPI serves the Vite shell
(`<div id="root"></div>`, no heading). Playwright had already hydrated
PublicWidget — visible text "Sentinel … Get Safety Status", and the source
of that page is `<h1>Sentinel</h1>`. A gate that looks at the shell cannot
be satisfied by editing the component, and editing the shell is wiped on
hydrate.
"""

from pathlib import Path

E2E = (
    Path(__file__).resolve().parents[1]
    / "web"
    / "backend"
    / "services"
    / "browser_preview_e2e.py"
).read_text(encoding="utf-8")


def test_a11y_reads_the_hydrated_dom_not_urllib():
    a11y = E2E[E2E.index("Basic a11y checks") :]
    assert "urlopen" not in a11y
    assert "landing_html" in a11y
    assert "page.content()" in E2E
    assert "spa_routes_from_source" in E2E
    assert "seed_urls=seed_urls" in E2E
    assert "page.evaluate" in a11y
    assert "a11y_preview_served_api_json" in a11y
    assert "document.querySelector('h1')" in a11y