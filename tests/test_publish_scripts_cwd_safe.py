"""The publish scripts must not depend on the current working directory.

**What went wrong.** `scripts/mirror_satellites.sh` read its satellite map as
`Path("scripts/satellite-map.yaml")` — relative to the cwd — while `_commit_and_push` did
`cd "$clone"` and never came back. There is exactly one `cd "$ROOT"` in that script, on line 18,
at startup. So the first satellite to be pushed moved the shell into its clone, and every later
satellite read the map from in there.

That produced two failures, and the loud one was the harmless one:

* **The traceback.** `FileNotFoundError: 'scripts/satellite-map.yaml'`, printed once per satellite
  and non-fatal, because the main loop is `export_satellite "$sat_id" || errors=$((errors + 1))`
  and that `||` disables `set -e` for the whole dynamic extent of the call.
* **The silent one.** The failed call is `extra_excludes="$(_python_map exclude-paths "$id")"`,
  so `extra_excludes` became the empty string — and an empty exclude list looks exactly like a
  satellite that needs no exclusions. That list is what keeps `helios/client_secret.json`,
  `skopos/servers.yaml`, `skopos/agent.yaml` and `argus/argus.config.json` out of a public
  mirror. Nothing leaked, because `mirror_satellites.sh` also carries an unconditional base
  exclude list (`.env`, `*.key`, `*.pem`, `*.sqlite3`, `data/secrets`, …) and a hard secret gate
  before every push — but the per-satellite layer had quietly stopped existing.

A third variant is nastier than either: line ~307 *copies* the map into the clone. When that copy
is present, the relative read does not fail — it succeeds against the wrong file.

**What is asserted here.** Both halves, because either alone leaves the trap armed: reads are
anchored (so a stray `cd` cannot matter), and the `cd` is contained (so an unanchored read added
tomorrow cannot matter). The last test runs the real extracted helper from a foreign directory,
which is the only one of these that would catch a re-broken path that still *looks* anchored.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
MIRROR = ROOT / "scripts" / "mirror_satellites.sh"
MAP = ROOT / "scripts" / "satellite-map.yaml"

#: Scripts that read the satellite map and may cd elsewhere while doing it.
PUBLISH_SCRIPTS = (
    "scripts/mirror_satellites.sh",
    "scripts/publish_all_repos.sh",
    "scripts/publish_satellite.sh",
    "scripts/publish_github_io.sh",
    "scripts/publish_aicom_factory.sh",
    "security/publish_aicom_factory.sh",
    "scripts/mirror_to_gitea.sh",
    "scripts/push_gitea_monorepo.sh",
    "scripts/import_satellite_pr.sh",
    "scripts/tag_satellite_release.sh",
)

#: A relative read of a repo file, in either language. `Path("scripts/…")`, `open("scripts/…")`.
RELATIVE_READ = re.compile(
    r"""(?:Path|open)\(\s*["'](?!/)(?:\./)?(scripts|security|config)/[^"']+["']""")


def _scripts_present() -> list[str]:
    return [s for s in PUBLISH_SCRIPTS if (ROOT / s).is_file()]


def test_the_scripts_we_guard_actually_exist() -> None:
    """Renaming a script out from under this list would make the tests below pass on nothing."""
    present = _scripts_present()
    assert MIRROR.is_file(), "scripts/mirror_satellites.sh is gone — this whole file is stale"
    assert len(present) >= 5, (
        f"only {len(present)} of {len(PUBLISH_SCRIPTS)} guarded scripts exist: {present}. "
        f"Update PUBLISH_SCRIPTS rather than letting the coverage quietly shrink.")


@pytest.mark.parametrize("rel", _scripts_present())
def test_no_cwd_relative_repo_reads(rel: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    offenders = []
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if RELATIVE_READ.search(line):
            offenders.append(f"{rel}:{lineno}: {stripped}")
    assert not offenders, (
        "these reads resolve against the current directory, which these scripts change:\n  "
        + "\n  ".join(offenders)
        + "\n\nAnchor them: pass the repo root in through the environment "
          '(AICOM_ROOT="$ROOT" python3 - …) and build the path from it, or use $ROOT directly in '
          "an unquoted heredoc.")


def test_commit_and_push_cannot_leak_its_cd() -> None:
    """`_commit_and_push` cd's into the clone and has a dozen `return` paths. Restoring the
    directory on each of them by hand is the kind of thing that is right until someone adds a
    thirteenth, so the body must be a subshell."""
    text = MIRROR.read_text(encoding="utf-8")
    assert "_commit_and_push() (" in text, (
        "_commit_and_push no longer has a subshell body. It runs `cd \"$clone\"`, so with a "
        "`{ … }` body that cd leaks into the caller and every satellite after the first one "
        "runs from the previous satellite's clone.")
    assert "_commit_and_push() {" not in text


def test_every_cd_in_mirror_is_anchored_or_contained() -> None:
    """Catalogue every cd. The only unguarded one may be the `cd "$ROOT"` at startup."""
    lines = MIRROR.read_text(encoding="utf-8").splitlines()
    leaks = []
    subshell_fns = {m.start() for m in re.finditer(r"^[a-z_]+\(\) \(", MIRROR.read_text(), re.M)}
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not re.match(r"^(cd|pushd)\s", stripped) or stripped.startswith("#"):
            continue
        if stripped in ('cd "$ROOT"', "cd \"$ROOT\""):
            continue
        # Which function encloses it, and is that function's body a subshell?
        enclosing = None
        for prev in range(lineno - 1, 0, -1):
            m = re.match(r"^([a-z_]+)\(\)\s*([({])", lines[prev - 1])
            if m:
                enclosing = m
                break
        if enclosing is None or enclosing.group(2) != "(":
            leaks.append(f"mirror_satellites.sh:{lineno}: {stripped}"
                         f"  (in {enclosing.group(1) if enclosing else 'top level'})")
    assert not leaks, (
        "these directory changes escape into the caller:\n  " + "\n  ".join(leaks)
        + "\n\nGive the enclosing function a subshell body — `name() ( … )` — so the cd cannot "
          "outlive it.")
    assert subshell_fns, "no subshell-bodied functions found at all; the regex probably broke"


@pytest.mark.parametrize("field", ["exclude_paths", "paths"])
def test_map_entries_are_plain_strings(field: str) -> None:
    """A bare `:memory:` in YAML is a MAPPING, not a string. Unquoted, skopos's entry parsed as
    `{':memory': None}`, which stringified into two junk rsync excludes and dropped the real one."""
    m = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    bad = [(s["id"], repr(v)) for s in m.get("satellites", [])
           for v in (s.get(field) or []) if not isinstance(v, str)]
    assert not bad, (
        f"{field} entries that YAML did not parse as strings: {bad}. "
        f"Quote anything containing a colon.")


def test_exclude_paths_have_no_spaces() -> None:
    """The consumer does `IFS=' ' read -ra EXTRA <<< "$extra_excludes"`, so a path containing a
    space silently becomes two wrong excludes."""
    m = yaml.safe_load(MAP.read_text(encoding="utf-8"))
    bad = [(s["id"], v) for s in m.get("satellites", [])
           for v in (s.get("exclude_paths") or []) if isinstance(v, str) and " " in v]
    assert not bad, f"exclude_paths containing spaces would be split by the consumer: {bad}"


def _extract_python_map_body() -> str:
    """Pull the real heredoc out of the shell function, so the test runs the shipped code."""
    text = MIRROR.read_text(encoding="utf-8")
    m = re.search(r"^_python_map\(\)\s*\{\n.*?<<'PYEOF'\n(.*?)^PYEOF$", text, re.S | re.M)
    assert m, "could not find the _python_map heredoc — has the helper been restructured?"
    return m.group(1)


def test_python_map_reads_the_map_from_a_foreign_cwd() -> None:
    """The behavioural check, and the only one here that would catch a path that looks anchored
    but is not. Runs the shipped helper from a directory that has no `scripts/` in it at all."""
    body = _extract_python_map_body()
    with tempfile.TemporaryDirectory() as away:
        assert not (Path(away) / "scripts").exists()
        proc = subprocess.run(
            [sys.executable, "-c", body, "exclude-paths", "skopos"],
            cwd=away, capture_output=True, text=True,
            env={**os.environ, "AICOM_ROOT": str(ROOT)},
        )
        assert proc.returncode == 0, (
            f"_python_map failed when run from {away} instead of the repo root.\n"
            f"stderr: {proc.stderr.strip()}\n"
            f"This is the original bug: _commit_and_push cd's into the satellite clone, so by the "
            f"second satellite this is the directory the helper runs in.")
        out = proc.stdout.split()
        for required in (".env", "servers.yaml", "agent.yaml", "skopos.sqlite3"):
            assert required in out, (
                f"'{required}' missing from skopos's exclude list read from a foreign cwd: {out}.\n"
                f"An empty or truncated list here means secret-bearing files stop being excluded "
                f"from the public mirror.")


def test_python_map_says_so_when_the_map_is_missing() -> None:
    """Failing loudly matters more than usual here: the caller assigns this to `extra_excludes`,
    and the main loop's `|| errors=…` disables `set -e`, so a silent empty result sails straight
    through into an rsync with no exclusions."""
    body = _extract_python_map_body()
    with tempfile.TemporaryDirectory() as away:
        proc = subprocess.run(
            [sys.executable, "-c", body, "exclude-paths", "skopos"],
            cwd=away, capture_output=True, text=True,
            env={**os.environ, "AICOM_ROOT": away},  # a root with no satellite-map.yaml
        )
        assert proc.returncode != 0, "a missing satellite map must be an error, not empty output"
        assert not proc.stdout.strip(), (
            "a missing map produced output on stdout — the caller would treat it as an exclude list")
        assert "satellite-map.yaml" in proc.stderr, (
            f"the error should name the file it could not find; got: {proc.stderr.strip()!r}")
