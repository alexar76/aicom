"""Tests for aicom factory vs satellite publish excludes."""

from __future__ import annotations

from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aicom_publish_config import (  # noqa: E402
    factory_exclude_paths,
    factory_local_exclude_paths,
    rsync_exclude_args,
    satellite_export_paths,
)


def test_factory_excludes_all_satellite_roots():
    excludes = set(factory_exclude_paths())
    for p in (
        "acex",
        "ai-service-mesh",
        "aimarket-hub",
        "aimarket-protocol",
        "aimarket-sdks",
        "aimarket-widget",
        "aimarket-agent",
        "desktop-integrations",
        "apps/pulse-terminal",
        "plugins",
        "wiki",
        "scripts/wiki-gitea",
    ):
        assert p in excludes, p


def test_publish_all_repos_script_exists():
    assert (ROOT / "scripts" / "publish_all_repos.sh").is_file()


def test_satellite_map_includes_wiki():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    ids = {s["id"] for s in data.get("satellites", [])}
    assert "aicom-wiki" in ids


def test_satellite_map_has_github_descriptions():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    missing = [
        sat.get("id")
        for sat in data.get("satellites", [])
        if not (sat.get("description") or "").strip()
    ]
    assert not missing, f"missing description: {missing}"


def test_publish_scripts_exist():
    assert (ROOT / "scripts" / "publish_aicom_factory.sh").is_file()
    assert (ROOT / "scripts" / "publish_satellite.sh").is_file()
    assert (ROOT / "scripts" / "aicom_publish_config.py").is_file()


def test_factory_rsync_excludes_cursor_and_github():
    """Factory publish uses rsync; .gitignore does not apply."""
    locals_ = set(factory_local_exclude_paths())
    assert ".cursor" in locals_
    assert ".github" in locals_
    excludes = {
        rsync_exclude_args()[i + 1]
        for i in range(len(rsync_exclude_args()) - 1)
        if rsync_exclude_args()[i] == "--exclude"
    }
    assert ".cursor" in excludes
    assert ".github" in excludes


def test_satellite_export_includes_provenance():
    paths = set(satellite_export_paths())
    assert "aimarket-hub/plugins/aimarket-provenance" in paths
