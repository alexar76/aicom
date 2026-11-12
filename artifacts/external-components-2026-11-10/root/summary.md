# SYMMARTYS HELIOS DIOSCURI THEOROS Alien Monitor Signal Hunt и Lottery

Срез публичных источников 10 ноября 2026. **Новых подтверждённых внешних интеграций или самостоятельных продуктовых обзоров в этой ветке нет.** Поиск учитывает точные namespace и прежнее имя EMPORION; тематические совпадения по греческим названиям отсеяны.

Выполнены 18 web-запросов, восемь публичных GitHub repository/README queries, два Sourcegraph code stream запроса и первичные чтения package metadata/graphs и одного кандидата. Все **22 GET** сохранены полностью, HTTP 200; длины и SHA-256 совпадают. Это ограниченный публичный поиск, а не перепись всего кода.

## Результаты по компонентам

| Компонент | Точная область проверки | Результат |
|---|---|---|
| SYMMARTYS и прежний EMPORION | `aimarket-symmartys`, `aimarket-emporion`, брендовый API origin; PyPI 0.5.0 и 0.4.2 | Оба текущих version-scoped graphs deps.dev: `totalCount=0`. Нового чужого source/review по точным маркерам не подтверждено |
| HELIOS | `helios-broadcast`, `alexar76/helios`; PyPI 0.2.2 | Graph 0. Единственный README-search hit `aionbuilders/helios` проверен первично и относится к другому пакету |
| DIOSCURI | `@alexar76/dioscuri`; npm 0.2.0 | Repository provenance указывает на наш проект, graph 0. Имена CASTOR/POLLUX/MNEMOSYNE без namespace не атрибутировались |
| THEOROS | `alexar76/theoros`, `Agent Sovereignty Canon` | Квалифицируемого чужого применения или обзора в полученных ответах нет. Собственная документация и античные одноимённые термины исключены |
| Alien Monitor | `alexar76/alien-monitor`, `monitor.modelmarket.dev` | Получены собственные страницы/перекрёстные ссылки и зеркала; нового чужого embed/runtime не установлено |
| Signal Hunt | `aimarket-signal-hunt`, `hunt.modelmarket.dev`; PyPI 0.1.2 | Graph 0. Нового внешнего игрового клиента/интеграции/отзыва не подтверждено |
| Pantheon | `pantheon.modelmarket.dev` | Собственная itch-дистрибуция и прежние каталожные следы не являются независимыми рецензиями. Это дополнительная поверхность вне satellite-карты |
| Lottery | `lottery.modelmarket.dev`, `alexar76/lottery` | Два web-запроса дали зеркала и описания внутри наших продуктов. В этой строке нет свежей code-index проверки или исполнения контрактов |

**Ноль в графе относится только к названной версии пакета в deps.dev**, а не к отсутствию HTTP-потребителей, private/manual installs или иных версий. PyPI descriptions/metadata содержат прямые ссылки на alexar76; для HELIOS и Signal Hunt поля project_urls отсутствуют, поэтому при атрибуции использован и полный опубликованный README, а не только совпадение имени.

## Проверенный ложный кандидат HELIOS

GitHub tokenization запроса `"helios-broadcast" in:readme -user:alexar76` вернул [aionbuilders/helios](https://github.com/aionbuilders/helios). Его полный README называет **`@aionbuilders/helios`**, WebSocket server для Bun, и демонстрирует импорт именно этого namespace. В тексте нет `helios-broadcast`, `alexar76`, `modelmarket.dev` или AIMarket. Поэтому это одноимённый проект, не downstream нашей видеосистемы. Имя репозитория уже встречалось в поисковом ответе 28 октября; первичное чтение здесь уточняет исключение, а не добавляет новый кейс.

## Ограничения поиска по коду

Оба Sourcegraph stream завершились с нулём показанных matches, но сообщили **`skipped=shard-match-limit`**; origin query также сообщил timeout. Их нельзя использовать как полное доказательство отсутствия интеграций. GitHub README queries показали нули для семи точных областей и один исключённый hit HELIOS; это индекс README, не аутентифицированный поиск по всем исходникам.

Исторический поисковый текст о 502 у Lottery и старые версии package snippets не приняты как текущее состояние сервиса. Свежих invokes, запусков продуктов и транзакций не выполнялось. Проверка доступности собственных приложений и исправление документации не входили в этот проход.

[Покрытие по каждому семейству](coverage.json) · [Пакетные области и ограничения](findings.json) · [Проверка сохранённых тел](capture-integrity.json) · [Воспроизводимая offline-сборка](analyze.py). Только публичные чтения и локальные файлы; без сообщений, авторизаций, публикаций, установки или исполнения чужого кода.
