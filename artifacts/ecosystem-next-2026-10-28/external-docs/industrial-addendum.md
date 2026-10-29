# Industrial Platform: подтверждён совместимый внешний AIMarket manifest

Дополнительная проверка 28 октября около17:11–17:13МСК после первоначального неподтверждённого PR49. Выполнены ещё семь публичных GET: шесть200, один404(rootpackage.json). POST, invoke, установки, оплаты и авторизации не выполнялись.

## Прямое техническое свидетельство

На стороннем [Industrial Platform gateway](https://x402-gateway-production-1f21.up.railway.app/.well-known/ai-market.json) опубликован AIMarket federation adapter **Industrial Platform Sentinel**, node ID `industrial-sentinel`. Discovery и [manifest](https://x402-gateway-production-1f21.up.railway.app/ai-market/v2/manifest) ответили HTTP200. В manifest четыре capability, все с нулевой ценой: install, wallet-monitor bootstrap, treasury-monitor bootstrap и transaction-watch bootstrap.

Публичный [исходник адаптера](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/blob/main/gateway/aimarket-federation.mjs#L108) прямо комментирует совместимость с AIMarket `manifest_canonical` и Python `json.dumps(sort_keys=True)`. Он реализует специфическую каноническую строку нашего протокола: `capabilities_count`, `generated_at`, `protocol_version`, `tools_hash`, `by_hub_hash`, включая Python JSON separators. Она совпадает с локальной спецификацией `aimarket-protocol/spec.md` §7.3.2 и `web/backend/services/ai_market_protocol/signing.py:150`. Это сильнее общего совпадения имени AIMarket; прямой modelmarket.dev/alexar76 URL в прочитанных внешних файлах не найден.

**Подпись полученного live manifest успешно проверена нашей чистой функцией `manifest_canonical` и локальной cryptography Ed25519.** Для контрольной проверки цена первой capability изменена только в памяти на0.01; та же подпись отвергнута. Никаких сетевых вызовов во время проверки и исполнения исходника провайдера не было. Из нашего backend через AST извлечена только чистая функция; приложение не импортировалось.

Это подтверждает работающую внешнюю публикацию manifest, совместимую с форматом и подписью нашего протокола на данном снимке. Не подтверждены полное соответствие протоколу, оператор/юридическая личность, официальный партнёрский статус, клиенты, установка Sentinel или реальные платежи. Ключ объявлен самим провайдером; проверка подписи не является проверкой его личности. Самообозначение `independent-provider` передано как метаданные источника.

## Ограничения предложения и PR

Discovery указывает `payment_configured:false`; AIMarket capabilities предоставляют бесплатный bootstrap. Заявленные recurring paid calls относятся к отдельным прямым x402 routes, не доказанным платежам через AIMarket. Manifest публикует `observations_30d:0`; заявленные latency/success fields в этом проходе не измерялись и за реальные показатели использования не выдаются.

[PR49 от13октября](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/pull/49) всё ещё **open**. [Публичный diff](https://github.com/industrial-platform-ai/industrial-platform-agent-tools/pull/49.diff) добавляет `/ai-market/v2/health` в уже существующий adapter и уточняет описание. Полученный main source содержит discovery/manifest/search/invoke, но ещё не добавленный в PR health handler. Успех live discovery/manifest не доказывает развёртывание этого PR или health-исправления. Опубликованные утверждения автора о запросах discovery clients из production logs не устанавливают, кто управлял этими клиентами.

## Свидетельства и воспроизведение

- `industrial-federation-source-live.json`: source/live URL, время, статус, SHA256 и публичные JSON-поля. Live manifest получен2026-10-28T14:11:32.585350UTC, response SHA256 `c58bf3cba9a55b6f38283caeb035fb326867b04793574725b733e930b2285a72`.
- `industrial-manifest-compatibility.json`: origin, provider identity fields, публичный ключ, canonical и два результата проверки.
- `verify_industrial_manifest.py`: минимальная проверка уже сохранённого снимка, без сетевых обращений и кода провайдера. Запуск: `python3 artifacts/ecosystem-next-2026-10-28/external-docs/verify_industrial_manifest.py`.
- `industrial-platform-pr49-diff.json`, `industrial-platform-root-source.json`: diff и README. Отсутствие root package.json не означает отсутствия приложения: adapter явно находится в подкаталогеgateway.

Текущие исходники читались из mutable main; их SHA256 сохранены. Immutable commit внутри возвращаемого install bundle относится к самому Sentinel bundle, не автоматически ко всему текущему адаптеру. Полное клонирование, исполнение внешнего кода и публикации не выполнялись.
