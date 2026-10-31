# Технические внешние сигналы alexar76 — 30 октября 2026

Срез публичных первоисточников около **06:55–06:59 МСК**, с сопоставлением со сводками 28 октября. Все сетевые действия — публичные GET; аккаунты не переключались, сообщений, tool calls внешних сервисов, установок, публикаций и GitHub writes не было.

## Что изменилось после 28 октября

**MCP issue3431: 19 → 22 комментария; из трёх добавленных два внешних.**

- [Paraphern, 28 октября 20:24 МСК](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431#issuecomment-6475879932) согласился сохранять launch arguments вместе с точной версией пакета. Он прямо ссылается на сверку alexar76: один и тот же пакет MongoDB с `--readOnly` и connection string и при bare launch показывал разную поверхность — на девять write tools больше. Это внешнее содержательное использование результата сверки в обсуждении.
- [basitalisandhu, 29 октября 21:22 МСК](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3431#issuecomment-6504918640) продолжил обсуждение актуальных версий и CI-проверки документации, поддержал пример MongoDB. Указанные им версии сторонних пакетов отдельно в этом проходе не проверялись.
- Третий новый комментарий принадлежит самому alexar76 и внешней реакцией не считается.

Это продолжение технического диалога. Решение команды MCP, merge документации или принятие предложенного стандарта не установлены.

**AgentDojo: новый предметный ответ на наш аудит.**

[RexHuang, 29 октября 15:59 МСК](https://github.com/ethz-spylab/agentdojo/issues/235#issuecomment-6497336759) подтвердил противоречие mention/recommendation в `InjectionTask6`; самостоятельно отметил, что не является maintainer. После нашего ответа [30 октября 04:14 МСК](https://github.com/ethz-spylab/agentdojo/issues/235#issuecomment-6512480723) он принял исправление описания Tasks0–5, выделил наш разбор 123 flagged runs как ключевые данные и предложил подготовить strict variant либо упаковать наш classifier при решении maintainers. Ветка содержит три комментария, один наш.

Это **две внешние реакции одного участника**. Независимая повторная разметка 123 runs, принятие изменений и решение maintainers не подтверждены. Числа из нашего комментария не превращаются во внешне воспроизведённые измерения, когда собеседник их повторяет.

**Vulnetix5: 10 → 11 комментариев, но добавился только наш ответ.** Последний новый комментарий alexar76 создан 29 октября 09:03 МСК; `updated_at` ветки29 октября09:35 МСК отражает также правку. [Наше сообщение](https://github.com/Vulnetix/advisory-database/issues/5#issuecomment-6489285683) перечисляет исправленные опубликованные версии и просит обновить девять записей. Нового внешнего подтверждения этих исправлений после среза28 октября в комментариях нет. Внешний аудит и текущий статус самих advisory-записей здесь не воспроизводились.

**HISTOR PR14 остаётся open/unmerged.** [PR](https://github.com/basitalisandhu/agent-skills-state-2026/pull/14): `merged=false`, `merged_at=null`, последнее `updated_at=2026-10-28T09:48:32Z`. Готовность автора обсудить включение HISTOR ещё не равна принятой ссылке в main.

## Новые для прежних сводок обнаружения

**FPL Cat — самостоятельное атрибутированное упоминание HISTOR.** [Статья оператора MCP](https://fplcat.com/blog/ai-agents-playing-fantasy-premier-league) опубликована **13 октября** (видимая дата и `BlogPosting.datePublished/dateModified` совпадают). В таблице посетителей указан `histor/0.1.0`, **39 запросов** и прямая ссылка на `https://histor.modelmarket.dev/`; назначение описано как журнал изменения определений инструментов. Автор сообщает, что разбирал посетителей с помощью Claude.

Это внешнее наблюдение исходящего краулера и ссылка на наш проект. Оно сильнее неатрибутированного совпадения user-agent, но не доказывает клиента HISTOR, потребление его данных или независимую проверку криптографии. 39 — запросы в описанном автором историческом срезе, не пользователи и не текущее число. Находка новая для сводок, материал старше текущего окна. Проверка сырых логов FPL Cat не выполнялась. См. [факт с метаданными](fplcat-fact.json).

**AICOM использован как источник автоматического code review в японском проекте.** [CodeRabbit, Next-Store PR28, 16 сентября05:58 МСК](https://github.com/myoshi2891/Next-Store/pull/28#discussion_r4022105489) ссылается на `alexar76/aicom/blob/main/web/frontend/eslint.config.mjs` при рекомендации native ESLint flat config без FlatCompat. Предыдущий аудит оставлял эту ветку неподтверждённым кандидатом; теперь прочитаны все52 issue comments и100 review comments первого ответа API, точный review найден в них. Это автоматическая внешняя ссылка на инженерный пример, не человеческая рекомендация и не внедрение AICOM. Полнота всех review comments сверх полученной страницы не заявляется.

Поиском также найден [Sanka DataSet](https://sanka.com/research/apps/dataset/) с заголовком нашего Show HN. Прямой GET получил308; полный материал и точная исходящая ссылка не прочитаны. Оставлен как поисковый след агрегатора, не новый независимый обзор.

## Что продолжает подтверждаться

- [MCPMoat competitors.md](https://github.com/Ducarv/mcpmoat/blob/dev/docs/competitors.md): SHA-256 `6a815d0d11b3b855d29990ef4995bca806a627f4ef4609e22eebfeebc375f638`, ровно как28 октября. Содержательное изучение WARDEN внешним проектом сохраняется; нового внедрения не установлено.
- [RugSnare README](https://github.com/Paraphern/rugsnare#independent-measurements) и [Shopify page](https://github.com/Paraphern/rugsnare/blob/main/docs/servers/shopify.md) по-прежнему содержат HISTOR и сверку данных. Это известное внешнее применение, не новый пользователь за двое суток.
- [Industrial Platform requirements](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/aimarket-sentinel/requirements.txt) всё ещё pin `alexar76/aimarket-hub` commit `2310569f1e4e50e1062d80725bd69ae313042a69`; [discovery](https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json) и [manifest](https://x402-gateway-production-1f21.up.railway.app/ai-market/v2/manifest) доступны HTTP200. Ранее установленное использование пакета в CI сохраняется; в этом проходе внешние CI и подпись manifest заново не проверялись, invoke и оплаты не выполнялись.
- [Hlido scorecard](https://github.com/ankitkapur1992-hlido/hlido-public/blob/main/scorecards/alexar76-aimarket-plugins.json):60/100, low confidence, `run_at=2026-08-05T12:00:00Z`. Свежесть репозитория не обновляет дату этого обзора.

## Каталоги и граф пакетов

[Small Print WARDEN](https://smallprint.dev/a/npm/%40aimarket/warden) в прямом HTML уже содержит **22 версии до0.22.2**, file fingerprint для0.22.2 и дату chain28 октября. Поисковый снимок ещё показывает9 версий до0.8.2. Прямая страница — текущая проверенная опора. Это продолжающееся внешнее автоматическое наблюдение опубликованного пакета, а не22 клиента или22 аудита безопасности.

[Odel](https://odel.app/modules/alexar76), [Canopii Plugins2.1.2](https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins/2.1.2), [ProtocolProbe MCP-security](https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security) и [Attested Memory](https://protocolprobe.com/mcp/servers/io.github.alexar76/attested-memory) прочитаны повторно. Canopii96/100 — рубрика анализатора; ProtocolProbe срез23 октября — read-only connection/tools/list и отдельные модельные пробы25–26 октября, без вызовов tools. Нового пользовательского отзыва или сертификации они не устанавливают. Прямой GET Glama завершился TLS-error; PulseMCP403; Smithery308. Эти ответы не приравниваются к отсутствию карточек.

PyPI однозначно связывает **aimarket-histor0.5.1**, aimarket-hub3.16.3 и aimarket-agent2.6.1 с alexar76. Одноимённый пакет **histor0.1.2 принадлежит historlabs/histor** и исключён. Перепроверка старых raw подтверждает:28 октября использовали правильный `aimarket-histor`; сокращение в прежней сводке не было ошибкой namespace.

deps.dev теперь отвечает200 и0 dependents для WARDEN0.22.2 и aimarket-histor0.5.0 (28 октября соответствующие версии были404). Для aimarket-histor0.5.1, aimarket-agent2.6.1 и Hub3.16.3 —404. Для WARDEN0.8.2 и agent2.6.0 —по одному direct dependent, как в прежнем проходе; происхождение этих зависимых пакетов заново не читалось. Нули — только индекс конкретной версии;404 — отсутствие доступной записи, не ноль пользователей. npm API отдаёт WARDEN1488 downloads за22–28 октября; установки CI, собственные и автоматические скачивания не отделяются.

## Область проверки

В [search-results.json](search-results.json) сохранены полные ответы24 целевых web-запросов. Дополнительно [verification-index.json](verification-index.json) содержит51 публичный GET с временем, статусом и SHA-256:42 HTTP200,4 HTTP404,3 HTTP308,1 HTTP403 и1 TLS-error. GitHub repository search по `alexar76 in:readme -user:alexar76` вернул11 репозиториев, как28 октября; чужие проекты, собственные comments в чужих ветках, зеркала и бот-агрегаторы классифицированы отдельно. Поиск не охватывает весь код GitHub и закрытые источники.

Главная новая динамика — ответы в двух предметных технических ветках. Главные новые атрибутированные обнаружения — статья FPL Cat и автоматическая ссылка CodeRabbit на ESLint-конфиг AICOM. Нового подтверждённого независимого внедрения сверх известного Industrial Platform и применения HISTOR в RugSnare этот проход не установил.
