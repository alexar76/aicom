"""Unit tests for llm.local_image helpers (no GPU/torch required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("local_image", _ROOT / "llm" / "local_image.py")
assert _spec and _spec.loader
li = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(li)


def test_model_id_default():
    assert li.local_image_model_id() == "stabilityai/sd-turbo"


def test_default_steps_clamped(monkeypatch):
    monkeypatch.setenv("AICOM_LOCAL_IMAGE_STEPS", "99")
    assert li.default_inference_steps() == 40
    monkeypatch.setenv("AICOM_LOCAL_IMAGE_STEPS", "2")
    assert li.default_inference_steps() == 2


def test_generate_requires_prompt():
    with pytest.raises(ValueError, match="prompt"):
        li.generate_local_image("  ")


def test_generate_missing_deps(monkeypatch):
    monkeypatch.setattr(li, "_load_pipeline", lambda: (_ for _ in ()).throw(RuntimeError("no torch")))
    with pytest.raises(RuntimeError, match="no torch"):
        li.generate_local_image("test prompt")
