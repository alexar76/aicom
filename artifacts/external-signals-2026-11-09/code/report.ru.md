# Внешний код и технические ответы: срез 9 ноября 2026

Проверка выполнена публичными GET и web-поиском, без авторизации, публикаций, GitHub writes, invokes, платежей, установки пакетов или исполнения чужого кода. Сильнейшая новая связь — внешний разработчик CrawlCheck переносит совместимую с HISTOR форму extras в свой опубликованный интерфейс. Одновременно старый внешний endpoint Industrial Platform больше не отвечает: четыре прежних маршрута вернули 404. Нового органического покупателя или нового подтвержденного production-внедрения этот проход не установил.

## CrawlCheck: внешняя совместимость, с точно ограниченной проверкой

7 ноября Emmanuel Orta [опубликовал собственную сверку трех наблюдателей](https://github.com/modelcontextprotocol/registry/issues/82#issuecomment-6711079035): 30 registry remotes, 479 tools, живые чтения 17:16–17:18 UTC; сообщил 30/30 совпадений MTL/1 над прочитанными им bytes с HISTOR. Это **его измерение**. В этой проверке мы не повторяли 30 чтений и не проверяли его сырые серверные ответы.

В [дополнении 18:26 UTC](https://github.com/modelcontextprotocol/registry/issues/82#issuecomment-6711311079) он сообщил, что `jcs_v1.extras_sha256` теперь берет HISTOR scope: все члены, кроме name/description/inputSchema/outputSchema, в форме `{"tools":{name:extras}}`. Он сообщил 30/30 совпадений extras, включая десять пустых. При этом прямо назвал три потенциальных расхождения кодировок: astral names, integral floats и integers > 2^53. [Ответ 19:39 UTC в OWASP](https://github.com/OWASP/secure-agent-playbook/issues/33#issuecomment-6712103956) подтверждает изменение и один конкретный hash. Человеческая личность и независимость оператора отдельно не проверялись; это опубликованные ответы аккаунта, который заявляет, что ведет CrawlCheck.

Что проверили мы непосредственно:

- [Текущая публичная спецификация](https://crawlcheck.io/spec/mcp-lockfile#jcs-v1), GET 200: в ней действительно расширен extras scope, присутствуют объект tools, предел 16,384 bytes на tool и 262,144 общий, oversized/omitted; changelog 7 ноября прямо фиксирует прежний scope title/annotations/icons. Спецификация все еще говорит RFC 8785 для extras; полное равенство со всеми Python JSON corner cases этим не доказано.
- [Закрепленный fixture](https://github.com/emmanuelorta/crawlcheck-core/blob/c634f497bd5873c2b2bd9f3ca9a26b188e08ac2a/sdk/test/fixtures/continuity.json), commit [c634f497](https://github.com/emmanuelorta/crawlcheck-core/commit/c634f497bd5873c2b2bd9f3ca9a26b188e08ac2a), **7 ноября 18:58:51 UTC**, содержит `jcs_v1.extras_sha256` в signed-baseline fixtures. Pinned и main bytes совпадают (SHA-256 29232877cc77953e…). Это публичный артефакт интерфейса и тестов, **не найденный diff реализации hosted canonicalizer**. В прочитанных JS continuity и Python lock SDK hosted canonicalizer не реализован.
- Наш GET [текущего HISTOR record CrawlCheck](https://histor.modelmarket.dev/api/v1/servers?q=io.github.emmanuelorta/crawlcheck), 9 ноября 19:26 UTC, показывает тот же `toolExtrasDigest`: **sha256-G44DGgW7+rp9YjMAaEG80Tm5RFoke8eYkrE6nGk69y8=**. Fixture `baseline_cases[0].lock.jcs_v1.extras_sha256` равен ему буквально. HISTOR lastObserved=2026-11-09T17:58:56Z, 28 tools. Наша проверка — один fixture и одна текущая запись; подписи fixture/HISTOR здесь не проверялись.

Это сильнее простой каталожной ссылки: внешний интерфейс и спецификация согласованы с конкретной конструкцией HISTOR, и опубликовано совпадающее значение. Это не установка aimarket-histor как зависимости и не коммерческий клиент.

## ACS: сторонние исследователи действительно читают HISTOR

- [avp9-nexus, 31 октября](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6545176155): разобрал snapshot 20 октября и source 410ee41; пишет о 250 label reads и сверке file hashes. Его содержательный вывод — names-only не равнозначен отсутствию чтения: старый профиль отказывал части numeric schemas. Сам не проверял подписи labels; выборка не census. Мы подтвердили наличие и содержание комментария, а не воспроизвели его выборку.
- [Mayur021, 2 ноября](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6572123939): сообщает, что прочитал HISTOR code, проверяет объяснение предыдущего автора, и требует profile identifier рядом с digest. [Следующий ответ](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6572965082) требует outputSchema и определения preprocessing. [Ответ 09:22](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6573529015) рассматривает двухдайджестную форму HISTOR как вариант для ACS.
- [AgentAvow, kenneives, 8 ноября](https://github.com/AgentAvow/AgentAvow/issues/240#issuecomment-6714769340) признает нашу независимую реализацию из README и просит разрешение сослаться на нее. Это внешний технический ответ, не уже добавленная ссылка или установка HISTOR.

ACS issue остается open. Нормативное принятие proposal, внедрение Guardian и человеческий характер всех account replies не установлены. Это влияние на обсуждение и независимый разбор данных, без утверждения о принятом стандарте.

## Что осталось от прежних сильных кейсов

**Industrial Platform.** [requirements main](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/aimarket-sentinel/requirements.txt) по-прежнему содержит git pin на `alexar76/aimarket-hub@2310569f…`; [AIMarket adapter source](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/gateway/aimarket-federation.mjs) доступен. Но discovery, v2 manifest, /health и /.well-known/x402 на прежнем Railway host все вернули **404** 9 ноября около 19:23–19:24 UTC. Исторический CI-успех из прежнего аудита не отменен, но живое участие этого endpoint в федерации сегодня не подтверждено. Это один ограниченный срез, не доказательство прекращения проекта или отказа от Hub вообще.

**RugSnare.** [Текущий README](https://github.com/Paraphern/rugsnare) сохраняет содержательное использование HISTOR snapshot и DOI: сравнение своего watch corpus, ссылки на method/dataset. Известный кейс, не новый клиент. Новая runtime-интеграция HISTOR в прочитанном README/tree не установлена.

**QuincyGB.** [AICOM#13](https://github.com/alexar76/aicom/issues/13) содержит 8 comments; последний внешний ответ 30 октября 14:14:59 UTC, новых ноябрьских ответов нет. Автор снова подтверждает изменения persistence, pricing, contract stability и feed вследствие наших review. RouteVerdict /health сейчас 200 с persistent store; Recheck feed v2 200. Запросы modelmarket в feed произошли из согласованных платных тестов, не органический спрос.

**traits-dev.** Сохраняется прежний единственный commit search hit по `@aimarket/warden`: классификационная работа с релизом 0.18.0. Новое внедрение WARDEN из этого не следует.

## Новые автоматические наблюдения не равны пользователям

**The Agent Forge.** [WARDEN page](https://theagentforge.io/t/npm%3A%40aimarket%2Fwarden) в web-index перечисляет два `house-tester` handshake, 0.21.0 и 0.22.2, по 9 tools. Live GET [check API](https://theagentforge.io/api/v1/check?id=npm%3A%40aimarket%2Fwarden), 9 ноября, дает один worked report на 0.22.2 от 5 ноября 04:00:20Z, `corroborated=false`, zero corroborations, verdict insufficient. [HISTOR page](https://theagentforge.io/t/github.com%2Falexar76%2Fhistor) описывает uvx handshake 0.5.2 с 3 tools; его live API тоже insufficient. Это один внешний автоматический тестер, а не несколько пользователей. Сырой page GET вернул app shell; авторство house-tester установлено по индексированному содержимому страницы, не из текущего JSON API. Функции scanner/wrap и HISTOR tools/call этим не проверены.

**ShortformKit.** [servers.json](https://github.com/shortformkit/free-remote-mcp-servers/blob/main/data/servers.json), tested=2026-11-09, содержит Attested Memory (13 tools), domain demo (1 tool), weather (3 tools). Это текущий протокольный индекс, прежний оператор. Отсутствие EMPORION в этой конкретной выдаче не доказывает outage.

**ragmap.** [Новый для проверенной базы каталог](https://github.com/khalidsaidi/ragmap) содержит EMPORION, 8 tools, `lastOk=2026-11-09` в [data/servers.json](https://github.com/khalidsaidi/ragmap/blob/main/data/servers.json). Это внешняя индексированная запись с датой наблюдения. Реальное выполнение VAT/санкционных функций и оплаченный спрос не установлены.

## Область и доказательства

Сырые ответы в *.raw; URL, UTC, HTTP status, bytes, SHA-256 — пятью capture-index JSON и commit-index.json. `verify_evidence.py` сверяет все captured bodies и конкретный fixture/record match, результат в verification.json. Web search/open ответы сохранены в web-results.json.

Пять GitHub searches: issues по identity/domain, commits Hub/WARDEN, README repos по domain. Own mirrors, старые owner submissions, bot radar, awesome forks и одноименные проекты исключены вручную. Поиск не полон, не включает private code, и `-author` не исключает собственный repository; такие Hub sync commits в результаты внедрений не включены. GitHub authenticated code search и dependencies graph не выполнялись. Отсутствие нового кандидата в этой выборке не означает отсутствие пользователей.
