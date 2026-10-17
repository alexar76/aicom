"""Every satellite takes pull requests, and a merged one lands at its monorepo path."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import satellite_import_paths as sip  # noqa: E402

SYNC_SUBJECT = "chore(satellite): sync aimarket-plugins from aicom monorepo"


def _entry(sat_id: str) -> dict:
    entry = sip.load_satellite(sat_id)
    assert entry is not None, sat_id
    return entry


def _history_mode_from_script(root: Path, sat_id: str) -> str:
    fn = subprocess.run(
        ["sed", "-n", "/^_satellite_history_mode()/,/^}/p", str(ROOT / "scripts/mirror_satellites.sh")],
        check=True, capture_output=True, text=True,
    ).stdout
    out = subprocess.run(
        ["bash", "-c", f'ROOT="$1"; {fn}\n_satellite_history_mode "$2"', "_", str(root), sat_id],
        check=True, capture_output=True, text=True,
    )
    return out.stdout.strip()


def test_every_satellite_in_the_map_is_live() -> None:
    data = yaml.safe_load((ROOT / "scripts/satellite-map.yaml").read_text(encoding="utf-8"))
    modes = {s["id"]: sip.history_mode(s) for s in data["satellites"]}
    assert modes and set(modes.values()) == {"live"}, {k: v for k, v in modes.items() if v != "live"}


def test_mirror_script_defaults_to_live_and_honours_an_explicit_mirror(tmp_path: Path) -> None:
    assert _history_mode_from_script(ROOT, "aimarket-hub") == "live"
    assert _history_mode_from_script(ROOT, "no-such-satellite") == "live"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/satellite-map.yaml").write_text(
        "satellites:\n  - id: a\n    history: mirror\n  - id: b\n", encoding="utf-8",
    )
    assert _history_mode_from_script(tmp_path, "a") == "mirror"
    assert _history_mode_from_script(tmp_path, "b") == "live"


def test_an_unreadable_map_never_selects_the_force_push_mode(tmp_path: Path) -> None:
    assert _history_mode_from_script(tmp_path, "aimarket-hub") == "live"


@pytest.mark.parametrize(
    ("sat_id", "repo_path", "mono_path"),
    [
        ("metis", "metis/api/app.py", "metis/metis/api/app.py"),
        ("aimarket-desktop", "apps/pulse/lib/main.dart", "desktop-integrations/pulse/lib/main.dart"),
        ("aimarket-desktop", "packages/core/x.dart", "desktop-integrations/packages/core/x.dart"),
        ("aimarket-desktop", "README.md", "desktop-integrations/README.md"),
        ("aimarket-plugins", "plugins/aimarket-provenance/p.py", "aimarket-hub/plugins/aimarket-provenance/p.py"),
        ("aimarket-plugins", "plugins/other/q.py", "plugins/other/q.py"),
        ("attested-memory", "apps/team-memory-os/x.ts", "team-memory-os/x.ts"),
        ("attested-memory", "src/hub.py", "attested/attested-memory-hub/src/hub.py"),
        ("logos", "vendor/oracle-core/oracle_core/x.py", "oracles/core/oracle_core/x.py"),
        ("profile", "README.md", "scripts/profile-readme/README.md"),
        ("profile", "assets/a.svg", "scripts/profile-readme/assets/a.svg"),
        ("aimarket-courses", "orchestration-course/README.md", "courses/orchestration-course/README.md"),
    ],
)
def test_satellite_paths_map_back_to_the_monorepo(sat_id: str, repo_path: str, mono_path: str) -> None:
    assert sip.map_path(repo_path, sip.import_path_map(_entry(sat_id))) == mono_path


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_import_writes_a_patch_with_monorepo_paths(tmp_path: Path) -> None:
    sat = tmp_path / "aimarket-plugins"
    sat.mkdir()
    _git(sat, "init", "-q", "-b", "main")
    (sat / "plugins/aimarket-provenance").mkdir(parents=True)
    (sat / "plugins/aimarket-provenance/p.py").write_text("x = 1\n")
    (sat / "README.md").write_text("plugins\n")
    (sat / "LICENSE").write_text("MIT\n")
    _git(sat, "add", "-A")
    _git(sat, "commit", "-q", "-m", SYNC_SUBJECT)
    # The merged pull request: one file under each mapping, plus a generated file.
    (sat / "plugins/aimarket-provenance/new_check.py").write_text("y = 2\n")
    (sat / "plugins/contributed").mkdir()
    (sat / "plugins/contributed/plugin.py").write_text("z = 3\n")
    (sat / "LICENSE").write_text("MIT, edited\n")
    _git(sat, "add", "-A")
    _git(sat, "commit", "-q", "-m", "Add a provenance check (#12)")

    out_dir = tmp_path / "out"
    env = {**os.environ, "SATELLITE_CLONE_URL": sat.as_uri(), "IMPORT_OUTDIR": str(out_dir)}
    run = subprocess.run(
        ["bash", str(ROOT / "scripts/import_satellite_pr.sh"), "aimarket-plugins"],
        capture_output=True, text=True, env=env, cwd=tmp_path,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    patch = (out_dir / "aimarket-plugins.patch").read_text()
    headers = [line for line in patch.splitlines() if line.startswith("diff --git ")]
    assert "diff --git a/aimarket-hub/plugins/aimarket-provenance/new_check.py " \
           "b/aimarket-hub/plugins/aimarket-provenance/new_check.py" in headers
    assert "diff --git a/plugins/contributed/plugin.py b/plugins/contributed/plugin.py" in headers
    assert len(headers) == 2, headers
    assert "LICENSE" in run.stdout  # reported as left out, not silently dropped
    assert "git -C" in run.stdout and "apply --3way" in run.stdout
