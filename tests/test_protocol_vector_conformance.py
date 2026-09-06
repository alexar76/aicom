"""The protocol's own test vectors must verify with the implementations that ship.

Four packages independently compute a canonical string over the same records: the hub
(`aimarket_hub.signing`), the oracle library (`oracle_core.signing`), the consumer SDK
(`aimarket_agent.receipts`) and the vector generator
(`aimarket-protocol/test-vectors/generate.py`). Nothing compared them, and by 2026-07-29 two
had drifted — in the direction that makes a signature cover LESS:

  * `receipt-signed.json` was signed over FIVE fields. The hub signs seven. So `success` and
    `latency_ms` sat outside the signature, and anyone implementing a client from these
    vectors — which is what they are for — would have accepted a receipt whose `success` was
    flipped from false to true with the signature still verifying.
  * `manifest-signed.json` was signed over THREE fields, without `tools_hash` or
    `by_hub_hash`. A relay could rewrite every price in `tools[]` and every per-peer
    `trust_score` in `by_hub` and the signature would still verify. That is precisely what
    the hub's comment says those digests exist to prevent, and `oracle_core` had been missing
    `by_hub_hash` for the same reason — which is why no oracle could federate at all until it
    was fixed. The vectors were the third copy of that bug and the only one nobody checked.

Production was never affected: the live hub has signed seven fields and five all along, and
real receipts verify. What was wrong was the reference material, which is worse in a way,
because it is what a third party builds against.

Verifying the COMMITTED vector against the hub's canonical is the whole guard: it can only
pass if the generator used the same formula, so drift in either one fails here.
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VECTORS = ROOT / "aimarket-protocol" / "test-vectors"

for pkg in ("aimarket-hub", "aimarket-agent", "oracles/core"):
    path = ROOT / pkg
    if path.is_dir() and str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_every_implementation_the_guard_compares_is_importable():
    """A guard that skips itself is not a guard.

    Each check below degrades to ``pytest.skip`` when a package cannot be imported, which is
    right for a local checkout missing an optional dependency — and wrong as the last word,
    because the canonical-parity check between the hub and the oracle library is the whole
    reason this file exists. Measured: without ``fastapi`` installed, ``oracle_core`` fails to
    import and that check vanishes, leaving 21 green tests and no parity guard at all.

    So this one FAILS instead of skipping, and names what is missing. CI installs all four.
    """
    missing = []
    for module, install in (
        ("aimarket_hub.signing", "pip install ./aimarket-hub  (or put it on PYTHONPATH)"),
        ("aimarket_agent.receipts", "pip install ./aimarket-agent"),
        ("oracle_core.signing", "pip install ./oracles/core"),
        ("aimarket_bridges.receipts", "pip install ./aimarket-bridges"),
    ):
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001 - the reason is the useful part
            missing.append(f"{module}: {type(exc).__name__}: {exc} -> {install}")

    assert not missing, (
        "the cross-package canonical guard cannot run against:\n  " + "\n  ".join(missing)
    )


def _vector(name: str) -> dict:
    path = VECTORS / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def key() -> str:
    return _vector("well-known.json")["signer_public_key"]


@pytest.fixture(scope="module")
def hub_signer():
    """A throwaway hub Signer, used only for its canonical-string methods."""
    try:
        from aimarket_hub.signing import Signer
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"aimarket_hub not importable: {exc}")
    return Signer(str(pathlib.Path(tempfile.mkdtemp()) / "key"))


@pytest.fixture
def factory_signing(tmp_path, monkeypatch):
    """The factory's signer, loaded without dragging in the whole web backend.

    `signing.py` imports `paths` → `core.paths` → the app's settings, so a plain import
    needs the factory's entire dependency set and skips everywhere else. Skipping is what
    left the fifth implementation unchecked for a month; this guard is about one canonical
    string, so the two modules it actually needs are stubbed and the rest is not loaded.
    """
    import importlib.util
    import types

    pkg = "web.backend.services.ai_market_protocol"
    for name in ("web", "web.backend", "web.backend.services", pkg):
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = []  # a package, so submodule imports resolve
            monkeypatch.setitem(sys.modules, name, module)
    paths = types.ModuleType(f"{pkg}.paths")
    paths.signing_key_path = lambda: tmp_path / "factory_key"
    monkeypatch.setitem(sys.modules, f"{pkg}.paths", paths)

    spec = importlib.util.spec_from_file_location(
        f"{pkg}.signing",
        ROOT / "web" / "backend" / "services" / "ai_market_protocol" / "signing.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, f"{pkg}.signing", module)
    spec.loader.exec_module(module)
    return module


def _ed25519_ok(signature_b64: str, message: str, key_b64: str) -> bool:
    crypto = pytest.importorskip("cryptography")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    del crypto
    pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_b64))
    try:
        pub.verify(base64.b64decode(signature_b64), message.encode())
        return True
    except InvalidSignature:
        return False


# ── the receipt vector ────────────────────────────────────────────────────────

class TestReceiptVector:
    def test_the_sdk_verifies_the_canonical_vector(self, key):
        """The consumer SDK is what a third party actually installs."""
        receipts = pytest.importorskip("aimarket_agent.receipts")
        result = receipts.verify_receipt(_vector("receipt-signed.json"), key)
        assert bool(result), (
            f"the protocol's own signed receipt does not verify with the SDK: {result.reason}"
        )

    def test_the_vector_is_signed_over_the_hub_seven_field_canonical(self, key, hub_signer):
        """The drift guard. Passes only if the generator used the hub's formula."""
        receipt = _vector("receipt-signed.json")
        canonical = hub_signer.receipt_canonical(receipt, 1)
        assert canonical.count("|") == 6, f"expected 7 fields, got: {canonical}"
        assert "success:" in canonical and "latency_ms:" in canonical
        assert _ed25519_ok(receipt["signature"]["value"], canonical, key), (
            "the vector's signature does not match the hub's canonical — one of the two "
            "drifted. Regenerate with test-vectors/generate.py after making them agree."
        )

    def test_the_sdk_and_the_hub_agree_byte_for_byte(self, hub_signer):
        receipts = pytest.importorskip("aimarket_agent.receipts")
        receipt = _vector("receipt-signed.json")
        assert receipts.canonical_string(receipt) == hub_signer.receipt_canonical(receipt, 1)

    def test_flipping_success_breaks_the_signature(self, key):
        """The reason the five-field canonical was a security defect and not untidiness.

        A rejection receipt says success:false. If that field is unsigned, the party holding
        the receipt can present it as a success.
        """
        receipts = pytest.importorskip("aimarket_agent.receipts")
        receipt = dict(_vector("receipt-signed.json"))
        receipt["success"] = not receipt.get("success")
        assert not bool(receipts.verify_receipt(receipt, key))

    def test_changing_latency_breaks_the_signature(self, key):
        receipts = pytest.importorskip("aimarket_agent.receipts")
        receipt = dict(_vector("receipt-signed.json"))
        receipt["latency_ms"] = int(receipt.get("latency_ms", 0)) + 1
        assert not bool(receipts.verify_receipt(receipt, key))

    def test_an_unsigned_field_does_not_affect_verification(self, key, hub_signer):
        """`channel_id` rides along outside the v1 canonical, by design: the canonical is a
        fixed field list, not "whatever the object happens to hold".

        This used to require the shipped vector to already carry a `channel_id`, and skipped
        its own point the day the vector was regenerated without one. The property does not
        depend on the fixture's contents: add the field here, prove the canonical string is
        byte-identical (so the assertion cannot go vacuous), and check the signature still
        verifies.
        """
        receipts = pytest.importorskip("aimarket_agent.receipts")
        receipt = dict(_vector("receipt-signed.json"))
        before = hub_signer.receipt_canonical(receipt, 1)
        receipt["channel_id"] = "ch_something_else"
        assert hub_signer.receipt_canonical(receipt, 1) == before, (
            "channel_id reached the v1 canonical — then it is a signed field and this test "
            "is asserting the opposite of the contract"
        )
        assert bool(receipts.verify_receipt(receipt, key))


# ── the manifest vector ───────────────────────────────────────────────────────

class TestManifestVector:
    def test_the_vector_is_signed_over_the_five_field_canonical(self, key, hub_signer):
        manifest = _vector("manifest-signed.json")
        canonical = hub_signer.manifest_canonical(manifest)
        assert "tools_hash:" in canonical and "by_hub_hash:" in canonical, canonical
        assert _ed25519_ok(manifest["signature"]["value"], canonical, key), (
            "the manifest vector's signature does not cover tools[] and by_hub — a relay "
            "could rewrite every price and every peer trust score undetected"
        )

    def test_the_oracle_library_computes_the_same_canonical(self, hub_signer):
        """oracle_core signs its own manifest and the hub verifies it, so a single differing
        byte means no oracle can federate. That happened: `by_hub_hash` was missing."""
        try:
            from oracle_core.signing import Signer as OracleSigner
        except Exception as exc:
            pytest.skip(f"oracle_core not importable: {exc}")
        oracle = OracleSigner(str(pathlib.Path(tempfile.mkdtemp()) / "key"))
        manifest = _vector("manifest-signed.json")
        assert oracle.manifest_canonical(manifest) == hub_signer.manifest_canonical(manifest)

    def test_tampering_with_tools_breaks_the_signature(self, key, hub_signer):
        manifest = json.loads(json.dumps(_vector("manifest-signed.json")))
        tools = manifest.get("tools")
        if not tools:
            pytest.skip("the manifest vector carries no tools[] to tamper with")
        tools[0]["price_per_call_usd"] = 999.0
        assert not _ed25519_ok(
            manifest["signature"]["value"], hub_signer.manifest_canonical(manifest), key
        ), "a rewritten price must invalidate the manifest signature"

    def test_tampering_with_by_hub_breaks_the_signature(self, key, hub_signer):
        """Even ADDING a by_hub block must break it: an absent by_hub hashes as {}."""
        manifest = json.loads(json.dumps(_vector("manifest-signed.json")))
        manifest["by_hub"] = {"evil.example": {"trust_score": 1.0}}
        assert not _ed25519_ok(
            manifest["signature"]["value"], hub_signer.manifest_canonical(manifest), key
        )

    def test_the_factory_computes_the_same_canonical(self, hub_signer, factory_signing):
        """The factory was the fifth implementation, and nobody compared it.

        `web/backend` signed three fields — capabilities_count, generated_at,
        protocol_version — as canonical JSON: the exact shape this file's docstring
        describes being fixed in the vectors on 2026-07-29, still live on
        magic-ai-factory.com a month later. Its own hub refused the manifest
        (`manifest_signed`), so the factory could not be admitted to the federation it
        publishes into, and every price in `tools[]` sat outside the signature.
        """
        manifest = _vector("manifest-signed.json")
        assert factory_signing.manifest_canonical(manifest) == hub_signer.manifest_canonical(
            manifest
        )

    def test_a_factory_signature_verifies_against_the_hub(self, hub_signer, factory_signing):
        """Round trip: signed by the factory, verified by the hub that must admit it."""
        manifest = json.loads(json.dumps(_vector("manifest-signed.json")))
        manifest["signature"] = factory_signing.manifest_signature(manifest)
        assert hub_signer.verify_manifest_signature(
            manifest, manifest["signature"]["public_key"],
        ), "a manifest this factory signs must verify with the hub's canonical"
        manifest["tools"][0]["price_per_call_usd"] = 999.0
        assert not hub_signer.verify_manifest_signature(
            manifest, manifest["signature"]["public_key"],
        ), "a rewritten price must invalidate the factory's signature too"

    def test_the_factory_signs_discovery_the_way_the_hub_reads_it(
        self, hub_signer, factory_signing
    ):
        """`/.well-known/ai-market.json` — signed over the whole document minus signature."""
        doc = {"name": "Fábrica", "capabilities_count": 2, "peers": []}
        doc["signature"] = factory_signing.object_signature(doc)
        assert hub_signer.verify(
            doc["signature"]["public_key"],
            doc["signature"]["value"],
            hub_signer.object_canonical(doc),
        ), "non-ASCII in a discovery document must not change where it verifies"


# ── the v2 canonical ──────────────────────────────────────────────────────────

class TestReceiptV2:
    """The hub signs a rejection receipt at v2, because on a rejection every v1 field is a
    constant and the signature therefore said nothing about WHY the money came back.

    The SDK computed only v1 until 2026-07-29 and so answered `invalid-signature` for every
    v2 receipt — the same false-alarm class as verifying against the wrong key, and on the
    receipts a buyer most wants to check.
    """

    @pytest.fixture
    def rejection(self):
        return {
            "nonce": "rcpt_v2", "product_id": "prod-x", "capability_id": "x.y@v1",
            "price_usd": 0.0, "timestamp": "2026-07-29T10:00:00Z", "success": False,
            "latency_ms": 0, "reason": "verification score below threshold",
            "verify_score": 0.31, "trace_id": "tr_abc", "refunded": True,
            "channel_id": "ch_1",
        }

    def test_the_hub_signs_a_rejection_at_v2(self, hub_signer, rejection):
        from aimarket_hub.signing import resolve_receipt_version

        assert resolve_receipt_version(rejection) == 2
        assert hub_signer.sign_receipt(rejection).get("version") == 2

    def test_hub_and_sdk_agree_on_a_v2_receipt(self, hub_signer, rejection):
        receipts = pytest.importorskip("aimarket_agent.receipts")
        signed = {**rejection, "signature": hub_signer.sign_receipt(rejection)}
        assert hub_signer.verify_receipt_signature(signed) is True
        result = receipts.verify_receipt(signed, hub_signer.public_key_b64)
        assert bool(result) is True, f"SDK rejects a valid v2 receipt: {result.reason}"

    def test_the_v2_canonicals_are_byte_identical(self, hub_signer, rejection):
        receipts = pytest.importorskip("aimarket_agent.receipts")
        signed = {**rejection, "signature": hub_signer.sign_receipt(rejection)}
        assert receipts.canonical_string(signed) == hub_signer.receipt_canonical(signed, 2)

    @pytest.mark.parametrize("field,value", [
        ("reason", "something else entirely"),
        ("verify_score", 0.99),
        ("refunded", False),
        ("trace_id", "tr_other"),
    ])
    def test_tampering_with_v2_evidence_breaks_the_signature(
        self, hub_signer, rejection, field, value
    ):
        """The point of v2: the evidence a rejection is argued from is now signed."""
        receipts = pytest.importorskip("aimarket_agent.receipts")
        signed = {**rejection, "signature": hub_signer.sign_receipt(rejection)}
        tampered = {**signed, field: value}
        assert not bool(receipts.verify_receipt(tampered, hub_signer.public_key_b64))

    def test_a_v1_receipt_still_verifies_without_a_version_marker(self, hub_signer):
        """Back-compat: a receipt signed before v2 existed carries no version and must keep
        verifying forever."""
        receipts = pytest.importorskip("aimarket_agent.receipts")
        invoke = {"nonce": "n1", "product_id": "p", "capability_id": "c@v1",
                  "price_usd": 0.004, "timestamp": "2026-07-29T10:00:00Z",
                  "success": True, "latency_ms": 12}
        signed = {**invoke, "signature": hub_signer.sign_receipt(invoke)}
        assert "version" not in signed["signature"], "a v1 block must stay byte-identical"
        assert bool(receipts.verify_receipt(signed, hub_signer.public_key_b64))

    @pytest.mark.parametrize("bad,expected", [
        ("two", "unreadable-signature-version"),
        (0, "unreadable-signature-version"),
        (9, "unsupported-canonical-version:9"),
    ])
    def test_an_unusable_version_fails_closed_with_its_own_reason(
        self, hub_signer, rejection, bad, expected
    ):
        """Not "invalid-signature": blaming the receipt for the verifier's age is the mistake
        this module already made once, with the wrong key."""
        receipts = pytest.importorskip("aimarket_agent.receipts")
        signed = {**rejection, "signature": hub_signer.sign_receipt(rejection)}
        signed["signature"] = {**signed["signature"], "version": bad}
        result = receipts.verify_receipt(signed, hub_signer.public_key_b64)
        assert bool(result) is False
        assert result.reason == expected, result.reason


# ── the bridge, which is the newest consumer of all this ──────────────────────

class TestBridgeAgreesWithTheVectors:
    def test_the_bridge_verifies_the_canonical_receipt_vector(self, key):
        """aimarket-bridges resolves the signing key per capability ORIGIN. Point it at a
        stub serving the vector's well-known and the vector must verify."""
        httpx = pytest.importorskip("httpx")
        bridges = ROOT / "aimarket-bridges"
        if bridges.is_dir() and str(bridges) not in sys.path:
            sys.path.insert(0, str(bridges))
        try:
            from aimarket_bridges.receipts import OriginKeyResolver
        except Exception as exc:
            pytest.skip(f"aimarket_bridges not importable: {exc}")

        well_known = _vector("well-known.json")
        client = httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=well_known))
        )
        check = OriginKeyResolver("https://hub.test", client=client).check(
            _vector("receipt-signed.json"), source_hub="https://peer.test/family"
        )
        assert check.verified is True, check.reason
        assert check.key == key, "the bridge must use the ORIGIN's published key"
