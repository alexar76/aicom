"""
Content language registry and resolution for landing / UI copy generation.

Priority (after explicit product override):
  1. Architect `content_language` (valid code)
  2. Clear majority language in user brief → that language
  3. Mixed / unclear brief → English
  4. Empty brief → interface locale, then platform default (`en`)
"""

from __future__ import annotations

import re
from typing import Any

# BCP 47 tag for <html lang="..."> (may differ from short content code)
CONTENT_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"label_en": "English", "html_lang": "en", "dir": "ltr"},
    "ru": {"label_en": "Russian", "html_lang": "ru", "dir": "ltr"},
    "es": {"label_en": "Spanish", "html_lang": "es", "dir": "ltr"},
    "de": {"label_en": "German", "html_lang": "de", "dir": "ltr"},
    "fr": {"label_en": "French", "html_lang": "fr", "dir": "ltr"},
    "pt": {"label_en": "Portuguese", "html_lang": "pt", "dir": "ltr"},
    "it": {"label_en": "Italian", "html_lang": "it", "dir": "ltr"},
    "pl": {"label_en": "Polish", "html_lang": "pl", "dir": "ltr"},
    "uk": {"label_en": "Ukrainian", "html_lang": "uk", "dir": "ltr"},
    "tr": {"label_en": "Turkish", "html_lang": "tr", "dir": "ltr"},
    "zh": {"label_en": "Chinese (Simplified)", "html_lang": "zh-Hans", "dir": "ltr"},
    "ja": {"label_en": "Japanese", "html_lang": "ja", "dir": "ltr"},
    "ko": {"label_en": "Korean", "html_lang": "ko", "dir": "ltr"},
    "ar": {"label_en": "Arabic", "html_lang": "ar", "dir": "rtl"},
    "hi": {"label_en": "Hindi", "html_lang": "hi", "dir": "ltr"},
    "id": {"label_en": "Indonesian", "html_lang": "id", "dir": "ltr"},
    "vi": {"label_en": "Vietnamese", "html_lang": "vi", "dir": "ltr"},
}

_LEGACY_ALIASES: dict[str, str] = {
    "eng": "en",
    "english": "en",
    "rus": "ru",
    "russian": "ru",
    "русский": "ru",
    "esp": "es",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
    "deutsch": "de",
    "german": "de",
    "français": "fr",
    "francais": "fr",
    "french": "fr",
    "português": "pt",
    "portugues": "pt",
    "portuguese": "pt",
    "zh-cn": "zh",
    "zh-hans": "zh",
    "chinese": "zh",
    "jp": "ja",
    "japanese": "ja",
    "kr": "ko",
    "korean": "ko",
    "ua": "uk",
    "ukrainian": "uk",
}

# Rough script / char-class detectors for brief heuristics (not a substitute for Architect judgment)
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_LATIN = re.compile(r"[A-Za-z\u00C0-\u024F]")
_CJK = re.compile(r"[\u3040-\u30FF\u3400-\u9FFF]")
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")

LANGUAGE_SYSTEM = """=== LANGUAGE_SYSTEM (mandatory for all user-visible copy) ===
Landing pages, marketing HTML, and any browser UI text MUST match the product content language.

**Architect responsibilities**
- Emit top-level JSON field **`content_language`**: a short code from the supported set (e.g. `ru`, `en`, `es`, `de`, `fr`, `pt`, `zh`, `ja`, `ar`).
- Decide from `user_brief` (idea + admin_instructions + specification), in this order:
  1. If the brief is **clearly and primarily** in one language → that code (Russian brief → `ru`, English → `en`, Spanish → `es`, etc.).
  2. If the brief is **mixed, bilingual without a dominant language, or too short to tell** → `en`.
  3. If the brief does not imply a language, use **`interface_locale`** from user data when present; otherwise `en`.
- When `content_locale` in user data is set to a specific code (not `auto`), treat it as the **default** unless the brief strongly demands another language — then pick the brief language and note the tension in `overview` (one short phrase).

**Developer responsibilities**
- Read `architecture.content_language` (fallback: `user_brief.content_locale` when not `auto`).
- Set `<html lang="...">` using the BCP 47 tag from user data `content_language_meta.html_lang` when provided, else the short code.
- **All visible strings** (headings, body, buttons, labels, `aria-label`, placeholders, alt text, meta description/title) MUST be in that language.
- Do **not** switch to English because UI presets or code comments are English — only English when `content_language` is `en`.
- For `ar`: set `dir="rtl"` on `<html>` and mirror layout consciously.
- JSON field names and file paths stay English; human-facing copy does not.

**Supported codes (non-exhaustive examples)**
`en`, `ru`, `es`, `de`, `fr`, `pt`, `it`, `pl`, `uk`, `tr`, `zh`, `ja`, `ko`, `ar`, `hi`, `id`, `vi` — use the closest supported code; prefer `en` when uncertain after applying the rules above."""


def normalize_content_language(raw: object | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("_", "-")
    if not s or s in ("auto", "default", "inherit"):
        return None
    if s in CONTENT_LANGUAGES:
        return s
    base = s.split("-", 1)[0]
    if base in CONTENT_LANGUAGES:
        return base
    return _LEGACY_ALIASES.get(s) or _LEGACY_ALIASES.get(base)


def content_language_meta(code: str) -> dict[str, str]:
    c = normalize_content_language(code) or "en"
    row = CONTENT_LANGUAGES.get(c, CONTENT_LANGUAGES["en"])
    return {"code": c, "html_lang": row["html_lang"], "dir": row["dir"], "label_en": row["label_en"]}


def detect_brief_language(text: str) -> str | None:
    """
    Return a content language code when the brief has a clear dominant language.
    Return None when mixed/unclear (caller should use English per product rules).
    """
    t = (text or "").strip()
    if len(t) < 12:
        return None

    scores: dict[str, int] = {}
    scores["ru"] = len(_CYRILLIC.findall(t))
    scores["ar"] = len(_ARABIC.findall(t))
    scores["zh"] = len(_CJK.findall(t))
    scores["ja"] = scores["zh"]  # grouped CJK; architect refines
    scores["ko"] = scores["zh"]
    scores["hi"] = len(_DEVANAGARI.findall(t))
    scores["en"] = len(_LATIN.findall(t))

    # Spanish / Portuguese / etc. need Latin letters; disambiguation is weak — rely on Architect
    ranked = sorted(((k, v) for k, v in scores.items() if v > 0), key=lambda x: -x[1])
    if not ranked:
        return None
    top_code, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if top_score < 8:
        return None
    if second_score > 0 and second_score / max(top_score, 1) > 0.35:
        return None
    if top_code in ("zh", "ja", "ko") and top_score > 0:
        return "zh" if scores["zh"] == top_score else top_code
    return top_code if top_code in CONTENT_LANGUAGES else None


def resolve_content_language(
    *,
    architect_value: object | None = None,
    product_content_locale: object | None = None,
    interface_locale: object | None = None,
    user_text: str = "",
    fallback: str = "en",
) -> str:
    explicit = normalize_content_language(product_content_locale)
    if explicit:
        return explicit

    from_arch = normalize_content_language(architect_value)
    if from_arch:
        return from_arch

    detected = detect_brief_language(user_text)
    if detected:
        return detected

    if (user_text or "").strip():
        return "en"

    iface = normalize_content_language(interface_locale)
    if iface:
        return iface

    fb = normalize_content_language(fallback) or "en"
    return fb


def product_locale_fields(
    *,
    interface_locale: object | None = None,
    content_locale: object | None = None,
    fallback_interface: str = "en",
) -> dict[str, str]:
    """Normalize locale fields stored on pipeline products."""
    iface = normalize_content_language(interface_locale) or normalize_content_language(fallback_interface) or "en"
    explicit = normalize_content_language(content_locale)
    return {
        "interface_locale": iface,
        "content_locale": explicit if explicit else "auto",
    }


def ensure_architecture_content_language(
    arch: dict[str, Any],
    *,
    product_content_locale: object | None = None,
    interface_locale: object | None = None,
    user_text: str = "",
    fallback: str = "en",
) -> str:
    code = resolve_content_language(
        architect_value=arch.get("content_language"),
        product_content_locale=product_content_locale,
        interface_locale=interface_locale,
        user_text=user_text,
        fallback=fallback,
    )
    arch["content_language"] = code
    arch["content_language_meta"] = content_language_meta(code)
    return code
