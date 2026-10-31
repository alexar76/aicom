# Работоспособность экосистемы: установки, endpoints и MCP — 28 октября 2026

> Названия компонентов приведены к текущему бренду. Имена пакетов, URL и идентификаторы в исторических данных сохранены.

Проверка начата около **19:16 МСК**. Использованы реальные опубликованные npm/PyPI-пакеты, отдельные окружения и процессы, MCP SDK 1.30.0 и локальный Docker Engine 29.2.1. Локальный checkout не подмешивался в первоначальные установки.

**Проверенные базовые MCP-сценарии работают. Найдены воспроизводимые дефекты опубликованных Oracle Gateway и METIS, а также устаревшие инструкции установки.** На момент первичной проверки исправления были только локальными. Последующий [rollout Oracle 0.3.3 и METIS 0.2.6](/Users/alex/Desktop/ai_tests/aicompany/aicom/docs/verification/oracle-metis-rollout-2026-10-28.ru.md) обновил семь production-контейнеров; публикация новых версий в PyPI ожидает доступа к токену. Ниже сохранены результаты первоначальной проверки опубликованных пакетов.

## Что действительно установлено и запущено

| Компонент | Опубликованная версия | Фактическая проверка | Результат |
| --- | --- | --- | --- |
| WARDEN | npm 0.22.2 | MCP: 9 tools; canonicalize, benign/poisoned scan, правила; wrap исполняет `add(2,3)=5`, блокирует drift и poisoning до исполнения | PASS |
| ARGUS | scoped 0.3.3; alias 0.3.1 | MCP: 3 tools; status/capabilities; `argus_ask` через локальный mock LLM, ошибочный ввод без запроса модели | PASS в проверенном режиме; alias устарел |
| TypeScript SDK | @aimarket/agent 0.3.0 | CJS/ESM, discovery mapping, Ed25519 и отказ при подмене | PASS |
| Shared MCP Gateway | aimarket-mcp 0.6.4 | MCP: 6 tools; fetch нашего llms.txt, поиск Hub; loopback SSRF-адрес отклонён | PASS |
| HISTOR | aimarket-histor 0.5.0 | MCP: 3 tools; локальный log/check, неправильные аргументы отклонены; crawler не запускался | PASS |
| Hub | aimarket-hub 3.16.0 | MCP: 8 tools; локальные search и бесплатный ping invoke в отдельной базе | PASS |
| Python Agent | aimarket-agent 2.6.0 | CLI help и настоящий read-only поиск публичного Hub | PASS; это клиент, не отдельный MCP-сервер |
| METIS | aimarket-metis 0.2.5 | HTTP health/metrics/OpenAPI/models; синтетический ключ и отказы 401 | HTTP PASS; опубликованный benchmark CLI сломан |
| MCP Packager | 2.1.2 | MCP: 3 tools; генерация пакета, Dockerfile и client config | PASS |
| Oracle Gateway | 0.3.2 | MCP: 36 tools; каталог, отказ без провайдера, положительный MCP→локальный HTTP маршрут | Базовый протокол PASS; бюджет и routing имеют дефекты ниже |
| Все 15 protocol plugins | версии из PyPI | Совместная установка, загрузка всех entrypoints, совпадение class/distribution versions, проверка зависимостей | PASS установки/импорта, не всех финансовых операций |

Для npm использованы отдельные prefix/cache и отключены install scripts. Python — отдельные venv на 3.11.15. Серверам не передавались пользовательские API-ключи, кошельки, Telegram/Discord tokens или реальные MCP-конфиги. Mock-провайдеры и синтетические состояния находились внутри стенда.

[npm: команды и результаты](../../artifacts/system-verification-2026-10-28/npm/summary.md), [Python: матрица установок](../../artifacts/system-verification-2026-10-28/python/verification-matrix.json), [плагины и контейнер](../../artifacts/system-verification-2026-10-28/install-schemes/summary.md).

Проверены и точные latest-pins официального MCP Registry, которые отстают от npm/PyPI: **WARDEN0.21.0** и **Gateway0.4.0** установлены отдельно и проходят handshake/list и безопасные проверки. У Gateway0.4.0 пять имён с суффиксом `_tool` и нет `market_status`; это другой интерфейс, чем шесть инструментов0.6.4. Реестр не обновлялся. [WARDEN из реестровой схемы](../../artifacts/system-verification-2026-10-28/npm/warden-registry-stdio.json), [Gateway из реестровой схемы](../../artifacts/system-verification-2026-10-28/python/gateway-registry-0.4.0/summary.json).

## Live endpoints и настоящие MCP-вызовы

Первый проход охватил **96 URL**: 58 страниц, 24 JSON/health/API, девять предполагаемых OpenAPI URL, три MCP info URL и два namespace официального реестра. После уточнения TLS-клиента получены 92 ответа200, два404, один401 и один405. Это транспортные результаты, не 96 успешных сквозных сценариев.

Дополнительно прочитано содержимое **14 health-ответов**: Factory, три Hub, GAIA, HISTOR, METIS, SYMMARTYS, HESTIA, LOGOS, MOMUS, BASANOS, Signal Hunt и Monitor. Они сообщают `ok/status=ok`; Signal Hunt видит свой Hub, MOMUS видит провайдера. Основной Hub сообщает payment_ready=true, два вспомогательных — false; это конфигурация, а не тест платежа. Версии live сервисов записаны отдельно от версий установленных пакетов: например, METIS live0.2.2, HISTOR live0.4.2, Hub live3.16.0.

Через настоящий MCP SDK успешно выполнены `initialize → initialized → tools/list` на **семи опубликованных endpoints**:

- `https://modelmarket.dev/mcp` и совместимый `/ai-market/mcp`;
- `/tools/mcp/security`, `/domains`, `/emporion`, `/weather` на modelmarket.dev;
- `https://hub.attestedmemory.net/mcp`.

На доступных интерфейсах прошли read-only `market_search` и `tool_list_cost`. Затем проверены результаты:

| Вызов | Наблюдение |
| --- | --- |
| Hub → GAIA `gaia.place.resolve@v1`, Kraków/PL | Город найден; `max_price_usd=0`, квитанция получена |
| SYMMARTYS `business_days`, DE, 28 октября +2 рабочих дня | Возвращено 30 октября |
| SYMMARTYS с `date=not-a-date` | Корректный отказ, результат не придуман |
| Domains `domain_quote(example.com)` | available=false, demo; регистрации или покупки не было |
| Weather, координаты Кракова | Отказ: нет live relay в радиусе75км; ближайшая Варшава примерно252км |
| Weather, координаты варшавского relay | Живое чтение получено, с источником и аттестацией |

У трёх полученных квитанций проверены подписи по опубликованным ключам фактических издателей: GAIA и SYMMARTYS — Ed25519+ML-DSA-65, Domains — Ed25519. Изменение цены отвергается. Первоначально доменная квитанция не совпала с ключами трёх других хабов; после определения её `source_hub=domains.modelmarket.dev` она успешно проверена по ключу правильного провайдера. Это не дефект подписи.

[SDK-сессии](../../artifacts/system-verification-2026-10-28/live/remote-mcp-results.json), [функциональные вызовы](../../artifacts/system-verification-2026-10-28/live/remote-mcp-functional.json), [контроль погоды](../../artifacts/system-verification-2026-10-28/live/weather-coverage-control.json), [квитанции GAIA/SYMMARTYS](../../artifacts/system-verification-2026-10-28/live/receipt-verification.json), [доменная квитанция по правильному ключу](../../artifacts/system-verification-2026-10-28/live/domains-receipt-verification.json).

## Найденные дефекты и локальные исправления

### Oracle Gateway 0.3.2

В реальном stdio-процессе опубликованного пакета, подключённом к loopback mock-Hub, воспроизведены:

1. В исходящий Hub POST не передавался атомарный `max_price_usd` до выполнения/оплаты.
2. Явный ответ `price_usd=0` подменялся ненулевым hint.
3. Фактическая цена0.0042 принималась при hard cap0.004, поскольку укладывалась в отдельный tolerance.
4. `source_hub=mcp-oracle-gateway` был тегом вместо допустимого источника маршрутизации. Live запрос с нулевой ценовой границей получил404 `Peer hub not found`; источник из реального каталога получил409 `price_limit_exceeded` до платной работы.

Локально исправлены [gateway_core.py](/Users/alex/Desktop/ai_tests/aicompany/aicom/plugins/aimarket-oracle-gateway/aimarket_oracle_gateway/gateway_core.py) и тесты: исходящий ceiling, сохранение нуля, отдельный actual cap, default source `local` и чтение `AIMARKET_SOURCE_HUB`. Для федерации документировано копирование source из выбранного результата поиска. Финальные пять MCP→mock HTTP сценариев и **55 целевых тестов** проходят.

Границы: direct-oracle не получил атомарный pre-payment контракт, которого его API не обещает; постпроверка не отменяет уже сделанную работу. Строгий quote/tolerance ceiling может отказать при округлении all-in цены Hub до цента. Успешный paid fulfillment, reconciliation этой разницы и реальные платёжные каналы не проверялись. Публичный пакет0.3.2 по-прежнему содержит исходные дефекты.

[До исправления](../../artifacts/system-verification-2026-10-28/install-schemes/oracle-wire-published.json), [после локального исправления](../../artifacts/system-verification-2026-10-28/install-schemes/oracle-wire-local-fixed.json), [live routing без расходов](../../artifacts/system-verification-2026-10-28/install-schemes/live-zero-price-routing.json).

### METIS 0.2.5

Чистая установка обнаружила `ModuleNotFoundError: benchmarks` у опубликованного `metis-benchmark`. После исправления упаковки обнаружился ещё один непубликуемый импорт `tests.support.mock_provider`.

Локально в wheel включены существующий benchmark package и четыре JSONL-датасета; offline provider перенесён в `metis.models.mock_provider`, а старый тестовый импорт оставлен совместимым. Explicit `allow_test_provider` gate сохранён. Также исправлена подсказка установки HTTP extra: `aimarket-metis[distributed]` вместо постороннего `metis[distributed]`.

Исправленный wheel установлен в новый venv отдельно от исходного сломанного пакета: CLI запускается, datasets доступны, **20 offline executions без ошибок**, **26 существующих тестов PASS**. Это проверка установки и проводки, не оценка качества реальной LLM. Исправленный release не публиковался.

[Локальный wheel и результаты](../../artifacts/system-verification-2026-10-28/python/metis-patched/wheel-regression.json), [регрессионные тесты](../../artifacts/system-verification-2026-10-28/python/metis-patched/source-regression.json).

### Инструкции установки

Локально исправлены основные инструкции ARGUS: legacy `argus-warden@latest` устанавливал0.3.1 с WARDEN0.4.0, тогда как проверенный scoped пакет0.3.3 содержит WARDEN0.8.2. В TypeScript SDK исправлены published version/import quickstart. В plugin README/install убраны устаревшие pending/source-only утверждения: все15 уже опубликованы. Oracle запуск заменён на существующий console entrypoint.

Текущая зависимость ARGUS от WARDEN0.8.2 не обновлялась до0.22.2 без отдельной совместимости. Локальная версия Hub3.16.1 ещё отсутствует в PyPI; документированная unversioned установка успешно ставит3.16.0. Это зафиксировано как разница source/published, а не сломанная базовая установка.

## Контейнеры, схемы и ограничения

- Dockerfile, реально возвращённый установленным Packager2.1.2, собран в локальный образ. Контекст — один Dockerfile, без монорепо и секретов. Контейнер с отключённой сетью, read-only root, снятыми capabilities и ограниченными ресурсами проходит MCP handshake/list и отклоняет ошибочный ввод. Контейнер удалён, тестовый image сохранён.
- Core и everything Compose проходят **статическую** валидацию без разрешения env-файлов. Стек из40контейнеров не поднимался; LLM-ключи и кошельки не использовались.
- Проверены37 npm schema checks,17 Python MCP input schemas и схемы Packager/Oracle. Это не полный перебор всех возможных входов.
- BASANOS намеренно отключает OpenAPI; HISTOR публикует его по документированному `/api/openapi.json`, который ответил200 и содержит40paths. Корневые `/openapi.json` у METIS/GAIA/LOGOS/MOMUS отдают HTML через edge; их нельзя выдавать за проверенную публичную JSON-схему.
- Live METIS `/v1/models` без ключа отвечает401. Локальный установленный HTTP-сервер отдельно проверен с правильным и неправильным синтетическими ключами. Коммерческая генерация модели не выполнялась.
- Claude Desktop/Cursor UI не запускались; проверены protocol/client-config generation и реальные SDK/stdio-подключения. Исторические версии каждого пакета, все финансовые операции, полный автономный Factory pipeline и все провайдерские функции не проверялись.

В рамках этой первоначальной проверки публикаций, deploy, GitHub writes, изменений аккаунтов, реальных платежей и сообщений не выполнялось. Последующий deployment описан в отдельном отчёте выше. Уже имевшиеся и параллельные изменения PingBlip не затрагивались. [Общий индекс evidence](../../artifacts/system-verification-2026-10-28/verification-index.json) связывает сценарии с воспроизводителями и выводами.
