"""Tests for optional <head> injection on generated static HTML."""

from pathlib import Path

import yaml

from web.backend.services import site_head_snippet as shs


def test_inject_before_close_head(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "general": {
                    "published_site_head_html": '<script id="t">console.log(1)</script>',
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shs, "CONFIG_PATH", cfg)

    root = tmp_path / "data"
    pid = "p1"
    html_path = root / "code" / pid / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text(
        "<!doctype html><html><head><title>x</title></head><body></body></html>",
        encoding="utf-8",
    )

    shs.inject_published_site_head_if_configured(root, pid)
    out = html_path.read_text(encoding="utf-8")
    assert shs.MARKER_BEGIN.split()[0] in out  # marker comment present
    assert '<script id="t">console.log(1)</script>' in out
    assert out.index("console.log") < out.lower().index("</head>")


def test_inject_after_open_head_when_no_close(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.dump({"general": {"published_site_head_html": "<meta name='x' content='y'/>"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(shs, "CONFIG_PATH", cfg)

    root = tmp_path / "data"
    pid = "p2"
    html_path = root / "code" / pid / "a.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html><head><title>t</title><body></body></html>", encoding="utf-8")

    shs.inject_published_site_head_if_configured(root, pid)
    out = html_path.read_text(encoding="utf-8")
    assert "<meta name='x' content='y'/>" in out


def test_skips_when_empty_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.dump({"general": {}}), encoding="utf-8")
    monkeypatch.setattr(shs, "CONFIG_PATH", cfg)

    root = tmp_path / "data"
    pid = "p3"
    html_path = root / "code" / pid / "index.html"
    html_path.parent.mkdir(parents=True)
    original = "<html><head></head><body></body></html>"
    html_path.write_text(original, encoding="utf-8")

    shs.inject_published_site_head_if_configured(root, pid)
    assert html_path.read_text(encoding="utf-8") == original


def test_idempotent_marker(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.dump({"general": {"published_site_head_html": "<script>1</script>"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(shs, "CONFIG_PATH", cfg)

    root = tmp_path / "data"
    pid = "p4"
    html_path = root / "code" / pid / "index.html"
    html_path.parent.mkdir(parents=True)
    html_path.write_text("<html><head></head><body></body></html>", encoding="utf-8")

    shs.inject_published_site_head_if_configured(root, pid)
    first = html_path.read_text(encoding="utf-8")
    shs.inject_published_site_head_if_configured(root, pid)
    second = html_path.read_text(encoding="utf-8")
    assert first == second
    assert second.count("<script>1</script>") == 1
