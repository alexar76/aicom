# Micky Arun: текущий платёжный цикл, hold, ошибки и возврат

25 октября 2026 года. [Вопрос Micky](https://dev.to/alexar76/one-key-for-an-agents-tool-calls-a-prepaid-usdc-balance-on-an-mcp-connection-a06#comment-3h1m7) проверен по текущим исходникам AIMarket Hub, а не по исходному исследованию интереса к оплате.

**146 проверок прошли на Linux: 36 новых и 110 существующих, без failures/errors/skips.** Дополнительный денежный trace прошёл 14 шагов и пять проверок сохранения средств. Это проверка реализации prepaid credits с фиктивными деньгами; публичный wheel, работающий production-хаб и реальные переводы USDC этим прогоном не проверены. Платёжный production-код не менялся.

## Условия проверки

Зафиксированы **193 входных файла** из текущего Hub с `__version__ = 3.16.0`, тесты и экспериментальные скрипты. Manifest SHA-256: `44aa709eef00fba64a3ab55d6dc983a28056ea1ca9c165e462e0b87e7d7ebac0`. [Входной manifest](../evidence/micky-payment-lifecycle-2026-10-25/input-manifest.json) определяет проверенные байты; номер версии сам по себе не означает, что они совпадают с опубликованным пакетом.

Исполнение: `admin-vps`, Linux amd64, **Docker `runc`, `--network none`**, Python **3.11.17**, SQLite **3.46.1**. Образ закреплён digest `sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377`. Это не gVisor. Исходники монтировались read-only, базы создавались в одноразовых writable `/tmp` и `/work/data`. Зависимости установлены по hash-pinned lock; среди них `pytest==9.1.1`, `fastapi==0.141.1`, `httpx==0.28.1`, `awr==2.0.0`. [Runtime и hashes исходников](../evidence/micky-payment-lifecycle-2026-10-25/results-retry3/runtime.json), [lock](../evidence/micky-payment-lifecycle-2026-10-25/results-retry3/requirements.lock.txt).

Настоящие код приложения, миграции, SQLite ledger, проверка подписи provider и MCP/invoke handlers используются напрямую. Удалённый provider transport заменён собственной контролируемой fixture; средства созданы как явно фиктивный grant. Проверка MCP использует существующий in-memory transport приложения, применяемый и stdio; внешний клиент/сеть не тестировались.

## Полученные результаты

| Вопрос | Проверенное поведение |
| --- | --- |
| Что происходит при hold? | Сумма уходит из доступного баланса в `held` **до** вызова provider. За $0.0059 резервируются ровно 590 millicents, без округления до цента. |
| Успешный вызов | Capture переносит ровно зарезервированную фиксированную цену из held в spent. Повтор capture/release не списывает и не возвращает её второй раз. |
| Ошибка после hold | Проверенные HTTP 400/500, `ok:false`, не-JSON и неверная подпись освобождают hold без списания. При имитированной ошибке capture результат клиенту не выдаётся и hold освобождается. Это не обещание отмены внешней работы provider. |
| Нехватка денег | Отказ до provider, без нового hold и записи списания. В 12 конкурирующих запросах по $0.004 при $0.01 проходят ровно два, десять получают отказ. Проверены общая и независимые SQLite connections. |
| Гонка capture/release | На 12 независимых connections побеждает одна операция; остальные — no-op. Резерв не расходуется дважды. Ошибка SQLite на записи ledger откатывает движение целиком. |
| Изменившаяся цена | Цена $0.015 при клиентском `max_price_usd=0.01` отклоняется до hold/provider. Сумма `charged_usd:999` внутри ответа provider не увеличивает фактический capture фиксированной цены $0.01. |
| Цена по объёму результата / overage | **Не реализованы этой схемой.** Capture не принимает новую сумму, а использует amount из hold. Нет поддерживаемого процента overage или алгоритма добора после выполнения работы. |
| Таймаут после эффекта | Credit hold освобождается, но синтетический внешний эффект остаётся. Две обычные попытки дали **два эффекта**, два receipt и нулевой charge. Отсутствие ответа и release не дают exactly-once исполнения; обычный retry не передаёт provider idempotency key в проверенном пути. |
| Возраст hold | Сам ledger не освобождает hold по возрасту. Sweep обычных abandoned credit holds не трогает его ровно на 3600 секундах и освобождает после 3600 секунд; повтор sweep не возвращает сумму снова. |
| Ключ и остаток | Автоматического TTL для API key/баланса нет. Старый активный ключ работает; отключённый аккаунт отказывает до provider. Ротация ключа инвалидирует прежний ключ и сохраняет баланс. |

Три новых набора: ledger и конкуренция (`aimarket-hub/tests/test_micky_credit_lifecycle.py`), настоящий MCP/invoke путь с фиктивным provider (`aimarket-hub/tests/test_micky_mcp_payment_flow.py`), expiry и восстановление (`aimarket-hub/tests/test_micky_expiry_recovery.py`).

## Что именно означает expiry и ограничение расходов

Обычные abandoned credit holds обслуживает `sweep_stale_credit_holds` (`aimarket-hub/aimarket_hub/invoke_funding.py`). По умолчанию scheduler запускается при старте и затем каждые **120 секунд** (`AIMARKET_SUBCONTRACT_SWEEP_S`; значение ≤0 выключает его). Учитываются лимит работы sweep и состояния владельцев. Это recovery-порог, **не точный клиентский deadline** и не гарантия возврата ровно через час. Verification holds, appeal bonds и subcontract allowances имеют отдельный жизненный цикл и исключены из обычного освобождения.

Обычный bearer API key ограничен текущим балансом, но не имеет собственного лимита долларов в минуту/час. Проверенный request rate limit останавливает второй вызов до нового hold, однако ключом bucket служит IP/session identity, **не денежный бюджет конкретного API key**. Это защита от частоты запросов, а не per-key velocity control.

Для ограничения денег существующая система подписанных mandates предоставляет `perCall`, `perDay`, `total`, scope и `validUntil`. `perDay` — **календарный UTC-день**, не скользящие 24 часа; `validUntil` — исключительная граница. Включение `require_mandate=True` у владельца нужно, чтобы сырой API key не обходил mandate. Прогон включал существующие проверки per-call/day, общих лимитов родителя, конкуренции и возврата reservations, а также новую проверку границы expiry. Это не утверждение о наличии per-hour лимита или включённых mandates на production.

## Release, refund и возврат USDC — разные операции

**Release** возвращает ещё не списанный hold в доступные service credits. **`CreditsLedger.refund`** — доверенный операторский примитив обратного credit/revenue adjustment; у него нет receipt-bound replay protection или ограничения суммой отдельного capture. Два одинаковых операторских вызова добавляют кредит дважды. Это не customer endpoint и не транзакционный возврат по receipt; автоматический повтор такого операторского действия нельзя считать безопасным.

Ни одна из этих операций не отправляет USDC в кошелёк. Неиспользованный prepaid баланс остаётся обязательством оператора, видимым в `outstanding_credit_usd`. Самостоятельного вывода USDC из credit account в проверенной реализации нет. Политику возврата остатка и фактический перевод должен определить и выполнить оператор; наличие метода `refund` не доказывает cash refund и не устанавливает правовые условия.

Отдельный **transfer-funded channel ledger** не следует выдавать за prepaid credits или гарантии escrow-контракта. Проверки подтвердили: close/expiry записывают остаток как долг, `refund_executed_usd=0`. Также сохранено отдельное ограничение: просроченная по `expires_at` строка со статусом `open` принимает debit/hold до sweep; pending hold откладывает expiry. Это вторичный результат аудита другого rail, без production-исправления.

## Денежный trace и границы результата

[Trace](../evidence/micky-payment-lifecycle-2026-10-25/results-retry2/ledger-trace-retry2.json) записывает 14 состояний настоящего ledger с исходным фиктивным $1: hold $0.20 → release; hold $0.20 → capture; отказ в $0.90 при доступных $0.80; hold $0.10 → восстановление после порога. В финале `balance_mc=80000`, `held_mc=0`, `spent_mc=20000`. На каждом шаге проверены неотрицательность и сохранение `balance + held + spent + collateral = 100000` millicents. Release сохраняет операторское обязательство, а не выплачивает его.

[Команды успешного прогона](../evidence/micky-payment-lifecycle-2026-10-25/execution-retry3.json), [JUnit: 146 passed](../evidence/micky-payment-lifecycle-2026-10-25/results-retry3/junit-retry3.xml), [читаемый лог](../evidence/micky-payment-lifecycle-2026-10-25/linux-tests-retry3.log), [output manifest](../evidence/micky-payment-lifecycle-2026-10-25/output-manifest-retry3.json). Предыдущие попытки сохранены: сначала ошибка длины argv при setup, затем read-only default DB paths. Исправлялась только изоляция временных данных; frozen source не менялся. Перед [удалением временного каталога сервера](../evidence/micky-payment-lifecycle-2026-10-25/cleanup.json) сверены **193 входных и 8 выходных файлов**; `removed: true`.

Прогон не устанавливает поведение PostgreSQL, сетевого production, chain settlement, всех типов provider errors или откат сторонних эффектов. Ответ Micky подготовлен локально для просмотра владельцем и не отправлен.

## Повторная проверка перед интеграцией в main

25 октября в 14:56 МСК тот же набор заново прошёл **146/146 проверок**, без failures/errors/skips, на текущих локальных байтах `main` при HEAD `2ce3ec2b91b4ba368b3a7cae9de8414c57750846`; свежий ledger trace снова прошёл **14 шагов и пять проверок**. Новый [manifest 193 файлов](../evidence/micky-payment-lifecycle-2026-10-25/main-integration/input-manifest.json) имеет SHA-256 `48b1fd625bc87d657023ada19bd818da4923cd5ff672b711dc40d9d2154507f8`; разрешённый архив — `b002b687b845b64fb9aca0fa0d4b540f91fa0b90ce202298e589e61c295226f4`. От первоначального снимка отличаются три файла параллельных security-исправлений: `card_topup.py`, `hub_routes/accounts.py`, `zk_groth16.py`; все три новых теста Micky, кредитный ledger, invoke-путь и lock зависимостей совпадают с первоначальными байтами. В рамках работы Micky финансовый код не менялся. [Команды и результаты](../evidence/micky-payment-lifecycle-2026-10-25/main-integration/execution.json), [JUnit](../evidence/micky-payment-lifecycle-2026-10-25/main-integration/results/junit.xml), [новый trace](../evidence/micky-payment-lifecycle-2026-10-25/main-integration/results/ledger-trace.json) относятся к новому снимку; первоначальный manifest и исторические результаты сохранены отдельно. Исполнение вновь использовало Linux `runc`, тесты и trace — `--network none`, без реальных платежей. При [очистке](../evidence/micky-payment-lifecycle-2026-10-25/main-integration/cleanup.json) сверены 193 входных и семь выходных файлов, `removed: true`; локально также подтверждено совпадение всех 189 файлов приложения, конфигурации и тестов с новым manifest.

Раскрытие AI для отчёта: AI-агенты подготовили сценарии, проверили код и оформили анализ; выводы опираются на сохранённые Linux-результаты, реальные ledger states и явно фиктивные деньги.
