from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from relay_scout.models import EndpointTarget


def default_config_path() -> Path:
    env = os.environ.get("RELAY_SCOUT_CONFIG")
    if env:
        return Path(env)
    return Path("relay-scout.yaml")


def load_config(path: Path | None = None) -> list[EndpointTarget]:
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        return _default_targets()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    targets = raw.get("targets") or raw.get("endpoints") or []
    out: list[EndpointTarget] = []
    for item in targets:
        if not isinstance(item, dict):
            continue
        out.append(
            EndpointTarget(
                name=str(item.get("name") or "unnamed"),
                url=str(item.get("url") or ""),
                kind=str(item.get("kind") or "json"),
                webhook_urls=[str(u) for u in (item.get("webhook_urls") or [])],
                interval_seconds=int(item.get("interval_seconds") or 60),
            )
        )
    return out or _default_targets()


def _default_targets() -> list[EndpointTarget]:
    return [
        EndpointTarget(name="factory", url="https://magic-ai-factory.com/api/health", kind="json"),
        EndpointTarget(name="monitor", url="https://magic-ai-factory.com/monitor/api/health", kind="json"),
        EndpointTarget(name="dioscuri", url="http://203.0.113.20:8790/health", kind="json"),
    ]


def config_as_dict(targets: list[EndpointTarget]) -> dict[str, Any]:
    return {
        "targets": [
            {
                "name": t.name,
                "url": t.url,
                "kind": t.kind,
                "webhook_urls": t.webhook_urls,
                "interval_seconds": t.interval_seconds,
            }
            for t in targets
        ]
    }
