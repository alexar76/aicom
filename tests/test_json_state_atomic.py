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


def test_existing_mode_is_kept(tmp_path: Path):
    import os

    target = tmp_path / "secret.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o600)
    write_json_atomic(target, {"k": "v"})
    assert oct(target.stat().st_mode)[-3:] == "600"


@pytest.mark.parametrize("existing", [False, True])
def test_secret_temp_is_private_before_the_content_is_flushed(tmp_path, monkeypatch, existing):
    import os
    import stat

    target = tmp_path / "secret.json"
    if existing:
        target.write_text("{}")
        target.chmod(0o600)
    original_fsync = os.fsync
    observed = []

    def check_permissions(fd):
        observed.append(stat.S_IMODE(os.fstat(fd).st_mode))
        original_fsync(fd)

    monkeypatch.setattr(os, "fsync", check_permissions)
    write_json_atomic(target, {"secret": "test-only"}, **({} if existing else {"mode": 0o600}))
    assert observed == [0o600]


def test_replace_failure_preserves_original_and_removes_temp(tmp_path, monkeypatch):
    import os

    target = tmp_path / "state.json"
    target.write_text('{"original": true}')

    def full_disk(*_):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", full_disk)
    with pytest.raises(OSError, match="disk full"):
        write_json_atomic(target, {"replacement": True})
    assert json.loads(target.read_text()) == {"original": True}
    assert list(tmp_path.iterdir()) == [target]


def test_writes_through_a_symlink(tmp_path: Path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    write_json_atomic(link, {"via": "link"})
    assert link.is_symlink()
    assert json.loads(real.read_text(encoding="utf-8")) == {"via": "link"}


@pytest.mark.parametrize("mode", [None, 0o600])
def test_bind_mounted_file_falls_back_to_an_in_place_write(tmp_path: Path, monkeypatch, mode):
    import errno
    import os

    target = tmp_path / "mounted.json"
    target.write_text("{}", encoding="utf-8")

    def busy(*a, **k):
        raise OSError(errno.EBUSY, "Device or resource busy")

    monkeypatch.setattr(os, "replace", busy)
    write_json_atomic(target, {"ok": True}, mode=mode)
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert list(tmp_path.iterdir()) == [target]
    if mode is not None:
        assert target.stat().st_mode & 0o777 == mode


def test_concurrent_threads_do_not_share_a_temp_file(tmp_path: Path):
    import threading

    target = tmp_path / "s.json"
    errors: list[BaseException] = []

    def write(n: int) -> None:
        try:
            for _ in range(20):
                write_json_atomic(target, {"n": n, "pad": "x" * 2000})
        except BaseException as exc:  # pragma: no cover - the failure being guarded
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert json.loads(target.read_text(encoding="utf-8"))["pad"] == "x" * 2000
    assert list(tmp_path.iterdir()) == [target]
