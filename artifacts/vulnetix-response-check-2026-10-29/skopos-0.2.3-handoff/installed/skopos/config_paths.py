"""Resolve config paths inside the project directory."""

from __future__ import annotations

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_root() -> Path:
    return _PROJECT_ROOT


def resolve_config_path(path: str, *, root: Path | None = None) -> Path:
    base = (root or _PROJECT_ROOT).resolve()
    candidate = Path(path).expanduser()
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError("Config path must stay inside the project directory")
    if resolved.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("Config path must be a YAML file")
    return resolved
