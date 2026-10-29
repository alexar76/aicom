"""The factory's manifest signature must carry its post-quantum half.

This is a regression test for a silent downgrade, not for the crypto. The factory signed
manifests with Ed25519 alone all through phase 2 of the PQC migration and nothing in the
process said so — no warning, no failed health check, a well-formed signed manifest on
every fetch. It surfaced only because hub.attestedmemory.net had reached phase 3
(AIMARKET_PQC_REQUIRE=1), refused every manifest from here, and froze its copy of this
catalogue for a week while still reporting the peer as active and freshly crawled.

So the assertions are: the pq_* block is PRESENT when the flag is on, the hub's own
verifier accepts the result under require_pq, and the flag being on with the library
missing RAISES instead of quietly producing a classical signature.
"""

from __future__ import annotations

import base64
import importlib
import sys

import pytest

from web.backend.services.ai_market_protocol import paths as factory_paths
from web.backend.services.ai_market_protocol import signing as factory_signing

sys.path.insert(0, "aimarket-hub")
from aimarket_hub.signing import Signer  # noqa: E402

MANIFEST = {
    "capabilities_count": 2,
    "generated_at": "2026-09-16T10:00:00Z",
    "protocol_version": "v1",
    "tools": [{"name": "run@v1", "price_per_call_usd": 0.35}],
    "by_hub": {},
}


@pytest.fixture()
def factory_key(tmp_path, monkeypatch):
    """Sign with a throwaway identity, never the developer's own key file."""
    key = tmp_path / "factory_signing_key"
    monkeypatch.setattr(factory_paths, "signing_key_path", lambda: key)
    monkeypatch.setattr(factory_signing, "signing_key_path", lambda: key)
    monkeypatch.setenv("AIMARKET_PQC", "1")
    return key


def test_manifest_signature_is_hybrid(factory_key):
    signature = factory_signing.manifest_signature(MANIFEST)
    assert signature["pq_algorithm"] == "ml-dsa-65"
    assert signature["pq_value"] and signature["pq_public_key"]


def test_hub_accepts_the_manifest_when_pq_is_required(factory_key):
    manifest = dict(MANIFEST)
    signature = factory_signing.manifest_signature(manifest)
    manifest["signature"] = signature
    canonical = Signer.__new__(Signer).manifest_canonical(manifest)
    assert Signer.verify_hybrid(
        signature["public_key"], signature, canonical, require_pq=True
    )


def test_a_substituted_pq_signature_is_refused(factory_key):
    manifest = dict(MANIFEST)
    signature = factory_signing.manifest_signature(manifest)
    manifest["signature"] = signature
    canonical = Signer.__new__(Signer).manifest_canonical(manifest)
    forged = dict(signature, pq_value=base64.b64encode(b"\x00" * 3309).decode())
    assert not Signer.verify_hybrid(
        signature["public_key"], forged, canonical, require_pq=True
    )


def test_the_pq_identity_survives_a_restart(factory_key):
    first = factory_signing.manifest_signature(MANIFEST)["pq_public_key"]
    importlib.reload(factory_signing)
    factory_signing.signing_key_path = lambda: factory_key
    assert factory_signing.manifest_signature(MANIFEST)["pq_public_key"] == first


def test_the_flag_off_still_signs_classically(factory_key, monkeypatch):
    monkeypatch.setenv("AIMARKET_PQC", "0")
    signature = factory_signing.manifest_signature(MANIFEST)
    assert signature["algorithm"] == "ed25519"
    assert "pq_value" not in signature


def test_the_flag_on_without_the_library_refuses_to_downgrade(factory_key, monkeypatch):
    monkeypatch.setattr(factory_signing, "_PQ_LIB", False)
    with pytest.raises(factory_signing.PQCMisconfigured):
        factory_signing.manifest_signature(MANIFEST)


def test_pq_first_start_adopts_one_complete_private_identity(factory_key, monkeypatch):
    import stat
    import threading
    from concurrent.futures import ThreadPoolExecutor

    barrier = threading.Barrier(4)
    generate = factory_signing._MLDSA.keygen

    def first_start():
        pair = generate()
        barrier.wait(timeout=10)
        return pair

    monkeypatch.setattr(factory_signing._MLDSA, "keygen", first_start)
    with ThreadPoolExecutor(max_workers=4) as workers:
        pairs = list(workers.map(lambda _: factory_signing._pq_keypair(), range(4)))
    assert len(set(pairs)) == 1
    path = factory_key.with_name(factory_key.name + "_mldsa")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert factory_signing._MLDSA.pk_from_sk(pairs[0][1]) == pairs[0][0]


def test_pq_corrupt_identity_is_not_silently_replaced(factory_key):
    path = factory_key.with_name(factory_key.name + "_mldsa")
    path.write_text("invalid-identity")
    with pytest.raises(ValueError, match="PQ signing identity"):
        factory_signing._pq_keypair()
    assert path.read_text() == "invalid-identity"
