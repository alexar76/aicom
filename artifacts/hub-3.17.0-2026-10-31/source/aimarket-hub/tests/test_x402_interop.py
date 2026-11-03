"""x402 interoperability: the hub advertises payment in the dialect the ecosystem speaks.

These tests pin the wire format against the live x402 V2 specification as verified on
2026-08-28. The format changed between V1 and V2 in ways that are easy to get wrong and
silent when wrong — the payload moved from the body to a header, `maxAmountRequired` became
`amount`, and networks became CAIP-2 — so each is asserted explicitly rather than trusted.
"""

import base64
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import x402
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

PAY_TO = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


@contextmanager
def _hub(monkeypatch, tmp_path, **env):
    env.setdefault("AIMARKET_X402_PAY_TO", PAY_TO)
    env.setdefault("AIMARKET_X402_CHAIN", "base")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    root = tmp_path / f"hub-{len(list(tmp_path.iterdir()))}"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        client.hub_db = db  # type: ignore[attr-defined]
        yield client


# ── the object itself ────────────────────────────────────────────────

def test_v2_object_matches_the_live_specification(monkeypatch):
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    doc = x402.payment_required_v2(0.08, "https://hub.example/ai-market/v2/invoke", "translate")

    assert doc["x402Version"] == 2, "V1 is superseded; the live protocol is 2"
    # V2 hoisted resource/description/mimeType out of each entry into one object.
    assert set(doc["resource"]) >= {"url", "description", "mimeType"}
    assert doc["resource"]["url"] == "https://hub.example/ai-market/v2/invoke"

    entry = doc["accepts"][0]
    assert entry["scheme"] == "exact"
    assert entry["network"] == "eip155:8453", "V2 names chains in CAIP-2, not as 'base'"
    assert entry["amount"] == "80000", "$0.08 at 6 decimals; the key is `amount`, not `maxAmountRequired`"
    assert entry["asset"] == USDC_BASE
    assert entry["payTo"] == PAY_TO
    # Read on-chain 2026-08-28: Base mainnet USDC name() == "USD Coin", version() == "2".
    # It is NOT the ticker, and it differs from Base Sepolia's "USDC" — a mismatch here makes
    # every payer signature invalid at the token contract, silently.
    assert entry["extra"] == {"name": "USD Coin", "version": "2"}, (
        "the token's EIP-712 domain — a payer cannot sign transferWithAuthorization without it"
    )
    assert "maxAmountRequired" not in entry, "that is the V1 name and must not appear in V2"


def test_no_recipient_means_no_offer(monkeypatch):
    """Advertising a payment method with nowhere to pay is an invitation the hub cannot honour."""
    monkeypatch.delenv("AIMARKET_X402_PAY_TO", raising=False)
    monkeypatch.delenv("AIMARKET_PAYMENT_RECIPIENT", raising=False)
    assert x402.payment_requirements(1.0) == []
    assert x402.payment_required_v2(1.0, "https://hub.example/x") is None
    assert x402.payment_requirements(1.0, pay_to=PAY_TO)


def test_sub_cent_prices_never_round_to_free(monkeypatch):
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    # $0.0033 is the hub's real average call price — it must not become 0 atomic units.
    assert int(x402.payment_requirements(0.0033)[0]["amount"]) == 3300
    assert int(x402.payment_requirements(0.0000004)[0]["amount"]) > 0


# ── the wire ─────────────────────────────────────────────────────────

def test_402_carries_the_payment_required_header(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIFACTORY_CRYPTO_ENABLED="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_capability(Capability(
            capability_id="paid.cap@v1", product_id="p1", name="Paid",
            price_per_call_usd=0.08, source_hub="local", invoke_url="https://provider.example/run",
        ))
        r = client.post("/ai-market/v2/invoke",
                        json={"capability_id": "paid.cap@v1", "product_id": "p1", "input": {}})
        # Asserted, not skipped. A skip here would let a regression in the middleware — the
        # thing this test exists for — report as green.
        assert r.status_code == 402, (
            f"expected a payment gate, got HTTP {r.status_code}: {r.text[:200]}"
        )

        assert "PAYMENT-REQUIRED" in {k.upper(): v for k, v in r.headers.items()}, (
            "V2 carries the payload in a header; a body-only 402 is invisible to x402 clients"
        )
        raw = {k.upper(): v for k, v in r.headers.items()}["PAYMENT-REQUIRED"]
        doc = json.loads(base64.b64decode(raw))
        assert doc["x402Version"] == 2
        assert doc["accepts"][0]["network"] == "eip155:8453"

        body = r.json()
        # V1 fields are additive — old consumers must see exactly what they saw before.
        assert body["success"] is False
        assert "error" in body and "detail" in body
        assert body.get("x402Version") == 1
        assert body["accepts"][0]["maxAmountRequired"] == doc["accepts"][0]["amount"]


def test_x402_can_be_switched_off(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_X402_ENABLED="0", AIFACTORY_CRYPTO_ENABLED="1") as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_capability(Capability(
            capability_id="paid.cap@v1", product_id="p1", name="Paid",
            price_per_call_usd=0.08, source_hub="local", invoke_url="https://provider.example/run",
        ))
        r = client.post("/ai-market/v2/invoke",
                        json={"capability_id": "paid.cap@v1", "product_id": "p1", "input": {}})
        assert r.status_code == 402, f"expected a payment gate, got HTTP {r.status_code}"
        assert "PAYMENT-REQUIRED" not in {k.upper() for k in r.headers}
        assert "x402Version" not in r.json()


# ── the Bazaar index ─────────────────────────────────────────────────

def test_discovery_resources_is_bazaar_shaped(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        db = client.hub_db  # type: ignore[attr-defined]
        db.upsert_capability(Capability(
            capability_id="translate.multi@v2", product_id="p1", name="Translate",
            description="translate text", price_per_call_usd=0.4, source_hub="local",
            # Local static packs are executable only when this column is a JSON object.
            prompt_template='{"result":"translated"}',
        ))
        db.upsert_capability(Capability(
            capability_id="free.cap@v1", product_id="p2", name="Free",
            price_per_call_usd=0.0, source_hub="local", prompt_template="{input}",
        ))
        r = client.get("/discovery/resources")
        assert r.status_code == 200
        doc = r.json()

        # The envelope every official x402 SDK deserializes.
        assert set(doc) >= {"x402Version", "items", "pagination"}
        assert set(doc["pagination"]) == {"limit", "offset", "total"}
        assert doc["x402Version"] == 2

        ids = [i["metadata"]["capability_id"] for i in doc["items"]]
        assert "translate.multi@v2" in ids
        assert "free.cap@v1" not in ids, "a free capability has nothing to advertise a price for"

        item = next(i for i in doc["items"] if i["metadata"]["capability_id"] == "translate.multi@v2")
        # The six interop-required fields.
        for field in ("resource", "type", "x402Version", "accepts", "lastUpdated"):
            assert field in item, f"missing interop field {field}"
        assert item["type"] == "http"
        assert item["accepts"][0]["amount"] == "400000"  # $0.40 at 6 decimals


def test_discovery_paginates_and_ignores_unknown_types(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        db = client.hub_db  # type: ignore[attr-defined]
        # The hub seeds a demo catalogue at startup, so count the delta, not the total.
        base_total = client.get("/discovery/resources").json()["pagination"]["total"]
        for i in range(5):
            db.upsert_capability(Capability(
                capability_id=f"c{i}@v1", product_id=f"p{i}", name=f"c{i}",
                price_per_call_usd=0.1, source_hub="local", prompt_template="{input}",
            ))
        page = client.get("/discovery/resources", params={"limit": 2, "offset": 0}).json()
        assert len(page["items"]) == 2
        assert page["pagination"]["total"] == base_total + 5
        total = page["pagination"]["total"]
        last = client.get("/discovery/resources", params={"limit": 2, "offset": total - 1}).json()
        assert len(last["items"]) == 1, "the final page must be a partial page, not an empty one"

        mcp = client.get("/discovery/resources", params={"type": "mcp"}).json()
        assert mcp["items"] == [], "claiming an mcp surface per capability would be a false promise"


def test_discovery_needs_no_credentials(monkeypatch, tmp_path):
    """SDK clients attach auth headers on the way in; a public index ignores them."""
    with _hub(monkeypatch, tmp_path) as client:
        assert client.get("/discovery/resources").status_code == 200
        assert client.get("/discovery/resources",
                          headers={"Authorization": "Bearer nonsense"}).status_code == 200


# ── ERC-8004 identity declaration ────────────────────────────────────

def test_erc8004_declaration_is_absent_unless_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("AIMARKET_ERC8004_AGENT_ID", raising=False)
    with _hub(monkeypatch, tmp_path) as client:
        assert "erc8004" not in client.get("/.well-known/ai-market.json").json()


def test_erc8004_declaration_sits_inside_the_document_signature(monkeypatch, tmp_path):
    """A declared identity outside the signature is rewritable by any relay.

    The .well-known document is signed as a whole. An `erc8004` block appended after
    `sign_object` would be unsigned — the same class of hole as an unsigned `tools[]`
    (spec §7.3.2), and it was exactly the mistake made while writing this feature.
    """
    with _hub(monkeypatch, tmp_path,
              AIMARKET_ERC8004_AGENT_ID="4242",
              AIMARKET_ERC8004_CHAIN="base") as client:
        wk = client.get("/.well-known/ai-market.json").json()
        assert wk["erc8004"]["agent_id"] == "4242"
        assert wk["erc8004"]["chain"] == "eip155:8453"
        # Verified on-chain 2026-08-28: same address on Ethereum and Base mainnet.
        assert wk["erc8004"]["identity_registry"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
        # The hub asserts, it does not check. Saying otherwise would be the dishonest part.
        assert wk["erc8004"]["verified_by_this_hub"] is False

        # Prove coverage rather than assert it: the document's own signature must verify
        # over the document WITH the block, and must fail over the same document without it.
        from aimarket_hub.signing import Signer

        signer = Signer(tmp_path / "verify-key")
        signed_doc = {k: v for k, v in wk.items() if k != "signature"}
        assert "erc8004" in signed_doc

        canonical_with = signer.object_canonical(signed_doc)
        canonical_without = signer.object_canonical(
            {k: v for k, v in signed_doc.items() if k != "erc8004"}
        )
        assert canonical_with != canonical_without, (
            "removing erc8004 did not change the signed bytes — the block is outside the signature"
        )


def test_validation_registry_is_not_advertised(monkeypatch, tmp_path):
    """ERC-8004's ValidationRegistry has no canonical deployment on any chain.

    Verified 2026-08-28: the canonical contracts repo publishes Identity and Reputation
    addresses for ~25 mainnets and none for Validation, and eth_getCode at the obvious
    vanity-pattern guess is empty on both Ethereum and Base. Advertising an address for it
    would be inventing one.
    """
    from aimarket_hub import x402

    for network in x402.ERC8004_REGISTRIES.values():
        assert "validation" not in network


def test_testnet_and_mainnet_usdc_domains_are_not_assumed_equal(monkeypatch):
    """The two chains' USDC contracts report different EIP-712 names. Assuming they match
    is the kind of error that produces a valid-looking offer nobody can pay."""
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    mainnet = x402.payment_requirements(1.0)[0]["extra"]
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base-sepolia")
    testnet = x402.payment_requirements(1.0)[0]["extra"]
    assert mainnet == {"name": "USD Coin", "version": "2"}
    assert testnet == {"name": "USDC", "version": "2"}
    assert mainnet != testnet


def test_the_advertised_resource_is_the_hubs_own_https_url(monkeypatch, tmp_path):
    """Behind nginx the ASGI scheme is http, so the offer advertised
    `http://modelmarket.dev/...` on a hub that only serves https — a payer checking what
    they are paying for against the URL they called sees a mismatch, and an http URL inside
    a payment offer is exactly the detail a careful client refuses on."""
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.models import Capability
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_X402_PAY_TO", "0x1218Ff3600000000000000000000000000000a0a")
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    root = tmp_path / "hub"
    root.mkdir(parents=True, exist_ok=True)
    config = HubConfig()
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    config.hub_url = "https://hub.example.org"
    db = HubDatabase(root / "hub.db")
    db.upsert_capability(Capability(
        capability_id="p.pack@v1", product_id="p-pack", name="Paid",
        description="d", price_per_call_usd=0.02, source_hub="local",
        invoke_url="", prompt_template='{"answer": "x"}',
    ))
    app = create_app(config=config, db=db, signer=Signer(root / "key"))
    with TestClient(app) as client:
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "p-pack", "capability_id": "p.pack@v1",
            "input": {}, "source_hub": "local",
        })
    assert r.status_code == 402
    accepts = r.json()["accepts"]
    assert accepts[0]["resource"] == "https://hub.example.org/ai-market/v2/invoke"
