"""STOICHEION — data hygiene, schemas, text and units.

The unglamorous half of any real catalogue: work out what a payload actually contains, say
how two of them differ, and convert a number into the unit the other side expected. All of it
is exact and reversible, and where a conversion is defined by a standards body the constant
is written out rather than approximated.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from uni.capabilities import (
    Capability, Catalogue, InvalidInput, choice, integer, number, rounded, text,
)

OBJ = {"type": "object"}
ANY = {}
MAX_DEPTH = 32


def _json_value(p: dict[str, Any], key: str) -> Any:
    if key not in p:
        raise InvalidInput(f"{key} is required")
    value = p[key]
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInput(f"{key} is not JSON-serialisable") from exc
    if len(encoded) > 1_000_000:
        raise InvalidInput(f"{key} is limited to 1 MB of JSON")
    return value


def _type_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def schema_infer(p: dict[str, Any]) -> Any:
    """Infer a JSON Schema from one or more samples. A field missing from any sample is
    optional; a field whose type varies becomes a union rather than the last type seen."""
    sample = _json_value(p, "sample")
    samples = sample if isinstance(sample, list) and p.get("as_samples") else [sample]

    def infer(values: list[Any], depth: int) -> dict[str, Any]:
        if depth > MAX_DEPTH:
            return {}
        kinds = sorted({_type_of(v) for v in values})
        if kinds == ["integer", "number"]:
            kinds = ["number"]
        node: dict[str, Any] = {"type": kinds[0] if len(kinds) == 1 else kinds}
        if "object" in kinds:
            objs = [v for v in values if isinstance(v, dict) and not isinstance(v, bool)]
            keys: dict[str, list[Any]] = {}
            for o in objs:
                for k, v in o.items():
                    keys.setdefault(k, []).append(v)
            node["properties"] = {k: infer(v, depth + 1) for k, v in sorted(keys.items())}
            node["required"] = sorted(k for k, v in keys.items() if len(v) == len(objs))
        if "array" in kinds:
            items = [x for v in values if isinstance(v, list) for x in v]
            node["items"] = infer(items, depth + 1) if items else {}
        return node

    return {"schema": infer(samples, 0), "samples": len(samples)}


def json_diff(p: dict[str, Any]) -> Any:
    """A structural diff by JSON Pointer: what was added, removed and changed."""
    a = _json_value(p, "a")
    b = _json_value(p, "b")
    added, removed, changed = [], [], []

    def esc(token: str) -> str:
        return token.replace("~", "~0").replace("/", "~1")

    def walk(x: Any, y: Any, path: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y)):
                sub = f"{path}/{esc(str(k))}"
                if k not in x:
                    added.append({"path": sub, "value": y[k]})
                elif k not in y:
                    removed.append({"path": sub, "value": x[k]})
                else:
                    walk(x[k], y[k], sub, depth + 1)
        elif isinstance(x, list) and isinstance(y, list):
            for i in range(max(len(x), len(y))):
                sub = f"{path}/{i}"
                if i >= len(x):
                    added.append({"path": sub, "value": y[i]})
                elif i >= len(y):
                    removed.append({"path": sub, "value": x[i]})
                else:
                    walk(x[i], y[i], sub, depth + 1)
        elif x != y or _type_of(x) != _type_of(y):
            changed.append({"path": path or "/", "from": x, "to": y})

    walk(a, b, "", 0)
    return {"added": added, "removed": removed, "changed": changed,
            "identical": not (added or removed or changed),
            "change_count": len(added) + len(removed) + len(changed)}


def canonicalise(p: dict[str, Any]) -> Any:
    """RFC 8785-style canonical JSON: sorted keys, no insignificant whitespace, plus the
    digest of the result — which is what makes two documents comparable across services."""
    value = _json_value(p, "value")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"canonical": canonical,
            "sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "bytes": len(canonical.encode())}


def flatten(p: dict[str, Any]) -> Any:
    value = _json_value(p, "value")
    sep = text(p, "separator", required=False, default=".", maximum=8) or "."
    out: dict[str, Any] = {}

    def walk(node: Any, prefix: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            out[prefix] = node
            return
        if isinstance(node, dict) and node:
            for k, v in node.items():
                walk(v, f"{prefix}{sep}{k}" if prefix else str(k), depth + 1)
        elif isinstance(node, list) and node:
            for i, v in enumerate(node):
                walk(v, f"{prefix}[{i}]", depth + 1)
        else:
            out[prefix or ""] = node

    walk(value, "", 0)
    return {"flat": out, "keys": len(out)}


def validate_shape(p: dict[str, Any]) -> Any:
    """Check a document against a minimal schema — type, required, enum, bounds. Not a full
    JSON Schema validator, and it says so rather than implying coverage it does not have."""
    value = _json_value(p, "value")
    schema = _json_value(p, "schema")
    if not isinstance(schema, dict):
        raise InvalidInput("schema must be an object")
    errors: list[str] = []

    def check(node: Any, sch: Any, path: str, depth: int) -> None:
        if depth > MAX_DEPTH or not isinstance(sch, dict):
            return
        expected = sch.get("type")
        if expected:
            kinds = expected if isinstance(expected, list) else [expected]
            actual = _type_of(node)
            ok = actual in kinds or (actual == "integer" and "number" in kinds)
            if not ok:
                errors.append(f"{path or '/'}: expected {'/'.join(kinds)}, got {actual}")
                return
        if "enum" in sch and node not in sch["enum"]:
            errors.append(f"{path or '/'}: {node!r} is not one of {sch['enum']}")
        if isinstance(node, (int, float)) and not isinstance(node, bool):
            if "minimum" in sch and node < sch["minimum"]:
                errors.append(f"{path or '/'}: {node} < minimum {sch['minimum']}")
            if "maximum" in sch and node > sch["maximum"]:
                errors.append(f"{path or '/'}: {node} > maximum {sch['maximum']}")
        if isinstance(node, dict):
            for req in sch.get("required", []) or []:
                if req not in node:
                    errors.append(f"{path}/{req}: required property is missing")
            for k, sub in (sch.get("properties") or {}).items():
                if k in node:
                    check(node[k], sub, f"{path}/{k}", depth + 1)
        if isinstance(node, list) and sch.get("items"):
            for i, item in enumerate(node):
                check(item, sch["items"], f"{path}/{i}", depth + 1)

    check(value, schema, "", 0)
    return {"valid": not errors, "errors": errors,
            "coverage": "type, required, enum, minimum, maximum — not a full JSON Schema validator"}


def deduplicate(p: dict[str, Any]) -> Any:
    items = _json_value(p, "items")
    if not isinstance(items, list):
        raise InvalidInput("items must be an array")
    if len(items) > 50_000:
        raise InvalidInput("items is limited to 50000 entries")
    key_field = p.get("key")
    seen: dict[str, int] = {}
    unique, duplicates = [], []
    for i, item in enumerate(items):
        if key_field is not None:
            if not isinstance(item, dict):
                raise InvalidInput(f"items[{i}] must be an object when `key` is given")
            fingerprint = json.dumps(item.get(key_field), sort_keys=True, ensure_ascii=False)
        else:
            fingerprint = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if fingerprint in seen:
            duplicates.append({"index": i, "first_seen": seen[fingerprint]})
        else:
            seen[fingerprint] = i
            unique.append(item)
    return {"unique": unique, "unique_count": len(unique),
            "duplicate_count": len(duplicates), "duplicates": duplicates[:500]}


def profile(p: dict[str, Any]) -> Any:
    """Column profile of an array of objects: type mix, null rate, cardinality, extremes."""
    rows = _json_value(p, "rows")
    if not isinstance(rows, list) or not rows:
        raise InvalidInput("rows must be a non-empty array of objects")
    if len(rows) > 50_000:
        raise InvalidInput("rows is limited to 50000 entries")
    columns: dict[str, list[Any]] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InvalidInput(f"rows[{i}] must be an object")
        for k, v in row.items():
            columns.setdefault(k, []).append(v)
    out = {}
    for name, values in sorted(columns.items()):
        present = [v for v in values if v is not None]
        types = Counter(_type_of(v) for v in values)
        col: dict[str, Any] = {
            "count": len(values), "present": len(present),
            "null_rate": rounded(1 - len(present) / len(rows)),
            "missing_from_rows": len(rows) - len(values),
            "types": dict(types.most_common()),
            "distinct": len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in present}),
        }
        nums = [float(v) for v in present if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums:
            col["min"] = rounded(min(nums))
            col["max"] = rounded(max(nums))
            col["mean"] = rounded(sum(nums) / len(nums))
        out[name] = col
    return {"rows": len(rows), "columns": out}


def text_metrics(p: dict[str, Any]) -> Any:
    """Counts plus Flesch reading ease. The syllable count is the standard vowel-group
    heuristic — an estimate, and labelled as one."""
    body = text(p, "text")
    words = re.findall(r"[A-Za-z0-9']+", body)
    sentences = [s for s in re.split(r"[.!?]+", body) if s.strip()]

    def syllables(word: str) -> int:
        w = word.lower()
        groups = re.findall(r"[aeiouy]+", w)
        count = len(groups)
        if w.endswith("e") and count > 1 and not w.endswith(("le", "ee")):
            count -= 1
        return max(1, count)

    syl = sum(syllables(w) for w in words) if words else 0
    ease = None
    if words and sentences:
        ease = (206.835 - 1.015 * (len(words) / len(sentences))
                - 84.6 * (syl / len(words)))
    return {
        "characters": len(body), "characters_no_spaces": len(re.sub(r"\s", "", body)),
        "words": len(words), "unique_words": len({w.lower() for w in words}),
        "sentences": len(sentences), "paragraphs": len([b for b in body.split("\n\n") if b.strip()]),
        "average_word_length": rounded(sum(len(w) for w in words) / len(words)) if words else 0.0,
        "average_sentence_words": rounded(len(words) / len(sentences)) if sentences else 0.0,
        "estimated_syllables": syl,
        "flesch_reading_ease": rounded(ease, 2) if ease is not None else None,
        "syllables_note": "vowel-group heuristic, not a dictionary lookup",
    }


def ngrams(p: dict[str, Any]) -> Any:
    body = text(p, "text")
    n = integer(p, "n", 2, minimum=1, maximum=8)
    top = integer(p, "top", 20, minimum=1, maximum=500)
    level = choice(p, "level", ("word", "character"), "word")
    units = re.findall(r"[^\W_]+", body.lower()) if level == "word" else list(body)
    if len(units) < n:
        return {"ngrams": [], "note": f"input has fewer than {n} {level}s"}
    counts = Counter(
        (" " if level == "word" else "").join(units[i:i + n])
        for i in range(len(units) - n + 1)
    )
    return {"n": n, "level": level, "total": sum(counts.values()),
            "distinct": len(counts),
            "ngrams": [{"gram": g, "count": c} for g, c in counts.most_common(top)]}


def text_normalise(p: dict[str, Any]) -> Any:
    body = text(p, "text")
    form = choice(p, "unicode_form", ("NFC", "NFD", "NFKC", "NFKD"), "NFC")
    out = unicodedata.normalize(form, body)
    if p.get("collapse_whitespace", True):
        out = re.sub(r"\s+", " ", out).strip()
    case = choice(p, "case", ("preserve", "lower", "upper", "casefold"), "preserve")
    if case == "lower":
        out = out.lower()
    elif case == "upper":
        out = out.upper()
    elif case == "casefold":
        out = out.casefold()
    if p.get("strip_accents", False):
        out = "".join(c for c in unicodedata.normalize("NFD", out)
                      if not unicodedata.combining(c))
    return {"normalised": out, "unicode_form": form, "case": case,
            "changed": out != body, "length": len(out)}


def digest(p: dict[str, Any]) -> Any:
    body = text(p, "text")
    algorithm = choice(p, "algorithm", ("sha256", "sha512", "sha3_256", "blake2b"), "sha256")
    data = body.encode()
    h = hashlib.new(algorithm, data) if algorithm != "blake2b" else hashlib.blake2b(data)
    return {"algorithm": algorithm, "hex": h.hexdigest(), "bytes_hashed": len(data)}


def deterministic_id(p: dict[str, Any]) -> Any:
    """UUIDv5 — the same name in the same namespace always yields the same id, which is what
    makes it usable as a join key between two systems that never talk."""
    name = text(p, "name", maximum=4096)
    namespace = text(p, "namespace", required=False, default="dns")
    known = {"dns": uuid.NAMESPACE_DNS, "url": uuid.NAMESPACE_URL,
             "oid": uuid.NAMESPACE_OID, "x500": uuid.NAMESPACE_X500}
    if namespace in known:
        ns = known[namespace]
    else:
        try:
            ns = uuid.UUID(namespace)
        except ValueError as exc:
            raise InvalidInput(
                "namespace must be dns, url, oid, x500 or a UUID") from exc
    return {"uuid": str(uuid.uuid5(ns, name)), "namespace": namespace, "name": name}


_UNITS: dict[str, dict[str, float]] = {
    # Every factor is exact by definition, not measured.
    "length": {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "mi": 1609.344,
               "yd": 0.9144, "ft": 0.3048, "in": 0.0254, "nmi": 1852.0},
    "mass": {"kg": 1.0, "g": 0.001, "mg": 1e-6, "t": 1000.0, "lb": 0.45359237,
             "oz": 0.028349523125, "st": 6.35029318},
    "time": {"s": 1.0, "ms": 0.001, "min": 60.0, "h": 3600.0, "d": 86400.0, "wk": 604800.0},
    "data": {"B": 1.0, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12,
             "KiB": 1024.0, "MiB": 1048576.0, "GiB": 1073741824.0, "TiB": 1099511627776.0},
    "speed": {"m/s": 1.0, "km/h": 1 / 3.6, "mph": 0.44704, "kn": 0.514444444444},
    "pressure": {"Pa": 1.0, "hPa": 100.0, "kPa": 1000.0, "bar": 100000.0,
                 "atm": 101325.0, "psi": 6894.757293168},
}


def convert_units(p: dict[str, Any]) -> Any:
    value = number(p, "value")
    frm = text(p, "from")
    to = text(p, "to")
    if frm in ("C", "F", "K") or to in ("C", "F", "K"):
        if frm not in ("C", "F", "K") or to not in ("C", "F", "K"):
            raise InvalidInput("a temperature can only be converted to another temperature")
        kelvin = {"C": value + 273.15, "F": (value - 32) * 5 / 9 + 273.15, "K": value}[frm]
        if kelvin < 0:
            raise InvalidInput("the result is below absolute zero")
        out = {"C": kelvin - 273.15, "F": (kelvin - 273.15) * 9 / 5 + 32, "K": kelvin}[to]
        return {"value": rounded(out), "from": frm, "to": to, "dimension": "temperature"}
    for dimension, table in _UNITS.items():
        if frm in table and to in table:
            return {"value": rounded(value * table[frm] / table[to]),
                    "from": frm, "to": to, "dimension": dimension}
    known = sorted({u for table in _UNITS.values() for u in table} | {"C", "F", "K"})
    raise InvalidInput(
        f"cannot convert {frm!r} to {to!r} — units must share a dimension. "
        f"Known units: {', '.join(known)}"
    )


def datetime_normalise(p: dict[str, Any]) -> Any:
    raw = text(p, "value", maximum=200)
    parsed = None
    for candidate in (raw, raw.replace("Z", "+00:00"), raw.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    if parsed is None:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d",
                    "%d %b %Y", "%d %B %Y", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        raise InvalidInput(f"could not parse {raw!r} as a date or timestamp")
    assumed_utc = parsed.tzinfo is None
    if assumed_utc:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc = parsed.astimezone(timezone.utc)
    return {
        "iso8601_utc": utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "epoch_seconds": int(utc.timestamp()),
        "date": utc.strftime("%Y-%m-%d"),
        "weekday": utc.strftime("%A"),
        "iso_week": utc.strftime("%G-W%V-%u"),
        "day_of_year": int(utc.strftime("%j")),
        "timezone_assumed_utc": assumed_utc,
    }


def datetime_difference(p: dict[str, Any]) -> Any:
    a = datetime_normalise({"value": text(p, "a", maximum=200)})
    b = datetime_normalise({"value": text(p, "b", maximum=200)})
    delta = timedelta(seconds=b["epoch_seconds"] - a["epoch_seconds"])
    total = delta.total_seconds()
    return {"seconds": int(total), "minutes": rounded(total / 60, 3),
            "hours": rounded(total / 3600, 4), "days": rounded(total / 86400, 5),
            "human": str(delta), "from": a["iso8601_utc"], "to": b["iso8601_utc"]}


def csv_profile(p: dict[str, Any]) -> Any:
    import csv as _csv
    import io

    body = text(p, "csv", maximum=2_000_000)
    delimiter = text(p, "delimiter", required=False, default=",", maximum=1) or ","
    rows = list(_csv.DictReader(io.StringIO(body), delimiter=delimiter))
    if not rows:
        raise InvalidInput("csv has no data rows")
    if len(rows) > 50_000:
        raise InvalidInput("csv is limited to 50000 data rows")
    typed: list[dict[str, Any]] = []
    for row in rows:
        out: dict[str, Any] = {}
        for k, v in row.items():
            if k is None:
                continue
            if v is None or v == "":
                out[k] = None
                continue
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
        typed.append(out)
    return profile({"rows": typed})


def text_diff(p: dict[str, Any]) -> Any:
    import difflib

    a = text(p, "a", maximum=500_000)
    b = text(p, "b", maximum=500_000)
    a_lines, b_lines = a.splitlines(), b.splitlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, lineterm="", n=integer(p, "context", 2, minimum=0, maximum=20)))
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return {"unified_diff": diff[:2000], "lines_added": added, "lines_removed": removed,
            "similarity": rounded(ratio), "identical": a == b}


CATALOGUE = Catalogue(
    product_id="stoicheion",
    name="STOICHEION Data Hygiene",
    description="Schema inference, structural diffing, profiling, text metrics and unit conversion",
    capabilities=[
        Capability("json.schema-infer@v1", "Infer a JSON Schema from one or more samples, with unions for varying types",
                   {"type": "object", "required": ["sample"], "properties": {"sample": ANY, "as_samples": {"type": "boolean"}}},
                   OBJ, 0.006, 70, schema_infer, {"sample": {"id": 1, "tags": ["a"]}}),
        Capability("json.diff@v1", "Structural diff by JSON Pointer: added, removed and changed paths",
                   {"type": "object", "required": ["a", "b"], "properties": {"a": ANY, "b": ANY}},
                   OBJ, 0.005, 60, json_diff, {"a": {"x": 1, "y": 2}, "b": {"x": 1, "y": 3, "z": 4}}),
        Capability("json.canonicalise@v1", "Canonical JSON with sorted keys plus the digest that makes documents comparable",
                   {"type": "object", "required": ["value"], "properties": {"value": ANY}},
                   OBJ, 0.002, 30, canonicalise, {"value": {"b": 2, "a": 1}}),
        Capability("json.flatten@v1", "Flatten nested objects and arrays into dotted paths",
                   {"type": "object", "required": ["value"], "properties": {"value": ANY, "separator": {"type": "string"}}},
                   OBJ, 0.003, 35, flatten, {"value": {"a": {"b": [1, 2]}}}),
        Capability("json.validate-shape@v1", "Check a document against a minimal schema, honest about what it does not cover",
                   {"type": "object", "required": ["value", "schema"], "properties": {"value": ANY, "schema": OBJ}},
                   OBJ, 0.004, 45, validate_shape,
                   {"value": {"n": 5}, "schema": {"type": "object", "required": ["n"], "properties": {"n": {"type": "integer", "maximum": 10}}}}),
        Capability("data.deduplicate@v1", "Remove duplicate records by whole value or by a key field, reporting what collided",
                   {"type": "object", "required": ["items"], "properties": {"items": {"type": "array"}, "key": {"type": "string"}}},
                   OBJ, 0.004, 50, deduplicate, {"items": [{"id": 1}, {"id": 1}, {"id": 2}], "key": "id"}),
        Capability("data.profile@v1", "Column profile of tabular records: types, null rate, cardinality and extremes",
                   {"type": "object", "required": ["rows"], "properties": {"rows": {"type": "array"}}},
                   OBJ, 0.008, 90, profile, {"rows": [{"a": 1, "b": "x"}, {"a": 3, "b": None}]}),
        Capability("text.metrics@v1", "Length, vocabulary and Flesch reading ease with the syllable model stated",
                   {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
                   OBJ, 0.003, 40, text_metrics, {"text": "The cat sat. It was warm and quiet."}),
        Capability("text.ngrams@v1", "Word or character n-gram frequencies, most common first",
                   {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}, "n": {"type": "integer"}, "top": {"type": "integer"}, "level": {"enum": ["word", "character"]}}},
                   OBJ, 0.004, 55, ngrams, {"text": "to be or not to be", "n": 2}),
        Capability("text.normalise@v1", "Unicode normalisation, whitespace collapse, case folding and accent stripping",
                   {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}, "unicode_form": {"enum": ["NFC", "NFD", "NFKC", "NFKD"]}, "case": {"enum": ["preserve", "lower", "upper", "casefold"]}, "collapse_whitespace": {"type": "boolean"}, "strip_accents": {"type": "boolean"}}},
                   OBJ, 0.002, 30, text_normalise, {"text": "  Café   au   lait  ", "strip_accents": True}),
        Capability("hash.digest@v1", "Cryptographic digest of a string in SHA-256, SHA-512, SHA3-256 or BLAKE2b",
                   {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}, "algorithm": {"enum": ["sha256", "sha512", "sha3_256", "blake2b"]}}},
                   OBJ, 0.001, 20, digest, {"text": "hello"}),
        Capability("id.deterministic@v1", "UUIDv5 for a name in a namespace — a join key two systems can derive independently",
                   {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "namespace": {"type": "string"}}},
                   OBJ, 0.001, 20, deterministic_id, {"name": "order-1234", "namespace": "url"}),
        Capability("units.convert@v1", "Exact conversion across length, mass, time, data, speed, pressure and temperature",
                   {"type": "object", "required": ["value", "from", "to"], "properties": {"value": {"type": "number"}, "from": {"type": "string"}, "to": {"type": "string"}}},
                   OBJ, 0.001, 20, convert_units, {"value": 26.2, "from": "mi", "to": "km"}),
        Capability("datetime.normalise@v1", "Parse a date or timestamp in many formats and return it as ISO 8601 UTC with derived fields",
                   {"type": "object", "required": ["value"], "properties": {"value": {"type": "string"}}},
                   OBJ, 0.002, 25, datetime_normalise, {"value": "14 Mar 2026"}),
        Capability("datetime.difference@v1", "Signed interval between two timestamps in every useful unit",
                   {"type": "object", "required": ["a", "b"], "properties": {"a": {"type": "string"}, "b": {"type": "string"}}},
                   OBJ, 0.002, 25, datetime_difference, {"a": "2026-01-01", "b": "2026-03-14T12:00:00Z"}),
        Capability("csv.profile@v1", "Parse CSV text, infer column types and profile every column",
                   {"type": "object", "required": ["csv"], "properties": {"csv": {"type": "string"}, "delimiter": {"type": "string"}}},
                   OBJ, 0.010, 110, csv_profile, {"csv": "a,b\n1,x\n3,\n"}),
        Capability("text.diff@v1", "Unified line diff with added/removed counts and a similarity ratio",
                   {"type": "object", "required": ["a", "b"], "properties": {"a": {"type": "string"}, "b": {"type": "string"}, "context": {"type": "integer"}}},
                   OBJ, 0.005, 60, text_diff, {"a": "one\ntwo\n", "b": "one\ntwo\nthree\n"}),
    ],
)
