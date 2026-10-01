"""The deep-crawl gate must fail a page whose content does not fit its boxes.

A generated landing shipped with its section icons cut in half by the squares they
sat in. Every gate passed it: HTTP 200, unchanged text snippet, a passing quality
score. Screenshots were captured, but the reviewer that reads them is a text-only
LLM handed their file PATHS. Nothing measured the rendered page, so nothing could
have seen it.
"""

from __future__ import annotations

from web.backend.services.browser_e2e_deep import deep_crawl_gate_issues


def _summary(layout: dict | None, *, url: str = "http://x/") -> dict:
    page: dict = {"url": url, "status": 200, "text_snippet": "NightCircuit"}
    if layout is not None:
        page["layout"] = layout
    return {"pages": [page], "navigation_failures": [], "loopback_hrefs": []}


def test_clipped_content_fails_the_gate():
    issues = deep_crawl_gate_issues(
        _summary({
            "clipped": [{"tag": "div", "cls": "feature-icon", "overflow_px": 14,
                         "box_px": 64, "text": "REAL-TIME MONITORING"}],
            "page_overflow_px": 0,
        })
    )
    clipped = [i for i in issues if i.startswith("deep_layout_clipped:")]
    assert len(clipped) == 1
    # The message has to name the box and the amount, or whoever picks it up cannot
    # tell a 2px rounding artefact from an icon sliced in half.
    assert "feature-icon" in clipped[0]
    assert "64px" in clipped[0] and "14px" in clipped[0]
    # And it must not suggest the fix that hides the defect.
    assert "do not add overflow:hidden" in clipped[0]


def test_a_page_that_scrolls_sideways_fails_the_gate():
    issues = deep_crawl_gate_issues(_summary({"clipped": [], "page_overflow_px": 37}))
    assert any(i.startswith("deep_layout_page_overflow:") and "37px" in i for i in issues)


def test_sub_pixel_rounding_is_not_a_defect():
    """Fractional layout maths must not fail somebody's build."""
    assert deep_crawl_gate_issues(_summary({"clipped": [], "page_overflow_px": 2})) == []


def test_a_clean_page_produces_nothing():
    assert deep_crawl_gate_issues(_summary({"clipped": [], "page_overflow_px": 0})) == []


def test_a_page_crawled_before_this_check_existed_is_not_a_failure():
    """Old reports have no `layout` key; they must not start failing retroactively."""
    assert deep_crawl_gate_issues(_summary(None)) == []


def test_one_page_cannot_flood_the_report():
    many = [{"tag": "p", "cls": f"c{i}", "overflow_px": 9, "box_px": 100, "text": "x"}
            for i in range(20)]
    issues = deep_crawl_gate_issues(_summary({"clipped": many, "page_overflow_px": 0}))
    assert len([i for i in issues if i.startswith("deep_layout_clipped:")]) == 6
