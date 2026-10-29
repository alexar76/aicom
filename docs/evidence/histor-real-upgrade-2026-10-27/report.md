# MCP экосистемы alexar76 — реальные наблюдения HISTOR

Разбор сохранённых определений и перепроверок ваших рабочих сценариев.

| Зависимость | Результат | Сценарии для проверки |
|---|---|---|
| https://modelmarket\.dev/mcp | Определения различаются; сопоставимость неизвестна | 2 |
| npm:@aimarket/warden | Определения различаются; сопоставимость неизвестна | 2 |
| pypi:aimarket\-mcp\-packager | Недостаточно данных | 1 |
| pypi:aimarket\-oracle\-gateway | Недостаточно данных | 1 |

## https://modelmarket\.dev/mcp

**Определения различаются; сопоставимость неизвестна**

- До: 2026\-10\-07T08:51:11Z; версия пакета не применяется; версия сервера 1\.2\.0; протокол неизвестен.
- После: 2026\-10\-27T02:27:17Z; версия пакета не применяется; версия сервера 1\.2\.0; протокол неизвестен.
Покрытие полей: только name, description, inputSchema и outputSchema. Полнота дополнительных полей неизвестна.

- Ограничение: Исторические annotations и другие дополнительные поля неизвестны\. Сравнены только core\-поля; изменения extras не определялись\.
- Ограничение: Протокол одного из наблюдений неизвестен\.
- Ограничение: Условия запуска одного из наблюдений неизвестны\.

### Выбрать подходящую capability по поиску Hub и сохранить relevance и note

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] market\_search: Прочитать изменённые инструкции; повторить обычный запрос и проверить выбор инструмента\.
- [ ] market\_search: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.

### Передать точные product\_id, capability\_id и source\_hub из поиска в вызов

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] market\_invoke: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.
- [ ] market\_search: Прочитать изменённые инструкции; повторить обычный запрос и проверить выбор инструмента\.
- [ ] market\_search: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.

### Изменения выбранных инструментов

**market\_invoke: Недостаточно данных**


**market\_search: Изменён**

- Описание удалено: “and”
- Описание добавлено: “\`input\`”
- Описание удалено: “\`input\`: the”
- Описание добавлено: “\(the”
- Описание удалено: “takes\.”
- Описание добавлено: “takes\) and \`relevance\` from 0 to 1; a \`note\` says when nothing matched well\.”

Размер model-facing JSON в UTF-8: весь список 12165 → 12231 байт; выбранные инструменты 2818 → 2884 байт.
Это не токены и не фактическая экономия.

## npm:@aimarket/warden

**Определения различаются; сопоставимость неизвестна**

- До: 2026\-10\-21T10:54:02Z; версия пакета неизвестна; версия сервера 0\.18\.0; протокол неизвестен.
- После: 2026\-10\-26T20:59:44Z; версия пакета 0\.22\.1; версия сервера 0\.22\.1; протокол неизвестен.
Покрытие полей: только name, description, inputSchema и outputSchema. Полнота дополнительных полей неизвестна.

- Ограничение: Исторические annotations и другие дополнительные поля неизвестны\. Сравнены только core\-поля; изменения extras не определялись\.
- Ограничение: Протокол одного из наблюдений неизвестен\.
- Ограничение: Условия запуска одного из наблюдений неизвестны\.
- Нет метаданных: before: packageVersion missing; not inferred

### Показать оператору server\_info и блок origin перед пересмотром approval

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] status\_mcp\_server: Проверить сохранённые входы, обязательные поля и типы; добавить граничный пример\.
- [ ] status\_mcp\_server: Повторить обработку результата: проверить поля и типы, которые читает сценарий\.
- [ ] status\_mcp\_server: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.

### Сохранить reviewed hashes и previousRevision при передаче review в approval

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] approve\_mcp\_server: Проверить сохранённые входы, обязательные поля и типы; добавить граничный пример\.
- [ ] approve\_mcp\_server: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.
- [ ] status\_mcp\_server: Проверить сохранённые входы, обязательные поля и типы; добавить граничный пример\.
- [ ] status\_mcp\_server: Повторить обработку результата: проверить поля и типы, которые читает сценарий\.
- [ ] status\_mcp\_server: Получить связанные с обоими наблюдениями annotations и другие extras; текущие метаданные не заменяют исторические\.

### Изменения выбранных инструментов

**approve\_mcp\_server: Изменён**

- Новые обязательные поля: —
- Изменения type: $/properties/server\_info, $/properties/server\_info/properties/name, $/properties/server\_info/properties/version
- inputSchema: $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;additionalProperties&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;name&quot;\.&quot;maxLength&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;name&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;version&quot;\.&quot;maxLength&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;version&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;type&quot;

**status\_mcp\_server: Изменён**

- Новые обязательные поля: —
- Изменения type: $/properties/server\_info, $/properties/server\_info/properties/name, $/properties/server\_info/properties/version
- inputSchema: $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;additionalProperties&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;name&quot;\.&quot;maxLength&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;name&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;version&quot;\.&quot;maxLength&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;properties&quot;\.&quot;version&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;server\_info&quot;\.&quot;type&quot;
- outputSchema: $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;approvedVersion&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;approvedVersion&quot;\.&quot;type&quot;\[0\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;approvedVersion&quot;\.&quot;type&quot;\[1\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;currentVersion&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;currentVersion&quot;\.&quot;type&quot;\[0\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;currentVersion&quot;\.&quot;type&quot;\[1\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;launch&quot;\.&quot;anyOf&quot;\[0\]\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;launch&quot;\.&quot;anyOf&quot;\[1\]\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;properties&quot;\.&quot;launch&quot;\.&quot;description&quot;, $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;required&quot;\[0\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;required&quot;\[1\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;required&quot;\[2\], $\.&quot;properties&quot;\.&quot;origin&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;reviewText&quot;\.&quot;description&quot;

Размер model-facing JSON в UTF-8: весь список 28371 → 29231 байт; выбранные инструменты 9307 → 10167 байт.
Это не токены и не фактическая экономия.

## pypi:aimarket\-mcp\-packager

**Недостаточно данных**

- До: 2026\-10\-17T14:27:29Z; версия пакета 2\.1\.1; версия сервера неизвестна; протокол неизвестен.
- После: дата неизвестна; версия пакета неизвестна; версия сервера неизвестна; протокол неизвестен.
Успешной пары определений нет. Поля инструментов не сравнивались.

- Ограничение: После обновления нет полного успешного наблюдения\.

### Получить manifest и интерактивную Docker connection string из capability specification

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] package\_capability: Получить оба полных успешных наблюдения в сопоставимом окружении\.

### Изменения выбранных инструментов

**package\_capability: Недостаточно данных**


## pypi:aimarket\-oracle\-gateway

**Недостаточно данных**

- До: дата неизвестна; версия пакета неизвестна; версия сервера неизвестна; протокол неизвестен.
- После: 2026\-10\-19T13:37:41Z; версия пакета неизвестна; версия сервера неизвестна; протокол неизвестен.
Успешной пары определений нет. Поля инструментов не сравнивались.

- Ограничение: До обновления нет полного успешного наблюдения\.
- Ограничение: После обновления нет полного успешного наблюдения\.

### Получить каталог oracle capabilities через Metis перед выбором платного оракула

Нужны сопоставимые наблюдения.

- [ ] Сверить protocol, launcher и условия доступа; повторить оба снимка в одном контексте\.
- [ ] list\_oracle\_capabilities: Получить оба полных успешных наблюдения в сопоставимом окружении\.

### Изменения выбранных инструментов

**list\_oracle\_capabilities: Недостаточно данных**


## Границы разбора

- Сравниваются наблюдавшиеся определения, не фактическое поведение сервера.
- Изменение не доказывает поломку; отсутствие изменений не подтверждает безопасность.
- Рабочие сценарии связаны по явно выбранным инструментам, без семантического анализа.
- Размер компактного JSON в UTF-8 — байты, не токены, деньги или фактическая экономия.
- launch отображается только хешем; условия не исполняются и секреты окружения не выводятся.

[Полные данные, версии и SHA-256 входных файлов](report.json).
