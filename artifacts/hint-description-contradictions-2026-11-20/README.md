# Подсказка поведения против описания того же инструмента: калибровка проверки WARDEN

20.11.2026. Повод: комментарий Joshua Bryan (IsoKron) под статьёй про readOnlyHint (DEV 5075663, 3lnhb): отпечаток и
lock хранят неверную подсказку так же стабильно, как верную. Пример из его аудитов, сверенный с исходником
`github/github-mcp-server` (main, 20.11): у `update_issue_labels` стоит `destructiveHint: false`, а описание говорит
«This replaces the current labels with the provided list».

Проверка: `warden/src/hint-claims.ts` (`hintContradictions`), находка `TOOL_HINT_CONTRADICTS_DESCRIPTION` в `scan`,
только информационная.

## Данные

Срез HISTOR 2026-11-16 (`https://histor.modelmarket.dev/datasets/2026-11-16/`, CC-BY-4.0). SHA-256 сверены с
`manifest.json`:

| Файл | SHA-256 |
|---|---|
| `servers.jsonl.gz` | `ab428f72a7b6be1922f5962d2fad2fc0c4251f17b0d54a71c547c3e71a59f924` |
| `tool_extras.jsonl.gz` | `b2cbb9f7ddec0f02ff769e61a544ca773001f95136dc3042956757b7cae4b45f` |
| `toolsets.jsonl.gz` (3,5 ГБ, читался потоком) | `a280040f23bea359b53dce3f50a1df90ef18a5542f7d95491bdfdfed85326ce3` |

Совокупность: серверы из каталога (не снятые), у которых записан текущий набор инструментов и текущая запись extras;
из них — инструменты, чьи аннотации явно говорят `readOnlyHint: true` или `destructiveHint: false`
(`extract.py`). Это определения, какими их отдали серверы краулеру HISTOR; WARDEN на самих серверах не запускался.

## Как калибровалось

Три прохода по частичному корпусу (18 тыс., 55 тыс., 135 тыс. инструментов) и два по полному, каждый раз с ручным
чтением случайных выборок совпадений. Что убрано после чтения:

- повелительное наклонение после первого предложения — почти всегда инструкция вызывающему («Edit one first with
  update_reply_draft», «Send the file as base64», «Remove names before pasting»);
- глаголы, которые чаще оказывались запросом, фильтром, классификацией или предлогом: execute, submit, run, follow,
  like/unlike, order, block, sign, star, subscribe, assign, reopen, ведущее «replace», а под readOnlyHint ещё drop и
  truncate («Drops a job only when…», «Truncate documents to N tokens»);
- create/update/upload/remove под readOnlyHint считаются только с объектом-ресурсом в следующих шести словах
  («Create text embeddings», «Removes duplicate lines», «Update a prior probability» — не записи);
- предложения о том, чего инструмент не делает или только показывает (preview, dry run, without touching, does not);
- «replaces the whole …» в предложении, где раньше назван другой инструмент («update_modifier REPLACES the whole
  choice list» в описании инструмента чтения);
- под readOnlyHint — «remove», «mint», «cannot be undone» и «replaces the whole …» совсем: в выборке они чаще
  описывали правку входа («Remove EXIF from a photo»), ссылку на скачивание или другой инструмент;
- форма третьего лица («Posts», «Bans», «Wipes», «Sets») — только с артиклем или вещью сразу после: иначе это
  существительное во множественном числе («Posts with applicant counts», «Bans grouped by reason»);
- create под readOnlyHint — не считается, если создаёт ссылку, URL или документ из переданных данных.

Тесты: `warden/test/hint-claims.test.ts`, `warden/test/scan.test.ts`.

## Результат

Полный проход: 36 170 текущих наборов инструментов прочитаны; в корпусе 468 359 инструментов на 26 808 серверах
с явной подсказкой (377 217 с `readOnlyHint: true`, 91 142 с `destructiveHint: false` без readOnlyHint true).
`node count.mjs warden/dist <corpus.jsonl> results-2026-11-16.json` (WARDEN этого коммита):

| Заявление | Инструментов с противоречием | Серверов | Хостов / пакетов | Доля от заявивших |
|---|---|---|---|---|
| `readOnlyHint: true` | 307 | 204 | 188 | 0,08 % |
| `destructiveHint: false` | 960 | 593 | 569 | 1,05 % |

Чаще всего: под readOnlyHint — create (43), writes (27), creates (19), send (15), purchase (14); под
destructiveHint false — remove (313), delete (92), «replaces the whole …» (65), «cannot be undone» (51).
Удалённых серверов и пакетов: 165 / 142 (readOnly), 306 / 654 (destructiveHint).

**Точность** (после последней правки правил, новая выборка, seed 123, 50 различных совпадений на заявление, разметка
вручную в `review-sample-seed123.json`): readOnlyHint — 40 из 50 действительно говорят, что инструмент что-то меняет;
destructiveHint false — 45 из 50 действительно говорят об удалении или перезаписи. Пять «нет» во втором случае:
три — необратимое, но добавляющее действие (публикация, получение значка), одно — про необратимость другого действия,
одно — «Drops» в смысле «кладёт». Ошибки первого случая: генераторы, которые возвращают текст файла, названия
инструментов («Cancel My Sub») и существительные. Оценка по 50 строкам грубая: ±10–14 п.п.

Чего этот счёт не говорит: что сервер действительно делает (WARDEN читает определение, не вызывает инструмент); сколько
противоречий пропущено (полнота не мерилась: размечены только совпадения); описания не на английском не читаются.
Пример из комментария (`update_issue_labels` GitHub) в срезе не встретился; вероятная причина (не проверялась):
инструмент включается флагом `issues_granular`.

Файлы: `results-2026-11-16.json` — все совпадения; `review-sample-seed123.json` — размеченная выборка.
