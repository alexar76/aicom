"""Receipts issued before anchoring was on reach HISTOR with their own issue time, or not at all.

Real hub + provenance plugin, real HISTOR app over its HTTP route (test_receipt_anchoring's
harness). The backfill only queues; the hub's own outbox sends.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("aimarket_provenance")
pytest.importorskip("histor.receipts")

from tests._mandate_kit import hub
from tests.test_receipt_anchoring import _histor_app, _issue_one, _outbox, _route_httpx_to


def _plugin_parts(client):
    plugin, outbox = _outbox(client)
    return plugin, outbox, plugin._storage


def _forget_outbox(storage):
    storage._conn.execute("DELETE FROM provenance_anchor_outbox")
    storage._conn.commit()


def test_old_receipts_are_queued_with_their_own_time_and_anchored(monkeypatch, tmp_path, capsys):
    from aimarket_hub.signing import Signer
    from aimarket_provenance import backfill
    from aimarket_provenance.receipt import ProvenanceReceipt

    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        plugin, outbox, storage = _plugin_parts(client)
        first, issuer = _issue_one(client, db)
        second, _ = _issue_one(client, db)
        # Ours, valid, and issued two days ago: what a backfill is for.
        two_days_ago = datetime.now(UTC).replace(microsecond=0) - timedelta(days=2)
        older = ProvenanceReceipt.create(model_id="m", provider_hub="here", input_payload={"a": 1},
                                         output_payload={"b": 2}, signer=plugin._signer, now=two_days_ago)
        storage.store(older)
        # Issued by someone else's key, stored here: the anchor would say "this hub issued it".
        stranger = ProvenanceReceipt.create(model_id="m", provider_hub="elsewhere", input_payload={"a": 1},
                                            output_payload={"b": 2}, signer=Signer(key_path=str(tmp_path / "other.key")))
        storage.store(stranger)
        # Ours by issuer, but altered after signing.
        doc = json.loads(json.dumps(storage.get_by_receipt_id(first["receipt_id"]).to_dict()))
        doc["id"] = doc["id"] + "-altered"
        doc["credentialSubject"] = {**doc.get("credentialSubject", {}), "altered": True}
        storage.store(ProvenanceReceipt.from_dict(doc))
        _forget_outbox(storage)   # as on a hub that turned anchoring on after issuing them

        args = ["--db", str(storage.db_path), "--key", str(plugin._signer.key_path)]
        assert backfill.main([*args, "--dry-run"]) == 0
        dry = json.loads(capsys.readouterr().out)
        assert (dry["seen"], dry["queued"], dry["foreign_issuer"], dry["invalid"]) == (5, 3, 1, 1), dry
        assert outbox.status(first["digest_sri"]) is None            # a dry run queues nothing

        assert backfill.main(args) == 0
        assert json.loads(capsys.readouterr().out)["queued"] == 3
        assert backfill.main(args) == 0
        again = json.loads(capsys.readouterr().out)
        assert again["queued"] == 0 and again["already_queued"] == 3  # idempotent

        services, histor_client = _histor_app(tmp_path, monkeypatch, issuer)
        _route_httpx_to(monkeypatch, histor_client)
        assert outbox.flush_once()["anchored"] == 3
        for issued in (first, second, {"digest_sri": older.digest_sri, "receipt_id": older.receipt_id}):
            proof = histor_client.get("/api/v1/receipts/proof", params={"digest": issued["digest_sri"]}).json()
            stored = storage.get_by_receipt_id(issued["receipt_id"])
            # the issue time HISTOR holds is the receipt's own, not the backfill's
            want = datetime.fromisoformat(stored.timestamp).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            assert proof["anchor"]["issuedAt"] == want
        assert want == two_days_ago.strftime("%Y-%m-%dT%H:%M:%SZ")      # the last one checked
        services.close()


def test_a_receipt_past_histors_window_is_left_alone(monkeypatch, tmp_path):
    """HISTOR's 30-day window is what stops backdating. A receipt older than that is not
    anchored under a false, fresher time — it is counted and skipped."""
    from aimarket_provenance import backfill

    with hub(monkeypatch, tmp_path, AIMARKET_HISTOR_URL="https://histor.test") as (client, db):
        plugin, outbox, storage = _plugin_parts(client)
        _issue_one(client, db)
        _forget_outbox(storage)
        key = plugin._signer.public_key_b64
        later = datetime.now(UTC) + timedelta(days=30)
        counts = backfill.backfill(backfill.stored_receipts(storage), outbox, issuer_public_key_b64=key, now=later)
        assert counts["too_old"] == 1 and counts["queued"] == 0
        # inside the window but within the margin of its edge: it could expire before it is sent
        edge = datetime.now(UTC) + timedelta(days=29, hours=23, minutes=30)
        counts = backfill.backfill(backfill.stored_receipts(storage), outbox, issuer_public_key_b64=key, now=edge)
        assert counts["too_old"] == 1
        earlier = datetime.now(UTC) - timedelta(hours=1)
        counts = backfill.backfill(backfill.stored_receipts(storage), outbox, issuer_public_key_b64=key, now=earlier)
        assert counts["future"] == 1 and counts["queued"] == 0


def test_a_hub_that_does_not_anchor_publishes_nothing(monkeypatch, tmp_path, capsys):
    """The UNI bubble runs without AIMARKET_HISTOR_URL so its virtual money never reaches the
    public log. The backfill honours the same switch."""
    from aimarket_provenance import backfill

    monkeypatch.delenv("AIMARKET_HISTOR_URL", raising=False)
    assert backfill.main(["--db", str(tmp_path / "provenance.db"), "--key", str(tmp_path / "k")]) == 2
    assert "does not anchor" in capsys.readouterr().err
    assert not (tmp_path / "provenance.db").exists()
