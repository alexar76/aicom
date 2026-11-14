"""The catalogs a pip-installed GAIA or ATLAS reads must be the repository's.

`aimarket-atlas` ships atlas/atlas/_config/*.yaml (setuptools takes package data only from inside the package);
`aimarket-gaia-gateway` ships gaia/config/*.yaml through hatch force-include. Before 2026-11-08 neither shipped them,
so `import atlas.main` failed from any PyPI install. Sync: ./scripts/sync_physical_sensor_catalogs.sh
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ("om_mesh_cities.yaml", "sc_mesh_cities.yaml", "extra_sensors.yaml")


@pytest.mark.parametrize("name", CATALOGS)
def test_atlas_packaged_copy_equals_the_canonical_catalog(name: str) -> None:
    canonical_path = ROOT / "gaia" / "config" / name
    if not canonical_path.is_file():
        pytest.skip(f"gaia/config/{name} absent (factory trimmed tree)")
    canonical = canonical_path.read_bytes()
    assert (ROOT / "atlas" / "atlas" / "_config" / name).read_bytes() == canonical, (
        f"atlas/atlas/_config/{name} out of sync — run ./scripts/sync_physical_sensor_catalogs.sh"
    )


def test_gaia_wheel_force_includes_every_catalog() -> None:
    gaia_proj = ROOT / "gaia" / "pyproject.toml"
    if not gaia_proj.is_file():
        pytest.skip("gaia/pyproject.toml absent (factory trimmed tree)")
    project = tomllib.loads(gaia_proj.read_text(encoding="utf-8"))
    hatch = project["tool"]["hatch"]["build"]["targets"]
    forced = hatch["wheel"]["force-include"]
    sdist = hatch["sdist"]["include"]
    for name in CATALOGS:
        assert forced.get(f"config/{name}") == f"gaia/_config/{name}"
        assert f"/config/{name}" in sdist, "a wheel built from the sdist needs the file too"


def test_atlas_package_data_covers_the_packaged_copies() -> None:
    project = tomllib.loads((ROOT / "atlas" / "pyproject.toml").read_text(encoding="utf-8"))
    assert "_config/*.yaml" in project["tool"]["setuptools"]["package-data"]["atlas"]
