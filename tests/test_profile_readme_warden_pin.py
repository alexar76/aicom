"""The profile README's WARDEN command names the version in warden/package.json.

On 2026-11-15, after WARDEN 0.27.0 reached npm, the GitHub profile still offered
`npx -y @aimarket/warden@0.26.0 scan` in all five languages: the release bumped every pin inside
warden/, and the profile lives outside it. A release that bumps warden/package.json now fails here
until the profile names the same version.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "scripts" / "profile-readme"
LANGUAGES = ("", ".ru", ".es", ".fr", ".zh")
PIN = re.compile(r"@aimarket/warden@(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)")


def _warden_version() -> str:
    return json.loads((ROOT / "warden" / "package.json").read_text(encoding="utf-8"))["version"]


@pytest.mark.parametrize("suffix", LANGUAGES, ids=lambda s: s.lstrip(".") or "en")
def test_profile_warden_command_names_the_current_version(suffix):
    text = (PROFILE_DIR / f"README{suffix}.md").read_text(encoding="utf-8")
    pins = PIN.findall(text)
    assert pins, f"README{suffix}.md no longer names an @aimarket/warden version"
    assert set(pins) == {_warden_version()}, (
        f"README{suffix}.md pins {sorted(set(pins))}, warden/package.json is {_warden_version()}"
    )
