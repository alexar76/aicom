"""Generated files must not turn harmless Git operations into host execution."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

from agents.dev_tree.paths import _resolve_safe_code_path
from core.product_git import ProductGit, UnsafeProductGit, has_product_git, private_metadata_path


@pytest.fixture(autouse=True)
def private_store(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "factory-state"))


@pytest.fixture
def product(tmp_path):
    root = tmp_path / "product"
    root.mkdir()
    (root / "README.md").write_text("ordinary generated code\n")
    # Build a standard pre-migration repository, without ProductGit having
    # imported it yet. Every other Git operation under test uses ProductGit.
    template = tmp_path / "empty-template"
    template.mkdir()
    result = subprocess.run(["/usr/bin/git", "init", f"--template={template}"], cwd=root,
                            env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
                                 "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
                            capture_output=True, timeout=5)
    assert result.returncode == 0
    with (root / ".git/config").open("a") as config:
        config.write("\n[user]\n name = Fixture\n email = fixture@example.invalid\n")
    return root


def _canary(tmp_path, name="executed"):
    marker = tmp_path / name
    script = tmp_path / f"{name}.sh"
    script.write_text(f"#!/bin/sh\nprintf proof > {shlex.quote(str(marker))}\ncat\n")
    script.chmod(0o700)
    return script, marker


@pytest.mark.parametrize("name", [
    ".git/config", ".git/hooks/pre-commit", "backend/.git/config", ".GIT/config",
    "backend\\.git\\config", "code/product/.git/config", "/app/data/code/product/.git/config",
])
def test_generated_writes_and_deletions_reject_all_git_components(tmp_path, name):
    root = tmp_path / "product"
    root.mkdir()
    assert _resolve_safe_code_path(root, name) is None


def test_generated_path_cannot_alias_git_but_github_remains_available(tmp_path):
    root = tmp_path / "product"
    (root / ".git").mkdir(parents=True)
    (root / "metadata_alias").symlink_to(root / ".git", target_is_directory=True)
    assert _resolve_safe_code_path(root, "metadata_alias/config") is None
    assert _resolve_safe_code_path(root, ".github/workflows/test.yml") == root / ".github/workflows/test.yml"


def test_old_status_fsmonitor_canary_reproduces_and_safe_api_refuses(product, tmp_path):
    from web.backend.api.sandbox_parts.git import _git_status_blocking

    script, marker = _canary(tmp_path)
    with (product / ".git/config").open("a") as config:
        config.write(f"\n[core]\n\tfsmonitor = {script}\n")
    # Reproduce the previous command only inside this disposable repository.
    subprocess.run(
        ["/usr/bin/git", "status", "--porcelain"], cwd=product,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
        capture_output=True, timeout=5,
    )
    assert marker.read_text() == "proof"
    marker.unlink()
    with pytest.raises(HTTPException) as rejected:
        _git_status_blocking(product, "fixture")
    assert rejected.value.status_code == 400
    assert not marker.exists()


def test_init_status_and_commit_ignore_executable_legacy_hooks(product, tmp_path):
    from web.backend.api.sandbox_parts.git import _git_init_blocking, _git_status_blocking

    script, marker = _canary(tmp_path)
    hooks = product / ".git/hooks"
    hooks.mkdir()
    for name in ("pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "post-index-change"):
        path = hooks / name
        path.write_text(script.read_text())
        path.chmod(0o700)
    assert _git_init_blocking(product, "fixture", "")["status"] == "initialized"
    status = _git_status_blocking(product, "fixture")
    assert status["status"] == "initialized"
    assert status["uncommitted_changes"] == 0
    assert len(status["recent_commits"]) == 1
    assert not marker.exists()


@pytest.mark.parametrize("section,key", [
    ('filter "evil"', "clean"), ('filter "evil"', "process"),
    ("core", "sshCommand"), ("core", "hooksPath"), ("core", "worktree"),
    ("credential", "helper"), ("include", "path"), ('includeIf "gitdir:**"', "path"),
    ("gpg", "program"), ("commit", "gpgSign"), ('alias', 'status'),
    ('url "ext::evil"', "insteadOf"), ('remote "origin"', "receivepack"),
    ('remote "origin"', "uploadpack"), ('remote "origin"', "vcs"),
    ('remote "origin"', "proxy"), ('remote "origin"', "pushurl"),
    ("extensions", "worktreeConfig"),
])
def test_executable_redirecting_and_indirected_config_fails_before_add(product, tmp_path, section, key):
    script, marker = _canary(tmp_path)
    (product / ".gitattributes").write_text("*.md filter=evil\n")
    with (product / ".git/config").open("a") as config:
        config.write(f"\n[{section}]\n\t{key} = {script}\n")
    with pytest.raises(UnsafeProductGit):
        with ProductGit(product) as git:
            git.run(["add", "-A"])
    assert not marker.exists()


def test_clean_filter_canary_is_not_executed_by_init_or_publish_preparation(product, tmp_path):
    from web.backend.api.sandbox_parts.git import _git_init_blocking, _git_push_blocking

    script, marker = _canary(tmp_path)
    (product / ".gitattributes").write_text("*.md filter=evil\n")
    with (product / ".git/config").open("a") as config:
        config.write(f'\n[filter "evil"]\n\tclean = {script}\n')
    for operation in (
        lambda: _git_init_blocking(product, "fixture", ""),
        lambda: _git_push_blocking(product, "fixture", "origin", "main"),
    ):
        with pytest.raises(HTTPException) as rejected:
            operation()
        assert rejected.value.status_code == 400
    assert not marker.exists()


@pytest.mark.parametrize("kind", ["gitdir-symlink", "gitdir-file", "config-symlink", "hooks-symlink",
                                 "config-hardlink", "alternates", "http-alternates", "commondir",
                                 "config.worktree", "worktrees", "nested"])
def test_external_shared_and_nested_metadata_is_refused(product, tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "config"
    sentinel.write_text("[core]\n\tbare = false\n")
    metadata = product / ".git"
    if kind in ("gitdir-symlink", "gitdir-file"):
        metadata.rename(tmp_path / "original-metadata")
        if kind == "gitdir-symlink":
            metadata.symlink_to(outside, target_is_directory=True)
        else:
            metadata.write_text(f"gitdir: {outside}\n")
    elif kind in ("config-symlink", "config-hardlink"):
        (metadata / "config").unlink()
        if kind == "config-symlink":
            (metadata / "config").symlink_to(sentinel)
        else:
            os.link(sentinel, metadata / "config")
    elif kind == "hooks-symlink":
        (metadata / "hooks").symlink_to(outside, target_is_directory=True)
    elif kind in ("alternates", "http-alternates"):
        path = metadata / "objects/info" / kind
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(outside))
    elif kind in ("commondir", "config.worktree"):
        (metadata / kind).write_text(str(outside))
    elif kind == "worktrees":
        (metadata / "worktrees").mkdir()
    else:
        (product / "nested/.git").mkdir(parents=True)
    before = sentinel.read_bytes()
    with pytest.raises(UnsafeProductGit):
        with ProductGit(product) as git:
            git.run(["status", "--porcelain"])
    assert sentinel.read_bytes() == before


def test_parent_global_config_git_environment_path_and_secrets_are_not_inherited(product, tmp_path, monkeypatch):
    script, marker = _canary(tmp_path)
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text(f"[core]\n\tfsmonitor = {script}\n")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "git").write_text(script.read_text())
    (fake_bin / "git").chmod(0o700)
    values = {
        "GIT_CONFIG_GLOBAL": str(global_config), "GIT_CONFIG_SYSTEM": str(global_config),
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": str(script),
        "GIT_CONFIG_PARAMETERS": f"'core.fsmonitor={script}'", "GIT_DIR": str(tmp_path / "outside"),
        "GIT_WORK_TREE": str(tmp_path), "GIT_EXEC_PATH": str(fake_bin), "GIT_TEMPLATE_DIR": str(fake_bin),
        "GIT_SSH_COMMAND": str(script), "GIT_ASKPASS": str(script), "SSH_ASKPASS": str(script),
        "PATH": str(fake_bin), "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path),
        "OPENAI_API_KEY": "canary-never-expose", "AWS_SESSION_TOKEN": "canary-never-expose",
        "LD_PRELOAD": str(script), "DYLD_INSERT_LIBRARIES": str(script),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with ProductGit(product) as git:
        assert "OPENAI_API_KEY" not in git.env and "AWS_SESSION_TOKEN" not in git.env
        assert "LD_PRELOAD" not in git.env and "DYLD_INSERT_LIBRARIES" not in git.env
        assert git.run(["add", "-A"]).returncode == 0
        assert git.run(["commit", "-m", "ordinary commit"]).returncode == 0
        assert git.run(["status", "--porcelain"]).returncode == 0
    assert not marker.exists()


def test_existing_standard_branch_remote_and_ignored_filter_attributes_remain_compatible(product):
    with (product / ".git/config").open("a") as config:
        config.write('\n[remote "origin"]\n\turl = https://github.com/example/example.git\n'
                     '\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
                     '[branch "main"]\n\tremote = origin\n\tmerge = refs/heads/main\n')
    (product / ".gitattributes").write_text("*.md filter=undefined-diff-filter\n")
    with ProductGit(product) as git:
        assert git.run(["add", "-A"]).returncode == 0
        assert git.run(["commit", "-m", "preserve ordinary history"]).returncode == 0
        assert git.run(["log", "--oneline", "-1"]).stdout.strip()
        assert git.run(["remote", "-v"]).stdout.count("https://github.com/example/example.git") == 2


def test_new_init_status_and_commits_survive_contexts_without_product_metadata(tmp_path):
    from web.backend.api.sandbox_parts.git import _git_init_blocking, _git_status_blocking

    root = tmp_path / "new-product"
    root.mkdir()
    (root / "README.md").write_text("first revision\n")
    assert not has_product_git(root)
    assert _git_init_blocking(root, "fixture", "")["status"] == "initialized"
    assert has_product_git(root) and not (root / ".git").exists()
    private = private_metadata_path(root)
    assert not private.is_relative_to(root)
    assert private.parent.stat().st_mode & 0o077 == 0
    (root / "README.md").write_text("second revision\n")
    with ProductGit(root) as git:
        assert git.run(["add", "-A"]).returncode == 0
        assert git.run(["commit", "-m", "second revision"]).returncode == 0
    status = _git_status_blocking(root, "fixture")
    assert len(status["recent_commits"]) == 2 and not status["uncommitted_changes"]


def test_source_config_swap_after_validation_cannot_install_filter(product, tmp_path, monkeypatch):
    script, marker = _canary(tmp_path)
    (product / ".gitattributes").write_text("*.md filter=evil\n")
    original_run = subprocess.run
    injected = []

    def swap_before_git(args, *a, **kw):
        if "add" in args and not injected:
            injected.append(True)
            with (product / ".git/config").open("a") as config:
                config.write(f'\n[filter "evil"]\n clean = {script}\n')
        return original_run(args, *a, **kw)

    with ProductGit(product) as git:
        monkeypatch.setattr(subprocess, "run", swap_before_git)
        assert git.metadata != product / ".git"
        assert git.run(["add", "-A"]).returncode == 0
        assert git.run(["commit", "-m", "safe private snapshot"]).returncode == 0
    # A later context must not re-import newly malicious product metadata.
    with ProductGit(product) as git:
        assert git.run(["status", "--porcelain"]).returncode == 0
    assert injected and not marker.exists()


def test_import_uses_anchored_directory_even_if_source_is_replaced(product, tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "config"
    sentinel.write_text("must not be read or changed\n")
    original_copy = ProductGit._copy_metadata

    def replace_opened_source(self, source_fd, destination):
        (product / ".git").rename(tmp_path / "opened-original")
        (product / ".git").symlink_to(outside, target_is_directory=True)
        return original_copy(self, source_fd, destination)

    monkeypatch.setattr(ProductGit, "_copy_metadata", replace_opened_source)
    with ProductGit(product) as git:
        assert git.run(["add", "-A"]).returncode == 0
        assert b"must not" not in (git.metadata / "config").read_bytes()
    assert sentinel.read_text() == "must not be read or changed\n"


def test_private_snapshot_is_validated_after_copying_mutable_config(product, tmp_path, monkeypatch):
    script, marker = _canary(tmp_path)
    original_copy = ProductGit._copy_metadata

    def mutate_during_snapshot(self, source_fd, destination):
        with (product / ".git/config").open("a") as config:
            config.write(f'\n[filter "evil"]\n clean = {script}\n')
        original_copy(self, source_fd, destination)

    monkeypatch.setattr(ProductGit, "_copy_metadata", mutate_during_snapshot)
    with pytest.raises(UnsafeProductGit):
        with ProductGit(product):
            pytest.fail("an unchecked private copy was accepted")
    assert not private_metadata_path(product).exists() and not marker.exists()


def test_source_file_symlink_swap_between_stat_and_open_is_refused(product, tmp_path, monkeypatch):
    sentinel = tmp_path / "outside-secret"
    sentinel.write_text("disposable canary must not enter private metadata\n")
    original_stat = os.stat
    swapped = []

    def swap_after_stat(path, *args, **kwargs):
        result = original_stat(path, *args, **kwargs)
        if path == "config" and "dir_fd" in kwargs and not swapped:
            swapped.append(True)
            (product / ".git/config").unlink()
            (product / ".git/config").symlink_to(sentinel)
        return result

    monkeypatch.setattr(os, "stat", swap_after_stat)
    with pytest.raises(UnsafeProductGit):
        with ProductGit(product):
            pytest.fail("the raced source link was followed")
    assert swapped and not private_metadata_path(product).exists()
    assert sentinel.read_text() == "disposable canary must not enter private metadata\n"


def test_private_storage_cannot_be_placed_inside_generated_code(tmp_path, monkeypatch):
    product = tmp_path / "product"
    product.mkdir()
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(product))
    with pytest.raises(UnsafeProductGit, match="outside generated code"):
        with ProductGit(product):
            pytest.fail("product-writable private storage was accepted")


def test_private_history_is_excluded_from_source_and_public_export():
    from scripts.aicom_publish_config import DEFAULT_RSYNC_EXCLUDES, classify_root, rsync_exclude_args

    root = Path(__file__).resolve().parents[1]
    assert "data/private_product_git/" in (root / ".gitignore").read_text().splitlines()
    ignored = subprocess.run(
        ["/usr/bin/git", "check-ignore", "--quiet", "--no-index", "custom-data/private_product_git/canary"],
        cwd=root, capture_output=True, timeout=5,
    )
    assert ignored.returncode == 0
    assert "data/private_product_git" in DEFAULT_RSYNC_EXCLUDES
    assert "private_product_git" in DEFAULT_RSYNC_EXCLUDES
    assert classify_root("data/private_product_git") == "excluded"
    assert "data/private_product_git" in rsync_exclude_args()
