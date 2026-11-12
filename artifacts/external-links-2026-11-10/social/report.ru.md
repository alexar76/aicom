# Социальные упоминания и внешние ссылки — 10 ноября 2026

**Новая содержательная находка — шесть атрибутируемых упоминаний экосистемы в Vouch Agent Trust Index с датой измерения 9 ноября.** Также подтверждены новый URL пересказа статьи на TeckDeck и три прежде не найденные точные карточки AgentRank с внешними ссылками на наши репозитории. Новых пользовательских постов в обычных соцсетях или подтверждённого применения продуктов в этой выборке не установлено.

Сделаны 24 различные поисковые строки в шести пакетах: точные article slugs и URL, сочетания с авторами прежних обсуждений, X/Bluesky/LinkedIn/Reddit/HN/Lobsters/Lemmy, newsletter и developer-community domains. Все пакеты вернули обычный ответ; один был пустым. Возвращённый пакет не гарантирует полноту каждой строки. База — два социально-региональных прохода 9 ноября, общий аудит и октябрьские свидетельства. Поиск и первичные GET — около 04:43–04:47 UTC 10 ноября.

## Vouch: внешняя проверка identity, не безопасности

[Agent Trust Index](https://vouch-protocol.com/agent-trust-index/) прямо перечисляет:

| Запись | Домен | Опубликованный результат |
|---|---|---|
| dev.modelmarket/domains | modelmarket.dev | A, 100; did:web, Ed25519 JWK |
| dev.modelmarket/emporion | modelmarket.dev | A, 100; did:web, Ed25519 JWK |
| dev.modelmarket/mcp-security | modelmarket.dev | A, 100; did:web, Ed25519 JWK |
| dev.modelmarket/weather | modelmarket.dev | A, 100; did:web, Ed25519 JWK |
| io.github.alexar76/aimarket-hub | modelmarket.dev | A, 100; did:web, Ed25519 JWK |
| io.github.alexar76/attested-memory | hub.attestedmemory.net | A, 100; did:web, Ed25519 JWK |

Это **упоминания**: в шести строках нет HTML-ссылок `<a>`. [Метод](https://vouch-protocol.com/agent-trust-index/methodology/) начисляет 60 за разрешаемый DID и 40 за пригодный публичный ключ. Он не проверяет безопасность приложения, исполнение функций или внедрение. Мы подтвердили опубликованный результат, не повторяли scan. Общие числа на главной и в методологии расходятся; их не используем. Несколько записей делят один домен — это не шесть независимых проверок инфраструктуры. [Извлечённые строки](vouch-ecosystem-rows.json).

## Новые URL с настоящими внешними ссылками

[TeckDeck: 331 date-only changes](https://teckdeck.io/posts/we-found-331-mcp-tool-list-changes-in-one-week-that-only-moved-a-date-each-one-costs-a-prompt-cache-write) содержит прямую ссылку на статью **dev.to/alexar76**, дату 3 ноября и пересказ её выводов. Это новый точный URL в проверенной базе, но сам TeckDeck уже известен как агрегатор. Самостоятельного воспроизведения исследования или нового автора этим не установлено.

AgentRank даёт полные доступные карточки с прямым `View on GitHub` на точные репозитории:

- [Metis](https://agentrank-ai.com/tool/alexar76--metis/) → `github.com/alexar76/metis`.
- [AIMarket Hub](https://agentrank-ai.com/tool/alexar76--aimarket-hub/) → `github.com/alexar76/aimarket-hub`.
- [AIMarket Agent](https://agentrank-ai.com/tool/alexar76--aimarket-agent/) → `github.com/alexar76/aimarket-agent`.

Это новые точные адреса относительно проверенных docs/artifacts, **не новый доказанный независимый оператор или внедрение**. Описания и оценки построены по metadata репозиториев; даты публикации карточек не установлены. Численные score, скачивания и ранги не приняты как метрики применения: тождество пакетов и метод расчёта здесь отдельно не проверялись.

[Attested Memory на AgentRank](https://agentrank-ai.com/tool/alexar76--attested-memory/) тоже прочитан полностью, но точный URL уже был в поисковом ответе 30 октября. В новые находки он не включён. Положительная атрибуция четырёх карточек и внешние ссылки сохранены в [agentrank-backlinks.json](agentrank-backlinks.json).

## Исключения и пределы

Model Context Problems оказался ложным совпадением: HISTOR найден внутри history, WARDEN внутри Bitwarden; полного alexar76/modelmarket/attestedmemory и отдельного нашего бренда в прочитанном тексте нет. Другие AIMarket, учебные/финансовые бренды и Telegram course labels без точной связи исключены. Зеркала free-programming-books и собственной wiki — распространение уже известного исходника, не самостоятельные рекомендации.

Упоминания IETF Du/Linda, witness staging, 1gateway, LupaRiel, Gemivo и прежние DEV-комментарии повторно не посчитаны. Forum for Agents/GregBenza с неоднозначным client label histor остаются возможными наблюдениями исходящего crawler, не клиентами HISTOR.

Восемь прямых GET вернули HTTP 200; длины и SHA-256 проверены. Категория AgentRank ограничена 4 MB и усечена; она использована только для обнаружения ссылок. Четыре конечные карточки прочитаны целиком. Приватные посты, авторизованный поиск и весь непроиндексированный интернет не охвачены. Сообщений, логинов, consent, оплат и внешних публикаций не было.

Свидетельства: `search-1.json`…`search-6.json`, `query-index.json`, HTTP-индексы, `novelty.json`, `summary.json`, `verification.json` и сохранённые raw.
