"""Every CI workflow must parse as YAML — GitHub silently ignores ones that do not.

`mirror-satellites.yml` embedded a shell heredoc whose Python body sat at column 1.
A column-1 line ends a `run: |` block scalar, so the file stopped being valid YAML
after that point and GitHub rejected the whole workflow: satellite mirroring had no
CI at all, and nothing said so — an invalid workflow is not a failed run, it is an
absent one, which is why the dashboards stayed green.

This also asserts the shape a workflow must have (`on`, `jobs`, and a `run`/`uses`
per step), so a file that parses into something GitHub cannot schedule still fails.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIRS = (ROOT / ".github" / "workflows", ROOT / ".gitea" / "workflows")


def _workflows() -> list[Path]:
    out: list[Path] = []
    for d in WORKFLOW_DIRS:
        if d.is_dir():
            out += sorted(p for p in d.rglob("*.yml")) + sorted(p for p in d.rglob("*.yaml"))
    return out


def test_there_are_workflows_to_check():
    assert _workflows(), "no workflow files found — the guard would pass vacuously"


@pytest.mark.parametrize("wf", _workflows(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_workflow_parses_and_has_jobs(wf: Path):
    try:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - the failure we are guarding
        pytest.fail(f"{wf.relative_to(ROOT)} is not valid YAML: {exc}")

    assert isinstance(doc, dict), f"{wf.relative_to(ROOT)} did not parse into a mapping"
    # PyYAML reads a bare `on:` key as the boolean True; either spelling is fine.
    assert "on" in doc or True in doc, f"{wf.relative_to(ROOT)} has no trigger (`on:`)"
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and jobs, f"{wf.relative_to(ROOT)} declares no jobs"

    for name, job in jobs.items():
        if not isinstance(job, dict) or "uses" in job:
            continue  # reusable-workflow call: it has no steps of its own
        for i, step in enumerate(job.get("steps") or []):
            assert isinstance(step, dict), f"{wf.name}:{name} step {i} is not a mapping"
            assert "run" in step or "uses" in step, (
                f"{wf.name}:{name} step {i} has neither `run` nor `uses` — a column-1 "
                "heredoc line inside a `run: |` block is the usual cause"
            )
