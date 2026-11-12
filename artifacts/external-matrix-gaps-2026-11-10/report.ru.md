# Проверка пробелов ACEX Pulse Escrow и недоступных источников

**Четыре ранее пропущенных или ограниченных README-запроса выполнены; новых подтверждённых чужих imports, API calls, embeds или signer configs выборка не дала.** Поиск дополнен точными Python namespaces ACEX, capital routes, Pulse frontend config и wire protocol HORKOS. Часть ранее недоступного содержания прочитана на обычных публичных страницах издателей; GitHub CORE REST quota не восстановилась.

Срез выполнен **10 ноября 2026 примерно в 20:03–20:11 UTC / 21:03–21:11 Europe/Amsterdam**. Основа сравнения — [предыдущий проход](../external-components-2026-11-10/report.ru.md). [Основная матрица обновлена](../external-components-2026-11-10/component-matrix.json): прежние записи сохранены, результаты этого прохода добавлены в `latest_follow_up`. [Отдельная дельта](matrix-delta.json) различает завершённый запрос, восстановленное содержание и остающееся ограничение.

## Завершённые поисковые проверки

| Компонент | Закрытый прежний пробел | Дополнительный точный поиск |
|---|---|---|
| ACEX | Repo URL в чужих README: HTTP 200, 0 результатов | `acex.integrations` и `ACEX_JUPITER_QUOTE_URL` в README; `AgentAuditPool` и `AgentListingRegistry` в commit messages — четыре ответа 200/0 |
| Pulse Terminal | Repo URL в чужих README: 200/0 | `magic-ai-factory.com/pulse` в чужих commit messages: 200/0 |
| Escrow / HORKOS | Repo URL в чужих README: 200/0 | `AIMARKET_ESCROW_SIGNER_URL` в чужих commit messages: 200/0 |
| Treasury | Прежний quota-403 query по `aimarket-treasury` в README теперь 200/0 | Это восстановление конкретного запроса, не новый dependent graph |

Все десять GitHub Search ответов содержат `incomplete_results=false`; полные тела и хеши сохранены. Эти нули относятся к названным README/commit-message queries, а не к содержимому каждого файла GitHub. Авторизованный полный code search не выполнялся. [Точные URLs, время и результаты](root/findings.json).

## Уточнённые маркеры реального кода

**ACEX.** Прежний fingerprint был слишком узким и сводился к Solana crate. Из 27 местных исходников, документов и config examples теперь выделены `acex.integrations.pricing`, `.ai_audit`, `.jupiter`; реальные импорты Hub/Factory; восемь контрактных имён, шесть публичных адресов, Solana ID; capital HTTP/WS/SSE routes, origins и настройки. Например, проверяются `build_pricing_snapshot`, `build_pack`, `fetch_jupiter_quote`, `/api/v2/capital/pricing` и Hub `/ai-market/v2/capital/...`.

Это делает последующую атрибуцию точнее, но собственные Hub → ACEX imports не являются внешним применением. PyPI `acex` 7.0.0 первично проверен и относится к другому ACE-X Backend с repo `acex-labs/acex`. Чужие показатели этого пакета к нашему продукту не относятся. Поисковый Fastly URL с нашим Jupiter guide является копией собственного контекста; прямое чтение вернуло 503. [ACEX fingerprints и исключения](acex/summary.md).

**Pulse.** `pulse-terminal` — частный frontend package. В двух собственных origins объявлен один и тот же собранный JS, равенство bytes/SHA-256 проверено. Публичный `src/lib/api.ts` совпадает с местным; точный fetch идёт к capital/pricing, настройки включают `VITE_PULSE_API_URL` и `VITE_PULSE_MONITOR_API`. Фактический клиент использует polling, хотя README описывает WS-first. Это уточнение текущего клиента, а не находка чужого embed.

**HORKOS.** Выделены Python namespace `escrow_signer`, service `escrow-policy-signer`, Hub `ExternalSigner`, JSON envelope и `AIMARKET_ESCROW_SIGNER_URL`. Прочитанные документы описывают loopback `/sign` через tunnel; публичный origin signer не установлен. Точные fingerprints включают EIP-712 `AIMarketEscrow` version 1, Base 8453, `DebitAuthorization(...)` и selector `0xf7becd80`. Сервис подписания и транзакции не вызывались. [Pulse и HORKOS source/protocol evidence](pulse-escrow/summary.md).

## Что удалось прочитать после прежних отказов

| Прежний недоступный материал | Прочитанный первоисточник | Что установлено и что нового |
|---|---|---|
| EbookFoundation PR13394 | [Официальная web-страница PR](https://github.com/EbookFoundation/free-programming-books/pull/13394), HTTP 200 | PR исторически merged eshellman 6 августа. Это принятие авторской ссылки/правки каталога, без свидетельства использования SDK или прохождения курса |
| Commit `b197a1cf...` | [Закреплённая web-страница commit](https://github.com/EbookFoundation/free-programming-books/commit/b197a1cf7f8c62153dacc22a351253ae88ec840c), HTTP 200 | Один документационный файл и одна добавленная строка. Подтверждён характер размещения; это не новая интеграция ноября |
| Obsidian README | [Репозиторий](https://github.com/2233admin/obsidian-llm-wiki), его canonical raw README и две связанные страницы примера, все 200 | Проверен не только README, но и явно связанный raw `team-memory-os.md` и compiled summary. Пример имеет `origin: internal-product-note` и описывает generic raw → wiki → review workflow. Уникальных наших identifiers нет; ни наше Attested Memory, ни другой одноимённый проект ему не приписаны |
| API Evangelist `apis.yml` | [Буквально опубликованный YAML APIs.io](https://artifacts.apis.io/attestedmemory-net/apis.yml), HTTP 200 | `x-source: harvest:mcp-registry`, created/modified 2 ноября; bytes совпали с сохранённым источником 9 ноября. GitHub `/contents/apis.yml` был неподтверждённым местоположением, а не единственным источником. Это прежний generated API profile, не foreign business client |

У PR13394 дополнительно подтверждена историческая редакционная курация: maintainer просил общую portal-ссылку, связанный School PR закрыт как duplicate. Эта первичная детализация не превращена в новый независимый продуктовый обзор. API access к этим REST адресам не объявляется восстановленным только потому, что обычная publisher web/raw-поверхность доступна. [Методы чтения, точные источники и сравнение с базой](recovery/summary.md).

## Остающиеся ограничения

- **GitHub CORE REST:** статус quota показывал remaining=0; один обычный повтор Obsidian README снова вернул 403. Дальнейшего polling или перебора авторизации не было. Ответные Date/reset не гарантируют фактического восстановления доступа.
- **UNDERCODE и Socket eSIM:** по одному обычному повтору каждого снова дали 403 с managed challenge. Это не GitHub quota. Тексты в этом проходе не прочитаны, новыми reviews не считаются.
- **grep.app:** единичный обычный retry точного ACEX import вернул 429. Он не является отрицательным результатом code search.
- **Private и неиндексируемый код:** прямые HTTP callers, ручные deployments и закрытые configs могли не попасть в открытые индексы.

Следовательно, закрыты конкретные пропущенные поисковые запросы и доступ к четырём содержательным материалам. Полный поиск по всему коду и два challenge-блокированных сайта остаются открытыми областями. Новых подтверждённых внешних integrations, imports, calls или configs — **0 в этой выборке**.

## Локальные свидетельства

[Дельта матрицы](matrix-delta.json) · [ACEX coverage](acex/coverage.json) · [Pulse/Escrow coverage](pulse-escrow/coverage.json) · [Восстановление источников](recovery/findings.json). Сохранены bodies, времена, HTTP status и SHA-256; проверка длин и хешей выполнена для собственных и переиспользованных captures. Общие root Search ответы не суммируются второй раз как обращения рабочих веток.

Дельта воспроизводится локально: `PYTHONDONTWRITEBYTECODE=1 python3 artifacts/external-matrix-gaps-2026-11-10/build_delta.py`, затем `PYTHONDONTWRITEBYTECODE=1 python3 artifacts/external-components-2026-11-10/consolidate.py`. Сторонний код, frontend scripts и signer не запускались; внешних сообщений, публикаций, account changes и GitHub writes не выполнялось.
