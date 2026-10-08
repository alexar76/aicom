"""Second doors to a public remote carry the first door's guards, or go through it.

publish_satellite.sh used to rsync a satellite with its own exclude list (no per-satellite
exclude_paths, no github_published check) and push it; publish_github_io.sh pushed with
no secret scan and a PAT in the clone URL. Both now go through the guarded path.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", *args], cwd=ROOT, capture_output=True, text=True, timeout=300,
        env={**os.environ, **(env or {})},
    )


def test_publish_satellite_goes_through_the_mirror():
    out = _run("scripts/publish_satellite.sh", "warden", "--dry-run")
    assert out.returncode == 0, out.stderr
    # The canonical mirror's own dry-run plan, not a private rsync + push.
    assert "All repos: ./scripts/publish_all_repos.sh" in out.stdout
    # The old private path printed its own "Source:/Remote:" header before pushing.
    assert "Source:    " not in out.stdout


def test_publish_satellite_takes_no_freestyle_remote():
    out = _run("scripts/publish_satellite.sh", "warden", "--remote", "git@github.com:someone/else.git")
    assert out.returncode != 0
    assert "satellite-map" in out.stderr


def test_publish_github_io_scans_before_it_pushes(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        "<p>key: sk-or-v1-" + "a1b2c3d4" * 6 + "</p>\n", encoding="utf-8")
    bare = tmp_path / "alexar76.github.io.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    out = _run(
        "scripts/publish_github_io.sh",
        env={"GITHUB_IO_SOURCE": str(site), "GITHUB_IO_REMOTE": str(bare),
             "MIRROR_FORBIDDEN_HOSTS": "203.0.113.77", "GH_PAT": "", "TMPDIR": str(tmp_path)},
    )
    assert out.returncode != 0, out.stdout + out.stderr
    assert "failed the secret scan" in out.stderr, out.stderr
    log = subprocess.run(["git", "--git-dir", str(bare), "rev-list", "--all", "--count"],
                         capture_output=True, text=True)
    assert log.stdout.strip() in ("", "0")


def test_publish_github_io_keeps_the_token_out_of_the_url():
    text = (ROOT / "scripts" / "publish_github_io.sh").read_text(encoding="utf-8")
    # A token in the clone URL lands in .git/config and in any error git prints.
    assert "x-access-token:${" not in text
