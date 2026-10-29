from __future__ import annotations

import json
import locale as syslocale
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "ru", "es", "fr", "zh")
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
SKOPOS_LOCALE_KEY = "skopos_locale"
SKOPOS_LOCALE_WIDGET = "skopos_locale_widget"


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


@lru_cache(maxsize=16)
def _catalog_cached(locale_mtime: tuple[str, float]) -> dict[str, Any]:
    loc, _mtime = locale_mtime
    path = LOCALES_DIR / f"{loc}.yaml"
    if not path.exists():
        path = LOCALES_DIR / f"{DEFAULT_LOCALE}.yaml"
    base = _load_yaml(path)
    if loc != DEFAULT_LOCALE:
        base_path = LOCALES_DIR / f"{DEFAULT_LOCALE}.yaml"
        merged = _load_yaml(base_path)
        merged.update(base)
        return merged
    return base


def _catalog(locale: str) -> dict[str, Any]:
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    path = LOCALES_DIR / f"{loc}.yaml"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return _catalog_cached((loc, mtime))


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Translate dotted key, e.g. security.title."""
    node: Any = _catalog(locale)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return key
        node = node[part]
    if not isinstance(node, str):
        return key
    try:
        return node.format(**kwargs)
    except KeyError:
        return node


def t_or(key: str, locale: str = DEFAULT_LOCALE, default: str = "", **kwargs: Any) -> str:
    """Translate ``key``, falling back to an English ``default`` given at the call site.

    ``t`` renders a missing key as the dotted key itself, and the en fallback is a shallow
    top-level dict.update — so a block that exists with holes does not fall back at all. A section
    whose ``remediation:`` block has not landed in all five catalogues would therefore show
    "remediation.title" to the operator. The call-site default keeps it in English until then, and
    stops mattering the moment the key exists.
    """
    text = t(key, locale, **kwargs)
    if text != key or not default:
        return text
    try:
        return default.format(**kwargs)
    except (KeyError, IndexError):
        return default


def t_list(key: str, locale: str = DEFAULT_LOCALE) -> list[str]:
    """Return a translated YAML list (e.g. agent.suggestions)."""
    node: Any = _catalog(locale)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return []
        node = node[part]
    if isinstance(node, list):
        return [str(item).strip() for item in node if str(item).strip()]
    return []


def locale_label(code: str) -> str:
    labels = {"en": "English", "ru": "Русский", "es": "Español", "fr": "Français", "zh": "中文"}
    return labels.get(code, code)


def _pick_supported_locale(tag: str) -> str | None:
    base = tag.strip().split(";")[0].split("-")[0].lower()
    if base in SUPPORTED_LOCALES:
        return base
    return None


def _locale_from_accept_language(header: str) -> str | None:
    for part in header.split(","):
        loc = _pick_supported_locale(part)
        if loc:
            return loc
    return None


def _locale_from_system() -> str | None:
    for raw in (
        os.environ.get("LANG"),
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        (syslocale.getdefaultlocale()[0] if syslocale.getdefaultlocale() else None),
    ):
        if not raw:
            continue
        loc = _pick_supported_locale(raw.replace("_", "-"))
        if loc:
            return loc
    return None


def detect_initial_locale() -> str:
    """Browser Accept-Language first, then OS locale, else English."""
    try:
        headers = getattr(getattr(st, "context", None), "headers", None)
        if headers is not None:
            accept = headers.get("Accept-Language") or headers.get("accept-language")
            if accept:
                loc = _locale_from_accept_language(str(accept))
                if loc:
                    return loc
    except Exception:
        pass
    return _locale_from_system() or DEFAULT_LOCALE


def _commit_locale_widget() -> None:
    picked = str(st.session_state.get(SKOPOS_LOCALE_WIDGET, DEFAULT_LOCALE))
    if picked in SUPPORTED_LOCALES:
        st.session_state[SKOPOS_LOCALE_KEY] = picked


def _sync_locale_widget() -> None:
    """Keep the language selectbox aligned with the canonical locale (no mid-run drift)."""
    loc = active_locale()
    if st.session_state.get(SKOPOS_LOCALE_WIDGET) != loc:
        st.session_state[SKOPOS_LOCALE_WIDGET] = loc


def active_locale() -> str:
    """Current UI locale from session (after the language selectbox)."""
    ensure_locale_state()
    loc = str(st.session_state[SKOPOS_LOCALE_KEY])
    return loc if loc in SUPPORTED_LOCALES else DEFAULT_LOCALE


def ensure_locale_state() -> None:
    if SKOPOS_LOCALE_KEY in st.session_state:
        return
    if "locale" in st.session_state:
        st.session_state[SKOPOS_LOCALE_KEY] = st.session_state["locale"]
        return
    st.session_state[SKOPOS_LOCALE_KEY] = detect_initial_locale()


def browser_page_title(section_key: str, locale: str | None = None) -> str:
    """Localized browser tab title: SKOPOS — {section}."""
    if locale is not None:
        loc = locale
    elif SKOPOS_LOCALE_KEY in st.session_state:
        loc = active_locale()
    else:
        loc = detect_initial_locale()
    return f"{t('app.title', loc)} — {t(section_key, loc)}"


# Sidebar navigation — (path, locale key, Material icon).
NAV_PAGES: tuple[tuple[str, str, str], ...] = (
    ("pages/0_Quick_Start.py", "app.quick_start", ":material/rocket_launch:"),
    ("pages/4_Documentation.py", "app.documentation", ":material/menu_book:"),
    ("dashboard.py", "app.analytics", ":material/insights:"),
    ("pages/1_Security.py", "app.security", ":material/shield:"),
    ("pages/3_Scan_History.py", "app.history", ":material/history:"),
    ("pages/5_Fleet.py", "app.fleet", ":material/dns:"),
    ("pages/6_Observability.py", "app.observability", ":material/monitoring:"),
    ("pages/7_Remediation.py", "app.remediation", ":material/healing:"),
    ("pages/2_Settings.py", "app.settings", ":material/smart_toy:"),
)


def _resolve_page_link_path(relpath: str) -> str:
    """Match NAV path to Streamlit's registered page script_path."""
    want = relpath.replace("\\", "/")
    want_name = Path(want).name
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is not None:
            for pdata in ctx.pages_manager.get_pages().values():
                script_path = str(pdata.get("script_path", "")).replace("\\", "/")
                if script_path == want or script_path.endswith(f"/{want}") or script_path.endswith(want_name):
                    return script_path
    except Exception:
        pass
    return relpath


def safe_page_link(page_path: str, **kwargs) -> bool:
    """Best-effort st.page_link for AppTest and multipage script contexts."""
    basename = Path(page_path.replace("\\", "/")).name
    resolved = _resolve_page_link_path(page_path)
    for candidate in (resolved, basename, page_path):
        if not candidate:
            continue
        try:
            st.page_link(candidate, **kwargs)
            return True
        except TypeError:
            plain = {k: v for k, v in kwargs.items() if k != "icon"}
            try:
                st.page_link(candidate, **plain)
                return True
            except Exception:
                continue
        except Exception:
            continue
    return False


def safe_container_page_link(container, page_path: str, **kwargs) -> bool:
    basename = Path(page_path.replace("\\", "/")).name
    resolved = _resolve_page_link_path(page_path)
    for candidate in (resolved, basename, page_path):
        if not candidate:
            continue
        try:
            container.page_link(candidate, **kwargs)
            return True
        except Exception:
            continue
    return False


def render_sidebar_nav(*, locale: str, collapsed: bool = False) -> None:
    """Translated sidebar page links."""
    for path, label_key, icon in NAV_PAGES:
        title = t(label_key, locale)
        resolved = _resolve_page_link_path(path)
        try:
            st.sidebar.page_link(
                resolved,
                label=title,
                icon=icon,
                use_container_width=True,
            )
        except TypeError:
            # Streamlit < 1.31 without icon= on page_link
            text = icon if collapsed else f"{icon} {title}"
            st.sidebar.page_link(resolved, label=text)
        except Exception:
            alt = Path(path).name
            if alt != resolved:
                try:
                    text = icon if collapsed else f"{icon} {title}"
                    st.sidebar.page_link(alt, label=text)
                    continue
                except Exception:
                    pass
            st.sidebar.caption(f"{icon} {title}")
