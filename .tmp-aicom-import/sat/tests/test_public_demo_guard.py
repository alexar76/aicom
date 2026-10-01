"""Public demo guard."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from web.backend.services import public_demo_guard as pdg


def test_public_demo_off_by_default(monkeypatch):
    monkeypatch.delenv("AIFACTORY_DEMO_READONLY", raising=False)
    assert pdg.is_public_demo() is False
    pdg.require_not_public_demo("test")  # no raise


def test_public_demo_blocks(monkeypatch):
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    assert pdg.is_public_demo() is True
    assert pdg.allows_passwordless_admin_login() is True
    st = pdg.public_demo_status()
    assert st["blocks_factory_backup"] is True
    assert st["allows_passwordless_admin_login"] is True
    with pytest.raises(HTTPException) as exc:
        pdg.require_not_public_demo("factory restore")
    assert exc.value.status_code == 403
