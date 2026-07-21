"""Unit tests for browser deep-crawl URL helpers (no Playwright)."""

from web.backend.services.browser_e2e_deep import (
    deep_crawl_gate_issues,
    is_loopback_href,
    normalize_visit_key,
    same_origin,
)


def test_same_origin_port():
    assert same_origin("http://127.0.0.1:9123/a.html", "http://127.0.0.1:9123/b.html")
    assert not same_origin("http://127.0.0.1:9123/a.html", "http://127.0.0.1:9124/a.html")


def test_normalize_visit_key_fragment():
    a = normalize_visit_key("http://127.0.0.1:5/page.html#faq")
    b = normalize_visit_key("http://127.0.0.1:5/page.html#pricing")
    assert a != b


def test_is_loopback_href():
    assert is_loopback_href("//localhost/foo")
    assert is_loopback_href("http://localhost:3000/")
    assert not is_loopback_href("./foo.html")
    assert not is_loopback_href("#faq")


def test_deep_crawl_gate_issues_http():
    issues = deep_crawl_gate_issues(
        {
            "navigation_failures": [],
            "loopback_hrefs": [],
            "pages": [{"url": "http://x/y", "status": 404}],
        }
    )
    assert any("deep_http_404" in i for i in issues)
