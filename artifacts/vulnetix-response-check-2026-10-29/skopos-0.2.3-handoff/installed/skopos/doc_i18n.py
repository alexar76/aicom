"""Documentation locales (20 languages, aligned with ARGUS) — separate from UI i18n."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# Same 20 codes as argus/docs/user-guide/README.md
DOC_LOCALES: tuple[tuple[str, str], ...] = (
    ("en", "English"),
    ("zh", "中文"),
    ("es", "Español"),
    ("hi", "हिन्दी"),
    ("ar", "العربية"),
    ("pt", "Português"),
    ("ru", "Русский"),
    ("ja", "日本語"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("ko", "한국어"),
    ("it", "Italiano"),
    ("tr", "Türkçe"),
    ("id", "Indonesia"),
    ("vi", "Tiếng Việt"),
    ("th", "ไทย"),
    ("hr", "Hrvatski"),
    ("sk", "Slovenčina"),
    ("nl", "Nederlands"),
    ("fa", "فارسی"),
)

DOC_LOCALE_CODES: frozenset[str] = frozenset(code for code, _ in DOC_LOCALES)

# Russian docs use Russian UI screenshots; Spanish docs use Spanish (or en fallback).
SCREENSHOT_LOCALE_FOR_DOC: dict[str, str] = {"ru": "ru", "es": "es"}

SKOPOS_DOC_LOCALE_KEY = "skopos_doc_locale"
SKOPOS_DOC_LOCALE_WIDGET = "skopos_doc_locale_widget"

I18N_DIR = Path(__file__).resolve().parent.parent / "docs" / "i18n"
DOCS_ROOT = Path(__file__).resolve().parent.parent / "docs"


def doc_locale_label(code: str) -> str:
    for c, name in DOC_LOCALES:
        if c == code:
            return name
    return code


def screenshot_locale_for_doc(doc_locale: str) -> str:
    """Map doc language to screenshot set (en, ru, or es)."""
    return SCREENSHOT_LOCALE_FOR_DOC.get(doc_locale, "en")


def normalize_doc_locale(code: str | None) -> str:
    if code and code in DOC_LOCALE_CODES:
        return code
    return "en"


@lru_cache(maxsize=1)
def _ui_catalog() -> dict[str, dict[str, Any]]:
    path = I18N_DIR / "ui.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def doc_t(key: str, doc_locale: str, **kwargs: Any) -> str:
    """Translate documentation chrome (title, tab labels) for the selected doc language."""
    loc = normalize_doc_locale(doc_locale)
    catalog = _ui_catalog()
    node: Any = catalog.get(loc) or catalog.get("en") or {}
    for part in key.split("."):
        if not isinstance(node, dict):
            node = {}
            break
        node = node.get(part, "")
    text = node if isinstance(node, str) else ""
    if not text and loc in ("en", "ru", "es"):
        try:
            from skopos.i18n import t

            mapped = {
                "title": "docs.title",
                "subtitle": "docs.subtitle",
                "nginx_disclaimer": "docs.nginx_disclaimer",
                "image_missing": "docs.image_missing",
                "doc_language": "docs.doc_language",
            }
            if key in mapped:
                text = t(mapped[key], loc, **kwargs)
                return text
            if key.startswith("sections."):
                section = key.split(".", 1)[1]
                text = t(f"docs.section.{section}", loc)
        except Exception:
            text = ""
    if not text:
        text = key
    if kwargs and "{" in text:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def doc_section_labels(doc_locale: str) -> dict[str, str]:
    loc = normalize_doc_locale(doc_locale)
    ui = _ui_catalog().get(loc) or _ui_catalog().get("en") or {}
    sections = ui.get("sections") or {}
    defaults = {
        "index": "Overview",
        "deployment": "Deployment",
        "configuration": "Configuration",
        "usage": "Usage",
        "nginx": "HTTP logs",
    }
    out: dict[str, str] = {}
    for slug, key in (
        ("index", "overview"),
        ("deployment", "deployment"),
        ("configuration", "configuration"),
        ("usage", "usage"),
        ("nginx", "nginx"),
    ):
        label = sections.get(key)
        if not label and loc in ("en", "ru", "es"):
            try:
                from skopos.i18n import t

                label = t(f"docs.section.{key}", loc)
            except Exception:
                label = None
        # Keys match GUIDE_SECTIONS' semantic `key` (overview, deployment, …).
        out[key] = label or defaults[slug]
    return out
