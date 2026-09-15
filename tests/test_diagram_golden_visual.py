"""
Golden PNG regression for diagram-heavy HTML (Playwright render vs committed baseline).

Generate / refresh baseline::
    pip install playwright pillow
    playwright install chromium
    python scripts/update_diagram_golden_png.py

CI / local run::
    export AIFACTORY_DIAGRAM_GOLDEN=1
    pytest tests/test_diagram_golden_visual.py -q
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "diagram_ok.html"
GOLDEN = Path(__file__).resolve().parent / "golden" / "diagram_ok.png"

pytestmark = pytest.mark.skipif(
    os.environ.get("AIFACTORY_DIAGRAM_GOLDEN", "").strip().lower() not in ("1", "true", "yes"),
    reason="Set AIFACTORY_DIAGRAM_GOLDEN=1 to run (requires playwright browsers + golden PNG)",
)


def _mean_abs_pixel_diff(a_png: bytes, b_png: bytes) -> float:
    from PIL import Image

    a = Image.open(io.BytesIO(a_png)).convert("RGB")
    b = Image.open(io.BytesIO(b_png)).convert("RGB")
    if a.size != b.size:
        a = a.resize(b.size, Image.Resampling.LANCZOS)
    w, h = a.size
    total = 0.0
    count = 0
    for y in range(h):
        for x in range(w):
            xa = a.getpixel((x, y))
            xb = b.getpixel((x, y))
            total += abs(xa[0] - xb[0]) + abs(xa[1] - xb[1]) + abs(xa[2] - xb[2])
            count += 1
    if count == 0:
        return 1.0
    return total / (count * 3 * 255.0)


@pytest.fixture(scope="module")
def chromium_page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as sp:
        browser = sp.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 640, "height": 480})
        yield page
        browser.close()


def test_diagram_fixture_matches_golden_png(chromium_page):
    if not GOLDEN.is_file():
        pytest.skip(f"Missing {GOLDEN} — run scripts/update_diagram_golden_png.py")

    uri = FIXTURE.resolve().as_uri()
    chromium_page.goto(uri, wait_until="domcontentloaded", timeout=30_000)
    chromium_page.wait_for_timeout(400)
    shot = chromium_page.screenshot(full_page=False)

    expected = GOLDEN.read_bytes()
    diff = _mean_abs_pixel_diff(shot, expected)

    assert diff <= 0.11, (
        f"diagram render drift mean_abs_diff={diff:.4f} > 0.11 — inspect fixture/UI or run "
        "DIAGRAM_GOLDEN_UPDATE=1 python scripts/update_diagram_golden_png.py"
    )
