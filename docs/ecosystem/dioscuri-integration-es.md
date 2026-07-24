# DIOSCURI — integración en el ecosistema

Cómo encaja **DIOSCURI** (agentes gemelos comunitarios) en el stack AICOM junto a GitHub, Gitea y Alien Monitor.

**Landing:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **Idiomas:** **[EN](./dioscuri-integration.md)** · **[RU](./dioscuri-integration-ru.md)** · **ES** · **[FR](./dioscuri-integration-fr.md)** · **[ZH](./dioscuri-integration-zh.md)**

## Planos

| Plano | Rol |
|-------|-----|
| **Monorepo** `dioscuri/` | Fuente de verdad |
| **GitHub** `alexar76/dioscuri` | Espejo público — docs, CI, referencia autoalojada |
| **Gitea#2** `alexar76/dioscuri` | Espejo ops privado (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Nodo del grafo — sondea `GET /health`, muestra KB + estado de adaptadores |

Publicar el espejo de GitHub (sin secretos):

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

Sincronizar Gitea (operador):

```bash
./scripts/mirror_to_gitea.sh dioscuri
```

## Despliegue en el host oracle (oracles.modelmarket.dev)

DIOSCURI corre en el **VPS oracle**, no en la flota de la fábrica (`modeldev.modelmarket.dev`). Factory Monitor solo sondea `http://oracles.modelmarket.dev:8790/health`.

**Un solo comando** (mirror → Gitea#2 → ssh → git pull → compose):

```bash
./scripts/deploy_dioscuri_oracle.sh
RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh   # + primera columna THEOROS
```

Requiere `ssh root@oracles.modelmarket.dev` sin contraseña (o `ssh oracle` — ver `~/.ssh/config`). La autenticación para **git push** usa `data/secrets/git-credentials` (igual que `mirror_to_gitea.sh`), no SSH.

Equivalente manual en oracle tras el mirror:

```bash
ssh root@oracles.modelmarket.dev
cd /root/dioscuri && git pull --ff-only && docker compose up -d --build
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
```

`./scripts/deploy_cognition.sh` es para el stack de cognition **local** en el host donde lo ejecutas — no un wrapper para un oracle remoto.

## Secretos — nunca en git

| Archivo | Propósito |
|---------|-----------|
| `.env` | Tokens de bots, claves LLM, claves de sindicación |
| `dioscuri.config.json` | Ajustes no secretos (enlaces, temas, controles de moderación) |

Ambos están **excluidos** del rsync de satélites (`satellite-map.yaml` → `exclude_paths`) y bloqueados por `scripts/verify_mirror_secrets.sh` antes del push.

Copia solo las plantillas:

```bash
cp dioscuri/.env.example dioscuri/.env
cp dioscuri/dioscuri.config.example.json dioscuri/dioscuri.config.json
```

Rellena los tokens en local — **nunca hagas commit**.

## Enlaces comunitarios (Telegram + Discord)

**Producción (canónico — usar en README y landings):**

| Clave | URL |
|-------|-----|
| Bot Telegram (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Canal Telegram (Castor — noticias) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Los usuarios autoalojados definen las invitaciones en `dioscuri.config.json`:

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT",
  "siteUrl": "https://magic-ai-factory.com",
  "githubOrg": "https://github.com/alexar76"
}
```

Alien Monitor lee los enlaces públicos desde env (opcional, para el panel del grafo):

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790          # objetivo del sondeo (red de compose)
```

## THEOROS (columna canon)

**THEOROS** es una tercera persona dentro del mismo proceso DIOSCURI — no un bot aparte. Publica el **Agent Sovereignty Canon** semanal en Discord `#the-canon` (domingo ~16 UTC, content kind `canon`).

| Recurso | URL |
|---------|-----|
| Corpus + landing | [alexar76/theoros](https://github.com/alexar76/theoros) · [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| Debate | `#canon-debate` en el Discord de DIOSCURI |
| Config | `links.theorosUrl` en `dioscuri.config.json`; añade `"theoros"` a `githubRepos` para el grounding de MNEMOSYNE |
| Ejecución manual | `DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1` |

Castor/Pollux anuncian los capítulos; **no** suplantan a Theoros. Guía completa: **[dioscuri/docs/theoros.md](../../dioscuri/docs/theoros.md)** (arquitectura, voice charter, config, checklist).

## Nodo Alien Monitor

El nodo **DIOSCURI** aparece al noroeste del client shelf. Sondea:

```
GET {ALIEN_DIOSCURI_URL}/health
```

Campos de la respuesta utilizados: `adapters.telegram`, `adapters.discord`, `kb.chunks`, `kb.repos`, `uptimeSec`, `social.*` (métricas cacheadas de Discord/Telegram/X).

Gris = inalcanzable; pulso dorado = al menos un gemelo activo o KB sembrada.

### Estadísticas sociales (cacheadas)

`GET /health` incluye `social` cuando hay tokens de API de plataforma configurados:

| Campo | Fuente |
|-------|--------|
| `discord_members` | Discord Bot API `approximate_member_count` |
| `telegram_members` | Telegram `getChatMemberCount` |
| `twitter_followers` | X API v2 `public_metrics` |

TTL de caché: `DIOSCURI_SOCIAL_CACHE_SEC` (por defecto 300s). Alien Monitor muestra las métricas desde caché de inmediato al hacer clic en el nodo — sin llamada en vivo a la API desde el grafo.

Env opcionales: `TWITTER_BEARER_TOKEN`, `TWITTER_USER_ID`, `TELEGRAM_CHANNEL_ID`.

## Sindicación HELIOS (opcional)

Cuando `HELIOS_SYNDICATION=1`, DIOSCURI añade trabajos `release-short` a `HELIOS_QUEUE_PATH` en cada nueva release de GitHub (fail-soft). Ver [helios-integration.md](./helios-integration.md).

## MNEMOSYNE ↔ GitHub

Los gemelos sincronizan READMEs y releases desde **repositorios públicos de GitHub** (`githubOwner: alexar76`). DIOSCURI no necesita su propio repositorio en la lista de KB para responder preguntas del ecosistema — pero publicar `alexar76/dioscuri` permite que los gemelos se documenten a sí mismos.

## Coautores y colaboradores

Los push de satélites se aplastan en **un único commit con autoría humana** (`sanitize_git_commit_meta.py` elimina `Co-Authored-By` y los trailers de herramientas de IA). Tras el push, `prune_github_collaborators.py` elimina del repositorio a los colaboradores bot/cursor/copilot.

## Documentos relacionados

- [DIOSCURI README (EN)](../../dioscuri/README.md) · [RU](../../dioscuri/README-ru.md) · [ES](../../dioscuri/README-es.md)
- [Setup](../../dioscuri/docs/setup.md)
- [Base de conocimiento del ecosistema](./knowledge-base.md)
- [Publicación en Gitea](../gitea-publishing.md) (interno)
