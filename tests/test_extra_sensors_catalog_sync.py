"""extra_sensors.yaml must stay in sync between GAIA and ATLAS."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAIA_YAML = ROOT / "gaia" / "config" / "extra_sensors.yaml"
ATLAS_YAML = ROOT / "atlas" / "config" / "extra_sensors.yaml"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_extra_sensors_yaml_in_sync() -> None:
    import pytest
    if not GAIA_YAML.is_file() or not ATLAS_YAML.is_file():
        pytest.skip("gaia/atlas extra_sensors.yaml absent (factory trimmed tree)")
    assert GAIA_YAML.read_bytes() == ATLAS_YAML.read_bytes(), (
        "extra_sensors.yaml out of sync — run ./scripts/sync_physical_sensor_catalogs.sh"
    )


def test_extra_sensors_loaders_agree() -> None:
    import pytest
    gaia_py = ROOT / "gaia" / "gaia" / "devices" / "extra_sensors.py"
    if not gaia_py.is_file():
        pytest.skip("gaia extra_sensors module absent (factory trimmed tree)")
    gaia = _load_module(
        "extra_sensors_gaia_ut",
        gaia_py,
    )
    atlas = _load_module(
        "extra_sensors_atlas_ut",
        ROOT / "atlas" / "atlas" / "extra_sensors.py",
    )
    assert set(gaia.KIND_META) == set(atlas.KIND_META)
    assert set(gaia.atlas_catalog_entries()) == set(atlas.atlas_catalog_entries())


def test_au_safecast_anchors_use_archive_mode() -> None:
    import pytest
    import yaml

    if not GAIA_YAML.is_file():
        pytest.skip("gaia extra_sensors.yaml absent (factory trimmed tree)")
    rows = yaml.safe_load(GAIA_YAML.read_text())["sensors"]
    by_id = {r["device_id"]: r for r in rows if r.get("kind") == "safecast"}
    for device_id in ("safecast-melbourne", "safecast-adelaide"):
        params = by_id[device_id].get("params") or {}
        assert params.get("max_age_days") == 0
        assert int(params.get("distance_m") or 0) >= 500_000
