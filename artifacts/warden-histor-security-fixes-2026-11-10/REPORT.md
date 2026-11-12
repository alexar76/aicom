# Исправления Warden и Histor — 10 ноября 2026

Локально исправлены подтверждённые проблемы из [предыдущей проверки](../warden-histor-security-2026-11-10/REPORT.md). Комплект Histor и его установленный scanner переведены на опубликованный Warden **0.25.0**. Собран локальный Docker-образ `histor:local-warden-0.25.0`; внутри проверены версия 0.25.0, ruleset v19 и digest принятой MOMUS сборки.

## Исправления

- **Relay больше не передаёт ключ по редиректам.** `warden/scripts/agentdojo/relay.py` проверяет HTTPS endpoint до чтения credentials и использует urllib opener с отказом от любых редиректов. Обычные ответы и повторы временных HTTP-ошибок сохранены. Новые тесты проходят через настоящий `main` и обработчики urllib с транспортом в памяти, фиктивным ключом и без сети.
- **В двух retry helpers убрана генерация shell-команды.** `retry_set.sh` и `retry_cross.sh` запускают subprocesses массивами аргументов; фиксированный Python dispatcher получает команды как JSON-данные. Имена сканеров ограничены четырьмя поддерживаемыми вариантами. Проверяются SET, схема retry JSON, имена файлов и числовые resource/worker настройки; `workers.conf` разбирается как данные. Сохранены изоляция контейнера, порядок сканеров и исходные файлы результатов. Ненулевой статус финального сканера теперь возвращается вызывающему процессу.
- **В Histor закреплён точный npm-архив Warden 0.25.0.** Обновлены manifest, lock и `vendor/warden-build.json`; старый текущий архив 0.22.3 удалён из vendor, его историческая копия в `docs/evidence` сохранена. Локальный `node_modules`, прежде содержавший 0.20.0, переустановлен из нового lock.
- **Пересборка проверяет установленный scanner.** `scanner/check-build.mjs` сверяет локальный archive SHA256/SRI, manifest/lock, имя и версию установленного пакета, SHA256 его package.json и канонический dist digest. Проверка выполняется в обоих Docker targets и `make scanner`. Тесты отказа от старой версии, изменённого кода, изменённого exports и изменённого архива включены в `make test` и локальные YAML CI. Эти workflow-файлы никуда не отправлялись и не запускались на GitHub.
- **Исправлен устаревший observer test.** Он вызывает настоящий image manager в check mode с фиктивным Docker и проверяет его образы и подключение через install/timer вместо поиска старых inline build-команд.

## Происхождение архива и сборка

Архив получен из публичного npm registry для точной версии, без отправки source/dependency inventory. Проверены registry SHA1 и SHA512 SRI; SHA256 архива — `2a4d006f685099139db72a5cc74c0dbb370f0213fd633bb696b0a1175676062c`.

Dist digest — `6c6d85a732825d19e56646b24a679268ae6bf86516fc24cc71ccf31872404a4d`, совпадает с подписанной принятой MOMUS сборкой run `20261110T142549`. Source commit квитанции и registry gitHead сохранены раздельно. Воспроизводимость закреплённой сборки проверяется офлайн; build verifier не подменяет отдельную проверку свежести MOMUS-квитанции.

Успешно выполнены чистый offline `npm ci` в отдельной временной папке и обычная Docker-сборка target `bundled`. В одноразовом контейнере без сети и с read-only root filesystem успешно выполнены `check-build.mjs` и `scan.mjs describe`. Histor-сервис из образа не запускался.

[Проверка архива](histor/package-verification.json), [чистая установка](histor/clean-install.log), [Docker build output](histor/docker-build-output.log), [проверка внутри контейнера](histor/container-check.log), [описание scanner внутри контейнера](histor/container-describe.json), [локальный image inspect](histor/image-inspect.json).

## Проверки

- Relay: **24 passed**, включая 15 переходов 301/302/303/307/308 на другой HTTPS-host, HTTP и тот же origin. Три 302 negative-control теста воспроизводят дефект на старом исходнике. [Доказательства](relay/REPORT.md).
- Histor: **205 passed**, **9 PostgreSQL skips** без тестовой БД; устаревший observer test больше не исключается. Отдельные 130 observer tests пересекаются с этим набором и не складываются с ним. Ruff проходит. [Доказательства](histor/REPORT.md).
- Build verifier: **5 passed** в чистой установке. Независимое ревью выявило и помогло закрыть обход через изменённый package.json.exports; новый negative test его фиксирует. [Ревью](histor/build-check-review.md).
- Shell helpers: **29/29 bounded cases passed**, включая два positive controls исходного дефекта. Fake-Docker regressions воспроизводят выполнение marker-файла на обоих старых scripts и проверяют отказ исправленных versions, нормальную диспетчеризацию, ограничения ресурсов и сохранность результатов. Независимое ревью также выявило и помогло исправить раннее чтение resource overrides: queued retry теперь читает актуальные лимиты после ожидания готовности. Точный перечень — [results.json](shell/results.json), [разбор](shell/REPORT.md). Реальные исследовательские Docker jobs и удалённые hosts не запускались.
- Точечная повторная проверка Vulnetix `VNX-BASH-001` на двух исправленных helpers: exit 0, срабатываний нет. Полный исходный noisy SAST-отчёт сохранён отдельно; общий clean результат ему не приписывается. [Результат](shell/vulnetix-shell-run.json).
- Проверки синтаксиса изменённых workflow YAML и `git diff --check` проходят.

Изменения остаются локальными. Production, аккаунты и Git remotes не изменялись; публикаций, GitHub writes и деплоев не было. Существующие посторонние README/landing изменения сохранены.
