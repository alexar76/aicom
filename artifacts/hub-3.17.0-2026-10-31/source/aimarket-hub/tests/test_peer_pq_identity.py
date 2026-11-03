"""Pinning a peer's post-quantum identity — the thing that makes requiring PQ mean anything.

Without a pinned PQ key, `verify_hybrid` reads `pq_public_key` out of the signature object, so the
PQ layer is useless against the only adversary it exists for: one who can forge Ed25519 forges it
against the pinned classical key and attaches an ML-DSA keypair of their own. A post-quantum
signature is worth exactly what the pinning of its public key is worth.

Two properties are load-bearing here and neither is obvious:

* **First sight is the only chance.** The pin has to be recorded while classical signatures can
  still authenticate it. A PQ key first seen after Ed25519 falls cannot be attributed to anyone,
  which is why the crawler records it on the first crawl rather than waiting for enforcement.

* **A changed PQ key is recorded, not rejected.** Rejecting would quarantine every legitimate
  rotation, including the ones this fleet causes itself — a component whose key path is not on a
  volume regenerates its ML-DSA key on every container recreate. Enforcement belongs to
  `AIMARKET_PQC_REQUIRE`, which already gates the verification policy.

And one regression guard: the `peers` upsert names its columns in three separate lists, and the
code says so — a column present in one and missing from another blanks itself on every crawl and
reads back as `""` with no error anywhere.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer, pqc_available

pqc_only = pytest.mark.skipif(not pqc_available(), reason="dilithium-py not installed")

CRAWLER = Path(__file__).resolve().parents[1] / "aimarket_hub" / "crawler.py"
DATABASE = Path(__file__).resolve().parents[1] / "aimarket_hub" / "database.py"


# ── the model and the three lists ────────────────────────────────────────────────────────────


def test_peer_carries_a_pq_key_and_a_mismatch_slot():
    peer = Peer(url="https://x.test", name="x")
    assert peer.pq_public_key == ""
    assert peer.advertised_pq_public_key == ""


def test_both_columns_appear_in_all_three_lists():
    """The failure this guards is silent: the value blanks on every crawl and reads back as ""."""
    src = DATABASE.read_text(encoding="utf-8")
    # Located by walking FORWARD from the peers statement. `VALUES (?` and `commit()` both occur
    # earlier in the file for other tables, and searching from zero produced a reversed, empty
    # slice that made this test pass vacuously.
    start = src.index("INSERT OR REPLACE INTO peers")
    values_at = src.index("VALUES (?", start)
    commit_at = src.index("self._conn.commit()", values_at)
    insert_cols = src[start:values_at]
    values_tuple = src[values_at:commit_at]
    row_reader = src[src.index("def _row_to_peer"):]
    assert insert_cols and values_tuple, "the slices must not be empty"
    for column in ("pq_public_key", "advertised_pq_public_key"):
        # 1) the INSERT column list, 2) the VALUES tuple, 3) _row_to_peer
        assert column in insert_cols, f"{column} missing from the INSERT column list"
        assert f"peer.{column}" in values_tuple, f"{column} missing from the VALUES tuple"
        assert f'{column}=d.get("{column}")' in row_reader, f"{column} missing from _row_to_peer"
    # The two must also be positionally consistent: one extra placeholder or one too few shifts
    # every column after it, which is a silent data-corruption bug rather than an error.
    assert insert_cols.count(",") + 1 == values_tuple.count("?")


def test_the_migration_is_registered_once_and_reversible():
    from aimarket_hub.migrations import MIGRATIONS

    rows = [m for m in MIGRATIONS if m[0] == 29]
    assert len(rows) == 1
    _version, name, up, down = rows[0]
    assert name == "029_peer_pq_identity"
    assert "ADD COLUMN pq_public_key" in up
    assert "ADD COLUMN advertised_pq_public_key" in up
    assert "DROP COLUMN pq_public_key" in down
    assert "DROP COLUMN advertised_pq_public_key" in down


def test_a_pq_key_survives_a_round_trip_through_the_database(tmp_path):
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(str(tmp_path / "hub.db"))
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED",
                        pq_public_key="PQKEY", advertised_pq_public_key=""))
    back = db.get_peer("https://p.test")
    assert back is not None
    assert back.pq_public_key == "PQKEY", "the pin blanked on write or read"

    # A second crawl that does not restate the pin must not erase it silently — the crawler
    # always carries it forward, so this asserts the value it carries is what persists.
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED",
                        pq_public_key="PQKEY", advertised_pq_public_key="OTHER"))
    back2 = db.get_peer("https://p.test")
    assert back2.pq_public_key == "PQKEY"
    assert back2.advertised_pq_public_key == "OTHER"


# ── the crawler's decision, asserted on its source because the crawl needs a network ─────────


def test_the_pq_key_is_read_from_inside_the_signature_block():
    """It is part of the signature object, not a sibling of `signer_public_key` — and read only
    when the signature IS an object: a bare-string signature (two strangers published one in
    October 2026) used to raise here and abort the crawl of that peer."""
    src = CRAWLER.read_text(encoding="utf-8")
    assert 'wk_sig = wk.get("signature")' in src
    assert 'wk_sig.get("pq_public_key") if isinstance(wk_sig, dict)' in src


def test_first_sight_pins_without_rejecting_anything():
    src = CRAWLER.read_text(encoding="utf-8")
    assert "pinned_pq_key = prior_pq_key or advertised_pq_key" in src
    # A peer seen for the first time cannot trip the ratchet: there is no pin to regress from.
    first_sight = src[src.index("elif advertised_pq_key and not prior_pq_key:"):]
    first_sight = first_sight[:first_sight.index("peer = Peer(")]
    assert "return None" not in first_sight, "first contact must never be rejected"


def test_the_ratchet_rejects_both_regressions():
    """Withdrawal and substitution are the same attack seen twice, and both must be refused."""
    src = CRAWLER.read_text(encoding="utf-8")
    block = src[src.index("if prior_pq_key and advertised_pq_key != prior_pq_key:"):]
    block = block[:block.index("elif advertised_pq_key and not prior_pq_key:")]
    assert "if _pq_ratchet_enabled():" in block
    assert "record_peer_pq_mismatch" in block
    assert "return None" in block, "the ratchet must actually reject"
    # The operator is told the remedy in the same line as the refusal.
    assert "/federation/peers/repin" in block
    # One condition covers both cases: `advertised != prior` is true when advertised is empty.
    assert 'if advertised_pq_key else "withdrawn"' in block


def test_the_ratchet_is_on_by_default_and_has_an_escape_hatch():
    import importlib

    crawler = importlib.import_module("aimarket_hub.crawler")
    assert crawler._pq_ratchet_enabled() is True, "must be enforced when unset"
    for off in ("0", "false", "no", "off", "OFF"):
        os.environ["AIMARKET_PQ_RATCHET"] = off
        try:
            assert crawler._pq_ratchet_enabled() is False, off
        finally:
            os.environ.pop("AIMARKET_PQ_RATCHET", None)
    os.environ["AIMARKET_PQ_RATCHET"] = "1"
    try:
        assert crawler._pq_ratchet_enabled() is True
    finally:
        os.environ.pop("AIMARKET_PQ_RATCHET", None)


def test_a_newcomer_is_untouched_by_the_ratchet():
    """The reason this is per-peer and not a global `require`: joining still costs nothing."""
    src = CRAWLER.read_text(encoding="utf-8")
    block = src[src.index("if prior_pq_key and advertised_pq_key != prior_pq_key:"):]
    block = block[:block.index("elif advertised_pq_key and not prior_pq_key:")]
    # Every rejection path is guarded by `prior_pq_key`, i.e. by there being a pin at all.
    assert block.startswith("if prior_pq_key and")


# ── the way back out: a pinned PQ key must not be a one-way door ─────────────────────────────


def test_a_pq_mismatch_gets_its_own_status_and_reason(tmp_path):
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(str(tmp_path / "hub.db"))
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED", pq_public_key="PQ1"))

    assert db.record_peer_pq_mismatch("https://p.test", pinned_pq_key="PQ1",
                                      advertised_pq_key="PQ2")
    row = db.get_peer("https://p.test")
    # NOT `key_mismatch`: the classical pin is intact, and an operator told "key changed" would
    # look for the wrong rotation and re-pin the wrong key.
    assert row.status == "pq_key_mismatch"
    assert "post-quantum key changed" in row.pin_reject_reason
    assert row.advertised_pq_public_key == "PQ2"
    assert row.pq_public_key == "PQ1", "the pin must stay fail-closed"

    db.record_peer_pq_mismatch("https://p.test", pinned_pq_key="PQ1", advertised_pq_key="")
    row = db.get_peer("https://p.test")
    assert "withdrawn" in row.pin_reject_reason, "a withdrawal reads differently from a rotation"


def test_repin_can_rotate_the_pq_key_alone(tmp_path):
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(str(tmp_path / "hub.db"))
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED", pq_public_key="PQ1"))
    db.record_peer_pq_mismatch("https://p.test", pinned_pq_key="PQ1", advertised_pq_key="PQ2")

    out = db.repin_peer_public_key("https://p.test", pq_public_key="PQ2")
    assert out["rotated"] == ["ml-dsa-65"], "the classical key was not touched"
    row = db.get_peer("https://p.test")
    assert row.pq_public_key == "PQ2"
    assert row.public_key == "ED", "rotating PQ must not disturb the Ed25519 pin"
    assert row.status == "active" and row.pin_reject_reason == ""
    assert row.advertised_pq_public_key == "", "the recorded incident is cleared with the pin"


def test_repin_requires_at_least_one_key(tmp_path):
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(str(tmp_path / "hub.db"))
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED"))
    with pytest.raises(ValueError, match="public_key or pq_public_key"):
        db.repin_peer_public_key("https://p.test")


def test_repin_pq_has_optimistic_concurrency(tmp_path):
    """Two operators re-pinning at once, or one working from a stale desk, must not both win."""
    from aimarket_hub.database import HubDatabase

    db = HubDatabase(str(tmp_path / "hub.db"))
    db.upsert_peer(Peer(url="https://p.test", name="p", public_key="ED", pq_public_key="PQ1"))
    with pytest.raises(ValueError, match="previous_pq_public_key does not match"):
        db.repin_peer_public_key("https://p.test", pq_public_key="PQ3",
                                 previous_pq_public_key="WRONG")
    assert db.get_peer("https://p.test").pq_public_key == "PQ1"
    out = db.repin_peer_public_key("https://p.test", pq_public_key="PQ3",
                                   previous_pq_public_key="PQ1")
    assert out["previous_pq_public_key"] == "PQ1"


def test_the_new_status_survives_the_trust_refresh(tmp_path):
    """A status missing from the preserve-list is silently rewritten to 'active' on refresh —
    which is how a real key_mismatch peer sat in production for five days."""
    src = DATABASE.read_text(encoding="utf-8")
    assert '"key_mismatch", "pq_key_mismatch"' in src


def test_the_endpoint_accepts_a_pq_only_repin():
    api = (Path(__file__).resolve().parents[1] / "aimarket_hub" / "hub_routes" / "federation.py").read_text()
    block = api[api.index('@router.post("/federation/peers/repin")'):]
    block = block[:block.index("crawl_stats = None")]
    assert "pq_public_key" in block and "previous_pq_public_key" in block
    assert "public_key or pq_public_key is required" in block
    assert "if not public_key and not pq_public_key:" in block


def test_both_verification_call_sites_receive_the_pin():
    """One un-threaded call site is a path where the PQ key is still self-asserted."""
    src = CRAWLER.read_text(encoding="utf-8")
    assert src.count("verify_manifest_signature(manifest, pinned_key, pinned_pq_key)") == 2
    assert "verify_manifest_signature(manifest, pinned_key)" not in src


# ── and the property the whole thing exists for ──────────────────────────────────────────────


@pqc_only
def test_a_pinned_peer_pq_key_refuses_a_substituted_one(tmp_path):
    """The attack the pin defeats, end to end through `verify_manifest_signature`."""
    from dilithium_py.ml_dsa import ML_DSA_65

    signer = Signer(key_path=tmp_path / "hub_key")
    manifest = {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z",
                "protocol_version": "v2", "tools": [{"name": "t"}]}
    signed = dict(manifest)
    signed["signature"] = signer.sign_manifest(manifest)
    canonical = signer.manifest_canonical(signed)

    real_pk, real_sk = ML_DSA_65.keygen()
    signed["signature"]["pq_algorithm"] = "ml-dsa-65"
    signed["signature"]["pq_public_key"] = base64.b64encode(real_pk).decode()
    signed["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(real_sk, canonical.encode())).decode()
    pin = signed["signature"]["pq_public_key"]

    assert signer.verify_manifest_signature(signed, signer.public_key_b64, pin)

    forged = json.loads(json.dumps(signed))
    fake_pk, fake_sk = ML_DSA_65.keygen()
    forged["signature"]["pq_public_key"] = base64.b64encode(fake_pk).decode()
    forged["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(fake_sk, canonical.encode())).decode()

    # Unpinned it passes — the PQ signature is valid for the key it names. That is the gap.
    assert signer.verify_manifest_signature(forged, signer.public_key_b64) is True
    # Pinned it is refused.
    assert signer.verify_manifest_signature(forged, signer.public_key_b64, pin) is False


@pqc_only
def test_an_empty_pin_still_verifies_a_hybrid_manifest(tmp_path):
    """Migration state: peers with no pin yet must keep working, or phase 2 de-federates them."""
    from dilithium_py.ml_dsa import ML_DSA_65

    signer = Signer(key_path=tmp_path / "hub_key")
    manifest = {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z",
                "protocol_version": "v2", "tools": [{"name": "t"}]}
    signed = dict(manifest)
    signed["signature"] = signer.sign_manifest(manifest)
    canonical = signer.manifest_canonical(signed)
    pk, sk = ML_DSA_65.keygen()
    signed["signature"]["pq_public_key"] = base64.b64encode(pk).decode()
    signed["signature"]["pq_value"] = base64.b64encode(
        ML_DSA_65.sign(sk, canonical.encode())).decode()

    assert signer.verify_manifest_signature(signed, signer.public_key_b64, "") is True
