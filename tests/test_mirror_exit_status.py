"""An aggregate mirror failure must reach the calling publish script."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _run_mirror(
    tmp_path: Path, *, missing_source: bool, through_wrapper: bool = False,
) -> subprocess.CompletedProcess[str]:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts" / "mirror_satellites.sh", scripts / "mirror_satellites.sh")

    # Use real satellite definitions, reduced to two active exports and one
    # optional export whose missing source must not affect the result.
    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text())
    satellites = {sat["id"]: sat for sat in data["satellites"]}
    optional = {**satellites["aimarket-hub"], "optional": True}
    (scripts / "satellite-map.yaml").write_text(yaml.safe_dump({
        "org": "alexar76",
        "satellites": [satellites["acex"], satellites["ai-service-mesh"], optional],
    }))
    if not missing_source:
        (tmp_path / "acex").mkdir()
    (tmp_path / "ai-service-mesh").mkdir()

    entrypoint = scripts / "mirror_satellites.sh"
    if through_wrapper:
        entrypoint = scripts / "publish_all_repos.sh"
        shutil.copy2(ROOT / "scripts" / "publish_all_repos.sh", entrypoint)
        # Keep the integration focused on mirror status propagation. The factory
        # stub accepts only dry-run, and the real wrapper skips metadata writes.
        (scripts / "publish_aicom_factory.sh").write_text(
            '#!/usr/bin/env bash\n[[ "$#" -eq 1 && "$1" == --dry-run ]] || exit 97\n'
        )

    env = {**os.environ, "GH_PAT": "", "GITHUB_TOKEN": ""}
    return subprocess.run(
        ["bash", str(entrypoint), "--dry-run"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20,
    )


def test_all_satellites_returns_failure_when_one_export_fails(tmp_path: Path) -> None:
    result = _run_mirror(tmp_path, missing_source=True)
    assert "SKIP: source missing:" in result.stdout
    assert "1 satellite(s) had errors." in result.stdout
    # A failed export must not prevent the remaining exports from being checked.
    assert "[dry-run] would rsync ai-service-mesh/" in result.stdout
    assert result.returncode != 0, result.stdout + result.stderr


def test_all_satellites_returns_success_when_every_export_succeeds(tmp_path: Path) -> None:
    result = _run_mirror(tmp_path, missing_source=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All satellites mirrored successfully." in result.stdout
    assert "[dry-run] would rsync acex/" in result.stdout
    assert "[dry-run] would rsync ai-service-mesh/" in result.stdout
    assert "SKIP: source missing:" not in result.stdout


@pytest.mark.parametrize("missing_source", [True, False])
def test_publish_wrapper_propagates_mirror_status(tmp_path: Path, missing_source: bool) -> None:
    result = _run_mirror(tmp_path, missing_source=missing_source, through_wrapper=True)
    assert "[dry-run] would rsync ai-service-mesh/" in result.stdout
    assert "Step 2/2: push trimmed factory aicom" in result.stdout
    if missing_source:
        assert result.returncode != 0, result.stdout + result.stderr
        assert "publish_all_repos finished with 1 error(s)." in result.stdout
        assert "publish_all_repos finished successfully" not in result.stdout
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "publish_all_repos finished successfully" in result.stdout
