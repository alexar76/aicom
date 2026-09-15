"""State files must survive a kill mid-write.

`data/state/pending_payments.json` was found at 0 bytes on the factory host on 2026-09-11:
`open(..., "w")` truncates before it writes, so anything that stops the process in between
destroys the state. `data/config/admin.json` had the same five-times-repeated pattern, and
losing it takes the admin's TOTP/WebAuthn registration with it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.json_state import write_json_atomic


def test_writes_and_replaces(tmp_path: Path):
    target = tmp_path / "state" / "pending_payments.json"
    write_json_atomic(target, {"a": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}
    write_json_atomic(target, {"b": 2})
    assert json.loads(target.read_text(encoding="utf-8")) == {"b": 2}
    assert list(target.parent.iterdir()) == [target], "no temp file left behind"


def test_previous_content_survives_a_failed_write(tmp_path: Path, monkeypatch):
    target = tmp_path / "s.json"
    write_json_atomic(target, {"keep": True})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        write_json_atomic(target, {"boom": Unserialisable()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": True}
    assert list(tmp_path.iterdir()) == [target], "the temp file is cleaned up on failure"


def test_mode_is_applied(tmp_path: Path):
    target = tmp_path / "secret.json"
    write_json_atomic(target, {"k": "v"}, mode=0o600)
    assert oct(target.stat().st_mode)[-3:] == "600"


def test_unicode_is_not_escaped(tmp_path: Path):
    target = tmp_path / "u.json"
    write_json_atomic(target, {"имя": "значение"})
    assert "имя" in target.read_text(encoding="utf-8")


def test_no_truncating_writes_left_in_the_two_repaired_files():
    root = Path(__file__).resolve().parents[1]
    for rel, name in (
        ("web/backend/api/payment.py", "PENDING_PAYMENTS_FILE"),
        ("web/backend/api/admin/auth.py", "ADMIN_JSON"),
    ):
        src = (root / rel).read_text(encoding="utf-8")
        assert f'open({name}, "w"' not in src, f"{rel} still truncates {name} before writing"
        assert "write_json_atomic(" in src
