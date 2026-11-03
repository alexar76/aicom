# Аудит безопасности aicom — 31 октября 2026

Проверены локальные исходники экосистемы `alexar76`, зависимости и границы Docker-сборки. Подтверждённые дефекты исправлены локально. Production, опубликованные npm/PyPI-пакеты и GitHub этим запуском не изменялись.

После исправлений: **0 HIGH/CRITICAL OSV-совпадений в отслеживаемых манифестах**, **0 совпадений с проверенными публичными записями Vulnetix**. Два оставшихся OSV-срабатывания на старые версии minimatch сохранены в исходном отчёте и отдельно разобраны как отсутствие описанного уязвимого кода. Это не заключение о полной безопасности всех серверов, системных пакетов или неизвестных дефектов.

## Что проверено

- 304 манифеста, из них 286 отслеживаются Git; 3 713 различных закреплённых сочетаний пакет/версия, из них 2 895 встречаются в отслеживаемых манифестах.
- Свежие полные архивы OSV для npm, PyPI, crates.io, Go и Pub: **270 620 записей**. Архивы включают записи GHSA, PYSEC, RustSec, Go и malware advisories. Происхождение, время загрузки и SHA-256: `download-provenance.json`, `dependencies-final/dataset-provenance.json`.
- **2 619 опубликованных OSV-записей Vulnetix** семейств PYPI/NPM/GO/CARGO и соответствующих VULN-семейств, commit `2bd7e6b782040caa1ad8d26ee6cccabef72ea986`. Сопоставлены также собственные имена и версии из 166 манифестов. Ошибок сопоставления нет. Это публичный advisory-database, а не заявление о проверке всех закрытых/API-источников VDB. Подтверждение: `vulnetix-provenance.json`, `vulnetix-matches-final.json`.
- Сопоставление с базами выполнялось локально; исходники в базы не передавались.
- Снимок 6 708 отслеживаемых файлов собственного кода: Bandit и gitleaks, дополнительная проверка структурированных секретов. Исключены окружения, сборки, vendor, тесты, research, docs и artifacts. Приоритетный ручной разбор: исходящий HTTP, наблюдаемые продавцы, кэш SKOPOS, аудит deployed versions, запуск исследовательского парсера и Docker-контекст.

## Исправления

| Проблема | Изменение и подтверждение |
|---|---|
| **Истощение памяти через сжатый ответ внешнего peer** | В `aimarket_hub/outbound_http.py` HTTPX распаковывал блок до проверки размера. При бюджете 4 КБ воспроизведено выделение 25 279 842 байт для ответа, распаковывающегося в 8 МиБ. Теперь читается raw stream, ограничиваются входные байты и выход zlib. gzip/deflate сохранены; повреждённые, составные, неподдерживаемые и усечённые потоки отклоняются. Проверены закрытие ответа, граничные размеры и память. `outbound-before.log`, `hub-security-final.log`. |
| **Исполнение callable из локального кэша SKOPOS** | `pickle.load` заменён существующим в проекте JSON/base64-форматом, общим для файлового и DB-кэша. Предусловие атаки — возможность подменить файл кэша; удалённый неавторизованный путь записи не установлен. Безопасный reducer в тесте выполнялся до исправления и больше не выполняется. Старые pickle-файлы становятся cache miss, данные пересчитываются. DataFrame и графики проходят round trip. `snapshot-before.log`, `snapshot-targeted-final.log`. |
| **Некорректные цены и URL наблюдаемых продавцов** | Отрицательные, нулевые, не-ASCII, неканонические и превышающие uint256 суммы больше не превращаются в платёжное предложение. NaN/Infinity и отрицательная discovery-цена не сохраняются как цена. Некорректный URL не обрывает обработку продавца. До исправления 17 из 18 новых проверок падали. Эти предложения не исполняют платёж через hub; проблема затрагивала корректность выдачи, сравнение бюджета и доступность обработки. `observed-before.log`, `hub-security-final.log`. |
| **Shell injection в исследовательском MCPTox builder** | Путь к датасету передавался в `os.system` без quoting. Теперь `subprocess.run` получает массив аргументов и `check=True`. Датасет по-прежнему разбирается через AST, его Python-код не исполняется. Проверен путь с пробелами и `;touch PWN;#`: файл-маркер не появляется, набор создаётся. `mcptox-regression.log`. |
| **Ложно чистый runtime-аудит при ошибке OSV/SSH** | `scripts/deployed_versions.py` больше не возвращает пустой успешный результат при сетевой ошибке, неполной/пагинированной OSV-выдаче, недоступной severity или ошибке инвентаризации. Exit code 2 и JSON `status: incomplete`; подтверждённое отсутствие Node отмечается отдельно. Ошибка одного контейнера не скрывается успехом другого. `runtime-gate-before.log`, `audit-gates-final.log`. Сам fleet этим запуском не опрашивался. |
| **Локальные служебные данные в Docker-образе** | Корневой `COPY . .` мог захватывать artifacts/output, `.internal`, вложенные Git/SSH/AWS/agent-каталоги, дополнительные venv, runtime-состояние и старую копию `lottery/alien-monitor`. Добавлены исключения. Реальные admin/provider-настройки под `data/` остаются исключёнными; после общего правила повторно разрешён только публичный `model_providers.example.yaml`, который нужен Dockerfile. Проверены сохранение runtime source, Solidity libraries и WARDEN measurements. Новая сборка образа не выполнялась. `docker-context-before.log`, `docker-context-final.log`. |

## Новые advisories зависимостей

Две записи появились в скачанной OSV-базе после предыдущего аудита, с OSV publication time 30 октября около 23:09 UTC. Сами upstream advisory pages датированы 27 октября.

- [CVE-2026-118773 / GHSA-3g3m-2fjr-6pw4](https://github.com/isaacs/node-glob/security/advisories/GHSA-3g3m-2fjr-6pw4): обход отмены обхода каталогов в glob. Обновлено до **14.0.2** в Emberline и Solana tooling. Регрессия на временном дереве: после abort — **0 дополнительных readdir**, обычный поиск продолжает работать.
- [CVE-2026-118764 / GHSA-g3hv-75wg-m249](https://github.com/isaacs/minimatch/security/advisories/GHSA-g3hv-75wg-m249): размножение globParts при `optimizationLevel >= 2`. Современные ветки 9/10 обновлены до **11.0.1** в TypeScript SDK, Emberline, Solana tooling, Kova, Aegis, PingBlip Memeforge/Web и Factory frontend. Scoped override сохраняет старый callable API там, где он нужен.

**Оставшиеся raw matches minimatch 3.1.5/5.1.9 не скрыты.** Upstream описывает `firstPhasePreProcess`, а OSV указывает широкий диапазон `<11.0.1`. В проверенных старых исходниках нет ни этого метода, ни обработки `optimizationLevel`. На атакующем шаблоне остаётся один globParts entry. Хеши исходников и результаты: `advisory-disposition.json`, `dependency-regressions.json`. Это локальная оценка применимости конкретного CVE, а не исправление upstream-базы и не исключение этих пакетов из будущих проверок.

Дополнительно устранена обнаруженная несогласованность PingBlip Web: его локальный folder-link адаптера `fast-glob` не обеспечивал разрешение собственной зависимости tinyglobby в lockfile. Оба проекта теперь используют локальный `.tgz` того же адаптера; установленные байты совпадают с исходником. Пакет не публиковался. `adapter-provenance.json`; оба установленных адаптера проходят собственные тесты.

Все восемь изменённых npm-деревьев проходят `npm ls --package-lock-only --include=dev --all`; install scripts не запускались. Точный diff версий: `dependency-changes-final.json`.

## Проверки и известные сбои общего QA

| Набор | Результат |
|---|---:|
| Hub: bounded HTTP, DNS pinning, observed sellers, federation assay | 170 passed |
| Audit gates, dependency scanner coverage, MCPTox paths | 101 passed |
| SKOPOS: файловый/DB-кэш, DataFrame, защита от pickle | 4 passed |
| Docker-контекст и сохранение нужных файлов | 30 passed |
| TypeScript SDK | 75 passed; TypeScript build прошёл |
| Emberline | 19 passed; полный TypeScript/Vite/PWA build прошёл |
| Solana JS client compatibility | 5 passed; typecheck прошёл |
| Kova/Aegis | оба typecheck прошли; реальный ts-morph glob selection прошёл |
| ESLint | реальный lint с временной конфигурацией в четырёх проектах прошёл; штатные print-config Factory/PingBlip прошли |

Строки относятся к указанным отдельным наборам; промежуточные повторные прогоны не суммируются.

Три существующие проблемы общего QA сохранены явно: SDK `npm run lint` не находит eslint.config; UI-тест SKOPOS ожидает отсутствующий `radio[0]` (тот же сбой воспроизведён с исходным модулем из HEAD); полный service-env suite даёт 151 passed/1 failed из-за трёх ранее неразрешённых env-имён factory, тот же assertion воспроизведён тестом из HEAD. Доступ сервиса к дополнительным credentials ради зелёного теста не расширялся. Это не падения целевых регрессий исправлений.

Bandit исходного снимка: 507 985 строк Python, 0 ошибок разбора, 1 930 сигналов, 9 HIGH. Один HIGH — исправленный shell call; остальные соответствуют прежнему разбору (локальные smoke helpers, неаутентификационные хеши, защитные Unicode-списки, явный SSH opt-out). Повторная проверка пяти изменённых production Python-файлов: 0 HIGH, 2 MEDIUM, 6 LOW. Все medium/low исходного дерева не объявляются полностью разобранными.

gitleaks: 379 `generic-api-key` сигналов, без новых file/rule locations относительно предыдущего снимка. Два изменённых файла с совпадениями содержат публичные `did:key` идентификаторы. Structured-secret check прошёл. Подтверждённой новой утечки production credential в этом source-снимке не найдено; история Git и private env этим результатом не покрыты. `secret-triage.json`.

## Остаточные ограничения

- В 18 ignored/untracked манифестах есть старые зависимости, в том числе HIGH/CRITICAL: npm-инструменты upstream OpenZeppelin checkout, старый `lottery/alien-monitor` и сохранённые distribution-снимки. Их файлы не удалялись и исторические доказательства не переписывались. Старый monitor и docs не попадают в корневую Docker-сборку; dev tools внутри upstream Solidity checkout нельзя считать обновлёнными. Полный raw-отчёт — `dependencies-final/findings.json`.
- 1 084 строки незафиксированных требований сохранены отдельно; многие покрываются соседним lockfile, но manifest-only диапазоны без разрешённой версии не считаются проверенными установленными зависимостями.
- У PYSEC-2024-311 повреждён upstream range. Сегодня повторно проверено, что запись не изменилась, а установленная в манифесте wasmtime 49.0.0 выше всех перечисленных верхних границ. Ошибка остаётся в `matching-errors.json`, обоснование — `osv-range-disposition.json`.
- Live fleet, OS/container packages, внешние интеграции, Git history и все пути исполнения не проверены исчерпывающе. Локальный патч не исправляет уже запущенный процесс: для переноса защиты в production нужны соответствующие сборки и deployment.
- Параллельные чужие изменения в рабочем дереве сохранены. Список файлов именно этого исправления и SHA-256: `changed-files.json`. Машиночитаемая сводка: `summary.json`.
