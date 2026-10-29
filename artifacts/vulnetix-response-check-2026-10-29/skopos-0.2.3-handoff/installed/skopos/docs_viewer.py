"""In-app documentation browser — markdown guides with screenshots (20 doc languages)."""

from __future__ import annotations

import inspect
from pathlib import Path

import streamlit as st

from skopos.doc_i18n import (
    DOC_LOCALES,
    SKOPOS_DOC_LOCALE_KEY,
    SKOPOS_DOC_LOCALE_WIDGET,
    doc_section_labels,
    doc_t,
    normalize_doc_locale,
    screenshot_locale_for_doc,
)

DOCS_ROOT = Path(__file__).resolve().parent.parent / "docs"
SCREENSHOTS = DOCS_ROOT / "screenshots"

GUIDE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("index", "overview"),
    ("deployment", "deployment"),
    ("configuration", "configuration"),
    ("usage", "usage"),
    ("nginx", "nginx"),
)


def _read_doc(doc_locale: str, slug: str) -> str:
    loc = normalize_doc_locale(doc_locale)
    path = DOCS_ROOT / loc / "guide" / f"{slug}.md"
    if not path.exists():
        path = DOCS_ROOT / "en" / "guide" / f"{slug}.md"
    if not path.exists():
        return f"_Missing guide: `{slug}.md`_"
    return path.read_text(encoding="utf-8")


def _resolve_image_path(src: str, *, doc_locale: str) -> Path | None:
    raw = src.strip().replace("\\", "/")
    shot_loc = screenshot_locale_for_doc(doc_locale)

    candidates: list[Path] = []
    if raw.startswith("screenshots/"):
        rel = raw[len("screenshots/") :]
        candidates.append(SCREENSHOTS / shot_loc / rel)
        candidates.append(SCREENSHOTS / "en" / rel)
        candidates.append(SCREENSHOTS / rel)
    elif raw.startswith("docs/screenshots/"):
        rel = raw[len("docs/screenshots/") :]
        candidates.append(DOCS_ROOT / "screenshots" / shot_loc / rel)
        candidates.append(DOCS_ROOT / "screenshots" / "en" / rel)
        candidates.append(DOCS_ROOT.parent / raw)
    else:
        candidates.append(SCREENSHOTS / shot_loc / raw)
        candidates.append(SCREENSHOTS / "en" / raw)
        candidates.append(SCREENSHOTS / raw)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _show_doc_image(img_path: Path, *, caption: str | None) -> None:
    """Render doc screenshot across Streamlit versions (API kw names differ)."""
    data = img_path.read_bytes()
    kw_sets: list[dict] = []
    try:
        params = inspect.signature(st.image).parameters
        if "use_container_width" in params:
            kw_sets.append({"use_container_width": True})
        if "use_column_width" in params:
            kw_sets.append({"use_column_width": True})
    except (TypeError, ValueError):
        pass
    kw_sets.append({})

    cap = (caption or "").strip()
    for extra in kw_sets:
        try:
            if cap:
                st.image(data, caption=cap, **extra)
            else:
                st.image(data, **extra)
            return
        except TypeError:
            continue
    st.image(data)


def render_markdown_with_images(body: str, *, doc_locale: str) -> None:
    """Render markdown, replacing ![alt](screenshots/foo.png) with st.image when present."""
    import re

    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    pos = 0
    for match in pattern.finditer(body):
        before = body[pos : match.start()]
        if before.strip():
            st.markdown(before)
        alt, src = match.group(1), match.group(2)
        img_path = _resolve_image_path(src, doc_locale=doc_locale)
        if img_path is not None:
            _show_doc_image(img_path, caption=alt or None)
        else:
            st.markdown(match.group(0))
            st.caption(doc_t("image_missing", doc_locale, path=src))
        pos = match.end()
    tail = body[pos:]
    if tail.strip():
        st.markdown(tail)


def _doc_locale_options() -> list[str]:
    return [code for code, _ in DOC_LOCALES]


def _doc_locale_labels() -> list[str]:
    return [label for _, label in DOC_LOCALES]


def _default_doc_locale(ui_locale: str) -> str:
    return normalize_doc_locale(ui_locale if ui_locale in {c for c, _ in DOC_LOCALES} else "en")


def _sync_doc_locale_widget(doc_locale: str) -> None:
    codes = _doc_locale_options()
    if doc_locale in codes:
        st.session_state[SKOPOS_DOC_LOCALE_WIDGET] = doc_locale


def _commit_doc_locale_widget() -> str:
    picked = st.session_state.get(SKOPOS_DOC_LOCALE_WIDGET)
    loc = normalize_doc_locale(str(picked) if picked else None)
    st.session_state[SKOPOS_DOC_LOCALE_KEY] = loc
    return loc


def active_doc_locale(*, ui_locale: str) -> str:
    """Selected documentation language (20 locales), independent of UI language."""
    if SKOPOS_DOC_LOCALE_KEY not in st.session_state:
        st.session_state[SKOPOS_DOC_LOCALE_KEY] = _default_doc_locale(ui_locale)
    return normalize_doc_locale(st.session_state.get(SKOPOS_DOC_LOCALE_KEY))


def render_docs_page(*, locale: str) -> None:
    """Documentation hub with section tabs and 20-language guide picker."""
    ui_locale = locale
    doc_locale = active_doc_locale(ui_locale=ui_locale)
    _sync_doc_locale_widget(doc_locale)

    st.markdown(
        f'<div class="hero-title">{doc_t("title", doc_locale)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="hero-sub">{doc_t("subtitle", doc_locale)}</div>',
        unsafe_allow_html=True,
    )

    st.selectbox(
        doc_t("doc_language", doc_locale),
        options=_doc_locale_options(),
        format_func=lambda c: next(l for code, l in DOC_LOCALES if code == c),
        key=SKOPOS_DOC_LOCALE_WIDGET,
        label_visibility="visible",
    )
    doc_locale = _commit_doc_locale_widget()

    st.info(doc_t("nginx_disclaimer", doc_locale))

    section_labels = doc_section_labels(doc_locale)
    labels = [section_labels[key] for _slug, key in GUIDE_SECTIONS]
    tabs = st.tabs(labels)
    for tab, (slug, _key) in zip(tabs, GUIDE_SECTIONS):
        with tab:
            render_markdown_with_images(_read_doc(doc_locale, slug), doc_locale=doc_locale)
