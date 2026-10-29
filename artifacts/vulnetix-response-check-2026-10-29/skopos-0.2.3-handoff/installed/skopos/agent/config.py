from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

ProviderKind = Literal["openai_compatible", "anthropic_compatible", "ollama", "lmstudio"]


@dataclass(frozen=True)
class ProviderConfig:
    id: str
    kind: ProviderKind
    base_url: str
    model: str
    api_key: str | None = None
    api_key_env: str | None = None
    extra_headers: dict[str, str] | None = None


@dataclass(frozen=True)
class AgentConfig:
    default_provider: str
    providers: dict[str, ProviderConfig]
    system_prompt: str
    max_context_chars: int = 120_000
    briefing_provider: str | None = None
    briefing_model: str | None = None


def _resolve_api_key(raw: dict[str, Any]) -> str | None:
    # Inline api_key in agent.yaml is lab-only — production must use env vars so
    # secrets are not committed or baked into images.
    if raw.get("api_key"):
        allow = os.environ.get("SKOPOS_ALLOW_INLINE_API_KEYS", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not allow:
            raise ValueError(
                "agent.yaml inline api_key is disabled; set api_key_env "
                "(or SKOPOS_ALLOW_INLINE_API_KEYS=1 for local lab only)"
            )
        return str(raw["api_key"])
    env_name = raw.get("api_key_env")
    if env_name:
        return os.environ.get(str(env_name))
    return None


def load_agent_config(path: str = "./agent.yaml") -> AgentConfig:
    p = Path(path).expanduser()
    if not p.exists():
        p = Path(path.replace(".yaml", ".example.yaml")).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")

    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("agent.yaml must be a mapping")

    default = str(raw.get("default_provider", "deepseek"))
    providers_raw = raw.get("providers") or {}
    providers: dict[str, ProviderConfig] = {}
    for pid, pr in providers_raw.items():
        if not isinstance(pr, dict):
            continue
        providers[str(pid)] = ProviderConfig(
            id=str(pid),
            kind=str(pr.get("kind", "openai_compatible")),  # type: ignore[arg-type]
            base_url=str(pr.get("base_url", "")),
            model=str(pr.get("model", "")),
            api_key=_resolve_api_key(pr),
            api_key_env=str(pr["api_key_env"]) if pr.get("api_key_env") else None,
            extra_headers=pr.get("extra_headers"),
        )

    return AgentConfig(
        default_provider=default,
        providers=providers,
        system_prompt=str(
            raw.get(
                "system_prompt",
                "You are a senior security analyst for production Linux servers.",
            )
        ),
        max_context_chars=int(raw.get("max_context_chars", 120_000)),
        briefing_provider=str(raw["briefing_provider"]).strip() if raw.get("briefing_provider") else None,
        briefing_model=str(raw["briefing_model"]).strip() if raw.get("briefing_model") else None,
    )


def get_provider(cfg: AgentConfig, provider_id: str | None = None) -> ProviderConfig:
    pid = provider_id or cfg.default_provider
    if pid not in cfg.providers:
        raise KeyError(f"Unknown provider '{pid}'. Available: {', '.join(cfg.providers)}")
    prov = cfg.providers[pid]
    if not prov.api_key and prov.kind in ("openai_compatible", "anthropic_compatible"):
        if prov.api_key_env:
            key = os.environ.get(prov.api_key_env)
            if key:
                return ProviderConfig(
                    id=prov.id,
                    kind=prov.kind,
                    base_url=prov.base_url,
                    model=prov.model,
                    api_key=key,
                    api_key_env=prov.api_key_env,
                    extra_headers=prov.extra_headers,
                )
    return prov
