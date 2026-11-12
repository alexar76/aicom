# Экономический core: отдельный проход по компонентам, 10 ноября 2026

**Новых подтверждённых сторонних runtime-интеграций, зависимостей или независимых испытаний продуктов core не установлено.** Проверены16 семейств и точные имена15 плагинов. Существующий внешний derivative Enterprise Factory подтверждён как самостоятельная доработка исходников, без признака новой активности; он учитывается отдельно от runtime.

Точные локальные package/import/repo fingerprints сохранены в `fingerprints.json`. Поиск шёл по каждому семейству и его именам, а не по общему alexar76. В `coverage.json` есть query, matched candidates, источники проверки, статус и предел для каждого компонента; там же перечислены все15 плагинов. HISTOR/WARDEN в этой ветке не исследовались.

## Что показывают зависимости

| Координата и область | Первичный результат | Как учитывать |
|---|---|---|
| PyPI `aimarket-hub@3.19.0` | deps.dev:15 direct dependents; named sample содержит все15 | Все имена буквально совпадают с нашими15 plugin manifests. Это внутренние связи экосистемы, не15 сторонних разработчиков |
| PyPI `aimarket-agent@2.6.2` |1 direct dependent: `aimarket-bridges@0.1.0` | Наш пакет, не внешний adopter. Представитель старой версии в графе не является наблюдением установленного клиента |
| npm `@aimarket/agent@0.4.0`, `@aimarket/widget@0.1.2` | Оба version-scoped graphs:0 | Ноль относится к конкретным версиям и публичному package graph, не всем приложениям и не прямому HTTP использованию |
| PyPI `aimarket-bridges@0.2.1`, `aimarket-treasury@0.1.4`, `aimarket-mcp-packager@2.1.3`, `aimarket-tee@2.0.1` | Четыре checked graphs:0 | Остальные13 plugin reverse graphs отдельно не запрашивались; отсутствие их внешних dependents не утверждается |
| Rust `aimarket-agent` | Официальный crates.io reverse endpoint: `total=0` | Registry-wide reverse index данного crate, без private/path/Git зависимостей |
| Dart `aimarket_agent` | Официальный pub.dev query `dependency:aimarket_agent`: пустой packages array | Результат одного публичного dependency query; не перепись Flutter apps |

Графы запрашивались после чтения актуальных registry metadata, с явной фиксацией версии. Downloads и stars не использовались как внедрения. Полные ответы — `package-metadata-index.json`, `reverse-dependency-index.json`, `named-dependency-index.json` и соответствующие тела.

Две дополнительные проверки касаются распределения наших пакетов, не стороннего использования: `ai-service-mesh` в точном PyPI JSON endpoint вернул404, хотя такое имя присутствует в локальном manifest и satellite map; это не ошибка доступности самого Mesh сервиса. Pub.dev сообщает latest `aimarket_agent0.3.0`, в локальном Dart manifest —0.4.0. Эти срезы не объявляются багом rollout или новым спросом; локальные и опубликованные версии разделены.

## Состояние каждого семейства

| Семейство | Результат целевого поиска и проверки |
|---|---|
| Hub | Прежние ProtocolProbe/MCPBeat/Odel/Tracevero/Glama; нового чужого импорта в полученной выдаче нет. Named graph — только наши plugins |
| Protocol | Собственная спецификация, собственный IETF draft и копии Wiki; exact foreign README query0. Прежние совместимые manifests не пересчитаны как новые |
| Python Agent | Свежая версия и граф проверены; единственный named dependent — наш Bridges |
| TypeScript SDK | Точный npm name/dependencies и общий SDK repo URL; внешний dependent текущей версии не найден в графе |
| Dart SDK | Точный import и SDK repo URL; own package docs/зеркала отделены от применения. Official dependency query пуст |
| Rust SDK | Cargo name/repo fingerprints и официальный reverse index; Docs.rs — документация нашего crate |
| Plugins | Все15 exact package names в трёх поисковых группах. Прежние awesome/Anclum/GitHubHelp copies — производные каталоги. Packager/TEE graphs проверены отдельно |
| Widget | Exact package и embed URL. Own npm/demo/Wiki, нового внешнего embed не подтверждено; foreign README0 |
| Bridges | Exact `aimarket_bridges`, own-version graph и external README0. Использование Agent через Bridges внутреннее |
| AI Service Mesh | Exact repo/package; только own/copy/awesome metadata, foreign README0. PyPI404 не превращён в нулевой graph |
| ACEX | Exact repo URL web search: own Wiki/topic references. Дополнительный GitHub query не отправлен после квоты |
| Pulse Terminal | Exact repo URL web search, локальный package `private:true`; own/copy context. Дополнительный GitHub query не отправлен |
| Escrow Signer / HORKOS | Exact repo и `escrow-policy-signer`/HORKOS; собственная страница и topic mirrors. Дополнительный GitHub query не отправлен |
| Treasury | Exact package web search, PyPI0.1.4 graph0; GitHub query403 — ограничение доступа, не0 результатов |
| Factory / AICOM | Enterprise Factory — прежний `derivative_source`, current head совпал с26 октября. UNDERCODE — прежнее освещение release notes, нынешний GET403 |
| Products | Exact `alexar76/aicom-products` repo URL; own topic/Wiki. Нового внешнего кейса выпущенного продукта не подтверждено |

## Реальный прежний кодовый кейс Factory

[Enterprise Factory](https://github.com/th3artfuldodger/enterprise-factory) вновь доступен; API подтверждает fork parent `alexar76/aicom`. Это не просто факт fork: сохранённое сравнение **26 октября** установило19 отдельных коммитов с изменениями агентов, API, интерфейса, тестов и памяти. Числа19 ahead/102 behind относятся к тому сравнению и не пересчитывались против сегодняшнего parent.

Нынешний default head — `ef124a40d592bf149fab93fb632a4aaf688a04fa`, **буквально тот же**, что в baseline26 октября. Последний push14 октября20:06UTC. Дополнительно прочитан [закреплённый `core/security_redaction.py`](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/core/security_redaction.py#L25), добавленный в прежнем diff: в нём есть реализации редактирования структуры/текста и фильтра логирования. Сторонний код не исполнялся.

Класс — **`derivative_source`**, повторно подтверждённый. Это самостоятельная исходниковая работа внешнего аккаунта, а не установленное production-развёртывание, успешный тест, покупатель или свежая интеграция. Author strings в исторических commits не удостоверяют личность и человеческое происхождение всего кода.

[UNDERCODE Factory release coverage](https://undercodenews.com/aicom-factory-just-updated-video/) остаётся известным материалом8 октября. Октябрьское первичное чтение установило пересказ release notes и AI disclosure. В этом проходе прямой GET403; текущая поисковая копия подтверждает присутствие материала, но свежий HTML не прочитан. Это не новый hands-on review.

## Охват и ограничения

Выполнены **29 поисковых попыток:24 web queries и5 GitHub README queries**. Первые четыре GitHub queries дали HTTP200/0 для Bridges, Widget, Mesh и Protocol. Пятый, Treasury, получил quota403; очередь остановлена. ACEX, Pulse и Escrow GitHub queries оставлены в coverage как **неотправленные**, при уже выполненном точном web-поиске. Повторов, смены IP или аккаунта не было. GitHub разбивает дефисы и другие знаки, поэтому совпадение token name не принималось как доказательство идентичности.

Сохранён **31 первичный GET:28 HTTP200, два403, один404**. Все тела полные; длина и SHA256 проверены в `capture-integrity.json`. Статусы403 относятся к GitHub Search и UNDERCODE,404 — к точному PyPI Mesh endpoint. Это ограничения/наблюдения конкретных адресов, не общий вывод об отсутствии проектов.

Результат ограничен этими запросами, индексами и версиями; весь интернет, полный code search, private deployments и реальный спрос не охвачены. Публикаций, сообщений, авторизаций, вызовов инструментов, платежей, установки или исполнения стороннего кода не было. Сборка coverage/findings и integrity воспроизводится локально: `.venv/bin/python artifacts/external-components-2026-11-10/core/build_report.py`.
