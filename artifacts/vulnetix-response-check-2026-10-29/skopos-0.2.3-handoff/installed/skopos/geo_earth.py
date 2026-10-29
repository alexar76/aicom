"""Textured 3D Earth sphere and country borders for Plotly globe charts."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

_ASSETS = Path(__file__).resolve().parent / "assets"
_EARTH_TEXTURE = _ASSETS / "earth.jpg"
_COUNTRIES_GEOJSON = _ASSETS / "ne_110m_countries.geojson"


def latlon_to_xyz(lat: float, lon: float, radius: float = 1.0) -> tuple[float, float, float]:
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    cos_lat = math.cos(lat_r)
    return (
        radius * cos_lat * math.cos(lon_r),
        radius * cos_lat * math.sin(lon_r),
        radius * math.sin(lat_r),
    )


def _sphere_grid(res_u: int, res_v: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    u = np.linspace(0, 2 * np.pi, res_u)
    v = np.linspace(0, np.pi, res_v)
    uu, vv = np.meshgrid(u, v)
    x = np.cos(uu) * np.sin(vv)
    y = np.sin(uu) * np.sin(vv)
    z = np.cos(vv)
    return x, y, z


@lru_cache(maxsize=1)
def _earth_rgb_array() -> np.ndarray:
    if not _EARTH_TEXTURE.is_file():
        raise FileNotFoundError(f"Earth texture missing: {_EARTH_TEXTURE}")
    return np.asarray(Image.open(_EARTH_TEXTURE).convert("RGB"))


def _sample_texture(lat: np.ndarray, lon: np.ndarray, img: np.ndarray) -> np.ndarray:
    h, w, _ = img.shape
    px = np.clip(((lon + 180.0) / 360.0 * (w - 1)).astype(int), 0, w - 1)
    py = np.clip(((90.0 - lat) / 180.0 * (h - 1)).astype(int), 0, h - 1)
    return img[py, px]


def _grid_triangles(res_u: int, res_v: int) -> tuple[list[int], list[int], list[int]]:
    i_idx: list[int] = []
    j_idx: list[int] = []
    k_idx: list[int] = []
    for row in range(res_v - 1):
        for col in range(res_u - 1):
            a = row * res_u + col
            b = a + 1
            c = a + res_u
            d = c + 1
            i_idx.extend([a, c])
            j_idx.extend([c, d])
            k_idx.extend([b, b])
    return i_idx, j_idx, k_idx


def build_textured_earth_mesh(
    *,
    res_u: int = 120,
    res_v: int = 60,
) -> dict:
    """Return Mesh3d kwargs: x, y, z, i, j, k, vertexcolor."""
    img = _earth_rgb_array()
    x, y, z = _sphere_grid(res_u, res_v)
    lat = np.degrees(np.arcsin(np.clip(z, -1.0, 1.0)))
    lon = np.degrees(np.arctan2(y, x))
    rgb = _sample_texture(lat, lon, img)

    vertexcolor = [
        f"rgb({int(r)},{int(g)},{int(b)})"
        for r, g, b in rgb.reshape(-1, 3)
    ]
    i_idx, j_idx, k_idx = _grid_triangles(res_u, res_v)

    return dict(
        x=x.flatten().tolist(),
        y=y.flatten().tolist(),
        z=z.flatten().tolist(),
        i=i_idx,
        j=j_idx,
        k=k_idx,
        vertexcolor=vertexcolor,
    )


def _iter_rings(geometry: dict):
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return
    if gtype == "Polygon":
        for ring in coords:
            yield ring
    elif gtype == "MultiPolygon":
        for poly in coords:
            for ring in poly:
                yield ring
    elif gtype == "LineString":
        yield coords
    elif gtype == "MultiLineString":
        for line in coords:
            yield line


@lru_cache(maxsize=1)
def build_country_border_lines(*, radius: float = 1.003) -> tuple[list[float | None], ...]:
    """Lon/lat rings from Natural Earth → 3D line lists with None gaps."""
    if not _COUNTRIES_GEOJSON.is_file():
        return [], [], []

    data = json.loads(_COUNTRIES_GEOJSON.read_text(encoding="utf-8"))
    xs: list[float | None] = []
    ys: list[float | None] = []
    zs: list[float | None] = []

    for feature in data.get("features", []):
        geom = feature.get("geometry") or {}
        for ring in _iter_rings(geom):
            if len(ring) < 2:
                continue
            for lon, lat in ring:
                x, y, z = latlon_to_xyz(float(lat), float(lon), radius)
                xs.append(x)
                ys.append(y)
                zs.append(z)
            xs.append(None)
            ys.append(None)
            zs.append(None)

    if xs and xs[-1] is None:
        xs.pop()
        ys.pop()
        zs.pop()

    return xs, ys, zs
