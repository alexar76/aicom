# Чужой код и использование данных HISTOR/WARDEN: углубление 10 ноября 2026

**Нового доказанного runtime-внедрения или dependency в этом проходе не найдено. Дополнительно подтверждён точный исторический комментарий Paraphern в Omnigent: он использует наш HISTOR count как аргумент в техническом предложении.** Более подробное чтение известных RugSnare/CrawlCheck материалов помогает отделить использование результатов исследования от подключения продукта.

Публичные чтения выполнены около **19:18–19:22 UTC**. База — вечерний `artifacts/external-links-2026-11-10/review.ru.md`, отчёты 9 ноября и октябрьские первичные свидетельства. Выполнены 20 web search строк и 35 публичных GET: 32×200, один 404 предположенного файла, два 429. Один ответ 200 обрезан по локальному лимиту и исключён из содержательных выводов об отсутствии. Все сохранённые тела совпадают с индексами по длине/SHA-256.

## Дополнительное подтверждённое использование данных в обсуждении

[Paraphern в Omnigent #12030](https://github.com/omnigent-ai/omnigent/issues/12030#issuecomment-6476897924), **28 октября 18:11:53 UTC**, предлагает хранить fingerprint в per-harness allowlist и проверять поверхность при запуске worker. В качестве аргумента он приводит собственные 218 изменений и **HISTOR ~45%** изменившихся remote tool lists за месяц. Первичный API возвращает 200, автора Paraphern и точные даты.

Это содержательное внешнее использование наших опубликованных результатов в design discussion. Оно одновременно продвигает продукт RugSnare, поэтому не считается беспристрастным обзором. В комментарии нет прямого href к HISTOR. Принятие предложения командой Omnigent и использование HISTOR в их runtime не установлены. Точный comment ID не встретился в проверенной прошлой локальной базе; это впервые сохранённый здесь **старый ответ известного внешнего оператора**, а не новый пользователь или ноябрьское событие.

## Что действительно лежит в чужом репозитории

[RugSnare comparison document, закреплённый commit 2efbfbae](https://github.com/Paraphern/rugsnare/blob/2efbfbae28e3b506c40aa33719804ab5c2f4f8c9/audits/drift-watch/comparison-dominion-captures.md) содержит отдельную трёхстороннюю таблицу PIN-SPEC/Dominion/MTL/1: field set, sort order, числовая канонизация и extras. В нём есть прямая Markdown-ссылка на [наш MTL PROFILE](https://github.com/alexar76/aicom/blob/main/awr/adoption/mcp-trust-label/PROFILE.md) и поправка от 26 октября к охвату `toolExtrasDigest`.

Этот URL **уже встречался в raw 28/29 октября и 9 ноября**. Новое здесь — подробное первичное чтение файла, не новая найденная ссылка. Таблица датирована октябрём и всё ещё говорит об отказе MTL/1 от дробей: это историческое описание, не актуальная характеристика MTL/1 1.1. При оценке совместимости требуется учитывать версию.

[Опубликованный в репозитории draft ответа 26 октября](https://github.com/Paraphern/rugsnare/blob/2efbfbae28e3b506c40aa33719804ab5c2f4f8c9/tools/reply-3431-crosscheck-2026-10-26.md) признаёт воспроизводимость замечаний alexar76 по шести загрязнённым pins и описывает повторную запись с чистых stands. Он также обсуждает launch arguments, network и package observations. Это сильнее общего упоминания: внешний проект сохраняет предметный инженерный разбор. Но файл прямо назван draft и содержит указание публиковать позднее; **сам draft не посчитан ещё одним опубликованным ответом** или работающим HISTOR reader. Связь и исходная публичная дискуссия уже были известны.

## Проверенные границы runtime и CI

В [product/package.json RugSnare 1.6.0](https://github.com/Paraphern/rugsnare/blob/2efbfbae28e3b506c40aa33719804ab5c2f4f8c9/product/package.json) нет объявленных dependencies/devDependencies. [Weekly workflow](https://github.com/Paraphern/rugsnare/blob/2efbfbae28e3b506c40aa33719804ab5c2f4f8c9/.github/workflows/weekly-drift-audit.yml) устанавливает RugSnare. Непосредственно прочитанный [runner](https://github.com/Paraphern/rugsnare/blob/2efbfbae28e3b506c40aa33719804ab5c2f4f8c9/audits/run-weekly-audit.mjs) берёт собственный watch-list, устанавливает сравниваемые npm versions и вызывает свои scan/diff. В этих полных файлах нет exact HISTOR/WARDEN identifiers, API адреса или читателя нашего датасета. Так что считать этот CI потребителем HISTOR оснований нет. Это ограничение конкретных файлов, не исключение HTTP calls/vendoring в остальных исходниках.

В закреплённом [CrawlCheck commit 6103cac1](https://github.com/emmanuelorta/crawlcheck-core/commit/6103cac17a0821d99fdd1acabca7ee56092e2a26) дополнительно прочитаны `paper/robots-shadowing.tex`, `paper/agent-safety-benchmark.tex` и `sdk/test/fixtures/continuity-gen.mjs`. В них нет exact HISTOR, alexar76, нашего domain или DOI. Эти papers/generator не добавляют независимое цитирование или reader к уже известному совместимому fixture. Соседние файлы полностью не исследованы; root отдельно проверяет текущие witness cosignatures. Чужой код не запускался.

[traits-dev commit d28c0c79](https://github.com/isotope13-dev/traits-dev/commit/d28c0c79dfc7aecb94c40acbbc8109ecee26d2ab) остаётся прежним единственным exact commit-search hit по WARDEN. Он датирован **21 октября** и описывает анализ/переклассификацию tarball `@aimarket-warden-0.18.0.tgz`, указывая SHA-256 и verify-side public-key context. В нём прямо раскрыта использованная модель. Это внешнее сканирование пакета, не dependency/import и не новое внедрение; кейс уже был в базе 9 ноября.

## Охват поиска и честные исключения

Семь GitHub repository/README запросов проверяли exact WARDEN package, HISTOR domain/package/dataset/DOI/extras и MTL/1+MCP. Четыре узкие строки дали ноль, dataset и DOI — только известный RugSnare. MTL/1+MCP запрос вернул 24 широких кандидата; поиск смешивает эту запись с mTLS/версиями. Эти результаты не использовались как доказательство связи без точных идентификаторов и не объявлялись внедрениями.

Четыре GitHub commit searches: WARDEN дал известный traits-dev; HISTOR domain и dataset — ноль; числовой fragment DOI дал три совпадения, которые относятся к SHA префиксу/постороннему числовому счётчику. Они исключены. Публичные forks APIs WARDEN и HISTOR вернули пустые списки. Forks/README/commit-message search не является поиском по всему коду и не измеряет пользователей.

Оба grep.app API запроса ответили 429; ограничение не обходилось. Рекурсивное дерево traits-dev достигло лимита 5,000,001 byte; неполный JSON не парсился и не служит доказательством отсутствия файлов. Предположенный корневой `RugSnare/package.json` ответил 404: наблюдение о dependencies основано на реальном `product/package.json`, а не на отсутствии корневого файла. Один четырёхстрочный web-пакет включал robots-blocked codeberg.org; полнота остальных строк пакета не предполагается. Числовые ложные совпадения, собственные статьи и автоматические каталоги не учитывались как независимое применение.

## Свидетельства

`findings.json` хранит classification, confidence, ownership, novelty, exact URLs и commit pins. `verification.json` проверяет длины/SHA и точные отрицательные проверки выбранных полных файлов. Пять `sources-0N.json` и `sources-0N-index.json` задают и описывают все GET; `.raw` — тела. Поисковые ответы — `search-01.json`…`search-05.json`, строки — `query-log.json`.

Выполнялись только публичные чтения и локальная запись технических свидетельств. Не выполнялись GitHub writes, публикации, сообщения, installs, чужой код, платежи, invokes или tools/call. Human identity/beneficial ownership внешних аккаунтов не проверялись. Отсутствие новой dependency в этом ограниченном проходе не доказывает отсутствие сторонних пользователей.
