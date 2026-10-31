# Аудит внешних сигналов всей экосистемы: восьмой проход, 30 октября 2026 года

> Названия компонентов приведены к текущему бренду. Имена пакетов, URL и идентификаторы в исторических данных сохранены.

**Найдены два дополнительных внешних следа: опубликованные протокольные измерения трёх endpoint экосистемы у ShortformKit и ссылка на курс оркестрации в образовательной статье The Learning Standard. Нового подтверждённого прикладного внедрения или органического покупателя не установлено.**

База сравнения — [предыдущий проход](external-use-pass7-2026-10-30.ru.md) и накопленные аудиты. Новизна относится к проверенной базе свидетельств: события датированы 26 октября и 22 сентября. Наши тестовые покупки не включены в спрос; новых оплат не было.

## ShortformKit опубликовал результаты проб трёх наших MCP endpoint

[ShortformKit](https://shortformkit.com/free-remote-mcp-servers/) публикует список удалённых MCP без обязательной авторизации и [исходники своего наблюдателя](https://github.com/shortformkit/free-remote-mcp-servers). В зафиксированном [data/servers.json](https://github.com/shortformkit/free-remote-mcp-servers/blob/f01dd8642676fe17b55e4dd140f261494b03d951/data/servers.json), tested=2026-10-26, найдены три строки экосистемы:

| Компонент | Endpoint | Зафиксировано |
| --- | --- | --- |
| Attested Memory Market | https://hub.attestedmemory.net/mcp | 13 инструментов, включая market_search, market_invoke и pipeline_prepare |
| SYMMARTYS | https://modelmarket.dev/tools/mcp/emporion | 8 инструментов, включая vat_check, sanctions_screen, company_lookup |
| GAIA weather | https://modelmarket.dev/tools/mcp/weather | 3 инструмента: weather_now, air_quality_now, nearby_sensors |

Это данные инструментария, а не одна скопированная строка описания: опубликованный [генератор](https://github.com/shortformkit/free-remote-mcp-servers/blob/f7e6e06ca2721eaf47e9bd2b194a2501c478941d/scripts/make_directory.py) пропускает в выдачу строки со status=open из результатов проб и берёт оттуда имена/количество tools. Название, описание, website и repo при этом приходят из registry metadata.

У [CI job от 26 октября](https://github.com/shortformkit/free-remote-mcp-servers/actions/runs/40296344622/job/121483217640) завершены success шаги Fetch the registry, Test every remote endpoint и Build data and README. Прочитаны код и workflow по head SHA этого запуска. Выходной commit f01dd864 меняет README и два файла данных; его время соответствует завершению прогона. Это подтверждает согласованность опубликованных результатов с исполнением внешнего тестового workflow. Сырые ответы каждой MCP-сессии не опубликованы в прочитанном наборе и нами заново не воспроизводились.

[Probe-код](https://github.com/shortformkit/free-remote-mcp-servers/blob/f7e6e06ca2721eaf47e9bd2b194a2501c478941d/scripts/probe.py) выполняет initialize, уведомление notifications/initialized и tools/list. Страница говорит о двух запросах; в коде дополнительно отправляется уведомление. tools/call отсутствует. Читается одна страница tools/list, не полный обход cursor. Поэтому число tools — результат конкретного снимка, не актуальное обещание всей функциональности.

**Класс сигнала — внешнее автоматическое протокольное наблюдение.** Исполнение функций памяти, VAT-проверки или погоды, проверка подписей ответов, использование в продукте и платёж этим не установлены. У Memory зафиксированы общие Hub/pipeline tools; это не тест memory.write или memory.read.

Attested Memory также показан на [японской](https://shortformkit.com/ja/free-remote-mcp-servers/) и [корейской](https://shortformkit.com/ko/free-remote-mcp-servers/) версиях страницы. Это один оператор и один набор измерений с локализованным представлением. Три языка не считаются тремя независимыми рекомендациями.

Имя shortformkit-mcpscan уже встречалось в сохранённой статистике посетителей чужого Æfact; связь с нашими endpoint тогда не подтверждалась. Новое здесь — собственный опубликованный проект наблюдателя и его три конкретных результата по экосистеме. [Проверка прежних следов](../evidence/external-use-pass8-2026-10-30/novelty-check.json).

## Курс оркестрации попал в источники образовательной статьи

[The Learning Standard: How Autonomous AI Agents Are Redefining Student Research Skills](https://thelearningstandard.org/news/how-autonomous-ai-agents-are-redefining-student-research-skills), видимая дата **22 сентября 2026**, содержит в Sources прямую ссылку на [наш orchestration-course](https://github.com/alexar76/aimarket-courses/tree/main/orchestration-course). URL и ресурс alexar76 отсутствовали в проверенных прежних внешних свидетельствах этого издателя.

Это новая для базы **внешняя библиографическая ссылка на образовательный компонент**. В основном тексте курс отдельно не оценивается. Прохождение курса, выполнение labs, включение в университетскую программу, человеческое редакционное ревью и самостоятельная перепроверка учебных результатов не установлены. Публичная About-страница не разрешила эти вопросы. Разные домены двух находок также не устанавливают двух разных конечных владельцев.

## Дополнительные проверки внедрений и социальных упоминаний

- По локальным manifests отобраны 17 package/version: HESTIA, Metis, LOGOS, GAIA, ATLAS, SKOPOS, THEMIS, BASANOS, DOLOS, HELIOS, scaffold Python/npm, Attested Memory client, DIOSCURI, agent SDK и два operator kits. Уже прочитанный граф @aimarket/agent исключён до обращения. **16 дополнительных deps.dev ответили 200, все totalCount=0.** Это отдельные версии в одном индексе, не ноль private/manual/HTTP пользователей. Статус выбранных версий как latest не утверждается.
- Общий поиск внешних PR показал 401 результат; первая страница из 100 целиком принадлежит dependabot. После фильтра остаются четыре PR: три уже известных docs-вклада в AICOM и один PR нашего Pages-сайта. Последний не устанавливает внешнего runtime-внедрения; принадлежность его автора отдельно не исследовалась. Прежние docs-вклады не считаются новыми.
- Commit search по aimarket-metis, aimarket-hestia и aimarket-atlas вернул ноль. attested-memory дал 48 текстовых совпадений общих терминов; сообщения не содержат проверенных уникальных маркеров нашего клиента. Все их diff не исследовались, внешнее использование пакета не установлено.
- Старый pulsefeed radar и прежние собственные submissions снова исключены. Известные Industrial Platform, RugSnare, Enterprise Factory, MCPMoat, кошельки AER и наши paid tests не добавлены как новые находки.
- Новых атрибутируемых пользовательских постов в полученной выдаче соцсетей не подтверждено. Проверены X/Bluesky, LinkedIn/Threads, Reddit и отдельные языковые формулировки использования. Запрос, включавший Weibo, получил robots block; три остальных запроса того пакета выполнены отдельно, сам Weibo не повторялся.

Дополнительный поиск использовал точные домены и редкие имена по карте экосистемы: фабрика, Hub, SDK/bridges/desktop/playground, оракулы, ACEX/Pulse/Lottery/Monitor, Metis/HESTIA/LOGOS, red-team и assurance компоненты, HELIOS/DIOSCURI/THEOROS, школа/курсы, Cite Desks/Emberline, Independent AI с KOVA/AEGIS/CHARON, Attested, operator kits, PingBlip и Пантеон. Это групповой и точечный поиск, а не полное обследование каждого продукта на каждой площадке. В китайском, японском/корейском и других языковых запросах известные зеркала и собственные локализации повторно новыми не считались.

## Свидетельства и ограничения

В журнале **43 исполнения поисковых строк, 40 различных строк**; для 39 различных строк возвращены пакетные результаты. Один запрос с Weibo остался без доступной выдачи. Три повтора внутри текущего прохода относятся к восстановлению остальных запросов заблокированного пакета и не расширяют уникальный охват. Буквальная сверка с прежними структурированными query fields не выявила точных повторов прошлых проходов. Получение пакетного ответа не доказывает отдельное исполнение каждой строки. [Журнал поиска](../evidence/external-use-pass8-2026-10-30/query-index.json).

Сохранены **37 прямых публичных GET, все HTTP 200**; каждое тело сверено по SHA-256. В эти GET входят deps.dev, GitHub search, данные и код наблюдателя, три языковые страницы и образовательная статья. [Общий индекс](../evidence/external-use-pass8-2026-10-30/audit-index.json), [машинная сводка](../evidence/external-use-pass8-2026-10-30/summary.json), [три строки наблюдений](../evidence/external-use-pass8-2026-10-30/shortformkit-ecosystem-rows.json), [область пакетов](../evidence/external-use-pass8-2026-10-30/package-scope.json) и [локальная проверка](../evidence/external-use-pass8-2026-10-30/verify_evidence.py).

Нами выполнялись публичные чтения и локальная запись аудита. Новых покупок, paid APIs, invokes, сообщений, публикаций, установок, исполнения чужого кода, смены аккаунтов и GitHub/Gitea writes не было. Закрытые проекты, полный интернет и все способы реального использования не охвачены.
