#!/usr/bin/env python3
"""Add a sensor to GAIA + ATLAS with one command.

Writes ``gaia/config/extra_sensors.yaml``, mirrors to atlas, done.

Examples::

  # Open-Meteo weather pin
  python3 scripts/add_gaia_atlas_sensor.py \\
    --kind open-meteo-weather --device-id om-wx-seoul \\
    --lat 37.5665 --lon 126.9780 --place Seoul \\
    --alias seoul --alias сеул --alias 서울

  # Weather + air pair (two pins, one place)
  python3 scripts/add_gaia_atlas_sensor.py \\
    --kind open-meteo-pair --slug seoul --place Seoul \\
    --lat 37.5665 --lon 126.9780 --alias seoul --alias сеул

  # NWS station
  python3 scripts/add_gaia_atlas_sensor.py \\
    --kind nws --device-id nws-ksfo --station KSFO \\
    --lat 37.6196 --lon -122.3748 --place "SFO Airport"

  # SIM campus device (no upstream)
  python3 scripts/add_gaia_atlas_sensor.py \\
    --kind sim-weather --device-id ws-lab-01 \\
    --lat 46.95 --lon 7.45 --place "Lab campus"

DISCLAIMER: this only registers kinds that already exist in GAIA code.
A brand-new upstream API still needs a LiveDevice subclass (Recipe B).
See docs/add-gaia-atlas-sensor.md
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GAIA_YAML = ROOT / "gaia" / "config" / "extra_sensors.yaml"
ATLAS_YAML = ROOT / "atlas" / "config" / "extra_sensors.yaml"
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]{1,31}$")

# Must match gaia.devices.extra_sensors.KIND_META (+ open-meteo-pair macro).
KINDS = (
    "open-meteo-weather",
    "open-meteo-air",
    "open-meteo-marine",
    "open-meteo-pair",
    "nws",
    "opensensemap",
    "noaa-tide",
    "usgs-river",
    "ndbc-buoy",
    "openaq",
    "uk-grid",
    "usgs-quake",
    "firms-fire",
    "safecast",
    "cybernews-jamming",
    "eonet",
    "swpc",
    "glm",
    "nws-cap",
    "sensor-community",
    "cwop",
    "argo",
    "metno-metar",
    "usgs-geomag",
    "nhc-cyclone",
    "emsc-quake",
    "ea-flood",
    "ptwc-tsunami",
    "kystverket-ais",
    "adsb-lol",
    "sim-weather",
    "sim-air",
    "sim-energy",
)

KIND_DEFAULTS = {
    "open-meteo-weather": {"layer": "weather", "label_prefix": "Open-Meteo Weather"},
    "open-meteo-air": {"layer": "air", "label_prefix": "Open-Meteo Air"},
    "open-meteo-marine": {"layer": "marine", "label_prefix": "Open-Meteo Marine"},
    "nws": {"layer": "weather", "label_prefix": "NWS Station"},
    "opensensemap": {"layer": "air", "label_prefix": "openSenseMap"},
    "noaa-tide": {"layer": "tide", "label_prefix": "NOAA Tide"},
    "usgs-river": {"layer": "river", "label_prefix": "USGS River"},
    "ndbc-buoy": {"layer": "marine", "label_prefix": "NDBC Buoy"},
    "openaq": {"layer": "air", "label_prefix": "OpenAQ"},
    "uk-grid": {"layer": "grid", "label_prefix": "UK Carbon Intensity"},
    "usgs-quake": {"layer": "quake", "label_prefix": "USGS Earthquake"},
    "firms-fire": {"layer": "fire", "label_prefix": "NASA FIRMS Fire"},
    "safecast": {"layer": "radiation", "label_prefix": "Safecast Radiation"},
    "cybernews-jamming": {"layer": "jamming", "label_prefix": "CyberNews GNSS"},
    "eonet": {"layer": "events", "label_prefix": "NASA EONET"},
    "swpc": {"layer": "spacewx", "label_prefix": "NOAA SWPC"},
    "glm": {"layer": "lightning", "label_prefix": "GOES GLM"},
    "nws-cap": {"layer": "alerts", "label_prefix": "NWS CAP"},
    "sensor-community": {"layer": "air", "label_prefix": "Sensor.Community"},
    "cwop": {"layer": "weather", "label_prefix": "CWOP"},
    "argo": {"layer": "argo", "label_prefix": "Argo Float"},
    "metno-metar": {"layer": "weather", "label_prefix": "MET Norway METAR"},
    "usgs-geomag": {"layer": "geomag", "label_prefix": "USGS Geomag"},
    "nhc-cyclone": {"layer": "cyclone", "label_prefix": "NHC Cyclone"},
    "emsc-quake": {"layer": "quake", "label_prefix": "EMSC Earthquake"},
    "ea-flood": {"layer": "flood", "label_prefix": "EA Flood Warning"},
    "ptwc-tsunami": {"layer": "tsunami", "label_prefix": "PTWC Tsunami"},
    "kystverket-ais": {"layer": "ais", "label_prefix": "Kystverket AIS"},
    "adsb-lol": {"layer": "adsb", "label_prefix": "ADSB.lol"},
    "sim-weather": {"layer": "weather", "label_prefix": "Weather Sim"},
    "sim-air": {"layer": "air", "label_prefix": "Air Quality Sim"},
    "sim-energy": {"layer": "energy", "label_prefix": "Energy Meter Sim"},
}


def _load() -> dict:
    if not GAIA_YAML.is_file():
        return {"version": 1, "sensors": []}
    return yaml.safe_load(GAIA_YAML.read_text(encoding="utf-8")) or {"version": 1, "sensors": []}


def _existing_ids(doc: dict) -> set[str]:
    return {
        str(s.get("device_id"))
        for s in (doc.get("sensors") or [])
        if isinstance(s, dict) and s.get("device_id")
    }


def _save(doc: dict) -> None:
    GAIA_YAML.parent.mkdir(parents=True, exist_ok=True)
    ATLAS_YAML.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, default_flow_style=False)
    # Keep a short header so humans see the disclaimer in the file itself.
    header = (
        "# Extra sensors — GAIA fleet + ATLAS pins.\n"
        "# DISCLAIMER: only known kinds (existing LiveDevice/SIM classes).\n"
        "# New upstream API ⇒ write code (Recipe B). Guide: docs/add-gaia-atlas-sensor.md\n"
        "# ONE COMMAND: python3 scripts/add_gaia_atlas_sensor.py --help\n\n"
    )
    # Strip previous auto-header if re-dumping pure yaml body
    body = text if not text.lstrip().startswith("#") else text
    GAIA_YAML.write_text(header + body, encoding="utf-8")
    shutil.copy2(GAIA_YAML, ATLAS_YAML)


def _row(
    *,
    kind: str,
    device_id: str,
    lat: float,
    lon: float,
    place: str,
    label: str | None,
    aliases: list[str],
    place_id: str | None,
    params: dict,
) -> dict:
    meta = KIND_DEFAULTS[kind]
    place = place.strip()
    label = (label or f"{meta['label_prefix']} · {place or device_id}").strip()
    row: dict = {
        "device_id": device_id,
        "kind": kind,
        "enabled": True,
        "label": label,
        "place": place,
        "lat": float(lat),
        "lon": float(lon),
        "layer": meta["layer"],
        "aliases": aliases,
    }
    if place_id:
        row["place_id"] = place_id
    if params:
        row["params"] = params
    return row


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Add a sensor to GAIA + ATLAS (one command).",
        epilog=(
            "DISCLAIMER: registers only built-in kinds. "
            "Brand-new APIs need a LiveDevice subclass — docs/add-gaia-atlas-sensor.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--device-id", help="Fleet/pin id, e.g. om-wx-seoul / nws-ksfo")
    ap.add_argument("--slug", help="For open-meteo-pair → om-wx-{slug} + om-aq-{slug}")
    ap.add_argument("--lat", type=float, help="Map anchor latitude")
    ap.add_argument("--lon", type=float, help="Map anchor longitude")
    ap.add_argument("--place", default="", help="Human place name on the pin")
    ap.add_argument("--label", default="", help="Override pin label")
    ap.add_argument("--alias", action="append", default=[], help="Analyst alias (repeatable)")
    ap.add_argument("--place-id", default="", help="Group several sensors under one Analyst place")
    ap.add_argument("--station", default="", help="NWS / NOAA / NDBC station id")
    ap.add_argument("--usgs-site", default="", help="USGS NWIS site number")
    ap.add_argument("--box-id", default="", help="openSenseMap box id")
    ap.add_argument("--location-id", default="", help="OpenAQ location id")
    args = ap.parse_args()

    kind = args.kind
    aliases = [a.strip() for a in args.alias if a and a.strip()]

    # Defaults for kinds that don't need a unique map anchor
    lat = args.lat
    lon = args.lon
    if lat is None or lon is None:
        if kind == "uk-grid":
            lat, lon = 54.0, -2.0
        elif kind in (
            "usgs-quake", "firms-fire", "cybernews-jamming",
            "eonet", "glm", "nws-cap", "argo",
        ):
            lat, lon = 0.0, 0.0
        elif kind == "safecast":
            lat, lon = 37.42, 141.03
        else:
            print("error: --lat and --lon are required for this kind", file=sys.stderr)
            return 1
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        print("error: lat/lon out of range", file=sys.stderr)
        return 1

    doc = _load()
    sensors = list(doc.get("sensors") or [])
    doc["version"] = int(doc.get("version") or 1)
    existing = _existing_ids(doc)
    added: list[str] = []

    if kind == "open-meteo-pair":
        slug = (args.slug or "").strip().lower()
        if not _SLUG_RE.match(slug):
            print("error: --slug required (^[a-z][a-z0-9]{1,31}$)", file=sys.stderr)
            return 1
        place = args.place.strip() or slug.title()
        if not aliases:
            aliases = [slug, place.lower()]
        place_id = args.place_id.strip() or slug
        for suffix, k in (("wx", "open-meteo-weather"), ("aq", "open-meteo-air")):
            device_id = f"om-{suffix}-{slug}"
            if device_id in existing:
                print(f"error: device_id already exists: {device_id}", file=sys.stderr)
                return 1
            sensors.append(
                _row(
                    kind=k,
                    device_id=device_id,
                    lat=lat,
                    lon=lon,
                    place=place,
                    label=args.label or None,
                    aliases=aliases,
                    place_id=place_id,
                    params={},
                )
            )
            added.append(device_id)
            existing.add(device_id)
    else:
        device_id = (args.device_id or "").strip().lower()
        if not _ID_RE.match(device_id):
            print("error: --device-id required (^[a-z][a-z0-9_-]{1,47}$)", file=sys.stderr)
            return 1
        if device_id in existing:
            print(f"error: device_id already exists: {device_id}", file=sys.stderr)
            return 1
        params: dict = {}
        if kind == "nws":
            if not args.station:
                print("error: --station required for nws", file=sys.stderr)
                return 1
            params["station"] = args.station.strip()
        elif kind == "opensensemap":
            if not args.box_id:
                print("error: --box-id required for opensensemap", file=sys.stderr)
                return 1
            params["box_id"] = args.box_id.strip()
        elif kind == "noaa-tide":
            params["station"] = (args.station or "8518750").strip()
        elif kind == "usgs-river":
            params["usgs_site"] = (args.usgs_site or "01646500").strip()
        elif kind == "ndbc-buoy":
            params["station"] = (args.station or "44025").strip()
        elif kind == "openaq":
            params["location_id"] = (args.location_id or "2178").strip()
        place = args.place.strip() or device_id
        if not aliases:
            aliases = [place.lower(), device_id]
        sensors.append(
            _row(
                kind=kind,
                device_id=device_id,
                lat=lat,
                lon=lon,
                place=place,
                label=args.label or None,
                aliases=aliases,
                place_id=args.place_id.strip() or None,
                params=params,
            )
        )
        added.append(device_id)

    doc["sensors"] = sensors
    _save(doc)

    print("OK: added", ", ".join(added))
    print(f"  → {GAIA_YAML}")
    print(f"  → {ATLAS_YAML} (mirrored)")
    print()
    print("DISCLAIMER: only built-in kinds. New upstream API ⇒ Recipe B in docs/add-gaia-atlas-sensor.md")
    print("Next: redeploy GAIA then ATLAS (LIVE kinds need GAIA_ENABLE_LIVE=1).")
    if kind == "openaq":
        print("Note: openaq also needs GAIA_OPENAQ_API_KEY on the host.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
