"""The guard that keeps agent knowledge bases from drifting away from reality.

This exists because the drift already happened: MOMUS, Treasury, ATLAS and the bridges were absent
from every single agent knowledge base while being fully built, deployed and documented. Nine
hand-typed component lists in four languages had no mechanism keeping them honest, so they rotted —
quietly, which is the only way this kind of thing rots.

The point of these tests is that **no human is responsible** for the roster. A satellite added to
scripts/satellite-map.yaml without a sync makes CI fail, and the fix is one command.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

ecosystem_knowledge = pytest.importorskip("ecosystem_knowledge")
sync = pytest.importorskip("sync_knowledge_base")


def test_every_satellite_reaches_every_knowledge_base():
    """The core guarantee: a component in the map appears in every base. No exceptions list."""
    ids = [c["id"] for c in ecosystem_knowledge.components()]
    assert len(ids) > 20, "the fact table looks truncated"
    for target in sync.TARGETS:
        text = target.full.read_text(encoding="utf-8")
        block = re.search(r"BEGIN GENERATED ecosystem-components(.*?)END GENERATED", text, re.S)
        assert block, f"{target.path} lost its generated fence"
        missing = [i for i in ids if f"- {i}" not in block.group(1)]
        assert not missing, f"{target.path} ({target.consumer}) is missing: {missing}"


def test_the_new_satellites_are_actually_there():
    """Named explicitly, because these are onboarding or core pieces people must discover."""
    for target in sync.TARGETS:
        text = target.full.read_text(encoding="utf-8")
        for cid in (
            "momus",
            "treasury",
            "atlas",
            "aimarket-bridges",
            "aimarket-playground",
            "create-aimarket-agent",
            "themis",
        ):
            assert f"- {cid}" in text, f"{target.path} does not know about {cid}"


@pytest.mark.parametrize(
    ("lang", "playground_terms", "cli_term", "supply_chain_term"),
    [
        ("ru", ("показание", "верификация", "квитанция"), "поставщиков", "цепочки поставок AI-агентов"),
        ("es", ("lectura", "verificación", "recibo"), "proveedores", "cadena de suministro de agentes de IA"),
        ("fr", ("lecture", "vérification", "reçu"), "fournisseurs", "chaîne d'approvisionnement des agents IA"),
        ("zh", ("读数", "验证", "收据"), "提供方", "AI 智能体供应链"),
    ],
)
def test_onboarding_satellites_use_the_localized_glossary(
    lang, playground_terms, cli_term, supply_chain_term
):
    """Generated descriptions follow the canonical five-language technical glossary."""
    target = next(t for t in sync.TARGETS if t.lang == lang)
    text = target.full.read_text(encoding="utf-8")
    block = re.search(r"BEGIN GENERATED ecosystem-components(.*?)END GENERATED", text, re.S)
    assert block
    playground_line = next(
        line for line in block.group(1).splitlines() if line.startswith("- aimarket-playground:")
    )
    cli_line = next(
        line for line in block.group(1).splitlines() if line.startswith("- create-aimarket-agent:")
    )
    auditor_line = next(
        line
        for line in block.group(1).splitlines()
        if line.startswith("- themis:")
    )
    assert all(term in playground_line for term in playground_terms)
    assert cli_term in cli_line
    assert supply_chain_term in auditor_line


def test_check_mode_is_clean():
    """`--check` must pass on a committed tree; if it does not, someone edited a block by hand."""
    assert sync.run("check") == 0, "run: python3 scripts/sync_knowledge_base.py --write"


def test_generated_block_is_safe_to_embed():
    """The block goes inside a TS template literal and Python triple-quoted strings.

    A stray backtick or ${ would break ARGUS's build; a stray triple quote would break ATLAS's
    module. Cheap to assert, expensive to discover at runtime."""
    block = ecosystem_knowledge.render_block()
    for forbidden in ("`", "${", '"""'):
        assert forbidden not in block, f"generated block contains {forbidden!r}"
    phys = pytest.importorskip("physical_capabilities")
    pblock = phys.render_block(lang="en")
    for forbidden in ("`", "${", '"""'):
        assert forbidden not in pblock, f"physical block contains {forbidden!r}"


def test_physical_skus_reach_every_knowledge_base():
    """A pin in STATION_CATALOG must appear in every assistant knowledge base."""
    phys = pytest.importorskip("physical_capabilities")
    skus = phys.catalog_sku_ids()
    assert "gaia.ais.public.read@v1" in skus
    assert "gaia.tsunami.read@v1" in skus
    assert "atlas.situation.brief@v1" in skus
    for target in sync.TARGETS:
        text = target.full.read_text(encoding="utf-8")
        block = re.search(
            r"BEGIN GENERATED physical-capabilities(.*?)END GENERATED",
            text,
            re.S,
        )
        assert block, f"{target.path} lost its physical-capabilities fence"
        missing = [s for s in skus if s not in block.group(1)]
        assert not missing, (
            f"{target.path} ({target.consumer}) is missing physical SKUs: {missing[:8]}"
        )


def test_runtime_overlay_ids_exist_in_the_map():
    """An overlay entry for a component that is not in the map is a silent no-op — catch the typo."""
    known = {c["id"] for c in ecosystem_knowledge.components()}
    for cid in ecosystem_knowledge.load_runtime():
        assert cid in known, f"ecosystem-runtime.yaml describes unknown component '{cid}'"


@pytest.mark.parametrize(
    "url",
    [
        # TEST-NET-1/2/3 documentation addresses — never real fleet IPs
        # (verify_mirror_secrets forbids those). One per first-octet width:
        # the old prefix guard only matched a single digit and let the rest through.
        "https://203.0.113.10:9410",
        "https://198.51.100.7",
        "http://192.0.2.55:8080",
        "https://[2001:db8::1]:9410",
    ],
)
def test_overlay_refuses_a_bare_ip(tmp_path, url):
    """Knowledge bases are published. A server IP in one is how infra addresses leaked before."""
    bad = tmp_path / "rt.yaml"
    bad.write_text(f'components:\n  momus:\n    url: "{url}"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bare IP"):
        ecosystem_knowledge.load_runtime(bad)


def test_overlay_still_accepts_a_hostname(tmp_path):
    """The guard must not reject legitimate public hostnames (incl. digit-leading ones)."""
    ok = tmp_path / "rt.yaml"
    ok.write_text(
        'components:\n'
        '  momus:\n    url: "https://momus.modelmarket.dev"\n'
        '  logos:\n    url: "https://5gnet.example.org:9401"\n',
        encoding="utf-8",
    )
    loaded = ecosystem_knowledge.load_runtime(ok)
    assert set(loaded) == {"momus", "logos"}


def test_registry_doc_lists_every_target():
    """The doc is how a person finds these files; a target missing from it is invisible."""
    doc = (ROOT / "docs" / "ecosystem" / "knowledge-sources.md").read_text(encoding="utf-8")
    for target in sync.TARGETS:
        assert target.path in doc, f"knowledge-sources.md does not mention {target.path}"
    for path, _ in sync.RUNTIME_CONSUMERS + sync.NOT_TARGETS:
        assert path in doc, f"knowledge-sources.md does not mention {path}"
    for src, dst in sync.FILE_MIRRORS:
        assert src in doc and dst in doc, f"knowledge-sources.md does not mention mirror {dst}"


def test_excluded_stores_are_justified_not_just_absent():
    """Every deliberate exclusion carries a reason, so the next person does not 'fix' it."""
    for path, reason in sync.NOT_TARGETS:
        assert len(reason) > 40, f"{path} is excluded without a real reason"


def test_file_mirror_carries_no_relative_links():
    """The mirror lands in another repo — a relative link there resolves to nothing.

    72 links in the Alien Monitor copy were dead on GitHub for exactly this reason.
    """
    rel_link = re.compile(r"!?\[[^\]]*\]\((?!https?://|mailto:|#)([^)\s]+)\)")
    for _, dst in sync.FILE_MIRRORS:
        text = (ROOT / dst).read_text(encoding="utf-8")
        dead = [m.group(1) for m in rel_link.finditer(text)]
        assert not dead, f"{dst} still carries relative links: {dead[:5]}"


def test_mirror_text_absolutises_links_that_resolve():
    """Rewrite what exists; leave what does not, so real breakage stays visible."""
    src = "docs/ecosystem/knowledge-base.md"
    out = sync.mirror_text(src, "see [wp](whitepaper/en.md#intro) and [ghost](no-such-file.md)")
    assert "https://github.com/alexar76/aicom/blob/main/docs/ecosystem/whitepaper/en.md#intro" in out
    assert "(no-such-file.md)" in out
