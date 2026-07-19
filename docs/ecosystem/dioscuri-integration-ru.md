# DIOSCURI — интеграция в экосистему

Как **DIOSCURI** (близнецы-сообщество) вписывается в стек AICOM вместе с GitHub, Gitea и Alien Monitor.

**Лендинг:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **English:** [dioscuri-integration.md](./dioscuri-integration.md) · **Español:** [dioscuri-integration-es.md](./dioscuri-integration-es.md)

## Плоскости

| Плоскость | Роль |
|-----------|------|
| **Monorepo** `dioscuri/` | Источник правды |
| **GitHub** `alexar76/dioscuri` | Публичное зеркало — доки, CI, self-host |
| **Gitea#2** `alexar76/dioscuri` | Приватное ops-зеркало (rsync) |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | Узел графа — опрос `GET /health`, KB + статус адаптеров |

Публикация на GitHub (без секретов):

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

## Секреты — никогда в git

| Файл | Назначение |
|------|------------|
| `.env` | Токены ботов, LLM-ключи |
| `dioscuri.config.json` | Несекретные настройки (ссылки, темы, модерация) |

Оба **исключены** из rsync (`satellite-map.yaml`) и блокируются `scripts/verify_mirror_secrets.sh`.

## Ссылки сообщества (Telegram + Discord)

**Продакшен (канон — README и лендинги):**

| Ключ | URL |
|------|-----|
| Telegram-бот (Castor — Q&A) | https://t.me/next_agent_market_bot |
| Telegram-канал (Castor — новости) | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

Приглашения в `dioscuri.config.json`:

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT"
}
```

Alien Monitor (опционально, для панели графа):

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790
```

## Узел Alien Monitor

**DIOSCURI** — северо-запад от client shelf. Опрос `GET {ALIEN_DIOSCURI_URL}/health`. Серый = недоступен; золотой пульс = хотя бы один близнец активен или KB заполнена.

## Связанные документы

- [DIOSCURI README (RU)](../../dioscuri/README-ru.md) · [README (ES)](../../dioscuri/README-es.md)
- [База знаний экосистемы (RU)](./knowledge-base-ru.md)
- [Setup](../../dioscuri/docs/setup.md)
