# ACEX: закрытие пробела в идентификаторах, 10 ноября 2026

**Пробел прежней матрицы закрыт: ACEX теперь проверен по реальным Python namespaces, контрактам, HTTP routes и настройкам, а не только по Solana crate. Нового подтверждённого чужого импорта, вызова или config не найдено.** Это результат ограниченного поиска; отсутствие всех внешних deployments не утверждается.

## Какие fingerprints добавлены

Из27 локальных исходников/документов/configs извлечены пути, строки и SHA256. Секретные файлы и значения окружения не читались. Полный набор — `fingerprints.json`.

- Python: `acex.integrations.pricing`, `acex.integrations.ai_audit`, `acex.integrations.jupiter`; функции `build_pricing_snapshot`, `build_pack`, `score_evidence`, `fetch_jupiter_quote`, `build_swap_plan`.
- Реальные собственные consumers: Hub `capital_pricing.py:37` и `acex_ai_audit.py:23`, Factory `web/backend/api/acex_capital.py:29`. Это внутренние импорты, не внешние внедрения. В корне ACEX нет отдельного Python package manifest; название PyPI-пакета по одному namespace не выводилось.
- Контракты: `AgentListingRegistry`, `AgentAuditPool`, `AgentCollateralVault`, `AgentShareToken`, `AgentNoteToken`, `AgentLendingPool`, `PulseAMM`, `PulseDistributor`; сохранены шесть публичных EVM addresses из локального deployment registry.
- Solana: package `acex-capital`, lib `acex_capital`, `declare_id` `9BkXiRFMB5bAMMqAXxTzaLPYspiGxoUTEeX8kih9ne73`; инструкции CapSense. Наличие ID в Anchor config не выдаётся за проверенный активный deployment.
- HTTP: `/api/v2/capital/pricing`, SSE `/stream`, WS `/ws`; Hub `/ai-market/v2/capital/{pricing,ipo,listings}`; origins `modelmarket.dev` и `magic-ai-factory.com`.
- Настройки/протокол: `VITE_PULSE_API_URL`, `ACEX_JUPITER_QUOTE_URL`, `ACEX_JUPITER_SWAP_URL`, `ACEX_REQUIRE_AI_AUDIT`, `ai-auditor:acex-v1`, `acex-ai-audit`.

Отдельно отмечено направление связи: наш `fetch_jupiter_quote` обращается к Jupiter, а `build_swap_plan` описывает его swap endpoint. Это не свидетельство того, что Jupiter применяет ACEX.

## Проверка по этим fingerprints

Выполнены16 целевых web queries в четырёх сохранённых batch responses: Python imports, наборы имён контрактов, audit tags, точные capital routes/origins, Jupiter config, Solana ID и PulseAMM address.

Корневая ветка дополнительно получила **пять относящихся к ACEX публичных GitHub Search ответов**, все HTTP200, `total_count=0`, `incomplete_results=false`:

1. Exact `github.com/alexar76/acex` в чужих README — закрывает ранее неотправленный запрос.
2. `acex.integrations` в чужих README.
3. `AgentAuditPool` в чужих commit messages.
4. `AgentListingRegistry` в чужих commit messages.
5. `ACEX_JUPITER_QUOTE_URL` в чужих README.

Их bytes, timestamps и SHA256 принадлежат общей корневой ветке: [gap-search index](../root/plan-2-search-index.json), [exact-search index](../root/plan-4-exact-search-index.json). Здесь они повторно проверены локально и **не считаются ещё пятью сетевыми запросами**. Эта ветка не обращалась к `api.github.com` и не предполагала восстановления CORE quota. Ответные HTTP Date раньше времени корневого capture; оба значения сохранены, гарантии мгновенной свежести индекса не делаются.

Нули относятся к конкретным README/commit searches, а не ко всем строкам кода GitHub. Прямое HTTP использование, private configs и непроиндексированные файлы могли остаться вне выборки.

## Два конкретных ложных следа

**PyPI `acex` — другой проект.** [Первичный JSON](https://pypi.org/pypi/acex/json), HTTP200, указывает version7.0.0, продукт ACE-X Backend и repository `github.com/acex-labs/acex`. В полученных metadata и declared dependencies нет alexar76, modelmarket.dev, наших namespaces/контрактов и aimarket зависимости. Это bounded проверка registry identity, не полный аудит чужого кода. Пользователей и downloads этого пакета нельзя относить к нашему ACEX. Поля сохранены в `homonym-analysis.json`.

**Fastly URL с нашим Jupiter guide — поисковая копия собственного контекста.** Выдача показывает `alexar76/acex/.../docs/jupiter-routing.md` и наш пример импорта. Прямой GET вернул503; текущая HTML-страница не подтверждена первично. Другой hostname и собственный скопированный пример не доказывают независимое применение. Содержимое503 и его хеш сохранены; повторов и обходов не было.

Большие PyPI simple indexes из выдачи содержат отдельные похожие слова, но не устанавливают ни наш namespace, ни вызов ACEX. Они не загружались целиком и не засчитывались. Кандидатов с реальным чужим source/config не возникло, поэтому дополнительные пустые GET для достижения численного ориентира не выполнялись.

## Свидетельства и новизна

По сравнению с `artifacts/external-components-2026-11-10/core/` новое здесь — **полнота ACEX fingerprints, завершённый exact repo query, четыре дополнительных GitHub queries и разобранный PyPI homonym**. Нового runtime кейса или независимого теста продукта нет. Существующие Enterprise/Industrial/agent-exec не пересчитывались как новые ACEX внедрения.

В этой ветке два primary GET: один200 и один503. Проверены длина/полнота/SHA256 обоих тел и пяти общих GitHub bodies;27 локальных source hashes при сборке совпали. `coverage.json` содержит результат по каждому измерению, `findings.json` — атрибуцию и source→target, `capture-integrity.json` — целостность.

Публикаций, входа в аккаунты, сообщений, установки/исполнения чужого кода, вызовов инструментов, транзакций и проверки live chain-state не было. Локальная пересборка: `.venv/bin/python artifacts/external-matrix-gaps-2026-11-10/acex/build_report.py`.
