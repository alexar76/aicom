#!/usr/bin/env python3
"""Stdio MCP server for Glama / Claude Desktop — AIMarket MCP Packager tools.

Exposes three read-only generator tools that turn an AIMarket hub capability
into the artifacts needed to ship it as a self-hosted MCP server product:
a packaged manifest, a Dockerfile, and a Claude Desktop config snippet.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from aimarket_mcp_packager.packager_core import MCPPackager

mcp = FastMCP(
    "aimarket-mcp-packager",
    instructions=(
        "Package an AIMarket hub capability as a self-hosted MCP server product. "
        "Call `package_capability` first to get the manifest, Docker image name, "
        "pricing tiers, and connection string; then `generate_dockerfile` and "
        "`generate_claude_desktop_config` to get the deployable artifacts. All "
        "three tools are pure and read-only — they never deploy or mutate anything."
    ),
)
_packager = MCPPackager()


# ── Shared parameter annotations (described once, reused by all tools) ─────────
CapabilityId = Annotated[
    str,
    Field(
        description=(
            "Fully-qualified capability identifier to package, e.g. "
            "'translate.multi@v2'. This is the single capability the generated "
            "MCP server will expose as a tool."
        ),
        examples=["translate.multi@v2", "summarize.long@v1"],
    ),
]
ProductId = Annotated[
    str,
    Field(
        description=(
            "Owning product ID on the AIMarket hub, e.g. 'prod-translate'. Used to "
            "namespace the Docker image and the MCP manifest."
        ),
        examples=["prod-translate"],
    ),
]
ServerName = Annotated[
    str,
    Field(
        description=(
            "Human-readable display name for the packaged MCP server, shown to end "
            "users in MCP clients such as Claude Desktop (e.g. 'Lyra Translator')."
        ),
        examples=["Lyra Translator"],
    ),
]
ServerDescription = Annotated[
    str,
    Field(
        description=(
            "One- or two-sentence summary of what the capability does. Surfaced in "
            "the MCP manifest and the Claude Desktop config. Optional but strongly "
            "recommended — it becomes the tool description in the generated server."
        ),
        examples=["Translate text into multiple languages with one call."],
    ),
]
InputSchema = Annotated[
    dict[str, Any] | None,
    Field(
        description=(
            "JSON Schema object describing the capability's input. For example, an "
            "object with a required string property 'text'. Omit or pass null for a "
            "schema-less capability."
        ),
        examples=[
            {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        ],
    ),
]
Registry = Annotated[
    str,
    Field(
        description=(
            "Container registry namespace for the built image. Defaults to "
            "'aifactory'. Set your own org/namespace to publish under a different "
            "account (e.g. 'ghcr.io/acme')."
        ),
        examples=["aifactory", "ghcr.io/acme"],
    ),
]


def _coerce_schema(value: dict[str, Any] | str | None) -> dict[str, Any]:
    """Normalize an input schema to a dict, tolerating a JSON string or null."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value.strip() else {}
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


@mcp.tool()
def package_capability(
    capability_id: CapabilityId,
    product_id: ProductId,
    name: ServerName,
    description: ServerDescription = "",
    input_schema: InputSchema = None,
    registry: Registry = "aifactory",
) -> str:
    """Build a complete self-hosted MCP server package for an AIMarket capability.

    Use this first. It assembles everything needed to ship the capability as a
    standalone MCP server: the Docker image name, the MCP manifest (server +
    tool definition), subscription/pricing tiers, and a connection string.

    Returns:
        A JSON object (string) with keys:
          - `docker_image`: the image name to build/run.
          - `mcp_manifest`: the full MCP manifest (server metadata + tools).
          - `subscription_tiers`: pricing tiers derived for the capability.
          - `connection_string`: how a client connects to the running server.

    Example:
        package_capability(
            capability_id="translate.multi@v2",
            product_id="prod-translate",
            name="Lyra Translator",
            description="Translate text into multiple languages.",
            input_schema={"type": "object",
                          "properties": {"text": {"type": "string"}},
                          "required": ["text"]},
        )
    """
    pkg = _packager.package(
        capability_id=capability_id,
        product_id=product_id,
        name=name,
        description=description,
        input_schema=_coerce_schema(input_schema),
        registry=registry,
    )
    return json.dumps(
        {
            "docker_image": pkg.docker_image,
            "mcp_manifest": pkg.mcp_manifest,
            "subscription_tiers": pkg.subscription_tiers,
            "connection_string": pkg.connection_string,
        },
        indent=2,
    )


@mcp.tool()
def generate_dockerfile(
    capability_id: CapabilityId,
    product_id: ProductId,
    name: ServerName,
    description: ServerDescription = "",
    input_schema: InputSchema = None,
    registry: Registry = "aifactory",
) -> str:
    """Generate a ready-to-build Dockerfile for the packaged MCP server.

    Takes the same capability inputs as `package_capability` and returns the
    Dockerfile text that builds the self-hosted MCP server image for it.

    Returns:
        The Dockerfile contents as plain text — write it to `Dockerfile` and
        run `docker build` to produce the image named in `package_capability`'s
        `docker_image` field.

    Example:
        generate_dockerfile(
            capability_id="translate.multi@v2",
            product_id="prod-translate",
            name="Lyra Translator",
        )
    """
    pkg = _packager.package(
        capability_id, product_id, name, description, _coerce_schema(input_schema),
        registry=registry,
    )
    return _packager.generate_dockerfile(pkg)


@mcp.tool()
def generate_claude_desktop_config(
    capability_id: CapabilityId,
    product_id: ProductId,
    name: ServerName,
    description: ServerDescription = "",
    input_schema: InputSchema = None,
    registry: Registry = "aifactory",
) -> str:
    """Generate a claude_desktop_config.json snippet for the packaged MCP server.

    Takes the same capability inputs as `package_capability` and returns the
    `mcpServers` entry that registers the docker-run MCP server with Claude
    Desktop (or any MCP host that reads this config format).

    Returns:
        A JSON object (string) containing an `mcpServers` block — merge it into
        the user's existing `claude_desktop_config.json` and restart the host.

    Example:
        generate_claude_desktop_config(
            capability_id="translate.multi@v2",
            product_id="prod-translate",
            name="Lyra Translator",
        )
    """
    pkg = _packager.package(
        capability_id, product_id, name, description, _coerce_schema(input_schema),
        registry=registry,
    )
    return _packager.generate_claude_desktop_config(pkg)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
