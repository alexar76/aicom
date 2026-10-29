"""Factory previews choose a GitHub push URL without changing the Gitea canon."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
GITEA = "https://gitea.example/alexar76/aicom.git"
GITHUB = "git@github.com:alexar76/aicom.git"


@pytest.fixture
def checkout(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("publish_aicom_factory.sh", "aicom_publish_config.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    (scripts / "satellite-map.yaml").write_text(
        "org: alexar76\nsatellites:\n  - id: aicom\n    exclude_paths: [private]\n"
    )
    study = tmp_path / "research/malware-feed-accuracy"
    study.mkdir(parents=True)
    (study / "publication-date.txt").write_text("2099-01-01\n")
    subprocess.run([GIT, "init", "-q", str(tmp_path)], check=True)
    subprocess.run([GIT, "-C", str(tmp_path), "remote", "add", "origin", GITEA], check=True)

    # The real script may query remotes only. Any network Git operation or
    # accidental remote mutation makes the test fail before it can execute.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "git"
    wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-C" ]; then shift 2; fi\n'
        'if [ "$1" = "remote" ] && { [ "$#" -eq 1 ] || [ "$2" = "get-url" ]; }; then\n'
        f'  exec {shlex.quote(GIT)} -C {shlex.quote(str(tmp_path))} "$@"\n'
        "fi\n"
        'echo "unexpected git operation in preview" >&2\nexit 90\n'
    )
    wrapper.chmod(0o755)
    python = bin_dir / "python3"
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    return tmp_path


def configure(checkout, name, fetch, *pushes):
    subprocess.run([GIT, "-C", str(checkout), "remote", "add", name, fetch], check=True)
    for url in pushes:
        subprocess.run([GIT, "-C", str(checkout), "remote", "set-url", "--add", "--push", name, url],
                       check=True)


def preview(checkout, *args, factory_remote="", token=""):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_") and key not in ("GH_PAT", "GITHUB_TOKEN", "AICOM_FACTORY_REMOTE")}
    env.update(PATH=f"{checkout / 'bin'}:{env['PATH']}", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_CONFIG_NOSYSTEM="1", AICOM_FACTORY_REMOTE=factory_remote, GH_PAT=token)
    config = checkout / ".git/config"
    before = config.read_bytes()
    out = subprocess.run(
        ["bash", str(checkout / "scripts/publish_aicom_factory.sh"), "--dry-run", *args],
        cwd=checkout / "research", env=env, capture_output=True, text=True, timeout=15,
    )
    assert config.read_bytes() == before, "preview changed Git remotes"
    assert "unexpected git operation" not in out.stderr
    return out


@pytest.mark.parametrize("name", ["gh", "github", "public-factory"])
def test_discovers_github_alias_while_origin_stays_gitea(checkout, name):
    configure(checkout, name, GITHUB)
    out = preview(checkout)
    assert out.returncode == 0, out.stderr
    assert f"Remote:  {GITHUB}" in out.stdout


def test_uses_push_urls_and_ignores_a_github_fetch_with_gitea_push(checkout):
    configure(checkout, "gh", GITHUB, GITEA)
    configure(checkout, "public", GITEA, "ssh://git@github.com/alexar76/aicom.git")
    out = preview(checkout)
    assert out.returncode == 0, out.stderr
    assert "Remote:  ssh://***@github.com/alexar76/aicom.git" in out.stdout


def test_selects_github_url_without_using_the_remote_with_multiple_push_urls(checkout):
    configure(checkout, "gh", GITEA, GITEA, GITHUB)
    out = preview(checkout)
    assert out.returncode == 0, out.stderr
    assert f"Remote:  {GITHUB}" in out.stdout


def test_duplicate_aliases_for_one_repository_are_not_ambiguous(checkout):
    configure(checkout, "gh", GITHUB)
    configure(checkout, "backup", "https://github.com/alexar76/aicom.git")
    out = preview(checkout)
    assert out.returncode == 0, out.stderr
    assert f"Remote:  {GITHUB}" in out.stdout


def test_distinct_factory_repositories_require_an_explicit_choice(checkout):
    configure(checkout, "gh", GITHUB)
    configure(checkout, "fork", "https://github.com/example-fork/aicom.git")
    out = preview(checkout)
    assert out.returncode != 0
    assert "multiple GitHub factory repositories" in out.stderr
    chosen = preview(checkout, factory_remote=GITHUB)
    assert chosen.returncode == 0, chosen.stderr


def test_explicit_argument_overrides_environment_and_discovery(checkout):
    configure(checkout, "gh", GITHUB)
    target = "https://github.com/alexar76/aicom.git"
    out = preview(checkout, "--remote", target, factory_remote=GITEA)
    assert out.returncode == 0, out.stderr
    assert f"Remote:  {target}" in out.stdout


def test_environment_overrides_discovery(checkout):
    configure(checkout, "gh", GITHUB)
    target = "https://github.com/alexar76/aicom.git"
    out = preview(checkout, factory_remote=target)
    assert out.returncode == 0, out.stderr
    assert f"Remote:  {target}" in out.stdout


@pytest.mark.parametrize("url", [
    GITEA,
    "https://github.com/alexar76/aimarket-hub.git",
    "https://evilgithub.com/alexar76/aicom.git",
    "https://github.com.evil.example/alexar76/aicom.git",
    "https://github.com@evil.example/alexar76/aicom.git",
])
def test_invalid_explicit_target_is_refused_instead_of_silently_replaced(checkout, url):
    configure(checkout, "gh", GITHUB)
    out = preview(checkout, factory_remote=url)
    assert out.returncode != 0
    assert "factory target must be a GitHub" in out.stderr
    assert "[dry-run]" not in out.stdout


def test_no_github_factory_push_target_explains_how_to_select_one(checkout):
    configure(checkout, "satellite", "https://github.com/alexar76/aimarket-hub.git")
    configure(checkout, "gh", GITHUB, GITEA)
    out = preview(checkout)
    assert out.returncode != 0
    assert "no configured GitHub push URL" in out.stderr
    assert "AICOM_FACTORY_REMOTE" in out.stderr


@pytest.mark.parametrize("url", [
    "https://example-secret@github.com/alexar76/aicom.git",
    "https://user:example-secret@github.com/alexar76/aicom.git",
])
def test_preview_redacts_url_credentials(checkout, url):
    out = preview(checkout, factory_remote=url)
    assert out.returncode == 0, out.stderr
    assert "example-secret" not in out.stdout + out.stderr
    assert "https://***@github.com/alexar76/aicom.git" in out.stdout


def test_preview_redacts_token_when_ssh_target_is_converted_to_https(checkout):
    configure(checkout, "gh", GITHUB)
    out = preview(checkout, token="example-factory-token")
    assert out.returncode == 0, out.stderr
    assert "example-factory-token" not in out.stdout + out.stderr
    assert "Remote:  https://***@github.com/alexar76/aicom.git" in out.stdout


def test_github_text_in_credentials_cannot_replace_the_repository_or_leak(checkout):
    out = preview(checkout, factory_remote="https://github.com:example-secret@github.com/alexar76/aicom.git")
    assert out.returncode == 0, out.stderr
    assert "example-secret" not in out.stdout + out.stderr
    assert "Remote:  https://***@github.com/alexar76/aicom.git" in out.stdout
