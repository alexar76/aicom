"""Product code-tree writability probe (data-keep owns the actual chown)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.code_tree_ownership import product_code_dir_writable, warn_if_product_code_unwritable


def test_missing_dir_is_not_a_blocker(tmp_path: Path) -> None:
    assert product_code_dir_writable("prod-x", root=tmp_path / "nope") is True


def test_writable_dir(tmp_path: Path) -> None:
    d = tmp_path / "prod-ok"
    d.mkdir()
    assert product_code_dir_writable("prod-ok", root=d) is True
    assert not (d / ".aicom_write_probe").exists()


def test_readonly_dir(tmp_path: Path) -> None:
    d = tmp_path / "prod-ro"
    d.mkdir()
    d.chmod(0o555)
    try:
        assert product_code_dir_writable("prod-ro", root=d) is False
    finally:
        d.chmod(0o755)


def test_warn_returns_false_when_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    data = tmp_path / "data"
    d = data / "code" / "prod-ro"
    d.mkdir(parents=True)
    d.chmod(0o555)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    try:
        assert warn_if_product_code_unwritable("prod-ro") is False
    finally:
        d.chmod(0o755)
    assert "not writable" in caplog.text
