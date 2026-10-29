"""Canonical MCP packager logic (stdlib-only). Used by stdio MCP server and hub shim."""

from __future__ import annotations

import base64
import json
import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from aimarket_mcp_packager.server_template import SERVER_SOURCE

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
        if input_schema and input_schema.get("type", "object") != "object":
            raise ValueError("MCP tool inputs must use an object schema")
        input_schema = {"type": "object", **input_schema}
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
                    "name": _slug(capability_id),
                    "description": description,
                    "inputSchema": input_schema or {"type": "object", "properties": {}},
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
            f"  stdin_open: true\n"
            f"  environment:\n"
            f"    - MCP_SERVER_NAME={safe_name}\n"
            f"    - AIMARKET_API_KEY\n"
            f"    - AIMARKET_HUB_URL\n"
            f"    - AIMARKET_SOURCE_HUB\n"
            f"  restart: unless-stopped"
        )
        connection_string = json.dumps(
            {
                "mcpServers": {
                    safe_name: {
                        "command": "docker",
                        "args": self._docker_args(image_tag),
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
            env_template={"AIMARKET_HUB_URL": "https://modelmarket.dev", "AIMARKET_API_KEY": "",
                          "AIMARKET_SOURCE_HUB": ""},
            subscription_tiers=mcp_manifest["pricing"]["tiers"],
            license_required=False,
        )

    @staticmethod
    def _docker_args(image: str) -> list[str]:
        return ["run", "--rm", "-i", "--env", "AIMARKET_API_KEY", "--env", "AIMARKET_HUB_URL",
                "--env", "AIMARKET_SOURCE_HUB", image]

    def generate_server_source(self, package: MCPServerPackage) -> str:
        config = {"name": package.name.split("/")[-1], "capability_id": package.capability_id,
                  "product_id": package.product_id, "tool": package.mcp_manifest["tools"][0]}
        encoded = base64.b64encode(json.dumps(config).encode()).decode("ascii")
        return SERVER_SOURCE.replace("__CONFIG_B64__", encoded)

    def generate_dockerfile(self, package: MCPServerPackage) -> str:
        short = package.name.split("/")[-1]
        source = base64.b64encode(self.generate_server_source(package).encode()).decode("ascii")
        return f"""# MCP Server: {package.name}
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir 'aimarket-mcp>=0.6.3,<0.7' 'jsonschema>=4.23,<5'
RUN python -c "import base64,pathlib; pathlib.Path('/app/mcp_server.py').write_bytes(base64.b64decode('{source}'))"
ENV MCP_SERVER_NAME={short}
ENV HOME=/tmp PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT ["python", "/app/mcp_server.py"]
"""

    def generate_claude_desktop_config(self, package: MCPServerPackage) -> str:
        return json.dumps(
            {
                "mcpServers": {
                    package.name.split("/")[-1]: {
                        "command": "docker",
                        "args": self._docker_args(package.docker_image),
                        "description": package.mcp_manifest["server"]["description"],
                    }
                }
            },
            indent=2,
        )

    def generate_install_script(self, package: MCPServerPackage) -> str:
        """Preserve the helper exposed by the old Hub-backed compatibility import."""
        command = shlex.join(["docker", *self._docker_args(package.docker_image)])
        return ("#!/bin/sh\nset -eu\n"
                f"docker pull {shlex.quote(package.docker_image)}\n"
                f"printf '%s\\n' {shlex.quote('MCP command: ' + command)}\n")
