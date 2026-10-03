# Задачи для коллеги

Всё, что нельзя сделать из кода: нужен вход в аккаунт, заполнение формы или решение человека. Каждый пункт — что сделать, где и с какими данными. Ключей и паролей здесь нет и не будет. Ключ, если он нужен, владелец смотрит у себя в терминале.

Обновлено: 2026-10-03.

---

## Сделать сейчас

### 1. Smithery — опубликовано, нужно пересканировать

Хаб опубликован: https://smithery.ai/servers/alexar76/aimarket-hub. Но при сканировании Smithery увидел 8 инструментов из 12. Не хватает четырёх главных: `weather_now`, `air_quality_now`, `nearby_sensors`, `fair_random`. Хаб показывает их, только пока может их обслужить, а в момент сканирования хабы перезапускались. Сейчас все 12 на месте.

**Что сделать:** на странице сервера в Smithery запустить повторное сканирование (**Rescan**, или в настройках сервера). Проверить, что инструментов стало 12.

WARDEN в Smithery не публикуем: он работает локально через npm, отдельного удалённого сервера у него нет.

### 2. x402-list.com — заявка на шесть платных маршрутов

Каталог x402-сервисов. Заявку проверяют автоматически (маршруты должны отвечать 402), потом вручную. Нужен e-mail — какой указать, решает владелец; на него придёт ответ о модерации.

Форма: https://x402-list.com/submit, тип **Service**.

| Поле | Что вписать |
|---|---|
| Service name | `AIMarket` |
| Service URL | `https://modelmarket.dev` |
| Website URL | `https://modelmarket.dev` |
| Email | по решению владельца |
| Category | `Data` |
| Description | `Signed real-world data and verifiable computation per call over x402 (USDC on Base): current weather and air quality at a place, the nearest live public sensors, ECVRF fair randomness with an offline-checkable proof, and two MCP security checks (HISTOR transparency log, WARDEN tool-definition scan).` |
| Endpoints | шесть строк: `/x402/weather-now`, `/x402/air-quality-now`, `/x402/nearby-sensors`, `/x402/fair-random`, `/x402/histor-check`, `/x402/warden-scan` |
| Notes | `All endpoints are POST with a JSON body; GET returns 404. Prices: $0.001 (weather, air quality, HISTOR, WARDEN), $0.006 (fair random), $0.03 (nearby sensors). OpenAPI: https://modelmarket.dev/openapi.json. Already listed on x402scan and the CDP Bazaar.` |

Если придёт отказ, что маршрут «не отвечает 402», пришлите текст: скорее всего, их проверка шлёт GET, а у нас только POST.

### 3. Cline MCP Marketplace — WARDEN

Каталог MCP-серверов внутри Cline (расширение VS Code). Подача — issue на GitHub с аккаунта `alexar76`.

1. Открыть https://github.com/cline/mcp-marketplace/issues/new/choose → шаблон **MCP Server Submission**.
2. **GitHub Repository URL:** `https://github.com/alexar76/warden`
3. **Logo Image:** перетащить файл `warden/docs/assets/logo-400.png` из репозитория (PNG 400×400).
4. **Installation Testing:** галочки ставить только после проверки. В Cline: MCP Servers → Configure → добавить
   `"warden": { "command": "npx", "args": ["-y", "@aimarket/warden"] }` и убедиться, что появились инструменты (`vet_mcp_server`, `static_scan_tools` и другие, всего 9).
5. **Additional Information:** `MCP security firewall for advertised tool definitions: static injection/exfiltration scan, signed threat feed, origin checks and pinning before a recorded allow/block verdict. Zero runtime dependencies, MIT. Also in the official MCP Registry (io.github.alexar76/warden) and on Glama.`

Очередь у них длинная, многие заявки закрывают без ответа. Это нормально, повторно не подаём.

### 4. LobeHub MCP Marketplace — WARDEN

1. Зайти на https://lobehub.com/mcp через GitHub (`alexar76`).
2. Кнопка **Submit MCP** → ссылка на репозиторий `https://github.com/alexar76/warden`.
3. Описание и логотип — те же, что для Cline (пункт 3).

---

## Следить, по ответам

### 5. Заявки на рассмотрении

Раз в несколько дней открыть и посмотреть, нет ли комментариев от проверяющих. На вопросы отвечать, а если вопрос технический, переслать его нам.

| Где | Что |
|---|---|
| https://github.com/docker/mcp-registry/pull/5365 | Хаб в каталоге Docker MCP |
| https://github.com/docker/mcp-registry/pull/5364 | WARDEN в каталоге Docker MCP |
| https://github.com/coinbase/x402/pull/373 | Мы на сайте x402.org |
| https://github.com/xpaysh/awesome-x402/pull/1680 | Список awesome-x402 |
| https://github.com/sudeepb02/awesome-erc8004/pull/120 | Список awesome-erc8004 |
| https://endpoint.x402jp.com | Сводный каталог x402. Подтягивает нас из x402scan сам, раз в сутки в 06:00 UTC. С 4 октября поиск по `modelmarket` должен находить шесть маршрутов; если нет — сообщить нам |
| OKX.AI, агент 14118 | Проверка в OKX. Смотреть в личном кабинете OKX (агентский кошелёк в песочнице на сервере attested) |

---

## Деньги — только по сообщению

### 6. Пополнить кошелёк отзывов WARDEN

Когда в Telegram (@Argis3Bot) придёт сообщение «пора пополнить», перевести **ETH в сети Base** на адрес:

`0x564bE09d06117A106ECC006a19b67768cBd91666`

Сумма — **0.0005 ETH**, это примерно 400 транзакций. Только сеть **Base**: перевод в Ethereum mainnet или другую сеть до кошелька не дойдёт.

### 7. Пополнить кошелёк газа хаба

Этот кошелёк платит газ за покупателей, когда хаб спонсирует их платежи. Если хаб в сводке пишет, что спонсорство кончилось (`gas_sponsor_daily_budget_exhausted` или пустой баланс), перевести **0.0005 ETH в сети Base** на адрес:

`0x663E0C31925EAd877fD9414C2e1862fa50b2650b`

---

## Решения, которые ждут владельца

### 8. Агенты, отложенные WARDEN

Если в сводке Telegram есть строка «ждут твоего решения», значит, WARDEN нашёл у агента что-то блокирующее. Отзыв этому агенту автоматически не публикуется. Владелец решает по каждому:
- оставить без отзыва;
- опубликовать факт со ссылкой на отчёт.

Сейчас уже решено: ENS Registration Agent (#19151) — без отзыва.

### 9. Гранты

Отложено владельцем (2026-10-02). Когда вернёмся: нужны ответы, кто получатель (физлицо или компания, страна) и чьё имя и контакт указывать.

---

## Как это всё проверить самому

```bash
deploy/erc-8004/warden-feedback --status   # отзывы WARDEN: последний запуск, баланс кошелька
```

Эта команда работает с Mac владельца или любой машины с доступом к admin-vps по ssh. Сводка отзывов также открыта по ссылке: https://histor.modelmarket.dev/.well-known/erc-8004/feedback/last-run.json

---

---

## Исключено по решению владельца

### Circle Agent Marketplace — не подаём

Решение владельца от 2026-10-03. В условиях Circle есть пункт: мы возмещаем Circle любые претензии, связанные с нашим сервисом или заявкой, включая расходы на юристов, и сумма ничем не ограничена. Форма заполнена и сохранена черновиком в Chrome, но **не отправлена**. Пока Circle не уберёт или не ограничит этот пункт, не подаём ни при каких других обстоятельствах: юрлицо или выручка ничего не меняют. Ответы для формы лежат в `submissions-2026-10.md`, раздел 6.
