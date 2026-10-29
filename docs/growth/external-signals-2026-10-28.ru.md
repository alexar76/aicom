# Упоминания экосистемы alexar76 28 октября 2026 года

Публичные источники проверены 28 октября около 14:20–14:34 МСК и сопоставлены с [проверкой реакций 27 октября](external-signals-2026-10-27.ru.md), [расширенным поиском 27 октября](external-mentions-expanded-2026-10-27.ru.md) и отчётами [26 октября](external-mentions-2026-10-26.ru.md) и [24 октября](../external-presence-2026-10-24.ru.md).

**Главные изменения — готовность автора внешнего исследования включить HISTOR после уточнений, новые ответы Vulnetix и улучшившийся показатель активности в Agent Economy Report.** Дополнительно подтверждены карточки GAIA в mcp.market, Modelmarket в INITE Atlas и AIMarket Plugins в MCP Bridge. Нового самостоятельного обзора всей экосистемы или нового подтверждённого внедрения внешней командой этот проход не установил.

## Новые содержательные ответы

| Источник и время МСК | Что подтверждено | Значение |
| --- | --- | --- |
| [Ревью basitalisandhu к HISTOR](https://github.com/basitalisandhu/agent-skills-state-2026/pull/14#pullrequestreview-5680480229), 28 октября 12:31 | Автор исследования считает историю удалённых MCP tool definitions полезным дополнением и готов включить датасет. Попросил версионированный источник с лицензией и датой, а также одно предложение о составе данных. | Внешний автор выразил готовность к цитированию. Статус ревью — CHANGES_REQUESTED; включение ещё не завершено. |
| [Текущий PR №14](https://github.com/basitalisandhu/agent-skills-state-2026/pull/14/files), чтение около 14:29–14:31 | В diff уже стоит DOI снимка 20 октября, CC BY 4.0 и краткое описание. Видимый ответ alexar76 от 12:48 сообщает об этих изменениях. PR открыт, `merged=false`. | Запрошенные изменения присутствуют, дальнейшее решение остаётся за автором исследования. Собственный ответ alexar76 не считается внешней реакцией. |
| [basitalisandhu в MCP issue 3431](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431#issuecomment-6465686147), 28 октября 12:43 | Поддержал предложенную alexar76 формулировку и обсудил сохранение launch arguments рядом с точной версией пакета. | Предметное продолжение технического обсуждения. Это мнение участника, а не решение команды MCP. |
| [Vulnetix о перепроверке пакетов](https://github.com/Vulnetix/advisory-database/issues/5#issuecomment-6455496971), 28 октября 01:48, изменено 02:53 | Исследователь сообщил о проверке опубликованных wheels, новых записях и неполных исправлениях для отдельных конфигураций. | Существенный внешний сигнал по безопасности; текущие записи и сегодняшние релизы сопоставлены ниже. |

Ссылка на HISTOR в [README Rugsnare](https://github.com/Paraphern/rugsnare#independent-measurements) и [исправление снимков Shopify после сверки с HISTOR](https://github.com/Paraphern/rugsnare/blob/main/docs/servers/shopify.md) сохраняются. Их blob SHA совпадают со срезом 27 октября: это ранее установленное применение наших данных, не новое внедрение за сутки.

## Изменения в записях Vulnetix

[Запись HESTIA 000504](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000504.json) теперь имеет статус **REJECTED**, дата отзыва — 27 октября 09:51 МСК. Исследователь [признал](https://github.com/Vulnetix/advisory-database/issues/5#issuecomment-6435014222), что спорный `exec` выполняется внутри per-call wasmtime, а не в host process. Это отзыв конкретной ошибочной записи, не всех замечаний к HESTIA.

База теперь перечисляет исправленные версии для ранее ожидавших ответа записей: [helios-broadcast 021897](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/PYPI/2026/21xxx/GCVE-110-PYPI-2026-021897.json) — 0.2.1, [skopos-fleet 021896](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/PYPI/2026/21xxx/GCVE-110-PYPI-2026-021896.json) — 0.2.1, [aimarket-histor 022091](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/PYPI/2026/22xxx/GCVE-110-PYPI-2026-022091.json) — 0.4.1. У SKOPOS объединённая запись охватывает несколько недостатков; отдельно исследователь относит включение SSH host-key verification к 0.1.5.

В девяти новых записях 000636–000644, опубликованных 28 октября, фиксированные версии пока не перечислены. Однако на PyPI уже появились более новые выпуски четырёх пакетов. Состояние на 14:31 МСК:

| Пакет | Записи Vulnetix | Верхняя affected-версия в записи | Последняя версия PyPI |
| --- | --- | --- | --- |
| aimarket-oracle-core | [000637](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000637.json) | 0.6.2 | **0.6.3**, 28 октября 10:54 |
| aimarket-logos | [000638](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000638.json) | 0.2.1 | **0.2.2**, 28 октября 12:56 |
| aimarket-mcp | [000640](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000640.json) | 0.6.3 | **0.6.4**, 28 октября 13:38 |
| aimarket-metis | [000641](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000641.json) | 0.2.4 | **0.2.5**, 28 октября 14:23 |
| aimarket-platon | [000636](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000636.json), [000643](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000643.json) | 0.1.5 | 0.1.5 |
| aimarket-treasury | [000642](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000642.json) | 0.1.3 | 0.1.3 |
| skopos-fleet | [000639](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000639.json), [000644](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000644.json) | 0.2.1 | 0.2.1 |

Замечания относятся к доверию адресным заголовкам от private-network peers, определению локального клиента у keyless-сервера, проверке SSH host keys для single-label remotes и общему бюджету попыток входа. В каждой записи есть условия применимости. **Более высокий номер выпуска сам по себе не доказывает исправление:** в этом проходе содержимое сегодняшних wheels и воспроизведение недостатков не проверялись. У Platon, Treasury и SKOPOS опубликованная текущая версия ещё совпадает с affected-диапазоном. [Ответы PyPI и точные записи](../../artifacts/ecosystem-mentions-2026-10-28/security-followups-index.json) сохранены со временем чтения и SHA-256.

## Внешнее наблюдение платежной активности

[Agent Economy Report](https://agenteconomy.report/s/modelmarket.dev.json), `as_of=2026-10-28`, показывает **CC, improving; 3 organic paying agents из 12 raw wallets; $0.39 settlements за 14 дней**. В подтверждённом срезе 24 октября были D, 0 organic, 5 raw wallets и $0.34. Три organic — классификация кошельков наблюдателем, не три идентифицированных клиента. Его показатель uptime остаётся 50% дневных проб; рейтинг ниже собственного порога BBB. Эти пробы нельзя напрямую сравнивать с частыми проверками других каталогов.

Data: [x402-list.com](https://x402-list.com/api/v1/services/aimarket/volume) (CC BY 4.0). За 27 октября UTC API показывает два settlements и [два адреса покупателей](https://x402-list.com/api/v1/services/aimarket/buyers), за неполное 28 октября — по одному. Денежная сумма каждого дня округлена до $0.00. Наблюдение относится ко всему адресу выплат, общему для сервисов, и измеряемым facilitators; это не показатель успешного выполнения задач или устойчивого спроса.

## Дополнительные подтверждённые карточки

Новизна здесь означает отсутствие ссылки в проверенных отчётах 24–27 октября, а не дату создания страницы. Все перечисленные страницы прочитаны прямым GET с HTTP 200 и точными идентификаторами проекта.

| Источник | Что найдено | Как учитывать |
| --- | --- | --- |
| [mcp.market GAIA](https://mcp.market/server/modelmarket-weather) | Отдельная карточка `dev.modelmarket/weather`, endpoint `modelmarket.dev/tools/mcp/weather`. Сканирование 27 октября: 91/100, три инструмента; при чтении 12 из 12 probes получили ответ, пользовательских отзывов нет. | Автоматическая проверка конкретного MCP endpoint. Code scan не выполнялся, поскольку сервер remote-only; оценка не переносится на всю экосистему. |
| [INITE Atlas Modelmarket](https://inite.ai/en/atlas/modelmarket.dev) | Карточка и [альтернативы](https://inite.ai/en/atlas/modelmarket.dev/alternatives), чтение каталога датировано 28 октября. | Дополнительный путь обнаружения. [Методика](https://inite.ai/en/atlas/method) описывает еженедельное чтение сайтов и реестров, а не пользовательское рецензирование. |
| [MCP Bridge](https://mcpbridge.org/directory/ai-ml/) | `alexar76/aimarket-plugins`, active, score 58, описание 15 plugins. | Карточка каталога с производными сведениями. Дата её создания не установлена. |
| [Skillget Rugsnare](https://skillget.dev/listings/paraphern-rugsnare?lang=en) | Карточка от 27 октября воспроизводит README, включая HISTOR и DOI. | Зеркало уже известного внешнего цитирования; не второе независимое применение данных. |
| [Forge WARDEN](https://forgeregistry.com/es/registry/%40aimarket%2Fwarden) | Дополнительный путь на известной площадке: карточка 0.21.0, B60. | Статический анализ относится к 0.5.0 и 5 сентября; его нельзя выдавать за проверку нынешней версии. |

## DEV и культурные проекты

DEV API вернул 59 статей alexar76. Полностью прочитаны все 12 веток с комментариями: **140 комментариев, 71 от внешних аккаунтов и 69 от alexar76**, счётчики совпали с метаданными статей. Относительно вчерашних 138 добавилась прочитанная июньская ветка с двумя старыми сообщениями. Во вчерашних 11 ветках новых комментариев нет; внешних ответов с датой 27 или 28 октября во всей выборке нет. Последний остаётся [Launch Gate от 26 октября 19:15 МСК](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3j38p).

Уточнение после [международного прохода около 15:40 МСК](external-global-2026-10-28.ru.md): публичный список DEV оказался неполным — в нём отсутствует доступная напрямую статья от 27 октября. Числа выше описывают возвращённую выборку и её ветки, а не гарантированно весь аккаунт. Прямые проверки двух последних статей подтвердили ноль комментариев на момент дополнительного чтения.

[HISTOR на Hacker News](https://news.ycombinator.com/item?id=50193565) сохраняет 1 point и 2 видимых комментария. [PingBlip на itch.io](https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game) остаётся собственным анонсом без ответов; на странице игры комментариев нет. У первых двух книг Trace of Refusal комментарии пусты, у третьей публичной секции комментариев нет. Новых подтверждённых чужих рецензий на Пантеон, трилогию или PingBlip не найдено. Счётчики просмотров не использованы как признак органического интереса: собственные проверки могут на них влиять.

[New Runtime](https://newruntime.com/readers/histor/) обновил известное наблюдение за user-agent `histor`: 183 запроса за 32 активных дня, последнее наблюдение 28 октября 09:52 МСК. На 24 октября было 141/27. Оператор по-прежнему unknown, уверенность low; прямой связи с modelmarket.dev нет. Совпадение с нашим клиентом вероятно, но строку user-agent можно подделать, поэтому это не установленное использование HISTOR внешним клиентом.

## Охват и свидетельства

Поиск включал точные домены, аккаунты, repository slugs и package names основных компонентов, security-спутников, культурных проектов, Independent AI, Attested Memory, Emberline и operator kits. Проверялись статьи, каталоги, пакеты, публичные обсуждения, X, Reddit, Bluesky, HN и языковые варианты поиска. Одноимённые продукты без связи с alexar76 или нашими доменами исключались. Новых атрибутируемых сторонних постов в просмотренной выдаче соцсетей не установлено; прямой поиск Bluesky и Reddit вернул 403 и не охватывает их непубличные или непроиндексированные материалы.

GitHub-поиск `alexar76 in:readme -user:alexar76` вновь дал 11 репозиториев, без нового кандидата. Это ограниченная выдача поиска по README, не полный поиск по коду или закрытым репозиториям.

[Общий индекс свидетельств](../../artifacts/ecosystem-mentions-2026-10-28/verification-index.json) связывает публичные URL, даты, HTTP-статусы и локальные источники. Первоначальные два ответа DEV 429 успешно дочитаны отдельными GET; недоступность web-open и DNS внутри sandbox не считалась отсутствием страницы. Подтверждённые выводы выше опираются на последующее прямое чтение. В этот проход выполнялись только публичные чтения; публикаций, сообщений, платежей и изменений аккаунтов не было.
