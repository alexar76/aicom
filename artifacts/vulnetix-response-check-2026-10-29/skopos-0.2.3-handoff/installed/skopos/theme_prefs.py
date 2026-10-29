"""Persist dashboard theme choice across sessions (optional file on disk)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from skopos.atomic_io import write_text_atomic

# Canonical theme id (mirrors SKOPOS_LOCALE_KEY for language).
SKOPOS_THEME_KEY = "skopos_theme"
# Streamlit selectbox widget key.
SKOPOS_THEME_WIDGET = "theme"


def prefs_path() -> Path:
    raw = os.environ.get("SKOPOS_UI_PREFS_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(".skopos/ui_prefs.json")


def load_saved_theme() -> str | None:
    path = prefs_path()
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        tid = (data.get("theme") or "").strip()
        return tid or None
    except Exception:
        return None


def save_theme_pref(theme_id: str) -> None:
    path = prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(path, json.dumps({"theme": theme_id}, indent=2) + "\n")
    except Exception:
        pass


def apply_theme_state(session, *, valid_ids: set[str], default: str) -> None:
    """Set SKOPOS_THEME_KEY from disk or existing widget values."""
    if SKOPOS_THEME_KEY in session:
        tid = str(session[SKOPOS_THEME_KEY])
        if tid in valid_ids:
            return
        session.pop(SKOPOS_THEME_KEY, None)

    saved = load_saved_theme()
    if saved and saved in valid_ids:
        session[SKOPOS_THEME_KEY] = saved
        return

    widget = session.get(SKOPOS_THEME_WIDGET)
    if widget in valid_ids:
        session[SKOPOS_THEME_KEY] = widget
        return

    legacy = session.get("app_theme_selector")
    if legacy in valid_ids:
        session[SKOPOS_THEME_KEY] = legacy
        return

    session[SKOPOS_THEME_KEY] = default


def sync_theme_widget(session, *, valid_ids: set[str], default: str) -> None:
    """Align the selectbox widget key with the canonical theme id."""
    tid = str(session.get(SKOPOS_THEME_KEY, default))
    if tid not in valid_ids:
        tid = default
        session[SKOPOS_THEME_KEY] = tid
    if session.get(SKOPOS_THEME_WIDGET) != tid:
        session[SKOPOS_THEME_WIDGET] = tid
