# Внешние тесты и документы — 28 октября 2026

Проверка около 18:00–18:04 МСК: 20 web-запросов, шесть публичных GitHub issue search и семь дополнительных GET. Всего 13 прямых GET, все HTTP200. Публикаций, сообщений, авторизаций, установки пакетов и исполнения стороннего кода не было.

## Новый подтверждённый источник: ProtocolProbe

[Карточка dev.modelmarket/mcp-security](https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security) и её [публичный JSON API](https://protocolprobe.com/api/v1/servers/dev.modelmarket/mcp-security) прямо связывают сервер с `https://modelmarket.dev/tools/mcp/security`, `alexar76/warden` и названием WARDEN/HISTOR. Это наш remote MCP security endpoint версии1.0.0, а не одноимённый продукт.

ProtocolProbe сообщает о реальной read-only сессии **23 октября 03:46:16UTC**: соединение531мс, весь проход3730мс, четыре tools, ноль resources/prompts. Обнаружены `warden_scan`, `histor_check`, `tool_list_cost`, `x402_check`. Из18 классов проверок exercised только2; tools/call не выполнялись. Показатель5/5 record checks — проверка публичных записей/репозитория, не оценка безопасности. Названные серверы не получают security score. Это дополнительное внешнее измерение достижимости и опубликованного каталога, не пользовательское внедрение или полный аудит.

Есть ещё внешнее исследование **чтения нашего tool list тремя моделями25–26октября**: по даннымAPI GPT-5-nano сгенерировал `warden_scan` с валидными по схеме аргументами; Haiku дал ответ без tool call; Gemini получил malformed-function-call. Модельный вызов здесь не отправлялся серверу — это запись выбора/валидации генерируемых аргументов. Эти единичные результаты не доказывают преимущество модели или поведение настоящего MCP-клиента.

Сайт также публикует 1257 tokens по Anthropic count_tokens для указанного им идентификатора `claude-opus-5-5` (проверка 24 октября). Это измерение представления списка, а не наш счёт за запросы. AI-классификации текста отдельно отмечены: в частности `x402_check` отнесён к financial/data-changing, хотя publisher annotation read-only=true; фактическое действие tool не проверялось.

Прочитана [методология](https://protocolprobe.com/methodology): авторы явно ограничивают тест чтением каталога и публичных записей. API данные лицензированы **CC BY4.0**, требуют attribution ProtocolProbe, ссылку на карточку и asOf/check date. Время получения наших ответов28октября не заменяет даты их измерений.

Evidence: `measurement-pages.json`, `measurement-methods-api.json`, `protocolprobe-fact.json`.

## Новый подтверждённый источник: Canopii Trust Index

[Карточка AIMarket Plugins](https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins) и [версия2.1.2](https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins/2.1.2) прочитаны HTTP200. Точный registry name `io.github.alexar76/aimarket-plugins`, ссылка на наш репозиторий; объявлены25tools. Показаны **96/100, Grade A, confidence92%, rubric2.11.0**.

Это балл сторонней рубрики по доступным исходникам/метаданным/истории версий, не доказательство полного аудита, запуска всех25tools или клиентов. На странице есть предупреждение о non-strict JSON schemas и limited adoption; эти наблюдения отдельно нами не воспроизводились. Точную дату скана в полученном видимом тексте/тегах time не удалось установить, поэтому не выдаём её за октябрьскую проверку или текущую гарантию безопасности. Пометки каталога вроде publisher-verified — утверждения каталога, отдельная проверка владения нами не проводилась. Никакие claim/login ссылки не нажимались.

Evidence: `measurement-pages.json`, `measurement-methods-api.json`. Даты28октября в HTTPmetadata — наши даты чтения.

## Закрытые пути и ограничения

- Дополнительных внешних fixtures/интеграций exact `@aimarket/warden`, HISTORfiles и `manifest_canonical` в проверенном наборе не подтверждено. Общие имена canonical/AWR дают множество посторонних проектов; словоAWR/2 в GitHub разбивается на широкие совпадения. Из359 найденных объектов прочитана только возвращённая первая страница, не заявляется полный аудит этой выдачи.
- [MCP issue3430](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/3430) прочитан вместе со всеми семью возвращёнными комментариями. DOI HISTOR находится в наших сообщениях alexar76; Paraphern обсуждает pinning routing metadata, но не даёт новой явной ссылки на HISTOR. Смежная реплика peach420fuzz ведёт к его собственному ProductionDesk. Не засчитываем как новое цитирование/использование датасета. Последний комментарий27октября — наша корректировка чисел, не новый внешний отклик.
- Exact ссылки WARDEN/ARGUS в GitHub comments вернули известный CodeRabbit/HypatiaPR83; повторно не считаем находкой. GitLab/Codeberg/sr.ht/Sourcegraph web-пути не дали нового атрибутируемого кода; Codeberg/sr.ht ограниченыrobots.
- PyPI package-mirror simple indexes, старые GitHub proxy mirrors, собственная Qiita, Odel/Glama/MCPRepository/SmallPrint/EnterpriseDNA и другие известные каталоги не считались новыми независимыми обзорами. Grep.app после предыдущего429 не использовался.

Все20web-запросов и полные результаты — пять `search-N.json`; перечень — `query-log.json`. 13GET с URL/временем/статусом/SHA256 — `verification-index.json`.
