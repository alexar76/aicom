# Внешние сигналы alexar76 — повторный срез 25 ноября 2026

После утреннего аудита подтверждены успешный запуск HISTOR в mcpcost, новое техническое выступление Canari в MCP Registry и всплеск загрузок eSIM Rails. Сверка трёх транзакций из 402radar с Base выявила два собственных перевода и один перевод с неатрибутированного адреса. [Утренний срез](report.ru.md) · [ответы MCPBeat и Internet Archive](outreach-followup.ru.md)

## Что изменилось у внешних наблюдателей

- **mcpcost подтвердил запуск HISTOR 0.11.0.** В срезе 24 ноября ещё было записано `needs_args` для 0.10.0. Актуальный JSON внешнего измерителя показывает успешный запуск `aimarket-histor==0.11.0` 24 ноября в 11:39 UTC и три инструмента. Зафиксировано 1 179 мс на `initialize` и 2 мс на `tools/list`. Отдельный замер этого источника 24 ноября дал 633 токена по Anthropic `count_tokens` и оценку 368 по o200k. Это два счётчика с разными методиками. Актуальная версия официальной записи — 0.11.0. [Снимок mcpcost](https://mcpcost.ulehla.dev/api/s/io.github.alexar76/histor.json) · [MCP Registry](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.alexar76%2Fhistor/versions/latest) · [предыдущая фиксация](../external-mentions-2026-11-24/evidence.json)
- **Canari продолжает работу в MCP Registry.** 25 ноября автор Canari принёс собственные результаты в PR #1404 и предложил явно описывать подпись и ключ в данных аттестации. Это продолжение работы уже известного контрибьютора WARDEN. Комментарий касается формата квитанции в #1404. Публикация Canari на PyPI оставалась 0.1.7. [Комментарий Canari](https://github.com/modelcontextprotocol/registry/pull/1404#issuecomment-7158078408) · [PyPI](https://pypi.org/project/canari-mcp/)
- **Сверка дайджестов продолжается на двух известных площадках.** В публичном индексе внешнего журнала yassinht за 25 ноября 50 550 записей, из них 29 764 с дайджестом. В срезе 23 ноября было 48 961 и 28 701. Индекс по-прежнему даёт адрес перезаписываемой выгрузки. Наш предыдущий встречный прогон охватил 48 серверов, поэтому счётчик индекса нельзя читать как объём сопоставления с HISTOR. DeclaredList 24 ноября заново проверил одну опубликованную запись `com.rtlpdf/arabic-pdf` 1.0.1 и сохранил статус `verified`. Это та же интеграция bcrypto0, а заявка на включение в список community projects остаётся открытой. [Индекс yassinht](https://yassinht.github.io/mcp-transparency-log/data/peers/index.json) · [наш прогон 23 ноября](../histor-peer-cross-check-2026-11-23/results.md) · [DeclaredList](https://declaredlist.com/) · [PR #1907](https://github.com/modelcontextprotocol/registry/pull/1907)

## Распространение пакетов

Суммы суточных счётчиков npm за два семидневных окна 2026 года. Реестр считает события загрузки, включая повторные и автоматические.

| Пакет | 10–16 ноября | 17–23 ноября | Что видно |
|---|---:|---:|---|
| [`@aimarket/esim-rails`](https://api.npmjs.org/downloads/range/2026-11-10:2026-11-23/@aimarket%2Fesim-rails) | 39 | 2 815 | Из них 1 026 за 22 ноября и 1 403 за 23 ноября, вместе 86%. Версия 0.5.1 опубликована 18 ноября. Источник всплеска по открытым данным установить не удалось. |
| [`@aimarket/warden`](https://api.npmjs.org/downloads/range/2026-11-10:2026-11-23/@aimarket%2Fwarden) | 1 436 | 3 121 | Рост в сопоставимых окнах, с несколькими заметными днями. |
| [`@alexar76/argus3`](https://api.npmjs.org/downloads/range/2026-11-10:2026-11-23/@alexar76%2Fargus3) | 564 | 917 | Значение второго окна совпало с утренним срезом. |
| [`mcp-token-cost`](https://api.npmjs.org/downloads/range/2026-11-10:2026-11-23/mcp-token-cost) | 0 | 370 | Версия 0.1.0 вышла 21 ноября. 312 событий пришлись на день релиза. |

Hugging Face вернул счётчик **413** у набора данных HISTOR против **409** в срезе 23 ноября. [API Hugging Face](https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions) · [срез 23 ноября](../external-mentions-2026-11-23/evidence.json)

## Платёжный маршрут и атрибуция

В свежем скане Agent402 от 12:09:41 UTC все восемь платных маршрутов ModelMarket всё ещё помечены доступными через `unproven` на Base с причиной `settlement_required`. Kertivo получил ожидаемый HTTP 402 по шести выбранным маршрутам. Market402 показывает восемь эндпоинтов в мониторинге и ноль маршрутов со статусом `verified`. Эти наблюдатели измеряют доступность и допуск к маршрутизации по собственным правилам. [Agent402](https://agent402.tools/api/index?seller=modelmarket.dev) · [Kertivo](https://kertivo.com/status.json?host=modelmarket.dev) · [Market402](https://market402.com/op/modelmarket.dev)

Для трёх верхних строк из раздела транзакций 402radar прочитаны успешные квитанции Base и события перевода USDC на адрес ModelMarket. Два перевода по **0,003 USDC** пришли с кошелька, который журнал AIMarket ранее описывает как собственный и пополненный оператором. У третьего перевода на **0,03 USDC** отправитель другой. Кто контролирует адрес и состоялась ли доставка по платному вызову, по квитанции перевода установить нельзя. Проверены ровно три строки, поэтому этот результат не пересчитывает полный 14-дневный объём Agent Economy Report. [402radar](https://402radar.io/modelmarket.dev) · [перевод 0,003](https://basescan.org/tx/0xffb022b15e4e8be66a11683f6e303f799c080a27a0c979c83bc445d19a3c1177) · [перевод 0,003](https://basescan.org/tx/0xbeaa0884fae1a6395fd3475c0f24d08b220e4c8986cdb7f6407a4007cdd64572) · [перевод 0,03](https://basescan.org/tx/0xb8e05ba2dd857759d905408490d3e86022e096ebd0eee02d39023f895daeba2a) · [журнал AIMarket](../../docs/onchain-journal.md)

## Границы среза

Прямые ответы собраны между 14:24 и 14:28 по Амстердаму. Проверка входящих GitHub issues и PR в репозиториях аккаунта, обновлённых 25 ноября, вернула ноль по запросу со сторонними авторами. Выборочные внешние запросы в GitHub, HN, DEV.to и веб-поиске не дали нового подтверждённого внедрения Factory, Attested Memory или PingBlip. Обзор Attested Memory в Atlas по-прежнему ссылается на старую ревизию. Статусы выбранных инициатив OWASP, MCP Transports WG и PR о включении HISTOR в awesome-list не изменились. Часть запросов DEV.to вернула 429, а нативные поиски Reddit и Bluesky — 403. [Машинные свидетельства](later-scan.evidence.json)
