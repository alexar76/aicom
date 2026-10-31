# Внешние изменения кода и использование релизов alexar76 30 октября 2026 года

**Подтверждены два дополнительных внешних сигнала: конкретные изменения продуктов Verdict Row по результатам наших тестов и использование точного релиза WARDEN во внешней классификационной работе.** Новый независимый клиент или установка нашего firewall в чужой production этим проходом не установлены.

База включает не только основной отчёт 30 октября, но и оба JSON-аудита 29 октября. Поэтому FPL Cat и исходное предложение QuincyGB не считаются новыми находками этого прохода.

## Verdict Row реализует наши замечания

В [AICOM issue 13](https://github.com/alexar76/aicom/issues/13) после первоначального входящего предложения появились три внешних ответа QuincyGB:

| Ответ МСК | Что сообщил внешний автор |
| --- | --- |
| [29 октября 15:27](https://github.com/alexar76/aicom/issues/13#issuecomment-6496661337) | Признал два замечания: округление $0,001 до $0,00 и смешение стабильности quality score со стабильностью контракта. Сообщил об исправлении и предложил продолжить проверку. |
| [30 октября 04:31](https://github.com/alexar76/aicom/issues/13#issuecomment-6512718071) | Признал сброс истории RouteVerdict при redeploy и согласился публиковать Recheck как JSONL по стабильному URL. |
| [30 октября 05:07](https://github.com/alexar76/aicom/issues/13#issuecomment-6513192467) | Сообщил о persistent volume и успешном собственном restart-тесте; дал адрес работающего feed. Старые полные ответы 25 октября не обещает восстановить из отсутствующих данных. |

Это **одна внешняя команда и один контакт**; три ответа и пять commits не считаются отдельными внедрениями.

Проверены закреплённые commit diffs — изменения присутствуют в исходниках и тестовых файлах:

| Commit | Изменение |
| --- | --- |
| [RouteVerdict 5a36f743, 29 октября 15:18 МСК](https://github.com/QuincyGB/route-verdict/commit/5a36f743d0b2b9b6dd42ee075f25d138e738e166) | Decimal-форматирование субцентовых сумм; отдельные schema_score_stability и contract_stability; регрессионные случаи. Автор прямо связывает исправления с review AICOM и требованием alexar76. |
| [RouteVerdict 15aec9f4, 30 октября 04:38 МСК](https://github.com/QuincyGB/route-verdict/commit/15aec9f488494efeaa981fb80cc5800cd5dd7f40) | Выбор persistent DB и видимость storage через /health. Commit ссылается на потерю предыдущего check после нашего повторного теста. |
| [StallRow 9303c9d6, 30 октября 04:42 МСК](https://github.com/QuincyGB/stall-row/commit/9303c9d6e9862c599711e979a8acba342dc634d7) | Публичный Recheck feed: сохранение каждого ответа и выдача JSONL. Commit прямо называет обещание AICOM survey. |
| [RouteVerdict 87503852, 30 октября 05:17 МСК](https://github.com/QuincyGB/route-verdict/commit/8750385243aa1aa89e71dbf5fff72f041e7b8286) | История проверок ресурса и field_changes с типом конкретного изменившегося поля. Есть ссылка на aicom#13. |
| [StallRow d7169826, 30 октября 05:24 МСК](https://github.com/QuincyGB/stall-row/commit/d71698264878f8daccec703b1d1f6d205aad47ff) | Versioned feed envelopes, hash chain, baseline pins/imports, field-level diffs, webhooks и timeline. Commit обозначает связь с пятью улучшениями AICOM; реализация этих интерфейсов видна в diff. |

Прямой **бесплатный GET** [Recheck feed](https://stall-row-production.up.railway.app/v1/recheck/feed) и его [v2](https://stall-row-production.up.railway.app/v1/recheck/feed?v=2) вернул HTTP 200: по 16 строк, включая две записи для modelmarket.dev/x402/histor-check. В обычном feed эти две строки содержат сохранённые состояния наших review-watch, без исторических status/changes. В v2 есть seq, record_id, prev_hash и record_hash. Проверена выдача структуры; криптографическая цепочка здесь заново не валидировалась.

[RouteVerdict health](https://route-verdict-production.up.railway.app/health) теперь сообщает check_store=persistent и /data/route-verdict.db. Это наблюдение ответа сервиса, не независимая проверка сохранности через restart.

**Что это доказывает:** внешний разработчик использует наши результаты тестирования для изменений своего продукта; конкретные изменения опубликованы, бесплатный feed работает. **Чего это не устанавливает:** внедрение нашего кода, нового покупателя HISTOR или органический спрос. Обе стороны прямо называют платежи requested review tests. Два modelmarket-watch в feed происходят из этих тестов. Платные вызовы, restart и чужие тесты в данном проходе не выполнялись. Количество passed tests в commit messages — заявление автора.

Сохранены полные API-ответы, [выбранные diff-фрагменты](quincy-selected-diffs.json) и [факты живой выдачи](quincy-live-facts.json).

## WARDEN используется как внешний классификационный образец

[Commit isotope13-dev/traits-dev от 21 октября 23:15 МСК](https://github.com/isotope13-dev/traits-dev/commit/d28c0c79dfc7aecb94c40acbbc8109ecee26d2ab) перечисляет @aimarket-warden-0.18.0.tgz, SHA-256 и переклассификацию suspicious → good. Пояснение относится к public-key PEM и verify-side использованию. В конце указан opencode с моделью GLM; человеческая независимая рецензия этим не установлена.

Идентичность образца проверена непосредственно: [опубликованный npm tarball @aimarket/warden 0.18.0](https://registry.npmjs.org/@aimarket/warden/-/warden-0.18.0.tgz) имеет SHA-256 **30b96f217c7ca951c3061e33b12e2601a739d6e14384e17f33998dc512f21c73**, точно совпадающий с commit message. Архив не устанавливался, не распаковывался и не исполнялся.

README внешнего traits-dev связывает правила со сканером [Atomdrift cleave](https://github.com/atomdrift-project/cleave). Это новый для проверенных сводок **след внешнего рассмотрения подлинного опубликованного пакета**. Корректность оценки, полный журнал сканирования и runtime-использование WARDEN внешним приложением не установлены. Commit меняет другие правила в том же наборе; отдельная правка правила WARDEN или публичный fixture WARDEN в его diff не обнаружены. Поэтому сведения о переклассификации атрибутируются автору commit, а совпадение артефакта подтверждено нами.

[Факт идентичности пакета](traits-package-identity.json) сохраняет URL, дату, хеши и границы вывода.

## Поиск чужого кода вне README

В Sourcegraph выполнены два завершённых публичных поиска: точные package markers и домены, с исключением alexar76 и README, но с включением forks/archives. Package-запрос вернул ноль совпадений; доменный — две Markdown-карточки eSIM operator kit в одном каталоге Arnon-hs/open-source. Эти карточки — дистрибуция описания проекта, не развёртывание оператора.

Дополнительно прочитаны GitHub commit/issue search по точным маркерам. Широкий aimarket-agent дал чужие одноимённые проекты Microsoft/DanWahlin и китайские AIMarket; уникальные ссылки на нашу экосистему у них не установлены. Собственные исторические submissions, зеркала, awesome forks и автоматические обновления scorecards исключены из независимого использования.

Деревья Industrial Platform, RugSnare и MCPMoat прочитаны целиком как списки файлов; исполняемый чужой код не запускался. В выбранных history.js/workflow RugSnare новой интеграции API HISTOR не найдено. Это ограничение выбранных файлов, не отсутствие любой возможной интеграции.

Codeberg project search aimarket вернул пустой список. GitLab project search — три совпадения по похожим названиям без установленных уникальных признаков нашей экосистемы; полный код этих проектов не читался. GitHub authenticated code search не использовался. Эти индексы не охватывают частные проекты и все HTTP-вызовы.

## Область и свидетельства

Выполнены **20 web-запросов и 35 прямых публичных GET**, включая 13 запросов поисковых API/индексов. Все 35 GET завершились HTTP 200; каждое сохранённое тело проверено по SHA-256. Статус HTTP 200 не означает положительной находки.

[verification-index.json](verification-index.json) объединяет запросы, даты, статусы и имена сырых файлов. [summary.json](summary.json) содержит классификацию результатов. Нового независимого runtime-внедрения сверх прежнего Industrial Platform этот проход не подтвердил. Сообщения, GitHub writes, авторизации, установки, платные API и платежи не выполнялись.

