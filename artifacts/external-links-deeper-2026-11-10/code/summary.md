# Чужой код и зависимости — углублённая проверка 10 ноября 2026

**Нового подтверждённого импорта наших пакетов, production-интеграции или исполнения бизнес-функций этот кодовый проход не установил.** Найден дополнительный generated wiki mirror; его provenance проверен и он исключён из независимых обзоров и внедрений. Отдельный новый кандидат с AIMarket Courses передан в корневую ветку для проверки учебной working branch.

Проверка выполнена примерно **19:16–19:22 UTC / 20:16–20:22 Europe/Amsterdam**. База — предыдущий вечерний `artifacts/external-links-2026-11-10/review.ru.md`, кодовый и пакетный отчёты 9 ноября, pinned исключения 26–30 октября. Прежние agent-exec/Industrial manifests в этой ветке повторно не проверялись; новых интеграций из их старой доступности не выводили.

## Проверенные исходники

| Источник | Что установлено на закреплённом source | Класс и новизна |
|---|---|---|
| [ShortformKit probe](https://github.com/shortformkit/free-remote-mcp-servers/blob/6e610a542f6dc5f996b0675d25f9477e92a154ee/scripts/probe.py#L39) | Код делает initialize, initialized, tools/list; tools/call в прочитанном файле нет. [README](https://github.com/shortformkit/free-remote-mcp-servers/blob/6e610a542f6dc5f996b0675d25f9477e92a154ee/README.md#L319) содержит Attested Memory endpoint | Реальный код протокольного наблюдателя, известный 9 ноября. Не потребление memory business functions и не новый клиент. Head9 ноября; новый source diff не установлен |
| [API Evangelist Attested Memory](https://github.com/api-evangelist/attestedmemory-net/blob/47195dfdb23ceea795b85f891e8c09608e590cbf/README.md#L73) | Полное pinned tree содержит только `.gitignore` и README. Каталог API/schema/skills ведёт на APIs.io | Generated профиль документации, известный 9 ноября. Импорта нашего Python пакета или runtime-кода в этом repo нет |
| [MCP Serverlist config record](https://github.com/tonylate520/mcp-serverlist/blob/a6cf429b3a9fa1caf0b49176a47ec158def2cea3/cli/lib/servers.json) и [configManager](https://github.com/tonylate520/mcp-serverlist/blob/a6cf429b3a9fa1caf0b49176a47ec158def2cea3/cli/lib/configManager.js) | Код способен записать выбранный config в файл клиента; наша запись задаёт Node.js и `npx -y alexar76/aimarket-plugins` | Config/template only. Успешного запуска не доказано; несоответствие Python packager уже отмечено 26 октября. Генератор сам по себе не является установкой |
| [Hexsecs Gateway card](https://github.com/hexsecs/awesome-kb-mcp-servers/blob/030cb01da9aa222cae5efcfb9ea15c71076183db/wiki/alexar76-aimarket-mcp.md#L7) | Прямая ссылка на наш repo; `depth: stub`, `status: unknown`; explicit upstream commit и source date | Дополнительный найденный generated mirror, docs-only. Не независимая проверка и не применение Gateway |

## Почему Hexsecs не считается новым внедрением

Публичный GitHub repo search по точному `alexar76 in:readme -user:alexar76` вернул12 repos, включая `hexsecs/awesome-kb-mcp-servers`. Exact имя этого repo не найдено в просмотренной прежней локальной базе. Однако событие датировано отдельно: upstream README захвачен4 ноября, текущий merge commit — **6 ноября06:12UTC**. Поиск обнаружил его сегодня; это не новая публикация10 ноября.

Описание GitHub всё ещё говорит о parked placeholder, но [текущий pinned README](https://github.com/hexsecs/awesome-kb-mcp-servers/blob/030cb01da9aa222cae5efcfb9ea15c71076183db/README.md#L3) уже содержит OpenShelf KB. Его текст прямо объясняет происхождение из awesome list и отсутствие независимой проверки статуса. Полное tree не усечено; в нём есть пять wiki paths с нашим namespace, но в этой ветке отдельно прочитана Gateway card, а не все пять карточек.

[Capture metadata](https://github.com/hexsecs/awesome-kb-mcp-servers/blob/030cb01da9aa222cae5efcfb9ea15c71076183db/raw/2026-11-04/capture.json) фиксирует `punkpeye/awesome-mcp-servers@29f2d490cc02468e7c9d87b0cf68d40d3041e7ef`. Прочитан и [ingest.py](https://github.com/hexsecs/awesome-kb-mcp-servers/blob/030cb01da9aa222cae5efcfb9ea15c71076183db/tools/ingest.py): это обработчик списка и генерация карточек. Он не устанавливает или вызывает наш сервис. Поэтому зеркало не добавлено к независимым обзорам, пользователям или интеграциям.

## Courses: новый кандидат остаётся задачей до проверки реализации

Корневая ветка нашла [S-AI-Projects/free-programming-books issue5](https://github.com/S-AI-Projects/free-programming-books/issues/5) со ссылкой на AIMarket Courses и предложением реализовать `tools/course_checks/r10-t041.py`. В этой ветке точный default-branch commit history по этому пути вернулHTTP200 и пустой массив.

**Это узкая проверка default branch, не общий вывод об отсутствии реализации.** В issue указана отдельная working branch `student/e26b07f1180`; корневая ветка дополнительно проверяет её, PR и происхождение fork. Итоговую атрибуцию нужно брать из корневых свидетельств углублённого прохода. Само содержимое issue этой веткой повторно не читалось. Выполнение checker, применение SDK и использование курса человеком на основании одной задачи не утверждаются.

## Дополнительные отрицательные проверки

- Публичные списки forks для Hub, Agent и Metis вернули пустые arrays. Это не отсутствие private forks, копий или любых интеграций.
- Один уровень публичных репозиториев Industrial Platform дал прежний agent-tools repo, два октябрьских fork и `.github`. Нового смежного source case не найдено; старый endpoint повторно не вызывался.
- Исправленный commit search `aimarket-hub -user:alexar76` дал0. По `aimarket-mcp` —17 hits: старые собственные submissions/merge commits, их copied history и одноимённый `aidotmarket`. История собственного добавления в чужой awesome list не является независимым применением.
- `aidotmarket/aimarket-mcp-server`, `sev7n4/aimarket`, `bracha55555-hue/aimarket`, `sep163/aimarket-agents` и `igor-holt/momus` сохраняются в прежних исключениях. Старые pinned проверки установили иные origins, workspace-local namespaces или явное различение проектов. Нового кода, меняющего атрибуцию, выборка не показала; весь их current source в этом проходе заново не читался.
- Точный README search по `modelmarket.dev` вернул прежний `khalidsaidi/ragmap` и awesome copies. Ragmap уже разобран9 ноября; search metadata не считается новым runtime diff.

## Охват и воспроизводимость

Сохранены **25 поисковых строк:12 web,9 repository searches,4 commit searches**. Две начальные commit queries с `-author:alexar76` не исключили собственные repos, поэтому их hits не использованы как внешнее принятие; сохранены исправленные queries с исключением владельца и выполнена ручная фильтрация. Один начальный broad commit result имел43 hits, а первая страница30; полный охват по нему не заявляется. Исправленный owner-excluded Hub query вернул0.

Всего **35 публичных unauthenticated GET, все HTTP200**, включая поисковые API, три fork list, один соседний repo list, четыре pinned tree и девять конкретных source files. Все35 тел полные; длина и SHA256 проверены. Метаданные и тела лежат в `github-*.json`, `primary-*.json`, `bodies/`; выводы и точные source→target связи — `findings.json`, целостность — `capture-integrity.json`.

GitHub repository search не является полным code search. Закрытые репозитории, приватные deployments, неиндексируемый код и фактический спрос не охвачены. Код сторонних проектов рассматривался как данные: его не устанавливали и не запускали, packages не скачивали, аккаунты не использовали, операторам не писали, tools/call/платежей/GitHub writes не выполняли. Локальная сборка выводов и проверка bytes: `python3 artifacts/external-links-deeper-2026-11-10/code/build_findings.py`.
