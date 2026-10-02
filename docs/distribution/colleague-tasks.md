# Задачи для коллеги

Всё, что нельзя сделать из кода: нужен вход в аккаунт, заполнение формы или решение человека. Каждый пункт — что сделать, где и с какими данными. Ключей и паролей здесь нет и не будет. Ключ, если он нужен, владелец смотрит у себя в терминале.

Обновлено: 2026-10-02.

---

## Сделать сейчас

### 1. Circle Agent Marketplace — подать наши платные API

**Что это.** Каталог Circle: сервисы с оплатой в USDC по x402. Агенты находят их через сайт `agents.circle.com/services` и через API. Каждую заявку проверяют вручную, кошелёк получателя проверяют по санкционным спискам.

**Где.** Форма: https://forms.gle/7YFzvdmMcn1JH5tF6

**Что вписать:**

| Поле | Значение |
|---|---|
| Название | `AIMarket` |
| Адреса сервисов | `https://modelmarket.dev/x402/weather-now`, `https://modelmarket.dev/x402/air-quality-now`, `https://modelmarket.dev/x402/nearby-sensors`, `https://modelmarket.dev/x402/fair-random`, `https://modelmarket.dev/x402/histor-check`, `https://modelmarket.dev/x402/warden-scan` |
| OpenAPI | `https://modelmarket.dev/x402/openapi.json` |
| Сеть и токен | Base mainnet (eip155:8453), USDC; facilitator — Coinbase CDP |
| Кошелёк получателя | `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` |
| Цены | $0.001 — погода, качество воздуха, HISTOR, WARDEN; $0.006 — честный рандом; $0.03 — ближайшие датчики |
| Категории | Data (погода, воздух, датчики), Utilities (проверяемая случайность), Security (проверки MCP) |
| Сайт | https://modelmarket.dev |

**Описание** (вставить как есть, по-английски):

> Signed real-world data and verifiable computation per call over x402: current weather and air quality at a place, the nearest live public sensors, ECVRF fair randomness with an offline-checkable proof, and two MCP security checks (HISTOR transparency log, WARDEN tool-definition scan). Every data result carries a signed receipt.

**Если форма принимает только один адрес**, вписать `https://modelmarket.dev/x402/weather-now`, а остальные пять перечислить в описании.

**Перед отправкой проверить:** открыть `https://modelmarket.dev/x402/openapi.json` в браузере — должен открыться JSON с шестью путями.

---

### 2. Smithery — подать хаб как MCP-сервер

**Что это.** Крупный каталог MCP-серверов. Через него пользователи подключают серверы к Claude, Cursor и другим клиентам. Нас там пока нет: проверено 2 октября.

**Шаги:**
1. Зайти на https://smithery.ai через GitHub-аккаунт `alexar76`.
2. Нажать **Publish** (или открыть smithery.ai/new), вкладка **URL**.
3. Адрес: `https://modelmarket.dev/mcp`
4. Имя: `@alexar76/aimarket-hub`
5. Пройти шаги до конца. Smithery сам просканирует сервер: ключи и настройки не нужны.

**Описание** (если спросят):

> Live, signed real-world data and verifiable computation sold per call by independent providers — weather, air quality, nearby sensors, fair randomness and a searchable market of more. The first calls per caller are free; every result carries a signed receipt.

**Как проверить, что всё прошло.** На странице сервера в Smithery должны появиться инструменты `weather_now`, `air_quality_now`, `nearby_sensors`, `fair_random`, `market_search`, `market_invoke`. Если сканирование не прошло, пришлите скриншот, разберёмся.

---

## Следить, по ответам

### 3. Заявки на рассмотрении

Раз в несколько дней открыть и посмотреть, нет ли комментариев от проверяющих. На вопросы отвечать, а если вопрос технический, переслать его нам.

| Где | Что |
|---|---|
| https://github.com/docker/mcp-registry/pull/5365 | Хаб в каталоге Docker MCP |
| https://github.com/docker/mcp-registry/pull/5364 | WARDEN в каталоге Docker MCP |
| https://github.com/coinbase/x402/pull/373 | Мы на сайте x402.org |
| https://github.com/xpaysh/awesome-x402/pull/1680 | Список awesome-x402 |
| https://github.com/sudeepb02/awesome-erc8004/pull/120 | Список awesome-erc8004 |
| OKX.AI, агент 14118 | Проверка в OKX. Смотреть в личном кабинете OKX (агентский кошелёк в песочнице на сервере attested) |

---

## Деньги — только по сообщению

### 4. Пополнить кошелёк отзывов WARDEN

Когда в Telegram (@Argis3Bot) придёт сообщение «пора пополнить», перевести **ETH в сети Base** на адрес:

`0x564bE09d06117A106ECC006a19b67768cBd91666`

Сумма — **0.0005 ETH**, это примерно 400 транзакций. Только сеть **Base**: перевод в Ethereum mainnet или другую сеть до кошелька не дойдёт.

### 5. Пополнить кошелёк газа хаба

Этот кошелёк платит газ за покупателей, когда хаб спонсирует их платежи. Если хаб в сводке пишет, что спонсорство кончилось (`gas_sponsor_daily_budget_exhausted` или пустой баланс), перевести **0.0005 ETH в сети Base** на адрес:

`0x663E0C31925EAd877fD9414C2e1862fa50b2650b`

---

## Решения, которые ждут владельца

### 6. Агенты, отложенные WARDEN

Если в сводке Telegram есть строка «ждут твоего решения», значит, WARDEN нашёл у агента что-то блокирующее. Отзыв этому агенту автоматически не публикуется. Владелец решает по каждому:
- оставить без отзыва;
- опубликовать факт со ссылкой на отчёт.

Сейчас уже решено: ENS Registration Agent (#19151) — без отзыва.

### 7. Гранты

Отложено владельцем (2026-10-02). Когда вернёмся: нужны ответы, кто получатель (физлицо или компания, страна) и чьё имя и контакт указывать.

---

## Как это всё проверить самому

```bash
deploy/erc-8004/warden-feedback --status   # отзывы WARDEN: последний запуск, баланс кошелька
```

Эта команда работает с Mac владельца или любой машины с доступом к admin-vps по ssh. Сводка отзывов также открыта по ссылке: https://histor.modelmarket.dev/.well-known/erc-8004/feedback/last-run.json
