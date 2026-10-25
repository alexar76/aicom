"""Admin users store invariants."""

from __future__ import annotations

import pytest

from web.backend.services import admin_users_store as store


def test_cannot_delete_super_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "USERS_PATH", tmp_path / "admin_users.json")
    row = store.create_user(
        username="admin",
        password_hash="hash",
        role="super_admin",
    )
    with pytest.raises(ValueError, match="super_admin"):
        store.delete_user(str(row["id"]))


def test_can_delete_non_super_admin(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "USERS_PATH", tmp_path / "admin_users.json")
    sa = store.create_user(username="boss", password_hash="h1", role="super_admin")
    op = store.create_user(username="operator1", password_hash="h2", role="operator")
    store.delete_user(str(op["id"]))
    assert store.get_user_by_id(str(op["id"])) is None
    assert store.get_user_by_id(str(sa["id"])) is not None


def test_concurrent_password_reset_and_disable_are_both_retained(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time

    monkeypatch.setattr(store, "USERS_PATH", tmp_path / "admin_users.json")
    row = store.create_user(username="operator", password_hash="old-hash", role="operator")
    save = store._save_raw

    def slow_disk(data):
        time.sleep(0.02)
        save(data)

    monkeypatch.setattr(store, "_save_raw", slow_disk)
    start = threading.Barrier(2)

    def change(fields):
        start.wait(timeout=5)
        store.update_user(row["id"], **fields)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(change, fields) for fields in ({"enabled": False}, {"password_hash": "new-hash"})]
        for result in results:
            result.result(timeout=5)
    current = store.get_user_by_id(row["id"])
    assert current["enabled"] is False
    assert current["password_hash"] == "new-hash"
    assert current["session_version"] != row["session_version"]
