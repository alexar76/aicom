# Pulse Terminal и HORKOS: закрытие пробелов матрицы, 10 ноября 2026

**Нового подтверждённого чужого embed, fetch client, signer client, import или независимого технического обзора не установлено.** Прежние пропущенные GitHub README-запросы восстановлены корневой веткой; оба вернули HTTP 200, total_count=0, incomplete_results=false. Покрытие дополнено точными публичными routes, конфигурацией клиента и signing protocol.

Проверка источников этой ветки: **20:04–20:06 UTC / 21:04–21:06 Europe/Amsterdam**. Выполнены 12 web-запросов. Корневая ветка предоставила четыре успешных GitHub search ответа: два README и два commit-message query. Итого **16 поисковых исполнений**. Наши десять primary GET все вернули 200; четыре root GET только переиспользованы по сохранённым путям, повторно не выполнялись и не должны второй раз суммироваться в общем охвате. Собственных вызовов `api.github.com` в этой ветке не было.

## Pulse: точный frontend и фактический data flow

Местный `apps/pulse-terminal/package.json` задаёт **`pulse-terminal` 0.1.0, `private: true`**. Поэтому опубликованный npm package и reverse-dependency graph нельзя предполагать по имени. Репозиторий — `alexar76/pulse-terminal`; продукт — ACEX Pulse Terminal, а не любой проект с названием Pulse.

Первично прочитаны [pulse.modelmarket.dev](https://pulse.modelmarket.dev/) и [factory /pulse/](https://magic-ai-factory.com/pulse/). Оба HTML объявляют `/pulse/assets/index-s972v_UH.js`. Обе реальные загрузки этого asset вернули **одинаковые 242 316 bytes**, SHA-256 **`3392d344aafd4cd94cc4a778fbc1035f188971b185d77aafbaccfea90db06931`**. Это два собственных origins с одним собранным клиентом, не два сторонних внедрения. Scripts читались как данные и не исполнялись.

[Публичный `src/lib/api.ts`](https://raw.githubusercontent.com/alexar76/pulse-terminal/main/src/lib/api.ts) побайтово совпадает с местным. Основные fingerprints:

- `VITE_PULSE_API_URL` задаёт API base; пустое значение означает тот же origin.
- Фактический fetch: `GET /api/v2/capital/pricing?chain=any|evm|solana&limit=…`, timeout 12 000 ms.
- Документированы `/api/v2/capital/pricing/stream` и `/api/v2/capital/pricing/ws`, а также Hub alias `/ai-market/v2/capital/pricing`.
- Для UNI используются `VITE_PULSE_MONITOR_API`, относительный `/pulse/api/monitor/state` и production nginx mapping на Monitor `/api/pulse/state`.
- Browser namespace: `pulse_terminal_locale`; режимы `LIVE` и `UNI`.

README говорит о WebSocket-first/SSE fallback. Текущий местный `usePricingStream.ts` явно использует **HTTP polling раз в 5 секунд** и для LIVE, и для UNI. В публичном собранном JS есть capital/pricing, polling и setInterval, но нет WebSocket и строк WS/SSE routes. Это уточнение текущего fingerprint, не проверка работоспособности каждого документированного транспорта.

Узкий [pricing GET с limit=1](https://magic-ai-factory.com/api/v2/capital/pricing?limit=1&chain=any) вернул 200, одну listing и один index, `protocol=acex`, `protocol_version=0.2.0`, `refresh_ms=5000`. `generated_at` ответа — **19:06:43 UTC**, время нашего capture — **20:04:36 UTC**; эти даты не смешиваются. Само чтение своей витрины не является внешним использованием, число возвращённых строк не является числом клиентов или сделок.

## HORKOS: публичная документация и непубличный signer API

Полные fingerprints сохранены в `fingerprints.json`: репозиторий **`alexar76/escrow-signer`**, имена **HORKOS / escrow-policy-signer**, Python namespace **`escrow_signer`**. Текущего pyproject у компонента нет; имя опубликованного PyPI package не предполагалось.

[Публичная landing](https://alexar76.github.io/escrow-signer/) — документация, а не signer endpoint. README описывает отдельный signer host и reverse SSH tunnel; Hub example — **`http://127.0.0.1:9500/sign`**. Публичный origin самого signer в исследованных источниках не установлен. Мы не пробовали его private/tunnel адреса, auth, sign, status или receipt routes.

Собственный Hub client `aimarket_hub.escrow_bridge.signer.ExternalSigner` отправляет по `AIMARKET_ESCROW_SIGNER_URL`:

- `POST` с `Authorization: Bearer …` и JSON envelope `transaction`;
- поля `to`, `data`, `chainId`, `gas`, `value`;
- ответный tx hash читает из `tx_hash` либо `transactionHash`.

Signer server задаёт точный `/sign` без redirect route; read-only интерфейсы в коде — `/health`, `/status`, `/receipt/<receipt_id>`. Это собственный wire protocol, а не свидетельство чужого signer client.

[Публичный `escrow_signer/eip712.py`](https://raw.githubusercontent.com/alexar76/escrow-signer/main/escrow_signer/eip712.py) побайтово совпал с местным. Для поиска чужого совместимого кода выделены:

- EIP-712 domain: **`AIMarketEscrow`**, version **`1`**, Base chain **8453**;
- type string: `DebitAuthorization(bytes32 channelId,address hub,address token,uint256 amount,bytes32 receiptId,uint256 nonce,uint256 deadline)`;
- call: `debitChannel(bytes32,uint256,bytes32,uint256,bytes)`, selector **`0xf7becd80`**, `value=0`;
- `hub` привязывается к собственному адресу signer, token/nonce читаются из chain state по коду;
- публичные адреса signer, escrow и USDC, compiled deployment profiles и env names сохранены отдельно с SHA местных источников.

Эти адреса и ограничения здесь атрибутированы опубликованному коду/README. Chain authorization, подписи транзакций и живое состояние signer не перепроверялись. Название профиля `independent` не устанавливает независимого оператора.

## Поиск чужого использования и новизна

Шесть web-строк для Pulse проверяли repo, оба origin, `VITE_PULSE_API_URL`, capital/pricing route и сочетание Pulse Terminal/ACEX. Шесть для HORKOS проверяли repo, product/service names, signer URL config, точный EIP-712 type и selector. Возвращались свои документы, зеркала topic/wiki, автоматическая APIs.io индексация собственного Attested Memory capital route и посторонние escrow-проекты. Они не стали внешними интеграциями только из-за похожего route или слова escrow.

Root успешно выполнил и сохранил:

| Семейство | Запрос | Результат |
|---|---|---|
| Pulse | `"github.com/alexar76/pulse-terminal" in:readme -user:alexar76` | 200; 0; incomplete=false |
| Pulse | commits: `"magic-ai-factory.com/pulse" -user:alexar76` | 200; 0; incomplete=false |
| HORKOS | `"github.com/alexar76/escrow-signer" in:readme -user:alexar76` | 200; 0; incomplete=false |
| HORKOS | commits: `"AIMARKET_ESCROW_SIGNER_URL" -user:alexar76 -author:alexar76` | 200; 0; incomplete=false |

Относительно предыдущей `component-matrix.json` новое — успешное закрытие конкретных skipped README queries, точные routes/protocol fingerprints и первичное чтение собственных surfaces. **Положительной дельты внешнего adoption нет.** README и commit-message search не являются поиском по каждому исходному файлу; нули не исключают HTTP calls из неиндексируемого или private code. Foreign candidate для чтения actual import/call не подтвердился.

## Свидетельства

`fingerprints.json` — полные идентификаторы, wire format и SHA местных источников; `coverage.json` — обе строки матрицы и shared root результаты; `findings.json` — классификация, confidence, source→target и novelty; `verification.json` — все длины/SHA, равенство двух bundle и двух public/local source pairs. Все 14 собственных/shared сохранённых тел проверены и полны. Исходные `.raw`, два HTTP index, три search ответа и `query-log.json` лежат рядом. Root API результаты хранятся в `../root/` и ссылаются оттуда.

В этом проходе не было внешних writes, auth, installs, browser script execution, signer calls, invokes, payments или запуска чужого кода. Public raw refs используют `main`; точные bytes/SHA сохранены, immutable commit resolution для нового чужого кода не потребовался, поскольку такого кандидата не найдено.
