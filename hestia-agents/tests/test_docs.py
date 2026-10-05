"""The agent catalogue exists in five languages and names every agent in each of them."""

from __future__ import annotations

from pathlib import Path

import pytest

from hestia_agents.manifests import AGENTS

DOCS = Path(__file__).resolve().parent.parent / "docs"
LANGS = ["", ".ru", ".es", ".fr", ".zh"]


@pytest.mark.parametrize("lang", LANGS)
def test_every_agent_is_in_every_language(lang: str) -> None:
    text = (DOCS / f"AGENTS{lang}.md").read_text(encoding="utf-8")
    for slug, meta in AGENTS.items():
        assert f"### {slug}" in text, (lang or "en", slug)
        assert meta["capability_id"] in text, (lang or "en", meta["capability_id"])


@pytest.mark.parametrize("lang", LANGS)
def test_prices_match_the_manifest(lang: str) -> None:
    text = (DOCS / f"AGENTS{lang}.md").read_text(encoding="utf-8")
    for meta in AGENTS.values():
        price = meta["price_per_call_usd"]
        dollars = f"${price:.3f}"
        euros_style = f"{price:.3f}".replace(".", ",") + " $"
        assert dollars in text or euros_style in text, (lang or "en", meta["capability_id"], price)


def test_the_languages_link_to_each_other() -> None:
    for lang in LANGS:
        text = (DOCS / f"AGENTS{lang}.md").read_text(encoding="utf-8")
        for other in LANGS:
            if other != lang:
                assert f"AGENTS{other}.md" in text, (lang, other)
