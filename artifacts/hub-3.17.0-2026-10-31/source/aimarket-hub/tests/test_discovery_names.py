"""Both spellings of the discovery document and the crawler header (aimarket-protocol/ietf)."""

from __future__ import annotations

from aimarket_hub.discovery_names import (
    DRAFT_WELL_KNOWN_PATH,
    LEGACY_WELL_KNOWN_PATH,
    SIGNATURE_PROFILE,
    discovery_base,
    draft_discovery_document,
    is_draft_document,
    normalize_discovery_document,
)

LEGACY = {
    "name": "Hub",
    "protocol_versions": ["v1", "v2"],
    "hub_version": "3.16.4",
    "manifest_url": "https://hub.example/ai-market/manifest",
    "capabilities_count": 7,
    "signer_public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
    "peers": [{"url": "https://other.example", "name": "Other"}],
}

DRAFT = {
    "name": "Hub",
    "protocol_versions": ["v2"],
    "catalogue_url": "https://hub.example/catalogue",
    "signer_public_key": "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
    "signature_profile": SIGNATURE_PROFILE,
    "peers": [
        "https://a.example/.well-known/agent-marketplace",
        "https://b.example/sub/.well-known/ai-market.json",
    ],
}


def test_discovery_base_strips_either_well_known_path():
    assert discovery_base("https://a.example/.well-known/agent-marketplace") == "https://a.example"
    assert discovery_base("https://b.example/sub/.well-known/ai-market.json/") == "https://b.example/sub"
    assert discovery_base("https://c.example/") == "https://c.example"


def test_a_draft_document_is_readable_by_every_legacy_reader():
    out = normalize_discovery_document(DRAFT)
    assert is_draft_document(DRAFT) and not is_draft_document(out)
    assert out["manifest_url"] == DRAFT["catalogue_url"]
    assert out["catalogue_url"] == DRAFT["catalogue_url"]          # nothing is removed
    assert out["peers"] == [
        {"url": "https://a.example", "name": "https://a.example",
         "well_known_url": "https://a.example/.well-known/agent-marketplace"},
        {"url": "https://b.example/sub", "name": "https://b.example/sub",
         "well_known_url": "https://b.example/sub/.well-known/ai-market.json"},
    ]
    assert DRAFT["peers"][0].startswith("https://")                 # input untouched

    from aimarket_hub.validator import validate_well_known
    assert validate_well_known(out) == []


def test_a_legacy_document_passes_through_unchanged():
    assert normalize_discovery_document(LEGACY) == LEGACY


def test_a_document_carrying_both_names_keeps_the_legacy_value():
    both = {**LEGACY, "catalogue_url": "https://elsewhere.example/catalogue"}
    assert normalize_discovery_document(both)["manifest_url"] == LEGACY["manifest_url"]


def test_the_draft_document_is_built_from_the_legacy_one():
    doc = draft_discovery_document(
        {**LEGACY, "hub_url": "https://hub.example"},
        ["https://other.example" + LEGACY_WELL_KNOWN_PATH],
    )
    assert doc["catalogue_url"] == LEGACY["manifest_url"]
    assert doc["manifest_url"] == LEGACY["manifest_url"]            # for a legacy reader that lands here
    assert doc["signer_public_key"] == LEGACY["signer_public_key"]
    assert doc["signature_profile"] == SIGNATURE_PROFILE
    assert doc["capabilities_count"] == 7
    assert doc["peers"] == ["https://other.example/.well-known/ai-market.json"]
    assert doc["legacy_discovery_url"] == "https://hub.example" + LEGACY_WELL_KNOWN_PATH
    assert doc["generated_at"].endswith("Z")
    assert DRAFT_WELL_KNOWN_PATH == "/.well-known/agent-marketplace"
    # round trip: what we publish, we can read
    back = normalize_discovery_document(doc)
    from aimarket_hub.validator import validate_well_known
    assert validate_well_known(back) == []
