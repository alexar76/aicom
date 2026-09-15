"""When GitHub catalog publish is armed — shared by QA house gate + catalog push."""

from __future__ import annotations

import os
from typing import Any


def github_pat_configured() -> bool:
    """True when the host has a write token for alexar76 GitHub publishes."""
    return bool((os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN") or "").strip())


def _general_flag(general: dict[str, Any] | None, key: str, default: Any = None) -> Any:
    if general is not None:
        return general.get(key, default)
    try:
        from core.config_merge import load_merged_config
        from core.paths import config_path

        raw = load_merged_config(config_path())
        g = raw.get("general") if isinstance(raw, dict) else None
        if isinstance(g, dict):
            return g.get(key, default)
    except Exception:
        pass
    return default


def github_catalog_armed(general: dict[str, Any] | None = None) -> bool:
    """Operator turned catalog publish on in Settings."""
    return bool(_general_flag(general, "product_catalog_enabled", False))


def github_house_gate_active(general: dict[str, Any] | None = None) -> bool:
    """README/CONTRIBUTING GitHub-house gate runs only when catalog is on *and* GH auth exists.

    Safe default: if GitHub is not configured, do not fail QA on house files.
    """
    if not bool(_general_flag(general, "product_catalog_require_github_house", True)):
        return False
    if not github_catalog_armed(general):
        return False
    return github_pat_configured()


def github_catalog_ready(general: dict[str, Any] | None = None) -> bool:
    """Catalog push may run: Settings on + GH_PAT present."""
    return github_catalog_armed(general) and github_pat_configured()
