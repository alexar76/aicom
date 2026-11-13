# WARDEN 0.26.1 — пакет для публикации

`aimarket-warden-0.26.1.tgz` — релизный кандидат на базе опубликованного 0.26.0 (`52fffde67532419fa86582c26cff91ce648a595f`). Он распознаёт системные ссылки Ubuntu на одноимённые uutils и блокирует подмену команды в `PATH` проекта. Экспериментальные изменения из текущей `main` в пакет не вошли. Статические счётчики тестов и ссылка на `tests.svg` удалены из пяти README; статус берётся из CI. Публикация в npm не выполнялась.

- `SHA256SUMS` проверяет сам архив; `pack.json` содержит npm integrity и список файлов.
- `source-commit.txt`, `warden-0.26.1-source.bundle` и `warden-0.26.1.patch` привязывают архив к локальному исходному дереву. Bundle требует указанный базовый коммит, ничего не отправляет в GitHub.
- `momus-build-digest.txt` — SHA-256 отсортированных `dist/*.js` в формате MOMUS. `Dockerfile.momus-candidate` описывает замену только пакета и соответствующего исходного дерева поверх работающего образа HISTOR.

## Проверки

- Node 22.22.1: `npm run typecheck`, `npm run build`, 1 653 теста в 72 файлах, проверка правил v19 и версий документации. Red team: 0 из 28 доставленных атак, 0 из 4 доставленных полевых регрессий.
- Чистая установка именно этого архива без сети. Импорт библиотеки, MCP `initialize` (версия 0.26.1) и `tools/list` (9 инструментов) прошли.
- Ubuntu 26.04.1 arm64, Node 22.23.4, `rust-coreutils` `0.10.0-1ubuntu2~26.04.1`, образ `ubuntu:resolute-20261105.1`, manifest `sha256:66b8084a0d45bd4877992bd38e04b51bfa99bd57293364cb6391fb674771846e`. `ubuntu-uutils-smoke.mjs` сравнивает распакованные версии 0.26.0 и 0.26.1 без сети. На двух входах Codex hook 0.26.1 разрешает системные `cat` и `ls` и запрещает локальный executable, ссылку на `/bin/sh` и ссылку на системный `cat` из начала `PATH`. Результат в `ubuntu-uutils-smoke.log`.
- Кандидат MOMUS: `sha256:9b8ad2242bcec84ae1e6bc6aa0545c5e42cc2dc913189ad4e64e72bdd11633e7`, unit `warden-release-quality-0261-final-20261112.service`. Команда MOMUS `authorize` подтвердила этот образ. Подписанный отчёт кандидата `20261112T183135` прошёл проверку подписи и дайджеста. MOMUS проверил 8 244 атаки и 362 штатных случая на основном наборе и 24 + 24 на закрытом наборе: 0 пропусков, ложных срабатываний или незавершённых случаев. Поведение: 72/72. Действителен до 14 ноября 18:06 UTC. Повторная оценка использует полный замер с тем же бинарным дайджестом; между кандидатами в архиве поменялись только README. Docker runtime config и 12 577 записей файловой системы вне двух каталогов WARDEN совпадают с базовым образом. Прод переключён на этот образ. Проверка после переключения подтвердила здоровый HISTOR, действующую подпись MOMUS и совпадение исходного коммита, образа и дайджеста с архивом.

## Как публиковать

Архив можно публиковать. MOMUS выдал отчёт `20261112T183135` в фазе `live`, а проверка из распакованного архива прошла. Текущий отчёт действителен до 14 ноября 2026, 19:06 по Амстердаму (18:06 UTC). Команда ниже повторно проверяет свежую подпись, байты архива и учётную запись npm перед публикацией. [Отчёт MOMUS](https://histor.modelmarket.dev/security-quality/latest.json)

После переключения HISTOR возобновил прерванный обход. Публичный аудит подтвердил подпись головы, включение записи MongoDB и непрерывность журнала от 2 161 546 до 2 164 746 записей. Результаты сохранены в `live-switch.log`, `live-promotion.log`, `momus-live-summary.json`, `npm-release-gate.log` и `histor-after-live-audit.log`.

Команды для запуска из каталога с этим README.

```sh
(
  set -eu
  shasum -a 256 -c SHA256SUMS
  archive="$PWD/aimarket-warden-0.26.1.tgz"
  extract=$(mktemp -d)
  trap 'rm -rf "$extract"' EXIT
  tar -xzf "$archive" -C "$extract"
  cd -P "$extract"
  node package/scripts/check-quality-gate.mjs package
  test "$(npm whoami --registry=https://registry.npmjs.org)" = alexar76
  npm publish "$archive" --access public --registry=https://registry.npmjs.org
  npm view @aimarket/warden@0.26.1 version dist.integrity --registry=https://registry.npmjs.org
)
```

## Публичное название

Главный сайт показывает `WARDEN by AIMarket — MCP tool firewall` в H1, заголовке вкладки и Open Graph. Заголовок сохраняется при смене языка. Хеш HTML на сервере и в исходниках совпал (`60a01773a1ea9197e71541be09fdc6d6f799049ba8ecfa6b3cef0b4677a8c752`). [Главный сайт](https://warden.modelmarket.dev/)

## GitHub Pages

На момент проверки `alexar76.github.io/warden` ещё отдавал старый заголовок, а `warden.modelmarket.dev` — новый `WARDEN by AIMarket`. [Сборка Pages](https://github.com/alexar76/warden/actions/runs/43261181680) на `62d8a925` упала: генератор зеркала добавил ссылку на удалённый `docs/badges/tests.svg`. В `scripts/satellite-readme-badges.yaml` запись уже убрана локально. При следующей синхронизации коллеге нужно убедиться, что экспорт README не содержит `tests.svg`, затем проверить CI и Pages. Сам npm-релиз не обновляет Pages.
