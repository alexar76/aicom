# Su propio hub

<!-- sensor-operator-guide -->
> ¿Tienes una estación meteorológica o un sensor de calidad del aire? [Vende las lecturas con tu propio Hub + GAIA](https://github.com/alexar76/aicom/blob/main/docs/sensor-operator.es.md).
<!-- /sensor-operator-guide -->

[English](operator-quickstart.md) · [Русский](operator-quickstart.ru.md) · [Español](operator-quickstart.es.md) · [Français](operator-quickstart.fr.md) · [中文](operator-quickstart.zh.md)

> La terminología sigue el [glosario de localización](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md) canónico. Los nombres de productos, identificadores de protocolo, URL, comandos de CLI y variables de entorno nunca se traducen.

Lo ha clonado o instalado, y la pregunta justa es qué obtiene a cambio. Esta página es el
camino completo, en orden: un hub en su máquina en un minuto, su propia API en él, una
dirección pública, una comprobación que le dice de antemano si otros hubs lo admitirán y la
llamada a la puerta. Nada de ello requiere cadena, contrato ni cuenta con nadie.

## 1. Un minuto, en su máquina

```bash
pip install "aimarket-hub[pqc]"       # Python 3.11+. O con uv: uvx --from "aimarket-hub[pqc]" aimarket …
aimarket quickstart --name "My hub"
aimarket serve                        # → http://localhost:9083
```

`quickstart` hace lo que un hub recién instalado no puede hacer solo, y puede ejecutarse de nuevo
sin riesgo:

1. **Guarda la configuración del hub** en `data/aimarket.env`, junto a la base de datos y las
   claves: el raíl de créditos activado, la confianza en los publicadores evaluada por este hub
   (`AIMARKET_ORACLE_FAMILY_URL=off`), la firma poscuántica híbrida, el nombre y un **token de
   administrador** generado. Cada comando `aimarket` lee ese archivo, así que `serve` desde una
   terminal nueva arranca con la misma configuración. El archivo es `0600`: haga copia de
   seguridad junto con las claves. Una variable del entorno (systemd, `docker run -e`, `export`)
   siempre prevalece sobre él.
2. **Publica dos capacidades que son realmente suyas y que realmente se ejecutan**, sin
   proveedor, modelo ni red: `hub.ping@v1`, **gratuita**, que responde con un recibo firmado por
   su hub — es lo que ejecuta el sandbox de admisión de otro hub — y `hub.hello@v1`, de pago, por
   la que paga un comprador.
3. **Emite una clave de comprador** con un pequeño saldo e imprime los curl de una venta completa.

Con Docker — desde un clon de [este repositorio](https://github.com/alexar76/aimarket-hub):

```bash
docker compose run --rm hub quickstart --name "My hub"
docker compose up -d                  # → http://127.0.0.1:9083
```

La configuración, las claves y la base de datos viven en el volumen `hub_data`. Cada comando de
abajo funciona igual como `docker compose run --rm hub <comando>`.

## 2. Su propia API

```bash
aimarket add weather.now@v1 --url https://api.example.com/weather \
  --price 0.002 --pay-to 0xYourWallet --description "Current weather for a city"
```

El hub envía un POST `{"input": …, "product_id": …, "capability_id": …}` a su URL y espera `200`
con un objeto JSON (o `{"result": …}`). La búsqueda, MCP, A2A, la oferta x402 y el recibo
firmado los pone el hub. `--pay-to` es la cartera a la que el comprador paga en USDC,
directamente al vendedor: el hub nunca custodia ese dinero ni se queda nada. Sin `--pay-to`, una
oferta de pago solo puede pagarse desde cuentas de crédito de su propio hub, que un comprador
enrutado desde otro hub no tiene.

`add` escribe en su propia base de datos, así que no hay depósito de publicador que pagarse a sí
mismo; los extraños que publican en su hub pasan por la puerta con controles descrita
[más abajo](#dejar-que-otros-publiquen-en-su-hub). En modo producción (`AIFACTORY_PROD=1`) cada
respuesta del proveedor debe ir firmada: pase `--provider-pubkey` y vea la firma en
[`examples/hello-capability/server.py`](../examples/hello-capability/server.py). Todas las
opciones: `aimarket add --help`.

## 3. Una dirección pública

Otros hubs solo admiten una dirección `https` que puedan alcanzar. Elija una:

- **Un VPS y un dominio.** Apunte el nombre al servidor y ponga cualquier proxy TLS delante de
  `127.0.0.1:9083`. Con [Caddy](https://caddyserver.com/) toda la configuración es:

  ```
  hub.example.com {
      reverse_proxy 127.0.0.1:9083
  }
  ```

- **Una plataforma con volumen persistente** — Railway, Render o Fly le dan un nombre `https`
  sin dominio propio. Monte el volumen en `/app/data`: claves, base de datos y configuración son
  la identidad de su hub, y un redespliegue sin ellos es otro hub. Archivos y pasos:
  [ejecutar en una plataforma](run-on-a-platform.es.md).
- **La instalación de producción completa** — systemd, nginx, copias de seguridad,
  monitorización: [despliegue en producción](production-deployment.es.md).

Después dígale al hub su dirección. Va dentro de cada documento que el hub firma:

```bash
aimarket quickstart --url https://hub.example.com   # actualiza la configuración guardada; conserva el token y las claves
```

## 4. Compruebe antes de llamar

```bash
aimarket doctor
```

`doctor` ejecuta contra su dirección pública el mismo assay de admisión que otros hubs le
ejecutan a usted, y dice qué corregir en cada comprobación fallida. Sobre una dirección local
lo comprueba todo salvo la alcanzabilidad y le dice el veredicto que obtendrá cuando el hub sea
público. El veto LLM no se consulta aquí; un hub que lo use aún puede rechazarle.

## 5. La llamada

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url": "https://hub.example.com", "hub_name": "My hub"}'
```

La respuesta incluye `assay_url`, donde lee el veredicto. El hub receptor ejecuta su
`hub.ping@v1` gratuita; la prueba es un recibo firmado. Un `pass` en un hub con admisión
automática pone sus propias capacidades en su catálogo, su búsqueda y su enrutamiento, y su hub
en su mapa; modelmarket.dev admite automáticamente. Su hub lee la federación desde el primer
arranque, a partir de las semillas incluidas en el repositorio. Todo el camino de admisión:
[unirse a la federación](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.es.md).

## 6. Lo que gana, con honestidad

- **Su propia API:** cada venta se paga a su cartera, directamente al vendedor. El hub no se
  queda nada.
- **Intermediación:** `AIMARKET_ROUTING_FEE_BPS` (1 % por defecto) cuando su hub enruta la venta
  de una capacidad de otro hub por el raíl de créditos. Una venta que el comprador paga al
  vendedor directamente por x402 no lleva tarifa.
- **Ventas de otros:** una comisión sobre los vendedores que publican en su hub — sección 7.
- **Demanda:** el tráfico de compradores en la federación todavía es pequeño. Los contadores en
  vivo son públicos (`https://verify.modelmarket.dev/demand.json`); léalos antes de contar con
  nada. Un hub cuesta lo que un VPS pequeño y se amortiza primero como escaparate de su propia
  API: MCP, x402, A2A y recibos firmados con un solo comando.

## 7. Un marketplace propio

Un hub también es un escaparate para servicios de otros: un catálogo de nicho con su nombre
(un sector, un idioma, una región), con el catálogo de la federación detrás desde el primer día.

- **Su marca.** `AIMARKET_HUB_NAME` y `AIMARKET_HUB_URL` firman cada página; un despliegue que
  no es el de referencia no muestra enlaces a sitios de otros.
- **Los vendedores se publican solos.** Una cuenta de crédito es una identidad de publicador:
  el vendedor emite una clave, deposita la garantía desde su saldo y publica — vea
  [dejar que otros publiquen](#dejar-que-otros-publiquen-en-su-hub). La garantía la fija usted
  con `AIMARKET_SUPPLY_MIN_STAKE_USD`.
- **Su comisión.** En una venta pagada desde una cuenta de crédito, `AIMARKET_PUBLISHER_SHARE_BPS`
  (70 % por defecto) va al saldo del vendedor y el resto es suyo; enrutar la venta de una
  capability de otro hub añade `AIMARKET_ROUTING_FEE_BPS`. Un vendedor que publica con su
  propia cartera cobra directamente por x402 y usted no se queda nada de esa venta: esa puerta
  sigue siendo suya.
- **Los compradores recargan en USDC** a una cartera suya ([recarga de créditos](credits-topup.es.md)),
  o usted les acredita tras cualquier pago que cobre por su cuenta.

Lo que queda a su cargo, no del software:

- Un saldo es dinero de su cliente en su contabilidad (`stats/live` → `outstanding_credit_usd`),
  y la parte ganada por un vendedor también es un saldo. Pagar a un vendedor es una
  transferencia que hace usted: el hub no envía valor.
- Condiciones, reembolsos, impuestos y lo que su jurisdicción exija a quien guarda saldos
  prepagados o vende por cuenta de otros los resuelve usted. El código no toma posición.

## Firmas poscuánticas desde el primer arranque

Lo poscuántico tiene dos mitades, y hacen cosas distintas:

- **`[pqc]` permite que el hub vea a sus pares.** Instala el verificador ML-DSA-65. La
  comprobación de una firma poscuántica falla cerrada, así que un hub sin él nunca indexa a un
  par que firma de forma híbrida, y todos los hubs de AIMarket lo hacen.
- **`AIMARKET_PQC=1` hace que el hub firme de forma híbrida** (quickstart lo guarda para un hub nuevo). Su manifiesto, su documento de
  descubrimiento y sus recibos llevan una firma ML-DSA-65 junto a la Ed25519, y los pares fijan
  su clave poscuántica la primera vez que la ven.

La clave poscuántica es un segundo archivo junto a la clásica:
`<AIMARKET_SIGNING_KEY_PATH>_mldsa`, por defecto `data/hub_signing_key_mldsa`. Haga copia de
seguridad de ambas a la vez y manténgalas en un mismo volumen. Si pierde el archivo ML-DSA, cada
par que lo haya fijado rechaza su hub hasta que lo vuelva a fijar
(`POST /federation/peers/repin`). Contexto:
[migración poscuántica](https://github.com/alexar76/aicom/blob/main/docs/pqc-migration.es.md).

## Cómo le pagan

Hay dos rieles y puede usar uno o los dos.

| | Créditos (`X-API-Key`) | Canales (`X-Payment-Channel`) |
|---|---|---|
| Configuración | una variable de entorno | contrato de depósito en garantía (escrow) que usted despliega en Base + 5 ajustes previos |
| Importe mínimo facturable | $0.00001 | $0.01 (céntimos enteros, redondeando hacia arriba) |
| Quién tiene el dinero | usted, prepago | usted, prepago (depósito on-chain) |
| Qué necesita el comprador | un cliente HTTP | una cartera con fondos y una firma typed data |

**Créditos** es el riel que funciona con `AIFACTORY_CRYPTO_ENABLED=0`, que es el valor por
defecto. Al activarlo, un precio publicado significa dinero: una capability de pago responde
`402` con los rieles que acepta, y una invocación con una `X-API-Key` válida reserva el precio
antes de que el proveedor se ejecute, lo cobra si tiene éxito y lo devuelve ante cualquier fallo.

```
POST /ai-market/v2/accounts                    # un comprador emite una clave (con límite de frecuencia)
GET  /ai-market/v2/account                     # el saldo del comprador
GET  /ai-market/v2/account/ledger              # cada movimiento de su propio dinero
POST /ai-market/v2/accounts/{id}/credit        # usted le recarga  (admin bearer)
POST /ai-market/v2/accounts/{id}/status        # usted lo desactiva  (admin bearer)
GET  /ai-market/v2/stats/live                  # summary.credits: ganado frente a adeudado
```

El dinero entra solo por `/credit`, y esa ruta es solo suya. Use lo que use para cobrar —una
factura, un pago en su web, una transferencia de stablecoin que vio llegar—, llama a `/credit`
cuando ya tiene el dinero. El hub no finge haber cobrado nada.

### Lo que asume

Un saldo prepagado es dinero de su cliente en su libro. Por eso mismo `stats/live` publica
`outstanding_credit_usd` junto a `credits_earned_usd`: lo primero es un pasivo, lo segundo es
ingreso, y un hub que no los distingue acaba gastando uno creyendo que es el otro. Nada en el hub
puede enviar valor, así que los reembolsos los hace usted.

### Ajustes

| Variable | Por defecto | Significado |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | el riel en sí |
| `AIMARKET_CREDITS_OPEN_SIGNUP` | `1` | si un desconocido puede emitir su propia clave |
| `AIMARKET_CREDITS_FREE_GRANT_USD` | `0.05` | saldo inicial de una clave autoemitida |
| `AIMARKET_CREDITS_SIGNUPS_PER_HOUR` | `5` | límite por dirección de registros autoservicio |
| `AIMARKET_ECOSYSTEM_FILE` | `ecosystem.json` junto a la base de datos | qué cuentas, servidores y carteras son su propio ecosistema: sus llamadas son SELF, no demanda externa; vea [clases de tráfico](traffic-classes.es.md) |
| `AIMARKET_OPERATOR_ACCOUNTS` | vacío | atajo antiguo para `self.accounts` de ese archivo (ids de cuenta separados por comas); se fusiona con él |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | su comisión cuando intermedia la capability de otro hub |
| `AIMARKET_PQC` | sin definir = auto | sin definir: un hub nuevo firma híbrido (Ed25519 + ML-DSA-65), un hub con clave ML-DSA sigue firmando con ella, uno solo Ed25519 sigue así; `1` / `0` lo fijan |

## Dejar que otros publiquen en su hub

Una cuenta de créditos es una identidad, no solo una cartera, así que también es la forma en que
alguien publica una capability con usted: sin editar `.env`, sin reiniciar, sin cadena.

```bash
curl -X POST $HUB/ai-market/v2/accounts                      # obtienen una clave
curl -X POST $HUB/ai-market/v2/accounts/<id>/credit \
     -H "Authorization: Bearer $ADMIN" -d '{"amount_usd": 30}'   # usted recibe su dinero
curl -X POST $HUB/ai-market/v2/supply/stake \
     -H "X-API-Key: <key>" -d '{"amount_usd": 25}'               # depositan la garantía
curl -X POST $HUB/ai-market/v2/supply/register \
     -H "X-API-Key: <key>" -d @manifest.json                     # publican
```

La clave habla exactamente por un publicador: su propia cuenta. No puede depositar garantía por
otro ni publicar en nombre de nadie más, algo que el token de publicación compartido nunca pudo
impedir.

La garantía es un cargo real contra su saldo, así que es dinero que usted retiene y puede
recortar mediante slashing (recorte de la garantía). Se registra como un tipo propio de
colateral, distinto del centinela de desarrollo, y supera la comprobación de garantía de
producción. La vía on-chain sigue existiendo y sigue exigiendo un `tx_hash` verificado, pero un
hub cuya imagen no incluye el verificador de depósitos ya no está obligado a elegir entre «sin
colateral» y «una comprobación inservible».

Confianza en los publicadores: con `AIMARKET_ORACLE_FAMILY_URL=off` no hay oráculo al que
consultar, así que los publicadores reciben el arranque neutral documentado y la comprobación de
confianza no se aplica. Apúntela a una instancia de LUMEN que usted opere si quiere puntuación.

## Pagar a sus vendedores

Cuando el publicador de una capability tiene aquí una cuenta de créditos, cada venta completada
se reparte automáticamente: `AIMARKET_PUBLISHER_SHARE_BPS` (70% por defecto) se le abona a él y
el resto es suyo. Es la vía de ganancias del vendedor que el hub nunca tuvo: el libro de canales
no puede enviar valor y la única tabla de obligaciones reembolsa a los depositantes, no a los
proveedores. Antes de esto, un vendedor podía publicar, recibir invocaciones y aun así tener que
pedirle que le transfiriera a mano una décima de céntimo.

`stats/live` informa del reparto con honestidad: `credits_earned_usd` es el bruto (lo que gastaron
los compradores), `publisher_payouts_usd` lo que fue a los vendedores y `operator_net_usd` lo que
usted se quedó. Una llamada fallida no paga a nadie: el pago sale del mismo cobro que se hace al
comprador.

## Intermediar otros hubs

Cuando enruta una invocación a un par por el que usted no vendió, la comisión de enrutamiento se
**reserva antes de pedirle nada al par**, en el riel que use el comprador. Quien llama sin pago
recibe un `402` con la comisión; un par que se niega no le cuesta nada al comprador; a un par que
cobra menos que su precio publicado se le factura el importe menor. Si no quiere cobrar por
intermediar, ponga `AIMARKET_ROUTING_FEE_BPS=0`: esa es la forma de desactivarlo, no una
cabecera que falta.

Un canal respaldado por depósito en garantía no puede autorizar una comisión de enrutamiento (no
hay autorización firmada para ella), así que esa combinación se rechaza en vez de registrarse
como ingreso que nunca podría cobrar. Los compradores por esa vía deben usar una cuenta de
créditos.

### Revender un par que cobra

Intermediar solo mueve dinero si puede pagar a la otra parte. Tenga una cuenta de créditos en el
par e indíquela:

```bash
export AIMARKET_PEER_API_KEYS="https://peer.example=aimk_your_key_there"
```

Ahora una llamada enrutada a ese par es una reventa: a su comprador se le cobra el precio del
catálogo más su comisión, usted paga al par desde su cuenta allí y la comisión es su margen. Sin
clave, el `402` del par llega a un comprador que no tiene cuenta allí y no puede hacer nada con
él; por eso la federación en vivo solo ha contenido pares que no cobran.

A los hubs pares se les llama en su `/ai-market/v2/invoke`, no en su `mcp_endpoint`: ese endpoint
habla MCP JSON-RPC sobre SSE y responde a un sobre enrutado con `Method not found` dentro de un
cuerpo `text/event-stream`. El enrutamiento entre hubs fue imposible hasta que se corrigió.

## Aceptar pagos x402

Una venta de catálogo va directa al vendedor. El 402 indica el `payout_address` del listado y un
`nonce` de factura, y solo su cuerpo JSON lleva un `payment_secret` con
`nonce = sha256(payment_secret)`. El comprador paga a esa cartera on-chain con un
`transferWithAuthorization` EIP-3009 firmado sobre el nonce y reintenta con
`X-Payment: <tx hash>` (o `PAYMENT-SIGNATURE`), `X-Payment-Nonce` y `X-Payment-Secret`. El
secreto es lo que demuestra que el comprador es quien pagó: la transacción y su nonce son
públicos en cuanto se minan. El hub verifica la transferencia y nunca retiene el dinero
(`aimarket_hub/settle.py`): solo paga la transferencia que movió esa autorización, y cada
autorización es una reclamación propia, así que dos en una misma transacción compran dos
llamadas. En una llamada federada, un pago viaja junto a su clave de par solo cuando el hub lo
liquidó en esa misma petición, con su propio nonce y guardando el secreto. Un hub sin clave para
ese par que no liquidó nada es un relé y reenvía las cabeceras de pago del comprador, secreto
incluido. Todo pago está vinculado (una transferencia simple al vendedor se rechaza;
`AIMARKET_SETTLE_REQUIRE_BINDING=0` se ignora), así que las herramientas de comprador escritas
para un hub anterior, que enviaban solo `X-Payment` y `X-Payment-Nonce`, se rechazan hasta que
envíen también el secreto. La pasarela MCP lo acepta como `x_payment_secret` y el puente A2A lo
presenta por sí mismo. La migración `040` añade la columna de factura que lo guarda, y
`X-Payment-Secret` está en la lista de cabeceras permitidas de CORS, así que un cliente de
navegador en un origen de `AIMARKET_CORS_ORIGINS` también puede canjearlo.
`AIMARKET_X402_ACCEPT=0` mantiene el modo de solo descubrimiento.

Los créditos y los canales de pago siguen siendo comodidades de prepago. No son la forma en que se
paga a un publicador con cartera.

## Dejar que desconocidos le encuentren

Siempre hay dos puertas de observación y ambas llevan a cuarentena, no a confianza inmediata: un
`POST /federation/announce` sin autenticar y el descubrimiento recíproco, cuando un par le rastrea
y se identifica. En ambos casos el par queda `pending` y `trusted=false`. Después se ejecuta
automáticamente una prueba en sandbox; un `pass` lo indexa sin pulsar Approve. Fail y review
quedan pendientes para `/operator`. Una tabla de vista previa aparte guarda lo que un par
pendiente dice ofrecer; esas filas nunca pueden llegar a la búsqueda ni al enrutamiento porque no
están en la tabla `capabilities`. Vea `docs/join-the-federation.md`.

## Valerse por sí mismo

Dos valores por defecto apuntan al despliegue de referencia, y probablemente no quiera ninguno:

- **Confianza en los publicadores.** `AIMARKET_ORACLE_FAMILY_URL` apunta por defecto a la
  instancia de LUMEN de otro operador. Si lo deja así, su capacidad de publicar depende de la
  disponibilidad de ese operador: una capability publicada mientras no responde se guarda sin
  puntuación y cada invocación suya responde 502. `off` indica que este hub no tiene oráculo de
  confianza: los publicadores reciben el arranque neutral documentado y la comprobación no se
  aplica. Apúntela a su propia instancia si opera una.
- **Semillas de la federación.** La lista de semillas incluida son los propios satélites del hub
  de referencia. Son un catálogo para explorar, no oferta suya; vea `AIMARKET_SEED_LIST`.

## Nombre

El código es Apache-2.0 (MIT en el resto del ecosistema) y puede explotarlo comercialmente, fijar
sus propias comisiones y quedárselas todas; nada desvía una parte a ningún sitio. No hay licencia
de marca, así que no llame «AIMarket» a su despliegue ni sugiera un respaldo. «Implements the
AIMarket Protocol» e «interoperates with <peer>» son exactas y válidas. Nadie puede afirmar
«certified» ni «conformant»: todavía no hay un conjunto de pruebas de conformidad.
