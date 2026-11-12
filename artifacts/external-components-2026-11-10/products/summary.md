# Остальные продуктовые компоненты — 10 ноября 2026

Проверены **13 семейств**, включая отдельные оболочки Attested Memory и перечень десяти desktop/IDE-приложений. **Нового независимого продуктового обзора или подтверждённого рабочего внедрения выборка не установила.** Наиболее предметные внешние связи здесь — учебные ссылки на AIMarket Courses; для Attested и Domain Operator Kit подтверждено автоматическое профилирование, которое не считается внедрением.

База сравнения включает сегодняшний [вечерний аудит](../../external-links-2026-11-10/review.ru.md), [углублённый проход](../../external-links-deeper-2026-11-10/report.ru.md), ноябрьские отчёты и октябрьские свидетельства. HISTOR не исследовался; случайные совпадения в поисковых ответах исключены из результата.

## Результат по каждому семейству

| Семейство | Что проверено и установлено | Ограничение |
|---|---|---|
| **Attested Memory: Hub / Personal / Team / Expert** | Точные домены, четыре package/product markers; [APIs.io](https://apis.io/providers/attestedmemory-net/) и [API Evangelist profile](https://github.com/api-evangelist/attestedmemory-net) подтверждены первично. Профиль сам описывает себя как сторонний каталог API | Это известное автоматическое описание контрактов, не применение Personal/Team/Expert. Для опубликованного клиента `attested-memory 0.2.0` deps.dev показывает 0 dependents |
| **Cite Desks / Emberline / Tideline / Solrecord / Seamark / Plinth / Smokeproof** | Точная parent-repo identity и отдельные домены/имена сохранены; web и grouped GitHub README search выполнены | Нового точно атрибутируемого чужого обзора/внедрения не подтверждено. Generic Cite Desk и own mirrors исключены; полный код всех выдач не изучался |
| **Domain Operator Kit** | [Glama server page](https://glama.ai/mcp/servers/alexar76/domain-operator-kit) и [renew assessment](https://glama.ai/mcp/servers/alexar76/domain-operator-kit/tools/renew) доступны; есть конкретная автоматическая критика полноты описания параметров, output и failure cases | Издатель оценивал описание/схему; это не человеческий обзор и не регистрация домена. First-observed schema — 20 октября; новая публикация не заявляется |
| **eSIM Operator Kit** | Точный `@aimarket/esim-rails`, repository/domain markers, текущая registry version 0.4.0 и её graph проверены | Dependents 0; Git/CLI use не охвачен. Socket — только search candidate, прямой GET 403. Внешний оператор или отзыв не подтверждён |
| **PingBlip** | [Страница игры](https://pingblip.itch.io/pingblip) и [launch topic](https://itch.io/t/7175888/pingblip-hatch-a-pet-from-real-weather-free-browser-game) прочитаны; на странице нет читательских комментариев, тема показывает posts 1–1 | Это собственная дистрибуция и собственный анонс. Tag listings, просмотры и отсутствие текста комментариев не равны оценке удержания или отсутствию игроков |
| **LinkedIn Profile Coach** | Точные repo и Flutter package markers, полное название; grouped README search — 0 результатов | Нового чужого обзора/кода не подтверждено. Совпадения обычных LinkedIn coaches исключены; app-store analytics не читалась |
| **AIMarket Desktop** | Family/core identity и отдельные выбранные SKU names; десять приложений перечислены в coverage; grouped README search — 0 | Не десять отдельных исчерпывающих code searches. Нового атрибутируемого применения не подтверждено |
| **AI landing generator** | `aicom-landing`, hosted path и namespace alias; registry 0.2.0 и version-scoped graph | В выдаче собственные registry/wiki/topic mirrors; dependents 0 не исключает CLI или генерацию сайтов. Нового foreign review/generated-site attribution не установлено |
| **AIMarket School** | Точная repo/domain identity; web и две страницы grouped education repository search | Известная Ananclaw card — каталог, не отзыв ученика. Нового учебного проекта/разбора не подтверждено |
| **AIMarket Courses** | В [каноническом списке EbookFoundation](https://github.com/EbookFoundation/free-programming-books/blob/main/courses/free-courses-en.md) есть прямая Markdown-ссылка на наш portal. Ссылка [The Learning Standard](https://thelearningstandard.org/news/how-autonomous-ai-agents-are-redefining-student-research-skills) на orchestration-course сохранилась | Current canonical source подтверждён; это не новый независимый review. Commit search показывает owner-authored move от 6 августа; PR/commit details не получены из-за quota. Learning Standard известен с 30 октября. Учебная issue S-AI-Projects уже разобрана предыдущим проходом; выполненная работа не подтверждена |
| **create-aimarket-agent** | Python/npm identity, точное имя генератора; npm latest 0.1.1 и её dependents graph | Dependents 0. Локальная 0.1.2 не подменяет публичную версию; scaffolder может использоваться без зависимости в созданном проекте. Чужой generated project не подтверждён |
| **AIMarket Playground** | Repo/domain и starter/checker markers; web и GitHub README sample | Нового внешнего starter project/обзора не подтверждено. Собственная golden path — не внешнее внедрение; публичные invoke не запускались |
| **Use-cases Portal** | `use.modelmarket.dev`, owner/repo identity; web и GitHub README sample | Topic mirror пересказывает собственные metadata; generic use-case portals не атрибутируются нам |

## Что удалось уточнить

Канонический файл EbookFoundation прямо ведёт на `https://alexar76.github.io/aimarket-courses/`. Commit search связывает перенос этой записи в MOOC-раздел с **alexar76**, commit `b197a1cf…`, 6 августа, PR #13394. Поэтому источник учитывается как внешний курируемый список с авторским происхождением размещения, а не независимое испытание курса. Текущий файл подтверждает наличие ссылки; подробности принятия PR из-за quota в этом проходе не перечитаны. Форки с тем же commit не являются отдельными рекомендациями.

У The Learning Standard сохраняется ссылка в Sources на `alexar76/aimarket-courses/tree/main/orchestration-course`; article metadata датируют материал **22 сентября 22:45 UTC**. Этот адрес уже проверен 30 октября. Организационная подпись и самоописание издателя не доказывают прохождения курса или человеческой независимой проверки notebook. Ссылка полезна как внешний образовательный контекст, не quality certification.

Два похожих GitHub-кандидата исключены по первичным README. `besboy3107/team-memory-os` — иной русскоязычный stdlib/SQLite app с другими API, без точных маркеров нашего Attested/AIMarket. Starlight использует attested memory как общий термин, но в прочитанном README не ссылается на нашу identity. Полные repository trees здесь не сканировались. [Отдельные свидетельства](false-positives.json).

## Покрытие и доказательства

- **35 web-строк**, девять пакетов; запросы и полные ответы сохранены. Движок иногда расширял точные фразы и игнорировал исключения; совпадения отсмотрены по identity markers.
- **34 публичных GET: 29 HTTP 200, пять HTTP 403**. Все тела сохранены без обрезания; длины и SHA-256 проверены в [capture-integrity.json](capture-integrity.json).
- GitHub: **шесть repository-search pages**, включая обе страницы education (36 возвращённых записей всего), и **два commit searches**. Это metadata/README/commit-message search, не авторизованный поиск всего кода. Большинство общих совпадений не проверялось полным clone; отсутствие adoption не объявляется доказанным.
- GitHub core quota заблокировала README одного кандидата и три detail-запроса; Socket также вернул 403. Это непрочитанные источники, не нулевая выдача. Повторов и обходов через смену авторизации/аккаунта не было.
- Четыре [version-scoped dependency graphs](dependency-graphs.json) показывают totalCount 0. Они не измеряют пользователей и не покрывают ручные, Git, CLI или generator workflows.

[coverage.json](coverage.json) даёт отдельную строку каждому семейству: точные маркеры, пути и строки локальных metadata, номера web queries, native GitHub results, primary status и предел вывода. [findings.json](findings.json) разделяет курируемые/содержательные ссылки, автоматическое присутствие, собственную дистрибуцию и исключения. [novelty-check.json](novelty-check.json) сохраняет точные совпадения URL в прежней базе: новый маршрут чтения или label не считается новой внешней связью.

Публичная выборка не охватывает private code, закрытые обсуждения, отзывы за логином и полную аналитику установок. Сообщений, логинов, публикаций, оплат, tools/call и исполнения чужого кода не выполнялось. Offline-сводка воспроизводится: `python3 artifacts/external-components-2026-11-10/products/analyze.py`.
