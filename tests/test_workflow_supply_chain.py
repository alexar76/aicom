"""Every CI workflow in the tree — root, satellites, courses, Gitea, templates — is held
to the same supply-chain rules, because each satellite is mirrored to its own public
repo and runs there with that repo's tokens.

* every third-party action is pinned to a commit (a tag is whatever its owner says today);
* the workflow's default token is read-only — a write scope is granted on the one job
  that needs it;
* a job that can mint an OIDC token (`id-token: write`) installs nothing and runs no
  tests: any package's install script could ask for a token for any audience, and the
  MCP registry gives an `io.github.alexar76/*` token to any repo of the owner;
* a dispatch input or PR text never reaches a shell by `${{ }}` splicing;
* a job that publishes to a registry runs in a named environment (where protection
  rules live);
* a downloaded archive or installer is checked against a pinned digest before it runs;
* `contents: write` is held only by a job that actually writes (release, push);
* another repo cloned into CI is checked out at a commit, not at whatever HEAD is.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "pin_workflow_actions", ROOT / "scripts" / "security" / "pin_workflow_actions.py"
)
pins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pins)

WORKFLOW_PATH = re.compile(r"(^|/)(\.github|\.gitea|_github)/workflows/[^/]+\.ya?ml$")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if "/node_modules/" not in p]


TRACKED = _tracked()
WORKFLOWS = sorted(p for p in TRACKED if WORKFLOW_PATH.search(p))
# Scripts that write workflow YAML for a satellite, a course or a starter repo.
GENERATOR_SUFFIXES = (".py", ".sh", ".mjs", ".js", ".ts", ".yml", ".yaml", ".j2", ".tmpl")
SELF = {"scripts/security/pin_workflow_actions.py", "tests/test_workflow_supply_chain.py"}


def _load(path: str) -> dict:
    doc = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _jobs(doc: dict) -> dict:
    jobs = doc.get("jobs") or {}
    return {k: v for k, v in jobs.items() if isinstance(v, dict)}


def _steps(job: dict) -> list[dict]:
    return [s for s in job.get("steps") or [] if isinstance(s, dict)]


def _runs(job: dict) -> list[str]:
    return [str(s["run"]) for s in _steps(job) if s.get("run")]


def _effective(doc: dict, job: dict) -> dict:
    perms = job.get("permissions", doc.get("permissions"))
    return perms if isinstance(perms, dict) else {}


def test_the_tree_has_workflows_to_check():
    assert len(WORKFLOWS) > 100


def test_every_action_is_pinned_to_a_commit():
    bad = []
    for path in TRACKED:
        if path in SELF or not path.endswith(GENERATOR_SUFFIXES):
            continue
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        if "uses:" not in text:
            continue
        bad += [f"{path}: {ref}" for ref in pins.unpinned(text)]
    assert not bad, (
        "unpinned actions (run scripts/security/pin_workflow_actions.py on these files):\n"
        + "\n".join(bad)
    )


@pytest.mark.parametrize("path", WORKFLOWS)
def test_the_default_token_is_read_only(path):
    doc = _load(path)
    assert "permissions" in doc, f"{path}: no top-level permissions — add `permissions: {{contents: read}}`"
    top = doc["permissions"]
    assert isinstance(top, dict), f"{path}: top-level permissions must be a mapping, not {top!r}"
    writes = sorted(k for k, v in top.items() if v not in ("read", "none"))
    assert not writes, f"{path}: top-level grants {writes}; grant them on the job that needs them"


INSTALLS = re.compile(
    r"\b(npm (ci|install|i|test|run)\b|npx\b|pnpm\b|yarn\b|bun (install|run)\b|pip3? install|"
    r"python3? -m pip\b|uv (sync|run|pip)\b|uvx\b|poetry\b|pytest\b|tox\b|flutter (pub|build|test)\b|"
    r"dart test\b|cargo (build|test|install|run)\b|cargo publish\b(?![^\n]*--no-verify)|"
    r"go (build|test|get|run)\b|make\b)"
)
# `dart pub get` is not listed: pub runs no package code at resolution time.


@pytest.mark.parametrize("path", WORKFLOWS)
def test_a_job_that_can_mint_oidc_tokens_runs_no_third_party_code(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        if _effective(doc, job).get("id-token") != "write":
            continue
        hits = sorted({m.group(0) for r in _runs(job) for m in INSTALLS.finditer(r)})
        assert not hits, (
            f"{path}:{name} holds id-token: write and runs {hits}; "
            "build/test in a job without it and hand the result over as an artifact"
        )


SPLICE = re.compile(
    r"\$\{\{\s*(inputs\.|github\.event\.inputs\.|github\.head_ref|"
    r"github\.event\.(pull_request|issue|comment|review|review_comment|head_commit|discussion)\.)"
)


@pytest.mark.parametrize("path", WORKFLOWS)
def test_no_input_or_pr_text_is_spliced_into_a_shell(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        for run in _runs(job):
            m = SPLICE.search(run)
            assert not m, f"{path}:{name} splices `{m.group(0)}…` into a shell; pass it through env:"


def _publishes(job: dict) -> bool:
    for step in _steps(job):
        uses = str(step.get("uses", ""))
        if uses.startswith(("pypa/gh-action-pypi-publish@", "rust-lang/crates-io-auth-action@")):
            return True
        if uses.startswith("docker/build-push-action@") and str((step.get("with") or {}).get("push", "")).lower() not in ("", "false"):
            return True
        run = str(step.get("run", ""))
        if re.search(
            r"\b(npm publish|cargo publish|dart pub publish|flutter pub publish|mcp-publisher publish|twine upload)\b"
            r"(?![^\n]*--dry-run)",
            run,
        ):
            return True
    return False


@pytest.mark.parametrize("path", WORKFLOWS)
def test_a_registry_publish_runs_in_an_environment(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        if _publishes(job):
            assert job.get("environment"), (
                f"{path}:{name} publishes to a registry outside an environment; "
                "add `environment: release` so its protection rules apply"
            )


DOWNLOADS = re.compile(r"\b(curl|wget)\b")
INTO_RUNNER = re.compile(r"\|\s*(sudo\s+)?(sh|bash|tar|python3?)\b")


@pytest.mark.parametrize("path", WORKFLOWS)
def test_no_download_runs_unchecked(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        for run in _runs(job):
            for line in run.replace("\\\n", " ").splitlines():
                m = INTO_RUNNER.search(line) if DOWNLOADS.search(line) else None
                assert not m, (
                    f"{path}:{name} pipes a download straight into `{m.group(2)}`; "
                    "fetch a versioned file, `sha256sum -c` it against a pinned digest, then run it"
                )


WRITES_CONTENTS = re.compile(r"\b(git\w* (-C \S+ )?push|gh release|gh pr|gh api\b[^\n]*-X\s*(POST|PUT|PATCH|DELETE))")
SCRIPT_CALL = re.compile(r"(?:\bbash|\bsh|\bpython3?|^|\s)\s*\.?/?((?:[\w.-]+/)*[\w.-]+\.(?:sh|py))\b", re.M)


def _repo_root(path: str) -> Path:
    """The repo a workflow runs in: the directory that holds its .github/.gitea folder."""
    return (ROOT / path).parent.parent.parent


def _writes(path: str, job: dict) -> bool:
    if any(
        str(s.get("uses", "")).startswith(("softprops/action-gh-release@", "peter-evans/create-pull-request@"))
        for s in _steps(job)
    ):
        return True
    for run in _runs(job):
        if WRITES_CONTENTS.search(run):
            return True
        # one level into the repo's own scripts the step calls
        for m in SCRIPT_CALL.finditer(run):
            script = _repo_root(path) / m.group(1)
            if script.is_file() and WRITES_CONTENTS.search(script.read_text(encoding="utf-8", errors="replace")):
                return True
    return False


@pytest.mark.parametrize("path", WORKFLOWS)
def test_contents_write_is_held_only_by_a_job_that_writes(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        if _effective(doc, job).get("contents") == "write":
            assert _writes(path, job), f"{path}:{name} holds contents: write but never pushes or releases; make it read"


CLONE = re.compile(r"git clone\b[^\n]*https://github\.com/[^\s]+")


@pytest.mark.parametrize("path", WORKFLOWS)
def test_a_cloned_repo_is_checked_out_at_a_commit(path):
    doc = _load(path)
    for name, job in _jobs(doc).items():
        for run in _runs(job):
            for m in CLONE.finditer(run):
                assert re.search(r"(checkout|fetch[^\n]*origin)\s+[0-9a-f]{40}\b", run[m.end():]), (
                    f"{path}:{name} clones `{m.group(0)}` at its moving HEAD; "
                    "check out a pinned commit after the clone"
                )


# ── Workflows the tree writes at publish time ─────────────────────────────────────────
# The mirror and the course scaffold generate CI for repos that exist only on GitHub, so
# the rules above would never see them in the tree.

def _generated() -> list[tuple[str, str]]:
    out = []
    mirror = (ROOT / "scripts" / "mirror_satellites.sh").read_text(encoding="utf-8")
    heredoc = re.compile(r"cat > \"[^\"]*/\.github/workflows/([\w.-]+)\" <<'(\w+)'\n(.*?)\n\2\n", re.S)
    for i, m in enumerate(heredoc.finditer(mirror)):
        out.append((f"mirror_satellites.sh:{m.group(1)}#{i}", m.group(3)))
    spec = importlib.util.spec_from_file_location(
        "scaffold_course", ROOT / "courses" / "_tooling" / "scaffold_course.py")
    scaffold = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scaffold)
    for course in scaffold._load_catalog():
        out.append((f"scaffold_course.py:{course.get('folder') or course.get('id')}", scaffold._ci_yml(course)))
    return out


GENERATED = _generated()


def test_the_generators_were_found():
    assert sum(1 for name, _ in GENERATED if name.startswith("mirror_satellites.sh")) >= 5
    assert any(name.startswith("scaffold_course.py") for name, _ in GENERATED)


@pytest.mark.parametrize("name,text", GENERATED, ids=[n for n, _ in GENERATED])
def test_a_generated_workflow_follows_the_same_rules(name, text):
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict), name
    assert not pins.unpinned(text), f"{name}: {pins.unpinned(text)}"
    top = doc.get("permissions")
    assert isinstance(top, dict) and all(v in ("read", "none") for v in top.values()), (
        f"{name}: the default token must be read-only, got {top!r}")
    for job_name, job in _jobs(doc).items():
        if _effective(doc, job).get("id-token") == "write":
            hits = sorted({m.group(0) for r in _runs(job) for m in INSTALLS.finditer(r)})
            assert not hits, f"{name}:{job_name} holds id-token: write and runs {hits}"
        for run in _runs(job):
            assert not SPLICE.search(run), f"{name}:{job_name} splices input into a shell"
