"""
Bootstrap /app/data/config/model_providers.yaml when missing.

Docker Compose bind-mounts ./data over /app/data, so a fresh host volume has no
config — the admin LLM Providers tab is empty and the pipeline has no keys.
We copy from (in order): repo data/config example, then image-only llm/_defaults.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

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
