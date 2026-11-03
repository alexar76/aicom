# Mandatos, subcontratación y anclaje de recibos

> **English:** [mandates.md](./mandates.md) · **Русский:** [mandates.ru.md](./mandates.ru.md) · **Français:** [mandates.fr.md](./mandates.fr.md) · **中文:** [mandates.zh.md](./mandates.zh.md)
>
> Código: [`mandates.py`](../aimarket_hub/mandates.py) · [`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`anchoring.py`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/aimarket_provenance/anchoring.py)

El texto normativo es [`aimarket-protocol/mandates.md`](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)
(AMD/1 para los mandatos, SUB/1 para la subcontratación). Esta página explica cómo ponerlo en
marcha y usarlo en este hub.

## Para qué sirve cada pieza

| Pieza | Pregunta que responde | Código |
|---|---|---|
| **Mandato** | «¿Quién autorizó este gasto, hasta cuánto y en qué?» Un propietario firma límites para la clave de un agente; el hub los hace cumplir. El agente nunca tiene la API key del propietario. | `aimarket_hub/mandates.py` |
| **Subcontratación** | «Este proveedor le compró a otro proveedor mientras me atendía: ¿con el dinero de quién y dónde aparece en mi factura?» | `aimarket_hub/subcontract.py` |
| **Capa de financiación** | Decide quién paga y bajo qué límites antes de que corra la ruta de pago; liquida después lo que abrió. | `aimarket_hub/invoke_funding.py` |
| **Anclaje** | «¿Puede el hub negar más tarde un recibo o cambiarle la fecha?» El resumen criptográfico (digest) de cada recibo de trabajo entra en el registro público de recibos de HISTOR. | `plugins/aimarket-provenance/aimarket_provenance/anchoring.py` |

Las tres piezas que tocan dinero funcionan sobre el **rail de créditos (credits rail)**, el único
rail en el que el hub mide el dinero por sí mismo. Un mandato o una asignación nunca viajan junto
con un canal de pago, un pago x402 o un id de visitante del sandbox: el hub rechaza esa combinación
(`400 mandate_rail_unsupported`, o `403 job_invalid` para un grant) en lugar de hacer cumplir un
límite que no puede ver.

## Límites monetarios y frontera de vencimiento

- `perCall` limita lo reservado para una llamada, incluida la comisión de enrutamiento cuando corresponda. `perDay` usa un **día natural UTC**, no una ventana móvil de 24 horas; `total` es el presupuesto total opcional. Son límites monetarios, no contadores de solicitudes, y no existe un límite monetario horario incorporado.
- Un mandato y toda su cadena de ancestros solo son utilizables con `validFrom <= now < validUntil`. **Exactamente en `validUntil` ya ha caducado.** Se acaba la autorización de trabajo nuevo; no es una promesa de cancelar trabajo iniciado ni de reembolsar on-chain.
- Active `require_mandate=True` al vincular al propietario de la cuenta financiadora. Registrar un mandato por sí solo no impide que alguien con la API key original gaste fuera de él. El rate limit por IP/sesión no es un presupuesto monetario por clave.
- El saldo prepagado y la API key subyacentes no tienen TTL automático. La recuperación de reservas y la devolución interna de crédito siguen el [ciclo del crédito](credits-topup.es.md#credit-lifecycle); no son pagos de dinero ni garantías del contrato escrow.

## Propietario: financiar a un agente sin entregarle tu clave

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

Para que el agente pueda abrir asignaciones de subcontratación, añade `subcontract_allowance_usd=`
y `subcontract_max_depth=` (1–3) a `issue_mandate`; sin ellos, el mandato no puede pagar ninguna.

### Qué rechaza el registro

`POST /ai-market/v2/mandates` no necesita clave: el documento se autentica a sí mismo. El hub
comprueba las reglas de campos de la especificación (§3.2) y la prueba criptográfica, y luego
rechaza:

| Respuesta | Cuándo |
|---|---|
| `403 mandate_invalid` "this mandate is not addressed to …" | `audience` no contiene exactamente el `AIMARKET_HUB_URL` de este hub: esquema, host, puerto y ruta (un hub montado bajo `/hub` es `https://example.net/hub`), sin barra final. El hub nunca serviría ese mandato, así que no lo guarda. La cadena que hay que usar es `mandates.audience` en `/.well-known/ai-market.json`. |
| `402 mandate_unfunded` | El emisor raíz de la cadena no está vinculado a una cuenta en este hub (paso 1). |
| `403 mandate_invalid` "register the parent mandate first" | Una redelegación cuyo padre no está registrado aquí. |
| `403 mandate_invalid` "… already registered a different mandate with id …" | El emisor ya registró otro documento con el mismo `id`. Un id de credencial nombra un solo mandato por emisor; emite el nuevo con un `id` nuevo (`issue_mandate` genera un `urn:uuid:` salvo que pases `mandate_id=`). |
| `403 mandate_invalid` "the mandate has already expired" | `now >= validUntil` (la frontera final es exclusiva). Un mandato cuyo `validFrom` todavía no ha llegado se registra y se lee como `pending`. |
| `403 mandate_invalid` "numbers in a mandate must be integers" | Un número con decimales en cualquier parte, o un entero fuera de ±(2^53 − 1). Los importes son µUSD enteros. |
| `400 mandate_malformed` | El cuerpo no es un objeto JSON, no tiene forma canónica o su forma canónica supera 16 KiB. |
| `413 mandate_malformed` | El cuerpo en bruto supera 20 KiB. |

Volver a enviar un documento ya registrado devuelve la misma respuesta: el registro es idempotente
por digest (`status` indica `revoked` si se ha revocado desde entonces).

**La regla de las claves de proof.** El objeto `proof` debe llevar exactamente `@context`, `type`,
`cryptosuite`, `created`, `verificationMethod`, `proofPurpose` y `proofValue`, y `proof.@context`
debe ser igual al `@context` del documento. El motivo: el digest que nombra un mandato se calcula
sobre todo el documento asegurado, proof incluida, pero `eddsa-jcs-2022` resume la configuración
de la proof con el `@context` *del documento* en lugar del propio, así que `proof.@context` no
queda cubierto por la firma. Si quedara libre, el agente al que el mandato limita podría reescribir
el documento y registrar copia tras copia, cada una con un digest nuevo y contadores de límites
nuevos, sin que revocar el original tocara ninguna. `issue_mandate` y el firmante de ARGUS
producen exactamente esta forma. Un mandato registrado antes de la regla que la incumple se vuelve
a comprobar cada vez que el hub lo lee, y ahora aparece como `invalid`.

### Propietarios y `require_mandate`

Solo el **primer** propietario de una cuenta se vincula con la API key sola. A partir de ahí,
añadir un segundo DID, desvincular uno o cambiar `require_mandate` exige además la firma de un
propietario existente: lo que se filtra es la API key, así que no debe bastar para deshacer la
protección:

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

Cada una va con la `X-API-Key` de la cuenta. Un cambio sin firma válida de un propietario recibe
`403 owner_authorization_required`; un DID ya vinculado a otra cuenta recibe
`409 owner_linked_elsewhere`. `require_mandate` se guarda por cada DID vinculado, y la cuenta
queda bloqueada mientras **cualquiera** de sus DID lo tenga activo: desactivarlo exige un cambio de
política para cada uno de esos DID. `GET /ai-market/v2/mandates/owners` (con la API key) lista los
DID vinculados y su `require_mandate`. A un propietario que ha perdido todas sus claves lo recupera
el operador: la misma llamada con `Authorization: Bearer $AIMARKET_ADMIN_TOKEN` (y la API key)
sustituye a la firma del propietario.

Con `require_mandate` activo, la API key sola ya no mueve el saldo:

- una invocación normal recibe `402 mandate_required`, igual que una que pide una asignación de
  subcontratación sin mandato;
- una garantía financiada con créditos (`POST /ai-market/v2/supply/stake` con la API key y un
  `amount_usd` positivo) recibe `403`: una garantía no le pagaría a un ladrón, pero congelaría el
  saldo como colateral y lo expondría al slashing (recorte de la garantía).

Una llamada hija pagada con el grant de un trabajo no se ve afectada: su dinero se autorizó en la
llamada raíz.

### Revocación

Se revoca con `POST /ai-market/v2/mandates/revoke`, firmado por cualquier emisor de la cadena
(`revoke_payload(owner, hub_origin=HUB, digest=digest)`), o solo con `{"digest"}` y la `X-API-Key`
de la cuenta de financiación, como interruptor de emergencia. Revocar un mandato revoca todo lo
redelegado a partir de él. Las reservas ya tomadas se liquidan con normalidad.

### Aprobación del propietario por encima de un umbral

Añada `approvalAbove` (µUSD) a los `limits` de un mandato y cualquier llamada que cueste más
espera por usted en lugar de gastar ([especificación §5.6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)).
Las llamadas pequeñas siguen sin usted; una grande necesita su firma sobre **esa** llamada.

1. La llamada del agente por encima del umbral responde `402 approval_required` con un bloque
   `approval`: `approval_id`, `capability_id`, `amount_usd`, `max_usd` (el techo que usted
   aprueba; en una llamada enrutada incluye la comisión de enrutamiento), `body_sha256` (la
   petición exacta), `expires_at` (24 h) y `url`. No se reserva nada. Una llamada que otro
   límite del mandato (`perCall`, `perDay`, `total`, el límite diario de un producto) rechazaría
   de todos modos se rechaza al instante con `402 mandate_limit`: nunca se le pide firmar lo que
   no podría ejecutarse.
2. Lo pendiente: `GET /ai-market/v2/mandates/approvals?status=pending` con el `X-API-Key` de la
   cuenta que financia.
3. La respuesta: `POST /ai-market/v2/mandates/approvals/{approval_id}` con
   `{"decision": "approve", "by": <su DID>, "t", "n", "s"}`; `s` es su firma Ed25519 sobre las
   líneas `aimarket-mandate-approval/1`, la URL base del hub, `approval_id`, `approve`, el digest
   del mandato, `body_sha256`, `max_micro`, `t`, `n` (separadas por `\n`). Puede firmar cualquier
   DID propietario de la cuenta. La clave API sola solo puede **denegar** (`{"decision": "deny"}`).
4. El agente repite la misma petición con una prueba nueva. Se ejecuta una vez; la aprobación se
   gasta con ella, o vuelve si la llamada falla antes del cobro. Una denegación se mantiene hasta
   que la solicitud expira (`402 approval_denied`).

Un mandato puede tener como máximo 16 solicitudes esperando (`429 approval_queue_full`). Un
mandato redelegado conserva el umbral del padre y solo puede bajarlo. Por A2A la tarea espera
en `AUTH_REQUIRED` y avanza cuando usted responde, con una notificación push al webhook del agente.

### Avisos cuando una llamada le espera

Sin un canal, el propietario solo se entera de una solicitud si pregunta (paso 2). Registre
canales en la cuenta que financia y el hub enviará allí cada solicitud nueva y la respuesta a
ella. Un aviso solo informa: aprobar sigue exigiendo la firma de una clave del propietario, que
ningún chat, canal ni ticket tiene, y cada mensaje dice cómo aprobar y cómo denegar.

```bash
# Telegram con el bot del hub (si el operador lo tiene): pulse Start con él y dé el id de su chat
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "telegram", "chat_id": "123456789"}'
# … o con su propio bot: añada "bot_token": "123456789:AA…"
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "slack", "webhook_url": "https://hooks.slack.com/services/T…/B…/…"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "jira", "base_url": "https://acme.atlassian.net", "email": "ops@acme.example",
       "api_token": "…", "project_key": "OPS", "issue_type": "Task"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "webhook", "url": "https://ops.acme.example/hooks/aimarket", "secret": "…"}'
# enviar ahora un mensaje de prueba y ver qué respondió el canal
curl -X POST "$HUB/ai-market/v2/mandates/notify/<channel_id>/test" -H "X-API-Key: $KEY"
```

| `kind` | Qué indica usted | Qué llega |
|---|---|---|
| `telegram` | `chat_id` (un número, o `@canal` donde el bot es administrador). `bot_token` para su propio bot; sin él se usa el bot del hub, si el operador lo tiene (`GET …/notify` lo nombra en `telegram_bot`). | Un mensaje: qué capacidad, cuánto, el techo, hasta cuándo, cómo aprobar y cómo denegar. En HTML, o las mismas palabras en texto plano si Telegram rechaza el marcado. |
| `slack` | `webhook_url` de un webhook entrante (`https://hooks.slack.com/services/…` o `/triggers/…`). | El mismo texto. |
| `jira` | `base_url` de Jira Cloud (https), `email`, `api_token` (id.atlassian.com → Security → API tokens), `project_key`, `issue_type` (por defecto `Task`). | Una incidencia por solicitud; la respuesta se añade como comentario. |
| `webhook` | `url` (https), `secret` opcional. | `POST` de `{"event": "mandate.approval.requested" \| "….approved" \| "….denied", "approval": {…}, "title", "text"}` con `X-AIMarket-Event`; con secreto, también `X-AIMarket-Signature: t=<unix>,v1=<hex HMAC-SHA256 de "<t>.<body>">`. |

- `GET /ai-market/v2/mandates/notify` lista los canales de la cuenta con el resultado de la
  última entrega de cada uno. Los secretos —token del bot, URL de Slack, token de Jira, secreto
  del webhook— se guardan para usarse y nunca se devuelven (de la URL de Slack se ven los cuatro
  últimos caracteres).
- `POST …/notify/{channel_id}/test` envía al momento un mensaje de prueba y responde `delivered`
  y lo que dijo el canal; `DELETE …/notify/{channel_id}` elimina un canal. Hasta 8 por cuenta.
- Un canal pertenece a la cuenta que financia y se entera de cada mandato que esa cuenta
  financia. Los canales se gestionan con la clave API de la cuenta, que ya lista sus solicitudes pendientes.
- Cada dirección se comprueba como cualquier dirección que un llamante da a este hub: solo
  https, sin redes privadas ni de metadatos, resuelta una vez y fijada, sin redirecciones. La
  entrega va fuera de la petición, se reintenta dos veces (a los 2 s y 10 s) si no hay
  respuesta, hay un 5xx o un 429, y nunca cambia la solicitud de la que informa.

### Leer el estado de un mandato

`GET /ai-market/v2/mandates/{digest}` responde a cualquiera que tenga el digest (a uno
desconocido: `404 mandate_unknown`). `status` es el estado del mandato **como cadena**: una
redelegación cuyo padre fue revocado no se puede usar, por limpia que parezca su propia fila:

| `status` | Significado |
|---|---|
| `active` | Se puede usar ahora. |
| `revoked` | Él o un ancestro fue revocado. `revoked_at` solo figura en el mandato que se revocó directamente; un descendiente muestra `revoked_at: null` y el motivo en `status_reason`. |
| `expired` | Él o un ancestro ha superado su `validUntil`. |
| `pending` | Él o un ancestro todavía no es válido (`validFrom` está por llegar). |
| `invalid` | La cadena no se sostiene: falta un ancestro, un eslabón incumple las reglas de estrechamiento o el documento guardado ya no pasa las reglas de campos. |

Los demás campos son `issuer`, `subject`, `parent`, `root`, `chain` (los digests, de la raíz a la
hoja), `depth` (0 para una raíz), `valid_from`, `valid_until`, `revoked_at`, y `status_reason`
siempre que el estado no sea `active`.

El uso —`usage`: `day`, `spent_today_usd`, `per_day_usd`, `remaining_today_usd`,
`spent_total_usd`, más `total_usd` y `remaining_total_usd` cuando el mandato tiene un límite
`total`— se añade para dos clases de llamante:

- la cuenta de financiación de la raíz, con su `X-API-Key`;
- cualquier clave de la cadena —cada emisor y cada sujeto, para que un propietario pueda vigilar
  a un agente al que redelegó— con una prueba de la petición (request proof) sobre `GET`, un cuerpo
  vacío y la ruta de la petición:

```python
from aimarket_agent import request_proof

digest = reg["digest"]
path = f"/ai-market/v2/mandates/{digest}"
proof = request_proof(owner, hub_origin=HUB, leaf_digest=digest, body=b"", method="GET", path=path)
httpx.get(f"{HUB}{path}", headers={"X-AIMarket-Mandate-Proof": proof}).json()["usage"]
```

Una prueba que no verifica recibe `401 mandate_proof_invalid` en lugar del estado. El gasto se
registra contra cada mandato de la cadena, así que las cifras de un padre incluyen lo que gastaron
sus redelegaciones. `day` es el día natural UTC que cubre el contador diario.

## Agente: pagar con el mandato

```python
from aimarket_agent import AIMarketAgent, Mandate

client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent, hub_origin=HUB))
r = client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
r["mandate"]    # {"digest", "agent", "principal", "depth"} on a delivered call
```

Cada llamada se firma sobre su cuerpo exacto, el hub, el método y la ruta, y un nonce de un solo
uso, dentro de 300 segundos del reloj del hub. La ruta es **relativa a la URL base del hub**: para
un hub publicado en `https://example.net/hub`, un POST a `https://example.net/hub/ai-market/v2/invoke`
firma `POST /ai-market/v2/invoke`, y `hub_origin` es `https://example.net/hub`. `Mandate` firma esa
ruta por defecto.

Qué vuelve cuando el hub dice que no:

- por encima de un límite: `402 mandate_limit`, con `limit` indicando cuál (`perCall`, `perDay`,
  `total`, `perProductPerDay`, o `subcontract.perCallAllowance` para una asignación) y `mandate`
  indicando el mandato de la cadena que rechazó. `perCall` cubre todo lo que reserva una llamada:
  en una llamada federada, su precio y la comisión de enrutamiento juntos. El producto que cuenta
  un límite por producto es el que el hub ejecuta, sea cual sea el `product_id` que escribió el
  llamante;
- fuera del alcance (scope): `403 mandate_scope`; desconocido, caducado, revocado o no dirigido a
  este hub: `403 mandate_invalid`; firma incorrecta, `t` caducado o nonce reutilizado:
  `401 mandate_proof_invalid`; una cuenta que solo paga bajo mandato, alcanzada sin él:
  `402 mandate_required`.

El SDK devuelve un rechazo 403 de mandato o de trabajo como
`{"refused": True, "error": …, "detail": …}`, no como `safety_blocked`, que queda reservado para la
puerta de seguridad de contenido. Un 402, 401 o 400 vuelve como el cuerpo del hub (`error`,
`detail` y, cuando están, `limit` / `mandate`).

El proveedor que ejecuta el hub recibe `X-AIMarket-Agent` (el sujeto de la hoja) y
`X-AIMarket-Principal` (el emisor raíz) —quién llama, avalado por el hub— y nada sobre la cuenta ni
los límites. Ninguna de las dos cabeceras se envía en una llamada enrutada a un hub peer: el peer
no verificó el mandato.

El mismo mandato paga por A2A (`POST /a2a`, [a2a.md](a2a.md)): las cabeceras viajan en la petición
A2A y la invocación va en una sola parte `application/json` en bruto con los bytes exactos que
firma la prueba, todavía para `POST /ai-market/v2/invoke`. Un límite alcanzado es una tarea
`REJECTED`. Volver a leer tus tareas (`GetTask`, `ListTasks`) exige una prueba nueva sobre
`POST /a2a` y el cuerpo JSON-RPC. `aimarket_agent.A2AClient(HUB, mandate=…)` y `argus a2a invoke`
de ARGUS hacen ambas cosas.

**ARGUS** paga de la misma manera. `argus mandate keygen` imprime un `did:key` de agente nuevo y
su secreto; el propietario emite un mandato para ese DID y lo registra; `ARGUS_AGENT_KEY` (el
secreto) y `ARGUS_MANDATE_FILE` (el JSON del mandato) hacen que ARGUS lo use.
`argus mandate status` muestra el estado de la cadena y el gasto, y
`argus mandate delegate --to <did:key> --per-call <usd> --per-day <usd>` registra una
redelegación más estrecha para un subagente.

## Proveedor: contratar a otro proveedor dentro de un trabajo

> La guía completa —los diagramas del flujo y del dinero, dónde está el dinero en cada paso,
> quién asume qué riesgo, las llamadas hijas en otros hubs, A2A, los errores y las notas para el
> operador— está en [subcontracting.es.md](subcontracting.es.md). Esta sección es la versión corta.

Cada proveedor que este hub ejecuta a través de su URL de invocación recibe `X-AIMarket-Job` (un
token firmado con la clave que el hub publica como `signer_public_key` en su well-known, válido 60
segundos) y `X-AIMarket-Hub` (dónde presentarlo), más `X-AIMarket-Job-Grant` cuando el comprador
reservó una asignación para subcontratas (allowance): el grant, el secreto que autoriza a gastar
de esa asignación. Devuélvelos en todo lo que compres mientras atiendes la llamada:

```python
from aimarket_agent import AIMarketAgent, JobContext

job = JobContext.from_headers(request.headers)       # None when the hub sent no token
buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
r = buyer.invoke_single("wx", "wx.read@v1", {"q": 1}, job=job)
r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

- Con un grant (**cost-plus**) la compra se paga con la asignación del comprador y no se puede
  enviar nada más con ella: ni `X-API-Key`, ni mandato, ni canal, ni pago x402
  (`403 job_invalid`); el SDK no añade su propio pago cuando el trabajo trae un grant. Toda cifra
  de saldo en la respuesta es lo que queda de la asignación, nunca el saldo del comprador.
- Sin él (**precio fijo**) pagas con tu propio rail; la compra aparece igualmente en el árbol del
  trabajo del comprador.

### Qué rechaza el hub dentro de un trabajo

| Respuesta | Cuándo |
|---|---|
| `403 job_invalid` | El token no es de este hub o ha caducado, o la llamada para la que se emitió ya ha vuelto: un proveedor que conserva un token más allá de su llamada no puede injertar compras en un trabajo cuya factura y recibo ya se entregaron. |
| `402 allowance_exhausted` | El grant está cerrado —se cierra en el momento en que vuelve la llamada raíz— o lo que queda no cubre el precio. |
| `403 job_limit` | `limit` dice cuál: `depth` (más profundo de lo que permite el trabajo), `cycle` (la capability ya está en la ruta), `nodes` (el trabajo ya tiene 64 llamadas, contando la raíz), `children` (el nodo que llama ya tiene 16 hijos). |
| `403 mandate_scope` | Una compra financiada por el grant fuera del alcance del mandato raíz. |
| `400 subcontract_unsupported` | Una llamada dentro de un trabajo pide su propia asignación; solo la raíz la fija. |

La profundidad que permite un trabajo: sin asignación (solo vinculación) es el máximo del hub, 3;
cada salto paga por sí mismo, así que la profundidad solo limita el tamaño del árbol. Con
asignación es el `max_depth` del comprador. Una llamada hija rechazada después de entrar en el
árbol —fuera del alcance del mandato raíz, por ejemplo, o con el mandato raíz revocado entretanto—
devuelve sus plazas y aparece en el árbol como `refused`.

### El lado del comprador: una asignación y la factura

El comprador pide una asignación en la llamada raíz:

```python
r = client.invoke_single("brief", "brief.make@v1", {...},
                         subcontract={"allowance_usd": 0.005, "max_depth": 2})
```

`allowance_usd` debe ser mayor que 0 y como mucho `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`;
`max_depth` va de 1 a 3 (1 por defecto). El hub reserva juntos el precio y la asignación en la
cuenta de crédito del comprador y, en una llamada con mandato, contra la cadena del mandato, cuya
hoja debe llevar un bloque `subcontract` que acote ambos. Una asignación en una llamada que paga
on-chain o por un canal, que no lleva ni `X-API-Key` ni mandato, o que se enruta a un peer recibe
`400 subcontract_unsupported`: el hub solo puede hacer pasar el dinero que él mismo mide.

La respuesta raíz lleva el bill of materials (lista de materiales):

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

- `nodes` son las llamadas subcontratadas; la raíz misma no aparece. `status` es `running`,
  `captured`, `failed` o `refused`; `funded_by` es `allowance` u `own`. `receipt_id` y
  `receipt_digest` nombran el recibo de trabajo AWR/2 de la llamada hija.
- El `price_usd` de un nodo financiado por la asignación es lo que esa llamada tomó realmente de la
  asignación (véanse [las reglas de abajo](#reglas-fáciles-de-pasar-por-alto));
  `spent_from_allowance_usd` es su suma.
- `allowance_usd`, `spent_usd` y `released_usd` solo aparecen cuando se fijó una asignación.
  `spent_usd` y `released_usd` son lo que liquidó el libro contable; valen `null` mientras la
  liquidación sigue pendiente (una liberación que falló y que el barrido reintenta; véase
  [Asignaciones varadas](#asignaciones-varadas)). `null` no significa que no se gastara nada.
- El bloque está en la respuesta de la raíz **haya entregado o no la raíz**. Una subcontrata que
  entregó cobra aunque el proveedor que la contrató falle después (cost-plus: los materiales
  consumidos se pagan), así que una raíz que falla sigue devolviendo la factura y el `job_id` que
  explican el cargo.
- Cada llamada que el hub ejecuta a través del endpoint de un proveedor recibe un id de trabajo,
  así que su respuesta lleva un bloque `subcontracting` aunque no se haya subcontratado nada
  (`"nodes": []`).

`GET /ai-market/v2/jobs/{job_id}` devuelve el árbol más tarde: los mismos nodos más el de la raíz
(`depth` 0), `spent_from_allowance_usd` y, con asignación, `allowance_usd`, `max_depth`,
`allowance_status`, y `spent_usd` / `released_usd` una vez registrada la liquidación. El id del
trabajo es una capability imposible de adivinar: quien lo tenga puede leer el árbol, y el hub solo
se lo da al comprador raíz y a los proveedores del trabajo.

El recibo de trabajo AWR/2 de la raíz enumera el recibo de trabajo de cada hija que entregó en
`credentialSubject.parents`: `id` es el `receipt_id` de la hija y `digestSRI` su `receipt_digest`.
El recibo de cada hija hace lo mismo con sus propias hijas, así que el árbol queda comprometido
salto a salto, no solo descrito.

Límites que el hub hace cumplir pida lo que pida el comprador: profundidad ≤ 3, 64 llamadas por
trabajo contando la raíz, 16 hijos por llamada, sin ciclos (una capability que ya está en la ruta),
un token que vive 60 segundos (el tiempo de espera de 30 segundos del proveedor más 30) y un grant
que muere con su llamada raíz.

### Reglas fáciles de pasar por alto

- **Una hija en otro hub necesita `source_hub`.** Solo la raíz debe ejecutarse en este hub; una
  hija puede ser cualquier capability que este hub enrute, y su precio (y, para un peer
  revendido, la comisión de enrutamiento) se descuenta de la asignación igual que uno local. Pero
  sin `source_hub: <la URL del peer que devuelve /search>` el hub busca una capability local,
  encuentra solo el listing del peer y responde `400`; el intento ocupa igualmente una de las 16
  plazas de hijos de la llamada y aparece en la factura como un nodo fallido.
- **El token del trabajo y el grant nunca salen de este hub.** Una hija enrutada llega al peer sin
  ninguno de los dos; la vinculación y el dinero se quedan donde el hub puede medirlos.
- **Verifica el token antes de gastar.** Tu URL de invocación es pública. Comprueba la firma con
  la `signer_public_key` del hub (de `/.well-known/ai-market.json`), que `iss` sea el hub al que
  sirves, `exp`, que la última entrada de `path` sea *tu* capability (el hub entrega un token a
  cada proveedor que ejecuta; esto impide que otro proveedor te reenvíe el suyo) y atiende cada
  `node` una sola vez. Rechaza todo lo demás antes de comprar nada.
- **`max_price_usd` en una hija enrutada se compara en centavos enteros.** El hub cotiza una
  capability enrutada como su precio más la comisión de enrutamiento redondeados al centavo hacia
  arriba, así que un tope por debajo de $0.01 rechaza una hija de $0.001 con
  `409 price_limit_exceeded`.
- **La factura cuadra.** El `price_usd` de un nodo financiado por la asignación es lo que esa
  llamada tomó de la asignación, comisión de enrutamiento incluida, así que esos nodos suman
  `spent_usd`, y `spent_usd + released_usd == allowance_usd`. Un nodo fallido cuya reserva se
  liberó muestra 0; uno que aun así costó dinero (el peer entregó y luego falló el cobro de la
  comisión) muestra lo que se tomó.

### Ejemplo resuelto: `weather.witness@v1`

[`examples/subcontract-capability`](../examples/subcontract-capability/) es un proveedor real
construido con estas reglas y operado por el operador del hub. Para un lugar compra
`gaia.weather.read@v1` y `gaia.air.read@v1` (producto `gaia.gateway`,
`source_hub: https://iot.modelmarket.dev`) a través del hub que lo llamó, dentro del trabajo del
llamante, y responde con ambas lecturas atestadas por los dispositivos, si coinciden en lugar y
momento, y el nodo del trabajo y el digest del recibo de cada hija, firmado sobre la forma canónica
del hub ligada a la petición. Cost-plus cuando el comprador envía una asignación (token + grant,
nada más); precio fijo en otro caso (token + su propia `X-API-Key`, bajo un tope diario, y sin clave
se niega).

[`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py) es el comprador raíz:

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py            # cost-plus, allowance $0.01
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a      # the root call over A2A 1.0
```

Comprueba dos hijas cobradas con la financiación esperada, `spent + released == allowance`,
precios de nodo que suman lo gastado, el mismo árbol desde `GET /ai-market/v2/jobs/{job_id}` y los
digests de los recibos de las hijas en `credentialSubject.parents` del recibo raíz.

Hay que ser claros sobre lo que demuestra: es **autoimpulsado**, con nuestro comprador, nuestro
servicio compuesto, nuestra GAIA y créditos internos. Cada salto recorre la ruta de código de
producción y cada afirmación se comprueba desde fuera, que es para lo que sirve; no es prueba de
que alguien más quiera el producto. El README del ejemplo tiene el manual del operador (systemd,
nginx, la exención de garantía, la publicación, una cuenta canario).
`tests/test_subcontract_example.py` ejecuta el proveedor y el canario contra la aplicación real del
hub.

## Operador

### Configuración

| Variable | Por defecto | Efecto |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | Los mandatos y las asignaciones necesitan el rail de créditos activo; si está apagado, una llamada con mandato o con asignación recibe `503 mandates_unavailable`. Los tokens de trabajo (vinculación) funcionan en ambos casos. |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | La URL base pública del hub, con la ruta incluida si el hub está montado bajo una. Es la audiencia que un mandato debe nombrar y el origen que firma cada prueba, así que un hub que se queda en el valor por defecto rechaza todo mandato dirigido a su nombre público. |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | La mayor asignación de paso que puede reservar una llamada raíz. |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | Cada cuánto se barren las asignaciones varadas (abajo). `0` apaga el barrido; un valor por debajo de 10 se sube a 10. |
| `AIMARKET_ADMIN_TOKEN` | sin definir | `Authorization: Bearer …` con él sustituye a la firma de un propietario en los cambios de propietarios: la vía de recuperación. |
| `AIMARKET_HISTOR_URL` | sin definir | Dónde ancla el plugin de provenance los digests de los recibos; sin definir = anclaje apagado. |
| `AIMARKET_HISTOR_FLUSH_S` | `30` | Cada cuánto la bandeja de salida (outbox) envía las anclas pendientes (el intervalo crece hasta 10 min mientras HISTOR falla o aplaza). |
| `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` | `30` | Días que una fila anclada queda en el outbox; después la ruta de estado pregunta a HISTOR. `0` las conserva todas. |
| `AIMARKET_MANDATE_APPROVAL_TTL_S` | `86400` | Cuánto queda abierta una solicitud de aprobación del propietario (300 s – 7 días); una aprobada se usa en la misma ventana. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN` (o `…_FILE`) | sin definir | El bot de Telegram propio del hub para los avisos de aprobación: al propietario le basta el id del chat. Sin él, un canal de Telegram necesita el `bot_token` del propietario. Nunca se registra en el log. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_NAME` | sin definir | El @nombre de ese bot, que `GET /mandates/notify` muestra para que el propietario sepa con quién pulsar Start. |

La imagen ya instala `awr` (lo necesita el plugin de provenance). Un hub instalado sin él arranca
con normalidad y responde `503 mandates_unavailable` a las llamadas con mandato.

Los clientes firman las rutas de las peticiones relativas a `AIMARKET_HUB_URL`; antes de comprobar
una prueba, el hub quita el prefijo de montaje que el servidor ASGI indica como `root_path`.

### Los bloques del well-known

`/.well-known/ai-market.json` le dice a un cliente, antes de que envíe nada, si este hub hace
cumplir AMD/1 y SUB/1 y con qué límites:

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

`mandates.enabled` y `subcontracting.allowance` siguen a `AIMARKET_CREDITS_ENABLED`;
`mandates.audience` es `AIMARKET_HUB_URL` sin barra final, la cadena exacta que debe contener la
`audience` de un mandato; `max_allowance_usd` sigue a `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`.

### Asignaciones varadas

Una asignación es una reserva de crédito en la cuenta del comprador que debería vivir exactamente
lo que su llamada raíz. Si la raíz nunca la liquidó —una caída a mitad de llamada, una liberación
que seguía fallando— el dinero se quedaría congelado. El hub hace un barrido al arrancar y después
cada `AIMARKET_SUBCONTRACT_SWEEP_S` segundos: una asignación cuyo grant caducó hace más de cinco
minutos y cuya reserva sigue retenida se cierra, lo que queda se libera, la reserva de una
asignación con mandato se liquida a lo que tomaron las hijas y la liquidación se registra, de modo
que se rellenan `spent_usd` / `released_usd` del trabajo. Hasta 50 asignaciones por ciclo; cuando
liquida alguna, registra `subcontract: settled N stale allowance(s)` con nivel WARNING. El barrido
solo corre con el rail de créditos activo, y nunca en la ruta de la petición.

### Migración 038

`038_job_receipts_and_settlement` añade:

| Columna | Para qué |
|---|---|
| `job_nodes.work_receipt_id` | El id del recibo de trabajo de la hija, que llevan la arista `parents` del recibo padre y el `receipt_id` de la factura. |
| `job_grants.spent_micro`, `released_micro`, `settled_at` | Cómo se liquidó la asignación, para que `GET /jobs/{job_id}` coincida con la factura que llevó la respuesta raíz. |
| `mandates.credential_id`, índice único sobre `(issuer, credential_id)` | Un id de credencial por emisor. |
| `mandate_holds.pending_back_micro` | Una devolución a una hija que llega mientras la reserva de la asignación sigue abierta; la resta la liquidación que la cierra. |

Se aplica al arrancar, como toda migración del hub. 036 y 037 pertenecen a otras ramas; las
versiones son un conjunto, no una secuencia, así que un hub puede mostrar 038 aplicada antes que
ellas. Las filas escritas antes de 038 conservan un `credential_id` vacío (el índice único las
omite) y un `work_receipt_id` vacío (su arista `parents` nombra el nodo como
`urn:aimarket:job-node:…`; el digest sigue comprometiendo los bytes correctos).

Las columnas µUSD de 034 y 035 son `BIGINT`. En SQLite es el mismo entero de 64 bits que antes. Un
hub PostgreSQL que aplicó 034/035 cuando decían `INTEGER` tiene columnas int4, cuyo tope es
$2,147.48, y una migración aplicada no se vuelve a ejecutar: cambia `mandate_usage.spent_micro`,
`mandate_holds.amount_micro`, `job_nodes.amount_micro` y `job_grants.allowance_micro` con
`ALTER TABLE … ALTER COLUMN … TYPE BIGINT`.

Cada llamada que el hub ejecuta a través del endpoint de un proveedor escribe una fila en
`job_nodes` al terminar, haya subcontratado o no.

### Anclar recibos en HISTOR

Con `AIMARKET_HISTOR_URL` definida, el plugin de provenance encola el digest de cada recibo de
trabajo y un hilo en segundo plano envía la cola al registro de recibos de HISTOR (qué se envía y
cómo se reintenta: [el README del plugin](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/README.md)). HISTOR solo
acepta anclas de los emisores que su operador lista en `HISTOR_RECEIPT_ISSUERS`, así que dale a ese
operador el `did:key` emisor de recibos de este hub. Se lee en cualquier recibo real:
`provenance_receipt.issuer` en la respuesta de una invocación, o `issuer.id` en el documento del
recibo:

```bash
curl -s "$HUB/ai-market/v2/p/provenance/receipt/$RECEIPT_ID" | jq -r '.issuer.id'
```

El plugin también lo registra al arrancar (`Provenance issuing AWR/2 receipts as did:key:…`).
Hasta que HISTOR lo liste, las anclas se rechazan con "issuer is not accepted" y siguen en
`pending`: el hub las reintenta con espera creciente durante un máximo de 30 días, así que no se
pierde nada mientras los dos operadores se ponen al día.

`GET /ai-market/v2/p/provenance/anchor/{receipt_id}` muestra en qué punto está un recibo:
`pending` (con `attempts` y `last_error`), `anchored` (con `leaf_index` y un `proof_url` hacia
HISTOR), `refused` (con `last_error`), `not_queued`, o `not_configured` cuando el anclaje está
apagado.

**Pasada la retención, responde el registro.** Las filas `anchored` salen del outbox cuando
superan `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` (30 por defecto; 0 las conserva); las filas
`pending` y `refused` nunca se borran. Para un recibo sin fila la ruta pregunta al propio
HISTOR: una prueba que nombra este digest bajo la clave de este hub se lee `anchored` con
`"source": "log"`; si no está en el registro, `not_queued`; si no se puede consultar, `unknown`,
nunca `anchored`. Las respuestas se recuerdan (una hora, cinco minutos, treinta segundos) para que
la ruta pública no pueda hacer que el hub bombardee el registro.

**Recibos emitidos antes de activar el anclaje.** Se encolan con su propia hora de emisión y el
outbox del hub en marcha los envía como cualquier otra fila:

```bash
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db --dry-run
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db
```

Solo encola recibos que verifican, emitidos por la clave de procedencia de este hub y más
recientes que la ventana de 30 días de HISTOR (con una hora de margen); se niega a ejecutarse sin
`AIMARKET_HISTOR_URL`, así que un hub que no ancla no publica nada. La ventana de HISTOR existe
para impedir fechar hacia atrás, de modo que un recibo más antiguo no puede anclarse con su hora
real y se deja como está. Un anclaje retroactivo prueba que el recibo existía cuando HISTOR lo
registró, no en la hora de emisión que el recibo declara.

El tráfico en `/a2a` y `/.well-known/agent-card.json` se cuenta en
`aimarket_hub_a2a_requests_total{method,result}` en `/metrics`; una tarea de invocación se cuenta
por el estado al que llegó (véase [a2a.md](a2a.md)).
