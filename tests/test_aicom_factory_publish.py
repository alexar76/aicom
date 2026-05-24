"""Tests for aicom factory vs satellite publish excludes."""

from __future__ import annotations

from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aicom_publish_config import factory_exclude_paths, satellite_export_paths  # noqa: E402


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
        "alien-monitor",
    ):
        assert p in excludes, p


def test_publish_all_repos_script_exists():
    assert (ROOT / "scripts" / "publish_all_repos.sh").is_file()


def test_satellite_map_includes_wiki():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    ids = {s["id"] for s in data.get("satellites", [])}
    assert "aicom-wiki" in ids


def test_satellite_map_includes_alien_monitor():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    by_id = {s["id"]: s for s in data.get("satellites", [])}
    assert "alien-monitor" in by_id
    assert by_id["alien-monitor"]["repo"] == "alien-monitor"
    assert "alien-monitor" in by_id["alien-monitor"]["topics"]


def test_satellite_map_has_github_descriptions():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    missing = [
        sat.get("id")
        for sat in data.get("satellites", [])
        if not (sat.get("description") or "").strip()
    ]
    assert not missing, f"missing description: {missing}"


def test_satellite_map_has_github_topics():
    import yaml

    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    missing = [
        sat.get("id")
        for sat in data.get("satellites", [])
        if sat.get("id") != "aicom-wiki" and not sat.get("topics")
    ]
    assert not missing, f"missing topics: {missing}"
    for extra in data.get("extra_repos") or []:
        assert extra.get("topics"), f"extra repo {extra.get('repo')} missing topics"
        assert (extra.get("description") or "").strip()


def test_publish_scripts_exist():
    assert (ROOT / "scripts" / "publish_aicom_factory.sh").is_file()
    assert (ROOT / "scripts" / "publish_satellite.sh").is_file()
    assert (ROOT / "scripts" / "aicom_publish_config.py").is_file()


def test_satellite_export_includes_provenance():
    paths = set(satellite_export_paths())
    assert "aimarket-hub/plugins/aimarket-provenance" in paths
