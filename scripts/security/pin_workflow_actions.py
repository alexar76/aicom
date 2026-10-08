#!/usr/bin/env python3
"""Pin every third-party action a workflow (or a workflow generator) names to a commit.

A tag or branch (`actions/checkout@v4`, `pypa/gh-action-pypi-publish@release/v1`,
`aquasecurity/trivy-action@master`) is whatever its owner points it at on the day the job
runs, so a hijacked tag runs inside our publish jobs with their registry credentials.
This rewrites `uses: owner/repo@<tag>` to `uses: owner/repo@<40-hex sha>  # <version>`
from the table below, in workflow YAML and in the scripts that write workflow YAML.

    python3 scripts/security/pin_workflow_actions.py FILE...      # rewrite in place
    python3 scripts/security/pin_workflow_actions.py --check FILE...

A ref missing from PINS is reported, never guessed: resolve it once with
`git ls-remote https://github.com/<owner>/<repo>` (take the `^{}` line of a tag),
add it here, and run again. tests/test_workflow_supply_chain.py holds every workflow
in the tree to a pinned ref.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# owner/repo@ref -> (commit, the release that commit is)
PINS: dict[str, tuple[str, str]] = {
    "actions/checkout@v4": ("11bd71901bbe5b1630ceea73d27597364c9af683", "v4.2.2"),
    "actions/checkout@v5": ("fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09", "v5.1.0"),
    "actions/setup-python@v5": ("a26af69be951a213d495a4c3e4e4022e16d87065", "v5.6.0"),
    "actions/setup-python@v6": ("ece7cb06caefa5fff74198d8649806c4678c61a1", "v6.3.0"),
    "actions/setup-node@v4": ("49933ea5288caeca8642d1e84afbd3f7d6820020", "v4.4.0"),
    "actions/setup-node@v7": ("949feb2413d6458794dcd2491c4babbbce0c15c1", "v7.1.0"),
    "actions/setup-java@v4": ("cf277c60eb25467037889841efdb72551f06f6c3", "v4.9.1"),
    "actions/upload-artifact@v4": ("ea165f8d65b6e75b540449e92b4886f43607fa02", "v4.6.2"),
    "actions/download-artifact@v4": ("d3f86a106a0bac45b974a628896c90dbdf5c8093", "v4.3.0"),
    "actions/upload-pages-artifact@v3": ("56afc609e74202658d3ffba0e8f6dda462b719fa", "v3.0.1"),
    "actions/configure-pages@v5": ("983d7736d9b0ae728b81ab479565c72886d7745b", "v5.0.0"),
    "actions/deploy-pages@v4": ("d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e", "v4.0.5"),
    "astral-sh/setup-uv@v6": ("d0cc045d04ccac9d8b7881df0226f9e82c39688e", "v6.8.0"),
    "aquasecurity/trivy-action@master": ("ed142fd0673e97e23eac54620cfb913e5ce36c25", "v0.36.0"),
    "dart-lang/setup-dart@v1": ("e51d8e571e22473a2ddebf0ef8a2123f0ab2c02c", "v1.7.0"),
    "docker/build-push-action@v6": ("10e90e3645eae34f1e60eeb005ba3a3d33f178e8", "v6.19.2"),
    "docker/login-action@v3": ("c94ce9fb468520275223c153574b00df6fe4bcc9", "v3.7.0"),
    "dtolnay/rust-toolchain@stable": ("89b12181fb390509a0842a86cc55eeb8eb928c1d", "stable 2026-10-01"),
    "foundry-rs/foundry-toolchain@v1": ("de808b1eea699e761c404bda44ba8f21aba30b2c", "v1.3.1"),
    "pypa/gh-action-pypi-publish@release/v1": ("dc37677b2e1c63e2034f94d8a5b11f265b73ba33", "v1.14.2"),
    "rust-lang/crates-io-auth-action@v1": ("c6f97d42243bad5fab37ca0427f495c86d5b1a18", "v1.0.5"),
    "softprops/action-gh-release@v2": ("c062e08bd532815e2082a85e87e3ef29c3e6d191", "v2.0.8"),
    "subosito/flutter-action@v2": ("1a449444c387b1966244ae4d4f8c696479add0b2", "v2.23.0"),
}

# `uses: owner/repo[/path]@ref` followed by an optional trailing `# comment`. The ref and
# the comment stop at a quote or backslash so the same pattern works inside generator
# string literals ("      - uses: actions/checkout@v4\n").
USES = re.compile(
    r"(?P<lead>uses:\s*)(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@(?P<ref>[^\s\"'\\#]+)"
    r"(?P<comment>[ \t]*#[^\n\"'\\]*)?"
)
SHA = re.compile(r"^[0-9a-f]{40}$")


def unpinned(text: str) -> list[str]:
    return [f"{m['action']}@{m['ref']}" for m in USES.finditer(text) if not SHA.match(m["ref"])]


def pin(text: str) -> tuple[str, list[str]]:
    missing: list[str] = []

    def sub(m: re.Match[str]) -> str:
        if SHA.match(m["ref"]):
            return m.group(0)
        key = f"{m['action']}@{m['ref']}"
        if key not in PINS:
            missing.append(key)
            return m.group(0)
        sha, version = PINS[key]
        return f"{m['lead']}{m['action']}@{sha}  # {version}"

    return USES.sub(sub, text), missing


def main(argv: list[str]) -> int:
    check = "--check" in argv
    paths = [Path(a) for a in argv if a != "--check"]
    bad = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if check:
            for ref in unpinned(text):
                print(f"{path}: {ref}")
                bad += 1
            continue
        new, missing = pin(text)
        for ref in missing:
            print(f"{path}: no pin for {ref} — add it to PINS", file=sys.stderr)
            bad += 1
        if new != text:
            path.write_text(new, encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
