"""Tests for SQLite-backed security persistence (H-3 / H-5)."""

from __future__ import annotations

import time

import pytest

from core.persistent_security_store import (
    PersistentSecurityStore,
    get_persistent_security_store,
    reset_persistent_security_store_for_tests,
)
from web.backend.core.security import SecurityManager


@pytest.fixture(autouse=True)
def _reset_store_singleton():
    reset_persistent_security_store_for_tests()
    yield
    reset_persistent_security_store_for_tests()


@pytest.fixture
def store(tmp_path, monkeypatch):
    db = tmp_path / "security_store.db"
    monkeypatch.setenv("AIFACTORY_SECURITY_STORE_DB", str(db))
    reset_persistent_security_store_for_tests()
    return PersistentSecurityStore(str(db))


def test_rate_limit_window_count_and_clear(store):
    key = "203.0.113.1"
    store.record_attempt(key, ts=time.time() - 100)
    store.record_attempt(key, ts=time.time() - 10)
    store.record_attempt(key)

    assert store.recent_attempt_count(key, window_seconds=60) == 2
    store.clear_attempts(key)
    assert store.recent_attempt_count(key, window_seconds=60) == 0


def test_rate_limit_persists_across_instances(tmp_path):
    db = tmp_path / "security_store.db"
    s1 = PersistentSecurityStore(str(db))
    s1.record_attempt("10.0.0.1")
    s1.record_attempt("10.0.0.1")
    s1.close()

    s2 = PersistentSecurityStore(str(db))
    assert s2.recent_attempt_count("10.0.0.1", window_seconds=900) == 2


def test_nonce_first_use_then_replay(store):
    assert store.claim_nonce("nonce-abc", ttl_seconds=300) is True
    assert store.claim_nonce("nonce-abc", ttl_seconds=300) is False


def test_nonce_expires_and_can_be_reissued(store):
    past = time.time() - 10
    with store.conn:
        store.conn.execute(
            "INSERT OR REPLACE INTO used_nonces (nonce, expires_at) VALUES (?, ?)",
            ("expired-nonce", past),
        )
    assert store.claim_nonce("expired-nonce", ttl_seconds=60) is True


def test_nonce_survives_restart(tmp_path):
    db = tmp_path / "security_store.db"
    s1 = PersistentSecurityStore(str(db))
    assert s1.claim_nonce("restart-nonce", ttl_seconds=300) is True
    s1.close()

    s2 = PersistentSecurityStore(str(db))
    assert s2.claim_nonce("restart-nonce", ttl_seconds=300) is False


def test_singleton_cache(tmp_path, monkeypatch):
    db = tmp_path / "security_store.db"
    monkeypatch.setenv("AIFACTORY_SECURITY_STORE_DB", str(db))
    a = get_persistent_security_store()
    b = get_persistent_security_store()
    assert a is not None and a is b


def test_store_unavailable_returns_none(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SECURITY_STORE_DB", "/proc/not-writable/security.db")
    reset_persistent_security_store_for_tests()
    assert get_persistent_security_store() is None


def test_security_manager_uses_persistent_store(tmp_path, monkeypatch):
    db = tmp_path / "security_store.db"
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AIFACTORY_SECURITY_STORE_DB", str(db))
    reset_persistent_security_store_for_tests()

    sm = SecurityManager(audit_log_path=str(audit))
    assert sm._rl_store is not None

    ip = "198.51.100.7"
    for _ in range(5):
        sm.record_login_attempt(ip, success=False)
    assert sm.check_login_attempts(ip) is False

    sm2 = SecurityManager(audit_log_path=str(audit))
    assert sm2.check_login_attempts(ip) is False

    sm2.record_login_attempt(ip, success=True)
    assert sm2.check_login_attempts(ip) is True
