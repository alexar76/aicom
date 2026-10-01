"""A preview iframe must not hand generated JS the factory's own origin.

`/api/sandbox/view/{id}` frames the untrusted preview with

    sandbox="allow-scripts allow-same-origin ..."

and an `src` on the factory's own origin (`sandbox_public_url` -> /api/sandbox/file/...).
Per the HTML sandbox spec, `allow-scripts` together with `allow-same-origin` on a
same-origin document leaves that document in its REAL origin — so the attribute provides no
isolation at all, and the generated script runs with factory-origin authority: same-origin
storage, and the factory's own API with whatever cookies the operator's browser carries.

Who supplies the script matters here: an ANONYMOUS caller can queue a build via
POST /api/public/generate-landing, and the operator later opens Admin -> Preview for it.

The safe default is an opaque origin. Preview fetch is restored without weakening the
sandbox: CORS for Origin: null on sandbox proxy paths (no credentials) + fetch shim
credentials:omit + X-Sandbox-Preview-Token. localStorage still needs an explicit
AIFACTORY_SANDBOX_PREVIEW_ALLOW_SAME_ORIGIN=1 opt-in.
"""

from __future__ import annotations

import importlib

import pytest


def _attr(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("AIFACTORY_SANDBOX_PREVIEW_ALLOW_SAME_ORIGIN",):
        if key not in env:
            monkeypatch.delenv(key, raising=False)
    mod = importlib.import_module("web.backend.services.sandbox_static_rewrite")
    importlib.reload(mod)
    return mod.sandbox_iframe_sandbox_attr()


def test_by_default_the_frame_gets_an_opaque_origin(monkeypatch):
    attr = _attr(monkeypatch)
    assert "allow-scripts" in attr, "the preview still has to run"
    assert "allow-same-origin" not in attr, (
        "allow-scripts + allow-same-origin on a same-origin src voids the sandbox: "
        "generated JS runs as the factory origin"
    )


def test_the_useful_permissions_are_kept(monkeypatch):
    attr = _attr(monkeypatch)
    for kept in ("allow-forms", "allow-popups", "allow-downloads", "allow-modals"):
        assert kept in attr, f"{kept} was dropped; the preview is needlessly crippled"


def test_an_operator_can_opt_back_in_explicitly(monkeypatch):
    """For a preview that genuinely needs same-origin storage — a deliberate, visible choice."""
    attr = _attr(monkeypatch, AIFACTORY_SANDBOX_PREVIEW_ALLOW_SAME_ORIGIN="1")
    assert "allow-same-origin" in attr


def test_the_viewer_renders_the_computed_attribute_not_a_frozen_constant():
    """The route must ask at render time, or the opt-in above could have no effect.

    Read from source rather than imported: the viewer module pulls in FastAPI, and this
    property is about what the file says, not about anything at runtime.
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "web" / "backend" / "api" / "sandbox.py"
    if not src.is_file():
        pytest.skip("viewer module not present")
    text = src.read_text(encoding="utf-8")
    assert "sandbox_iframe_sandbox_attr()" in text, (
        "the viewer still interpolates a frozen module constant, so the env opt-in — and "
        "any future change to the attribute — cannot reach the rendered page"
    )
