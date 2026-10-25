"""Durable quote-key creation, backup safety and multi-worker publication."""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from web.backend.services.checkout_quote import seal_quote


@pytest.mark.parametrize("body", [
    "invalid", "", "[]", "null", '{"quote": null}',
    '{"quote": {"quote_seal": "existing-seal"}}', '{"quote": {"quote_version": 1}}',
])
def test_unknown_or_sealed_history_cannot_get_a_replacement_key(tmp_path, body):
    state = tmp_path / "pending.json"
    state.write_text(body)
    with pytest.raises(RuntimeError):
        seal_quote({"payment_id": "new"}, state)
    assert not (tmp_path / "checkout_quote.key").exists()


@pytest.mark.parametrize("pending", [{}, {"legacy": {"payment_id": "legacy"}}])
def test_unsigned_legacy_quotes_allow_initial_key_creation(tmp_path, pending):
    state = tmp_path / "pending.json"
    state.write_text(json.dumps(pending))
    assert len(seal_quote({"payment_id": "new"}, state)) == 64


def test_parallel_key_publication_keeps_one_complete_private_key(tmp_path):
    state = tmp_path / "pending.json"
    quote = {"payment_id": "same", "amount": 5}
    with ThreadPoolExecutor(max_workers=8) as pool:
        signatures = list(pool.map(lambda _: seal_quote(quote, state), range(24)))
    assert len(set(signatures)) == 1
    key = tmp_path / "checkout_quote.key"
    assert len(key.read_bytes()) == 32
    assert key.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".checkout-key-*"))


def test_failed_publication_removes_partial_key(tmp_path, monkeypatch):
    def fail(*_):
        raise OSError("synthetic link failure")

    monkeypatch.setattr(os, "link", fail)
    with pytest.raises(OSError):
        seal_quote({"payment_id": "new"}, tmp_path / "pending.json")
    assert list(tmp_path.iterdir()) == []
