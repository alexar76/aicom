# Дополнительный поиск внешнего использования кода 30 октября 2026 года

**Новых независимых runtime-внедрений в этом проходе не установлено.** Проверены ранее не обследованные промежуточные версии WARDEN, reverse dependencies Rust/Dart SDK, редкие package markers и истории трёх AICOM forks, для которых прежнее compare не находило общего предка. Известные QuincyGB, traits-dev, Industrial Platform, RugSnare, MCPMoat и agent-exec повторно новыми не считались.

## Промежуточные версии WARDEN

Из [официального npm registry](https://registry.npmjs.org/%40aimarket%2Fwarden) получены 22 опубликованные версии. Повторно не запрашивались уже прочитанные 0.8.2, 0.15.0 и 0.22.2; для остальных **19 версий** прочитаны отдельные deps.dev dependents.

У 0.4.0 найдены три direct dependents: argus-3 0.3.1, argus-warden 0.3.1 и @alexar76/argus3 0.3.1. У 0.7.0 — @alexar76/argus3 0.3.2. Остальные 17 проверенных версий имеют нулевые счётчики в этом индексе.

Метаданные [argus-3](https://registry.npmjs.org/argus-3/latest) и [argus-warden](https://registry.npmjs.org/argus-warden/latest) прямо указывают maintainer alexar76 и repository alexar76/argus. Это варианты собственного ARGUS, не два новых внешних пользователя. Scoped ARGUS уже был установлен как собственная зависимость предыдущими аудитами.

Версионный индекс не охватывает приватный код, ручные установки, unpublished applications и вызовы HTTP/MCP. Нулевой dependent не означает ноль пользователей. Результаты и область исключённых повторных запросов сохранены в version-and-fork-scope.json и http-version-index.json.

## Rust и Dart SDK

Официальный [crates.io reverse dependency API](https://crates.io/api/v1/crates/aimarket-agent/reverse_dependencies?page=1&per_page=100) вернул dependencies=[], versions=[], meta.total=0. [Родной поиск pub.dev dependency:aimarket_agent](https://pub.dev/packages?q=dependency%3Aaimarket_agent) показывает 0 packages.

Это отсутствие опубликованных зависимых пакетов в двух ответах реестров, не отсутствие частных приложений или установок SDK. Поисковая выдача возвращала собственные Dart API docs и Rust docs.rs; их автоматическая генерация не является внешним внедрением.

## Три ранее неразобранных fork AICOM

Прямые [forks API AICOM](https://api.github.com/repos/alexar76/aicom/forks?per_page=100&sort=newest) вновь перечислили четыре прежних fork. Enterprise Factory уже имеет установленную самостоятельную доработку в аудите 26 октября и здесь повторно не анализировался.

Для остальных прочитаны default branch histories:

- [ayeshanazneen1/aicom](https://api.github.com/repos/ayeshanazneen1/aicom/commits?per_page=30): два коммита — public mirror snapshot и coverage badge от GitHub Actions.
- [adity982/aicom](https://api.github.com/repos/adity982/aicom/commits?per_page=30): те же два типа коммитов.
- [BenjaminAyivoh1/aicom](https://api.github.com/repos/BenjaminAyivoh1/aicom/commits?per_page=30): snapshot и badge.

Во всех трёх API вернул по два элемента, меньше размера страницы. Это закрывает прежний пробел чтения default history; новых самостоятельных изменений эта история не показывает. Другие ветки и приватные изменения не проверены. Сам fork не считается запуском продукта.

Прямые forks API WARDEN, HISTOR, AIMarket Hub, ARGUS и Attested Memory вернули пустые массивы. Ранее встречавшийся fork aimarket-mcp не относится к этому набору и не объявляется исчезнувшим.

## Новые поисковые маркеры и отсеянные совпадения

Выполнены шесть новых GitHub commit search по @alexar76/awr-verify, awr-emitter, aimarket-bridges, aimarket-mcp, aimarket-oracle-gateway и aimarket_agent. Первые три вернули 0. Gateway/oracle вернули прежние собственные submissions и их awesome forks, плюс сторонний aidotmarket/aimarket-mcp-server. Прочитанный закреплённый config последнего задаёт другой origin — ai-market-backend-production.up.railway.app/api/v1; client реализует ai.market Agent API. Связь с нашей экосистемой не установлена.

aimarket_agent вернул два commit в китайском sev7n4/aimarket с собственными @aimarket/agent-core и @aimarket/agent-skills. Прочитанный commit показывает private package agent-core и зависимость workspace:*, то есть локальный пакет этого монорепозитория. Эти результаты не содержат установленных ссылок на alexar76/modelmarket.dev и не считаются использованием нашего SDK.

Новый завершённый Sourcegraph поиск вне README включал aimarket-bridges, aimarket_oracle_gateway, awr-emitter, @alexar76/awr-verify/emit и aimarket_agent, с forks/archives: done=true, matchCount=0. Это результат данного индекса, не всего кода GitHub.

Дополнительно 16 web-запросов проверяли классы AIMarketAgent/AimarketAgent, старый пример hub.aicom.io, конфигурации MCP и lockfile-признаки. Нового атрибутируемого внешнего применения они не дали. Старый hostname использован только как поисковый маркер из опубликованного Rust README, текущая принадлежность домена не устанавливалась.

## Свидетельства

Сохранены **16 web-запросов и 43 прямых GET**, все HTTP 200. Каждый сохранённый ответ проверен по SHA-256. Search-0…3.json содержат полные ответы поиска, четыре HTTP-индекса — URL, время, статус и хеши, verification-index.json — итоговую локальную проверку.

Платные API, покупки, invokes, сообщения, смена auth, установка или исполнение чужого кода и GitHub writes не выполнялись. Эта ветка не участвует в покупке Agent402, которую отдельно ведёт основной агент.

