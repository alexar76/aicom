"""The two publish-safety tools must see the distributions from an agent's worktree.

**What went wrong.** Agent sessions work in checkouts under `.claude/worktrees/<name>/`, and both
tools excluded `.claude` by testing the WHOLE path rather than the part below the repo root:

* `scripts/verify_published_dist_freshness.py` matched `SKIP_PARTS` against absolute path parts,
  so from a worktree every pyproject was skipped. `--json` gave `"rows": []` and exit 0 — a false
  green from the check the owner runs before every publish ("a red line means bump, not
  re-publish"), with about ninety distributions in the tree it never looked at.
* `scripts/publish_pypi.sh` ran `find "$ROOT" -not -path '*/.claude/*'`, which excluded every
  pyproject when `$ROOT` itself is under `.claude/`, so a name like `aimarket-safety` did not
  resolve; only explicit paths and the hard-coded aliases did.

**What is asserted here.** Both properties, for a root that sits under `.claude/` and for one that
does not: discovery finds the real trees, and a stale copy at `.claude/worktrees/x/` INSIDE the
root is still excluded — the comment in publish_pypi.sh records a real build from such a copy.
Offline: discovery only, with the PyPI lookup stubbed.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts" / "verify_published_dist_freshness.py"
PUBLISH = ROOT / "scripts" / "publish_pypi.sh"

#: Where the repo root sits: an ordinary checkout, and an agent's worktree.
ROOT_LOCATIONS = ("checkout", ".claude/worktrees/agent-x", "artifacts/checkouts/agent-x")


def _pyproject(path: Path, name: str, version: str = "0.1.0") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\n', encoding="utf-8")


def _fake_monorepo(base: Path, location: str) -> Path:
    """Two live trees, plus copies of one of them where nothing may find it."""
    root = base / location
    _pyproject(root / "alpha", "demo-alpha")
    (root / "alpha" / "demo_alpha").mkdir()
    (root / "alpha" / "demo_alpha" / "__init__.py").write_text("", encoding="utf-8")
    _pyproject(root / "plugins" / "beta", "demo-beta")
    # A week-old session worktree inside this root, carrying the same name as a live tree and
    # one that exists nowhere else.
    _pyproject(root / ".claude" / "worktrees" / "stale" / "alpha", "demo-alpha")
    _pyproject(root / ".claude" / "worktrees" / "stale" / "gone", "demo-only-in-stale-copy")
    _pyproject(root / "web" / "node_modules" / "pkg", "demo-alpha")
    _pyproject(root / ".venv" / "lib" / "site-packages" / "dep", "demo-alpha")
    # A release verification leaves copied pyprojects in both ignored sdist
    # caches and tracked source snapshots. Neither is another publishable tree.
    _pyproject(root / "artifacts" / "rollout" / "uv-cache" / "sdists-v9" / "src", "demo-alpha")
    _pyproject(root / "artifacts" / "rollout" / "release-source", "demo-beta")
    _pyproject(root / "artifacts" / "only-copy", "demo-only-in-artifacts")
    (root / ".gitignore").write_text("artifacts/**/uv-cache/\n", encoding="utf-8")
    for generated in ("venv", ".cache", "uv-cache", "build", "dist"):
        _pyproject(root / "alpha" / generated / "copied-source", "demo-alpha")
    return root


def _git_index(root: Path) -> None:
    """The verifier lists tracked files. Force-add everything, the stale copy included, so the
    exclusion is what keeps it out rather than .gitignore."""
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "add", "-A", "-f", "."], cwd=root, check=True, capture_output=True)


def _load_verifier():
    spec = importlib.util.spec_from_file_location("verify_published_dist_freshness", VERIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── verify_published_dist_freshness.py ──────────────────────────────────────────────────────


@pytest.fixture(params=ROOT_LOCATIONS)
def verifier_on_fake_repo(request, tmp_path, monkeypatch):
    root = _fake_monorepo(tmp_path, request.param)
    _git_index(root)
    mod = _load_verifier()
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "_pypi", lambda name: None)  # never the network
    return mod, root


def test_verifier_finds_the_trees_and_skips_nested_copies(verifier_on_fake_repo) -> None:
    mod, root = verifier_on_fake_repo
    found = [p.relative_to(root).as_posix() for p in mod._first_party_pyprojects()]
    assert found == ["alpha/pyproject.toml", "plugins/beta/pyproject.toml"], (
        f"from {root}: discovered {found}. An empty list is the original bug — the root's own "
        f"`.claude` ancestor matched SKIP_PARTS. Anything under .claude/, node_modules/ or .venv/ "
        f"means a stale copy would be compared instead of the live tree.")


def test_verifier_follows_a_local_rename_before_staging(verifier_on_fake_repo) -> None:
    mod, root = verifier_on_fake_repo
    (root / "alpha").rename(root / "renamed")
    _pyproject(root / "output" / "release-source", "demo-copy")
    found = [p.relative_to(root).as_posix() for p in mod._first_party_pyprojects()]
    assert found == ["plugins/beta/pyproject.toml", "renamed/pyproject.toml"]


def test_verifier_json_run_has_rows(verifier_on_fake_repo, capsys) -> None:
    """The end-to-end shape of the false green: `--json` from a worktree printed no rows."""
    mod, _root = verifier_on_fake_repo
    assert mod.main(["--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    rows = {r["dist"]: r for r in report["rows"]}
    assert set(rows) == {"demo-alpha", "demo-beta"}
    assert rows["demo-alpha"]["imports"] == ["demo_alpha"], (
        "import names come from the same tree walk; an empty list here hides every collision")


def test_verifier_refuses_to_pass_when_it_found_nothing(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / ".claude" / "worktrees" / "empty"
    root.mkdir(parents=True)
    _git_index(root)
    mod = _load_verifier()
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "_pypi", lambda name: pytest.fail("no pyproject, no lookup"))
    assert mod.main([]) == 2, "an empty discovery reported as a pass is exactly the false green"
    assert "nothing was checked" in capsys.readouterr().err


# ── publish_pypi.sh resolve_package_dir ──────────────────────────────────────────────────────


def _resolve_package_dir_source() -> str:
    """The shipped function, so the test runs the code that publishes."""
    text = PUBLISH.read_text(encoding="utf-8")
    m = re.search(r"^resolve_package_dir\(\) \{\n.*?^\}\n", text, re.S | re.M)
    assert m, "could not find resolve_package_dir() in publish_pypi.sh — restructured?"
    return m.group(0)


def _resolve(root: Path, name: str) -> subprocess.CompletedProcess:
    script = (
        "set -euo pipefail\n"
        f"{_resolve_package_dir_source()}"
        'ROOT="$1"; PKG=""\n'
        'resolve_package_dir "$2" && echo "PKG=$PKG" || echo "rc=$?"\n'
    )
    return subprocess.run(["bash", "-c", script, "resolve", str(root), name],
                          capture_output=True, text=True)


@pytest.mark.parametrize("location", ROOT_LOCATIONS)
def test_publish_resolves_names_and_skips_nested_copies(tmp_path, location) -> None:
    root = _fake_monorepo(tmp_path, location)

    beta = _resolve(root, "demo-beta")
    assert beta.stdout.strip() == "PKG=plugins/beta", (
        f"from {root}: {beta.stdout.strip()!r} {beta.stderr.strip()!r}. `rc=1` is the original "
        f"bug — find excluded everything because $ROOT itself is under .claude/.")

    # Declared by the live tree AND by copies under .claude/, node_modules/ and .venv/: any copy
    # that is not excluded turns this into the ambiguity error (exit 2), or a build of the copy.
    alpha = _resolve(root, "demo-alpha")
    assert alpha.returncode == 0 and alpha.stdout.strip() == "PKG=alpha", (
        f"from {root}: {alpha.stdout.strip()!r} {alpha.stderr.strip()!r}")

    stale = _resolve(root, "demo-only-in-stale-copy")
    assert stale.stdout.strip() == "rc=1", (
        f"a name that only a nested .claude/worktrees copy declares resolved: {stale.stdout!r}. "
        f"That is the incident in publish_pypi.sh's comment — a stale worktree copy got built.")

    artifact = _resolve(root, "demo-only-in-artifacts")
    assert artifact.stdout.strip() == "rc=1", (
        f"an artifact-only source snapshot resolved as a publishable project: {artifact.stdout!r}")


@pytest.mark.parametrize("location", ROOT_LOCATIONS)
def test_publish_still_refuses_two_real_source_projects(tmp_path, location) -> None:
    root = _fake_monorepo(tmp_path, location)
    _pyproject(root / "plugins" / "another-alpha", "demo-alpha")

    result = _resolve(root, "demo-alpha")
    assert result.returncode == 2
    assert "declared by 2 pyproject.toml files" in result.stderr
    assert "alpha/pyproject.toml" in result.stderr
    assert "plugins/another-alpha/pyproject.toml" in result.stderr
    assert "rollout/uv-cache" not in result.stderr

    # An explicit source directory is still an intentional disambiguation.
    explicit = _resolve(root, "plugins/another-alpha")
    assert explicit.returncode == 0
    assert explicit.stdout.strip() == "PKG=plugins/another-alpha"


@pytest.mark.parametrize("location", ROOT_LOCATIONS)
def test_verifier_refuses_artifact_only_discovery(tmp_path, monkeypatch, capsys, location) -> None:
    root = tmp_path / location
    _pyproject(root / "artifacts" / "rollout" / "release-source", "demo-copied")
    _git_index(root)
    mod = _load_verifier()
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "_pypi", lambda name: pytest.fail("artifact metadata must not be queried"))

    assert mod._first_party_pyprojects() == []
    assert mod.main(["--json"]) == 2
    assert "nothing was checked" in capsys.readouterr().err
