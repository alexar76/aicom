# aimarket-mcp-packager

**Package any capability as a ready-to-run MCP server for Claude Desktop.**
One command: capability → Docker image + MCP manifest + Claude Desktop config. Self-hosted distribution with subscription pricing. Path to Anthropic MCP-registry.

## When to Use
- Distribute AI capabilities as self-hosted Docker containers
- List commercial MCP servers in Anthropic's registry
- Enterprise customers who want on-prem deployment
- Subscription-based AI capability monetization

## Installation
```bash
pip install aimarket-mcp-packager
```

## Example
```python
from aimarket_mcp_packager.mcp_packager import MCPPackager

packager = MCPPackager()
pkg = packager.package(
    capability_id="translate.multi@v2", product_id="prod-001",
    name="Lyra", description="Multilingual translator",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    price_per_call_usd=0.40
)

print(pkg.docker_image)              # aifactory/lyra:2.0.0
print(pkg.subscription_tiers)        # Starter $9.99/mo, Pro $49.99/mo, Enterprise $299.99/mo
print(packager.generate_claude_desktop_config(pkg))
# {"mcpServers": {"lyra": {"command": "docker", "args": ["run", "--rm", "-i", "aifactory/lyra:2.0.0"]}}}

# Generate full Dockerfile
print(packager.generate_dockerfile(pkg))
```

## Subscription Tiers
| Tier | Calls/month | Price |
|------|------------|-------|
| Starter | 100 | $9.99 |
| Pro | 1,000 | $49.99 |
| Enterprise | 10,000 | $299.99 |

## License
MIT · Maintained by AI-Factory
