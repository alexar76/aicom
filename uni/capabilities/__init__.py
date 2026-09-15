"""The bubble's capability registry.

Every capability here is a pure function of its input, computed with the standard library.
That is a hard rule, not a stylistic one: a capability inside the sealed realm may not reach
the network, may not call a model, and may not consult anything outside the bubble — and a
capability that returns a canned string would make the catalogue a stage set rather than a
market. What is sold here is genuinely computed; only the money is simulated.

Adding one: write the function, declare its schemas and price, and append it to its
catalogue's list. `uni/tests/test_capabilities.py` then exercises it automatically — every
capability must carry an example that actually runs, must be deterministic, and must reject
malformed input with `ValueError` rather than a traceback.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

#: Raised by a capability when the CALLER is at fault. The satellite maps it to 400 and does
#: not count it against the capability's success rate — a rejected input is not a failure to
#: compute, and conflating the two makes a well-behaved provider look unreliable.
InvalidInput = ValueError


@dataclass(frozen=True)
class Capability:
    capability_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    price_usd: float
    p50_latency_ms: int
    run: Callable[[dict[str, Any]], Any]
    example: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Catalogue:
    product_id: str
    name: str
    description: str
    capabilities: list[Capability]

    @property
    def by_id(self) -> dict[str, Capability]:
        return {c.capability_id: c for c in self.capabilities}


#: The bubble's satellites. Names are its own — this is a parallel world, not a copy of ours
#: — but the SHAPE mirrors the live federation: a few large catalogues, a few small ones.
CATALOGUES = ("khronos", "kyma", "psephos", "stoicheion", "diktyon", "horizon")


def load_catalogue(name: str) -> Catalogue:
    if name not in CATALOGUES:
        raise SystemExit(f"unknown catalogue {name!r} — one of {', '.join(CATALOGUES)}")
    module = importlib.import_module(f"uni.capabilities.{name}")
    return module.CATALOGUE


def load_all() -> list[Catalogue]:
    return [load_catalogue(n) for n in CATALOGUES]


# ── shared input coercion ────────────────────────────────────────────────────────
# Every capability validates its own input. These exist so that a malformed request gets the
# same wording wherever it lands, and so no capability reaches a traceback by accident.

def numbers(payload: dict[str, Any], key: str = "series", *, minimum: int = 1,
            maximum: int = 100_000) -> list[float]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise InvalidInput(f"{key} must be an array of numbers")
    if len(raw) < minimum:
        raise InvalidInput(f"{key} needs at least {minimum} value(s), got {len(raw)}")
    if len(raw) > maximum:
        raise InvalidInput(f"{key} is limited to {maximum} values, got {len(raw)}")
    out: list[float] = []
    for i, v in enumerate(raw):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise InvalidInput(f"{key}[{i}] is not a number")
        value = float(v)
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidInput(f"{key}[{i}] is not finite")
        out.append(value)
    return out


def integer(payload: dict[str, Any], key: str, default: int | None = None, *,
            minimum: int | None = None, maximum: int | None = None) -> int:
    if key not in payload or payload.get(key) is None:
        if default is None:
            raise InvalidInput(f"{key} is required")
        return default
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidInput(f"{key} must be an integer")
    if minimum is not None and value < minimum:
        raise InvalidInput(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise InvalidInput(f"{key} must be <= {maximum}")
    return value


def number(payload: dict[str, Any], key: str, default: float | None = None, *,
           minimum: float | None = None, maximum: float | None = None) -> float:
    if key not in payload or payload.get(key) is None:
        if default is None:
            raise InvalidInput(f"{key} is required")
        return float(default)
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInput(f"{key} must be a number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise InvalidInput(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise InvalidInput(f"{key} must be <= {maximum}")
    return value


def text(payload: dict[str, Any], key: str, *, maximum: int = 200_000,
         required: bool = True, default: str = "") -> str:
    value = payload.get(key)
    if value is None:
        if required:
            raise InvalidInput(f"{key} is required")
        return default
    if not isinstance(value, str):
        raise InvalidInput(f"{key} must be a string")
    if len(value) > maximum:
        raise InvalidInput(f"{key} is limited to {maximum} characters")
    return value


def choice(payload: dict[str, Any], key: str, options: tuple[str, ...], default: str) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str) or value not in options:
        raise InvalidInput(f"{key} must be one of {', '.join(options)}")
    return value


def rounded(value: float, digits: int = 6) -> float:
    """Round for transport. Floats that differ in the 17th digit make two honest providers
    disagree about the same computation, and a consumer comparing them see a fault."""
    if value != value or value in (float("inf"), float("-inf")):
        raise InvalidInput("result is not finite for this input")
    return round(value + 0.0, digits)


#: Schema fragments used across catalogues.
SERIES_SCHEMA = {"type": "array", "items": {"type": "number"}, "minItems": 1}
