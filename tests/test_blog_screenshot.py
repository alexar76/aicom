"""Hero capture prefers the live product URL over a sandbox landing."""

from __future__ import annotations

from web.backend.services.blog_screenshot import live_capture_page_urls


def test_canonical_vercel_host_is_first():
    urls = live_capture_page_urls("prod-bdb1634806de")
    assert urls[0] == "https://prod-bdb1634806de.vercel.app/"


def test_capture_uses_the_live_page_when_it_answers(monkeypatch, tmp_path):
    import web.backend.services.blog_screenshot as shot

    monkeypatch.setattr(shot, "blog_asset_path", lambda pid: tmp_path / f"{pid}.webp")
    monkeypatch.setattr(shot, "live_capture_page_urls", lambda pid: ["https://prod-x.vercel.app/"])
    monkeypatch.setattr(shot, "page_answers", lambda url, timeout=15.0: True)

    seen: dict = {}

    def _page(url, pid):
        seen["url"] = url
        seen["pid"] = pid
        return f"/api/blog/assets/{pid}.webp"

    monkeypatch.setattr(shot, "_screenshot_page", _page)

    def _boom(*_a, **_k):
        raise AssertionError("sandbox must not start when the live page answers")

    monkeypatch.setattr(shot, "_post_json", _boom)
    assert shot.capture_blog_hero("prod-x") == "/api/blog/assets/prod-x.webp"
    assert seen["url"] == "https://prod-x.vercel.app/"
