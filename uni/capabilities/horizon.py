"""HORIZON — geodesy and sensor telemetry.

The bubble's counterpart to a sensor network: distances on a sphere, geometry on the ground,
and the small set of transforms every telemetry pipeline needs before a reading means
anything. Earth is modelled as a sphere of mean radius 6 371 008.8 m (IUGG); that is stated
in the outputs, because a caller doing survey work needs the ellipsoid, not this.
"""
from __future__ import annotations

import math
from typing import Any

from uni.capabilities import (
    Capability, Catalogue, InvalidInput, choice, integer, number, numbers, rounded, text,
)

OBJ = {"type": "object"}
EARTH_RADIUS_M = 6_371_008.8
POINT_SCHEMA = {
    "type": "object", "required": ["lat", "lon"],
    "properties": {"lat": {"type": "number", "minimum": -90, "maximum": 90},
                   "lon": {"type": "number", "minimum": -180, "maximum": 180}},
}
_GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def _point(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, dict):
        raise InvalidInput(f"{label} must be an object with lat and lon")
    lat, lon = value.get("lat"), value.get("lon")
    for name, v in (("lat", lat), ("lon", lon)):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InvalidInput(f"{label}.{name} must be a number")
    lat, lon = float(lat), float(lon)
    if not -90 <= lat <= 90:
        raise InvalidInput(f"{label}.lat must be between -90 and 90")
    if not -180 <= lon <= 180:
        raise InvalidInput(f"{label}.lon must be between -180 and 180")
    return lat, lon


def _points(p: dict[str, Any], key: str = "points", *, minimum: int = 1) -> list[tuple[float, float]]:
    raw = p.get(key)
    if not isinstance(raw, list):
        raise InvalidInput(f"{key} must be an array of {{lat, lon}} objects")
    if len(raw) < minimum:
        raise InvalidInput(f"{key} needs at least {minimum} point(s)")
    if len(raw) > 20_000:
        raise InvalidInput(f"{key} is limited to 20000 points")
    return [_point(v, f"{key}[{i}]") for i, v in enumerate(raw)]


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def distance(p: dict[str, Any]) -> Any:
    a = _point(p.get("from"), "from")
    b = _point(p.get("to"), "to")
    metres = _haversine(a, b)
    return {"metres": rounded(metres, 3), "kilometres": rounded(metres / 1000, 6),
            "miles": rounded(metres / 1609.344, 6),
            "nautical_miles": rounded(metres / 1852.0, 6),
            "model": "haversine on a sphere of radius 6371008.8 m (IUGG mean)"}


def bearing(p: dict[str, Any]) -> Any:
    lat1, lon1 = (math.radians(v) for v in _point(p.get("from"), "from"))
    lat2, lon2 = (math.radians(v) for v in _point(p.get("to"), "to"))
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    initial = (math.degrees(math.atan2(y, x)) + 360) % 360
    back = (initial + 180) % 360
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return {"initial_bearing_deg": rounded(initial, 4),
            "back_bearing_deg": rounded(back, 4),
            "compass": points[int((initial + 11.25) % 360 // 22.5)]}


def destination(p: dict[str, Any]) -> Any:
    """Where you arrive following a constant initial bearing for a given distance."""
    lat1, lon1 = (math.radians(v) for v in _point(p.get("from"), "from"))
    brg = math.radians(number(p, "bearing_deg", minimum=-360, maximum=360))
    dist = number(p, "distance_m", minimum=0) / EARTH_RADIUS_M
    lat2 = math.asin(math.sin(lat1) * math.cos(dist) + math.cos(lat1) * math.sin(dist) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(dist) * math.cos(lat1),
                             math.cos(dist) - math.sin(lat1) * math.sin(lat2))
    return {"lat": rounded(math.degrees(lat2), 8),
            "lon": rounded((math.degrees(lon2) + 540) % 360 - 180, 8)}


def bounding_box(p: dict[str, Any]) -> Any:
    pts = _points(p, minimum=1)
    lats = [a for a, _ in pts]
    lons = [b for _, b in pts]
    # Deliberately not antimeridian-aware, and it says so: silently "fixing" a box that
    # crosses 180 degrees is how a wrong bounding box becomes invisible.
    crosses = max(lons) - min(lons) > 180
    return {"south": rounded(min(lats), 8), "north": rounded(max(lats), 8),
            "west": rounded(min(lons), 8), "east": rounded(max(lons), 8),
            "width_m": rounded(_haversine((min(lats), min(lons)), (min(lats), max(lons))), 2),
            "height_m": rounded(_haversine((min(lats), min(lons)), (max(lats), min(lons))), 2),
            "points": len(pts),
            "may_cross_antimeridian": crosses,
            "note": "planar min/max on lon — not antimeridian-aware" if crosses else None}


def centroid(p: dict[str, Any]) -> Any:
    """Averaged in 3-D and projected back, so points either side of the antimeridian do not
    average to a point on the far side of the planet."""
    pts = _points(p, minimum=1)
    x = y = z = 0.0
    for lat, lon in pts:
        rlat, rlon = math.radians(lat), math.radians(lon)
        x += math.cos(rlat) * math.cos(rlon)
        y += math.cos(rlat) * math.sin(rlon)
        z += math.sin(rlat)
    n = len(pts)
    x, y, z = x / n, y / n, z / n
    hyp = math.sqrt(x * x + y * y)
    if hyp < 1e-12 and abs(z) < 1e-12:
        raise InvalidInput("points are antipodally balanced — the centroid is undefined")
    return {"lat": rounded(math.degrees(math.atan2(z, hyp)), 8),
            "lon": rounded(math.degrees(math.atan2(y, x)), 8),
            "points": n, "method": "3-D vector mean projected back to the sphere"}


def point_in_polygon(p: dict[str, Any]) -> Any:
    """Ray casting in lat/lon. Fine at the scale a sensor network cares about; not a
    spherical-geometry containment test, and the output says so."""
    pt = _point(p.get("point"), "point")
    poly = _points(p, "polygon", minimum=3)
    lat, lon = pt
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        lat_i, lon_i = poly[i]
        lat_j, lon_j = poly[j]
        if (lon_i > lon) != (lon_j > lon):
            crossing_lat = lat_i + (lon - lon_i) / (lon_j - lon_i) * (lat_j - lat_i)
            if lat < crossing_lat:
                inside = not inside
        j = i
    edge = min(_haversine(pt, v) for v in poly)
    return {"inside": inside, "vertices": len(poly),
            "nearest_vertex_m": rounded(edge, 2),
            "model": "planar ray casting on lat/lon"}


def nearest(p: dict[str, Any]) -> Any:
    origin = _point(p.get("from"), "from")
    candidates = p.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise InvalidInput("candidates must be a non-empty array")
    if len(candidates) > 20_000:
        raise InvalidInput("candidates is limited to 20000 entries")
    k = integer(p, "k", 1, minimum=1, maximum=min(1000, len(candidates)))
    scored = []
    for i, c in enumerate(candidates):
        pt = _point(c, f"candidates[{i}]")
        scored.append({"index": i, "id": c.get("id"), "lat": pt[0], "lon": pt[1],
                       "distance_m": rounded(_haversine(origin, pt), 2)})
    scored.sort(key=lambda d: (d["distance_m"], d["index"]))
    return {"nearest": scored[:k], "considered": len(scored)}


def geohash_encode(p: dict[str, Any]) -> Any:
    lat, lon = _point(p.get("point"), "point")
    precision = integer(p, "precision", 9, minimum=1, maximum=12)
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = [], 0, 0, True
    while len(out) < precision:
        if even:
            mid = sum(lon_range) / 2
            if lon > mid:
                ch = (ch << 1) | 1
                lon_range[0] = mid
            else:
                ch <<= 1
                lon_range[1] = mid
        else:
            mid = sum(lat_range) / 2
            if lat > mid:
                ch = (ch << 1) | 1
                lat_range[0] = mid
            else:
                ch <<= 1
                lat_range[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_GEOHASH_ALPHABET[ch])
            bit, ch = 0, 0
    return {"geohash": "".join(out), "precision": precision,
            "cell_height_m": rounded((lat_range[1] - lat_range[0]) * 111_320, 2),
            "cell_width_m": rounded((lon_range[1] - lon_range[0]) * 111_320
                                    * math.cos(math.radians(lat)), 2)}


def geohash_decode(p: dict[str, Any]) -> Any:
    code = text(p, "geohash", maximum=12).lower()
    if not code or any(c not in _GEOHASH_ALPHABET for c in code):
        raise InvalidInput("geohash must use the base-32 geohash alphabet")
    lat_range, lon_range = [-90.0, 90.0], [-180.0, 180.0]
    even = True
    for ch in code:
        idx = _GEOHASH_ALPHABET.index(ch)
        for shift in (4, 3, 2, 1, 0):
            bit = (idx >> shift) & 1
            target = lon_range if even else lat_range
            mid = sum(target) / 2
            target[0 if bit else 1] = mid
            even = not even
    return {"lat": rounded(sum(lat_range) / 2, 8), "lon": rounded(sum(lon_range) / 2, 8),
            "bounds": {"south": rounded(lat_range[0], 8), "north": rounded(lat_range[1], 8),
                       "west": rounded(lon_range[0], 8), "east": rounded(lon_range[1], 8)}}


def path_length(p: dict[str, Any]) -> Any:
    pts = _points(p, minimum=2)
    legs = [_haversine(a, b) for a, b in zip(pts, pts[1:])]
    total = sum(legs)
    return {"total_m": rounded(total, 2), "total_km": rounded(total / 1000, 6),
            "legs": [rounded(l, 2) for l in legs],
            "longest_leg_m": rounded(max(legs), 2),
            "straight_line_m": rounded(_haversine(pts[0], pts[-1]), 2),
            "sinuosity": rounded(total / _haversine(pts[0], pts[-1]))
            if _haversine(pts[0], pts[-1]) > 0 else None}


def simplify(p: dict[str, Any]) -> Any:
    """Ramer-Douglas-Peucker with the tolerance given in metres."""
    pts = _points(p, minimum=2)
    tolerance = number(p, "tolerance_m", 10.0, minimum=0.0)

    def perpendicular(pt, start, end) -> float:
        if start == end:
            return _haversine(pt, start)
        # Local flat-earth projection is accurate well past the scale where a tolerance in
        # metres is meaningful, and avoids a great-circle cross-track term for every point.
        scale = math.cos(math.radians(start[0]))
        px, py = (pt[1] - start[1]) * scale, pt[0] - start[0]
        ex, ey = (end[1] - start[1]) * scale, end[0] - start[0]
        norm = ex * ex + ey * ey
        t = max(0.0, min(1.0, (px * ex + py * ey) / norm)) if norm else 0.0
        dx, dy = px - t * ex, py - t * ey
        return math.hypot(dx, dy) * math.pi / 180 * EARTH_RADIUS_M

    def rdp(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(points) < 3:
            return points
        worst, index = 0.0, 0
        for i in range(1, len(points) - 1):
            d = perpendicular(points[i], points[0], points[-1])
            if d > worst:
                worst, index = d, i
        if worst <= tolerance:
            return [points[0], points[-1]]
        return rdp(points[:index + 1])[:-1] + rdp(points[index:])

    kept = rdp(pts)
    return {"simplified": [{"lat": rounded(a, 8), "lon": rounded(b, 8)} for a, b in kept],
            "from_points": len(pts), "to_points": len(kept),
            "tolerance_m": tolerance,
            "reduction": rounded(1 - len(kept) / len(pts))}


def window_aggregate(p: dict[str, Any]) -> Any:
    """Tumbling-window aggregation of timestamped readings — the first thing any telemetry
    pipeline does, and the step where an off-by-one bucket goes unnoticed for months."""
    raw = p.get("readings")
    if not isinstance(raw, list) or not raw:
        raise InvalidInput("readings must be a non-empty array of {t, value}")
    if len(raw) > 100_000:
        raise InvalidInput("readings is limited to 100000 entries")
    window = number(p, "window_s", 60.0, minimum=1e-6)
    how = choice(p, "how", ("mean", "sum", "min", "max", "count", "last"), "mean")
    points = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise InvalidInput(f"readings[{i}] must be an object")
        t, v = r.get("t"), r.get("value")
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            raise InvalidInput(f"readings[{i}].t must be a number (epoch seconds)")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InvalidInput(f"readings[{i}].value must be a number")
        points.append((float(t), float(v)))
    points.sort()
    origin = points[0][0]
    buckets: dict[int, list[float]] = {}
    for t, v in points:
        buckets.setdefault(int((t - origin) // window), []).append(v)
    fns = {"mean": lambda b: sum(b) / len(b), "sum": sum, "min": min, "max": max,
           "count": len, "last": lambda b: b[-1]}
    return {"window_s": window, "how": how, "buckets": [
        {"start_t": rounded(origin + k * window, 6), "n": len(v),
         "value": rounded(float(fns[how](v)))}
        for k, v in sorted(buckets.items())
    ]}


def threshold_alerts(p: dict[str, Any]) -> Any:
    """Threshold crossings with hysteresis and a minimum duration — the two things that turn
    a noisy sensor into an alert storm when they are missing."""
    xs = numbers(p, "series", minimum=1)
    high = number(p, "high")
    clear = number(p, "clear", high, minimum=None)
    min_samples = integer(p, "min_samples", 1, minimum=1, maximum=len(xs))
    if clear > high:
        raise InvalidInput("clear must not be above high — hysteresis works downward")
    alerts, active, run, start = [], False, 0, 0
    for i, x in enumerate(xs):
        if not active:
            if x >= high:
                run += 1
                if run == 1:
                    start = i
                if run >= min_samples:
                    active, run = True, 0
                    alerts.append({"start_index": start, "end_index": None,
                                   "peak": rounded(x)})
            else:
                run = 0
        else:
            alerts[-1]["peak"] = rounded(max(alerts[-1]["peak"], x))
            if x <= clear:
                alerts[-1]["end_index"] = i
                active = False
    return {"alerts": alerts, "count": len(alerts), "currently_alerting": active,
            "high": high, "clear": clear, "min_samples": min_samples}


def debounce(p: dict[str, Any]) -> Any:
    """Suppress state flapping: a change is only accepted after it holds for N samples."""
    raw = p.get("states")
    if not isinstance(raw, list) or not raw:
        raise InvalidInput("states must be a non-empty array")
    if len(raw) > 100_000:
        raise InvalidInput("states is limited to 100000 entries")
    hold = integer(p, "hold", 2, minimum=1, maximum=len(raw))
    stable = raw[0]
    out, candidate, run, transitions = [], stable, 0, []
    for i, s in enumerate(raw):
        if s == stable:
            run, candidate = 0, stable
        elif s == candidate:
            run += 1
            if run >= hold:
                transitions.append({"index": i, "from": stable, "to": candidate})
                stable, run = candidate, 0
        else:
            candidate, run = s, 1
        out.append(stable)
    return {"debounced": out, "transitions": transitions,
            "suppressed": sum(1 for a, b in zip(raw, out) if a != b), "hold": hold}


def calibrate(p: dict[str, Any]) -> Any:
    """Two-point linear calibration: map raw sensor counts onto engineering units."""
    raw_low = number(p, "raw_low")
    raw_high = number(p, "raw_high")
    ref_low = number(p, "ref_low")
    ref_high = number(p, "ref_high")
    if raw_low == raw_high:
        raise InvalidInput("raw_low and raw_high must differ")
    gain = (ref_high - ref_low) / (raw_high - raw_low)
    offset = ref_low - gain * raw_low
    readings = numbers(p, "readings", minimum=0) if isinstance(p.get("readings"), list) else []
    return {"gain": rounded(gain), "offset": rounded(offset),
            "formula": "value = gain * raw + offset",
            "calibrated": [rounded(gain * r + offset) for r in readings]}


def dewpoint(p: dict[str, Any]) -> Any:
    """Magnus-Tetens dew point, plus absolute humidity. Constants are the WMO set for water
    over the -45..60 C range; outside it the result is refused rather than extrapolated."""
    temp_c = number(p, "temperature_c", minimum=-80, maximum=80)
    rh = number(p, "relative_humidity_pct", minimum=0.1, maximum=100)
    if not -45 <= temp_c <= 60:
        raise InvalidInput("the Magnus coefficients used here are valid from -45 to 60 C")
    a, b = 17.62, 243.12
    gamma = math.log(rh / 100) + (a * temp_c) / (b + temp_c)
    dew = (b * gamma) / (a - gamma)
    svp = 6.112 * math.exp((a * temp_c) / (b + temp_c))
    vp = svp * rh / 100
    absolute = 216.679 * vp / (temp_c + 273.15)
    return {"dew_point_c": rounded(dew, 3),
            "saturation_vapour_pressure_hpa": rounded(svp, 4),
            "vapour_pressure_hpa": rounded(vp, 4),
            "absolute_humidity_g_m3": rounded(absolute, 4),
            "model": "Magnus-Tetens, WMO coefficients a=17.62 b=243.12"}


def heat_index(p: dict[str, Any]) -> Any:
    """NOAA Rothfusz heat index with the two published adjustments, in C."""
    temp_c = number(p, "temperature_c", minimum=-80, maximum=80)
    rh = number(p, "relative_humidity_pct", minimum=0, maximum=100)
    t = temp_c * 9 / 5 + 32
    if t < 80:
        # Below 80 F Rothfusz is not valid; NOAA uses the simple form there.
        hi = 0.5 * (t + 61.0 + ((t - 68.0) * 1.2) + (rh * 0.094))
        adjusted = "simple form (below 80 F)"
    else:
        hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh
              - 0.00683783 * t * t - 0.05481717 * rh * rh + 0.00122874 * t * t * rh
              + 0.00085282 * t * rh * rh - 0.00000199 * t * t * rh * rh)
        adjusted = "Rothfusz"
        if rh < 13 and 80 <= t <= 112:
            hi -= ((13 - rh) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
            adjusted = "Rothfusz with low-humidity adjustment"
        elif rh > 85 and 80 <= t <= 87:
            hi += ((rh - 85) / 10) * ((87 - t) / 5)
            adjusted = "Rothfusz with high-humidity adjustment"
    hi_c = (hi - 32) * 5 / 9
    if hi_c >= 54:
        risk = "extreme danger"
    elif hi_c >= 41:
        risk = "danger"
    elif hi_c >= 32:
        risk = "extreme caution"
    elif hi_c >= 27:
        risk = "caution"
    else:
        risk = "none"
    return {"heat_index_c": rounded(hi_c, 2), "heat_index_f": rounded(hi, 2),
            "risk": risk, "model": adjusted}


CATALOGUE = Catalogue(
    product_id="horizon",
    name="HORIZON Geo & Telemetry",
    description="Geodesy, spatial queries and the transforms a sensor stream needs before it means anything",
    capabilities=[
        Capability("geo.distance@v1", "Great-circle distance between two points in metres, kilometres, miles and nautical miles",
                   {"type": "object", "required": ["from", "to"], "properties": {"from": POINT_SCHEMA, "to": POINT_SCHEMA}},
                   OBJ, 0.001, 20, distance, {"from": {"lat": 51.5, "lon": -0.12}, "to": {"lat": 48.85, "lon": 2.35}}),
        Capability("geo.bearing@v1", "Initial and back bearing between two points with the compass point",
                   {"type": "object", "required": ["from", "to"], "properties": {"from": POINT_SCHEMA, "to": POINT_SCHEMA}},
                   OBJ, 0.001, 20, bearing, {"from": {"lat": 51.5, "lon": -0.12}, "to": {"lat": 48.85, "lon": 2.35}}),
        Capability("geo.destination@v1", "The point reached from an origin on a given bearing and distance",
                   {"type": "object", "required": ["from", "bearing_deg", "distance_m"], "properties": {"from": POINT_SCHEMA, "bearing_deg": {"type": "number"}, "distance_m": {"type": "number"}}},
                   OBJ, 0.002, 25, destination, {"from": {"lat": 51.5, "lon": -0.12}, "bearing_deg": 90, "distance_m": 10000}),
        Capability("geo.bounding-box@v1", "Bounding box of a point set with its ground dimensions, flagging antimeridian risk",
                   {"type": "object", "required": ["points"], "properties": {"points": {"type": "array", "items": POINT_SCHEMA}}},
                   OBJ, 0.002, 30, bounding_box, {"points": [{"lat": 51.5, "lon": -0.12}, {"lat": 48.85, "lon": 2.35}]}),
        Capability("geo.centroid@v1", "Spherical centroid via 3-D vector mean, correct across the antimeridian",
                   {"type": "object", "required": ["points"], "properties": {"points": {"type": "array", "items": POINT_SCHEMA}}},
                   OBJ, 0.003, 35, centroid, {"points": [{"lat": 10, "lon": 179}, {"lat": 10, "lon": -179}]}),
        Capability("geo.point-in-polygon@v1", "Ray-casting containment test with the distance to the nearest vertex",
                   {"type": "object", "required": ["point", "polygon"], "properties": {"point": POINT_SCHEMA, "polygon": {"type": "array", "items": POINT_SCHEMA}}},
                   OBJ, 0.004, 45, point_in_polygon,
                   {"point": {"lat": 1, "lon": 1}, "polygon": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 2}, {"lat": 2, "lon": 2}, {"lat": 2, "lon": 0}]}),
        Capability("geo.nearest@v1", "The k nearest candidates to a point, by great-circle distance",
                   {"type": "object", "required": ["from", "candidates"], "properties": {"from": POINT_SCHEMA, "candidates": {"type": "array"}, "k": {"type": "integer"}}},
                   OBJ, 0.005, 55, nearest,
                   {"from": {"lat": 51.5, "lon": -0.12}, "candidates": [{"id": "a", "lat": 51.6, "lon": -0.1}, {"id": "b", "lat": 48.85, "lon": 2.35}], "k": 1}),
        Capability("geo.geohash-encode@v1", "Geohash for a point at a chosen precision, with the cell's ground size",
                   {"type": "object", "required": ["point"], "properties": {"point": POINT_SCHEMA, "precision": {"type": "integer", "minimum": 1, "maximum": 12}}},
                   OBJ, 0.002, 25, geohash_encode, {"point": {"lat": 51.5, "lon": -0.12}, "precision": 7}),
        Capability("geo.geohash-decode@v1", "Centre point and bounds of a geohash cell",
                   {"type": "object", "required": ["geohash"], "properties": {"geohash": {"type": "string"}}},
                   OBJ, 0.002, 25, geohash_decode, {"geohash": "gcpuuz9"}),
        Capability("geo.path-length@v1", "Total and per-leg length of a track, with straight-line distance and sinuosity",
                   {"type": "object", "required": ["points"], "properties": {"points": {"type": "array", "items": POINT_SCHEMA}}},
                   OBJ, 0.004, 45, path_length, {"points": [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 1, "lon": 1}]}),
        Capability("geo.simplify@v1", "Ramer-Douglas-Peucker track simplification with the tolerance in metres",
                   {"type": "object", "required": ["points"], "properties": {"points": {"type": "array", "items": POINT_SCHEMA}, "tolerance_m": {"type": "number"}}},
                   OBJ, 0.008, 90, simplify,
                   {"points": [{"lat": 0, "lon": 0}, {"lat": 0.0001, "lon": 0.5}, {"lat": 0, "lon": 1}], "tolerance_m": 100}),
        Capability("sensor.window-aggregate@v1", "Tumbling-window aggregation of timestamped readings",
                   {"type": "object", "required": ["readings"], "properties": {"readings": {"type": "array"}, "window_s": {"type": "number"}, "how": {"enum": ["mean", "sum", "min", "max", "count", "last"]}}},
                   OBJ, 0.006, 70, window_aggregate,
                   {"readings": [{"t": 0, "value": 1}, {"t": 30, "value": 3}, {"t": 90, "value": 5}], "window_s": 60}),
        Capability("sensor.threshold-alerts@v1", "Threshold crossings with hysteresis and a minimum duration, so noise is not an alert storm",
                   {"type": "object", "required": ["series", "high"], "properties": {"series": {"type": "array", "items": {"type": "number"}}, "high": {"type": "number"}, "clear": {"type": "number"}, "min_samples": {"type": "integer"}}},
                   OBJ, 0.005, 60, threshold_alerts, {"series": [1, 9, 9, 1, 1], "high": 5, "clear": 2, "min_samples": 2}),
        Capability("sensor.debounce@v1", "Suppress state flapping by requiring a change to hold for N samples",
                   {"type": "object", "required": ["states"], "properties": {"states": {"type": "array"}, "hold": {"type": "integer"}}},
                   OBJ, 0.004, 50, debounce, {"states": ["off", "on", "off", "on", "on", "on"], "hold": 2}),
        Capability("sensor.calibrate@v1", "Two-point linear calibration from raw counts to engineering units",
                   {"type": "object", "required": ["raw_low", "raw_high", "ref_low", "ref_high"], "properties": {"raw_low": {"type": "number"}, "raw_high": {"type": "number"}, "ref_low": {"type": "number"}, "ref_high": {"type": "number"}, "readings": {"type": "array", "items": {"type": "number"}}}},
                   OBJ, 0.003, 35, calibrate, {"raw_low": 100, "raw_high": 900, "ref_low": 0, "ref_high": 100, "readings": [500]}),
        Capability("sensor.dewpoint@v1", "Dew point, vapour pressure and absolute humidity from temperature and relative humidity",
                   {"type": "object", "required": ["temperature_c", "relative_humidity_pct"], "properties": {"temperature_c": {"type": "number"}, "relative_humidity_pct": {"type": "number"}}},
                   OBJ, 0.003, 30, dewpoint, {"temperature_c": 22.5, "relative_humidity_pct": 61}),
        Capability("sensor.heat-index@v1", "NOAA heat index in Celsius with the published low- and high-humidity adjustments",
                   {"type": "object", "required": ["temperature_c", "relative_humidity_pct"], "properties": {"temperature_c": {"type": "number"}, "relative_humidity_pct": {"type": "number"}}},
                   OBJ, 0.003, 30, heat_index, {"temperature_c": 33, "relative_humidity_pct": 70}),
    ],
)
