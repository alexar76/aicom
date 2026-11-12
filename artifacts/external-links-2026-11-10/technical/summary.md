# Технические внешние ссылки: уточнение на 10 ноября 2026

Срез 19:04–19:09 UTC. База сравнения — `artifacts/external-signals-2026-11-09/code/report.ru.md`, основной отчёт 9 ноября, более глубокий social/regional проход 9 ноября и утренний `external-links-2026-11-10/report.ru.md`. Известные связи не объявлялись новыми. Выполнены 16 поисковых строк, три web-open и 31 первичный публичный GET: 29 ответов 200, один 308, один 404. Сохранены полные ограниченные тела, UTC, URL и SHA-256; проверка всех длин/хешей прошла.

## Подтверждённая свежая дельта

**Новый внешний ответ AgentAvow в ACS.** [kenneives, 10 ноября 03:07:41 UTC](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6757834108) исправил собственное прежнее описание HISTOR: по его сообщению, в MTL/1 1.1 дроби и целые >2^53 обрабатываются так же, как в профиле AgentAvow. Он оставляет два различия: число без представимого double, например 1e400, и отсутствующий description. Сопоставлены полные сохранённые списки комментариев: 25 вчера, 26 сегодня; добавился ровно этот ID. Это предметный внешний технический ответ, не принятый ACS стандарт или внедрение пакета. В самом новом комментарии нет нового href к нашим сайтам: это ответ аккаунту alexar76 о профиле HISTOR.

**Hugging Face changes viewer снова отдаёт данные.** Вчерашняя DatasetGenerationError в текущем первичном срезе не воспроизводится. [Dataset page](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions) возвращает 200, содержит changes/train и ссылки страниц, прежнего текста ошибки нет. [is-valid](https://datasets-server.huggingface.co/is-valid?dataset=alexar76%2Fhistor-mcp-tool-definitions) возвращает preview/viewer/search/filter/statistics=true. [splits](https://datasets-server.huggingface.co/splits?dataset=alexar76%2Fhistor-mcp-tool-definitions) показывает восемь configs, failed=[] и pending=[]. Дополнительный узкий [GET одной строки changes/train](https://datasets-server.huggingface.co/rows?dataset=alexar76%2Fhistor-mcp-tool-definitions&config=changes&split=train&offset=0&length=1) вернул 200, ровно одну строку, truncated_cells=[]. Это восстановленное начальное чтение конкретного subset. Полнота датасета не проверялась: HTML всё ещё помечает viewer-partial; файлы датасета не скачивались.

**Agent Forge читает более новую версию HISTOR.** Прямой [page GET](https://theagentforge.io/t/github.com%2Falexar76%2Fhistor) сейчас отдаёт первичный JSON: house-tester для **0.6.1**, worked, mcp-handshake, 9 ноября 07:04:13 UTC; сохраняется предыдущий report 0.5.2. Текущий [check API](https://theagentforge.io/api/v1/check?id=github.com%2Falexar76%2Fhistor) имеет verdict=insufficient, один owner, corroborated=false. Поисковая копия ещё показывает только 0.5.2. Это обновление автоматического тестирования одним внешним оператором, а не два новых пользователя. WARDEN по тому же API остаётся на известном единственном report 0.22.2 от 5 ноября.

## Сильные прежние связи и точные направления

| Источник | Точная связь | Что подтверждено сейчас |
|---|---|---|
| [RugSnare README](https://github.com/Paraphern/rugsnare) | DOI `10.5281/zenodo.23512760` | Прямая Markdown-ссылка, содержательная сверка своего корпуса с HISTOR. README побайтово совпадает со вчерашним. Известное переиспользование данных; новая runtime-интеграция не установлена |
| [ScraperWatch Outside check](https://scraperwatch.com/mcp-changes/) | HTML href `https://histor.modelmarket.dev` | Внешняя сверка от 1 ноября; следом сохранена поправка parser от 2 ноября. Counts в outside check относятся к данным до удаления. Адрес без завершающего `/` вернул 308, со слешем — 200 |
| [CrawlCheck spec](https://crawlcheck.io/spec/mcp-lockfile#jcs-v1) | Совместимость extras, без нашего href в spec | Основной текст spec и fixture не изменились с 9 ноября. Fixture extras буквально совпадает с текущим HISTOR record. Совместимость не превращена в новую входящую ссылку |
| [ACS разбор avp9-nexus](https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6545176155) | HISTOR domain, version DOI, pinned GitHub source | Содержательный внешний анализ по-прежнему доступен; это старый ответ 31 октября |
| [CrawlCheck в MCP Registry issue](https://github.com/modelcontextprotocol/registry/issues/82#issuecomment-6711079035) | HISTOR public servers API | Внешний ответ и ссылка 7 ноября сохранены, список comments прочитан полностью; нового внешнего ответа после базы не найдено |

CrawlCheck fixture `sha256-G44DGgW7+rp9YjMAaEG80Tm5RFoke8eYkrE6nGk69y8=` равен текущему `toolExtrasDigest` записи CrawlCheck в HISTOR, lastObserved **10 ноября 17:58:31 UTC**, 28 tools. Это повторная проверка одного опубликованного значения, не повторный независимый прогон 30 servers; подписи в этом проходе не проверялись.

## Где ссылка ещё не подтверждена или её нельзя считать новой

- **AgentAvow:** 8 ноября автор просил разрешения сослаться на нашу сверку. 10 ноября issue получило наш ответ. В текущем root README и [v1 README](https://github.com/AgentAvow/AgentAvow/blob/main/docs/standards/tool-manifest-digest-vectors-v1/README.md) нет HISTOR/alexar76/нашего href. Просьба о ссылке не является уже размещённой ссылкой. Все файлы репозитория на содержимое не прочитаны.
- **heldfast:** наш собственный interop report ссылается на него, но в прочитанном полном heldfast README нет HISTOR/alexar76/нашего URL. Входящая связь из этого файла не установлена.
- **[Canopii HISTOR](https://index.canopii.dev/server/io.github.alexar76/histor):** прямой HTML href к `github.com/alexar76/histor` подтверждён. Точный URL уже был в поисковом baseline 9 ноября; новое — первичное чтение. Это автоматическая карточка, не независимое применение сервиса.
- **[MCPWatch HISTOR](https://mcpwatch-zeta.vercel.app/servers/io.github.alexar76__histor/):** прямой GET ответил 404. Это состояние конкретной внешней карточки, не outage HISTOR.
- **[PR14 agent-skills-state-2026](https://github.com/basitalisandhu/agent-skills-state-2026/pull/14):** всё ещё open, merged=false, updated_at 28 октября. Main README не содержит HISTOR/alexar76. Собственное непринятое предложение не считается принятой внешней ссылкой.
- **[OpenAlex](https://openalex.org/W7223029314):** cited_by_count по-прежнему 0; это счётчик данного индекса, который не отменяет GitHub-цитирование RugSnare. HF downloads=295 при API-чтении — платформенный счётчик, не число независимых людей.

## Ограничения и файлы

В этой ветке нового доказанного коммерческого клиента, dependency или production runtime-внедрения WARDEN/HISTOR не установлено. Аккаунт третьей стороны и содержательный ответ не являются проверкой человеческой личности автора. Поиск публичен и ограничен; отсутствие результата не доказывает отсутствие использования. Метрики автоматических каталогов не считаются нашей телеметрией.

`findings.json` содержит классификацию, ownership, confidence, даты и source→target связи; `verification.json` — длины/хеши, дельту ACS и точное fixture/record совпадение. `http-index.json`, `extra-http-index.json`, `v1-http-index.json`, `hf-http-index.json`, `hf-row-http-index.json` описывают все 31 GET; рядом находятся `.raw`. Поисковые ответы — `search-01.json`…`search-04.json`, web-open — `open-05.json`, строки запросов — `query-log.json`.

Внешних сообщений, публикаций, GitHub writes, invokes, tools/call, оплат, установки чужих пакетов или выполнения чужого кода не было.
