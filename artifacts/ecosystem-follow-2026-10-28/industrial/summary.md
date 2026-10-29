# Industrial Platform: история интеграции AIMarket Hub — 28 октября 2026

Проверка около 17:59–18:05 МСК. Новое по отношению к прежнему подтверждению manifest: **внешний проект прямо зависит от нашего AIMarket Hub и имеет успешную CI-проверку его установки и импорта**. Отдельно установлены точные наши домены в workflow анонса. Всё выполнено только чтением публичных источников; ни один внешний workflow, POST, invoke, установка или платёж нами не запускался.

## Прямая зависимость от кода alexar76

[requirements.txt в закреплённом commit0266b6d](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/0266b6d59355acdebec6e76036e2451396d2799f/aimarket-sentinel/requirements.txt#L1) содержит `git+https://github.com/alexar76/aimarket-hub.git@2310569f1e4e50e1062d80725bd69ae313042a69`. Текущий main вернул те же байты. Это точная ссылка на наш репозиторий и commit, а не совпадение имени AIMarket.

[Dockerfile](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/0266b6d59355acdebec6e76036e2451396d2799f/aimarket-sentinel/Dockerfile#L8) устанавливает requirements и запускает app.py через uvicorn. [app.py5–8](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/0266b6d59355acdebec6e76036e2451396d2799f/aimarket-sentinel/app.py#L5) импортирует `aimarket_hub.api/config/database/models` и создаёт четыре локальные Sentinel-capability.

Это подтверждённая **интеграция библиотеки в опубликованном исходнике и build-конфигурации**. Сам Python-контейнер нами не собирался, его production-развёртывание не установлено. Ранее проверенный живой Node gateway — отдельный путь реализации; нельзя автоматически считать его этим Python-приложением.

## Установка и импорт Hub в чужом CI

Самая ранняя [проверка Verify Sentinel Distribution](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/actions/runs/37384892675) выполнена **5 октября 22:49 UTC** (6 октября01:49 МСК), head `5a400bd4b2d82c495ccb54e0aea007a02cb9f60a`.

GitHub jobs API сообщает `success` для job **aimarket** и отдельно для шагов:

- `Run pip install -r requirements.txt`;
- `Import hub and verify four offerable capabilities`.

[Workflow в точном head коммите](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/5a400bd4b2d82c495ccb54e0aea007a02cb9f60a/.github/workflows/verify-sentinel-distribution.yml#L34) ставит пакет, импортирует app и проверяет `app.db.count_offerable("local")==4`. В прочитанном workflow нет `continue-on-error`, условия пропуска этих шагов или флага Python `-O`. Важная хронология: [requirements этого запуска](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/5a400bd4b2d82c495ccb54e0aea007a02cb9f60a/aimarket-sentinel/requirements.txt#L1) — **aimarket-hub==3.14.0**, а не нынешний Git pin. [Метаданные PyPI этой версии](https://pypi.org/pypi/aimarket-hub/3.14.0/json) прямо указывают Repository/Documentation `alexar76/aimarket-hub` и Homepage `modelmarket.dev`.

Таким образом, публичная CI-система сообщает успешную установку и использование нашего пакета в тестовом приложении. Это сильнее намерения в README; не доказаны production-запуск Python Hub, независимые клиенты или платные вызовы. Журналы Actions получили403, поэтому конкретный stdout этого запуска не читался и CI-результат нами не воспроизводился. Повторов/обхода403 не было.

Свидетельства: `distribution-runs.json`, `distribution-initial-jobs.json`, `distribution-test-workflow.json`, `requirements-at-initial-run.json`, `ci-package-provenance.json`. Сам [job](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/actions/runs/37384892675/job/112015630799) доступен по прямой ссылке.

## История адаптера и анонс нашим Hub

История `gateway/aimarket-federation.mjs` содержит два коммита от аккаунта industrial-platform:

| UTC 5 октября | Коммит | Действие |
| --- | --- | --- |
| 22:49:29 | [5a400bd](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/commit/5a400bd4b2d82c495ccb54e0aea007a02cb9f60a) | Добавляет Python AIMarket Hub и portable distribution. |
| 22:53:22 | [e3cd892](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/commit/e3cd89289faed6d785fa4fddaf406e158403cfe8) | Добавляет Node federation adapter и регистрирует его в gateway/server.mjs. |
| 23:05:37 | [0266b6d](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/commit/0266b6d59355acdebec6e76036e2451396d2799f) | Закрепляет bootstrap artifacts. |

[Workflow анонса44–54](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/e8f654c6e9825a23b885a8d92a414ea6a29109d9/.github/workflows/announce-sentinel-aimarket.yml#L44) явно содержит `hub.modelmarket.dev`, `hunt.modelmarket.dev` и `modelmarket.dev`, маршрут `/ai-market/v2/federation/announce`. До анонса workflow предусматривает бесплатный install-invoke на собственном Sentinel. Это описание чужой автоматизации; нами такие запросы не выполнялись.

Публичные metadata показывают четыре существующих запуска workflow: два success и два failure. У [последнего успешного](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/actions/runs/37386350807) шаг Verify/announce также success. Текст workflow на точном runhead совпадает с прочитанной закреплённой версией. Но доступ к logs403: точные HTTP-ответы наших трёх Hub не прочитаны. Поэтому **не заявляется полученная нами квитанция принятия анонса, admission или вызовов**. Привязка к нашим доменам установлена исходником; результаты видимости пира root проверяет отдельно.

## Область и ограничения

12 web-запросов по exact names/слугам/строкам/доменам не дали новой независимой публикации вне этой цепочки. Шумовые каталоги и патентные совпадения исключены. 24 прямых GET:23 HTTP200, один403 для Actions logs. GitHub search API не использовался. Дерево455путей — инвентарь, а не чтение всех файлов; прочитаны только выбранные исходники, manifests и workflow.

Оператор/юридическое лицо, человеческое авторство каждого изменения, официальный партнёрский статус и объём пользовательского спроса не устанавливались. Использование наших кодовых зависимостей в CI и публикация совместимого внешнего manifest — разные, отдельно подтверждённые факты.

Журналы: `query-log.json`, `verification-index.json`. Все GitHub действия — GET; сообщений, PR, push, rerun, публикаций и изменений аккаунтов не выполнялось.
