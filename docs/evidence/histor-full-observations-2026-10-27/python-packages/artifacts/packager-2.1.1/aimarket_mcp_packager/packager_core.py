"""Canonical MCP packager logic (stdlib-only). Used by stdio MCP server and hub shim."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(value: str, fallback: str = "mcp") -> str:
    """Constrain free-text to a docker/compose-safe token.

    ``name`` and ``registry`` flow into image tags and the docker-compose /
    Dockerfile text templates. Without this, a value containing newlines or
    YAML metacharacters could inject extra compose keys (e.g. ``privileged``).
    """
    slug = _SLUG_RE.sub("-", (value or "").strip().lower()).strip("-._")
    return slug or fallback


@dataclass
class MCPServerPackage:
    name: str
    version: str
    capability_id: str
    product_id: str
    docker_image: str
    docker_compose_snippet: str
    mcp_manifest: dict[str, Any]
    connection_string: str
    env_template: dict[str, str] = field(default_factory=dict)
    subscription_tiers: list[dict[str, Any]] = field(default_factory=list)
    license_required: bool = True


class MCPPackager:
    """Package capabilities as self-hosted MCP servers."""

    def package(
        self,
        capability_id: str,
        product_id: str,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        price_per_call_usd: float = 0.40,
        registry: str = "aifactory",
    ) -> MCPServerPackage:
        del price_per_call_usd
        safe_name = _slug(name)
        safe_registry = _slug(registry, "aifactory")
        image_name = f"{safe_registry}/{safe_name}"
        image_tag = f"{image_name}:2.0.0"
        mcp_manifest = {
            "protocol": "mcp",
            "version": "1.0",
            "server": {
                "name": f"{name} MCP Server",
                "description": description,
                "vendor": registry,
            },
            "tools": [
                {
                    "name": capability_id,
                    "description": description,
                    "inputSchema": input_schema,
                }
            ],
            "pricing": {
                "model": "subscription",
                "tiers": [
                    {"name": "Starter", "calls_per_month": 100, "price_usd_month": 9.99},
                    {"name": "Pro", "calls_per_month": 1000, "price_usd_month": 49.99},
                    {"name": "Enterprise", "calls_per_month": 10000, "price_usd_month": 299.99},
                ],
            },
        }
        docker_compose = (
            f"{safe_name}:\n"
            f"  image: {image_tag}\n"
            f"  ports:\n"
            f"    - '3100:3100'\n"
            f"  environment:\n"
            f"    - MCP_SERVER_NAME={safe_name}\n"
            f"    - AIFACTORY_LICENSE_KEY=${{AIFACTORY_LICENSE_KEY}}\n"
            f"  restart: unless-stopped"
        )
        connection_string = json.dumps(
            {
                "mcpServers": {
                    safe_name: {
                        "command": "docker",
                        "args": ["run", "-d", "-p", "3100:3100", image_tag],
                        "env": {"AIFACTORY_LICENSE_KEY": "${AIFACTORY_LICENSE_KEY}"},
                    }
                }
            },
            indent=2,
        )
        return MCPServerPackage(
            name=image_name,
            version="2.0.0",
            capability_id=capability_id,
            product_id=product_id,
            docker_image=image_tag,
            docker_compose_snippet=docker_compose,
            mcp_manifest=mcp_manifest,
            connection_string=connection_string,
            env_template={"AIFACTORY_LICENSE_KEY": "your_license_key_here"},
            subscription_tiers=mcp_manifest["pricing"]["tiers"],
        )

    def generate_dockerfile(self, package: MCPServerPackage) -> str:
        short = package.name.split("/")[-1]
        return f"""# MCP Server: {package.name}
FROM python:3.12-slim
WORKDIR /app
ENV MCP_SERVER_NAME={short}
ENV MCP_SERVER_PORT=3100
EXPOSE 3100
ENTRYPOINT ["python", "-m", "mcp_server"]
"""

    def generate_claude_desktop_config(self, package: MCPServerPackage) -> str:
        return json.dumps(
            {
                "mcpServers": {
                    package.name.split("/")[-1]: {
                        "command": "docker",
                        "args": ["run", "--rm", "-i", package.docker_image],
                        "description": package.mcp_manifest["server"]["description"],
                    }
                }
            },
            indent=2,
        )
