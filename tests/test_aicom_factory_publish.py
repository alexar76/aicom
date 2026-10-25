"""Tests for aicom factory vs satellite publish excludes."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from aicom_publish_config import (
    DEFAULT_RSYNC_EXCLUDES,
    PUBLIC_FACTORY_ROOTS,
    check_roots,
    classify_root,
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


def test_factory_publish_is_live_append_only():
    """GitHub factory matches metis live mode: append, never orphan/--force."""
    text = (ROOT / "scripts" / "publish_aicom_factory.sh").read_text()
    assert "git_auth push --force" not in text
    assert 'rm -rf "$CLONE/.git"' not in text
    assert "chore(factory): sync" in text
    assert "import_factory_pr.sh" in text
    assert "_inject_factory_live_banner" in text
    assert (ROOT / "scripts" / "import_factory_pr.sh").is_file()


def test_factory_rsync_excludes_cursor_and_github():
    """Factory publish uses rsync; .gitignore does not apply."""
    assert "independent" in DEFAULT_RSYNC_EXCLUDES
    assert "unused" in DEFAULT_RSYNC_EXCLUDES
    assert "build" in DEFAULT_RSYNC_EXCLUDES
    assert ".build" in DEFAULT_RSYNC_EXCLUDES
    assert ".venv-quality" in DEFAULT_RSYNC_EXCLUDES
    assert "independent" in factory_exclude_paths()
    locals_ = set(factory_local_exclude_paths())
    assert ".cursor" in locals_
    assert ".github" in locals_
    assert "contracts/zk/.tools" in locals_
    assert "independent" in locals_
    args = rsync_exclude_args()
    excludes = {
        args[i + 1]
        for i in range(len(args) - 1)
        if args[i] == "--exclude"
    }
    assert ".cursor" in excludes
    assert ".github" in excludes
    assert "contracts/zk/.tools" in excludes
    assert "data/funnel" in excludes
    assert ".runtime" in excludes
    assert "data/uni_settlements.jsonl" in excludes
    assert "data/water_quality_history.json" in excludes
    assert "independent" in excludes
    assert ".venv-quality" in excludes
    assert "docs/evidence/mcp-sdk-recovery-2026-10-24" in excludes
    assert "docs/evidence/external-presence-2026-10-24" in excludes
    assert "artifacts/security-audit-2026-10-25" in excludes
    assert "artifacts/security-bincode-2026-10-25" in excludes
    assert "artifacts/security-migration-2026-10-25" in excludes
    assert "artifacts/quality-audit-2026-10-24" in excludes
    assert "cite-desks" in factory_local_exclude_paths()
    assert "cite-desks" in DEFAULT_RSYNC_EXCLUDES
    assert "cite-desks" in factory_exclude_paths()
    assert "deploy/backup/README.md" in locals_
    assert "deploy/nginx/esim.modelmarket.dev.conf" in locals_
    assert "artifacts/stripe-reversals-sandbox" in locals_
    assert "artifacts/stripe-tax-sandbox" in locals_
    assert "artifacts/histor-zenodo-*" in locals_
    assert "scripts/delivery-survey/buy.jsonl" in locals_
    assert "iphone-awg.conf" in locals_
    assert "data/logos" in locals_
    assert "artifacts" in PUBLIC_FACTORY_ROOTS


def test_satellite_export_includes_provenance():
    paths = set(satellite_export_paths())
    assert "aimarket-hub/plugins/aimarket-provenance" in paths



def test_every_tracked_repo_root_is_classified():
    """A deny-list leaks by omission; this makes a new root an explicit decision.

    plans/, promo/ and .momus/ reached the public mirror because nothing required anyone
    to say whether a new top-level directory was public. Now every tracked root is either
    excluded, a satellite, or named in PUBLIC_FACTORY_ROOTS — or this fails.
    """
    stray = check_roots(ROOT)
    assert not stray, (
        "unclassified repo roots (decide: exclude list, satellite-map.yaml, or "
        f"PUBLIC_FACTORY_ROOTS): {stray}"
    )


def test_root_audit_reads_one_configuration_snapshot(monkeypatch):
    import aicom_publish_config as config

    reads = []

    def excludes():
        reads.append(True)
        return ["satellite-a", "satellite-b"]

    monkeypatch.setattr(config, "factory_exclude_paths", excludes)
    monkeypatch.setattr(config, "_shipped_roots", lambda _: ["satellite-a", "satellite-b", "README.md", "unknown"])
    assert config.check_roots(ROOT) == ["unknown"]
    assert len(reads) == 1


def test_an_untracked_root_is_classified_too(tmp_path):
    """The factory export rsyncs the working tree and the clone runs `git add -A`, so an
    untracked root that .gitignore does not cover ships exactly like a tracked one."""
    import subprocess
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    (tmp_path / ".gitignore").write_text("ignored-dir/\n", encoding="utf-8")
    (tmp_path / "ignored-dir").mkdir()
    (tmp_path / "ignored-dir" / "f").write_text("x", encoding="utf-8")
    (tmp_path / ".stray-keys").mkdir()
    (tmp_path / ".stray-keys" / "signing_key").write_text("x", encoding="utf-8")
    stray = check_roots(tmp_path)
    assert ".stray-keys" in stray
    assert "ignored-dir" not in stray


def test_root_classification_is_exhaustive_and_secrets_are_never_public():
    for name in ("independent", "pantheon", "modelmarket-blog", "cite-desks", "attested", "saas-compose.yml", "domain-kit"):
        assert classify_root(name) != "public", name
    assert classify_root("domain-kit") == "excluded"
    assert classify_root(".env") == "excluded"
    assert classify_root("aimarket-hub") == "satellite"
    assert "README.md" in PUBLIC_FACTORY_ROOTS
    assert "attested" not in PUBLIC_FACTORY_ROOTS
    assert "agent-skills" in PUBLIC_FACTORY_ROOTS
    assert "okx-a2mcp" in PUBLIC_FACTORY_ROOTS


def test_factory_publish_overlays_public_cursor_skills():
    """rsync drops .cursor; GitHub clones still need Cursor skills without a copy step."""
    text = (ROOT / "scripts" / "publish_aicom_factory.sh").read_text()
    assert "copy_factory_cursor_skills" in text
    assert "agent-skills/skills" in text
    assert "aimarket-hub-mcp" in text
    assert "warden-mcp-firewall" in text
    assert text.count("copy_factory_cursor_skills") >= 3
