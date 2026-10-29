"""Economy configuration — derived from env; disabled unless explicitly enabled."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class EconomyConfig:
    enabled: bool
    public_base_url: str
    product_id: str
    publisher_id: str
    invoke_path: str
    api_key: str | None
    hub_url: str | None
    auto_register: bool
    publish_token: str | None
    agent_yaml_path: str
    config_path: str

    @property
    def invoke_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        path = self.invoke_path if self.invoke_path.startswith("/") else f"/{self.invoke_path}"
        return f"{base}{path}"


def load_economy_config() -> EconomyConfig:
    public = (
        os.environ.get("SKOPOS_AIMARKET_PUBLIC_URL", "").strip()
        or os.environ.get("SKOPOS_PUBLIC_URL", "").strip()
        or "http://127.0.0.1:8502"
    )
    return EconomyConfig(
        enabled=_truthy("SKOPOS_AIMARKET_ENABLED"),
        public_base_url=public,
        product_id=os.environ.get("SKOPOS_AIMARKET_PRODUCT_ID", "prod-skopos").strip() or "prod-skopos",
        publisher_id=os.environ.get("SKOPOS_AIMARKET_PUBLISHER_ID", "skopos-fleet").strip() or "skopos-fleet",
        invoke_path=os.environ.get("SKOPOS_AIMARKET_INVOKE_PATH", "/aimarket/invoke").strip() or "/aimarket/invoke",
        api_key=os.environ.get("SKOPOS_AIMARKET_API_KEY", "").strip() or None,
        hub_url=os.environ.get("SKOPOS_HUB_URL", "").strip() or None,
        auto_register=_truthy("SKOPOS_AIMARKET_AUTO_REGISTER"),
        publish_token=(
            os.environ.get("SKOPOS_AIMARKET_PUBLISH_TOKEN", "").strip()
            or os.environ.get("AIMARKET_PUBLISH_TOKEN", "").strip()
            or None
        ),
        agent_yaml_path=os.environ.get("SKOPOS_AGENT_YAML", "./agent.yaml").strip() or "./agent.yaml",
        config_path=os.environ.get("SKOPOS_CONFIG_PATH", "./servers.yaml").strip() or "./servers.yaml",
    )
