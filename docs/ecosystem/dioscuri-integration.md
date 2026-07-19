# DIOSCURI — ecosystem integration

How **DIOSCURI** (twin community agents) fits the AICOM stack alongside GitHub, Gitea, and Alien Monitor.

**Landing:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **Languages:** **[RU](./dioscuri-integration-ru.md)** · **[ES](./dioscuri-integration-es.md)**

## Planes

| Plane | Role |
|-------|------|
| **Monorepo** `dioscuri/` | Source of truth |
| **GitHub** `alexar76/dioscuri` | Public mirror — docs, CI, self-host reference |
| **Gitea#2** `alexar76/dioscuri` | Private ops mirror (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Graph node — polls `GET /health`, shows KB + adapter status |

Publish GitHub mirror (no secrets):

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

Sync Gitea (operator):

```bash
./scripts/mirror_to_gitea.sh dioscuri
```

## Deploy on oracle host (78.17.126.214)

DIOSCURI runs on the **oracle VPS**, not the factory fleet (`5.129.212.122`). Factory Monitor polls `http://78.17.126.214:8790/health` only.

**One command** (mirror → Gitea#2 → ssh → git pull → compose):

```bash
./scripts/deploy_dioscuri_oracle.sh
RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh   # + first THEOROS column
```

Requires passwordless `ssh root@78.17.126.214` (or `ssh oracle` — see `~/.ssh/config`). Auth for **git push** uses `data/secrets/git-credentials` (same as `mirror_to_gitea.sh`), not SSH.

Manual equivalent on oracle after mirror:

```bash
ssh root@78.17.126.214
cd /root/dioscuri && git pull --ff-only && docker compose up -d --build
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
```

`./scripts/deploy_cognition.sh` is for **local** cognition stack on the host where you run it — not a remote oracle wrapper.

## Secrets — never in git

| File | Purpose |
|------|---------|
| `.env` | Bot tokens, LLM keys, syndication keys |
| `dioscuri.config.json` | Non-secret tuning (links, topics, moderation knobs) |

Both are **excluded** from satellite rsync (`satellite-map.yaml` → `exclude_paths`) and blocked by `scripts/verify_mirror_secrets.sh` before push.

Copy templates only:

```bash
cp dioscuri/.env.example dioscuri/.env
cp dioscuri/dioscuri.config.example.json dioscuri/dioscuri.config.json
```

Fill tokens locally — **never commit**.

## Community links (Telegram + Discord)

**Production (canonical — use in READMEs and landings):**

| Key | URL |
|-----|-----|
| Telegram bot (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Telegram channel (Castor — news) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Self-hosters set invites in `dioscuri.config.json`:

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT",
  "siteUrl": "https://magic-ai-factory.com",
  "githubOrg": "https://github.com/alexar76"
}
```

Alien Monitor reads public links from env (optional, for the graph panel):

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790          # poll target (compose network)
```

## THEOROS (canon column)

**THEOROS** is a third persona in the same DIOSCURI process — not a separate bot. It publishes the weekly **Agent Sovereignty Canon** to Discord `#the-canon` (Sunday ~16 UTC, `canon` content kind).

| Resource | URL |
|----------|-----|
| Corpus + landing | [alexar76/theoros](https://github.com/alexar76/theoros) · [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| Debate | `#canon-debate` on the DIOSCURI Discord |
| Config | `links.theorosUrl` in `dioscuri.config.json`; add `"theoros"` to `githubRepos` for MNEMOSYNE grounding |
| Manual run | `DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1` |

Castor/Pollux announce chapters; they do **not** impersonate Theoros. Full guide: **[dioscuri/docs/theoros.md](../../dioscuri/docs/theoros.md)** (architecture, voice charter, config, checklist).

## Alien Monitor node

The **DIOSCURI** node appears northwest of the client shelf. It polls:

```
GET {ALIEN_DIOSCURI_URL}/health
```

Response fields used: `adapters.telegram`, `adapters.discord`, `kb.chunks`, `kb.repos`, `uptimeSec`, `social.*` (cached Discord/Telegram/X metrics).

Gray = unreachable; gold pulse = at least one twin awake or KB seeded.

### Social stats (cached)

`GET /health` includes `social` when platform API tokens are configured:

| Field | Source |
|-------|--------|
| `discord_members` | Discord Bot API `approximate_member_count` |
| `telegram_members` | Telegram `getChatMemberCount` |
| `twitter_followers` | X API v2 `public_metrics` |

Cache TTL: `DIOSCURI_SOCIAL_CACHE_SEC` (default 300s). Alien Monitor shows metrics from cache immediately on node click — no live API call from the graph.

Optional env: `TWITTER_BEARER_TOKEN`, `TWITTER_USER_ID`, `TELEGRAM_CHANNEL_ID`.

## HELIOS syndication (optional)

When `HELIOS_SYNDICATION=1`, DIOSCURI appends `release-short` jobs to `HELIOS_QUEUE_PATH` on each new GitHub release (fail-soft). See [helios-integration.md](./helios-integration.md).

## MNEMOSYNE ↔ GitHub

The twins sync READMEs and releases from **public GitHub repos** (`githubOwner: alexar76`). DIOSCURI does not need its own repo in the KB list to answer ecosystem questions — but publishing `alexar76/dioscuri` lets the twins document themselves.

## Co-authors & collaborators

Satellite pushes squash to a **single human-authored commit** (`sanitize_git_commit_meta.py` strips `Co-Authored-By` and AI tool trailers). After push, `prune_github_collaborators.py` removes bot/cursor/copilot collaborators from the repo.

## Related

- [DIOSCURI README (EN)](../../dioscuri/README.md) · [RU](../../dioscuri/README-ru.md) · [ES](../../dioscuri/README-es.md)
- [Setup](../../dioscuri/docs/setup.md)
- [Ecosystem knowledge base](./knowledge-base.md)
- [Gitea publishing](../gitea-publishing.md) (internal)
