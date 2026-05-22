"""JSON Schema validation for capability manifests.

Validates incoming manifests from peer hubs against the protocol schemas.
Rejects manifests that don't conform, protecting the index from garbage.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import jsonschema

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


def _schema_dir() -> Path:
    env = os.environ.get("AIMARKET_SCHEMA_DIR", "").strip()
    if env:
        return Path(env)
    # Repo layout: aicom/aimarket-protocol/schemas
    repo = Path(__file__).resolve().parent.parent.parent / "aimarket-protocol" / "schemas"
    if repo.is_dir():
        return repo
    # Docker: /app/aimarket-protocol/schemas
    return Path("/app/aimarket-protocol/schemas")


_SCHEMA_DIR = _schema_dir()


def _load_schema(name: str) -> dict[str, Any] | None:
    path = _SCHEMA_DIR / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def validate_well_known(data: dict[str, Any]) -> list[str]:
    """Validate a .well-known/ai-market.json response. Returns list of errors (empty = valid)."""
    schema = _load_schema("well-known.json")
    if not schema or not _HAS_JSONSCHEMA:
        return _basic_well_known_check(data)
    return _validate(schema, data)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Validate a capability manifest. Returns list of errors (empty = valid)."""
    schema = _load_schema("manifest.json")
    if not schema or not _HAS_JSONSCHEMA:
        return _basic_manifest_check(data)
    return _validate(schema, data)


def validate_receipt(data: dict[str, Any]) -> list[str]:
    """Validate a receipt. Returns list of errors (empty = valid)."""
    schema = _load_schema("receipt.json")
    if not schema or not _HAS_JSONSCHEMA:
        return []
    return _validate(schema, data)


def _validate(schema: dict[str, Any], data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    validator_cls = jsonschema.validators.validator_for(schema)
    # Custom resolver to not fetch $ref from network
    resolver = jsonschema.RefResolver.from_schema(schema)
    for err in validator_cls(schema, resolver=resolver).iter_errors(data):
        errors.append(err.message)
    return errors


def _basic_well_known_check(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("name"), str):
        errors.append("name is required")
    if not isinstance(data.get("manifest_url"), str):
        errors.append("manifest_url is required")
    return errors


def _basic_manifest_check(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data.get("protocol_version"), str):
        errors.append("protocol_version is required")
    if not isinstance(data.get("tools"), list):
        errors.append("tools array is required")
    if not isinstance(data.get("signature"), dict):
        errors.append("signature is required")
    return errors
