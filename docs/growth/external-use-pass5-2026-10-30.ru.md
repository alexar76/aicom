# Новые свидетельства внешнего использования AICOM 30 октября 2026 года

**Уже известный внешний форк Enterprise Factory подтверждён на более сильном уровне: его GitHub Actions содержит завершённые шаги CI с тестированием backend, сборкой frontend и проверками production-конфигурации.** Это дополнительное свидетельство использования кода в чужой сборочной среде. Работающий внешний production-сервис, новый покупатель или новая интеграция 30 октября этим не установлены.

Дата события — **14 октября**, дата дополнительной проверки — **30 октября**. Сам форк и его собственные изменения были известны [26 октября](../evidence/external-mentions-2026-10-26/enterprise-factory.json); повторным обнаружением проекта они не считаются.

Публичный аккаунт владельца отличается от alexar76; его фактическая принадлежность отдельно не расследовалась.

## Внешний форк выполнял CI

[Запуск CI Enterprise Factory](https://github.com/th3artfuldodger/enterprise-factory/actions/runs/38629232333) создан 14 октября в 20:06 UTC / 23:06 МСК, head_sha=ef124a40d592bf149fab93fb632a4aaf688a04fa. В API все три jobs имеют conclusion=success, выбранные шаги завершены и не помечены skipped:

| Job | Что подтверждено метаданными и опубликованным workflow |
| --- | --- |
| [backend-tests](https://github.com/th3artfuldodger/enterprise-factory/actions/runs/38629232333/job/116076256030) | Checkout, получение satellite dependencies, установка backend dependencies, вызов Factory pytest suite и выдача coverage report. |
| [frontend-build](https://github.com/th3artfuldodger/enterprise-factory/actions/runs/38629232333/job/116076255938) | Установка npm dependencies и Build; package.json определяет build как next build. |
| [Production misconfig guards](https://github.com/th3artfuldodger/enterprise-factory/actions/runs/38629232333/job/116076255419) | Получение зависимостей, установка backend dependencies и отдельный pytest для tests/test_prod_startup_guard.py. |

[Workflow](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/.github/workflows/ci.yml) прочитан по head_sha запуска. В нём нет continue-on-error для этих шагов. Корневое дерево того commit не содержит aimarket-hub, acex или plugins. Выполняемый [fetch-скрипт](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/scripts/ci_fetch_factory_test_deps.sh) получает соответствующие репозитории alexar76; [install-скрипт](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/scripts/ci_install_factory_test_deps.sh) предусматривает editable installs Hub и ACEX.

Это предметнее одного форка или ссылки в README: внешний CI использует factory tree и шаги подготовки наших компонентов. Не утверждается, что установлен сегодняшний релиз или что все 19 собственных изменений форка использовались реальными клиентами. Backend checkout в workflow называет main; точные checkout bytes из лога отдельно не восстановлены.

## Почему зелёный CI не равен полной проверке приложения

У [backend pytest runner](https://github.com/th3artfuldodger/enterprise-factory/blob/ef124a40d592bf149fab93fb632a4aaf688a04fa/scripts/run_factory_pytest_ci.py) есть особый путь: при наличии .coverage он может остановить зависший процесс и вернуть результат генерации coverage JSON. Следовательно, success шага Factory pytest suite сам по себе **не устанавливает прохождение всех assertions**. Количество passed/failed здесь не заявляется.

Запрос подробного backend-job log вернул **403**. Повторного обращения или обхода не выполнялось. Скрипты прочитаны как текст; чужой код и тесты нами не запускались.

Отдельные Factory Release Gate и Security Gate на том же push имеют failure. Причины по одним метаданным не выводятся. Нельзя переносить успех выбранного CI workflow на весь release или безопасность приложения.

Публичный deployments API вернул пустой список; поле homepage у форка ведёт на наш magic-ai-factory.com. Собственный работающий внешний endpoint этим не установлен. Пустой deployments API также не исключает ручное или частное размещение.

## Свежие ответы после прошлого среза

Проверено окно после **30 октября 07:25:26 UTC / 10:25:26 МСК**:

- MCP issue 3431, AgentDojo issue 235 и Vulnetix issue 5 не вернули новых или отредактированных комментариев в соответствующих since-запросах.
- В трёх GitHub search — mentions, входящие issues и внешние ссылки на modelmarket.dev — нет возвращённых кандидатов с updated_at после cutoff.
- PR 14 с HISTOR остаётся open, merged=false; это прежний незавершённый контакт, не новая принятая публикация.
- DEV вернул прежние 62 статьи. Счётчик одной ветки вырос с 28 до 29; сверка ID выявила только комментарий alexar76 от 30 октября 07:28 МСК. Он исключён из внешних сигналов и предшествует текущему cutoff. В остальных ветках счётчики не изменились; их содержимое повторно не читалось, изменения текста без изменения счётчиков этим способом не охвачены.

Новых подтверждённых независимых сообщений в этой проверенной выборке нет. Платёж Agent402 и другие наши тестовые покупки не включаются в спрос.

## Новые поисковые кандидаты исключены

18 поисковых web-запросов охватили свежие упоминания, фактическое использование, notebooks и национальные/социальные формулировки. Возвращённые собственные README, реестры и старые агрегаторы не добавлены как новые находки.

[Русский дайджест AI Академии](https://ai-academy.ink/post/ai-digest-2026-07-31/) действительно обсуждает warden, но его исходящая ссылка ведёт на chris-asmussen/warden. Это другой проект. Свежая [заметка Quidproquo о cedr](https://quidproquo.cc/posts/daily/2026-10-30-tool-cedr-en/) сравнивает его с DataScience-EngineeringExperts/mcp-warden; к нашему пакету она не атрибутирована. Тематическое совпадение не считается упоминанием alexar76.

[Китайская статья «Warden：给 MCP 工具调用加一道安全代理»](https://zhupite.com/sec/warden-mcp-security-proxy.html) также исключена: её исходная ссылка ведёт на AlwaysReadyAllies/warden. Название и тема совпадают, репозиторий другой.

## Свидетельства

Сохранены **24 публичных GET: 23 HTTP 200 и один 403** для лога Actions. Все 23 полученных тела сверены по SHA-256. GitHub Search API включены в эти GET и не складываются с ними как отдельные источники; 18 web-запросов учтены отдельно.

[Машинная сводка](../evidence/external-use-pass5-2026-10-30/summary.json), [общий индекс](../evidence/external-use-pass5-2026-10-30/audit-index.json), [GET-only сборщик](../evidence/external-use-pass5-2026-10-30/read_public.py) и [локальная проверка снимков](../evidence/external-use-pass5-2026-10-30/verify_evidence.py) связывают выводы с первоисточниками и сохранёнными снимками.

Выполнялись только публичные чтения и локальная запись свидетельств. Новых оплат, установок, запуска чужого кода, сообщений, GitHub/Gitea writes или изменений аккаунтов не было. Закрытые проекты и полный интернет не охвачены.

