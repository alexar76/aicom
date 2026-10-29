# MCPMoat: прямая атрибуция и реализация — 28 октября 2026

Продолжение уже найденного обзора `docs/competitors.md`. Нового внешнего проекта или внедрения WARDEN в этой части не подтверждено. Уточнён ещё один прямой документальный след: [PRD, строка1004](https://github.com/Ducarv/mcpmoat/blob/fc776bc2eb10376994b6d021a18f6230487bc033/docs/PRD.md#L1004) включает `alexar76/warden` в риск сильных конкурентов и требует изучить их перед M4. Это дополнительный документ того же проекта, а не независимая вторая рекомендация.

Все файлы привязаны к основному `dev` commit `fc776bc2eb10376994b6d021a18f6230487bc033`; повторный branch GET подтвердил прежний SHA. Чужой код не выполнялся, пакеты не устанавливались.

## Что реализовано относительно пяти кредитованных идей

| Идея из обзора | Что подтверждено чтением текущего кода/документации | Граница вывода |
| --- | --- | --- |
| Версия и digest набора правил в отчёте | В проверенной структуре `ScanReport`/`JSONFinding` и `internal/rules/set.go` такой метадаты не выявлено. `SchemaVersion=4` — версия формата отчёта; `JSONAccept.Digest` относится к pin. | Версия схемы и pin digest не доказывают реализацию ruleset digest. Не заявляется поиск по каждой строке всех556файлов. |
| Подробный pin diff | [render.go45–78](https://github.com/Ducarv/mcpmoat/blob/fc776bc2eb10376994b6d021a18f6230487bc033/internal/pins/render.go#L45) превращает canonical tool в текст с префиксами полей; `internal/pins/diff.go` и `internal/report/diff.go` формируют/выводят unified line diff. | Реальный код есть. Это сравнение строк по полям, а не подтверждённый word diff WARDEN. |
| Severity отдельно от блокировки, advisory не блокирует | [Exit codes12–20](https://github.com/Ducarv/mcpmoat/blob/fc776bc2eb10376994b6d021a18f6230487bc033/docs/exit-codes.md#L12) задаёт `--fail-on`; LLM findings считаются как другие, максимум high. `internal/report/findings.go106–108` называет LLM source advisory, поскольку оценку создала модель. | Advisory label здесь **не гарантирует** неблокирующее поведение. Нельзя считать полностью перенятым принцип never-blocking advisory. |
| Явные ограничения | [docs/limits.md](https://github.com/Ducarv/mcpmoat/blob/fc776bc2eb10376994b6d021a18f6230487bc033/docs/limits.md) существует в закреплённой ветке,234строки; ограничения также связаны из кода renderer. | Документ опубликован; причинная связь с WARDEN отдельно не доказана. |
| Методика с held-out test set | В выбранной документации и дереве не установлена отдельная опубликованная методика такого измерения. Есть acceptance fixtures и unit/integration tests. | Наличие тестов не заменяет доказательство held-out benchmark. |

Критическая хронология: [issue60](https://github.com/Ducarv/mcpmoat/issues/60) и epic5 уже **17 октября** требовали unified diff description/schema. Обзор датирован23октября; issue60 закрыт25октября, epic5 —26октября. Поэтому наличие diff после обзора не доказывает, что идея впервые появилась из WARDEN. В изученных исходниках прямого credit WARDEN не найдено. Известное credit в сравнении остаётся реальным, но пять предложений не означают пять внедрённых заимствований.

## Область чтения

- Четыре web-запроса по цепочке MCPMoat/WARDEN/credit; полные ответы в `web-chain.json`. Small Print и автоматические каталоги оказались уже известными, повторно не проверялись.
- 22 отдельных публичных GET, все HTTP200: branch, immutable tree, три страницы issue/PR,13закреплённых файлов и4дополнительных файла реализации.
- Дерево содержит556blobpaths. Это инвентарь, не чтение всех исходников.
- Три страницы дают260уникальных issue/PR. Проверены заголовки и body: точные WARDEN/alexar76 refs обнаружены только в уже известных32/111. Комментарии всех260веток не читались.
- GitHub search API, авторизации, сообщений, заявок и GitHub writes не было. На последних API чтениях core remaining был8; raw-file GET не использует этот bucket.

Evidence: `discovery.json`, `older-issues.json`, `pinned-files.json`, `implementation.json`. Метаданные времени/статуса/SHA-256 — `verification-index.json`. Факты реализации — статическое чтение; тесты MCPMoat нами не запускались.
