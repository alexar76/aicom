# Распространение пакетов и внешние MCP-наблюдения — 9 ноября 2026

Пакеты скачиваются, а внешние автоматические наблюдатели продолжают читать их метаданные и MCP-поверхность. **Нового подтверждённого независимого runtime-потребителя по проверенным графам зависимостей не установлено.** Рост отдельных download counters концентрируется в дни релизов и собственных проверок; приписывать его новым людям или платящим клиентам нельзя. Срез основных GET: 19:23–19:25 UTC (20:23–20:25 в Amsterdam), дополнительные HF/OpenAlex прочитаны позднее в том же проходе.

## Сопоставимые недельные окна

Источник npm — публичный [daily range API](https://api.npmjs.org/downloads/range/2026-10-19:2026-11-08/%40aimarket%2Fwarden), даты включительно, UTC. Это количества скачиваний, не уникальные установки. CI, автоматические сканеры и собственные проверки не отделены.

| npm package | 19–25 октября | 26 октября–1 ноября | 2–8 ноября |
| --- | ---: | ---: | ---: |
| @aimarket/warden | 932 | 1009 | 1032 |
| @alexar76/argus3 | 74 | 162 | 504 |
| @aimarket/agent | 33 | 21 | 189 |
| @aimarket/widget | 7 | 7 | 240 |
| @alexar76/awr-verify | 3 | 4 | 167 |
| create-aimarket-agent | 0 | 0 | 367 |

WARDEN остаётся примерно на уровне тысячи downloads в неделю: последняя равная неделя выше предыдущей на 23 скачивания, около 2.3%. Для ARGUS последняя неделя выше на 342. Но 3 ноября дали 182 из 504 ARGUS, 104 из 189 agent, 182 из 240 widget, 115 из 167 awr-verify и 287 из 367 scaffold downloads. Для ARGUS ещё 192 пришлись на 8 ноября. Локальные `artifacts/npm-release-2026-11-03/README.md` и `artifacts/package-release-2026-11-08/README.md` фиксируют подготовку релизов и собственные consumer/security проверки в эти дни. Совпадение по датам — основание осторожно трактовать пики, **не доказанная атрибуция каждого скачивания**.

Сохранённый 30 октября показатель WARDEN 1488 за 22–28 октября точно воспроизводится сегодняшним рядом. Это другое, перекрывающееся окно; сравнивать его с 1032 как равные последовательные недели нельзя.

PyPI: суммы датированных строк [PyPI Stats overall](https://pypistats.org/api/packages/aimarket-hub/overall?mirrors=false), `without_mirrors`. [Документация](https://pypistats.org/api/) говорит об исключении известных зеркал и обновлении раз в сутки. Это не исключает CI, собственные установки и остальных ботов. Все ряды доходят до 8 ноября; событие 9 ноября ещё может отсутствовать.

| PyPI package | 26 октября–1 ноября | 2–8 ноября |
| --- | ---: | ---: |
| aimarket-hub | 793 | 493 |
| aimarket-mcp | 353 | 90 |
| aimarket-histor | 524 | 1140 |
| aimarket-agent | 176 | 180 |
| aimarket-atlas | 225 | 908 |
| aimarket-gaia-gateway | 23 | 130 |
| attested-memory | 10 | 114 |
| awr | 372 | 284 |
| awr-emitter | 4 | 7 |

Разнонаправленная динамика: Hub и MCP снизились, HISTOR/ATLAS выросли. Пики 4 ноября — 717 из 1140 у HISTOR и 782 из 908 у ATLAS. У Attested 88 из 114 относятся к 3 ноября, когда опубликован клиент 0.2.0. У GAIA 84 из 130 относятся к 8 ноября, когда опубликована 0.3.0. Равномерное увеличение внешнего использования этими числами не установлено. Суммы используют возвращённые строки; отсутствующие суточные строки отдельно как нули не верифицировались.

`recent` API для нескольких пакетов вернул `last_month < last_week` (например, HISTOR 0 и 1140, ATLAS 58 и 908). Сырые ответы сохранены. В выводах использованы только явно датированные `overall` ряды; причину несогласованности `recent` этот аудит не устанавливает.

## Версии и зависимости

Текущий npm `/latest` уже показывает WARDEN **0.24.0**, ARGUS **0.3.5**, agent **0.4.0**, widget **0.1.2**, awr-verify **2.0.1**. Scaffold npm — **0.1.1**. PyPI показывает Hub **3.19.0**, HISTOR **0.7.0**, ATLAS **0.4.0**, GAIA **0.3.0**, agent **2.6.2**, MCP **0.6.4**, Attested client **0.2.0**, awr **2.0.1**, awr-emitter **2.0.0**. Это более свежие публичные факты, чем локальные заметки о подготовленных/held релизах; заметки не заменяют registry check. Код опубликованных архивов в этом проходе не исполнялся и не сравнивался с рабочим деревом.

Правильное имя Python AWR verifier — `awr`, установленное из локального `awr/reference/python/pyproject.toml` и подтверждённое [PyPI metadata](https://pypi.org/pypi/awr/json). Первоначальные GET `awr-verify` получили 404: это ошибочный кандидат namespace, не отсутствие AWR на PyPI. Одноимённый `histor` не использовался: проверялся `aimarket-histor`.

Из **15 текущих version-scoped графов deps.dev** 13 вернули totalCount=0. У [aimarket-agent 2.6.2](https://deps.dev/_/s/pypi/p/aimarket-agent/v/2.6.2/dependents) одна прямая зависимость: `aimarket-bridges 0.1.0`; [PyPI metadata bridges](https://pypi.org/pypi/aimarket-bridges/json) связывает проект с alexar76. У [awr 2.0.1](https://deps.dev/_/s/pypi/p/awr/v/2.0.1/dependents) totalCount=18, directCount=4, indirectCount=15; выборки полностью относятся к нашей экосистеме: Hub, provenance, HISTOR, emitter и aimarket plugins. Direct и indirect пересекаются, складывать 4+15 в 19 уникальных нельзя. Новая независимая зависимость в этих данных не подтверждена.

Это ограниченный индекс конкретных актуальных версий, не полный граф всех исторических версий, Git-зависимостей, private/manual installs или HTTP-клиентов. Известный Industrial Platform, использующий pin Git commit, этим способом не проверяется.

## Внешнее автоматическое наблюдение

[Small Print WARDEN](https://smallprint.dev/a/npm/%40aimarket/warden) обновился до **26 tracked versions**, latest **0.24.0**, last checked **9 ноября**. В прежнем прямом срезе 30 октября были 22 версии до 0.22.2. Внешний наблюдатель следит за публикациями. Его текущая страница содержит внутренне разнящиеся summary denominators (22 releases / 26 versions), а описание правил инструмента всё ещё говорит ruleset v14. Эти строки не устанавливают ни актуальность runtime-кода, ни независимую security-сертификацию, ни число пользователей. Не следует переносить claim страницы «no advisory on record» в утверждение об отсутствии уязвимостей.

Полный [ShortformKit dataset](https://raw.githubusercontent.com/shortformkit/free-remote-mcp-servers/main/data/servers.json), `tested=2026-11-09`, снова содержит три строки экосистемы:

| Endpoint | Published result |
| --- | --- |
| https://hub.attestedmemory.net/mcp | 13 tools, как в срезе 26 октября |
| https://modelmarket.dev/tools/mcp/weather | 3 tools, как в срезе 26 октября |
| https://modelmarket.dev/tools/mcp/domains | 1 tool, domain_quote; новая строка относительно прежней сохранённой выборки |

SYMMARTYS `/tools/mcp/emporion` в нынешнем итоговом списке отсутствует. [Текущий генератор](https://github.com/shortformkit/free-remote-mcp-servers/blob/main/scripts/make_directory.py) оставляет максимум два endpoint на регистрируемый домен, выбирая по latency, и применяет дедупликацию. Поэтому исчезновение одной modelmarket.dev строки при появлении другой не доказывает недоступность SYMMARTYS. Raw probe JSON текущего запуска не прочитан. `tested` в итоговом JSON вычисляется как максимум дат проб, не отдельный timestamp каждого endpoint.

[Текущий probe-код](https://github.com/shortformkit/free-remote-mcp-servers/blob/main/scripts/probe.py) делает initialize, уведомление initialized и tools/list, без tools/call. Список инструментов — внешнее протокольное наблюдение, не исполнение функций и не покупка. Аннотации read-only self-reported. Domains описан как demo seller с отказом заказов; трактовать его наличие в каталоге как коммерческий спрос нельзя.

[Glama aimarket-mcp](https://glama.ai/mcp/servers/alexar76/aimarket-mcp) доступен и показывает пять tools. Это обнаружимость/каталог, не подтверждённый пользователь. Прямые ProtocolProbe GET дали HTTP403: свежие состояния не установлены; 403 не означает отсутствие карточек.

## Research distribution

[HF dataset API](https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions) сейчас возвращает downloads=230, likes=0; 30 октября API давал 113/0. Это месячный счётчик, не накопительное количество и не новые люди. [Страница датасета](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions) в web-срезе показывает «Downloads last month»=227: цифры разных срезов расходятся на три, вероятная причина — кэш или время обновления, но она отдельно не установлена. По [методике Hugging Face](https://huggingface.co/docs/hub/datasets-download-stats), GET/HEAD файлов одного repo с одного IP в пределах пяти минут группируются в одно скачивание; уникальные люди и исключение CI из публичного счётчика этим не гарантированы.

Та же HF-страница показывает для выбранного subset `changes` ошибку **DatasetGenerationError, TypeError: Couldn't cast array of type string to null** и сообщает о недоступности полного viewer. Это наблюдаемая помеха внешнему исследователю. Скачивание или чтение всех файлов не выполнялось; повреждение файлов и полная непригодность датасета не установлены. Исправление в рамках read-only аудита не делалось.

[OpenAlex W7223029314](https://api.openalex.org/works/W7223029314) возвращает **cited_by_count=0**, updated_date=2026-11-03, DOI концепта `10.5281/zenodo.23512759`. Это ноль в конкретном индексе и с его лагом, не доказательство отсутствия любого научного или прикладного использования. Не следует смешивать его с DOI отдельной версии `23512760` и его счётчиками Zenodo.

## Evidence и пределы

68 прямых публичных GET: 64 HTTP200, два HTTP404 ошибочного namespace `awr-verify`, два HTTP403 ProtocolProbe. Тела и SHA-256 сохранены в `http-index.json`, `followup-index.json`, `final-index.json`, `research-index.json`; `summarize.py` проверяет все хеши и собирает `summary.json`. Отдельно web-прочитаны документы PyPI Stats/HF и публичная HF-страница. Первый ShortformKit capture ограничился 8MB и является усечённым JSON; для выводов использован повторный полный файл `shortformkit-full.raw`, 8,539,637 bytes. Других повторов одного и того же PyPI Stats endpoint в текущем проходе не было.

Установок, внешних tool invokes, оплат, сообщений, публикаций, смены аккаунтов и GitHub writes не было. Проверена репрезентативная часть распространения экосистемы, не все площадки и не полный интернет. Внешние потребители других каналов исследуются отдельно.
