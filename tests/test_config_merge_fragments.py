"""Layered config: primary overlay path vs bundled fragments directory."""

from __future__ import annotations

from pathlib import Path

import yaml

from core.config_merge import config_fragments_dir, load_merged_config


def test_config_fragments_dir_default():
    primary = Path("/app/config.yaml")
    assert config_fragments_dir(primary) == Path("/app/config/fragments")


def test_config_fragments_dir_env_override(monkeypatch):
    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", "/opt/aicom/fragments")
    assert config_fragments_dir(Path("/data/writable.yaml")) == Path("/opt/aicom/fragments")


def test_load_merged_overlay_under_arbitrary_dir_uses_fragments_env(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parent.parent
    frags = repo_root / "config" / "fragments"
    assert frags.is_dir(), "repo must ship config/fragments for this test"

    overlay = tmp_path / "data" / "config" / "admin_config_overlay.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(
        yaml.dump({"general": {"published_site_head_html": "<script id=\"x\">1</script>"}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", str(frags))
    merged = load_merged_config(overlay)

    assert merged.get("general", {}).get("published_site_head_html") == '<script id="x">1</script>'
    # At least one known fragment default should still be present
    assert "storefront" in merged or "web" in merged


def test_the_parse_is_reused_until_a_file_changes(tmp_path, monkeypatch):
    """The pipeline worker reads the config per product per cycle; re-parsing it was 92% of its
    CPU on factory-vps (2026-10-23). A file that changes is still seen at once."""
    import yaml as _yaml

    from core import config_merge

    frag = tmp_path / "config" / "fragments"
    frag.mkdir(parents=True)
    (frag / "00-base.yaml").write_text("factory:\n  hold: false\n", encoding="utf-8")
    primary = tmp_path / "config.yaml"
    primary.write_text("factory:\n  focus: []\n", encoding="utf-8")
    monkeypatch.delenv("AIFACTORY_CONFIG_FRAGMENTS_DIR", raising=False)
    calls = []
    real = _yaml.safe_load
    monkeypatch.setattr(config_merge.yaml, "safe_load", lambda text: calls.append(1) or real(text))

    first = config_merge.load_merged_config(primary)
    for _ in range(50):
        assert config_merge.load_merged_config(primary) == first
    assert len(calls) == 2                       # one fragment + the primary, parsed once
    first["factory"]["hold"] = "mutated by a caller"
    assert config_merge.load_merged_config(primary)["factory"]["hold"] is False   # callers get copies

    primary.write_text("factory:\n  focus: [prod-1]\n  hold: true\n", encoding="utf-8")
    after = config_merge.load_merged_config(primary)
    assert after["factory"]["focus"] == ["prod-1"] and after["factory"]["hold"] is True
    (frag / "10-more.yaml").write_text("extra: 1\n", encoding="utf-8")
    assert config_merge.load_merged_config(primary)["extra"] == 1
