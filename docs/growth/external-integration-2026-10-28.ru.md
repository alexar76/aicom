# Внешнее CI-использование AIMarket Hub и новые измерения — 28 октября 2026

Продолжение [проверки внешнего manifest](external-cases-2026-10-28.ru.md), начатое около 17:59 МСК. Теперь подтверждены два дополнительных уровня связи Industrial Platform с экосистемой: **наш пакет используется в их CI**, а **четыре предложения Sentinel присутствуют в публичных manifest трёх наших хабов**. Также найдены ProtocolProbe и Canopii и уточнено состояние опубликованного индекса Trovark.

## Наш Hub установлен и импортирован во внешнем CI

В [запуске Industrial Platform](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/actions/runs/37384892675/job/112015630799) от **5 октября 22:49 UTC / 6 октября 01:49 МСК** отдельно успешны установка requirements и импорт приложения с проверкой четырёх доступных предложений. Workflow прочитан по тому же commit `5a400bd4b2d82c495ccb54e0aea007a02cb9f60a`; соответствующие шаги не пропущены, `continue-on-error` не задан.

В [requirements этого запуска](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/5a400bd4b2d82c495ccb54e0aea007a02cb9f60a/aimarket-sentinel/requirements.txt#L1) стоит **`aimarket-hub==3.14.0`**. Метаданные этой версии PyPI прямо ведут на `alexar76/aimarket-hub` и modelmarket.dev. Приложение импортирует `aimarket_hub.api/config/database/models`.

В более позднем [закреплённом requirements](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/0266b6d59355acdebec6e76036e2451396d2799f/aimarket-sentinel/requirements.txt#L1), совпавшем с текущим main, уже указан git commit `2310569f1e4e50e1062d80725bd69ae313042a69` нашего Hub. Dockerfile устанавливает эту зависимость. Исторический успех CI с PyPI-версией не подменяется утверждением, что именно этот более поздний git pin проверялся в том запуске.

Это подтверждённое внешнее использование пакета при сборке и CI-проверке. Развёртывание Python Hub в production этим не установлено. Ранее проверенный live Node-адаптер manifest и Python-приложение — разные части проекта.

История показывает добавление Python Hub и Node federation peer 5 октября UTC. Найден и workflow объявления пира на `hub.modelmarket.dev`, `hunt.modelmarket.dev`, `modelmarket.dev`. Метаданные успешных запусков доступны, но запрос журнала вернул 403; подтверждённой HTTP-квитанции принятия объявления нет. Workflow нами не запускался.

[История, первоисточники и границы](../../artifacts/ecosystem-follow-2026-10-28/industrial/summary.md), [статусы отдельных шагов](../../artifacts/ecosystem-follow-2026-10-28/industrial/distribution-initial-jobs.json), [requirements исторического запуска](../../artifacts/ecosystem-follow-2026-10-28/industrial/requirements-at-initial-run.json) и [принадлежность PyPI-пакета](../../artifacts/ecosystem-follow-2026-10-28/industrial/ci-package-provenance.json) сохранены локально.

## Sentinel уже виден в публичной федерации

Прямое чтение около **18:03 МСК** подтвердило Industrial Platform Sentinel в `peers` у всех трёх наших discovery-страниц. Их manifest содержат по четыре записи с внешним `source_hub=https://x402-gateway-production-1f21.up.railway.app`:

| Публичный manifest | Предложения Sentinel |
| --- | --- |
| [modelmarket.dev](https://modelmarket.dev/ai-market/v2/manifest) | 4 |
| [hub.modelmarket.dev](https://hub.modelmarket.dev/ai-market/v2/manifest) | 4 |
| [hunt.modelmarket.dev](https://hunt.modelmarket.dev/ai-market/v2/manifest) | 4 |

Это четыре предложения одного пира, показанные тремя нашими индексами, а не двенадцать клиентов или три независимых внедрения. Во всех четырёх записях цена нулевая; `observations_30d=0`, основание репутации — unobserved. Поля route status, latency, trust и success rate не использованы как доказательство исполненных вызовов. Invoke и платежи не выполнялись.

Видимость в публичных peers/manifest теперь установлена непосредственно. Механизм первоначального добавления пира, юридическая личность оператора и официальный партнёрский статус остаются непроверенными. [Снимки discovery и manifest](../../artifacts/ecosystem-follow-2026-10-28/root/hub-discovery-scope.json) содержат URL, время, хеши и отобранные записи.

Отдельный просмотр остальных origin показал, почему нельзя считать каждый чужой hostname внешним клиентом: Attested Memory, Independent AI/CHARON и magic-ai-factory.com — уже известные части нашей экосистемы. [Перечень доменов с этой оговоркой](../../artifacts/ecosystem-follow-2026-10-28/root/advertised-external-peer-origins.json) сохранён.

## ProtocolProbe прочитал наш MCP и исследовал tool list

[ProtocolProbe: dev.modelmarket/mcp-security](https://protocolprobe.com/mcp/servers/dev.modelmarket/mcp-security) связывает запись с `https://modelmarket.dev/tools/mcp/security` и WARDEN/HISTOR. По опубликованным данным сессии **23 октября 03:46 UTC**: соединение 531 мс, обнаружены четыре tools, весь проход 3730 мс. Это данные ProtocolProbe, **CC BY 4.0**, прочитанные нами 28 октября.

Инструменты — `warden_scan`, `histor_check`, `tool_list_cost`, `x402_check`. Выполнены два класса проверок из 14 применимых; всего в рубрике 18. Tools/call не выполнялись. Метка 5/5 относится к проверкам публичных записей и репозитория, а не к безопасности сервера.

API также содержит пробы чтения списка инструментов тремя моделями **25–26 октября**. Сгенерированные аргументы проверялись по схеме; вызовы серверу не отправлялись. Эти единичные пробы не доказывают качество выполнения задач или преимущество одной модели. [Данные и точные ограничения](../../artifacts/ecosystem-follow-2026-10-28/tests-docs/protocolprobe-fact.json), [методология и сводка](../../artifacts/ecosystem-follow-2026-10-28/tests-docs/summary.md) сохранены.

## Canopii и уточнение Trovark

[Canopii, AIMarket Plugins 2.1.2](https://index.canopii.dev/server/io.github.alexar76/aimarket-plugins/2.1.2) показывает **96/100, A**, confidence 92%, rubric 2.11.0 и 25 объявленных tools. Это рубрика по исходникам и метаданным. Дата скана в полученном тексте не установлена; запуск функций или полный аудит этим не подтверждаются. [Прочитанные страницы и ограничения](../../artifacts/ecosystem-follow-2026-10-28/tests-docs/summary.md) сохранены.

У Trovark разобраны фактические публичные артефакты [index/results.json](https://github.com/lets-order-some-fries/trovark/blob/main/index/results.json) и [docs/index.html](https://github.com/lets-order-some-fries/trovark/blob/main/docs/index.html). Они всё ещё показывают Plugins **B−72**, но это снимок **15 августа**, rubric 1.7.0. Сентябрьская перепроверка с INSUFFICIENT DATA подтверждена отдельно; она не доказывает пересборку публичного индекса. Старый балл не является текущей оценкой. [Сводка и свидетельства](../../artifacts/ecosystem-follow-2026-10-28/backlinks/summary.md) фиксируют это различие.

## Свежие ответы и область проверки

На **18:00 МСК** новых комментариев или правок после предыдущего среза в MCP3431, AgentMesh561 и Vulnetix5 нет. PR14 с HISTOR остаётся открытым, merged=false. У двух последних DEV-статей по-прежнему ноль комментариев; API показывает одну реакцию у localhost-статьи и четыре у сравнительной. Личности реагировавших не устанавливались, реакции не считаются подтверждёнными внешними пользователями. [Срез ответов](../../artifacts/ecosystem-follow-2026-10-28/root/current-response-delta.json) сохранён.

Поиск новых backlinks к обзорам, книжных рецензий и внешних fixtures дополнительных подтверждений не дал. DOI в MCP issue3430 оказался в наших собственных сообщениях. Общий [индекс поисков и HTTP-чтений](../../artifacts/ecosystem-follow-2026-10-28/verification-index.json) фиксирует проверенную область. Закрытые источники и весь код GitHub не охвачены. Выполнялись только чтения; публикаций, заявок, сообщений, изменений аккаунтов и GitHub writes не было.

За проход выполнены 60 web-запросов и шесть GitHub issue search. В HTTP-индексе 59 прямых GET: 58 ответов200 и один403 для журнала Actions; после отказа журнал не запрашивался повторно. Поисковые API включены в HTTP-число, а не прибавляются к нему как отдельные чтения.
