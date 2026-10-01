"""Content language resolution and prompt wiring."""

from llm.agent_prompt_split import build_architect_system_prompt, build_architect_user_data
from llm.content_languages import (
    LANGUAGE_SYSTEM,
    detect_brief_language,
    ensure_architecture_content_language,
    normalize_content_language,
    product_locale_fields,
    resolve_content_language,
)
from llm.visual_quality_system import VISUAL_QUALITY_SYSTEM


def test_normalize_aliases():
    assert normalize_content_language("RU") == "ru"
    assert normalize_content_language("español") == "es"
    assert normalize_content_language("auto") is None


def test_detect_russian_brief():
    text = "Создай лендинг для студии йоги в Москве с расписанием и ценами на русском языке."
    assert detect_brief_language(text) == "ru"


def test_mixed_brief_falls_back_to_en_when_text_present():
    text = "Make a landing page для фитнес студии with pricing"
    assert detect_brief_language(text) is None
    assert (
        resolve_content_language(
            user_text=text,
            interface_locale="ru",
        )
        == "en"
    )


def test_empty_brief_uses_interface_locale():
    assert resolve_content_language(user_text="", interface_locale="es") == "es"


def test_explicit_product_locale_overrides():
    assert (
        resolve_content_language(
            product_content_locale="de",
            user_text="English only brief for a gym",
            interface_locale="en",
        )
        == "de"
    )


def test_ensure_architecture_sets_meta():
    arch: dict = {"content_language": "es"}
    code = ensure_architecture_content_language(
        arch,
        user_text="Landing para gimnasio boutique",
    )
    assert code == "es"
    assert arch["content_language"] == "es"
    assert arch["content_language_meta"]["html_lang"] == "es"


def test_architect_system_includes_language_system():
    sys = build_architect_system_prompt("ROLE")
    assert LANGUAGE_SYSTEM in sys
    assert VISUAL_QUALITY_SYSTEM in sys


def test_architect_user_data_locale_fields():
    payload = build_architect_user_data(
        idea="test",
        spec={},
        admin_instructions="",
        landing_charter=True,
        peer_feedback=None,
        research_context="",
        methodology_block="",
        landing_note="",
        full_note="",
        ux_note="",
        interface_locale="ru",
        content_locale="auto",
    )
    assert payload["interface_locale"] == "ru"
    assert payload["content_locale"] == "auto"
    assert payload["content_language_meta"]["code"] == "ru"


def test_product_locale_fields():
    assert product_locale_fields(interface_locale="RU", content_locale="auto") == {
        "interface_locale": "ru",
        "content_locale": "auto",
    }
    assert product_locale_fields(interface_locale=None, content_locale="fr") == {
        "interface_locale": "en",
        "content_locale": "fr",
    }
