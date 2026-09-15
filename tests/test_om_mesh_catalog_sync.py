"""GAIA and ATLAS Open-Meteo mesh catalogs must stay identical."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAIA_YAML = ROOT / "gaia" / "config" / "om_mesh_cities.yaml"
ATLAS_YAML = ROOT / "atlas" / "config" / "om_mesh_cities.yaml"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_om_mesh_cities_yaml_in_sync() -> None:
    assert GAIA_YAML.is_file(), f"missing canonical {GAIA_YAML}"
    assert ATLAS_YAML.is_file(), f"missing mirror {ATLAS_YAML}"
    assert GAIA_YAML.read_bytes() == ATLAS_YAML.read_bytes(), (
        "om_mesh_cities.yaml out of sync — run ./scripts/sync_om_mesh_catalog.sh"
    )


def test_om_mesh_loaders_agree_on_slugs() -> None:
    gaia_mesh = _load_module(
        "om_mesh_gaia_under_test",
        ROOT / "gaia" / "gaia" / "devices" / "om_mesh.py",
    )
    atlas_mesh = _load_module(
        "om_mesh_atlas_under_test",
        ROOT / "atlas" / "atlas" / "om_mesh.py",
    )
    gaia_slugs = [c["slug"] for c in gaia_mesh.OM_MESH_CITIES]
    atlas_slugs = [c["slug"] for c in atlas_mesh.OM_MESH_CITIES]
    assert gaia_slugs == atlas_slugs
    assert len(gaia_slugs) >= 1
    assert set(gaia_mesh.atlas_catalog_entries()) == set(atlas_mesh.atlas_catalog_entries())
    targets = atlas_mesh.place_targets()
    assert set(targets) == set(gaia_slugs)
