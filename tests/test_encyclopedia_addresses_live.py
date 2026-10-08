"""The public encyclopedia's "Live Base MAINNET" table lists the live contracts.

It is published to GitHub Pages in five languages and listed the June escrow, NFT and
lottery and the August ACEX set long after each was redeployed — a reader paying into
the address shown would have paid a contract the hub no longer reads. Every address in
that table must be the registry's current one for the same name, in every language.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "config" / "deployments" / "base-mainnet.json").read_text(encoding="utf-8"))
LANGS = ["en", "ru", "es", "fr", "zh"]


def _mainnet_tables(doc):
    for chapter in doc.get("chapters") or doc.get("sections") or []:
        table = chapter.get("table") if isinstance(chapter, dict) else None
        if table and any("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" in json.dumps(r) for r in table.get("rows", [])):
            yield table


def _all_tables(doc):
    found = list(_mainnet_tables(doc))
    if found:
        return found
    # Fall back to a deep search when the document nests chapters differently.
    out = []
    def walk(x):
        if isinstance(x, dict):
            if "rows" in x and any("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" in json.dumps(r) for r in x["rows"]):
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    return out


@pytest.mark.parametrize("lang", LANGS)
def test_the_mainnet_table_names_the_live_address_for_each_contract(lang):
    doc = json.loads((ROOT / "docs" / "encyclopedia" / "content" / f"{lang}.json").read_text(encoding="utf-8"))
    tables = _all_tables(doc)
    assert tables, f"{lang}: no Base mainnet table found"
    live = {k.lower(): v.lower() for k, v in REGISTRY["contracts"].items()}
    for table in tables:
        for row in table["rows"]:
            name = re.sub(r"\s*\(.*\)$", "", str(row[0])).strip()
            m = re.search(r"0x[0-9a-fA-F]{40}", str(row[1]))
            assert m, f"{lang}: row {row!r} has no address"
            key = "usdc" if name.lower().startswith("usdc") else name.lower()
            assert key in live, f"{lang}: {name} is not in the deployment registry"
            assert m.group(0).lower() == live[key], (
                f"{lang}: {name} shows {m.group(0)}, the registry's live one is {REGISTRY['contracts'][next(k for k in REGISTRY['contracts'] if k.lower() == key)]}"
            )
