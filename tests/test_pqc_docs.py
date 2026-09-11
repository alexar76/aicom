"""Five-language parity for the post-quantum migration document.

The load-bearing checks are not word counts. Two specific ways a translation of THIS document can
be actively harmful:

1. It renames a switch. An operator reads their own language and types what it says; a translated
   `ORACLE_PQC_REQUIRE` is an outage.
2. It drops the honest limitation. Phases 1–2 buy the ABILITY to migrate, not post-quantum
   security, and an unpinned PQ key authenticates the document rather than the peer. A translation
   that omits either reads as "we are post-quantum" — the exact overstatement the English text is
   written to avoid.

So the invariants are the identifiers, and the claims are asserted per language.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
DOCS = {
    "en": DOCS_DIR / "pqc-migration.md",
    "ru": DOCS_DIR / "pqc-migration.ru.md",
    "es": DOCS_DIR / "pqc-migration.es.md",
    "fr": DOCS_DIR / "pqc-migration.fr.md",
    "zh": DOCS_DIR / "pqc-migration.zh.md",
}

#: Identifiers an operator types or greps. Identical in every language by definition.
INVARIANTS = (
    "ORACLE_PQC",
    "ORACLE_PQC_REQUIRE",
    "AIMARKET_PQC_REQUIRE",
    "ORACLE_SIGNING_SEED_B64",
    "PQCMisconfigured",
    "ml-dsa-65",
    "ed25519",
    "pq_value",
    "pq_public_key",
    "pq_algorithm",
    "{key_path}_mldsa",
    "verify_hybrid",
    "verify_signature_object",
    "pq_public_key_b64",
    "aimarket-oracle-core[pqc]",
    "aimarket-hub[pqc]",
    "dilithium-py",
    "PeerRecord",
    "debitChannel",
    "secp256k1",
    "FIPS 204",
)


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_every_language_exists_and_carries_the_invariants(lang):
    path = DOCS[lang]
    assert path.is_file(), f"{lang} documentation is missing"
    text = path.read_text(encoding="utf-8")
    for token in INVARIANTS:
        assert token in text, (lang, token)


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_structure_matches_english(lang):
    """Same section count, same table count, one diagram. A dropped section is a dropped rule."""
    en = DOCS["en"].read_text(encoding="utf-8")
    text = DOCS[lang].read_text(encoding="utf-8")
    assert len(re.findall(r"^## ", text, re.M)) == len(re.findall(r"^## ", en, re.M))
    assert text.count("| --- |") == en.count("| --- |")
    assert text.count("```mermaid") == 1


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_the_three_phases_are_all_present_and_numbered(lang):
    text = DOCS[lang].read_text(encoding="utf-8")
    # Phase numbers travel as digits in every language, so they are checkable without translating.
    for phase in ("1", "2", "3"):
        assert re.search(rf"\|\s*{phase}\s*\|", text), (lang, phase)


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_the_honest_limitation_survives_translation(lang):
    """Both halves of it: the downgrade attack, and the unpinned-PQ-key gap."""
    text = DOCS[lang].read_text(encoding="utf-8")
    # The downgrade attack is named in the local language but always alongside `pq_*`.
    assert "pq_*" in text, lang
    # The pinning sentence is a blockquote in every language — it is the one claim that must not
    # be softened into "we now have post-quantum signatures".
    assert re.search(r"^> ", text, re.M), lang
    # And the phase table must still say REQUIRE is what closes it.
    assert "ORACLE_PQC_REQUIRE=1" in text, lang


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_no_cross_language_leakage(lang):
    """A prior 5-language pass left Russian sentences inside the EN/ES/ZH files."""
    text = DOCS[lang].read_text(encoding="utf-8")
    cyrillic = len(re.findall(r"[А-Яа-яЁё]", text))
    cjk = len(re.findall(r"[一-鿿]", text))
    if lang == "ru":
        assert cyrillic > 500 and cjk == 0
    elif lang == "zh":
        assert cjk > 500 and cyrillic == 0
    else:
        assert cyrillic == 0 and cjk == 0, (lang, cyrillic, cjk)


@pytest.mark.parametrize("lang", sorted(DOCS))
def test_language_switcher_links_resolve(lang):
    text = DOCS[lang].read_text(encoding="utf-8")
    targets = re.findall(r"\]\((pqc-migration[^)#]*|localization-glossary\.md)\)", text)
    assert targets, f"{lang} has no cross-language links"
    for target in targets:
        assert (DOCS_DIR / target).is_file(), (lang, target)
    # Each doc links to the other four, never to itself.
    own = DOCS[lang].name
    assert own not in targets, f"{lang} links to itself"


def test_glossary_defines_the_terms_the_docs_use():
    """The glossary is the terminology source of truth, so it must carry these rows."""
    glossary = (DOCS_DIR / "localization-glossary.md").read_text(encoding="utf-8")
    for term in ("post-quantum cryptography", "hybrid signature", "ML-DSA-65",
                 "downgrade attack", "downgrade guard", "pinned PQ key", "post-quantum-ready"):
        assert term in glossary, term
    # The row that keeps "ready" from being translated as "secure".
    assert "post-quantum-ready" in glossary
    assert "phase 3" in glossary


def test_deployment_table_states_that_no_signer_emits_pq_yet():
    """If phase 2 ever lands, this test fails and forces the doc to be updated with it.

    Deliberately a documentation assertion and not a runtime probe: `ORACLE_PQC` is set per
    DEPLOYED node, so nothing importable here can tell you whether production signs hybrid.
    """
    en = DOCS["en"].read_text(encoding="utf-8")
    assert "no signer emits `pq_value` yet" in en
