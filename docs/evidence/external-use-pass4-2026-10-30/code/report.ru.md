# Проверка новых downstream внедрений 30 октября 2026 года

**Нового независимого внедрения, runtime-клиента или атрибутируемого внешнего упоминания в этой ветке не установлено.** Проверен дополнительный слой отдельных Hub plugins и embeddable widget. Известные Industrial Platform, RugSnare, MCPMoat, QuincyGB, traits-dev, agent-exec и наша покупка Agent402 не пересчитываются.

## Отдельные plugins и widget

deps.dev вернул HTTP 200 и totalCount=0 для 13 выбранных package/version:

- PyPI: aimarket-safety 2.0.1, aimarket-channels 2.0.1, aimarket-tee 2.0.1, aimarket-reputation 2.0.1, aimarket-orchestrator 2.0.0, aimarket-streaming 2.0.1, aimarket-mcp-packager 2.1.3, aimarket-zk 2.1.1, aimarket-data-cap 3.0.0 и aimarket-dataset 2.0.0.
- npm: @aimarket/widget 0.1.1, @aimarket/hub-client 0.0.1 и @aimarket/sdk 0.0.1.

Это счётчики зависимостей конкретных версий в одном публичном индексе. Они не устанавливают число установок, приватных приложений, ручного использования или HTTP-вызовов. Версии выбраны по локальным package manifests; их статус как самых новых выпусков не утверждается. Никакого внешнего зависимого пакета для дополнительной атрибуции в ответах не появилось.

## Commit и repository search

Выполнены десять новых запросов публичного GitHub API:

- commit search по aimarket-safety, aimarket-channels, aimarket-mcp-packager и @aimarket/widget;
- README repository search по safety и packager;
- commit search по AWR-PROOF, TOOL_DEF_CROSS_TOOL, TOOL_DEF_SECRET_HARVEST и attestedmemory.net.

По packager получены десять commit-совпадений: два старых commit SHA собственного awesome-list submission, размноженные по пяти копиям списка. Четыре README-результата также являются каталогами. Это не десять внешних внедрений или новых рекомендаций.

AWR-PROOF вернул один нерелевантный авиационный commit с текстом AWRS proofing. Остальные reason-code/origin запросы не вернули совпадений. Это ограничение конкретных запросов, не полный поиск по чужому коду.

Двенадцать web-запросов по редким AWR/MTL-маркерам, WARDEN finding codes, widget embed syntax, optional plugins и library/config fingerprints дали собственные README, реестры и известные каталожные страницы. Новых атрибутируемых кандидатов не установлено.

## Свидетельства и ограничение подсчёта

Сохранены актуальные ответы **23 различных публичных URL**, все HTTP 200, каждое тело проверено по SHA-256. Это 13 графов и десять поисковых API-запросов. Индекс — [verification-index.json](verification-index.json); выбранная область — [scope.json](scope.json) и [followup-queries.json](followup-queries.json).

Фактически выполнены **42 GET**: при импорте первоначального helper повторно запустились первые 19 чтений. Побочный запуск исправлен защитой __main__. Повторные обращения не расширяют охват, не добавлены к 23 различным URL и не считаются дополнительными находками. Сохранены последние снимки этих URL; первые перезаписанные тела не выдаются за отдельно верифицированные captures.

Никакие аккаунты или authentication не менялись. Публикаций, сообщений, GitHub writes, платежей, установки и исполнения чужого кода в этой ветке не было. Покупка Agent402 принадлежит отдельной пользовательской проверке и не является органическим спросом.

