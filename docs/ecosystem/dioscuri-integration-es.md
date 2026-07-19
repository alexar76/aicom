# DIOSCURI — integración en el ecosistema

Cómo encajan **DIOSCURI** (gemelos comunitarios) en el stack AICOM junto a GitHub, Gitea y Alien Monitor.

**Landing:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **English:** [dioscuri-integration.md](./dioscuri-integration.md) · **Русский:** [dioscuri-integration-ru.md](./dioscuri-integration-ru.md)

## Planos

| Plano | Rol |
|-------|-----|
| **Monorepo** `dioscuri/` | Fuente de verdad |
| **GitHub** `alexar76/dioscuri` | Espejo público — docs, CI, self-host |
| **Gitea#2** `alexar76/dioscuri` | Espejo ops privado (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Nodo del grafo — poll `GET /health`, KB + estado de adaptadores |

Publicar en GitHub (sin secretos):

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

## Secretos — nunca en git

| Archivo | Propósito |
|---------|-----------|
| `.env` | Tokens de bots, claves LLM |
| `dioscuri.config.json` | Ajustes no secretos (enlaces, temas, moderación) |

Ambos **excluidos** del rsync (`satellite-map.yaml`) y bloqueados por `scripts/verify_mirror_secrets.sh`.

## Enlaces comunitarios (Telegram + Discord)

**Producción (canónico — README y landings):**

| Clave | URL |
|-------|-----|
| Bot Telegram (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Canal Telegram (Castor — noticias) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Invitaciones en `dioscuri.config.json`:

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT"
}
```

Alien Monitor (opcional, panel del grafo):

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790
```

## Nodo Alien Monitor

**DIOSCURI** aparece al noroeste del client shelf. Poll `GET {ALIEN_DIOSCURI_URL}/health`. Gris = inalcanzable; pulso dorado = al menos un gemelo activo o KB sembrada.

## Documentos relacionados

- [DIOSCURI README (ES)](../../dioscuri/README-es.md)
- [Base de conocimiento (ES)](./knowledge-base-es.md)
- [Setup](../../dioscuri/docs/setup.md)
