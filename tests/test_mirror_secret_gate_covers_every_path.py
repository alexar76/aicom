"""The mirror secret scan must gate every publish path, not one of them.

`scripts/verify_mirror_secrets.sh` existed and was called twice: once inside
`export_simple`, and once inside the `live` branch of `_commit_and_push`. The other nine
publish paths — lottery, oracles, platon, plugins, the desktop monorepo, the courses
monorepo, wiki, wiki_argus, profile — each rsync with their own hand-written exclude list
and pushed without ever running it.

That matters more here than the file count suggests: rsync copies the WORKING TREE, so
`.gitignore` does not protect a mirror, and this is the same mechanism that published a real
key once (see the memory note on the trimmed public mirror). A force-push afterwards does
not un-publish a secret.

Every export_* funnels through `_commit_and_push`, so the gate belongs there — once,
unconditionally, before `git add -A`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mirror_satellites.sh"


@pytest.fixture(scope="module")
def script() -> str:
    if not SCRIPT.is_file():
        pytest.skip("mirror_satellites.sh not present")
    return SCRIPT.read_text(encoding="utf-8")


def _commit_and_push_body(src: str) -> str:
    """The function's own text. It opens with `(` (a subshell, so its `cd` cannot leak),
    so the body ends at the matching top-level `)`."""
    start = src.index("_commit_and_push()")
    rest = src[start:]
    end = rest.index("\n)\n")
    return rest[: end + 3]


def test_the_secret_scan_runs_inside_commit_and_push(script):
    body = _commit_and_push_body(script)
    assert "verify_mirror_secrets.sh" in body, (
        "the only place every publish path passes through does not run the secret scan"
    )


def _code_only(body: str) -> str:
    """Comments mention these commands too — blank them so offsets mean execution order."""
    out = []
    for line in body.splitlines():
        out.append("" if line.lstrip().startswith("#") else line)
    return "\n".join(out)


def test_the_scan_runs_before_every_staging_and_push_in_the_function(script):
    """There are three `git add -A` on different branches through this function, and the
    scan used to sit after the first two — inside the `live` branch only."""
    body = _code_only(_commit_and_push_body(script))
    scan_at = body.index("verify_mirror_secrets.sh")
    stages = [m for m in _finditer(body, "git add -A")]
    assert stages, "no staging found — the extraction is wrong, not the script"
    assert scan_at < min(stages), (
        f"the scan is at {scan_at} but staging starts at {min(stages)}: "
        f"{len([s for s in stages if s < scan_at])} of {len(stages)} staging points "
        "happen before anything is scanned"
    )


def test_the_scan_is_not_duplicated_per_history_mode(script):
    """One scan per push. Two meant the placement was per-branch rather than shared."""
    body = _code_only(_commit_and_push_body(script))
    assert body.count("verify_mirror_secrets.sh") == 1, (
        "more than one scan in the function — it is still keyed to a branch"
    )


def _finditer(haystack: str, needle: str) -> list[int]:
    out, i = [], haystack.find(needle)
    while i >= 0:
        out.append(i)
        i = haystack.find(needle, i + 1)
    return out


def test_every_publish_path_goes_through_the_gated_helper(script):
    """If a future export_* pushed on its own, the gate above would not cover it."""
    exports = re.findall(r"^(export_[a-z_]+)\(\)", script, re.M)
    assert len(exports) >= 8, exports
    body = _commit_and_push_body(script)
    outside = script.replace(body, "")
    stray = [
        line.strip()
        for line in outside.splitlines()
        if re.search(r"^\s*git\s+(-c[^&|;]*\s)?push\b", line)
    ]
    assert not stray, f"publish paths that bypass the gated helper: {stray}"
