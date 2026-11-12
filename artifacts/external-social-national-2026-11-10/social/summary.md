# Соцсети и сообщества — срез 10 ноября 2026

**Нового атрибутируемого независимого социального поста, обзора или подтверждённого использования экосистемы эта выборка не добавила.** Известные содержательные контакты сохранились. Дельты проверены по comment IDs и reply URIs: в выбранных известных ветках новых внешних ответов нет. Собственные новые публикации учтены отдельно.

База сравнения — социальные отчёты 9 ноября, утренний social-проход 10 ноября, сегодняшний углублённый reviews-проход и products-аудит. Новизна сравнивается с накопленными `docs/` и `artifacts/`; дата чтения не заменяет дату события.

## Проверяемые дельты обсуждений

| Источник | Сверка с прежними ID | Что это означает |
|---|---|---|
| [HN, известная ветка](https://news.ycombinator.com/item?id=50193565) | Те же **50205750** и **50223414**; новых и удалённых IDs нет | [Вопрос ITAltitudes](https://news.ycombinator.com/item?id=50205750) от 23 октября — прежний внешний технический контакт. Ответ `alex_artamokhov` от 24 октября — собственный |
| Bluesky: Metis, GAIA, Hub, ARGUS | В четырёх деревьях те же четыре reply URI, новых/удалённых URI нет | Все четыре ответа принадлежат owner DID, а не внешним читателям. Их нельзя считать четырьмя пользователями |
| [DEV: marketplace feedback](https://dev.to/alexar76/we-built-a-marketplace-for-ai-agents-sellers-told-us-the-integration-wasnt-worth-it-2c6m) | **13→13**, множества `id_code` совпали | Прежние чужие комментарии сохранены; новых ID или внешних аккаунтов в этой ветке нет |
| [DEV: x402 survey](https://dev.to/alexar76/we-tried-to-buy-one-call-from-100-x402-sellers-most-delivered-almost-nobody-is-buying-2498) | **35→35**, множества `id_code` совпали | Известные Textokit / Agent Embassy / seller-discussion ответы не пересчитываются заново |
| DEV: Multica, Metis benchmark, healthy-containers case, новый ARD case | Четыре текущих публичных comment endpoint вернули `[]` | Это подтверждает текущее отсутствие ответов в полученных списках. Где старого reply-ID snapshot нет, дельта не подменяется metadata-счётчиком |

[HN IDs, авторы и даты](hn-thread-delta.json) · [Bluesky URI, DID и даты](bsky-reply-delta.json) · [DEV IDs, авторы и ссылки](dev-comment-delta.json).

Bluesky author feed вернул **66 записей, как и 9 ноября**, без новых URI; cursor отсутствует. Это публичный feed данного аккаунта, не весь Bluesky. Четыре выбранные reply trees касаются разных продуктов; остальные lifetime-обсуждения и quote posts целиком не перечитывались.

## Собственная дистрибуция

В DEV metadata теперь **76 публикаций вместо 75**. Новая для snapshot запись — [собственная ARD-статья](https://dev.to/alexar76/we-added-ard-discovery-to-six-hubs-and-found-a-broken-signed-search-result-3nlp), ID **4993724**, publication metadata **10 ноября, 14:00 UTC**. Её comment endpoint прочитан отдельно и вернул пустой список. Это собственная публикация, не внешний отклик.

В публичном [Telegram-канале](https://t.me/s/just_for_agents) видны восемь новых собственных post IDs **403–410** по сравнению с предыдущим 20-post window. В полученном HTML нет публичной discussion-разметки. Эти восемь broadcast-постов не считаются читательскими ответами; старые записи, вышедшие за окно, не объявляются удалёнными. Просмотры и reactions не использованы как числа людей. [Точные post URLs и даты](telegram-own-distribution.json).

## Известный чужой пост и два впервые прочитанных старых комментария

[QuincyGB, 25 октября](https://dev.to/quincygb/eighteen-routes-five-conversations-one-bug-a-customer-found-for-us-6lm) в собственном отчёте о x402-продуктах прямо называет AIMarket среди адресатов своего outreach. Сам материал уже был в базе 29 октября; это повторное подтверждение известного стороннего текста, не новый пользовательский обзор ноября.

Два reader comment IDs не найдены в проверенной прежней базе:

- [indie_ship_log, 3ip9h](https://dev.to/quincygb/eighteen-routes-five-conversations-one-bug-a-customer-found-for-us-6lm#comment-3ip9h), **25 октября, 07:26:38 UTC**;
- [robertpaschal, 3j0ef](https://dev.to/quincygb/eighteen-routes-five-conversations-one-bug-a-customer-found-for-us-6lm#comment-3j0ef), **25 октября, 16:20:17 UTC**.

Оба обсуждают баг примера и клиентский feedback в продукте Quincy. **Ни одного точного имени, домена или handle нашей экосистемы в их body нет.** Это два новых первичных прочтения исторических комментариев; они исключены из наших mentions, reviews и adoption. Человеческая независимость владельцев аккаунтов не проверялась. [Разбор](quincy-outside-discussion.json), [проверка новизны](novelty-check.json).

## Охват платформ и ограничения

Выполнены **32 web-строки: 30 тематических и два контрольных запроса**, восемь пакетов. Использованы точные repo/package/domain/product markers для Metis, ARGUS, Attested, Hub/SDK, GAIA/ATLAS, HESTIA, kits, courses, PingBlip, Cite Desks и других компонентов. Проверялись X/Twitter, Reddit, Bluesky/Mastodon, HN/Lobsters, LinkedIn, Telegram/YouTube, DEV чужих авторов, Hashnode/HackerNoon и выбранные developer forums. Telegram-поиск включал `t.me/s`, TGStat и Telemetr.

Семь тематических пакетов вернули Empty search results. Пакет с известными контактами/контролем индекса вернул прежние каталоги и Quincy. Это не исчерпывающий поиск каждой платформы: результаты пакетные, индексирование неполно, а точные фразы и исключения могут расширяться движком. Каталоги, собственные блоги и copies не превращены в независимые публикации.

**26 public/native GET: 24 HTTP 200, два HTTP 403.** Все тела сохранены полностью в пределах лимита; длины и SHA-256 проверены в [capture-integrity.json](capture-integrity.json).

- HN native search по пяти точным package/domain маркерам вернул ноль; известная ветка проверена отдельно по IDs.
- Mastodon.social: два публичных запроса, Attested и Metis, дали `statuses=[]`. Один instance не представляет весь fediverse.
- Bluesky public search и Reddit native search вернули **403**. Их поисковое состояние остаётся неизвестным; login/challenge/robots не обходились. Отдельные публичные Bluesky feed/thread endpoint были доступны.
- Lobsters показал ноль stories для выбранного domain query; сам сайт сообщил нормализацию punctuation. Комментарии всего сайта этим не обследованы.
- X/LinkedIn/YouTube, TGStat/Telemetr, Hashnode/HackerNoon проверялись по доступной индексированной выдаче. Авторизованные feeds, закрытые группы, private comments и полная analytics не читались.

[findings.json](findings.json) содержит platform coverage и ссылки на каждую дельту; [query-index.json](query-index.json) — все строки и границы их интерпретации. Новые external accounts/comments не приравнивались к product users. Внешних сообщений, публикаций, логинов, consent, оплат, tools/call, GitHub CORE-запросов и GitHub writes не было.

Offline-сборка: `python3 artifacts/external-social-national-2026-11-10/social/analyze.py`.
