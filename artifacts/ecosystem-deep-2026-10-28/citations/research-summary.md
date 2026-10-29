# HISTOR: научная индексация и переиспользование — 28 октября 2026

Проверка: 24 целевых веб-запроса и 13 публичных GET к Zenodo, DataCite, Hugging Face, OpenAlex, Semantic Scholar, Europe PMC и GitHub. Родные API считаны 2026-10-28 13:30:29–13:30:31 UTC (16:30 MSK); запросы выполнены около этого времени. Авторизации, оплат и публикаций не было.

## Подтверждённое новое наблюдение

HISTOR индексируется в **OpenAlex** как dataset **W7223029314**:
- Карточка: https://openalex.org/W7223029314
- Проверенный API: https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760
- Title: HISTOR snapshot 2026-10-20: MCP tool definitions and how they change.
- Возвращаемый DOI: https://doi.org/10.5281/zenodo.23512759 (concept).
- indexed_in: datacite; created_date: 2026-10-21; updated_date: 2026-10-22T09:42:04.148104.
- cited_by_count: **0** на время проверки.
- Это подтверждённый дополнительный путь обнаружения датасета, а не самостоятельная научная цитата или доказательство использования.
- Точные HTTP metadata и выбранные поля: openalex-doi.json, openalex-fact.json.

## Проверка зарегистрированных связей и цитат

- DataCite version DOI 10.5281/zenodo.23512760: citationCount=0, единственная relatedIdentifier — IsVersionOf concept DOI.
- DataCite concept DOI 10.5281/zenodo.23512759: citationCount=0, единственная relatedIdentifier — HasVersion version DOI.
- Reverse query relatedIdentifiers.relatedIdentifier для version DOI: total=1, только собственная concept запись. Независимой записи со ссылкой на version DOI в этом запросе не найдено.
- Europe PMC exact DOI query: hitCount=0.
- Semantic Scholar exact version DOI: HTTP404, Paper not found. Это ограничение наличия записи в этом API, не доказательство отсутствия цитат.
- Известное цитирование/сверка Paraphern/Rugsnare на GitHub этим нулевым счётчикам не противоречит: данные научные индексы не охватывают все GitHub README. Mirror Skillget той же README не посчитан второй цитатой.

## Hugging Face и Zenodo

- HF repo alexar76/histor-mcp-tool-definitions lastModified 2026-10-26T13:52:53Z, downloads=111, likes=0.
- HF dataset search exact name вернул только собственный repo.
- HF public discussions API: одна discussion от parquet-converter BOT, 2026-10-21; человеческого обсуждения в возвращённом списке нет.
- HF metadata usedBy отсутствует/null — из этого нельзя заключать, что датасет никем не используется.
- Zenodo version record: 20 downloads / 18 unique_downloads, 64 views / 63 unique_views. Concept record API редиректит на version 23512760.
- Downloads/views отражают счётчики платформ, не независимых пользователей, анализов или цитат. DataCite own view/download counters не подставлялись вместо Zenodo.

## Agent skills PR14

https://github.com/basitalisandhu/agent-skills-state-2026/pull/14 остаётся open, merged=false, updated_at=2026-10-28T09:48:32Z. Main README SHA 020eedc0210e49d212e38fa0c784360bc100c6c9 не содержит HISTOR, DOI или alexar76. Это ещё не принятая внешняя ссылка. Никаких действий в GitHub не выполнялось.

## Границы вывода

В проверенных API и 24 целевых запросах **новых независимых papers, notebooks, datasets/code reuse со ссылкой на HISTOR не подтверждено**. Запросы включали точные version/concept DOI, HF repo, полное название снимка, servers.jsonl.gz/toolsets.jsonl.gz, notebook/Colab/Kaggle/GitLab, HAL, J-STAGE/CiNii, CNKI, arXiv, eLibrary/CyberLeninka, SciELO и ScienceON. Использованы китайские, японские, русские, корейские, португальские и испанские поисковые термины цитирования/датасетов. Это целевые запросы к одному поисковому сервису, не полный просмотр национальных баз и не обзор всего научного интернета.

Часть exact/site запросов поисковик расширял: ложные совпадения чисел DOI в объявлениях/реестрах и чужой histor.dev исключены. Свои публикации на DEV/Qiita/PyPI, автоматические каталоги/сравнения, уже известные Radyz/New Runtime/FPL Cat/billionare.me не засчитаны новыми исследовательскими цитатами. У New Runtime UA наблюдение само по себе не доказывает оператора; attribution unknown не объявляется ошибкой.

Полный перечень запросов: query-log.json. Результаты поиска сохранены отдельными JSON по батчам; метаданные публичных GET — native-index.json и отдельные записи.

