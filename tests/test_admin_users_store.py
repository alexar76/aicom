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
