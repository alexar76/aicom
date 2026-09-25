"""What GitHub will accept from scripts/satellite-map.yaml when a satellite is published.

HISTOR's first publish failed with a bare "Repository creation failed." (HTTP 422): its map
description was 387 characters, GitHub's limit is 350, and the helper printed only the top-level
message, not the per-field error that said why.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ensure_github_repo import GITHUB_DESCRIPTION_MAX, clamp_description, error_detail  # noqa: E402


def _satellites():
    data = yaml.safe_load((ROOT / "scripts" / "satellite-map.yaml").read_text(encoding="utf-8"))
    return [s for s in (data.get("satellites") or data) if isinstance(s, dict)]


def test_every_published_description_fits_github():
    too_long = {s["id"]: len(s.get("description") or "") for s in _satellites()
                if s.get("github_published") and len(s.get("description") or "") > GITHUB_DESCRIPTION_MAX}
    assert not too_long, f"GitHub refuses descriptions over {GITHUB_DESCRIPTION_MAX} characters: {too_long}"


def test_a_long_description_is_cut_at_a_word_not_refused():
    text = "word " * 200
    out = clamp_description(text)
    assert len(out) <= GITHUB_DESCRIPTION_MAX and out.endswith("…") and not out.endswith(" …")
    assert clamp_description("  short\n text ") == "short text"


def test_the_error_says_why():
    payload = {"message": "Repository creation failed.",
               "errors": [{"resource": "Repository", "code": "custom", "field": "description",
                           "message": "description is too long (maximum is 350 characters)"}]}
    assert "maximum is 350" in error_detail(payload)


def test_a_422_without_a_reason_says_what_to_do(monkeypatch):
    """HISTOR's repo creation kept failing with a bare 422 and no errors: the token could push but not create."""
    import ensure_github_repo as egr

    calls = []

    def fake_request(method, url, token, body=None):
        calls.append((method, url))
        if method == "GET":
            return 404, {}
        return (404, {}) if "/orgs/" in url else (422, {"message": "Repository creation failed."})

    monkeypatch.setenv("GH_PAT", "not-a-real-token")
    monkeypatch.setattr(egr, "_request", fake_request)
    monkeypatch.setattr(egr, "_token_kind", lambda token: "fine-grained token of alexar76")
    ok, msg = egr.ensure_repo("alexar76", "histor", description="x")
    assert not ok and "github.com/new" in msg and "fine-grained token of alexar76" in msg
