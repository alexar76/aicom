# Проверки по внешним сигналам от 25 ноября 2026

## Attested Memory

Локальная страница `/developers` использует опубликованный Python-клиент `attested-memory==0.3.0`. Тест берёт пример прямо из HTML, загружает wheel с проверенной SHA-256 и выполняет `share → read → revoke → HTTP 403` через локальные Personal API, Gateway и Memory Market. Ссылка на пример и копирование кода проверены в Chrome при ширине 390 и 1280 пикселей. [Страница в репозитории](../../../saas-landing/developers.html) · [PyPI](https://pypi.org/project/attested-memory/0.3.0/) · [тест примера](test_attested_quickstart.py)

После разбора Atlas ревизии `25d6b1a` публичный репозиторий обновился до `84e7057` в 16:20 UTC. В новой ревизии сверены побайтово с локальными копиями тест, команда `reconcile_provenance` и таймер. Тест поднимает локальный журнал и проверяет, что сохранённая в Memory Market квитанция выявляет сдвиг головы журнала. Тесты также проверяют привязку к владельцу, изменение квитанции и создание записи после появления квитанции об оплате. Это конкретная ревизия и тест для следующего разбора Atlas. [Публичная ревизия](https://github.com/alexar76/attested-memory/commit/84e7057bd2ed88344d99066f1827933a5cb6cda5) · [публичный тест](https://github.com/alexar76/attested-memory/blob/84e7057bd2ed88344d99066f1827933a5cb6cda5/tests/test_provenance_crosscheck.py) · [SHA-256 файлов](attested-public-pin.json)

Из корня `aicom`, с зависимостями Python-проектов в `.venv`:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  artifacts/external-mentions-2026-11-25/implementation/test_attested_quickstart.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 AIFACTORY_DEV=1 \
  PYTHONPATH=attested/attested-memory-hub/provenance-ledger/src:attested/attested-memory-hub/memory-market/src \
  .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  attested/tests/test_actor_proxy_flow.py \
  attested/attested-memory-hub/tests/test_provenance_crosscheck.py
```

Прошли тест точного примера и восемь интеграционных тестов. Тест примера использует wheel из локальной папки релиза. Если wheel отсутствует в рабочей копии, скачайте wheel той же версии с PyPI в папку релиза. Тест самостоятельно проверит SHA-256. [Локальная папка релиза](../../attested-memory-0.3.0-release-2026-11-25/README.md)

## ReloadPi

В сохранённых квитанциях Base есть один платёж и три возврата по 1,61 USDC. Подтвердились адреса, сумма, направление и время включения каждого перевода в блок. Сумма трёх возвратов — 4,83 USDC. Запрос к документированному `GET /api/catalog/orders?txHash=…` по опубликованному платежу дал HTTP 200 и `found: false`. Связь между этим платежом и конкретным возвратом ждёт строки статуса от оператора. [Полевой отчёт](https://github.com/sF1nX/x402-signals/issues/1) · [Квитанции, блоки и результат поиска](reloadpi-base-evidence.json) · [Черновик ответа Cross](../../external-mentions-2026-11-24/reply-reloadpi-2026-11-25.md)

```sh
python3 artifacts/external-mentions-2026-11-25/implementation/check_reloadpi_transfers.py
```

Проверка работает офлайн по сохранённым RPC-ответам. Если оператор предоставит запись по опубликованному платежу, её можно передать через `--operator-order FILE`. JSON принимает `order_id` (можно редактированный стабильный идентификатор), `state` со значением `FULFILLMENT_FAILED`, `failed_at` с часовой зоной, `payment_tx_hash` и `refund_tx_hash`. Скрипт сверяет хеши, направление, сумму и попадание отметки времени между блоком оплаты и блоком возврата. Источник перехода состояния в этой проверке — запись оператора.

## HISTOR и mcp-rc-check

В наблюдении HISTOR №157 от 24 сентября 2026 у четырёх из семи инструментов изменились только описания. Для фикстуры оставлены четыре изменённых инструмента и неизменный контроль `list_zones`. Два других неизменных инструмента удалены из обеих копий. Исходные digest относятся к полным спискам. Комментарий OWASP ссылается на DOI архива без номера наблюдения. Здесь указан собственный проверяемый номер адаптированного примера. [Архив HISTOR, CC BY 4.0](https://doi.org/10.5281/zenodo.23512760) · [OWASP #4](https://github.com/OWASP/Agentic-Evidence/issues/4#issuecomment-7109908336) · [Фикстура](histor-review-one.json)

```sh
python3 artifacts/external-mentions-2026-11-25/implementation/check_histor_partial_review.py \
  /path/to/mcp-rc-check/dist/cli.js
```

На `mcp-rc-check` 0.5.0 с коммита `a4dd460` проверено ожидаемое поведение частичного обновления lock-файла. До принятия `cheapest_window` видны четыре изменения описаний. После остаются `get_forecast`, `get_prices` и `get_renewables`. У `list_zones` сохранён исходный pin, включая `required`. Эта версия CLI отвечает `unknown option --only`. Для сборки с реализацией из #19 тот же скрипт с `--feature` вызывает нативный `surface lock --only` и проверяет тот же результат. [Задача #19](https://github.com/basitalisandhu/mcp-rc-check/issues/19) · [Проверенная ревизия](https://github.com/basitalisandhu/mcp-rc-check/tree/a4dd460b7e57e72adfafd346ba766c42120ce03e) · [Результат](histor-result.json)

## mcp-token-cost и OpenCode

README, текстовый, Markdown и HTML-отчёты и калькулятор на пяти языках теперь называют свою метрику стоимостью полного списка. Прогноз цены относится к запросам, которые отправляют этот список. OpenCode 2.4.1 проверен с одним синтетическим MCP-сервером и локальным OpenAI-совместимым провайдером. Замер сделан для первого модельного запроса с инструментами, без вызовов инструментов. [Документация OpenCode](https://opencode.ai/docs/mcp-servers/) · [OpenCode #58716](https://github.com/anomalyco/opencode/issues/58716) · [Трасса](opencode-result.json)

| Метрика | Прямое подключение | Code Mode |
|---|---:|---:|
| Полный MCP-каталог, `o200k_base` | 634 | 634 |
| Определения тестового MCP в `tools` | 7 | 0 |
| Токены этих определений в `tools` | 648 | 0 |
| Токены всех определений в `tools`, включая встроенные | 4 305 | 3 657 |

При прямом подключении клиент добавляет к именам инструментов префикс сервера. Поэтому 648 токенов на стороне клиента отличаются от 634 в исходном списке. Для числа 3 657 посчитаны определения в `tools`, включая `execute`. Системные сообщения, содержимое результатов вызовов и обёртка провайдера в этот подсчёт не входят. Локальный провайдер вернул фиксированный usage **1 234 входных / 7 выходных** в обоих запросах. Столько же передал OpenCode в событии `step_finish`. Эти два числа проверяют передачу usage. Реальный расход провайдера в эксперименте не измерялся.

```sh
python3 artifacts/external-mentions-2026-11-25/implementation/trace_opencode.py \
  /path/to/opencode
```

Для повтора нужны OpenCode 2.4.1, Python 3.9+, Node и установленные зависимости `mcp-token-cost`. Провайдер слушает только `127.0.0.1`. Прошли 40 тестов `mcp-token-cost` и 87 тестов `okx-a2mcp`. [Релиз OpenCode 2.4.1](https://github.com/anomalyco/opencode/releases/tag/v2.4.1)
