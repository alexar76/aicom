"""Tests for Marketing-agent launch blog posts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.paths import blog_index_path, blog_posts_dir
from web.backend.services.product_blog import (
    build_launch_post,
    get_blog_post,
    publish_product_launch_blog_post,
    update_blog_post,
)


@pytest.fixture
def blog_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("web.backend.services.product_blog.blog_posts_dir", lambda: tmp_path / "blog" / "posts")
    monkeypatch.setattr("web.backend.services.product_blog.blog_index_path", lambda: tmp_path / "blog" / "index.json")
    monkeypatch.setattr(
        "web.backend.services.product_blog.marketing_content_path",
        lambda pid: state / pid / "marketing_content.json",
    )
    return state


def _write_marketing(state: Path, product_id: str, marketing: dict) -> None:
    d = state / product_id
    d.mkdir(parents=True)
    (d / "marketing_content.json").write_text(
        json.dumps({"marketing": marketing}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_build_launch_post_from_marketing_blog_block(blog_env: Path):
    pid = "prod-test-01"
    _write_marketing(
        blog_env,
        pid,
        {
            "product_name": "Nebula Desk",
            "tagline": "Calm focus for noisy teams",
            "short_description": "A tiny desk ritual app.",
            "blog_post": {
                "title": "Launch: Nebula Desk — calm focus rituals",
                "excerpt": "Shipped a minimalist focus timer with team-aware quiet hours.",
                "read_time_minutes": 7,
                "tags": ["product launch", "productivity"],
                "body": [
                    {"type": "p", "text": "We shipped Nebula Desk for teams drowning in notification debt."},
                    {"type": "h2", "text": "What landed"},
                    {"type": "ul", "items": ["Quiet hours", "Focus sessions", "Team presence strip"]},
                ],
            },
        },
    )
    post = build_launch_post(pid, product={"idea": "focus app"})
    assert post is not None
    assert post["slug"] == "launch-prod-test-01"
    assert post["author"] == "AI-Factory Marketing"
    assert any(b.get("type") == "product_link" for b in post["body"])


def test_publish_writes_files(blog_env: Path):
    pid = "prod-ship-99"
    _write_marketing(
        blog_env,
        pid,
        {
            "product_name": "Pulse Relay",
            "long_description": "Webhook inbox for developers.",
            "key_benefits": ["Search", "Replay", "Retention defaults"],
        },
    )
    assert publish_product_launch_blog_post(pid, product={"idea": "webhooks"}, capture_screenshot=False)
    slug = "launch-prod-ship-99"
    post_file = blog_posts_dir() / f"{slug}.json"
    assert post_file.is_file()
    index = json.loads(blog_index_path().read_text(encoding="utf-8"))
    assert any(p["slug"] == slug for p in index["posts"])


def test_screenshot_token_and_include_flag(blog_env: Path):
    pid = "prod-visual-01"
    _write_marketing(
        blog_env,
        pid,
        {
            "product_name": "Canvas Flow",
            "blog_post": {
                "title": "Launch: Canvas Flow",
                "excerpt": "Visual workflow builder.",
                "include_screenshot": True,
                "screenshot_caption": "Hero landing preview",
                "body": [
                    {"type": "p", "text": "We shipped Canvas Flow."},
                    {"type": "img", "src": "__FACTORY_SCREENSHOT__", "alt": "Canvas Flow"},
                ],
            },
        },
    )
    post = build_launch_post(pid, capture_screenshot=False)
    assert post is not None
    imgs = [b for b in post["body"] if b.get("type") == "img"]
    assert len(imgs) == 1
    assert imgs[0]["src"].endswith(f"{pid}.webp")
    assert imgs[0].get("caption") == "Hero landing preview"


def test_screenshot_defaults_on_unless_marketing_opts_out(blog_env: Path):
    pid = "prod-hero-01"
    _write_marketing(blog_env, pid, {"product_name": "Harbor", "tagline": "A quiet watch."})
    post = build_launch_post(pid, capture_screenshot=False)
    assert post is not None
    assert post["includeScreenshot"] is True


def test_cli_product_can_opt_out_of_the_hero_shot(blog_env: Path):
    pid = "prod-cli-01"
    _write_marketing(
        blog_env,
        pid,
        {
            "product_name": "Pipekit",
            "blog_post": {"title": "Launch: Pipekit", "excerpt": "A CLI.", "include_screenshot": False},
        },
    )
    post = build_launch_post(pid, capture_screenshot=False)
    assert post is not None
    assert post["includeScreenshot"] is False
    assert not any(b.get("type") == "img" for b in post["body"])


def test_update_blog_post_marks_admin_edited(blog_env: Path):
    pid = "prod-edit-01"
    _write_marketing(blog_env, pid, {"product_name": "Edit Me", "tagline": "Hello"})
    publish_product_launch_blog_post(pid, capture_screenshot=False)
    slug = "launch-prod-edit-01"
    updated = update_blog_post(slug, {"title": "Edited title", "status": "draft"})
    assert updated["title"] == "Edited title"
    assert updated["source"] == "admin_edited"
    assert updated["status"] == "draft"
    assert get_blog_post(slug)["title"] == "Edited title"
