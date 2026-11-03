# Мандаты, субподряд и якорение квитанций

> **English:** [mandates.md](./mandates.md) · **Español:** [mandates.es.md](./mandates.es.md) · **Français:** [mandates.fr.md](./mandates.fr.md) · **中文:** [mandates.zh.md](./mandates.zh.md)
>
> Код: [`mandates.py`](../aimarket_hub/mandates.py) · [`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`anchoring.py`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/aimarket_provenance/anchoring.py)

Нормативный текст — [`aimarket-protocol/mandates.md`](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)
(AMD/1 для мандатов, SUB/1 для субподряда). Эта страница — о том, как запустить и использовать
это на данном хабе.

## Зачем нужна каждая часть

| Часть | На какой вопрос отвечает | Код |
|---|---|---|
| **Мандат** | «Кто разрешил эту трату, до какой суммы и на что?» Владелец подписывает лимиты для ключа агента; хаб сам их соблюдает. Агент никогда не держит API-ключ владельца. | `aimarket_hub/mandates.py` |
| **Субподряд** | «Этот поставщик, обслуживая меня, купил у другого поставщика — на чьи деньги и где это в моём счёте?» | `aimarket_hub/subcontract.py` |
| **Слой финансирования** | До того как запустится платёжный путь, решает, кто платит и под чьими лимитами; после — рассчитывает то, что открыл. | `aimarket_hub/invoke_funding.py` |
| **Якорение (anchoring)** | «Может ли хаб потом отречься от квитанции или изменить её дату?» Дайджест каждой квитанции о работе попадает в публичный журнал квитанций HISTOR. | `plugins/aimarket-provenance/aimarket_provenance/anchoring.py` |

Все три денежные части работают на **кредитном рельсе (credits rail)** — единственном рельсе, на
котором хаб сам учитывает деньги. Мандат или бюджет субподряда никогда не идут вместе с платёжным
каналом, платежом x402 или идентификатором посетителя песочницы: хаб отклоняет такое сочетание
(`400 mandate_rail_unsupported`, а для grant — `403 job_invalid`), вместо того чтобы соблюдать
лимит, которого он не видит.

## Денежные лимиты и граница expiry

- `perCall` ограничивает резерв на один вызов, включая routing fee, когда она применяется. `perDay` считает **календарный день UTC**, не скользящие 24 часа; `total` — необязательный общий бюджет. Это лимиты денег, а не количества запросов; встроенного почасового денежного лимита нет.
- Мандат и все его предки допускают работу только при `validFrom <= now < validUntil`. **Ровно в `validUntil` он уже истёк.** Это прекращает разрешение на новую работу, а не обещает отмену уже начатой работы или ончейн-возврат.
- При привязке владельца финансирующего аккаунта включите `require_mandate=True`. Одна регистрация мандата не мешает обладателю обычного API-ключа расходовать баланс вне мандата. Rate limit по IP/session не заменяет денежный бюджет ключа.
- У базового prepaid-баланса и API-ключа нет автоматического TTL. Восстановление резерва и внутренний возврат кредитов описаны в [жизненном цикле кредитов](credits-topup.ru.md#credit-lifecycle); это не выплата денег и не гарантия escrow-контракта.

## Владелец: финансировать агента, не отдавая ему свой ключ

```python
from aimarket_agent import AgentKey, issue_mandate, owner_link_payload
import httpx

HUB = "https://modelmarket.dev"                      # this hub's AIMARKET_HUB_URL, exactly
owner = AgentKey.from_seed_hex(OWNER_SEED_HEX)       # keep this offline
agent = AgentKey.generate()                          # this one goes to the agent

# 0. The account id your API key names.
ACCOUNT_ID = httpx.get(f"{HUB}/ai-market/v2/mandates/owners",
                       headers={"X-API-Key": API_KEY}).json()["account_id"]

# 1. Link your DID to your credit account (once). The API key proves the account, the
#    signature proves the key. require_mandate=True makes the raw API key stop paying.
httpx.post(f"{HUB}/ai-market/v2/mandates/owners", headers={"X-API-Key": API_KEY},
           json=owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True))

# 2. Issue and register a mandate for the agent key.
doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["gaia.*", "atlas.nearest.read@v1"],
                    per_call_usd=0.02, per_day_usd=1.00, total_usd=10.00, valid_days=30)
reg = httpx.post(f"{HUB}/ai-market/v2/mandates", json=doc).json()
# {"digest": "sha256-…", "status": "active", "root": "sha256-…", "root_issuer": "did:key:…", "depth": 0, …}
```

Чтобы агент мог открывать бюджеты субподряда, передайте в `issue_mandate` параметры
`subcontract_allowance_usd=` и `subcontract_max_depth=` (1–3); без них мандат не может за них
платить.

### Что отклоняет регистрация

`POST /ai-market/v2/mandates` не требует ключа: документ сам себя удостоверяет. Хаб проверяет
правила полей из спецификации (§3.2) и подпись, а затем отклоняет:

| Ответ | Когда |
|---|---|
| `403 mandate_invalid` "this mandate is not addressed to …" | `audience` не содержит `AIMARKET_HUB_URL` этого хаба в точности — схема, хост, порт и путь (хаб, смонтированный под `/hub`, — это `https://example.net/hub`), без завершающего слэша. Такой мандат хаб никогда не обслужит, поэтому и не хранит его. Нужная строка — `mandates.audience` в `/.well-known/ai-market.json`. |
| `402 mandate_unfunded` | Корневой издатель цепочки не привязан к аккаунту на этом хабе (шаг 1). |
| `403 mandate_invalid` "register the parent mandate first" | Переделегирование, родитель которого здесь не зарегистрирован. |
| `403 mandate_invalid` "… already registered a different mandate with id …" | Издатель уже зарегистрировал другой документ с тем же `id`. Один идентификатор credential называет один мандат у одного издателя; выпустите новый со свежим `id` (`issue_mandate` сам создаёт `urn:uuid:`, если не передан `mandate_id=`). |
| `403 mandate_invalid` "the mandate has already expired" | `now >= validUntil` (конечная граница исключительна). Мандат, у которого `validFrom` ещё впереди, регистрируется и читается как `pending`. |
| `403 mandate_invalid` "numbers in a mandate must be integers" | Где-либо есть дробное число или целое вне ±(2^53 − 1). Суммы — целые µUSD. |
| `400 mandate_malformed` | Тело не является JSON-объектом, у него нет канонической формы, или каноническая форма больше 16 КиБ. |
| `413 mandate_malformed` | Сырое тело больше 20 КиБ. |

Повторная отправка уже зарегистрированного документа возвращает тот же ответ — регистрация
идемпотентна по дайджесту (`status` будет `revoked`, если мандат с тех пор отозван).

**Правило ключей proof.** Объект `proof` должен содержать ровно `@context`, `type`,
`cryptosuite`, `created`, `verificationMethod`, `proofPurpose` и `proofValue`, а `proof.@context`
должен совпадать с `@context` документа. Причина: дайджест, которым называется мандат, берётся
от всего защищённого документа вместе с proof, но `eddsa-jcs-2022` хеширует конфигурацию proof,
подставляя `@context` *документа* вместо собственного, — поэтому `proof.@context` подписью не
покрыт. Будь он свободным, агент, которого мандат ограничивает, мог бы переписывать документ и
регистрировать копию за копией — каждая с новым дайджестом и новыми счётчиками лимитов, и ни одну
не затронул бы отзыв оригинала. `issue_mandate` и подписант ARGUS создают ровно такую форму.
Мандат, зарегистрированный до появления правила и нарушающий его, перепроверяется при каждом
чтении хабом и теперь показывает `invalid`.

### Владельцы и `require_mandate`

Только **первый** владелец аккаунта привязывается одним API-ключом. После этого добавить второй
DID, отвязать один из них или изменить `require_mandate` можно лишь с подписью уже существующего
владельца: утекает именно API-ключ, поэтому его одного не должно хватать, чтобы снять защиту:

```python
from aimarket_agent import owner_unlink_payload

# another owner (key rotation), authorised by an existing one
owner_link_payload(new_owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True,
                   authorized_by=owner)
# switch require_mandate off for a DID that is already linked: a policy change
owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=False,
                   authorized_by=owner, action="policy")
# unlink — body of POST /ai-market/v2/mandates/owners/unlink
owner_unlink_payload(old_owner.did, hub_origin=HUB, account_id=ACCOUNT_ID, authorized_by=owner)
```

Каждый запрос отправляется с `X-API-Key` аккаунта. Изменение без действительной подписи владельца
получает `403 owner_authorization_required`; DID, уже привязанный к другому аккаунту, —
`409 owner_linked_elsewhere`. `require_mandate` хранится для каждого привязанного DID отдельно, и
аккаунт заблокирован, пока он включён **хотя бы у одного** из его DID: чтобы выключить, нужна
смена политики для каждого такого DID. `GET /ai-market/v2/mandates/owners` (с API-ключом)
показывает привязанные DID и их `require_mandate`. Владельца, потерявшего все ключи,
восстанавливает оператор: тот же запрос с `Authorization: Bearer $AIMARKET_ADMIN_TOKEN` (и
API-ключом) заменяет подпись владельца.

Когда `require_mandate` включён, один API-ключ больше не двигает баланс:

- обычный вызов получает `402 mandate_required`, как и вызов, который просит бюджет субподряда
  без мандата;
- залог из кредитов (`POST /ai-market/v2/supply/stake` с API-ключом и положительным `amount_usd`)
  получает `403`: залог не заплатил бы вору, но заморозил бы баланс как обеспечение и подставил
  бы его под слэшинг.

Дочерний вызов, оплаченный из grant задания, это не затрагивает: его деньги были разрешены на
корневом вызове.

### Отзыв

Отзыв — `POST /ai-market/v2/mandates/revoke`: с подписью любого издателя в цепочке
(`revoke_payload(owner, hub_origin=HUB, digest=digest)`) или только с `{"digest"}` и `X-API-Key`
финансирующего аккаунта — как аварийный выключатель. Отзыв мандата отзывает всё, что от него
переделегировано. Уже взятые резервы рассчитываются как обычно.

### Подтверждение владельца выше порога

Добавьте в `limits` мандата `approvalAbove` (µUSD) — и любой вызов дороже этой суммы не
тратит деньги, а ждёт вас ([спецификация §5.6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)). Мелкие
вызовы идут без вас; крупный требует вашей подписи под **этим** вызовом.

1. Вызов агента выше порога отвечает `402 approval_required` с блоком `approval`:
   `approval_id`, `capability_id`, `amount_usd`, `max_usd` (потолок, который вы одобряете; для
   маршрутизированного вызова в нём комиссия маршрутизации), `body_sha256` (точный запрос),
   `expires_at` (24 ч) и `url`. Ничего не резервируется. Повтор до вашего ответа возвращает тот же запрос.
   Вызов, который другой лимит мандата (`perCall`, `perDay`, `total`, дневной лимит продукта) всё
   равно отклонит, сразу получает `402 mandate_limit`: вас не просят подписать то, что не выполнится.
2. Что ждёт ответа: `GET /ai-market/v2/mandates/approvals?status=pending` с `X-API-Key`
   финансирующего аккаунта.
3. Ответ: `POST /ai-market/v2/mandates/approvals/{approval_id}` с
   `{"decision": "approve", "by": <ваш DID>, "t", "n", "s"}`, где `s` — подпись Ed25519 над строками
   `aimarket-mandate-approval/1`, базовый URL хаба, `approval_id`, `approve`, дайджест мандата,
   `body_sha256`, `max_micro`, `t`, `n` (через `\n`). Подписать может любой DID-владелец аккаунта.
   Один API-ключ может только **отклонить** (`{"decision": "deny"}`): одобрение тратит деньги, а
   утекает именно ключ.
4. Агент повторяет тот же запрос со свежим доказательством. Вызов выполняется один раз;
   одобрение тратится вместе с ним или возвращается, если вызов сорвался до списания. Отказ
   действует до истечения запроса (`402 approval_denied`).

Одновременно ждать могут не больше 16 запросов одного мандата (`429 approval_queue_full`).
Переделегированный мандат сохраняет порог родителя и может его только понизить. По A2A задача
ждёт в `AUTH_REQUIRED` и сдвигается, когда вы ответили, с push-уведомлением на webhook агента.

### Уведомления, когда вызов ждёт вас

Без канала владелец узнаёт о запросе, только если спросит сам (шаг 2 выше). Подключите каналы к
финансирующему аккаунту — и хаб будет присылать туда каждый новый запрос и ответ на него.
Уведомление только сообщает: одобрить по-прежнему можно лишь подписью ключа владельца, которой нет
ни в чате, ни в канале, ни в задаче, и каждое сообщение объясняет, как одобрить и как отклонить.

```bash
# Telegram через бота хаба (если оператор его запустил): нажмите у него Start и укажите id своего чата
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "telegram", "chat_id": "123456789"}'
# … или через своего бота: добавьте "bot_token": "123456789:AA…"
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "slack", "webhook_url": "https://hooks.slack.com/services/T…/B…/…"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "jira", "base_url": "https://acme.atlassian.net", "email": "ops@acme.example",
       "api_token": "…", "project_key": "OPS", "issue_type": "Task"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "webhook", "url": "https://ops.acme.example/hooks/aimarket", "secret": "…"}'
# отправить тестовое сообщение сейчас и увидеть ответ канала
curl -X POST "$HUB/ai-market/v2/mandates/notify/<channel_id>/test" -H "X-API-Key: $KEY"
```

| `kind` | Что указать | Что приходит |
|---|---|---|
| `telegram` | `chat_id` (число или `@канал`, где бот — администратор). `bot_token` — для своего бота; без него используется бот хаба, если оператор его запустил (`GET …/notify` называет его в `telegram_bot`). | Сообщение: какая способность, сколько, потолок, до какого срока, как одобрить и как отклонить. В HTML, а если Telegram отверг разметку — те же слова простым текстом. |
| `slack` | `webhook_url` входящего webhook (`https://hooks.slack.com/services/…` или `/triggers/…`). | Тот же текст. |
| `jira` | `base_url` Jira Cloud (https), `email`, `api_token` (id.atlassian.com → Security → API tokens), `project_key`, `issue_type` (по умолчанию `Task`). | Задача на каждый запрос; ответ добавляется к ней комментарием. |
| `webhook` | `url` (https), необязательный `secret`. | `POST` с `{"event": "mandate.approval.requested" \| "….approved" \| "….denied", "approval": {…}, "title", "text"}` и заголовком `X-AIMarket-Event`; с секретом ещё `X-AIMarket-Signature: t=<unix>,v1=<hex HMAC-SHA256 от "<t>.<body>">`. |

- `GET /ai-market/v2/mandates/notify` — каналы аккаунта с итогом последней доставки каждого.
  Секреты — токен бота, URL Slack, токен Jira, секрет webhook — хранятся для отправки и никогда
  не возвращаются (у URL Slack видны последние четыре символа).
- `POST …/notify/{channel_id}/test` сразу шлёт тестовое сообщение и отвечает `delivered` и тем,
  что сказал канал; `DELETE …/notify/{channel_id}` удаляет канал. Не больше 8 на аккаунт.
- Канал принадлежит финансирующему аккаунту и слышит о каждом мандате, который этот аккаунт
  финансирует. Управляет каналами API-ключ аккаунта — тот же ключ и так видит его ожидающие запросы.
- Каждый адрес проверяется как любой адрес, который хабу даёт вызывающий: только https, никаких
  частных и metadata-сетей, имя разрешается один раз и закрепляется, без редиректов. Доставка идёт
  вне запроса, при отсутствии ответа, 5xx или 429 повторяется дважды (через 2 с и 10 с) и никогда
  не меняет запрос, о котором сообщает.

### Как прочитать статус мандата

`GET /ai-market/v2/mandates/{digest}` отвечает любому, у кого есть дайджест (на неизвестный —
`404 mandate_unknown`). `status` — это состояние мандата **как цепочки**: переделегированием,
родитель которого отозван, пользоваться нельзя, как бы чисто ни выглядела его собственная строка:

| `status` | Значение |
|---|---|
| `active` | Можно пользоваться сейчас. |
| `revoked` | Отозван он сам или предок. `revoked_at` заполнен только у мандата, который отозвали напрямую; у потомка — `revoked_at: null`, а причина — в `status_reason`. |
| `expired` | Он сам или предок вышел за свой `validUntil`. |
| `pending` | Он сам или предок ещё не вступил в силу (`validFrom` впереди). |
| `invalid` | Цепочка не держится: предка нет, звено нарушает правила сужения или сохранённый документ больше не проходит правила полей. |

Остальные поля — `issuer`, `subject`, `parent`, `root`, `chain` (дайджесты от корня к листу),
`depth` (0 у корня), `valid_from`, `valid_until`, `revoked_at` и `status_reason`, если статус не
`active`.

Расход — `usage`: `day`, `spent_today_usd`, `per_day_usd`, `remaining_today_usd`,
`spent_total_usd`, а также `total_usd` и `remaining_total_usd`, если у мандата есть лимит `total`, —
добавляется для двух видов вызывающих:

- финансирующего аккаунта корня, с его `X-API-Key`;
- любого ключа в цепочке — каждого издателя и каждого субъекта, чтобы владелец мог следить за
  агентом, которому переделегировал, — с доказательством запроса (request proof) для `GET`, с
  пустым телом и путём запроса:

```python
from aimarket_agent import request_proof

digest = reg["digest"]
path = f"/ai-market/v2/mandates/{digest}"
proof = request_proof(owner, hub_origin=HUB, leaf_digest=digest, body=b"", method="GET", path=path)
httpx.get(f"{HUB}{path}", headers={"X-AIMarket-Mandate-Proof": proof}).json()["usage"]
```

Непроходящее доказательство даёт `401 mandate_proof_invalid` вместо статуса. Трата записывается
на каждый мандат цепочки, поэтому цифры родителя включают то, что потратили его
переделегирования. `day` — календарный день UTC, который покрывает дневной счётчик.

## Агент: платить по мандату

```python
from aimarket_agent import AIMarketAgent, Mandate

client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent, hub_origin=HUB))
r = client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
r["mandate"]    # {"digest", "agent", "principal", "depth"} on a delivered call
```

Каждый вызов подписывается по точному телу, хабу, методу и пути и одноразовому nonce — в пределах
300 секунд от часов хаба. Путь **отсчитывается от базового URL хаба**: для хаба, опубликованного
как `https://example.net/hub`, POST на `https://example.net/hub/ai-market/v2/invoke` подписывает
`POST /ai-market/v2/invoke`, а `hub_origin` равен `https://example.net/hub`. `Mandate` по
умолчанию подписывает именно этот путь.

Что приходит, когда хаб отказывает:

- лимит превышен: `402 mandate_limit`, где `limit` называет какой (`perCall`, `perDay`, `total`,
  `perProductPerDay` или `subcontract.perCallAllowance` для бюджета субподряда), а `mandate` — мандат
  цепочки, который отказал. `perCall` покрывает всё, что резервирует один вызов, — у
  федеративного вызова это цена и комиссия маршрутизации вместе. Лимит на продукт считается по
  продукту, который хаб реально исполняет, какой бы `product_id` ни прислал вызывающий;
- вне области действия (scope): `403 mandate_scope`; неизвестен, истёк, отозван или адресован не
  этому хабу: `403 mandate_invalid`; неверная подпись, устаревший `t` или повторный nonce:
  `401 mandate_proof_invalid`; аккаунт, который платит только по мандату, вызван без него:
  `402 mandate_required`.

SDK возвращает отказ 403 по мандату или заданию как `{"refused": True, "error": …, "detail": …}`, а
не как `safety_blocked` — тот оставлен для шлюза безопасности контента. Ответы 402, 401 и 400
приходят как тело ответа хаба (`error`, `detail` и, где есть, `limit` / `mandate`).

Поставщик, которого запускает хаб, получает `X-AIMarket-Agent` (субъект листа) и
`X-AIMarket-Principal` (корневой издатель) — кто вызывает, заверенное хабом, — и ничего об
аккаунте или лимитах. Ни один из этих заголовков не отправляется при вызове, маршрутизированном на
хаб-пир: пир мандат не проверял.

Тот же мандат платит и через A2A (`POST /a2a`, [a2a.md](a2a.md)): заголовки идут в запросе A2A, а
вызов — в одной сырой части `application/json` с точными байтами, которые подписывает
доказательство, — по-прежнему для `POST /ai-market/v2/invoke`. Достигнутый лимит — это задача в
состоянии `REJECTED`. Чтение своих задач (`GetTask`, `ListTasks`) требует свежего доказательства
для `POST /a2a` и тела JSON-RPC. `aimarket_agent.A2AClient(HUB, mandate=…)` и `argus a2a invoke` в
ARGUS делают и то и другое.

**ARGUS** платит так же. `argus mandate keygen` печатает новый `did:key` агента и его секрет;
владелец выпускает мандат на этот DID и регистрирует его; `ARGUS_AGENT_KEY` (секрет) и
`ARGUS_MANDATE_FILE` (JSON мандата) переключают ARGUS на него. `argus mandate status` показывает
статус цепочки и расход, а `argus mandate delegate --to <did:key> --per-call <usd> --per-day <usd>`
регистрирует более узкое переделегирование для субагента.

## Поставщик: нанять другого поставщика внутри задания

> Полное руководство — диаграммы процесса и движения денег, где находятся деньги на каждом шаге,
> кто какой риск несёт, дочерние вызовы на других хабах, A2A, ошибки и заметки для оператора —
> в [subcontracting.ru.md](subcontracting.ru.md). Этот раздел — краткая версия.

Каждый поставщик, которого этот хаб исполняет через его invoke URL, получает `X-AIMarket-Job`
(токен, подписанный ключом, который хаб публикует как `signer_public_key` в своём well-known,
действителен 60 секунд) и `X-AIMarket-Hub` (куда его предъявлять), а если покупатель выделил
бюджет субподряда (allowance), ещё и `X-AIMarket-Job-Grant` — grant, секрет на трату из этого
бюджета. Отправляйте их обратно со всем, что покупаете, обслуживая вызов:

```python
from aimarket_agent import AIMarketAgent, JobContext

job = JobContext.from_headers(request.headers)       # None when the hub sent no token
buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
r = buyer.invoke_single("wx", "wx.read@v1", {"q": 1}, job=job)
r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

- С grant (**cost-plus**) покупка оплачивается из бюджета покупателя, и вместе с ней нельзя
  отправлять ничего другого — ни `X-API-Key`, ни мандата, ни канала, ни платежа x402
  (`403 job_invalid`); SDK не добавляет свою оплату, если у задания есть grant. Любая цифра
  баланса в ответе — это остаток бюджета, а не баланс покупателя.
- Без grant (**фиксированная цена**) вы платите своим рельсом; покупка всё равно появляется в
  дереве задания покупателя.

### Что хаб отклоняет внутри задания

| Ответ | Когда |
|---|---|
| `403 job_invalid` | Токен выпущен не этим хабом или истёк, либо вызов, для которого он выпущен, уже вернулся: поставщик, у которого токен пережил его вызов, не может прицепить покупки к заданию, чей счёт и квитанция уже выданы. |
| `402 allowance_exhausted` | Grant закрыт — он закрывается в момент, когда корневой вызов возвращается, — или остатка не хватает на цену. |
| `403 job_limit` | `limit` говорит, что именно: `depth` (глубже, чем разрешает задание), `cycle` (capability уже есть на пути), `nodes` (в задании уже 64 вызова, считая корень), `children` (у вызывающего узла уже 16 детей). |
| `403 mandate_scope` | Покупка за счёт grant вне области действия корневого мандата. |
| `400 subcontract_unsupported` | Вызов внутри задания просит собственный бюджет; задаёт его только корень. |

Какую глубину допускает задание: без бюджета (только связывание) — максимум хаба, 3: каждый
шаг платит сам за себя, поэтому глубина ограничивает лишь размер дерева. С бюджетом — `max_depth`
покупателя. Дочерний вызов, отклонённый уже после того, как он вошёл в дерево (например, вне
области действия корневого мандата или когда корневой мандат тем временем отозван), возвращает
свои слоты и показывается в дереве как `refused`.

### Сторона покупателя: бюджет и счёт

Покупатель просит бюджет на корневом вызове:

```python
r = client.invoke_single("brief", "brief.make@v1", {...},
                         subcontract={"allowance_usd": 0.005, "max_depth": 2})
```

`allowance_usd` должен быть больше 0 и не больше `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`;
`max_depth` — от 1 до 3 (по умолчанию 1). Хаб резервирует цену и бюджет вместе на кредитном
аккаунте покупателя, а при вызове по мандату — ещё и в цепочке мандата, чей лист должен содержать
блок `subcontract`, ограничивающий оба значения. Бюджет на вызове, который платит ончейн или через
канал, не несёт ни `X-API-Key`, ни мандата или маршрутизируется на пир, получает
`400 subcontract_unsupported`: хаб может пропускать через себя только те деньги, которые сам
учитывает.

Корневой ответ несёт bill of materials (спецификацию работ):

```json
"subcontracting": {
  "job_id": "job_…",
  "nodes": [
    { "node": "node_…", "parent": "node_…", "depth": 1,
      "product_id": "wx", "capability_id": "wx.read@v1",
      "price_usd": 0.001, "funded_by": "allowance", "status": "captured",
      "receipt_digest": "sha256-…", "receipt_id": "urn:uuid:…" }
  ],
  "spent_from_allowance_usd": 0.001,
  "allowance_usd": 0.005,
  "spent_usd": 0.001,
  "released_usd": 0.004
}
```

- `nodes` — это вызовы на субподряде; самого корня в списке нет. `status` — `running`, `captured`,
  `failed` или `refused`; `funded_by` — `allowance` или `own`. `receipt_id` и `receipt_digest`
  называют квитанцию о работе AWR/2 дочернего вызова.
- `price_usd` узла, оплаченного из бюджета, — это то, что этот вызов реально взял из бюджета (см.
  [правила ниже](#правила-которые-легко-упустить)); `spent_from_allowance_usd` — их сумма.
- `allowance_usd`, `spent_usd` и `released_usd` появляются, только если бюджет задан. `spent_usd`
  и `released_usd` — то, что рассчитал леджер; пока расчёт ещё не завершён (не удался возврат,
  который повторит зачистка — см. [Зависшие бюджеты](#зависшие-бюджеты)), они равны `null`.
  `null` не означает, что ничего не потрачено.
- Блок есть в ответе корня, **доставил корень результат или нет**. Субподрядчику, который
  доставил, платят, даже если нанявший его поставщик затем упал (cost-plus: израсходованные
  материалы оплачиваются), поэтому упавший корень всё равно возвращает счёт и `job_id`, которые
  объясняют списание.
- Каждый вызов, который хаб исполняет через эндпоинт поставщика, получает id задания, поэтому в
  его ответе есть блок `subcontracting`, даже если субподряда не было (`"nodes": []`).

`GET /ai-market/v2/jobs/{job_id}` возвращает дерево позже: те же узлы плюс собственный узел корня
(`depth` 0), `spent_from_allowance_usd`, а при бюджете — `allowance_usd`, `max_depth`,
`allowance_status` и `spent_usd` / `released_usd`, когда расчёт записан. Id задания — это
неугадываемая capability: кто его знает, тот может прочитать дерево, а хаб выдаёт его только
корневому покупателю и поставщикам задания.

Квитанция о работе AWR/2 корня перечисляет квитанцию каждого доставившего дочернего вызова в
`credentialSubject.parents`: `id` — это `receipt_id` дочернего вызова, `digestSRI` — его
`receipt_digest`. Квитанция каждого дочернего вызова делает то же для своих детей, так что дерево
закреплено подписью шаг за шагом, а не только описано.

Лимиты, которые хаб соблюдает, что бы ни просил покупатель: глубина ≤ 3, 64 вызова на задание
включая корень, 16 детей на вызов, никаких циклов (capability, уже стоящая на пути), токен живёт
60 секунд (30-секундный таймаут поставщика плюс 30), grant умирает вместе со своим корневым
вызовом.

### Правила, которые легко упустить

- **Дочернему вызову на другом хабе нужен `source_hub`.** На этом хабе должен исполняться только
  корень; дочерним может быть любая capability, которую этот хаб маршрутизирует, и её цена (а для
  перепродаваемого пира — ещё и комиссия маршрутизации) вырезается из бюджета так же, как у
  локальной. Но без `source_hub: <URL пира, который возвращает /search>` хаб ищет локальную
  capability, находит только листинг пира и отвечает `400` — а попытка всё равно занимает один из
  16 слотов детей вызова и показывается в счёте как упавший узел.
- **Токен задания и grant никогда не покидают этот хаб.** Маршрутизированный дочерний вызов
  приходит к пиру без них; связь и деньги остаются там, где хаб может их учитывать.
- **Проверяйте токен, прежде чем тратить.** Ваш invoke URL публичен. Проверьте подпись по
  `signer_public_key` хаба (из `/.well-known/ai-market.json`), что `iss` — это хаб, который вы
  обслуживаете, `exp`, что последний элемент `path` — *ваша* capability (хаб выдаёт токен каждому
  поставщику, которого запускает, — это не даёт другому поставщику переиграть свой токен у вас), и
  обслуживайте каждый `node` один раз. Всё остальное отклоняйте, ничего не покупая.
- **`max_price_usd` у маршрутизированного дочернего вызова сравнивается в целых центах.** Хаб
  называет цену маршрутизированной capability как её цену плюс комиссию маршрутизации,
  округлённую вверх до цента, поэтому потолок ниже $0.01 отклоняет дочерний вызов за $0.001 с
  `409 price_limit_exceeded`.
- **Счёт сходится.** `price_usd` узла, оплаченного из бюджета, — это то, что вызов взял из
  бюджета, включая комиссию маршрутизации, поэтому такие узлы в сумме дают `spent_usd`, и
  `spent_usd + released_usd == allowance_usd`. Упавший узел, чей резерв вернулся, показывает 0; тот,
  что всё же стоил денег (пир доставил, а затем не удалось списать комиссию), показывает взятое.

### Разобранный пример: `weather.witness@v1`

[`examples/subcontract-capability`](../examples/subcontract-capability/) — настоящий поставщик,
построенный по этим правилам и запущенный оператором хаба. Для места он покупает
`gaia.weather.read@v1` и `gaia.air.read@v1` (продукт `gaia.gateway`,
`source_hub: https://iot.modelmarket.dev`) через хаб, который его вызвал, внутри задания
вызывающего, и отвечает обоими показаниями с аттестацией устройств, совпадают ли они по месту и
времени, а также узлом задания и дайджестом квитанции каждого дочернего вызова — с подписью над
канонической формой хаба, привязанной к запросу. Cost-plus, когда покупатель присылает бюджет
(токен + grant, больше ничего); иначе фиксированная цена (токен + собственный `X-API-Key`, в
пределах дневного потолка, а без ключа он отказывает).

[`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py) — корневой покупатель:

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py            # cost-plus, allowance $0.01
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a      # the root call over A2A 1.0
```

Он проверяет два списанных дочерних вызова с ожидаемым финансированием,
`spent + released == allowance`, цены узлов, сумма которых равна потраченному, то же дерево из
`GET /ai-market/v2/jobs/{job_id}` и дайджесты квитанций детей в `credentialSubject.parents`
квитанции корня.

Важно понимать, что это демонстрирует: пример **самоприводной** — наш покупатель, наш составной
сервис, наша GAIA, внутренние кредиты. Каждый шаг идёт по продакшн-пути кода, и каждое утверждение
проверяется снаружи — для этого он и нужен; это не свидетельство того, что продукт нужен
кому-то ещё. В README примера есть инструкция для оператора (systemd, nginx, исключение по залогу,
публикация, аккаунт канарейки). `tests/test_subcontract_example.py` запускает поставщика и
канарейку против настоящего приложения хаба.

## Оператор

### Конфигурация

| Переменная | По умолчанию | Действие |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | Мандатам и бюджетам нужен включённый кредитный рельс; когда он выключен, вызов по мандату или с бюджетом получает `503 mandates_unavailable`. Токены заданий (связывание) работают в любом случае. |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | Публичный базовый URL хаба, вместе с путём, если хаб смонтирован под ним. Это audience, которую должен назвать мандат, и origin, который подписывает каждое доказательство, поэтому хаб со значением по умолчанию отклоняет каждый мандат, адресованный его публичному имени. |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | Наибольший сквозной бюджет, который может зарезервировать один корневой вызов. |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | Как часто зачищаются зависшие бюджеты (ниже). `0` выключает зачистку; значение меньше 10 поднимается до 10. |
| `AIMARKET_ADMIN_TOKEN` | не задан | `Authorization: Bearer …` с ним заменяет подпись владельца при смене владельцев — путь восстановления. |
| `AIMARKET_HISTOR_URL` | не задан | Куда плагин provenance отправляет якоря дайджестов квитанций; не задан — якорение выключено. |
| `AIMARKET_HISTOR_FLUSH_S` | `30` | Как часто очередь отправки (outbox) шлёт ожидающие якоря (пока HISTOR сбоит или откладывает, интервал растёт до 10 мин). |
| `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` | `30` | Сколько дней заякоренная строка хранится в outbox; потом маршрут статуса спрашивает HISTOR. `0` — хранить всё. |
| `AIMARKET_MANDATE_APPROVAL_TTL_S` | `86400` | Сколько открыт запрос на подтверждение владельца (300 с – 7 дней); одобренный надо использовать в том же окне. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN` (или `…_FILE`) | не задан | Собственный Telegram-бот хаба для уведомлений о подтверждениях: владельцу достаточно id чата. Без него Telegram-каналу нужен `bot_token` владельца. Никогда не пишется в журнал. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_NAME` | не задан | @имя этого бота; `GET /mandates/notify` показывает его владельцам, чтобы они знали, у кого нажать Start. |

Образ уже ставит `awr` (он нужен плагину provenance). Хаб, установленный без него, запускается
нормально и отвечает `503 mandates_unavailable` на вызовы по мандату.

Клиенты подписывают пути запросов относительно `AIMARKET_HUB_URL`; прежде чем проверять
доказательство, хаб убирает префикс монтирования, который ASGI-сервер сообщает как `root_path`.

### Блоки well-known

`/.well-known/ai-market.json` ещё до отправки чего-либо сообщает клиенту, соблюдает ли этот хаб
AMD/1 и SUB/1 и с какими лимитами:

```json
"mandates": {
  "spec": "aimarket-protocol/mandates.md", "version": "AMD/1", "enabled": true,
  "audience": "https://modelmarket.dev",
  "register": "/ai-market/v2/mandates", "owners": "/ai-market/v2/mandates/owners",
  "revoke": "/ai-market/v2/mandates/revoke", "status": "/ai-market/v2/mandates/{digest}",
  "max_chain": 4
},
"subcontracting": {
  "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1", "version": "SUB/1",
  "job_tokens": true, "allowance": true, "max_allowance_usd": 1.0,
  "max_depth": 3, "max_nodes_per_job": 64, "max_children_per_node": 16,
  "jobs": "/ai-market/v2/jobs/{job_id}"
}
```

`mandates.enabled` и `subcontracting.allowance` следуют `AIMARKET_CREDITS_ENABLED`;
`mandates.audience` — это `AIMARKET_HUB_URL` без завершающего слэша, ровно та строка, которую
должна содержать `audience` мандата; `max_allowance_usd` следует
`AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`.

### Зависшие бюджеты

Бюджет субподряда — это кредитный резерв на аккаунте покупателя, который должен жить ровно столько,
сколько его корневой вызов. Если корень так его и не рассчитал — падение посреди вызова, возврат,
который раз за разом не удавался, — деньги остались бы замороженными. Хаб проводит зачистку один
раз при старте и затем каждые `AIMARKET_SUBCONTRACT_SWEEP_S` секунд: бюджет, чей grant истёк
больше пяти минут назад, а резерв всё ещё держится, закрывается, остаток возвращается, резерв
бюджета по мандату рассчитывается до того, что взяли дети, и расчёт записывается — так у задания
заполняются `spent_usd` / `released_usd`. До 50 бюджетов за цикл; если что-то рассчитано, в лог
на уровне WARNING пишется `subcontract: settled N stale allowance(s)`. Зачистка работает только
при включённом кредитном рельсе и никогда — на пути запроса.

### Миграция 038

`038_job_receipts_and_settlement` добавляет:

| Колонка | Для чего |
|---|---|
| `job_nodes.work_receipt_id` | Id квитанции о работе дочернего вызова — его несут ребро `parents` родительской квитанции и `receipt_id` в счёте. |
| `job_grants.spent_micro`, `released_micro`, `settled_at` | Как был рассчитан бюджет, чтобы `GET /jobs/{job_id}` совпадал со счётом из ответа корня. |
| `mandates.credential_id`, уникальный индекс по `(issuer, credential_id)` | Один идентификатор credential на издателя. |
| `mandate_holds.pending_back_micro` | Возврат дочернему вызову, пришедший, пока резерв бюджета ещё открыт; его вычитает расчёт, который этот резерв закрывает. |

Она применяется при старте, как любая миграция хаба. 036 и 037 принадлежат другим веткам; версии —
это множество, а не последовательность, поэтому хаб может показывать 038 применённой раньше них.
Строки, записанные до 038, сохраняют пустой `credential_id` (уникальный индекс их пропускает) и
пустой `work_receipt_id` (их ребро `parents` называет узел как `urn:aimarket:job-node:…`; дайджест
по-прежнему закрепляет нужные байты).

Колонки µUSD миграций 034 и 035 имеют тип `BIGINT`. В SQLite это то же 64-битное целое, что и
раньше. У хаба на PostgreSQL, применившего 034/035, когда там стояло `INTEGER`, колонки int4 с
пределом $2,147.48, а применённая миграция повторно не выполняется: переведите
`mandate_usage.spent_micro`, `mandate_holds.amount_micro`, `job_nodes.amount_micro` и
`job_grants.allowance_micro` командой `ALTER TABLE … ALTER COLUMN … TYPE BIGINT`.

Каждый вызов, который хаб исполняет через эндпоинт поставщика, по завершении пишет одну строку
в `job_nodes` — был субподряд или нет.

### Якоря квитанций в HISTOR

Когда задан `AIMARKET_HISTOR_URL`, плагин provenance ставит дайджест каждой квитанции о работе в
очередь, а фоновый поток отправляет её в журнал квитанций HISTOR (что отправляется и как
повторяется — в [README плагина](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/README.md)). HISTOR принимает
якоря только от издателей, которых его оператор перечислил в `HISTOR_RECEIPT_ISSUERS`, поэтому
сообщите этому оператору `did:key` издателя квитанций своего хаба. Его можно прочитать с любой
живой квитанции — `provenance_receipt.issuer` в ответе на вызов или `issuer.id` в документе
квитанции:

```bash
curl -s "$HUB/ai-market/v2/p/provenance/receipt/$RECEIPT_ID" | jq -r '.issuer.id'
```

Плагин также пишет его в лог при старте (`Provenance issuing AWR/2 receipts as did:key:…`). Пока
HISTOR его не внёс, якоря отклоняются как "issuer is not accepted" и остаются в `pending`: хаб
повторяет их с нарастающей паузой до 30 дней, так что ничего не теряется, пока два оператора
договариваются.

`GET /ai-market/v2/p/provenance/anchor/{receipt_id}` показывает, где находится квитанция:
`pending` (с `attempts` и `last_error`), `anchored` (с `leaf_index` и `proof_url` в HISTOR),
`refused` (с `last_error`), `not_queued` или `not_configured`, если якорение выключено.

**После срока хранения отвечает журнал.** Строки `anchored` удаляются из outbox, когда они
старше `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` (по умолчанию 30; 0 — хранить всегда); строки
`pending` и `refused` не удаляются никогда. Для квитанции без строки маршрут спрашивает сам
HISTOR: доказательство с этим дайджестом под ключом этого хаба — `anchored` с `"source": "log"`;
нет в журнале — `not_queued`; журнал недоступен — `unknown`, но никогда не `anchored`. Ответы
запоминаются (час, пять минут, тридцать секунд), чтобы публичный маршрут нельзя было
использовать, чтобы заставить хаб долбить журнал.

**Квитанции, выданные до включения якорения.** Их ставят в очередь с их собственным временем
выдачи, а outbox работающего хаба отправляет их как обычные строки:

```bash
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db --dry-run
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db
```

В очередь попадают только квитанции, которые проходят проверку, выданы ключом provenance этого
хаба и моложе 30-дневного окна HISTOR (с запасом в час); без `AIMARKET_HISTOR_URL` команда не
запускается, так что хаб, который не якорит, ничего не публикует. Окно HISTOR существует, чтобы
нельзя было задним числом, поэтому квитанцию старше окна нельзя заякорить с её настоящим временем
— она остаётся как есть. Дозаякоренная квитанция доказывает, что она существовала к моменту
записи в HISTOR, а не в заявленное в ней время выдачи.

Трафик на `/a2a` и `/.well-known/agent-card.json` считается в
`aimarket_hub_a2a_requests_total{method,result}` на `/metrics`; задача вызова считается по
состоянию, которого она достигла (см. [a2a.md](a2a.md)).
