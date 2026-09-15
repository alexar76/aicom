"""Tests for MCP packager name/registry sanitization (compose/Dockerfile safety)."""

import json
import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "aimarket-mcp-packager"
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

from aimarket_mcp_packager.packager_core import MCPPackager  # noqa: E402


def test_package_sanitizes_name_and_registry():
    pkg = MCPPackager().package(
        capability_id="cap",
        product_id="prod",
        name="Evil\n  privileged: true",
        description="d",
        input_schema={},
        registry="acme/../x",
    )
    # No newline / YAML metachars leak into the image tag or compose text.
    assert "\n" not in pkg.docker_image
    assert "privileged: true" not in pkg.docker_compose_snippet
    assert ":" not in pkg.docker_image.rsplit(":", 1)[0]  # only the tag colon
    assert pkg.docker_image == "acme-..-x/evil-privileged-true:2.0.0"

    # Compose service key + env value are the slug, not raw input.
    first_line = pkg.docker_compose_snippet.splitlines()[0]
    assert first_line == "evil-privileged-true:"

    conn = json.loads(pkg.connection_string)
    assert list(conn["mcpServers"].keys()) == ["evil-privileged-true"]


def test_package_empty_name_falls_back():
    pkg = MCPPackager().package("cap", "prod", "   ", "", {}, registry="")
    assert pkg.docker_image == "aifactory/mcp:2.0.0"


def test_dockerfile_has_no_injection():
    pkg = MCPPackager().package("cap", "prod", "Bad\nRUN rm -rf /", "", {})
    dockerfile = MCPPackager().generate_dockerfile(pkg)
    assert "rm -rf" not in dockerfile
    assert "RUN rm" not in dockerfile
