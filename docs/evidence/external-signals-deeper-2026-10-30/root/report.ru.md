# Внешние маршрутизаторы и реализации протокола 30 октября 2026 года

Этот раздел сопоставляет новые публичные чтения с сохранёнными результатами 27–29 октября. Новые факты относятся к декларациям роутера и проверке подписи конкретного manifest. Платные вызовы и запуск чужих инструментов не выполнялись.

## Agent402 изменил основание ограничения AIMarket

[Индекс Agent402](https://agent402.tools/api/index?seller=modelmarket.dev) теперь показывает **170 HTTP-маршрутов, восемь платных**, routerDispatchReason=settlement_required. В [снимке 29 октября](../../../../artifacts/external-deep-2026-10-29/independent-tests/agent402-fact.json) было 173 маршрута и settlement_self_funded для всех восьми платных путей. Число HTTP-маршрутов не равно количеству продуктов или пользователей.

Семь из восьми платных путей теперь имеют Base unprovenTier=true с лимитом underlying price $0,01. nearby-sensors за $0,03 такой отметки не имеет. Это отличие текущего публичного решения от сохранённого снимка; причины изменения и первичные транзакции не проверялись. Смена метки не доказывает новую покупку или опровержение/подтверждение прежней классификации.

Бесплатная [рекомендация WARDEN](https://agent402.tools/api/route?q=WARDEN&include=external&top=10) содержит modelmarket.dev/x402/warden-scan и **executeViaCallableNow=true, executeViaLane=unproven**. В ней указан upstream price $0,001 и цена агрегированного route-execute $0,01. Это объявленная доступность через ограниченный режим после proven-кандидатов, не квитанция исполнения. Запрос HISTOR в top 10 нашего маршрута не вернул; более широкие страницы не читались.

[Опубликованный исходник dispatch-eligibility.js](https://github.com/MikeyPetrillo/Agent402/blob/48aff2412cd297da40eaadf3f61f25a5b1be2a68/src/dispatch-eligibility.js#L277) согласуется с флагом: unproven tier разрешается для settlement_required, положительной цены в пределах лимита и отсутствия отдельной ошибки привязки кошелька. Commit и три файла сохранены как текст; не исполнялись. Production overrides и исходные расчёты settlement не воспроизводились.

## Подпись agent-exec соответствует канонизации нашего Hub

[Discovery agent-exec](https://agent-exec.448c.org/.well-known/ai-market.json) и [manifest](https://agent-exec.448c.org/ai-market/manifest) прочитаны с HTTP 200. Manifest объявляет **protocol_version=v1, 15 tools**, у каждого есть input_schema. Подпись — объект, ключ совпадает с discovery.

Ed25519-подпись снимка корректна над строкой, рассчитанной нашей manifest_canonical из signing.py. Контрольное изменение описания первого инструмента делает подпись некорректной. Это подтверждает совместимость подписываемых байтов конкретного снимка; полный протокол, безопасность сервиса и исполнение tools не проверены.

[Публичный список peers Hub](https://modelmarket.dev/ai-market/v2/federation/peers) показывает agent-exec как active/trusted с тем же public_key, но capabilities_count=0. Такой active peer уже присутствовал в [сохранённом ответе 29 октября](../../machina-federation-recheck-2026-10-29/hub-peers.json). Поэтому это новая проверка совместимости, не новое подключение 30 октября и не 15 исполненных предложений в нашем каталоге.

Проверка [Machina](https://mach402.dev/ai-market/v2/manifest) показывает прежнее препятствие: восемь tools, signature остаётся строкой; Ed25519 корректен над compact sorted JSON, но не над нашей canonical string. Machina остаётся pending. Текущее состояние совпадает с прежним локальным диагнозом; новая успешная интеграция не установлена.

[Скрипт проверки](verify_peer_manifests.py) извлекает через AST только чистую manifest_canonical из локального кода и использует cryptography для Ed25519. Ключи не генерируются, чужой код не запускается. [Результат](peer-manifest-compatibility.json) содержит отрицательный контроль и SHA-256 локального источника.

## Известные покупки и собственная телеметрия

[UseTested](https://usetested.com/v1/review?service=modelmarket.dev) всё ещё показывает один исторический тест histor-check от 27 октября за $0,001. Число calls_tested=1, квитанция и updated_at не изменились. Эта покупка уже была проверена 29 октября; повторного спроса здесь не найдено.

Публичный stats/live нашего Hub отдельно сохранён, но не используется как независимый источник. Метка external при traffic_basis=null является запасной классификацией. Псевдонимы sandbox и собственные агрегаты не позволяют установить новых независимых людей или команды.

## Область

В этой ветке выполнены **28 web-запросов и 17 GET**, все HTTP 200. Точные дополнительные домены включают emberlinedesk.com и Deal/Meter/Prove Attested Memory. Нового атрибутируемого внедрения по ним не найдено в просмотренных результатах.

Запросы сохранены в search-0.json…search-6.json; HTTP-чтения — в http-index.json, http-source-index.json, http-route-index.json и http-peer-index.json. [summary.json](summary.json) объединяет факты и ограничения. Публикаций, сообщений, платежей, invokes, допуска peers и изменений аккаунтов не было.

