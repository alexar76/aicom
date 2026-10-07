# Instalación para agentes — Hub MCP y WARDEN

> 🌐 [English](README.md) · [Русский](README.ru.md) · **Español** · [Français](README.fr.md) · [中文](README.zh.md)

Dos skills públicos y una URL para pegar. No hace falta clonar este monorepo para **probar** el marketplace.

| Puerta | Qué es |
|------|------------|
| **Hub MCP** | `https://modelmarket.dev/mcp` — primero `market_search`, después `market_invoke`. Pasa siempre `source_hub`. |
| **Skill: aimarket-hub-mcp** | Explica cómo añadir esa URL y llamar las dos herramientas sin recibir 404 en resultados federados. |
| **Skill: warden-mcp-firewall** | `npx -y @aimarket/warden` — revisa un volcado de `tools/list`. No actúa como proxy de otros servidores. |

Documentación canónica: [`hosted-mcp-endpoint.md`](../hosted-mcp-endpoint.md). El tamaño del trial activo está en `free_trial.max_invokes_per_visitor` de [/.well-known/ai-market.json](https://modelmarket.dev/.well-known/ai-market.json).

## Archivos canónicos

GitHub sirve directamente estos archivos:

- [`agent-skills/skills/aimarket-hub-mcp/SKILL.md`](../../agent-skills/skills/aimarket-hub-mcp/SKILL.md)
- [`agent-skills/skills/warden-mcp-firewall/SKILL.md`](../../agent-skills/skills/warden-mcp-firewall/SKILL.md)
- Paquete de plugin: [`agent-skills/`](../../agent-skills/) · marketplace: [`.claude-plugin/marketplace.json`](../../.claude-plugin/marketplace.json)

`.cursor/skills/` es la copia para Cursor de esos mismos dos archivos, incluida en el repositorio. No crees una tercera ruta.

Archivos raw:

- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md
- https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

## Cursor — skill Hub MCP

Sin clonar, desde cualquier proyecto:

```bash
mkdir -p .cursor/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o .cursor/skills/aimarket-hub-mcp/SKILL.md
```

Después pega `https://modelmarket.dev/mcp` en `.cursor/mcp.json` (la estructura aparece en el skill):

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp"
    }
  }
}
```

Si este repositorio ya es el workspace, el skill está en `.cursor/skills/aimarket-hub-mcp/`; solo falta añadir la URL MCP.

## Claude Code — skill Hub MCP

Sin clonar:

```bash
mkdir -p ~/.claude/skills/aimarket-hub-mcp
curl -fsSL https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/aimarket-hub-mcp/SKILL.md \
  -o ~/.claude/skills/aimarket-hub-mcp/SKILL.md
```

Añade la misma URL en los ajustes MCP de Claude Desktop o Claude Code.

O instala el plugin desde un checkout de AICOM:

```bash
claude plugin marketplace add /path/to/aicom
claude plugin install aimarket-agent-skills
```

No existe una entrada de Anysphere Cursor Marketplace.

## Skill firewall WARDEN

Usa el mismo `curl`, pero con el directorio `warden-mcp-firewall`:

https://raw.githubusercontent.com/alexar76/aicom/main/agent-skills/skills/warden-mcp-firewall/SKILL.md

Configuración stdio del skill:

```json
{
  "mcpServers": {
    "warden": {
      "command": "npx",
      "args": ["-y", "@aimarket/warden"]
    }
  }
}
```

WARDEN no inicia ni hace proxy de otros servidores MCP; pásale `tools/list`.

## Tras las llamadas gratuitas: una clave

[modelmarket.dev/start](https://modelmarket.dev/start) da una clave con un clic (sin correo, empieza en $0) y la recarga con USDC en Base desde una billetera del navegador. Pon la clave como cabecera en la misma conexión MCP: las llamadas de pago se cobran del saldo y, mientras no alcance, la prueba gratuita sigue valiendo.

```bash
claude mcp add --transport http aimarket https://modelmarket.dev/mcp --header "X-API-Key: aimk_…"
```

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp",
      "headers": { "X-API-Key": "aimk_…" }
    }
  }
}
```

claude.ai o Claude Desktop (conector personalizado, sin campo de cabecera) y cualquier otro cliente que solo acepte una URL (conectores de ChatGPT en modo desarrollador, plataformas de agentes): pega `https://modelmarket.dev/mcp/k/aimk_…` — la clave va en la URL, así que mantenla privada.

## Sin cripto en la primera pantalla

Los skills y la primera pantalla empiezan por la URL y las dos herramientas: trial y luego 402. No empieces por monederos ni tokens.
