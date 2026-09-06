#!/usr/bin/env python3
"""Refresh checked-in P4 station registries from official upstream directories.

The generated modules are duplicated deliberately: GAIA and ATLAS are deployed
as separate images and neither package may import runtime data from the other.
Run from the monorepo root::

    python3 scripts/update_p4_networks.py
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RADNET_GEOJSON = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/ArcGIS/rest/services/"
    "EPA_Radiation_Air_Monitors/FeatureServer/0/query?where=1%3D1&"
    "outFields=name%2Ccity%2Cstate%2CState_Abbr%2Curl&returnGeometry=true&"
    "outSR=4326&f=geojson"
)
RADNET_DOWNLOADS = "https://www.epa.gov/radnet/radnet-csv-file-downloads"
NDBC_ACTIVE = "https://www.ndbc.noaa.gov/activestations.xml"
USER_AGENT = "AIMarket-registry-refresh/1.0 (+https://modelmarket.dev)"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def normalized_name(value: str) -> str:
    value = urllib.parse.unquote(value).upper().replace("FORT", "FT")
    return re.sub(r"[^A-Z0-9]", "", value)


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "station"


def radnet_rows() -> list[dict[str, Any]]:
    directory = json.loads(fetch(RADNET_GEOJSON))
    downloads = fetch(RADNET_DOWNLOADS).decode("utf-8", errors="replace")
    urls = re.findall(
        r'href="([^"]*cdx-radnet-rest/api/rest/csv/[0-9]{4}/fixed/[^"]+)"',
        downloads,
        flags=re.I,
    )
    paths: dict[tuple[str, str], str] = {}
    for raw_url in urls:
        url = html.unescape(raw_url)
        path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
        try:
            tail = path.split("/fixed/", 1)[1]
            state, city_path = tail.split("/", 1)
        except (IndexError, ValueError):
            continue
        paths[(state.upper(), normalized_name(city_path))] = city_path

    # The location directory uses public-facing city labels while four download
    # paths retain an older operational name. Keep the official endpoint name.
    aliases = {
        ("CA", "SANBERNARDINO"): "SAN BERNARDINO COUNTY",
        ("NM", "NAVAJODAM"): "NAVAJO LAKE",
        ("NY", "LOCKPORT"): "BUFFALO",
        ("NY", "NEWYORK"): "NYC EML",
    }
    rows: list[dict[str, Any]] = []
    for feature in directory.get("features") or []:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates") or []
        if len(coords) < 2:
            continue
        state = str(props.get("State_Abbr") or "").upper()
        city = str(props.get("city") or props.get("name") or "").strip()
        key = (state, normalized_name(city))
        city_path = paths.get(key) or aliases.get(key)
        if not state or not city or not city_path:
            raise RuntimeError(f"RadNet location has no CSV endpoint match: {state} {city}")
        if state == "AL" and city == "Birmingham":
            device_id = "radnet-birmingham"
        elif state == "DC" and city == "Washington":
            device_id = "radnet-washington"
        elif state == "CA" and city == "Los Angeles":
            device_id = "radnet-los-angeles"
        else:
            device_id = f"radnet-{state.lower()}-{slug(city)}"
        rows.append(
            {
                "device_id": device_id,
                "state": state,
                "city_path": city_path.upper(),
                "name": city,
                "latitude": round(float(coords[1]), 6),
                "longitude": round(float(coords[0]), 6),
            }
        )
    rows.sort(key=lambda row: (str(row["state"]), str(row["name"])))
    if len(rows) != 140 or len({row["device_id"] for row in rows}) != 140:
        raise RuntimeError(f"expected 140 unique RadNet monitors, got {len(rows)}")
    return rows


def dart_rows() -> list[dict[str, Any]]:
    root = ET.fromstring(fetch(NDBC_ACTIVE))
    rows: list[dict[str, Any]] = []
    for station in root.findall("station"):
        if str(station.attrib.get("dart") or "").lower() != "y":
            continue
        station_id = str(station.attrib.get("id") or "").strip()
        if not re.fullmatch(r"[0-9]{5}", station_id):
            continue
        rows.append(
            {
                "device_id": "noaa-dart-01" if station_id == "46407" else f"dart-{station_id}",
                "station_id": station_id,
                "name": str(station.attrib.get("name") or station_id).strip(),
                "owner": str(station.attrib.get("owner") or "NDBC").strip(),
                "latitude": round(float(station.attrib["lat"]), 6),
                "longitude": round(float(station.attrib["lon"]), 6),
            }
        )
    rows.sort(key=lambda row: str(row["station_id"]))
    if not rows or len({row["station_id"] for row in rows}) != len(rows):
        raise RuntimeError("NDBC returned an empty or duplicate DART registry")
    return rows


def module_text(radnet: list[dict[str, Any]], dart: list[dict[str, Any]]) -> str:
    return (
        '"""Generated official P4 station registries; do not edit by hand.\n\n'
        "Refresh with ``python3 scripts/update_p4_networks.py`` from the monorepo root.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        f"RADNET_DIRECTORY_URL = {RADNET_GEOJSON!r}\n"
        f"DART_DIRECTORY_URL = {NDBC_ACTIVE!r}\n\n"
        f"RADNET_STATIONS = {tuple(radnet)!r}\n\n"
        f"DART_STATIONS = {tuple(dart)!r}\n\n"
        '__all__ = ["RADNET_DIRECTORY_URL", "DART_DIRECTORY_URL", '
        '"RADNET_STATIONS", "DART_STATIONS"]\n'
    )


def main() -> None:
    radnet = radnet_rows()
    dart = dart_rows()
    body = module_text(radnet, dart)
    targets = (
        ROOT / "gaia/gaia/devices/p4_networks.py",
        ROOT / "atlas/atlas/p4_networks.py",
    )
    for target in targets:
        target.write_text(body, encoding="utf-8")
    print(f"wrote {len(radnet)} RadNet and {len(dart)} DART stations to {len(targets)} modules")


if __name__ == "__main__":
    main()
