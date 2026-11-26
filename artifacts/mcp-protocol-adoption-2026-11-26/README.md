# Какую версию протокола MCP отвечают серверы реестра — замер 26 ноября 2026

Данные и скрипты к статье «Which MCP servers speak 2026-07-28? 59% of PyPI packages, 28% of remotes, 6% of npm»
(блог: `modelmarket-blog/posts/which-mcp-servers-speak-2026-07-28-59-of-pypi-packages-28-of-remotes-6-of-npm/`; там же лежат опубликованные файлы данных
`remote_protocols.csv`, `dependency_sample.json`, `results-2026-11-26.json`).

## Что посчитано

- **Удалённые серверы.** Одна строка на сервер с успешным чтением между 2026-11-02T09:00Z и 2026-11-26T16:00Z:
  `remote_protocols.sql` (один запрос только на чтение к базе HISTOR, 1 мин 47 с, 25 931 строка). «Текущая» версия —
  последнее успешное чтение за 19–26 ноября: 25 023 сервера, из них 7 059 (28,21 %) отвечают 2026-07-28.
  Контрольный запрос другой формы (DISTINCT ON по тому же окну) дал те же семь чисел.
- **Пакеты npm и PyPI.** Открытый снимок HISTOR от 2026-11-23, `package_observations.jsonl.gz`, запуски наблюдателя 5
  (первым идёт `server/discover`) с 2026-11-15T19:57Z по 2026-11-23T07:18Z: 26 276 записей;
  PyPI 3 694 из 6 236 (59,24 %), npm 1 267 из 20 040 (6,32 %).
- **Причина разрыва.** `sample_dependencies.py`: по 300 случайных пакетов из каждого реестра (seed 20261126), строка
  зависимости читается из метаданных реестра для той версии, что запускалась; ничего не устанавливается.
- **Домены.** `psl.py` — регистрируемый домен по Public Suffix List (копия от 26.11.2026 не хранится в репозитории).

## Как повторить

```sh
python3 -B count_protocols.py ../../modelmarket-blog/posts/which-mcp-servers-speak-2026-07-28-59-of-pypi-packages-28-of-remotes-6-of-npm/remote_protocols.csv \
  package_observations.jsonl.gz servers.jsonl.gz public_suffix_list.dat > results.json
python3 make_figures.py results.json ../../modelmarket-blog/posts/which-mcp-servers-speak-2026-07-28-59-of-pypi-packages-28-of-remotes-6-of-npm/dependency_sample.json figures
```

`package_observations.jsonl.gz` и `servers.jsonl.gz` — из https://histor.modelmarket.dev/datasets/2026-11-23/,
`public_suffix_list.dat` — с https://publicsuffix.org/list/public_suffix_list.dat.

## Что проверено по первичным источникам (26.11.2026)

- Спецификация 2026-07-28, changelog: рукопожатие `initialize` убрано, `server/discover` обязателен для серверов.
- PyPI `mcp`: 2.0.0 загружен 2026-07-28; в 2.x `mcp_types/version.py` перечисляет 2026-07-28; 1.30.0 — только до 2025-11-25.
- FastMCP: 4.0.0 (2026-08-31) требует `mcp>=2.0.0,<3`; 2.14.5 и 3.4.11 требуют `mcp<2.0`.
- npm `@modelcontextprotocol/sdk` 1.32.2 (2026-10-23): в `dist/esm/types.js` и `dist/esm/server/index.js` нет строк
  `2026-07-28` и `server/discover`; `@modelcontextprotocol/core` 2.4.0 их содержит; `@modelcontextprotocol/server` 2.0.0 вышел 2026-07-27.
- Отчёт Censys (апрель 2026): 12 520 сервисов, 89,4 % на 2025-03-26 — прочитан в браузере.

## Сравнение с нашим счётом от 1 ноября

`artifacts/mcp-protocol-eras-2026-11-01/` (опубликован 2 ноября в статье про 2 195 непрочитанных серверов): 4 097 из
21 474 (19,08 %). Издатель с 1 882 записями тогда целиком отвечал 2025-06-18, 12 ноября перешёл (1 848 записей за день).
Без него: 4 097 из 19 592 (20,91 %) → 5 212 из 23 176 (22,49 %). По регистрируемым доменам: 3 121 из 12 911 (24,17 %) →
4 248 из 15 750 (26,97 %). Первая версия статьи (16:37–16:55Z 26.11) говорила, что таких замеров никто не публиковал;
это было неверно — исправлено в блоге и на DEV.to в тот же час.

## Ограничения

Те же, что в последнем разделе статьи. Дополнительно: переходы «обратно» (109 серверов) могут быть следствием
сбоя пробы у сервера, отвечающего в обоих режимах; список `supportedVersions` HISTOR не хранит.
