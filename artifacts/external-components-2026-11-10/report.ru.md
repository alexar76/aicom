# Внешнее использование остальных компонентов экосистемы alexar76

**Новых подтверждённых интеграций в чужом runtime, внешних пакетных зависимостей или независимых продуктовых обзоров этот проход не установил.** Наиболее сильные известные кодовые связи вне HISTOR — производный проект Enterprise Factory и историческое использование Hub в CI Industrial Platform. Их происхождение, даты и пределы отделены от свежих находок.

Срез выполнен **10 ноября 2026 примерно в 19:34–19:44 UTC / 20:34–20:44 Europe/Amsterdam**. База сравнения — [вечерняя проверка ссылок](../external-links-2026-11-10/review.ru.md), [предыдущий углублённый проход](../external-links-deeper-2026-11-10/report.ru.md), ноябрьские и октябрьские свидетельства. HISTOR и WARDEN в текущую исследовательскую область не включены.

## Покрытие компонентов

[Общая матрица](component-matrix.json) сопоставляет результаты **52 строкам satellite-карты**, включая алиасы и продуктовые оболочки; отдельно добавлен Pantheon. Это не 53 независимых продукта. Восемь остальных строк карты помечены как исключения: профиль, две wiki, HISTOR/WARDEN и три неопубликованных reference-реализации того же автора. Для каждой исследуемой строки указано семейство, файл результатов и точный индекс записи.

| Область | Компоненты и отдельные координаты | Результат |
|---|---|---|
| Экономическое ядро | Hub, Protocol, Python Agent, TypeScript/Dart/Rust SDK, 15 plugin names, Widget, Bridges, Service Mesh, ACEX, Pulse, Escrow/HORKOS, Treasury, Factory, Products | Нового чужого import/call/embed в проверенных источниках не подтверждено. Enterprise Factory — прежняя самостоятельная доработка исходников |
| Агенты и оракулы | Metis, ARGUS, HESTIA, THEMIS, HEPHAESTUS, ATLAS, GAIA, Oracles/Platon, оба MCP gateway, MOMUS, BASANOS, DOLOS, LOGOS, SKOPOS | Положительные графы oracle-core и MOMUS оказались внутренними. Одноимённый чужой MOMUS исключён первично |
| Продукты и обучение | Attested Hub/Personal/Team/Expert, Cite Desks и алиасы, Domain/eSIM kits, PingBlip, Coach, Desktop, Landing, School, Courses, scaffold generator, Playground, Use-cases Portal | Сохраняются известные учебные ссылки и автоматические профили; нового стороннего приложения, learner project или самостоятельного обзора не установлено |
| Сообщество и визуализация | SYMMARTYS/EMPORION, HELIOS, DIOSCURI, THEOROS, Alien Monitor, Signal Hunt, Lottery, Pantheon | Нового подтверждения в полученных точных запросах нет. Web-only и неполные code-index проверки явно отмечены |

Для семейства Desktop сохранён перечень десяти SKU, для Cite Desks — дочерние названия и домены, для памяти — четыре оболочки. Это семейный поиск с отдельными маркерами, а не исчерпывающая проверка каждого файла каждого дочернего продукта. [Core](core/coverage.json) · [Агенты и оракулы](agents-oracles/coverage.json) · [Продукты](products/coverage.json) · [Остальные семейства](root/coverage.json).

## Чужой код который действительно связан с экосистемой

**Enterprise Factory остаётся реальным внешним производным проектом AICOM.** [Репозиторий](https://github.com/th3artfuldodger/enterprise-factory) имеет parent `alexar76/aicom`. Октябрьское сравнение установило самостоятельные изменения агентов, API, интерфейса, тестов и памяти. Нынешний head `ef124a40d592bf149fab93fb632a4aaf688a04fa` совпадает с сохранённым 26 октября; последнего нового push после 14 октября не появилось. Дополнительно первично прочитан [изменённый модуль редактирования чувствительных данных](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/core/security_redaction.py#L25).

Это самостоятельная исходниковая работа внешнего аккаунта, а не простой star. Связь уже известна. [Сохранённый разбор CI от 30 октября](../../docs/growth/external-use-pass5-2026-10-30.ru.md) также фиксирует установку зависимостей и сборочные шаги, но отдельно предупреждает: success backend job не доказывает прохождение всех assertions из-за особого поведения runner. Публичный production endpoint этим не установлен. [Текущая перепроверка происхождения и head](core/summary.md).

**Industrial Platform — прежний прямой потребитель Hub в коде и CI.** Исторический workflow устанавливал `aimarket-hub==3.14.0`, затем requirements был переведён на git pin нашего Hub. В [публичном requirements](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/aimarket-sentinel/requirements.txt) сохраняется точная зависимость. Предыдущий сегодняшний срез повторно получил 404 от прежнего Railway discovery; поэтому этот кейс учитывается как историческое code/CI использование, без утверждения о работающем нынешнем deployment. [Первичные свидетельства предыдущего среза](../external-links-2026-11-10/ecosystem/summary.md).

Эти два проекта не добавлены к числу новых интеграций текущего поиска. Сохранённая протокольная совместимость manifest agent-exec также уже известна и не заменяет доказательство импорта нашей библиотеки в его исходниках.

## Что оказалось внутренними зависимостями

| Проверенная координата | Показанный результат | Атрибуция |
|---|---:|---|
| `aimarket-hub` 3.19.0 | 15 direct dependents | Все 15 — наши plugin packages |
| `aimarket-agent` 2.6.2 | 1 | Наш `aimarket-bridges` |
| `aimarket-oracle-core` 0.6.4 | 20 | Девятнадцать имён совпали с местными project names; двадцатый — прежний EMPORION, подтверждённый по PyPI provenance |
| `aimarket-momus` 0.2.0 | 1 | Наш Treasury |

Эти counts не складываются в пользователей или независимых интеграторов. Остальные успешно прочитанные графы выбранных версий дали нули, включая отдельные SDK, Widget, Metis, HESTIA, ATLAS/GAIA, шлюзы, LOGOS/SKOPOS, HELIOS/DIOSCURI, Signal Hunt, SYMMARTYS/EMPORION и четыре продуктовых пакета. Проверка core охватила отдельные reverse graphs Packager и TEE; графы остальных 13 plugins отдельно не запрашивались.

Есть существенные границы: graph API для ARGUS/THEMIS/BASANOS/DOLOS ответил 404, поэтому использование по этому индексу **неизвестно**. Точный PyPI endpoint Service Mesh тоже ответил 404; это не liveness-ошибка самого сервиса. `@aimarket/hephaestus-core` локально имеет `private: true`. Pub.dev latest Dart SDK — 0.3.0 при локальной 0.4.0, npm scaffold — 0.1.1 при локальной 0.1.2. Проверенные registry-версии не подменены локальными.

Прямые HTTP calls, Git/path installs, CLI и использование генератора без оставшейся dependency могут не попасть в публичный граф. Точные package names дополнялись repo URL и API origins. [Пакетные области core](core/summary.md) · [Атрибуция двадцати oracle-core dependents](agents-oracles/oracle-core-dependent-attribution.json).

## Независимые публикации и учебные ссылки

[Канонический список EbookFoundation](https://github.com/EbookFoundation/free-programming-books/blob/main/courses/free-courses-en.md) сохраняет прямую ссылку на AIMarket Courses. В commit search происхождение переноса записи связано с нашим авторским размещением; копии этой истории в forks не являются новыми рекомендациями. Это присутствие во внешнем курируемом списке, без нового свидетельства прохождения курса.

[The Learning Standard](https://thelearningstandard.org/news/how-autonomous-ai-agents-are-redefining-student-research-skills) по-прежнему ссылается на orchestration-course в Sources. Материал датирован 22 сентября и уже проверялся 30 октября. Ссылка подтверждена заново, самостоятельное испытание notebooks или качества курса из неё не следует.

Для Attested Memory [APIs.io](https://apis.io/providers/attestedmemory-net/) и API Evangelist прямо описывают стороннее автоматическое профилирование API. Glama даёт предметные замечания к описанию инструмента Domain Kit `renew`, но это оценка metadata, а не реальная регистрация домена или человеческий продуктовый обзор. PingBlip itch-страница и launch topic принадлежат самому издателю; новых читательских комментариев в прочитанном HTML нет. [Публикации и решения по каждому продукту](products/summary.md).

Известная UNDERCODE-заметка о релизе Factory датирована 8 октября и пересказывает release notes с раскрытым AI assistance. В этом проходе она ответила 403, поэтому свежего первичного чтения нет; поисковая копия не превращена в новый обзор.

## Исключённые совпадения и доступность поиска

- `aionbuilders/helios` — другой Bun WebSocket package. Полный README не содержит нашего namespace или домена; слово broadcast в нём описывает WebSocket rooms.
- `igor-holt/momus` прямо отличает свой Genesis Conductor от нашего red-team satellite. Текущий README прочитан по закреплённому commit.
- `besboy3107/team-memory-os` и Starlight attested memory не содержат наших уникальных маркеров в прочитанных README. Общий термин не доказывает связь с Attested Memory.
- Карточки, wiki mirrors, автоматические security/package assessments, topic pages и собственные статьи отделены от независимого применения. Прежние 12 репозиториев общего README-поиска совпали с предыдущим срезом по точным именам; прирост не заявляется.

Публичные GitHub quotas остановили часть запросов. В coverage сохранены как **неотправленные** дополнительные native queries ACEX/Pulse/Escrow, хотя точный web-поиск выполнен; Treasury query получил 403. В продуктовой ветке ещё четыре detail-запроса и Socket eSIM получили 403. Их нельзя считать пустой выдачей.

Оба Sourcegraph code stream ответили 200 с нулём показанных matches, но сообщили `skipped=shard-match-limit`; один также сообщил timeout. Эти ответы не дают полного отрицательного поиска по коду. README и commit-message search также не являются проверкой всех исходников. Аутентифицированный code search, приватные deployments и закрытые отзывы не охвачены.

## Сохранённые результаты

Каждая ветка сохраняет точные запросы, даты, первичные тела и SHA-256. Для всех тел сверены длины и хеши: [31 core](core/capture-integrity.json), [27 агенты/оракулы](agents-oracles/verification.json), [34 продукты](products/capture-integrity.json), [22 корневые проверки](root/capture-integrity.json). Числа относятся к ответам, включая повторяющиеся источники и ошибки доступа, а не к аудиториям.

[Общая матрица компонентов](component-matrix.json) · [Машинная сводка](summary.json). Матрица воспроизводится локально: `PYTHONDONTWRITEBYTECODE=1 python3 artifacts/external-components-2026-11-10/consolidate.py`. Сторонний код не устанавливался и не запускался; внешних публикаций, сообщений и записей не выполнялось.
