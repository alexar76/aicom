"""Keep the two onboarding projects visible and terminology-consistent everywhere."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LANDING = ROOT / "ecosystem-landing" / "index.html"
LANGUAGES = ("en", "ru", "es", "fr", "zh")
ONBOARDING_KEYS = (
    "p_playground_tag",
    "p_playground_p",
    "L_open_playground",
    "p_create_agent_tag",
    "p_create_agent_p",
    "L_cli_docs",
)


def _landing_i18n() -> dict[str, dict[str, str]]:
    text = LANDING.read_text(encoding="utf-8")
    marker = "  const I18N = "
    start = text.index(marker) + len(marker)
    translations, _ = json.JSONDecoder().raw_decode(text[start:])
    return translations


def test_landing_has_complete_onboarding_copy_in_all_five_languages():
    translations = _landing_i18n()
    assert tuple(translations) == LANGUAGES
    for lang in LANGUAGES:
        missing = [key for key in ONBOARDING_KEYS if not translations[lang].get(key, "").strip()]
        assert not missing, f"landing {lang} is missing onboarding translations: {missing}"


@pytest.mark.parametrize(
    ("lang", "playground_terms", "provider_term"),
    [
        ("ru", ("показание", "верификацию", "квитанцией"), "поставщика"),
        ("es", ("lectura", "verificación", "recibo"), "proveedor"),
        ("fr", ("lecture", "vérification", "reçu"), "fournisseur"),
        ("zh", ("读数", "验证", "收据"), "提供方"),
    ],
)
def test_landing_onboarding_copy_uses_canonical_glossary_terms(
    lang: str,
    playground_terms: tuple[str, ...],
    provider_term: str,
):
    translations = _landing_i18n()[lang]
    assert all(term in translations["p_playground_p"] for term in playground_terms)
    assert provider_term in translations["p_create_agent_p"]


def test_landing_cards_link_to_live_product_and_both_repositories():
    text = LANDING.read_text(encoding="utf-8")
    for url in (
        "https://play.modelmarket.dev/",
        "https://github.com/alexar76/aimarket-playground",
        "https://github.com/alexar76/create-aimarket-agent",
    ):
        assert f'href="{url}"' in text
    for key in ONBOARDING_KEYS:
        assert re.search(rf'data-i18n="{re.escape(key)}"', text)


def test_ecosystem_readmes_list_both_onboarding_projects():
    for rel in ("ecosystem-README.md", "scripts/profile-readme/README.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for project in ("aimarket-playground", "create-aimarket-agent"):
            assert project in text, f"{rel} does not mention {project}"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_five_language_supply_chain_admission_docs(lang: str):
    suffix = "" if lang == "en" else f"-{lang}"
    path = ROOT / "docs" / "ecosystem" / f"supply-chain-admission{suffix}.md"
    text = path.read_text(encoding="utf-8")
    assert "```mermaid" in text
    assert "THEMIS" in text
    assert "WARDEN" in text
    assert "MOMUS" in text
    assert "Alien Monitor" in text
    assert "Hub" in text
    assert "approve" in text and "review" in text and "reject" in text
    for other in LANGUAGES:
        if other == lang:
            continue
        other_suffix = "" if other == "en" else f"-{other}"
        assert f"supply-chain-admission{other_suffix}.md" in text
