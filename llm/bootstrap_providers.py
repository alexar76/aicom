"""
Bootstrap /app/data/config/model_providers.yaml when missing.

Docker Compose bind-mounts ./data over /app/data, so a fresh host volume has no
config — the admin LLM Providers tab is empty and the pipeline has no keys.
We copy from (in order): repo data/config example, then image-only llm/_defaults.

Also auto-migrates legacy provider ids (deep-seek → deepseek_api) in YAML config
and ``llm_calls.jsonl`` on startup when enabled.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

import yaml

from core.paths import data_root, logs_dir
from llm.pricing_estimate import migrate_llm_calls_provider_ids
from llm.provider_ids import is_legacy_provider_id, normalize_llm_provider_id

logger = logging.getLogger(__name__)


def _app_root_from_config_path(config_path: Path) -> Path:
    # /app/data/config/model_providers.yaml -> /app
    return config_path.parents[2]


def _example_candidates(config_path: Path) -> list[Path]:
    app = _app_root_from_config_path(config_path)
    return [
        app / "data" / "config" / "model_providers.example.yaml",
        app / "llm" / "_defaults" / "model_providers.example.yaml",
    ]


def ensure_model_providers_file(config_path: str | Path = "/app/data/config/model_providers.yaml") -> bool:
    """
    If model_providers.yaml is missing, copy the bundled example next to it.

    Returns True if the target file exists after the call (already there or created).
    """
    p = Path(config_path)
    if p.exists():
        return True
    for ex in _example_candidates(p):
        if ex.is_file():
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ex, p)
            logger.info(
                "Bootstrapped LLM providers config at %s from %s — set DEEPSEEK_API_KEY "
                "(or other api_key_env vars) in the environment or edit keys in Admin.",
                p,
                ex,
            )
            return True
    logger.warning(
        "Cannot bootstrap %s: no example found (tried %s).",
        p,
        ", ".join(str(x) for x in _example_candidates(p)),
    )
    return False


def migrate_model_providers_yaml(config_path: str | Path) -> dict[str, int]:
    """
    Rename legacy keys under ``providers:`` and fix default_provider / routing_rules refs.
    """
    stats = {"keys_renamed": 0, "rules_updated": 0, "skipped": 0}
    p = Path(config_path)
    if not p.is_file():
        return stats

    try:
        with open(p, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Could not read %s for provider id migration: %s", p, e)
        return stats

    if not isinstance(config, dict):
        return stats

    providers = config.get("providers")
    if not isinstance(providers, dict):
        return stats

    renamed: dict[str, str] = {}
    new_providers: dict[str, Any] = {}
    for key, val in providers.items():
        canon = normalize_llm_provider_id(str(key))
        if is_legacy_provider_id(key):
            renamed[str(key)] = canon
            stats["keys_renamed"] += 1
        if canon in new_providers:
            stats["skipped"] += 1
            continue
        new_providers[canon] = val

    if not renamed:
        return stats

    config["providers"] = new_providers
    dp = config.get("default_provider")
    if isinstance(dp, str) and dp in renamed:
        config["default_provider"] = renamed[dp]

    for rule in config.get("routing_rules") or []:
        if not isinstance(rule, dict):
            continue
        for field in ("preferred_provider", "fallback_provider"):
            val = rule.get(field)
            if isinstance(val, str) and val in renamed:
                rule[field] = renamed[val]
                stats["rules_updated"] += 1

    backup = p.with_suffix(p.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(p, backup)
    with open(p, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)

    logger.info(
        "Migrated legacy provider ids in %s: %s (rules_updated=%s)",
        p,
        renamed,
        stats["rules_updated"],
    )
    return stats


def auto_migrate_provider_ids(
    *,
    config_path: str | Path | None = None,
    llm_calls_path: str | Path | None = None,
    migrate_yaml: bool = True,
    migrate_jsonl: bool = True,
) -> dict[str, Any]:
    """
    Bootstrap providers file if missing, then migrate legacy provider ids.

    Controlled by ``AIFACTORY_AUTO_MIGRATE_PROVIDER_IDS`` (default ``1``).
    """
    if os.environ.get("AIFACTORY_AUTO_MIGRATE_PROVIDER_IDS", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return {"skipped": True}

    cfg = Path(config_path or data_root() / "config" / "model_providers.yaml")
    ensure_model_providers_file(cfg)

    out: dict[str, Any] = {"config_path": str(cfg)}
    if migrate_yaml and cfg.is_file():
        out["yaml"] = migrate_model_providers_yaml(cfg)

    if migrate_jsonl:
        log_path = Path(llm_calls_path or logs_dir() / "llm_calls.jsonl")
        out["jsonl_path"] = str(log_path)
        out["jsonl"] = migrate_llm_calls_provider_ids(log_path, dry_run=False, re_enrich_cost=True)
        if out["jsonl"].get("migrated"):
            logger.info("Auto-migrated llm_calls provider ids: %s", out["jsonl"])

    return out
