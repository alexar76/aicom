"""Streamlit voice input via Web Speech API."""

from __future__ import annotations

import os

import streamlit.components.v1 as components

_DIR = os.path.dirname(os.path.abspath(__file__))
_component = components.declare_component("voice_input", path=os.path.join(_DIR, "frontend"))


def render_voice_input(*, key: str | None = None) -> str | None:
    """Microphone button; returns transcribed text when user speaks."""
    result = _component(key=key, default=None)
    if result is None:
        return None
    text = str(result).strip()
    return text or None
