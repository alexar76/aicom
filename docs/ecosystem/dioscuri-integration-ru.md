# DIOSCURI — интеграция в экосистему

Как **DIOSCURI** (близнецы-агенты сообщества) вписывается в стек AICOM вместе с GitHub, Gitea и Alien Monitor.

**Лендинг:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **Языки:** **[EN](./dioscuri-integration.md)** · **RU** · **[ES](./dioscuri-integration-es.md)** · **[FR](./dioscuri-integration-fr.md)** · **[ZH](./dioscuri-integration-zh.md)**

## Плоскости

| Плоскость | Роль |
|-----------|------|
| **Monorepo** `dioscuri/` | Источник правды |
| **GitHub** `alexar76/dioscuri` | Публичное зеркало — доки, CI, self-host reference |
| **Gitea#2** `alexar76/dioscuri` | Приватное ops-зеркало (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Узел графа — опрашивает `GET /health`, показывает KB + статус адаптеров |

Публикация зеркала на GitHub (без секретов):

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

Синхронизация Gitea (оператор):

```bash
./scripts/mirror_to_gitea.sh dioscuri
```

## Развёртывание на oracle-хосте (78.17.126.214)

DIOSCURI работает на **oracle VPS**, а не на фабричном флоте (`5.129.212.122`). Factory Monitor опрашивает только `http://78.17.126.214:8790/health`.

**Одна команда** (mirror → Gitea#2 → ssh → git pull → compose):

```bash
./scripts/deploy_dioscuri_oracle.sh
RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh   # + первая колонка THEOROS
```

Требуется беспарольный `ssh root@78.17.126.214` (или `ssh oracle` — см. `~/.ssh/config`). Аутентификация для **git push** использует `data/secrets/git-credentials` (как и `mirror_to_gitea.sh`), а не SSH.

Ручной эквивалент на oracle после mirror:

```bash
ssh root@78.17.126.214
cd /root/dioscuri && git pull --ff-only && docker compose up -d --build
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
```

`./scripts/deploy_cognition.sh` — для **локального** стека cognition на хосте, где вы его запускаете, а не обёртка для удалённого oracle.

## Секреты — никогда в git

| Файл | Назначение |
|------|------------|
| `.env` | Токены ботов, LLM-ключи, ключи синдикации |
| `dioscuri.config.json` | Несекретные настройки (ссылки, темы, ручки модерации) |

Оба **исключены** из satellite rsync (`satellite-map.yaml` → `exclude_paths`) и блокируются `scripts/verify_mirror_secrets.sh` перед push.

Копируйте только шаблоны:

```bash
cp dioscuri/.env.example dioscuri/.env
cp dioscuri/dioscuri.config.example.json dioscuri/dioscuri.config.json
```

Заполняйте токены локально — **никогда не коммитьте**.

## Ссылки сообщества (Telegram + Discord)

**Продакшен (канон — используйте в README и лендингах):**

| Ключ | URL |
|------|-----|
| Telegram-бот (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Telegram-канал (Castor — новости) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Self-hosters задают приглашения в `dioscuri.config.json`:

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT",
  "siteUrl": "https://magic-ai-factory.com",
  "githubOrg": "https://github.com/alexar76"
}
```

Alien Monitor читает публичные ссылки из env (опционально, для панели графа):

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790          # цель опроса (сеть compose)
```

## THEOROS (колонка canon)

**THEOROS** — третья персона в том же процессе DIOSCURI, а не отдельный бот. Она публикует еженедельный **Agent Sovereignty Canon** в Discord `#the-canon` (воскресенье ~16 UTC, content kind `canon`).

| Ресурс | URL |
|--------|-----|
| Корпус + лендинг | [alexar76/theoros](https://github.com/alexar76/theoros) · [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| Дебаты | `#canon-debate` в Discord DIOSCURI |
| Конфиг | `links.theorosUrl` в `dioscuri.config.json`; добавьте `"theoros"` в `githubRepos` для граундинга MNEMOSYNE |
| Ручной запуск | `DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1` |

Castor/Pollux анонсируют главы; они **не** выдают себя за Theoros. Полное руководство: **[dioscuri/docs/theoros.md](../../dioscuri/docs/theoros.md)** (архитектура, voice charter, конфиг, чек-лист).

## Узел Alien Monitor

Узел **DIOSCURI** появляется северо-западнее client shelf. Он опрашивает:

```
GET {ALIEN_DIOSCURI_URL}/health
```

Используемые поля ответа: `adapters.telegram`, `adapters.discord`, `kb.chunks`, `kb.repos`, `uptimeSec`, `social.*` (кешированные метрики Discord/Telegram/X).

Серый = недоступен; золотой пульс = хотя бы один близнец активен или KB заполнена.

### Соцстатистика (кешированная)

`GET /health` включает `social`, когда настроены API-токены платформ:

| Поле | Источник |
|------|----------|
| `discord_members` | Discord Bot API `approximate_member_count` |
| `telegram_members` | Telegram `getChatMemberCount` |
| `twitter_followers` | X API v2 `public_metrics` |

TTL кеша: `DIOSCURI_SOCIAL_CACHE_SEC` (по умолчанию 300s). Alien Monitor показывает метрики из кеша сразу по клику на узел — без живого запроса к API из графа.

Опциональные env: `TWITTER_BEARER_TOKEN`, `TWITTER_USER_ID`, `TELEGRAM_CHANNEL_ID`.

## Синдикация HELIOS (опционально)

Когда `HELIOS_SYNDICATION=1`, DIOSCURI добавляет задания `release-short` в `HELIOS_QUEUE_PATH` при каждом новом релизе GitHub (fail-soft). См. [helios-integration.md](./helios-integration.md).

## MNEMOSYNE ↔ GitHub

Близнецы синхронизируют README и релизы из **публичных репозиториев GitHub** (`githubOwner: alexar76`). DIOSCURI не обязан иметь собственный репозиторий в списке KB, чтобы отвечать на вопросы об экосистеме, — но публикация `alexar76/dioscuri` позволяет близнецам документировать самих себя.

## Соавторы и коллабораторы

Push сателлита схлопывается в **один коммит с человеческим авторством** (`sanitize_git_commit_meta.py` убирает `Co-Authored-By` и трейлеры AI-инструментов). После push `prune_github_collaborators.py` удаляет коллабораторов bot/cursor/copilot из репозитория.

## Связанные документы

- [DIOSCURI README (EN)](../../dioscuri/README.md) · [RU](../../dioscuri/README-ru.md) · [ES](../../dioscuri/README-es.md)
- [Setup](../../dioscuri/docs/setup.md)
- [База знаний экосистемы](./knowledge-base.md)
- [Публикация в Gitea](../gitea-publishing.md) (внутреннее)
