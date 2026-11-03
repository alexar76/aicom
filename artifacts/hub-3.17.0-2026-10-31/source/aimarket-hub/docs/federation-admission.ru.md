# Допуск в федерацию — sandbox-assay, затем автоматический индекс

> **English:** [federation-admission.md](./federation-admission.md) · **Español:** [federation-admission.es.md](./federation-admission.es.md) · **Français:** [federation-admission.fr.md](./federation-admission.fr.md) · **中文:** [federation-admission.zh.md](./federation-admission.zh.md)
>
> Код: [`federation_assay.py`](../aimarket_hub/federation_assay.py) · [`api.py`](../aimarket_hub/api.py) · [`crawler.py`](../aimarket_hub/crawler.py) · [`config.py`](../aimarket_hub/config.py)
>
> Путь вступления: [`docs/join-the-federation.ru.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.ru.md)

---

## Зачем это есть

Стук (`POST /federation/announce` или входящий `X-AIMarket-Crawler`) — это **наблюдение**.
Он не должен индексировать каталог: это была бы инъекция манифеста. Раньше из карантина
выводил только человек на `/operator`, кликая Approve на каждый новый хаб.

Оператор не будет сидеть на этой очереди. Поэтому допуск после карантина **автоматический**,
но скорит **то, что реально отработало в песочнице**, а не текст из `.well-known`.

Аналог на фабрике (в хаб фабрику не импортируем):

| Фабрика | Хаб федерации |
|---------|----------------|
| `product_automated_verify` — скорить тесты/артефакты, не витрину | `analyze_sandbox_output` — safety gate + schema + без частных IP |
| `docs/sandbox-trust-model.md` — мягкая изоляция, не гипервизор | Ограниченный HTTP POST на *их* публичный invoke (их код локально не исполняем) |
| `agents/surrogate_reviewer.py` — JSON approve/block | Опциональный `AIMARKET_FEDERATION_JUDGE_URL` — **только вето**, evidence без `name`/`description` |

LLM, которой дали `name` / `description`, поставит штамп на гладкий маркетинг. Этот путь закрыт.

## Конвейер

```text
стук → pending (ничего не индексируется)
    → жёсткие проверки (SSRF / schema / Ed25519 / same-origin)
    → sandbox POST до 3 публичных бесплатных capability (побеждает первая с подписанной квитанцией)
    → бесплатного нет? стучимся в самую дешёвую платную и читаем её 402
    → анализ живого payload
    → опциональное LLM-вето по evidence (без брошюры)
    → pass + AUTO_ADMIT=1 → trusted + crawl
    → fail / review → остаются pending (стол оператора)
```

Запуск:

1. Фоновая задача после успешного анонса без токена (`outcome == added`).
2. Конец каждого цикла crawl, до 3 pending без терминального `pass`/`fail`.
3. Admin `POST /ai-market/v2/federation/assay`.

## Две породы улик

**Работа, которая выполнилась** — бесплатная capability ответила подписанной квитанцией.
Самое сильное, что пир может показать; ассей пробует это первым.

**Платёжная дверь, которая отвечает** — если бесплатного нет, стучимся в самую дешёвую
платную **не платя**. 402, называющий рельс и получателя и котирующий ту же цену, что и
каталог пира, — это улика: эндпоинт жив, говорит на протоколе и держит собственный прайс.
Ничего не покупается, платёжные заголовки не отправляются никогда.

Почти вся эта федерация продаёт всё, что имеет, поэтому при правиле «только бесплатное»
такие хабы не могли предъявить улик вообще и вечно висели на столе оператора — SKOPOS, ATLAS
и собственная фабрика проекта в их числе. Досье помнит породу улики
(`sandbox.evidence_kind`), так что `pass` по платёжной двери не спутать с выполненной работой.

Стук показывает две вещи, которые брошюра прячет: 402 с ценой, отличной от каталога
(`sandbox_price_matches`), и платную capability, отдающую 200 на неоплаченный invoke
(`sandbox_price_enforced`). И то, и другое — `review`.

## Вердикты

| Вердикт | Смысл | Автодопуск |
|---------|---------|------------|
| `pass` | Жёсткие проверки + подписанная квитанция + анализ не false + судья не false | да, если `AIMARKET_FEDERATION_AUTO_ADMIT=1` (дефолт) |
| `review` | Нечего предложить публично, 402 без платёжных инструкций, цена в 402 расходится с каталогом, платная capability отдана без оплаты, анализ fail или судья `block` | нет |
| `fail` | SSRF, схема, плохая подпись, несовпадение ключа | нет |

No `AIMARKET_FEDERATION_JUDGE_KEY` / `OPENROUTER_API_KEY` → судья не вызывается и
**автодопуск не работает**. Оператор жмёт Approve на `/operator`. На проде модель —
MiniMax (`minimax/minimax-m3`) через OpenRouter, тот же токен, что у остальных сервисов.

## Переменные

| Variable | Default | Эффект |
|----------|---------|--------|
| `AIMARKET_FEDERATION_ASSAY` | `1` | Мастер-переключатель |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | Прогнать до 3 публичных бесплатных capability |
| `AIMARKET_FEDERATION_ASSAY_TIMEOUT_S` | `8` | Таймаут sandbox POST |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | `pass` → `trusted` + crawl. Алиас: `AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | пусто | OpenAI-compatible chat POST |
| `AIMARKET_FEDERATION_JUDGE_KEY` | пусто | Bearer для судьи |
| `AIMARKET_FEDERATION_JUDGE_MODEL` | `gpt-4o-mini` | id модели |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | Ошибка судьи блокирует допуск |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | Ручной Approve без последнего `pass` отказывается |
| `AIMARKET_FEDERATION_ASSAY_LLM` | игнорируется | Не судья брошюры |

## Стол оператора

`/operator` — путь **исключений**: только платные хабы, вето, dismiss. Это не очередь
штатного допуска.

## Пределы изоляции

Хаб не гоняет код пира в локальном venv или gVisor. Он POST-ит на их публичный invoke
с ограничением тела и размера (`262_144`), причём предел держится **на потоке**: недопущенный
пир не заставит хаб набрать в память ответ, который всё равно будет отвергнут. Это **мягкая**
изоляция того же класса, что preview на фабрике, не мультиарендный гипервизор. SSRF-стражи
по-прежнему режут частные и link-local цели.

Куда именно стучаться, решает [`federation_transport`](../aimarket_hub/federation_transport.py) —
то же правило, что и у маршрутизируемых invoke: пир, объявивший себя хабом (`hub_version` или
`v2` в `protocol_versions`), зондируется по своему `/ai-market/v2/invoke`, потому что
рекламируемый им `mcp_endpoint` говорит на MCP JSON-RPC и на конверт AI-Market отвечает ошибкой.
Голый сервис-возможность сохраняет свой объявленный эндпоинт.
