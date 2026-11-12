# Широкая экосистема: внешние ссылки, вечерний срез 10 ноября 2026

Проверка выполнена около **19:05–19:08 UTC** (20:05–20:08 Europe/Amsterdam). Основа сравнения — уже существующий утренний `../report.ru.md`, `artifacts/external-signals-2026-11-09/report.ru.md` и его ветки, дополнительный социально-региональный проход 9 ноября, затем октябрьские свидетельства. WARDEN/HISTOR как самостоятельные продукты — область другой ветки.

**Две дополнительные карточки MCPIndex подтверждены первично:** [AIMarket Hub](https://mcpindex.ai/server/io-github-alexar76-aimarket-hub) и [AIMarket MCP Gateway](https://mcpindex.ai/server/io-github-alexar76-aimarket-mcp). Обе HTTP200, обе имеют реальные HTML-ссылки на соответствующие репозитории `github.com/alexar76/aimarket-hub` и `github.com/alexar76/aimarket-mcp`. У ссылок `rel="nofollow noreferrer"`. Exact URLs не найдены в просмотренной прежней базе; домен MCPIndex встречался раньше в других контекстах. Это две дополнительные страницы одного оператора, не два новых независимых канала или новых пользователя. Дата первой публикации карточек не установлена.

## Что именно измеряет MCPIndex

Карточка показывает Hub как запись официального MCP Registry, version 3.15.21, с неприсвоенным maintainer listing. Показанный quality score относится к публичным метаданным зрелости, а не к безопасности поведения.

Прямой GET [verdict API Hub](https://mcpindex.ai/api/v1/trust/server/io-github-alexar76-aimarket-hub) вернул `status=PARTIAL`, `directive=REVIEW`, `granularity=description-level`, одну dimension `mcpindex.integrity.description=PASS`. API сам перечисляет границы: semantic only, no conformance, описание registry без input schema, небольшой screening model, отсутствие калибровки. Срок expires 17 ноября не является датой публикации карточки.

[Методология](https://mcpindex.ai/methodology), прочитанная по реальному href, подтверждает, что поведенческий conformance probe ещё не применён к публичному corpus. Поэтому карточка подтверждает внешнее индексирование и автоматическую оценку текста; она не устанавливает независимый запуск наших функций, аудит безопасности или покупателя. Методология и JSON API сохранены полностью.

## Свежесть сильных прежних связей

- **agent-exec:** [discovery](https://agent-exec.448c.org/.well-known/ai-market.json) HTTP200, 19 capability; объявленный [manifest](https://agent-exec.448c.org/ai-market/manifest) HTTP200, тоже 19. Подпись сохранённых bytes успешно проверена чистым канонизатором нашего Hub, изменение description в памяти отвергнуто. Состояние повторяет 9 ноября; нового внедрения здесь не заявляется. Это протокольная совместимость снимка под самим объявленным ключом, без вызова инструментов, оплаты и установления личности оператора. В discovery нет прямого backlink на нас.
- **Industrial Platform:** текущий [requirements](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/aimarket-sentinel/requirements.txt) всё ещё содержит git pin на `alexar76/aimarket-hub@2310569f1e4e50e1062d80725bd69ae313042a69`. Прежний [Railway discovery](https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json) вновь HTTP404. Сохраняется исходниковая зависимость; работающий endpoint по этому адресу не подтверждён. Это повторяет 9 ноября и не отменяет историческую октябрьскую совместимость.
- **[A2A Registry](https://a2aregistry.org/agents/841eea85-51d4-450c-b35a-086534dc08f6/):** HTTP200, реальные ссылки на `/a2a` и agent card, опубликованная история включает 10 ноября и version 3.17.0. Заявления Task verified и uptime относятся к измерениям издателя; они здесь не повторялись. Источник известен с октября.
- **[Hlido](https://hlido.eu/passport/alexar76-aimarket-plugins/):** паспорт и публичный scorecard доступны. Обзор датирован 5 августа, next review due 5 ноября уже прошёл. Изменение доступности файла не считается новым обзором ноября; сам scorecard не доказывает исполнение наших продуктов.

## Каталожное присутствие и неподтверждённые кандидаты

Повторно доступны страницы Odel для Hub, Plugins, Attested Memory; Glama для GAIA/weather и MCP Gateway; APIs.io для Attested Memory; Tracevero Gateway; LightNow Hub; LibHunt GAIA; авторский индекс MCPRepository; Complete AI Training Gateway. Их реальные href извлечены в `source-target-links.json`. Это подтверждение распространения метаданных, README и ссылок, а не новые человеческие обзоры, независимые интеграции или аудитории. По одному домену может быть много страниц и сотни ссылок из скопированных README.

[MCPBeat GAIA weather](https://mcpbeat.com/mcp-servers/modelmarket/weather/) — новый exact URL в просмотренной базе, но **только поисковый кандидат**: поисковая выдача описывает handshake/tools-list наблюдение, прямой GET дал403, web.open — cache miss. Текущий HTML и backlinks не подтверждены. [ProtocolProbe weather](https://protocolprobe.com/mcp/servers/dev.modelmarket/weather) уже встречался в поиске 9 ноября; текущий GET также403, web.open cache miss. Блокировки не интерпретируются как исчезновение записей, а цифры snippets не выдаются за нашу свежую телеметрию.

Прочитаны полные актуальные README и requirements `bracha55555-hue/aimarket` и `sep163/aimarket-agents`: в этих файлах нет точных ссылок на alexar76/modelmarket.dev и нашей зависимости. Они сохраняются в исключениях как одноимённые проекты, без утверждения о полной проверке каждого файла репозитория.

Запросы по Metis, Hephaestus, courses/school, протоколу и SDKs не добавили подтверждённых независимых runtime-интеграций. Собственные Pages/пакеты, зеркала Wiki и авторский IETF draft не пересчитаны как внешнее принятие; локальный интернет, приватные группы и неиндексируемые документы полностью не охвачены.

## Свидетельства и пределы

Сохранены **20 поисковых строк в пяти batch responses** и **30 публичных GET**: 25 HTTP200, два403, три404. Один404 относится к прежнему Industrial endpoint. Ещё два — к первоначально предположенным `/ai-market/v2/manifest` и `/docs/methodology`; эти пути не были обнаруженными ссылками, поэтому **не считаются битыми внешними ссылками**. Затем прочитаны именно объявленные `/ai-market/manifest` и `/methodology`, оба200. Первоначальные DNS errors внутри network sandbox были ограничением среды; финальные GET получены через разрешённый сетевой доступ.

Для всех30 тел проверены длина, полнота и SHA256. `findings.json` содержит24 классифицированных наблюдения и пределы выводов; `verification*.json` — статусы, даты, href и поля; `source-target-links.json` —315 связей, включая313 уникальных в пределах страницы HTML href и две machine references. **315 не является числом новых backlinks, операторов или аудиторий.** Значительная часть — многократные ссылки каталогов на нашу документацию.

Офлайн-проверка подписи воспроизводится командой `python3 artifacts/external-links-2026-11-10/ecosystem/verify_agent_exec.py`. Она исполняет только чистую функцию нашего канонизатора над уже сохранёнными bytes. Сторонний код не запускался; сообщений, публикаций, авторизаций, вызовов MCP tools, платежей и GitHub writes не было.
