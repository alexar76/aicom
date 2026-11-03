"""Source and wheel installs must resolve the same authored UI assets."""
from pathlib import Path

import pytest

from aimarket_hub import ui_assets


def test_source_assets_preferred(tmp_path):
    for name in ui_assets.UI_FILES:
        (tmp_path / name).write_text("authored")
        assert ui_assets.ui_asset_path(name, tmp_path) == str(tmp_path / name)


def test_wheel_fallback_is_inside_the_package(monkeypatch, tmp_path):
    package = tmp_path / "aimarket_hub"
    monkeypatch.setattr(ui_assets, "__file__", str(package / "ui_assets.py"))
    for name in ui_assets.UI_FILES:
        assert ui_assets.ui_asset_path(name) == str(package / "static" / "ui" / name)


@pytest.mark.parametrize("name", ["../.env", "/etc/passwd", "unknown.html"])
def test_only_named_public_assets_are_resolved(name):
    with pytest.raises(ValueError):
        ui_assets.ui_asset_path(name)
