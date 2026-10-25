# Новые площадки для материалов экосистемы

Проверено 24 октября 2026 года. Обновлено с учётом решения пользователя: площадки, требующие человеческого авторства или запрещающие AI-написанные тексты, пока исключены из рабочей очереди.

Здесь «новые» означает: площадки не обнаружены как цели в просмотренных `seeding-playbook.md` и `handoff-bridge-distribution.md`. Это не гарантия, что никто из команды не обращался к ним раньше. Письма, заявки, публикации и регистрации в ходе проверки не отправлялись. GitHub-подачи не входят в этот план.

**Первая очередь — две площадки с явно предусмотренным AI-участием.**

| Приоритет | Площадка и маршрут | Подходящий материал | Подтверждённые условия |
|---|---|---|---|
| 1 | **Real World Data Science / Royal Statistical Society** — `rwds@rss.org.uk`; [порядок подачи](https://realworlddatascience.net/contributor-docs/contributor-guidelines.html) | Методологический кейс HISTOR: как измерять изменения MCP tool definitions, отделять косметические изменения от структурных и учитывать ненаблюдавшиеся состояния. Вариант: анализ данных через DuckDB. | Сначала brief: тема, аудитория, synopsis до 250 слов, выводы и формат. Можно отправлять по email, работать через Google Docs/Word — GitHub не обязателен. [AI-политика](https://realworlddatascience.net/contributor-docs/call-for-contributions.html) прямо допускает прозрачное использование AI и просит описать его роль. Нужны проверки качества данных и ограничения. |
| 2 | **HackerNoon** — [Start Writing → Submit for Review](https://help.hackernoon.com/how-do-i-get-published) | WARDEN: проверка firewall на собственных документированных ограничениях. Отдельный материал AIMarket: что показывают реальные оплаченные вызовы и неоплаченные проверки. | В [официальных credibility indicators](https://help.hackernoon.com/emoji-credibility-indicators/ai-assisted) предусмотрена маркировка AI-generated частей текста. Это подтверждает наличие формата, но не гарантирует приём любого полностью сгенерированного материала. Нужны факты, техническая глубина и раскрытие связи с продуктом. Брендовые публикации имеют отдельные условия — не смешивать их с авторским кейсом. |

Для RWDS мой приоритет выше: есть и релевантная исследовательская аудитория, и прямое описание работы с AI в правилах. Для HackerNoon сильнее подходит законченная история с результатом, ошибками и выводами. Это оценка соответствия, а не прогноз охвата или принятия.

**Следующая очередь — предложение уже опубликованной ссылки, датасета или проекта.** На перечисленных страницах подачи не найдено требования писать материал без AI. Отсутствие такого пункта не означает установленного разрешения на любой AI-контент; при подаче следует раскрыть способ подготовки.

| Приоритет | Куда | Что предложить | Как подать и что учесть |
|---|---|---|---|
| 3 | **Data Is Plural** | Открытый датасет HISTOR от 20 октября: история tool definitions, изменений и наблюдений. | [Критерии и контакт](https://www.data-is-plural.com/faq/criteria/): `jsvine@gmail.com`. Нужны прямая загрузка, документация, форматы, происхождение, лицензия и ограничения. Это предложение датасета куратору, а не заказ гостевой статьи. |
| 4 | **PyCoder’s Weekly** | Исследование запуска MCP-пакетов в gVisor: Python-зависимости, импорт, launcher/runtime, воспроизводимость наблюдений. | [Submit a Link](https://pycoders.com/submissions) ведёт на Google Form. Принимают предложения собственных проектов и статей. Свежая активность подтверждается [архивом](https://pycoders.com/issues); в [выпуске 743](https://pycoders.com/issues/743) уже был материал о тестировании MCP-клиентом. Лучше Python-выводы и инструменты, чем общая карта экосистемы. |
| 5 | **selfh.st / Self-Host Weekly** | AI-Factory как self-hosted pipeline; альтернативно HISTOR как самостоятельно развёртываемый журнал или Attested Memory с конкретным сценарием хранения контекста. | [Submit Content](https://selfh.st/submit/), [контактная страница](https://selfh.st/contact/). Есть отдельные направления Newsletter и Apps Directory; выбрать одно для первой подачи. Рассылка активна: последний просмотренный выпуск от 23 октября. Нужны ясное назначение, доступная демонстрация и короткий путь установки. |
| 6 | **Help Net Security** | Исследовательская новость HISTOR либо технический разбор границ WARDEN с данными и воспроизводимыми примерами. | [Официальный контакт](https://www.helpnetsecurity.com/contact/): `press@helpnetsecurity.com` — входящая точка для новостей и материалов. Сначала короткий pitch со ссылкой на первичный источник. Приём и ответ не гарантируются. На странице есть отдельная рассылка об open-source security tools. |
| 7 | **Data Elixir** | Датасет HISTOR и один полезный аналитический результат, воспроизводимый запросом. | [Contact](https://dataelixir.com/contact/) — форма Name / Email / Message для вопросов и предложений. Это общий контакт, а не подтверждённая специальная форма отбора статей. Тематика — data science, аналитика, ML. |
| 8 | **FindMCP** | HISTOR либо WARDEN: один инструмент, одна задача. | [Submit](https://findmcp.app/submit): публичный repo/docs/remote URL, английское описание минимум 80 знаков, JSON установки для Claude Desktop, transport, категория, email. Лимит указан как три сервера на IP/email за сутки. Проверить текущую карточку перед подачей; не путать появление в каталоге с читательским спросом. |

**Профессиональные обсуждения — отдельный маршрут.** Подходят для предоставления результатов и получения технических вопросов. AI-политика OWASP-каналов пока не установлена. MCP Contributors исключён после чтения обязательных правил вступления 24.10.2026: AI-generated сообщения запрещены даже после проверки и одобрения человеком.

| Куда | Почему подходит | Точка входа |
|---|---|---|
| **MCP Security Interest Group — отложено** | Тематика подходит HISTOR, но правила MCP Contributors прямо запрещают AI-generated сообщения, включая проверенные человеком. По решению пользователя такие площадки сейчас исключаем. | [Официальный charter](https://modelcontextprotocol.io/community/interest-groups/security); обязательный экран правил в [Discord](https://discord.com/channels/1358869848138059966/1358869848138059969) прочитан после входа qwezzy721. Приглашение принято, согласие с правилами не отмечено, сообщение не опубликовано. |
| **OWASP GenAI Security Project** | Методика red-team, ограничения детектирования и наблюдения за tool definitions могут быть полезны рабочим группам. | [Текущий onboarding](https://genai.owasp.org/contributing/): OWASP Slack, общий `#project-genai`, дальше канал нужного workstream. [Более старая страница](https://genai.owasp.org/contribute/) называет каналы `team-llm-*`; ориентироваться на текущие указания координаторов. Не заявлять одобрение OWASP или статус партнёра. |

**Резерв с ограничениями.**

- **tl;dr sec:** аудитория подходит WARDEN/HISTOR. В [выпуске от 22 октября](https://tldrsec.com/p/tldr-sec-351) редактор приглашает отвечать на письмо с вопросами и feedback. Специальная открытая форма приёма ссылок не найдена; AI-политика не установлена. Оставить как контакт для предложения материала, не считать готовым автоматическим каналом публикации.
- **SANS Internet Storm Center:** [форма](https://isc.sans.edu/contact.html) принимает сведения о security events и наблюдения. Использовать для конкретного технического наблюдения с доказательствами. Реклама продукта или общая статья об экосистеме не соответствует назначению формы. AI-политика не установлена.
- **Medium:** [политика](https://help.medium.com/hc/en-us/articles/22576852947223-Artificial-Intelligence-AI-content-policy) допускает AI-assisted текст с раскрытием использования; AI-generated writing нельзя закрывать paywall Partner Program. Ограничения распространения существенны, поэтому это запасная поверхность публикации, а не обещание новой аудитории. Правила конкретных publications могут быть строже.

**Что исключено из текущей очереди.**

| Площадка | Причина |
|---|---|
| MCP Contributors / Security IG | Правило вступления №3: запрет AI-generated сообщений даже после проверки и одобрения человеком. Проверено в Chrome после входа 24.10.2026. Подготовленный текст не опубликован; раскрытие AI запрет не отменяет. |
| [InfoQ](https://www.infoq.com/write-for-infoq/) | Запрещает преимущественно AI-написанный контент; AI разрешает для исследования и грамматики. По решению пользователя отложено. |
| [Хабр / Песочница](https://habr.com/ru/sandbox/start/) | Прямо исключает статьи, написанные с помощью генеративных моделей, даже при авторских мыслях. Отложено. |
| [LWN](https://lwn.net/op/AuthorGuide.lwn) | Не принимает LLM-generated статьи и pitches. Отложено; черновики для отправки туда не подготовлены. |
| [TechRadar Pro Perspectives](https://www.techradar.com/pro/perspectives-how-to-submit) | Запрещает AI при drafting и упоминание собственных продуктов/исследовательских отчётов внутри материала. Отложено. |
| [r/netsec](https://www.reddit.com/r/netsec/wiki/guidelines/) | AI-generated посты не приветствуются; строгие правила самопродвижения. Для текущего способа подготовки материалов отложено. |
| [The New Stack](https://thenewstack.io/contributions/) | В просмотренном поисковом снимке правил гостевая программа приостановлена с 17 июля 2026; также указан запрет wholly AI-generated работы. Прямое повторное чтение вернуло 403. Не тратить текущую очередь. |
| [Ministry of Data](https://ministry.ofdata.org/submit/) | Единственный конкретный маршрут на странице — GitHub issue; понятный независимый email/form не найден. GitHub-публикации запрещены правилами workspace. |
| PulseMCP | Статус паузы найден в свежих внешних обзорах; прямую страницу подтвердить не удалось. Уже фигурировал в старом плане и не считается новым местом. |
| Console.dev, Changelog, TLDR / TLDR AI | Уже есть в старом seeding-playbook. Можно позже перепроверить, но не выдавать их за новые находки. |

**Материалы для первой волны.**

1. Датасет HISTOR: зафиксированный снимок 20 октября, README, схема полей, пример DuckDB-запроса, provenance, ограничения и DOI. В числах различать registry entries, remote endpoints, packages, прочитанные tool sets и когорту наблюдения. База: [датасет](https://histor.modelmarket.dev/datasets/), [Hugging Face](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions), [DOI](https://doi.org/10.5281/zenodo.23512759).
2. WARDEN: один документированный класс проблемы, способ воспроизведения, исправление и оставшиеся ограничения. Выводы о правилах не превращать в обещание общей безопасности MCP.
3. AI-Factory для selfh.st: результат, который получает self-hosted пользователь, способ установки, требования к LLM и реальная демонстрация. Выводы об on-chain экономике здесь второстепенны.
4. AIMarket для HackerNoon: честная история проверок и оплаченных вызовов. Даты и окна явно указать; отделить own tests, monitoring и неизвестных плательщиков. Не заявлять подтверждённых постоянных клиентов без свидетельств.

**Три коротких черновика предложения темы.** Они созданы с AI-помощью для проверки пользователем и не отправлены. Перед использованием проверить актуальность ссылок и чисел; AI-участие раскрывать по правилам получателя.

Для Data Is Plural:

> Subject: Dataset suggestion: how MCP tool definitions change over time
>
> HISTOR publishes an open dataset of MCP tool definitions and their recorded changes. The 20 October 2026 snapshot contains 81,879 listed remote-server and package entries and 23,821 recorded changes across 24 September–20 October. Downloads are gzip JSON Lines, with documentation, checksums, a signed manifest and a DOI. The compilation is CC BY 4.0; rights in individual tool definitions remain with their publishers. Daily remote observations can miss intermediate states, and a changed definition does not establish malicious behavior. We maintain the project and prepared this note with AI assistance. Dataset: https://histor.modelmarket.dev/datasets/ — DOI: https://doi.org/10.5281/zenodo.23512759

Для PyCoder’s Weekly:

> HISTOR's MCP package census examines what npm and PyPI servers actually advertise when started inside a gVisor sandbox. The Python angle is dependency compatibility, import failures, and launchers whose advertised tools depend on local runtime state. The report explains the measurement method and the observer's limitations. We maintain HISTOR; this submission note was prepared with AI assistance. Suggested link: https://dev.to/alexar76/we-installed-12915-mcp-servers-and-started-each-one-41-never-answered-3heh

Для Help Net Security:

> Subject: Research pitch: measuring changes in MCP tool definitions
>
> We maintain HISTOR, a public log of MCP tool definitions, and WARDEN, an MCP inspection and enforcement tool. We have released a downloadable dataset with dated observations, recorded definition changes, checksums and a signed manifest. A useful editorial angle is how clients can interpret changes after approving a server, including the limits of daily observation and pattern scanning. The data documents observed interfaces; it does not certify servers as safe. This note was prepared with AI assistance. Dataset and documentation: https://histor.modelmarket.dev/datasets/

Рекомендуемый порядок работы: RWDS и HackerNoon как новые редакционные направления; параллельно подготовить адресные предложения датасета для Data Is Plural и Python-материала для PyCoder’s; selfh.st — отдельная подача AI-Factory. Затем Help Net Security и профильные обсуждения. Все отправки требуют отдельного поручения пользователя; текущая задача — поиск и подготовка локального списка.
