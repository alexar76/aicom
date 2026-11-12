# Почему Agent402 не маршрутизирует восемь платных API AIMarket

Срез: 9 ноября 2026, 19:34–19:37 UTC. Это публичные чтения и локальная диагностика; ни платежей, ни tool invokes, ни сообщений, ни внешних записей не выполнялось. Чужой код загружен как текст и не исполнялся.

**Подтвержденная непосредственная причина:** Agent402 применяет один seller/wallet-level settlement gate ко всем восьми маршрутам. Его нынешний verdict — `settlement_self_funded`, detail `below the settlement floor`. Этот reason отключает и proven, и дешевую unproven lane. Наши цены и USDC domain этот блок не объясняют. **Но сам reason не доказывает, что конкретные деньги AIMarket были seller-funded:** upstream складывает в одну категорию также возвраты и собственные покупки роутера. Для AIMarket конкретные net/gross figures и deduction classes публично не раскрыты.

## Что отвечает production

[Seller index](https://agent402.tools/api/index?seller=modelmarket.dev) и [WARDEN route search](https://agent402.tools/api/route?q=WARDEN&include=external), прочитаны заново в 19:34–19:35 UTC:

- 183 маршрута, восемь платных; все восемь имеют `executeViaCallableNow=false` и одинаковый reason выше.
- Last crawl `fetchedAt=1794248039060`; health=1, routable=true, Base network известен.
- Live/crawled payTo в индексе — **0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a**.
- Канонический Base USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, domain `USD Coin`; положительного domain mismatch нет.
- Цены underlying: HISTOR, WARDEN, weather, air quality — $0.001; x402-check и mcp-diff — $0.003; fair-random — $0.006; nearby-sensors — $0.03. Все ниже текущего $0.05 unproven ceiling. Этот runtime ceiling виден у других unproven результатов того же WARDEN route search, а не только в source defaults.

Это диагноз решения одного роутера. Прямое платное выполнение наших функций здесь не повторялось. Наличие tier metadata `executeVia` само по себе не означает разрешение: явный callable flag false.

### Прямые неоплаченные HEAD quotes

В **19:52:32–19:52:33 UTC** выполнено ровно восемь HEAD непосредственно к нашим платным URL: **8/8 HTTP402**, `Allow: POST`, читаемый PAYMENT-REQUIRED. Redirects отключены; payment headers, подпись и тело запроса отсутствовали. Во всех challenge один accept: exact, `eip155:8453`, canonical USDC `0x8335…2913`, payTo `0x1218…Ad0a`, EIP-712 `USD Coin` / `2`.

| Route | Atomic USDC из HEAD |
|---|---:|
| histor-check | 1000 |
| warden-scan | 1000 |
| air-quality-now | 1000 |
| weather-now | 1000 |
| x402-check | 3000 |
| mcp-diff | 3000 |
| nearby-sensors | 30000 |
| fair-random | 6000 |

Все суммы совпали с прочитанным Agent402 index. Полные headers/challenge, UTC и hashes — [quotes/summary.json](quotes/summary.json) и восемь route JSON. Это независимая от crawler cache проверка **готовности отдать платежные условия**, не оплаченной доставки или settlement.

Перед запросами проверен локальный source: [okx-a2mcp/src/app.js:183](/Users/alex/Desktop/ai_tests/aicompany/aicom/okx-a2mcp/src/app.js:183) завершает неоплаченный HEAD в quote branch перед POST quota/allow handler и `service.handle`; HEAD с payment header получил бы405. Source hashes и выдержки — [quotes/source-check.json](quotes/source-check.json). Это review workspace implementation, без утверждения о hash deployed binary. Ни free quota, ни платная функция в этой ветке исходника не вызываются; runtime quota counters отдельно не читались.

## Ветка решения и пороги

Зафиксирован public main **81a674d1a3cf7fdbbcc04f4da366c144ccd393f7**, commit 9 ноября 12:35:30 UTC. Это проверенный source snapshot; отдельного соответствия deployed binary этому SHA не установлено.

[settlement-proof.js#L315](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/settlement-proof.js#L315) и [server.js#L1349](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/server.js#L1349) задают default proven floor: **50 settlements и три distinct payers**. Если payer figure неизвестна, breadth не применяется; измеренный ноль применяется. Значения могут быть изменены env `SOR_MIN_SETTLED_TX`/`SOR_MIN_DISTINCT_PAYERS`; публичные modelmarket rows не показывают эти runtime env, поэтому 50/3 здесь именно defaults.

Последовательность в [dispatch-eligibility.js#L303-L334](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/dispatch-eligibility.js#L303-L334):

1. Проверяется net credited history. Недостаточная — `settlement_required`.
2. Если **withheld gross** history на соответствующем wallet прошла бы floor, reason меняется на `settlement_self_funded` ([line 312](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/dispatch-eligibility.js#L312)). Это не правило «хотя бы один свой тест означает блок».
3. Unproven допускается только при reason `settlement_required`, без wallet-binding defects и с ценой в потолке ([line 332](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/dispatch-eligibility.js#L332)). Reason из пункта 2 поэтому выключает trial.

Потолок unproven с 5 ноября увеличен **$0.01 → $0.05**; default rolling caps $0.25 на seller и $5 на lane за 24 часа ([base-unproven.js#L13-L48](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/base-unproven.js#L13-L48)). Эти caps проверяются позже при покупке; нынешний reason возник до них.

## Какие деньги он учитывает

Gate объединяет per-wallet evidence из трех источников: собственный leaderboard scan, chain merchant join и Bazaar quality. Это maxima/выбор лучшего wallet evidence, а не сумма всех счетчиков. Данные засчитываются там, куда live 402 просит платить.

- [Текущий leaderboard](https://agent402.tools/api/leaderboard) сообщает scan window **7 days**, asOf **2026-11-09T16:43:38.723Z**, windowSeconds=604800. При `?seller=` он не фильтруется; top/limit публично ограничены 50. Наш малый seller в прочитанном top50 отсутствует, что не означает нулевой ledger.
- [Bazaar branch](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/evidence-binding.js#L217-L245) читает **30-day** counts. Поэтому восемь прямых входящих переводов за последние семь дней не опровергают возможность gross>=50 из Bazaar за 30 дней. AER resource totals не являются точной копией Agent402 cache и не подставляются в его формулы как измеренные inputs.
- [seller-funding.js#L1-L67](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/seller-funding.js#L1-L67): только собственные исходящие USDC с payTo к payer, в chain order. Пул расходуется FIFO на последующие обратные payments. Покрытый минимум наполовину payment перестает считаться settlement. Предыдущие genuine payments могут сниматься как refunds при последующем исходящем transfer; экономическое назначение другого сервиса из USDC Transfer не видно.
- История пары wallet/payer при первом чтении идет с deployment canonical USDC (default block **2,797,221**), не только за семь дней. Pools сохраняются. Если более половины прочитанных известных USD self-funded, wallet circular; `lastCircularAt` может удерживать suppression Bazaar/chain evidence **30 дней**. Pending funding reads после прежнего circular verdict также могут удерживать credited figures. Точный retained state AIMarket публично не прочитан.
- Собственные покупки **Agent402** также исключаются из proof seller. Это действует с [commit 8b8a4cee, 29 октября 01:06 UTC](https://github.com/MikeyPetrillo/Agent402/commit/8b8a4cee0ca939af69856ddedafa85cb0303e044).

## Подтвержденная неточность upstream reason

В [evidence-binding.js#L220-L245](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/evidence-binding.js#L220-L245) net reductions включают **self-funded calls, refunds и router purchases**. [Line 272](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/evidence-binding.js#L272) сохраняет **любую** reduced gross figure в selfByWallet; line 258 делает то же для gross/net leaderboard. Dispatch branch не различает эти причины.

Следовательно, публичное описание reason, которое говорит об USDC, сначала посланном продавцом покупателю, шире фактически проверенной причины. Это конкретный источник ложной атрибуции, а не доказательство, что AIMarket попал именно в нее.

[diagnose.py](diagnose.py) — наша независимая сокращенная арифметическая модель этих веток. Она не импортирует upstream code и не делает network calls. Пять **синтетических**, не production, случаев дают:

| Gross / net calls | Почему deducted | Seller-funded calls | Verdict / trial |
|---|---|---:|---|
| 49 / 49 | нет deductions | 0 | settlement_required / trial да |
| 50 / 49 | один router purchase; gross4/net3 payers | 0 | settlement_self_funded / trial нет |
| 50 / 49 | один refund | 0 | settlement_self_funded / trial нет |
| 50 / 49 | один funded payment | 1 | settlement_self_funded / trial нет |
| 51 / 50 | один router purchase | 0 | proven |

Предпосылки: один origin/wallet, Bazaar — сильнейший source, scanGenuine ниже него, известный правильный payTo/domain, нет delivery/category failures, минимум три net payers. Это показывает threshold cliff и неоднозначный label. Не воспроизводит полный накопленный ledger или exact AIMarket verdict inputs. Результаты — analysis.json.

## Что показывает покупка WARDEN 30 октября

Операторский тест был успешен: заплачено router **0.01 USDC**, получено за WARDEN **0.001 USDC**, чистый расход **0.009 USDC**. Это не независимый спрос.

Сохраненные проверенные receipts: block **53,272,857**, **2026-10-30T04:37:41Z**:

- Router **0x77065d81e18ad403BCD6e9A0616b288e16744121 → payout wallet 0x1218…Ad0a**, 1,000 atomic USDC, [tx 33c43c…](https://basescan.org/tx/0x33c43c06ad086a068983c14bf2788c217544feaec873160b0ff5b2188fff1279), **global log 73**.
- Payout wallet **→ router**, 10,000 atomic USDC, [tx 097048…](https://basescan.org/tx/0x097048836ca8a17feda32b06d39ba69439f00c0ddd435eee336c5e4097c7e9c9), **global log 342**.

Порядок принципиален: upstream payment был **раньше** оплаты роутера. Нельзя автоматически назвать его seller-funded prepayment. Если бы до пары не было pool/credit/refundable history и оба события попали в read, сокращенная логика сочла бы 0.001 refunded, а остаток 0.009 оставила в pool для поздних payments. Экономически это была покупка у роутера, а не refund; токеновые события не несут это назначение. Существовавшее retained state неизвестно, поэтому фактическую запись Agent402 этим сценарием не объявляем.

В пределах [bounded chain-сверки](chain/report.ru.md) за последние семь дней payout wallet получил восемь переводов canonical USDC на **0.009 USDC** от семи адресов и отправил один на **0.002 USDC**. Новых переводов пары payout↔router нет; последние видимые — этот октябрьский тест. Этот короткий ряд не равен Bazaar30d и не объясняет exact Agent402 deductions. Тест30окт нельзя объявлять единственной причиной нынешнего блока.

## Регрессия и пути исправления

**Новое ужесточение source policy не подтверждено.** seller-funding.js pinned 30 октября и 9 ноября byte-identical: SHA-256 **15978a7b2163fc66971b534ad8e35abe36a856d919cdcde2dc339375de0b9564**; последний source commit этого файла — [dd4e97c8, 29 сентября](https://github.com/MikeyPetrillo/Agent402/commit/dd4e97c882d7fd7d7f9fd871e0db1dfb7bf34a7f). Base deductions в evidence-binding также сохранились; diff 6 ноября расширяет другие EVM chains. Наблюдаемая перемена соответствует изменению rolling counts, cached evidence или funding-read state; выбрать конкретный вариант без подробностей нельзя.

На нашей стороне published payTo/domain/цены выглядят согласованно; найденной ошибки accept, которую можно исправить для снятия этого verdict, нет. Правильные дальнейшие действия зависят от того, что лежит в private evidence:

1. **Уточнить underlying evidence у Agent402:** runtime floors, net/gross calls и payers, отдельно funded/refunded/router-owned deductions, source windows, lastCircularAt и funding-read progress. Плательщиков раскрывать для этого не требуется. Их source предусматривает такой operator dossier, но он token-protected; публичный seller dossier стоит $0.05 и не покупался.
2. **Upstream classification fix:** сохранять причины deductions раздельно и публиковать соответствующий reason. Решение unproven lane задавать самостоятельным policy условием, а не побочным эффектом слишком широкого reason. Proven floor и исключение router-owned demand можно сохранить. Допуск возвратов/своих router purchases в trial — решение оператора роутера, не факт, что gate следует отключить.
3. **Если net history действительно ниже floor:** это легитимное недоказанное proven-состояние. Его не исправляет изменение нашего API. Нужны настоящие повторные независимые покупки либо предусмотренная оператором bounded trial policy; операторские self-tests не превращаются в независимые покупательские доказательства.

Подготовлен factual correction [draft](upstream-correction-draft.en.md), **только локально**. Он не утверждает, что синтетический случай равен AIMarket, и не просит засчитать наши тесты как органический спрос. Ничего не отправлено.

## Проверка свидетельств

Сырые публичные ответы *.raw и четыре HTTP-index JSON; source-pin.json фиксирует SHA/date. analysis.json фиксирует живые routes, source equivalence и synthetic reproduction. Отдельно сохранены восемь HEAD quotes. Проверка хешей — verify_evidence.py / verification.json. Отдельный публичный source endpoint `src/index.js` оказался404; нужный entry point `src/server.js` затем прочитан. Private API, operator tokens, новый paid dossier и платные probes не использовались.
