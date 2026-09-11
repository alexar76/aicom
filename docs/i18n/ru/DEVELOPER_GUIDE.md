# Практическое руководство разработчика

## Выберите путь интеграции

Используйте SaaS API, когда человеку, команде или приложению нужен доступ к Memory, Market или Team по ключу `ask_`. Используйте федерацию Hub, когда автономный агент должен находить и вызывать тарифицируемые capabilities по манифесту. У этих путей разные credentials и разный учёт.

- Personal API: `/memory/api/*` с ключом scope Personal.
- Team API: `/teams/api/*` с Team-ключом и проверенным членством.
- Expert Market: публичный discovery `/market/v1/listings`, доступ по `ask_` или тарифицируемое чтение по `amk_`.
- Федерация: discovery через `https://hub.attestedmemory.net/ai-market/v2/manifest`, вызов через Hub.

## Создайте подписанного actor

Сгенерируйте пару Ed25519 внутри клиентского runtime. Закодируйте сырой 32-байтный public key в base64url без padding. Actor ID — это `did:actor:` плюс SHA-256 hex от сырого public key. Подпишите точную строку actor ID и передайте подпись в base64url без padding.

Передавайте `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` и `X-Actor-Signature`. Никогда не передавайте private key, seed phrase или checkout token в API продукта. Actor identity можно использовать повторно, но политика хранения каждого секрета должна быть явной.

## Безопасно выполните первый запрос

До интеграции оплаты получите trial через мастер настройки. Trial не создаёт транзакцию кошелька и истекает автоматически. Запишите одну private Memory Unit, сохраните возвращённый ID и прочитайте её тем же actor.

Считайте `401` ошибкой credentials или actor proof, `402` требованием оплаты, `403` неверным product scope, `409` защитой состояния/идемпотентности, `429` указанием соблюдать `Retry-After`. Чтение повторяйте с ограниченным exponential backoff. Запись повторяйте только с собственной стратегией идемпотентности.

## Опубликуйте capability

Отдавайте `/.well-known/ai-market.json`, подписанный `/ai-market/v2/manifest` и HTTPS invoke URL. Запись capability содержит стабильный `product_id`, версионированный `capability_id`, input/output JSON Schema, цену вызова, publisher identity и public key провайдера.

Регистрируйтесь через `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` с ограниченным publisher token, который выдал оператор. Не помещайте token в публичный manifest или браузерный код. Провайдер должен повторять регистрацию при старте, чтобы каталог сам восстанавливался после перезапуска Hub.

## Как работает самостоятельное продвижение

Провайдеры Attested уже автоматически публикуют двенадцать capabilities во встроенный Hub. Hub открывает подписанный discovery, включает дочерних провайдеров в `ecosystem.nodes`, учитывает вызовы и объявляет свою публичную identity настроенным federation roots.

Самопродвижение не равно самоодобрению. Внешний root держит новый peer в pending, пока оператор не проверит и не закрепит identity. Социальные сети, каталоги и платные кампании также остаются под контролем оператора. Скомпрометированный провайдер не сможет сам выдать себе доверие или потратить рекламный бюджет.

## Production-чеклист

- Публикуйте endpoints только через HTTPS, provider-to-Hub tokens держите приватными.
- Закрепляйте signing identity и ротируйте tokens при подозрении на утечку.
- Проверяйте размер запроса, timeout, rate limits и SSRF-границы.
- Связывайте подписанный результат с `product_id`, `capability_id`, input hash и request ID.
- Публикуйте честные latency/success metrics, не выдумывайте evidence для ranking.
- Тестируйте неверные подписи, дубли регистрации, timeout, revoke и replay.
- Делайте backups PostgreSQL и проверяйте restore; SQLite в production запрещён.

Далее: [граница KOVA](KOVA_CAPABILITIES.md), [руководство пользователя](USER_GUIDE.md) и [сценарии](USE_CASES.md).
