# Capabilities KOVA в Attested

## Что такое KOVA

KOVA — независимый сервис для Base и USDC. Он не установлен внутри Attested Hub.
KOVA публикует в Hub шесть продуктов, которые агенты находят, оценивают и вызывают
через федерацию.

## Как агент вызывает KOVA

Агент обращается к Hub через `POST /ai-market/v2/invoke`, а не к приватному адресу
провайдера KOVA. Hub применяет правила доступа и расчётов, записывает вызов и
маршрутизирует запрос в KOVA.

Доступны `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` и `kova.usdc.webhook.register@v1`.

## Почему checkout идёт другим путём

Подписка Attested вызывает invoice API KOVA по аутентифицированному
service-to-service соединению. Она намеренно не покупает платную capability KOVA,
чтобы проверить платёж за саму себя. Так нет циклического биллинга: один заказ
создаёт ровно один entitlement.

## Кто платит KOVA

При покупке подписки USDC покупателя переводится напрямую на
`SAAS_PAYMENT_RECIPIENT`. В этом переводе нет автоматического split или процента
для KOVA. Gateway использует отдельный `KOVA_API_KEY`; если ключ получен по платному
тарифу KOVA Pro или Business, оператор покупает и продлевает его отдельно.
Федеративные вызовы capabilities — третий, независимо тарифицируемый контур: цена
за вызов и routing fee Hub записываются как потребление capability и не вычитаются
из оплаты подписки Attested.

## Что видно операторам

Hub записывает федеративный вызов, цену, статус и квитанцию. Заказы Attested,
trial/paid ключи и число запросов отдельно видны в защищённом Operator ledger.
Settlement desk KOVA показывает её заказы, префиксы ключей и API usage. Открытые
ключи ни одна панель не возвращает.

## Граница безопасности

Provider endpoint требует приватный `X-AIMarket-Internal-Token`, сверяет identity
маршрута и body и строже ограничивает write capabilities. Ответ содержит
`X-Provider-Signature`: Ed25519-подпись связывает `product_id`, `capability_id`,
хеш input и result, поэтому результат нельзя подставить к другому запросу.

## Безопасная настройка

Используйте случайный `KOVA_CAPABILITY_TOKEN` длиной от 32 символов, равный
`AIMARKET_CAPABILITY_TOKEN` Hub. Задайте `KOVA_HUB_URL` и `KOVA_INVOKE_BASE`.
Provider endpoints оставляйте в приватной сервисной сети, наружу публикуйте Hub.
