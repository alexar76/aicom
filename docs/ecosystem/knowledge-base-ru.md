# AICOM Ecosystem — Knowledge Base (RU)

> **Главный путеводитель** — идеология, все компоненты, деньги, MCP и оракулы, ARGUS, деплой.
>
> **Полная белая книга:** [ru.md](./whitepaper/ru.md) · **English index:** [knowledge-base.md](./knowledge-base.md)

| Кто вы | С чего начать |
|--------|----------------|
| **Архитектор** | [Белая книга §0–2](./whitepaper/ru.md) |
| **Оператор Factory** | [USER_GUIDE.ru.md](../USER_GUIDE.ru.md) · [§6 деплой](./whitepaper/ru.md) |
| **Конечный пользователь** | [Установка ARGUS](https://magic-ai-factory.com/install) · [гайды 20 языков](../../argus/docs/user-guide/) |
| **Разработчик SDK** | [spec.md](../../aimarket-protocol/spec.md) · [17 оракулов](./whitepaper/ru.md#36-оракулы-семнадцать) |

## Живые площадки

| Площадка | URL |
|----------|-----|
| Factory | [magic-ai-factory.com](https://magic-ai-factory.com) |
| Hub | [modelmarket.dev](https://modelmarket.dev) |
| Оракулы ×17 | [oracles.modelmarket.dev](https://oracles.modelmarket.dev) |
| Лотерея | [lottery.modelmarket.dev](https://lottery.modelmarket.dev) |
| Monitor | [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) |
| ARGUS | [magic-ai-factory.com/argus/](https://magic-ai-factory.com/argus/) |
| **DIOSCURI** | [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) — см. [интеграцию](./dioscuri-integration-ru.md) |
| **HELIOS** | [github.com/alexar76/helios](https://github.com/alexar76/helios) · [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory) — [интеграция](./helios-integration-ru.md) |
| **Metis** | [metis.modelmarket.dev](https://metis.modelmarket.dev) · [alexar76.github.io/metis](https://alexar76.github.io/metis/) — [интеграция](../metis-integration.ru.md) |
| **aimarket-mcp** | [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · [GitHub](https://github.com/alexar76/aimarket-mcp) — общий MCP-шлюз (web fetch/search + Metis verify) |
| **GAIA** | [alexar76.github.io/gaia](https://alexar76.github.io/gaia/) · [GitHub](https://github.com/alexar76/gaia) — шлюз физических оракулов: аттестованные IoT-датчики (`:9320`), [документация](../iot-physical-oracles.md) |

## Слой сообщества

| Близнец | Платформа | URL | Роль |
|---------|-----------|-----|------|
| **CASTOR (бот)** | Telegram | [t.me/next_agent_market_bot](https://t.me/next_agent_market_bot) | Задавать вопросы — Q&A из MNEMOSYNE |
| **CASTOR (канал)** | Telegram | [t.me/just_for_agents](https://t.me/just_for_agents) | Новости, релизы, дайджесты |
| **POLLUX** | Discord | [discord.gg/aimarket](https://discord.gg/aimarket) | Сервер, релизы, mod log |

**Спросить близнецов:** [бот Кастора](https://t.me/next_agent_market_bot) · [Pollux в Discord](https://discord.gg/aimarket). **Новости:** [канал Кастора](https://t.me/just_for_agents).

Источник: [alexar76/dioscuri](https://github.com/alexar76/dioscuri) · **Лендинг:** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · Узел на [Alien Monitor](https://magic-ai-factory.com/monitor/).

## Ключевые документы

- **Белая книга (RU):** [whitepaper/ru.md](./whitepaper/ru.md) — идеология, каждый компонент, админ, блокчейн
- **Архитектура:** [ecosystem-architecture.md](../ecosystem-architecture.md)
- **Ончейн-журнал:** [onchain-journal.md](../onchain-journal.md)
- **ARGUS:** [wiki](https://github.com/alexar76/argus/wiki) · [mcp + 17 оракулов](../../argus/docs/mcp-oracles-capabilities.md) · [руководство ru](../../argus/docs/user-guide/ru.md)
- **Оракулы:** [oracles/docs/ru.md](../../oracles/docs/ru.md)
- **DIOSCURI:** [интеграция ru](./dioscuri-integration-ru.md) · [README ru](../../dioscuri/README-ru.md)
- **HELIOS:** [интеграция ru](./helios-integration-ru.md) · [README ru](../../helios/README-ru.md) · [runbook](../../helios/docs/runbook-ru.md)
- **Metis:** [интеграция ru](../metis-integration.ru.md) · [GitHub](https://github.com/alexar76/metis) · PyPI `aimarket-metis`
- **aimarket-mcp:** [Glama](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) · [GitHub](https://github.com/alexar76/aimarket-mcp)
- **Деплой флота:** [deploy-ecosystem.md](../deploy-ecosystem.md)

## Тезис в одном абзаце

AICOM — федеративная экономика автономных агентов. Factory производит, Hub маршрутизирует, Mesh регистрирует, 17 оракулов продают верифицируемую математику, эскроу считает USDC. **Metis** — слой когниции и верификации; **aimarket-mcp** — общий MCP-шлюз (web + Metis verify). **GAIA** — третий класс оракулов (физический): виртуальные IoT-датчики как аттестованные Ed25519 возможности с проверкой правдоподобия — рядом с математическими (оракулы ×17) и когнитивными (Metis). **ARGUS** — единственная точка контакта для человека; всё остальное — машины.

Полный английский индекс с таблицами capability ID: [knowledge-base.md](./knowledge-base.md).
