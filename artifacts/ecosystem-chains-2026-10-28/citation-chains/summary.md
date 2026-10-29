# Цепочки внешних ссылок — 28 октября 2026

Проверка около 16:48–16:53 МСК. 24 различных веб-запроса и 15 публичных GET (14 различных URL, все HTTP200). Полные поисковые ответы — шесть JSON по батчам; перечень — `query-log.json`. Прямые чтения — `http-index-all.json`, дата и SHA-256 каждого ответа сохранены. Входов в аккаунты, сообщений, GitHub writes и публикаций не было.

## Результат

**Новых независимых цитирующих публикаций, обзоров или внедрений через проверенные цепочки не подтверждено.** Это вывод данного ограниченного прохода, не отсутствие ссылок во всём интернете. Проверялись точные URL/title fragments Hubwiz/Radyz/Hlido, сочетания RugSnare с HISTOR/alexar76 и китайские/чешские формулировки.

- Известная [Hubwiz](https://www.hubwiz.com/blog/agent-security-nine-incidents-six-controls/) по-прежнему прямо атрибутирует HISTOR и alexar76, подробно пересказывает запуск 12,915 пакетов, и оговаривает, что это данные авторов, а не endorsement. Страница публично показывает 16 октября по своей локальной дате; прежняя датировка 15 октября в отчётах могла относиться к UTC metadata. Новым материалом этот источник не считается.
- Известная [Radyz](https://radyz.cz/rychle-zpravy/histor-otevrel-dataset-zmen-nastroju-mcp-nikoli-seznam-skodlivych-serveru/) доступна, 22 октября. Share-buttons являются возможностью поделиться, не доказательством реально опубликованных постов.
- Известная [Hlido review](https://hlido.eu/reviews/alexar76-aimarket-plugins/) всё ещё tested2026-08-05/re-test2026-11-05, score60/FADING. Новую рецензию не нашли.
- [RugSnare homepage](https://rugsnare.com/) самостоятельный сайт стороннего проекта; в полученной странице точных наших alexar76/modelmarket.dev нет. Поиск HISTOR без границы слова цеплял **History**, что не является упоминанием. Известная ссылка на датасет находится в README; homepage existence не считается новым применением HISTOR.

## Проверенные ложные тематические кандидаты Hubwiz

Известная статья Hubwiz содержит ссылки на другие материалы, тематически похожие на наши исследования. **Проверка первоисточников показала других авторов**, поэтому эти страницы исключены из наших упоминаний:

| Наблюдённая связанная страница | Реальный источник/предмет |
| --- | --- |
| [MCP tool count,1932 runs](https://www.hubwiz.com/blog/mcp-tool-count-1932-runs-measured/) | @yahhi (Moein), worklore/worklore-mcp. Не alexar76. |
| [x402 guardrails,25µs](https://www.hubwiz.com/blog/agent-payment-security-x402-guardrails/) | @dailycontext. Не alexar76. |
| [delivery verification gates](https://www.hubwiz.com/blog/agent-delivery-verification-gates/) | @dannwaneri/claimcheck и другие источники. Не AICOM. |
| [restart/replay/idempotency](https://www.hubwiz.com/blog/agent-restart-replay-idempotency-retro/) | @anis_meziani и ApowerB. |
| [audit logs witness/suspect](https://www.hubwiz.com/blog/agent-audit-logs-witness-suspect/) | @james_anderson_h, @slabb/noirebox и другие авторы. |
| [Bash deny-rule bypass](https://www.hubwiz.com/blog/claude-code-bash-deny-rule-bypass/) | @gabrielanhaia, Claude Code shell variable bypass; не наш period-bypass/FlowGuard. |
| [MCP registry supply-chain audit](https://www.hubwiz.com/blog/mcp-registry-supply-chain-audit/) | Статический скан15,341 @dmitrii_p, pezhik/skilltotal; не HISTOR runtime study12,915. |
| [source-aware verification](https://www.hubwiz.com/blog/source-aware-verification-for-mcp-agents/) | MultiverseComputingCAI/ProvenanceGuard, не Metis. |

В теле и выбранных metadata этих восьми страниц нет точных alexar76/modelmarket.dev/HISTOR/WARDEN/AICOM. Наличие на части страниц ссылки обратно на известный обзор безопасности не превращает их содержание в новый обзор нашей экосистемы. [Китайский AI-перевод feinterview](https://feinterview.poetries.top/ai-monitor/news/how-many-tools-should-an-mcp-server-have-i-measured-5-to-100-in-claude-code-codex-and) также прямо ведёт к @yahhi, исключён.

## Дополнительная карточка известного каталога

[MCP Index: alexar76/aimarket-plugins](https://mcp.zalize.com/s/alexar76-aimarket-plugins) содержит точный репозиторий и modelmarket.dev, HTTP200. MCP Index уже известен по карточкам Gateway/WARDEN от 26 октября. Это дополнительная карточка того же каталога, не новый независимый обзор.

53/100 на странице — открыто описанный heuristic: GitHub stars3/40, activity25/25, license10/10, official0/10, not-archived5/5, description5/5, topics5/5. Это техническая формула метаданных, не 53 пользователя и не оценка по результатам запуска. Каталог прямо говорит, что score не endorsement. Пример uvx-конфига помечен как шаблон с просьбой сверить имя пакета с README; работоспособность в этом проходе не проверялась. Репозиторий каталога, указанный на странице, wookat/mcp-index; сторонний исходный код не выполнялся.
