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
    purge_factory_local_paths,
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


def test_factory_rsync_omits_internal_evidence_and_keeps_public_content(tmp_path):
    import subprocess

    source = tmp_path / "source"
    target = tmp_path / "export"
    reports = (
        "artifacts/quality-audit-2026-10-23/factory-tests.xml",
        "artifacts/quality-audit-2026-10-23/followup/factory-tests.xml",
        "artifacts/quality-audit-2026-10-24/factory-tests.xml",
        "artifacts/oracle-metis-rollout-2026-10-28/postdeploy-install/cache/ssh.py",
        "artifacts/system-verification-2026-10-28/python/gateway/mcp.stderr.log",
        "artifacts/external-deep-2026-10-29/social/identity-search-log.json",
        "docs/growth/publication-2026-10-25/launchgate/prepare_blog.py",
        "docs/evidence/histor-full-observations-2026-10-27/hub/baseline-wire.json",
        "docs/evidence/histor-full-observations-2026-10-27/hub/recheck-wire.json",
        "docs/evidence/histor-release-0.4.2-2026-10-27/release.json",
        "docs/evidence/histor-release-0.4.2-2026-10-27/sandboxes.json",
        "artifacts/security-rollout-2026-10-30/admin-inventory.txt",
        "docs/evidence/fleet-cleanup-2026-10-29/snapshot.json",
        "docs/evidence/fleet-resource-check-2026-10-29/collect.py",
        "docs/evidence/external-use-pass4-2026-10-30/social/lobsters-native-stories.html",
        "docs/evidence/external-signals-2026-10-30/social/raw/youtube-channel.html",
        "scripts/.mirror-forbidden-hosts",
    )
    for rel in reports:
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<testsuite name='local-audit'/>\n", encoding="utf-8")
    public = {
        "artifacts/kaggle-histor/public-example.txt": "public example\n",
        "docs/evidence/histor-full-observations-2026-10-27/python-packages/artifact-index.json": "{}\n",
        "docs/growth/publication-2026-10-25/launchgate/article.published.md": "# Published article\n",
        "docs/evidence/external-signals-2026-10-30/summary.json": "{}\n",
    }
    for rel, content in public.items():
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    subprocess.run(
        ["rsync", "-a", "--delete", *rsync_exclude_args(), f"{source}/", f"{target}/"],
        check=True, capture_output=True, text=True, timeout=15,
    )

    assert not (target / "artifacts/quality-audit-2026-10-23").exists()
    assert not (target / "artifacts/quality-audit-2026-10-24").exists()
    for rel in reports:
        assert not (target / rel).exists(), rel
    for rel, content in public.items():
        assert (target / rel).read_text(encoding="utf-8") == content, rel


def test_reused_factory_tree_removes_old_internal_glob_matches(tmp_path):
    internal = (
        "artifacts/security-rollout-2026-10-30/inventory.txt",
        "docs/evidence/fleet-cleanup-2026-10-29/snapshot.json",
        "docs/evidence/external-signals-2026-10-30/social/raw/page.html",
        "scripts/.mirror-forbidden-hosts",
    )
    for rel in (*internal, ".git/config", "README.md", "artifacts/kaggle-histor/public.txt"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture\n")
    purge_factory_local_paths(tmp_path)
    assert all(not (tmp_path / rel).exists() for rel in internal)
    for rel in (".git/config", "README.md", "artifacts/kaggle-histor/public.txt"):
        assert (tmp_path / rel).read_text() == "fixture\n"


def test_factory_purge_refuses_workspace_and_symlink_escape(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="workspace"):
        purge_factory_local_paths(ROOT)
    external = tmp_path / "outside"
    external.mkdir()
    secret = external / "fleet-snapshot.txt"
    secret.write_text("must stay\n")
    tree = tmp_path / "candidate"
    (tree / "docs").mkdir(parents=True)
    (tree / "docs/evidence").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        purge_factory_local_paths(tree)
    assert secret.read_text() == "must stay\n"


def test_rsync_omits_local_environments_and_host_policy_at_any_depth(tmp_path):
    import subprocess

    source = tmp_path / "source"
    dependency_paths = (
        ".venv-test/lib/python3.11/site-packages/cryptography/ssh.py",
        "apps/example/.venv-test/lib/python3.11/site-packages/cryptography/ssh.py",
        ".mirror-forbidden-hosts",
        "scripts/.mirror-forbidden-hosts",
    )
    public_sources = {"app.py": "# application\n", "apps/example/main.py": "# example\n"}
    for rel in dependency_paths:
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# installed dependency snapshot\n", encoding="utf-8")
    for rel, content in public_sources.items():
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    # Satellite exports use the canonical defaults; factory exports add their
    # own exclusions. Both must omit local environments and private host policy.
    defaults = [part for pattern in DEFAULT_RSYNC_EXCLUDES for part in ("--exclude", pattern)]
    for name, excludes in (("satellite", defaults), ("factory", rsync_exclude_args())):
        target = tmp_path / name
        subprocess.run(
            ["rsync", "-a", *excludes, f"{source}/", f"{target}/"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        for rel in dependency_paths:
            assert not (target / rel).exists(), (name, rel)
        for rel, content in public_sources.items():
            assert (target / rel).read_text(encoding="utf-8") == content, (name, rel)



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
