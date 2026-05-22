"""aimarket-mcp-packager plugin — Package capabilities as ready-to-run MCP servers for Claude Desktop."""

from aimarket_hub.plugin import HubPlugin
from aimarket_mcp_packager.mcp_packager import MCPPackager


class MCPPlugin(HubPlugin):
    name = "aimarket-mcp-packager"
    version = "2.0.0"
    description = "Package capabilities as ready-to-run MCP servers for Claude Desktop"
    homepage = "https://github.com/ai-factory/aimarket-mcp-packager"
    category = "tooling"

    def __init__(self):
        super().__init__()
        self._packager = MCPPackager()

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field
        from fastapi.responses import JSONResponse

        class PackageRequest(BaseModel):
            capability_id: str = Field(..., min_length=2)
            product_id: str = Field(..., min_length=2)
            name: str = Field(..., min_length=1)
            description: str = Field("")
            input_schema: dict = Field(default_factory=dict)

        @router.post("/mcp/package")
        async def package_capability(body: PackageRequest):
            pkg = self._packager.package(body.capability_id, body.product_id,
                                          body.name, body.description, body.input_schema)
            return {"docker_image": pkg.docker_image, "subscription_tiers": pkg.subscription_tiers,
                    "mcp_manifest": pkg.mcp_manifest}

    def get_manifest_extension(self):
        return {"mcp": {"enabled": True, "registry": "aifactory"}}
