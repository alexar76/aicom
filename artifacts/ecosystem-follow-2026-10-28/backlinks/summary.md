# Цепочки отзывов и опубликованный индекс Trovark — 28 октября 2026

Проверка около 17:59–18:03 МСК. 20 web-запросов и девять публичных GET. Входов, сообщений, установки/исполнения стороннего кода и GitHub writes не было. GitHub API core/search не использовались; исходники и публичные HTML читались напрямую.

## Новое уточнение: опубликованный артефакт Trovark хранит старый B−72

Прежний проход установил, что в сентябрьской перепроверке Trovark AIMarket Plugins изменился с B−72 на INSUFFICIENT DATA, а исправление приняли25сентября. Теперь отдельно прочитаны фактические опубликованные в `main` артефакты:

- [index/results.json](https://github.com/lets-order-some-fries/trovark/blob/main/index/results.json), запись `/entries/155`: `ref=alexar76/aimarket-plugins`, `overall=72`, `grade=B-`.
- Снимок явно датирован `generatedAt=2026-08-15T19:32:30.425Z`, `rubricVersion=1.7.0`.
- [docs/index.html](https://github.com/lets-order-some-fries/trovark/blob/main/docs/index.html) также содержит строку AIMarket Plugins B−72 и тот же августовский timestamp в подвале.

**Это старый августовский снимок, не сегодняшняя оценка.** Принятие исправления кода и измерение изissue не доказывают, что закоммиченный индекс после этого пересобран. Текущее исполняемое поведение Trovark нами не проверялось. Статус INSUFFICIENT DATA подтверждён в описанной сентябрьской перепроверке; старый B−72 до сих пор присутствует в отдельно прочитанном артефакте. Эти факты не противоречат друг другу.

Путь к результатам получен по наблюдённым ссылкам: текущий README → docs/methodology.md → index/drift.json и папкаindex → публичное дерево → index/results.json и index/site.ts. Генератор прямо называет `docs/index.html` своим output. URL индивидуальной карточки не выдумывался. В README и полученном About репозитория не обнаружено отдельной ссылки на живой GitHub Pages/domain, поэтому наличие deployment отдельного сайта не заявляется.

Metadata: `trovark-current-results.json`, `trovark-committed-card.json`. JSONответ GET200, SHA256 `73a17dfbd74e82d028b13ef5e697cff698f251d68c8eda82d79ebf09ff03f4ba`; HTML GET200, SHA256 `d34abf85b4cb5515690d65f75c6c175344c54bbc5fef7965ee75e1cb7c336de1`. Точное время и выбранная запись сохранены.

## Цепочки цитирования и литературные отзывы

Новых независимых публикаций, цитирующих Trovark/MCPMoat-сравнение/CodeRabbit ARGUS-source, в 20 целевых запросах не установлено. Проверены точные repository slugs, фразы про credit/INSUFFICIENT DATA, полный ARGUS pinning.ts URL и внешние review/comparison сочетания.

Поисковые запросы по Trace of Refusal, Pantheon и внешним читательским площадкам (Goodreads/StoryGraph/BookBub/Reddit/Lemmy/RoyalRoad) не подтвердили новую рецензию. Единственный точный дополнительный результат — уже известная карточка Fanfics «Вес ответа». Её «Последнее обновление: вчера» не использовано как новая дата публикации или отзыв. Посторонние философские работы про trace/refusal, конференция Kristeva и совпадения слов не относятся к нашей трилогии.

Это ограниченный публичный поиск, не полный просмотр закрытых читательских групп или всех backlinks интернета. Исходники Trovark не исполнялись; карточки не пересчитывались. Полные ответы поиска — пять JSON-батчей; перечень в `query-log.json`. Прямые чтения — `verification-index.json`.
