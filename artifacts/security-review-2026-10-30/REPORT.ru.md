# Расширенный аудит aicom — 30 октября 2026

Проверены свежие публичные базы, отслеживаемые зависимости всего дерева, исходники несколькими сканерами и основные реализации протоколов. Найденные дефекты в HISTOR и независимых Rust/JS/Go реализациях исправлены локально; совместимые security-обновления зависимостей внесены. После исправлений в отслеживаемых манифестах **нет совпадений Vulnetix и HIGH/CRITICAL OSV**, но остаются три уведомления MODERATE/LOW. Это результат проверки исходников; обновление production и опубликованных пакетов не выполнялось.

## Источники и покрытие

- Vulnetix advisory-database: commit `9dd2ecd820b7ed7fa7054132812a09021acdb3ff`, получен 30.10.2026. Прочитаны все **2 565 published OSV-записей** семейств PYPI/NPM/GO/CARGO и соответствующих VULN-семейств; ошибок загрузки и сопоставления нет. Withdrawn-записи не выдаются за действующие.
- Дополнительно сопоставлены собственные версии из **166 манифестов**, 163 уникальных сочетания ecosystem/name/version. База GCVE не смешивалась со STIX и результатами сканера. Подтверждения и исправления из переписки issue #5 сверены с историей чатов и свежим чтением issue.
- Получен **21 STIX-файл** Vulnetix; SHA-256 каждого совпал с текущим индексом. `malscan --fetch-definitions` обновил также runtime definitions: 16 внешних источников доступны, один URLHaus вернул HTTP 410. Индекс и STIX скачаны успешно; старый источник URLHaus не считается обновлённым.
- OSV: целиком скачаны свежие архивы npm, PyPI, crates.io, Go, Pub. Они включают GHSA, PYSEC, RUSTSEC, Go и MAL-записи OpenSSF; алиасы объединены. Сопоставление локальное, списки зависимостей не отправлялись. **304 манифеста**, до изменений 3 720 закреплённых версий, после — 3 716. Ошибок парсинга нет.
- Снимок для статических сканеров: **6 700 отслеживаемых файлов, 83 947 331 байт**. Исключены каталоги artifacts/research/docs/vendor/tests/assets, окружения, сборки и symlink; отдельные inline-тесты, векторы и исследовательские скрипты вне этих каталогов попадают в снимок. Точный список и хеши: `source-inventory.json`. Снимок сделан до исправлений этого аудита; изменённые протокольные файлы затем проверены тестами и вручную.
- Manifest-only диапазоны без разрешённой версии остаются видимыми в `dependencies-after/unresolved-requirements.json` (это не счётчик уникальных непроверенных пакетов). Локальные ignored-копии рассматриваются отдельно от отслеживаемого источника: общий OSV-отчёт содержит их устаревшие зависимости, в том числе HIGH/CRITICAL. Их не следует устанавливать или считать проверенным production-источником.

Происхождение загрузок, даты и SHA-256: `initial-fetch.json`, `download-provenance.json`, `vulnetix-osv-provenance.json`, `dependencies-after/dataset-provenance.json`. Большие базы и исходный SARIF OSSGadget хранятся во временном cache `/private/tmp/aicom-security-review-20261030/`; в репозитории сохранены сводки, совпавшие записи и воспроизводимые проверки.

## Исправленные дефекты протоколов

1. **HISTOR: ограничение HTTP body после полной загрузки.** Witness принимал весь stream в память, затем проверял 16 KiB; публичные JSON-операции так же проверяли 2 MiB после buffering. `read_bounded_body` останавливает чтение сразу при превышении лимита. Тест проверяет отказ на chunked-потоке, отсутствие чтения хвоста и принятие тела ровно на границе.
2. **Rust-федератор: DNS rebinding между проверкой и соединением.** Раньше `check_fetch_url` проверял один ответ DNS, а ureq разрешал имя повторно самостоятельно. Теперь resolver проверяет именно адреса, передаваемые dial, отказывает при смешанном public/private ответе; ambient HTTP proxy отключён, Host/TLS hostname остаются исходными. Redirects по-прежнему запрещены. Тесты проверяют private, смешанный и пустой набор адресов.
3. **Rust и Go: IPv6 transition routes.** NAT64, 6to4 и Teredo могли обходить проверку прямых private IPv4. Эти transition-префиксы теперь консервативно отклоняются; добавлены негативные случаи для loopback/private IPv4 внутри IPv6.
4. **Rust: неограниченная рекурсия JSON.** Удалённый announce/manifest мог вызвать переполнение стека глубокой вложенностью. Лимит — 128 контейнеров; документ глубиной 100 000 отвергается без обхода всей вложенности. JS-парсер receipt получил тот же лимит.
5. **Rust/JS: неоднозначный и некорректный JSON.** Оба парсера теперь отвергают повторные ключи, включая одинаковые имена через Unicode escape, неполные экспоненты и неэкранированные control characters. JS проверяет четыре hex-цифры Unicode escape; Rust корректно объединяет surrogate pairs и отклоняет некорректные. Проверены валидная emoji-пара и обычная экспонента.

Предыдущее исправление `c0eca9020` (ASCII и границы чисел размеров HISTOR) включено в тестирование. Указанные изменения не требуют ослабления подписи, доверия к peer или авторизации.

## Тесты и проверяемые границы

| Набор | Результат |
|---|---:|
| Hub: полный suite, федерация, платёжные каналы, x402, подписи, replay, crawler, admission, paid tier, transport | 3 760 passed, 17 skipped |
| Hub: денежные гонки и pool scoping на отдельном disposable PostgreSQL | 18 passed |
| HISTOR: полный suite вне внешней integration-папки, SQLite **и PostgreSQL**, checkpoint/witness/log/MCP | 1 126 passed, 0 skipped |
| Oracle core: полный suite, включая proxy/paid-tier guards | 578 passed, 1 skipped |
| AWR Python reference и emitter, все 69 reason codes | 486 passed |
| Desk kernel | 92 passed |
| JS emitter, receipt verifier и новые parser regressions | 25 passed |
| AWR conformance: Python/Rust/browser-node | 354/354, все три реализации conformant |
| AIMarket Protocol vectors | 23/23 |
| Rust protocol unit/admission/vector/parser regressions | проходят |
| Rust AWR полный cargo suite | проходит |
| Go федератор полный go test ./... | проходит |

Наборы пересекаются; строки не суммируются как уникальные тесты. Первые попытки с запретом локальных сокетов дали инфраструктурные падения; окончательные результаты — full/PG XML и final-логи. Для HISTOR закрыты все 219 ранее пропущенных PostgreSQL-вариантов. Оставшиеся пропуски полного Hub и oracle-core перечислены в XML, включая необязательные плагины и тесты PostgreSQL вне отдельного выбранного набора; live integration со всеми внешними сервисами не выполнялась.

## Сканеры из обзора и дополнительные проверки

| Инструмент | Что реально выполнено |
|---|---|
| **Vulnetix CLI 3.151.2 / malscan-engine 0.6.1** | Официальная macOS arm64-сборка, SHA-256 проверен. Явный локальный install-layout со снимком first-party source, 6 700 файлов, без home/system scan, upload, analytics и memory. 52 IOC-срабатывания; других detector hits нет. |
| **GuardDog 3.2.0** | Локальные Python и npm scans снимка; `errors={}`. Source heuristics выполнены; registry metadata не передавались, popularity caches недоступны в офлайн-запуске. Threat/capability findings сохранены раздельно; metadata rules на такой local source scan не покрыты. |
| **OSSGadget 0.2.38** | Установлен официальный NuGet CLI, дополнительно все 10 файлов BackdoorRules из тега v0.2.38. Без правил первоначальный запуск дал предупреждение — этот пустой результат не использован. Рабочий прогон: 176 138 regex-сигналов в 4 239 файлах. Полный SARIF ~497 MB; SHA и ограниченная сводка сохранены. Это широкие эвристики, не 176 тысяч подтверждённых уязвимостей. .NET 8 tool исполнялся на .NET 10 с roll-forward. |
| **malcontent** | Официальный registry cgr.dev вернул 403; Docker Hub mirror дважды завершился сетевым EOF. Запуска нет, clean-вердикта нет. |
| **Atomdrift Scan 2.13.0** | Бинарник и SHA-256 проверены, модели stable `2b5ea646` получены. Traits `76e610a9af` не загрузились после повторов, прямой URL вернул 403; запуск сообщил `No YARA rules loaded` и завершился ошибкой. Результат не используется как scan. LLM и hopper не включались. |
| **Packj** | Свежий официальный образ получен. В отличие от ранее проверенной версии, help заявляет local_python/local_nodejs. Попытка local_python HISTOR без сети не стартовала: импорт/инициализация требует DNS pypi.org. Полезного scan-result нет; trace и выполнение анализируемых пакетов не включались. |
| **Bandit 1.9.4** | 506 518 строк Python, 0 ошибок анализа. 1 925 сигналов, из них 9 HIGH; все HIGH разобраны в `bandit-triage.json`. Medium/Low сохранены как очередь, не названы исправленными или полностью разобранными. |
| **gitleaks 8.30.1 + structured-secret verifier** | Снимок first-party source: structured check прошёл. gitleaks дал 379 generic-api-key срабатываний; triage — публичные ключи/DID, Anvil development keys, fixture/canary, identifiers и demo receipt tokens. Значения редактированы. Подтверждённой новой production credential leak в снимке не установлено; полномочия старых demo receipt tokens на live-серверах не проверялись. Git history, окружения и все бинарные артефакты этим результатом не покрыты. Дополнительный scan всего Git index нашёл 5 разных public browser API token literals в ранее сохранённом YouTube HTML; 18 вхождений отредактированы в текущем снимке. Это не установленные секреты аккаунта alexar76; история не переписывалась, исходный hash и redaction receipt сохранены. |

52 сигнала Vulnetix: публичные RPC Solana/Ethereum/Polygon, `pump.fun`, Rust-вызовы `self.ws()` и public-IP fixture `104.16.0.1`. Каждый сохранён с файлом, строкой и интерпретацией в `vulnetix-malscan-triage.json`. Сам сканер выставляет `malicious=true`; это отражено, но наличие строки IOC не доказывает вредоносную операцию. Доступность и репутация внешних сервисов не сертифицировались.

GuardDog отмечает, в частности, observer canaries HISTOR, Telegram notification code, scanner research strings, environment config, учебные/install helpers и generated sqlite JS. Срабатывания не являются доказательством malware; проверки доверия в каждом из этих компонентов отдельно не исчерпаны. OSSGadget указывает и на те же install helpers/описания возможностей. Приоритетный ручной разбор выполнен по протоколам и HIGH Bandit; весь массив эвристик не объявляется подтверждённо безопасным.

## Зависимости: что изменено и что осталось

Обновлены пять lock-файлов с `aimarket-oracle-core` до 0.6.3, `dnspython` desk-kernel до 2.9.0, `systeminformation` в Kova/Verified Execution Hub до 5.33.19, `@hono/node-server` там же до 2.1.5, Vite Pantheon до 6.4.5. Подробный diff версий — `dependency-changes.json`. dnspython обновлён по официальным PyPI artifact URL/hash без исполнения sdist: штатный `uv --no-build` блокировался старой зависимостью http-ece. Остальные locks обновлены штатными uv/npm без install scripts. Смена lock не обновляет уже установленное окружение.

Остаются **три advisory ID в tracked source**:

1. **MODERATE GHSA-rmxm-3fg6-px4f**, `@hono/node-server 1.19.17`, Daily Card. Исправление 2.1.3 требует major-перехода. Уязвимость касается обхода prefix middleware при выдаче static files. Текущий код выдаёт `webDist` как публичный root, prefix-auth для его части в исходнике не обнаружен; без проверки runtime config это условная оценка, запись оставлена видимой.
2. **MODERATE GHSA-wx4j-mvgx-mqwp**, `satori 0.16.0`, Kova и Verified Execution Hub. Исправление 0.33.5; прямого использования Satori в first-party коде не найдено. Transitive dependency остаётся; обновление и проверка SVG/OG цепочки нужны отдельно.
3. **LOW GHSA-gcqx-w48m-w2h4**, `deepmerge 4.3.1`, четыре frontend lock-файла. Prototype poisoning результата merge; фиксированная версия в advisory не указана. Использование с недоверенными объектами и downstream patch/replacement требуют отдельного разбора.

Одна некорректная upstream OSV range (`PYSEC-2024-311`, wasmtime 49.0.0) оставлена в errors и отдельно разобрана в `osv-range-disposition.json`: текущая версия выше всех перечисленных affected upper bounds. Это не ошибка чтения манифеста и не скрытый clean-результат.

## Границы результата и дальнейшая эксплуатация

Аудит расширен на всё дерево manifests и несколько реализаций протоколов, а не только на один checkpoint-патч. При этом не выполнены production rollout и сплошная инвентаризация контейнеров/OS-пакетов, обновление Node/интерпретаторов, полноценный сетевой pentest всех сервисов, проверка каждого маршрута каждого продукта или доказательство отсутствия неизвестных уязвимостей. Сам факт прохождения тестов не заменяет эти проверки.

Нельзя сообщать «все дыры закрыты»: остаются три dependency advisories, непроверенные runtime-конфигурации и очередь Medium/Low/эвристик. Подтверждённые здесь изменения готовы к review; GitHub writes и отправка сообщений Vulnetix не выполнялись.

Основные первоисточники: [Vulnetix database](https://github.com/Vulnetix/advisory-database), [переписка issue #5](https://github.com/Vulnetix/advisory-database/issues/5), [STIX index](https://vulnetix.com/malscan-stix/index.json), [официальный CLI](https://github.com/Vulnetix/cli), [OSV bulk data](https://google.github.io/osv.dev/data/), [Packj audit documentation](https://github.com/ossillate-inc/packj/blob/main/packj/audit/README.md).
