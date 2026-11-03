"""`quickstart` says how the hub will sign and which key files are its identity.

A hub without dilithium-py fails closed on every hybrid signature, so it silently indexes no
peer that signs hybrid; hybrid signing is opt-in; and once it is on, the ML-DSA key file must be
backed up with the classical key. The report is the only place a fresh operator hears all three.
"""

from __future__ import annotations

import pytest

from aimarket_hub import cli, signing


def test_a_new_hub_signs_hybrid_by_default(tmp_path, monkeypatch, capsys):
    """Since 3.15.20 a hub with no identity yet signs as every AIMarket hub does."""
    monkeypatch.delenv("AIMARKET_PQC", raising=False)
    key = tmp_path / "hub_signing_key"
    cli._signing_report(key)
    out = capsys.readouterr().out
    assert "signing hybrid" in out
    assert key.exists() and (tmp_path / "hub_signing_key_mldsa").exists()


def test_an_ed25519_only_hub_keeps_its_identity_and_is_offered_the_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AIMARKET_PQC", raising=False)
    key = tmp_path / "hub_signing_key"
    signing.Signer(key, pqc=False)          # an existing classical hub
    cli._signing_report(key)
    out = capsys.readouterr().out
    assert "Ed25519 only" in out and "keeps it" in out
    assert "export AIMARKET_PQC=1" in out
    assert f"{key}_mldsa" in out  # what will need backing up, said before it exists
    assert not (tmp_path / "hub_signing_key_mldsa").exists()


def test_an_explicit_off_is_obeyed_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIMARKET_PQC", "0")
    key = tmp_path / "hub_signing_key"
    cli._signing_report(key)
    out = capsys.readouterr().out
    assert "Ed25519 only" in out
    assert not key.exists()
    assert not (tmp_path / "hub_signing_key_mldsa").exists()


def test_without_the_library_it_says_peers_will_not_be_indexed(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AIMARKET_PQC", raising=False)
    monkeypatch.setattr(signing, "_PQ_LIB", False)
    cli._signing_report(tmp_path / "k")
    out = capsys.readouterr().out
    assert "will not index peers that sign hybrid" in out
    assert "pip install 'aimarket-hub[pqc]'" in out


def test_on_without_the_library_is_loud_not_a_crash(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIMARKET_PQC", "1")
    monkeypatch.setattr(signing, "_PQ_LIB", False)
    cli._signing_report(tmp_path / "k")
    out = capsys.readouterr().out
    assert "refuses to start" in out
    assert not (tmp_path / "k").exists()


@pytest.mark.skipif(not signing.pqc_available(), reason="needs the pqc extra")
def test_on_creates_both_keys_names_them_and_keeps_them(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIMARKET_PQC", "1")
    key = tmp_path / "hub_signing_key"
    pq_key = tmp_path / "hub_signing_key_mldsa"
    cli._signing_report(key)
    out = capsys.readouterr().out
    assert "signing hybrid" in out
    assert str(key) in out and str(pq_key) in out
    assert key.exists() and pq_key.exists()
    # The same identity `serve` will load: a second run reads the keys, it does not mint new ones.
    before = pq_key.read_text()
    cli._signing_report(key)
    assert pq_key.read_text() == before
    assert signing.Signer(key).pq_public_key_b64


def test_the_report_and_the_signer_read_one_switch(monkeypatch):
    for value, expected in (("1", True), ("on", True), ("true", True), ("0", False), ("", False)):
        monkeypatch.setenv("AIMARKET_PQC", value)
        assert signing.pqc_signing_enabled() is expected
