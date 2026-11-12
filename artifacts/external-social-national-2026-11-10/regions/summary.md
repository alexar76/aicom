# Европа, СНГ и Латинская Америка: региональный проход 10 ноября

**Нового точно атрибутированного независимого обзора, читательского обсуждения или применения экосистемы этот проход не установил.** Проверены запросы для RU/UA/DE/FR/ES/PT/PL/CZ/NL/IT. Поиск не ограничивался HISTOR/WARDEN: использовались Hub, Attested Memory, SYMMARTYS, Bridges, Domain/eSIM kits, PingBlip, Cite Desks, учебный генератор, книги и редкие названия статей о Hephaestus/Multica.

Новое полезное уточнение — обычный публичный **Habr RSS доступен без consent**, но конкретный exact-domain feed содержит ноль записей. Это не доказательство отсутствия упоминаний на Habr вообще. Итальянский одноимённый AiMarket и тематическая страница AgentStackList не дали атрибуции нашей экосистеме.

## Охват

Поданы **28 query shapes в семи пакетах**. Все семь вернули ответ, один пакет — Empty search results; ответ пакета не заверяет полноту отдельной строки. Поисковик нередко возвращал глобальные каталоги вместо местных источников, расширял точные фразы и игнорировал исключения. Такие fallback results вручную не засчитывались как национальные публикации.

| Язык / регион | Запрошенные площадки и маркеры | Результат полученной выборки |
|---|---|---|
| RU / СНГ | Habr, VC, DTF, Pikabu; Bridges, SYMMARTYS, eSIM/domain kit, PingBlip, «Вес ответа» и фамилия автора | Нового атрибутируемого автора/обсуждения нет. Дополнительно прочитан публичный Habr RSS |
| UA | DOU, dev.ua, AIN; точные домены, create-aimarket-agent и украинское уточнение отзыва | Точного самостоятельного украинского текста в ответах не установлено |
| DE | Heise, Golem; домен + Erfahrungen, свежий marketplace article title | Прежние англоязычные каталоги/наблюдатели не превращены в немецкий обзор |
| FR | LinuxFR, Developpez; точные домены/Bridges, avis agents | Own package docs, API profiles и общие исследования attested memory исключены |
| ES / ЛатАм | Meneame, Genbeta, Xataka, Platzi, devs.com.ar, HolaMundo; Cite Desks и rare domain-buyer title | Самостоятельного испанского текста с точной связью не найдено в полученных ответах |
| PT / Бразилия | TabNews, DevMedia, iMasters, Diolinux, Tecnoblog, Código Fonte; продукты и generator | Own PyPI/tutorial/Hub pages не засчитаны как бразильские пользователи или отзывы |
| PL | Sekurak, Niebezpiecznik, Zaufana Trzecia Strona, JustJoinIT, Bulldogjob, Wykop | Полученные глобальные карточки не устанавливают польского автора или локальное обсуждение |
| CZ | Root.cz, Lupa.cz, Radyz; продукты и zkušenosti | Нового источника нет; exact native AIMarket API отдельно вернул пустой массив |
| NL | Tweakers, Computable, Dutch IT Channel; domain + ervaringen | Нового независимого нидерландского материала не установлено |
| IT | Punto Informatico, HWUpgrade, Tom's Hardware; domain + recensione | Прочитан одноимённый ai-market.it; HTML — shell, связь с нашей identity не установлена |

Дополнительные exact-title запросы использовали собственные статьи о покупке домена за $1.54, sample fire brief, цене capability chain и Multica agents. Первоначальные названия сверены с локальными `meta.json`; вымышленные местные переводы не использовались. Оригинальный текст или перевод собственного материала не считается независимым отзывом.

Сверка с **56 прежними query files и 1 002 различными структурированными query strings** не нашла буквальных повторов текста наших запросов. Это не семантическая новизна, не проверка всего старого интернета и не доказательство новой аудитории. Списки файлов и метод — `previous-query-files.txt`, `query-novelty.json`.

## Четыре первичных чтения

Чтения выполнены **20:25 UTC / 21:25 Europe/Amsterdam**; все четыре HTTP 200.

**[Habr public RSS](https://habr.com/ru/rss/search/?q=%22modelmarket.dev%22&target_type=posts&order=relevance).** Получен валидный RSS XML, `item` — 0. Домен modelmarket.dev находится только в title/description как эхо поискового запроса, а не в публикации. Feed указывает собственный pubDate 19:27 UTC; это поле издателя, не время нашей загрузки. Баннер не открывался и не подтверждался, cookies/login/UI не использовались. Результат относится к exact quoted-domain RSS, а не к полному Habr, комментариям и всем возможным spellings. Прежняя ошибка другого native API не переносится на этот рабочий RSS endpoint.

**[Radyz native search AIMarket](https://radyz.cz/wp-json/wp/v2/search?search=AIMarket&per_page=100).** HTTP 200, JSON `[]`. Это ещё один exact keyword check известного издателя. Прежний контроль уже показал, что WordPress search может пропустить известную ecosystem source-ссылку вне индексируемого текста; поэтому пустой ответ не доказывает отсутствия ссылок. Известная чешская заметка о HISTOR от 22 октября новой находкой не объявляется и здесь не пересчитывается.

**[AiMarket.it FAQ](https://ai-market.it/faq).** HTML 4 443 bytes объявляет итальянский язык, canonical `ai-market.it` и publisher metadata **Bizpower SRLS**. В полученном HTML нет наших точных доменов, аккаунта и выбранных product markers. При этом body содержит только JS root: rendered FAQ не прочитан, а scripts не исполнялись. Поэтому это **неатрибутированный одноимённый кандидат**, а не доказанное упоминание нашей экосистемы и не полный вывод о несвязанности всего сайта. Автор конкретного FAQ и дата публикации не установлены.

**[AgentStackList trending](https://agentstacklist.com/trending/).** Полное тело 2 411 694 bytes сохранено. В нём нет девяти выбранных точных ecosystem markers и четырёх редких article-title фрагментов. Это тематический fallback полученной поисковой выдачи; страница не засчитана как наш обзор. Вывод ограничен сохранённым HTML, не другими страницами или историей сайта; национальность оператора по поисковому уточнению не приписывается.

## Что повторно не посчитано

В выдачах снова появились LibHunt с нашей Multica-статьёй, Web Pulse/ShortSingh с marketplace launch, Agenstry, Agent Economy Report, Karatum, A2A Registry, Vouch и API Evangelist/APIs.io. Эти операторы/страницы уже находятся в накопленной базе; новые crawl dates не превращены в новых авторов. Они не перечитывались здесь первично и им не приписаны свежие reviews/comments. Локализованный UI и региональный поисковый термин не определяют страну оператора.

Собственные PyPI/Pages/DEV/Wiki/tutorials, общие scientific papers об attested memory, а также несвязанные Emberline/Tideline названия не засчитаны как чужое применение Cite Desks или Attested Memory. Известные Gemivo, LupaRiel, UNDERCODE и Radyz не объявлены повторно новыми национальными источниками.

## Свидетельства и пределы

`queries.json` и `query-index.json` сохраняют все аргументы, domain filters и статус пакета; `search-01.json`…`search-07.json` — полные исходные ответы. `primary-index.json` содержит точные URL/время/статус/полноту/SHA256; `findings.json` разделяет native results, homonym/shell, thematic fallback, own content и known aggregation. `verification.json` и `capture-integrity.json` подтверждают длины, SHA256 и отсутствие усечения всех четырёх тел.

Закрытые сообщества, материалы за логином, весь национальный интернет и полноценное исполнение frontend не охвачены. Не выполнялись consent-действия, публикации, сообщения, логины, изменение аккаунтов, GitHub CORE/API calls, платежи и запуск чужого кода. Локальная пересборка: `.venv/bin/python artifacts/external-social-national-2026-11-10/regions/build_report.py`.
