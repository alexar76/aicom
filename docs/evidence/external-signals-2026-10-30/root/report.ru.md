# Внешние наблюдатели и научные индексы 30 октября 2026 года

Публичные источники прочитаны 30 октября около 06:53–07:01 МСК. Этот раздел дополняет параллельные проверки социальных, технических и региональных источников.

## Экономические наблюдения

[Agent Economy Report](https://agenteconomy.report/s/modelmarket.dev.json), срез **29 октября**, сохраняет **CC, improving**, три organic paying agents, 11 raw wallets, **$0,08 за 14 дней** и uptime 57,1% по своим дневным пробам. Срез 28 октября: CC, три organic, 12raw, $0,39, uptime50%. Это классификация адресов наблюдателем, не установленные люди/компании.

Дневное [углубление 30 октября](../../../growth/external-use-pass6-2026-10-30.ru.md) сопоставило два показанных AER префикса с нашим тестовым кошельком и известным плательщиком UseTested. Поэтому тройка organic не подтверждает трёх независимых прикладных клиентов. Сопоставление использует усечённые адреса; скрытый граф AER не пересчитывался.

Бесплатная [дневная история](https://agenteconomy.report/s/data/ratings-daily.csv.gz) подтверждает оба среза. Переход D→CC27–28 октября нельзя трактовать как появление новых покупателей: organic = 3 и $0,39 в обоих днях, а uptime увеличился 42,9→50%. Методика использует порог uptime50% для выхода изD. Изменения общего метода также публиковались 28 октября; причинность оценки не сводим к одному фактору.

Падение суммы на$0,31 согласуется с выходом платежей 14 октября из скользящего окна: [x402-list.com](https://x402-list.com/api/v1/services/aimarket/volume) показывает ровно$0,31 за тот день. Это сопоставление двух источников, а не транзакционная сверка каждой выплаты.

**Data: x402-list.com (CC BY 4.0).** За 29 октября UTC: пять settlements, пять адресов покупателей, округлённо$0,01. За неполное 30 октября UTC: четыре settlements и четыре адреса, сумма округлена до$0,00. Источники: [volume](https://x402-list.com/api/v1/services/aimarket/volume), [buyers](https://x402-list.com/api/v1/services/aimarket/buyers). Это измеряемые facilitators и весь payout-address оператора: не суммировать как независимые продукты, не приравнивать к успешной доставке или новым клиентам.

В прочитанной 30 октября [методике AER](https://agenteconomy.report/s/methodology) и [changelog](https://agenteconomy.report/s/changelog) присутствует запись, датированная **2 ноября 2026**, то есть будущим относительно среза. Она не использована как уже вступившее изменение. Текущие числа выше непосредственно подтверждены JSON и открытым CSV.

## A2A наблюдатели

[A2A Registry](https://a2aregistry.org/api/agents/841eea85-51d4-450c-b35a-086534dc08f6) показывает is_healthy=true, 100% reachability и успешную task-conformance пробу 30 октября **05:24 МСК**,860 мс. AgentCard3.16.0, две skills. Это внешний автоматический тест протокола, не покупка.

[Agenstry](https://agenstry.com/agents/modelmarket.dev) при прямом чтении: **78/100,B,67 успешных проб**, две skills; за отображённые 7 дней — ноль invocations, lookups и impressions. В [срезе 24 октября](../../../external-presence-2026-10-24.ru.md) уже было 78/B и 59 проб: оценка не новая. Поисковый снимок всё ещё отдаёт 60/C и сентябрьские данные, поэтому он не использован для актуальной оценки.

## Научная индексация HISTOR

[OpenAlex](https://api.openalex.org/works/https://doi.org/10.5281/zenodo.23512760): cited_by_count=0; запись создана 21 октября и связана с conceptDOI. [DataCite version](https://api.datacite.org/dois/10.5281/zenodo.23512760) и [concept](https://api.datacite.org/dois/10.5281/zenodo.23512759) также citationCount=0.

[Hugging Face](https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions):113 downloads против 111 28 октября,0 likes; единственная [дискуссия](https://huggingface.co/api/datasets/alexar76/histor-mcp-tool-definitions/discussions) создана parquet-converter BOT. +2 downloads не означают двух новых пользователей. Индексируемой научной цитаты не установлено; известное использование HISTOR проектом RugSnare этим не отменяется.

## Область

36 web-запросов сохранены в search-initial, search-broad, search-targeted и search-additional JSON. Они охватывают точные домены, DOI, уникальные исследовательские числа, IndependentAI, Karatum, Emberline, AttestedMemory и TraceofRefusal. Из результата исключены собственные Medium/DEV, каталоги, DNS-списки и совпадения названий без связи с каноническими доменами.

23 прямыхGET зарегистрированы в трёх HTTP-индексах:22 ответа 200, один 404 по предварительно предположенному пути Agenstry. Наблюдённый правильный путь /methodology прочитан успешно. Сохранены полные ответы иSHA-256. Платные API и tools/call не выполнялись.

