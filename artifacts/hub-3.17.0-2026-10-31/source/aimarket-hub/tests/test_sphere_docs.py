"""The sphere rule, documented in five languages, checked for drift.

The rule decides whether somebody else's node appears on a map at all, so a translation
that quietly drops one of the three ways in is worse than no translation: an operator reads
their own language, concludes a free capability is not enough, and prices something they
meant to give away.

These are structural checks, not a review of the prose: every language must carry the
disclaimer, all three participation routes, the environment variables by name, and the
addresses in the worked example. Prose is the translator's; facts are not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
LANGS = {
    "en": "who-gets-a-sphere.md",
    "ru": "who-gets-a-sphere.ru.md",
    "es": "who-gets-a-sphere.es.md",
    "fr": "who-gets-a-sphere.fr.md",
    "zh": "who-gets-a-sphere.zh.md",
}


@pytest.fixture(scope="module")
def texts() -> dict[str, str]:
    missing = [name for name in LANGS.values() if not (DOCS / name).exists()]
    assert not missing, f"missing translations: {missing}"
    return {lang: (DOCS / name).read_text(encoding="utf-8") for lang, name in LANGS.items()}


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_leads_with_the_disclaimer(texts, lang):
    """The reader has to learn "the viewer decides, not you" before anything else."""
    head = texts[lang][:900]
    assert "⚠️" in head, "no disclaimer block at the top"
    assert head.index("⚠️") < texts[lang].index("| ")  # before the first table


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_states_all_three_routes(texts, lang):
    """Supplier / consumer / on-chain. Dropping one changes what an operator does."""
    text = texts[lang]
    assert "public_free" in text, "the free-capability route must be explicit"
    assert "consumer_hub" in text, "the consumer route must be explicit"
    assert "AIMARKET_ESCROW_EVM_ADDRESS" in text, "the on-chain route must be explicit"


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_names_the_variables_that_do_the_work(texts, lang):
    text = texts[lang]
    for name in (
        "AIMARKET_PAYMENT_RECIPIENT",
        "AIMARKET_HUB_URL",
        "AIMARKET_CHAIN_REALM=uni",
        "ALIEN_KEEP_SILENT_NODES",
        "payment_configured",
    ):
        assert name in text, f"{name} missing from {lang}"


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_shows_the_contracts_block(texts, lang):
    text = texts[lang]
    assert '"contracts"' in text
    for role in ('"role": "escrow"', '"role": "wallet"', '"role": "token"'):
        assert role in text, f"{role} missing from {lang}"
    assert '"simulated": true' in text, "the bubble flag must be documented"


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_says_declared_is_not_verified(texts, lang):
    """The distinction the whole feature rests on."""
    text = texts[lang]
    assert "/api/chain/address/" in text, "no pointer to the built-in scanner"
    # the explorer caveat: a bubble address on a public explorer is a wrong link
    assert "basescan.org" in text


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_language_keeps_the_three_tier_table(texts, lang):
    text = texts[lang]
    assert text.count("|---|") >= 1
    assert "8453" in text, "the worked example's chain id"


def test_translations_are_not_stubs(texts):
    """A 20-line "translation" that links to the English page is a silent gap."""
    lengths = {lang: len(text.splitlines()) for lang, text in texts.items()}
    shortest = min(lengths.values())
    assert shortest > 120, f"suspiciously short translation: {lengths}"


def test_the_english_page_is_linked_from_the_declaration_guide():
    """Two pages about what a monitor draws must find each other."""
    for name in ("ecosystem-declaration.md", "ecosystem-declaration.ru.md"):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert "who-gets-a-sphere" in text, f"{name} does not link the sphere rule"
