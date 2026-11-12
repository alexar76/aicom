# Остальные агенты и оракулы: внешнее использование, 10 ноября 2026

**Для 15 проверенных семейств нового подтверждённого чужого runtime-внедрения, dependency или самостоятельного технического обзора не установлено.** Проверка уточнила происхождение положительных dependency counts: 20 dependents oracle-core и единственный dependent MOMUS относятся к нашей экосистеме. Одноимённый Igor Holt MOMUS исключён по его собственному явному различению проектов.

Срез первичных источников: **19:35–19:39 UTC / 20:35–20:39 Europe/Amsterdam**. Выполнены 30 целевых web-запросов, один общий GitHub README query и четыре commit-message query по точным HTTP origins — **35 поисковых исполнений**. Первичных GET — **27**, из них 23 ответа 200 и четыре 404 индексированных package-version graphs. Все тела сохранены полностью и сверены по длине/SHA-256. HISTOR не исследовался; автоматические каталоги и копии нашей документации не учитывались как независимые внедрения.

## Покрытие каждого семейства

Точные package/repo/module/origin fingerprints извлечены из местных pyproject/package/server metadata и README; каждый источник и его SHA сохранены в `inventory.json`. В `coverage.json` есть отдельная запись для каждого семейства с двумя точными web-запросами, ответным файлом, HTTP origin и состоянием графа. Нули в таблице означают только ответ version-scoped deps.dev, а не ноль пользователей.

| Семейство | Точный package fingerprint | HTTP origin или граница атрибуции | Граф зависимостей в этом срезе |
|---|---|---|---|
| METIS | `aimarket-metis` 0.2.6; Python `metis` | `https://metis.modelmarket.dev` | 0 dependents |
| ARGUS | `@alexar76/argus3` 0.3.6; `io.github.alexar76/argus3` | stdio; `magic-ai-factory.com/argus/` — homepage, не доказанный публичный runtime API | 404, неизвестно |
| HESTIA | `aimarket-hestia` 0.2.0; Python `hestia` | `https://hestia.modelmarket.dev`; README описывает `POST /v1/tenants` | 0 |
| THEMIS | `aimarket-themis` 0.1.0 | В прочитанном README нет установленного standalone public API origin; общий Hub URL сам по себе недостаточен | 404, неизвестно |
| HEPHAESTUS | `@aimarket/hephaestus-core` 0.1.0 | `https://forge.modelmarket.dev` — studio/frontend; локальный npm package имеет `private: true` | Published npm adoption query неприменим |
| ATLAS | `aimarket-atlas` 0.4.0; Python `atlas` | `https://atlas.modelmarket.dev` | 0 |
| GAIA | `aimarket-gaia-gateway` 0.3.0; Python `gaia` | `https://iot.modelmarket.dev` | 0 |
| Oracles / Platon | `aimarket-oracle-core` 0.6.4; `aimarket-platon` 0.1.6; `oracle_core` | `https://oracles.modelmarket.dev`, включая Platon UMBRAL; 17 oracle package aliases локально | core: 20 внутренних; Platon: 0 |
| Oracle Gateway | `aimarket-oracle-gateway` 0.3.3; `aimarket_oracle_gateway.stdio_server` | stdio package; `modelmarket.dev` — backend Hub, не собственный hosted MCP origin | 0 |
| MCP Gateway | `aimarket-mcp` 0.6.4; `aimarket_mcp.stdio_server` | stdio или собственный HTTP deployment; maintained `modelmarket.dev/mcp` относится к Hub | 0 |
| MOMUS | `aimarket-momus` 0.2.0; Python `momus` | `https://momus.modelmarket.dev` | 1: наш Treasury |
| BASANOS | `aimarket-basanos` 0.1.0 | `https://basanos.modelmarket.dev` | 404, неизвестно |
| DOLOS | `aimarket-dolos` 0.1.0; Python `dolos` | `https://dolos.modelmarket.dev` | 404, неизвестно |
| LOGOS | `aimarket-logos` 0.2.2; Python `logos` | `https://logos.modelmarket.dev` | 0 |
| SKOPOS | `skopos-fleet` 0.3.0; Python `skopos` | `https://skopos.modelmarket.dev` | 0 |

Metis/IOT/ATLAS origins дополнительно проверены отдельными commit-message запросами; HESTIA и Forge — общей четвёртой строкой. Все четыре ответа 200, total_count=0, incomplete_results=false. Это поиск по сообщениям commits, не чтение всего кода GitHub. Возможная HTTP-интеграция без зависимости не исключается.

## Почему положительные графы не означают новых пользователей

[deps.dev oracle-core 0.6.4](https://deps.dev/pypi/aimarket-oracle-core/0.6.4/dependents) возвращает **20 direct dependents**, и [первичный список имён](https://deps.dev/_/s/pypi/p/aimarket-oracle-core/v/0.6.4/dependents) содержит все двадцать записей. Девятнадцать имён буквально совпали с project names местных pyproject: oracle packages, GAIA, MOMUS, LOGOS, SYMMARTYS, Treasury и SKOPOS. Последний `aimarket-emporion` атрибутирован по [публичной PyPI metadata](https://pypi.org/pypi/aimarket-emporion/json), ссылающейся на `github.com/alexar76/emporion`. Покомпонентное происхождение сохранено в `oracle-core-dependent-attribution.json`. Подлинность всех текущих wheel-артефактов криптографически не проверялась; это атрибуция пакетных записей и ролей, не аудит публикаций.

[MOMUS 0.2.0](https://deps.dev/_/s/pypi/p/aimarket-momus/v/0.2.0/dependents) имеет ровно один direct dependent — **`aimarket-treasury` 0.1.0**, наш отдельный payer. Ни 20, ни 1 нельзя представлять как число внешних интеграторов. Эти графы относятся к конкретным версиям и не охватывают прямые HTTP calls, копирование исходников, CLI calls без manifest dependency или private code.

## Проверенный ложный кандидат и свежая база

[igor-holt/momus README, закреплённый commit 1ac416e4](https://github.com/igor-holt/momus/blob/1ac416e4c2e2f92c23209db977166eccafcde2be/README.md) описывает Genesis Conductor и прямо отличает его от alexar76 red-team satellite. README, repository metadata, commit и полное небольшое дерево прочитаны первично. Кандидат исключён как **известный октябрьскому аудиту одноимённый проект**. В identity search он попадает именно из-за текста различения; это не свидетельство fork, import или integration.

Общий [GitHub README query](https://api.github.com/search/repositories?q=alexar76%20in%3Areadme%20-user%3Aalexar76&per_page=100) вернул 12 репозиториев. Проверены **точные full_name sets**, а не только число: относительно свежего `artifacts/external-links-deeper-2026-11-10/code/github-searches.json` added=[] и removed=[]. Поэтому переход «11→12» здесь не заявляется новизной. Текущее множество совпадает с уже выполненным сегодня проходом.

## Что исключено из результатов

Поисковые batches вернули преимущественно собственные GitHub Pages/PyPI/DEV статьи, зеркала wiki/README, автоматические MCP-каталоги и автоматически построенные comparisons. Small Print/mcpcost/ProtocolProbe по ARGUS и gateway — автоматическое чтение surface, не стороннее пользовательское внедрение. Mend diff страницы SKOPOS — индексированные package diffs, не чужой импорт. WorldProgramming и WebPulse пересказывают собственную статью об экосистеме; число копий не стало числом независимых обзоров. Общие совпадения Metis/Gaia/Skopos и Acria AIMARKET вручную не приписывались экосистеме.

Эти страницы не расширялись отдельными primary GET: по текущему scope приоритет был у чужого кода, точных origins и графов. В возвращённых выдачах нового кандидата, которому требовалась проверка actual import/call, не установлено.

## Пределы вывода и воспроизведение

Это ограниченный публичный поиск, не полный обзор интернета. Авторизация и GitHub authenticated code search не использовались. README поиск не читает package manifests во всех репозиториях; commit search не ищет буквальный URL в каждом файле. Поисковик игнорировал часть exclusions и расширял некоторые короткие имена, поэтому собственные/автоматические/одноимённые результаты исключались вручную. Отсутствие нового подтверждения не доказывает отсутствие сторонних пользователей.

Данные и проверки: `coverage.json` — 15 семейств; `findings.json` — классифицированные выводы; `inventory.json` — fingerprints и локальное происхождение; `verification.json` — проверка всех 27 тел и full_name delta. `sources-0N.json`/`sources-0N-index.json` задают и описывают GET; `.raw` хранят ответы; `search-01.json`…`search-08.json` и `query-log.json` — поиск. Сборка выполняется собственным локальным `build_report.py`; сохранённый чужой код не запускался.

Не было публикаций, GitHub writes, сообщений, payments, invokes, tools/call, installs, account authentication или исполнения чужих scripts. Внешние аккаунты не считаются доказанно независимыми людьми только по различию username.
