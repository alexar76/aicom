# Una llamada del cliente para ejecutar un pipeline pagado

[English](one-call-pipelines.md) · [Русский](one-call-pipelines.ru.md) · [Español](one-call-pipelines.es.md) · [Français](one-call-pipelines.fr.md) · [中文](one-call-pipelines.zh.md)

`await run_pipeline(...)` reúne preparación, firma local, ejecución raíz y espera automática en una operación. La ruta normal realiza **dos solicitudes principales al Hub**: preparar el grafo e invocar la raíz. Las llamadas RPC de blockchain son adicionales. HTTP 202, fallos de transporte o errores temporales pueden exigir más solicitudes al mismo pedido; dos intercambios HTTP no garantizan su finalización.

## Vendedores independientes y recuperación: 3.10.1

Un grafo de pago admite ahora un peer de confianza que anuncie **`SELLER-OP/1`**, sin `SELLS_FOR`, cuenta de reventa ni clave de crédito del peer. El comprador paga la factura del vendedor con fondos reales. Conserva `source_hub`: `run_pipeline(...)`, HTTP y MCP seleccionan el adaptador automáticamente. Las cadenas gratuitas siguen funcionando sin fuente de pago.

La preparación verifica el manifiesto firmado y obtiene una oferta del mismo peer. Debe estar activo, ser de confianza y tener claves fijadas; una clave PQ fijada exige también verificación PQ. Se comprueban SKU, comprador, precio de catálogo, destinatario declarado, red, token, reparto e importe y caducidad. No se siguen URL arbitrarias de la oferta. Un peer incompatible se rechaza con `settlement_route_unsupported` antes de firmar o pagar. Preparar puede dejar una factura sin usar, pero no ejecuta trabajo ni transfiere fondos.

El vendedor guarda `operation_id` y emite un `operation_token` limitado a esa operación. La oferta firmada incluye condiciones, nonce/caducidad y esquema de entrada. El token queda en el estado privado del Hub comprador, fuera de la factura pública. La entrada puede depender de pasos anteriores; entrada concreta, comprador y hash de pago se fijan al primer invoke. Modificarlos devuelve HTTP 409. El secreto de factura permanece en el vendedor; no se crea una factura competidora ni se reenvían credenciales de crédito o grants SUB/1. La clave privada del monedero permanece en el cliente.

Rutas: `POST /ai-market/v2/operations/prepare`, `POST /ai-market/v2/operations/{operation_id}/invoke`, `GET /ai-market/v2/operations/{operation_id}`. Invoke y status requieren `X-Operation-Token`; sin token válido se devuelve 404. Prepare acepta `product_id`, `capability_id`, `wallet`, `max_price_usd`; invoke acepta `input`, `wallet`, `tx_hash`, omitido para trabajo gratuito. Un invoke pendiente devuelve 202; un resultado terminal, exitoso o fallido, 200: comprueba `status` y `success`. Status firma el estado sin ejecutar ni pagar. El cliente habitual conserva sus dos solicitudes principales al Hub.

El Hub comprador emite la transacción firmada original, verifica el pago y consulta primero la operación remota. El vendedor verifica también el pago, persiste el bloqueo antes de llamar al proveedor y conserva el resultado firmado. La firma vincula operación, hashes de oferta y entrada, monedero y transacción. Una respuesta perdida se recupera leyendo la misma operación; el resultado guardado sobrevive a un reinicio. La factura raíz incluye `payment_rail: independent_seller`, oferta y estado/recibo firmados. Un hijo local SUB/1 enlaza el resultado al árbol con financiación `own`, sin transferir crédito entre hubs.

El worker comprador renueva su lease cada 30 segundos. Tras 180 segundos sin renovación, el mismo invoke raíz puede recuperar un hijo `SELLER-OP/1` en curso cuyo paso y job están persistidos. El servidor transfiere la propiedad atómicamente y rechaza escrituras del worker antiguo. Status anuncia `resume_same_run`; el SDK conserva el paquete firmado original. No se desbloquean proveedores antiguos arbitrarios; otros estados inciertos requieren conciliación por el operador.

La garantía es **envío como máximo una vez y resultados duraderos**, no ejecución exactamente una vez para cualquier proveedor. El proveedor final recibe `Idempotency-Key` y `X-AIMarket-Operation-Id` estables; necesita idempotencia persistente para cerrar su propia brecha entre ejecución y respuesta. Si el vendedor cae en ese punto o desconoce el resultado, devuelve `reconciliation_required` sin repetir el envío. Un bloqueo obsoleto se señala a los 180 segundos, sin liberarlo. `recovery.action: contact_operator` exige conciliar esa operación; `replacement_payment_allowed` sigue false. El vendedor envuelve únicamente listados locales, sin `pipeline.run@v1` recursivo. No todos los endpoints x402 implementan este protocolo.

Despliega Hub **3.10.1** y migraciones **44** (operaciones) y **45** (leases). No hace falta redesplegar contratos de pago. Actualiza también los peers independientes para que anuncien el protocolo. Un grafo pagado mantiene una red/token; el cliente empaquetado admite Base USDC y necesita gas nativo. Patrocinio de gas, más redes, coordinación de nonce entre máquinas y reembolsos automáticos quedan fuera de esta versión.

Se prueban hubs con claves y bases separadas, solicitudes inmutables, ofertas manipuladas, concurrencia, respuestas perdidas, bloqueo del worker antiguo, entradas dinámicas, cadenas gratuitas y pagos reales en Anvil mediante el código del Hub. Dos escenarios Anvil usan token y cuentas desechables, incluyendo pérdida de respuesta; prueban la integración, no la actualización de todos los vendedores. Las verificaciones de producción se registran por separado. Estas pruebas no requieren un nuevo cargo en mainnet.

## 1. Preparar el grafo

Llama a `POST /studio/prepare-pipeline` con `nodes`, `wallet` opcional y `max_budget_usd`. Combina los anteriores `/studio/preflight` y `/studio/paid-runs/{run_id}/prepare-pipeline`. Devuelve `ready`, `blockers`, identidades y condiciones de los pasos, `total_units`, `run_id`, `access_token`, `graph_digest`, `wallet`, `expires_at` y `offers` con nonces de factura y autorizaciones EIP-712. Preparar no crea un job raíz ni envía fondos. Un grafo gratuito no necesita monedero y devuelve `offers` vacío; uno pagado sin monedero se rechaza. Los endpoints anteriores siguen disponibles. El manifiesto anuncia la nueva ruta en `pipeline_execution.prepare_graph`.

`max_budget_usd` en la solicitud al Hub limita solo los servicios. El parámetro `max_total_usd` del SDK también comprueba la reserva para comisiones de red descrita más abajo.

```json
{
  "nodes": [
    {"id": "weather", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}},
    {"id": "air", "product_id": "gaia.gateway", "capability_id": "gaia.air.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}, "depends_on": ["weather"]}
  ],
  "wallet": "<buyer-address>",
  "max_budget_usd": 1
}
```

## 2. Firmar localmente y ejecutar

El cliente vincula la respuesta al grafo y al monedero solicitados y comprueba ofertas, autorizaciones, saldos, red, nonces pendientes y gas estimado. Firma localmente autorizaciones EIP-3009 y transacciones EIP-1559, asigna nonces consecutivos y guarda el paquete completo antes de enviarlo. El Hub recibe transacciones firmadas, nunca la clave privada. Se envía un pedido raíz `pipeline.run@v1`; el ejecutor transmite cada pago justo antes del paso correspondiente. La respuesta correcta incluye resultado final, factura firmada, recibo raíz y árbol SUB/1. Comprueba `status` y `success`: un fallo del proveedor también es terminal y un pago externo no se reembolsa automáticamente.

```json
{
  "product_id": "hephaestus",
  "capability_id": "pipeline.run@v1",
  "source_hub": "local",
  "input": {
    "run_id": "<prepared-run-id>",
    "access_token": "<scoped-run-token>",
    "transactions": {"weather": "0x<signed-transaction>", "air": "0x<signed-transaction>"}
  }
}
```

## Python y línea de comandos

Instala el wheel publicado con el extra `client` (comando abajo). El cliente paga con **USDC nativo en Base (8453) o Ethereum (1)** (ver los perfiles de pago adicionales más abajo) y está probado en macOS/Linux. Cualquier otra red o token se rechaza salvo que tu propia política `accepted_assets` lo incluya. Los grafos gratuitos no necesitan firmante, RPC ni techo de cotización. El firmante es un objeto local con `address`, `sign_message` y `sign_transaction`.

```python
import json, os
from eth_account import Account
from aimarket_hub.pipeline_client import run_pipeline

result = await run_pipeline(
    json.load(open("blueprint.json")),
    hub="https://modelmarket.dev",
    signer=Account.from_key(os.environ["PIPELINE_WALLET_KEY"]),
    rpc_url="https://mainnet.base.org",
    max_total_usd="1",
    state_path="order.private.json",
    wait=True,
)
print(result["status"], result["final_result"], result["bill_of_materials"])
```

```bash
python examples/pipeline-run/run.py blueprint.json \
  --hub https://modelmarket.dev --rpc https://mainnet.base.org \
  --max-total-usd 1 \
  --execute --prompt-key --state order.private.json
```

`--prompt-key` lee la clave localmente sin eco; alternativamente proporciona `PIPELINE_WALLET_KEY` de forma segura en el entorno. Un grafo gratuito o una reanudación posterior a la firma no necesita clave. Un pedido CLI nuevo exige `--execute`. El ejemplo anterior `client.py --budget` conserva su presupuesto solo para servicios. La versión 3.10.1 requiere desplegar Hub y migraciones 44–45, sin redesplegar los contratos de pago.

## Presupuesto, estado y recuperación

`max_total_usd` incluye servicios y una reserva conservadora para gas. Antes de firmar y de cada envío o reintento raíz, el cliente consulta el contrato ETH/USD fijado de Chainlink en Base mediante dos RPC con nombres de host distintos. El segundo es `https://base-rpc.publicnode.com`, o `https://mainnet.base.org` si el principal es PublicNode; se puede configurar con `price_rpc_url` / `--price-rpc`. Ambas lecturas deben validar Base, 8 decimales, ronda completa y positiva de hasta 1500 segundos, bloque de hasta 120 segundos y secuenciador activo tras una hora de recuperación. Los contratos se leen en el bloque observado. Una diferencia superior al 2% detiene el envío. Se usa el precio mayor **más 25%**. El antiguo `native_usd_ceiling`, ahora opcional, solo puede aumentar esta valoración; no la reduce ni sustituye un oráculo inaccesible. Con ETH a $20 000, el cálculo usa al menos $25 000 aunque un archivo antiguo contenga 6000.

Cada pago reserva 300 000 gas al doble del precio observado y 100 veces la cota L1 de Base GasPriceOracle para 2048 bytes, más $0.05 por pedido. Si se supera el presupuesto guardado, se pausa el envío conservando pedido y firmas. Datos ausentes, antiguos o contradictorios también bloquean nuevos envíos, sin recurrir a un precio fijo. Los grafos gratuitos y resultados finales guardados localmente no necesitan oráculo. Tras una interrupción, se consulta primero el estado del pedido enviado. El archivo de recuperación registra las dos cotizaciones, rondas, fechas y valoración. No crear otra compra para sustituir un pedido de resultado incierto.

La comprobación se realiza antes del envío del cliente, no continuamente durante un grafo largo. Los RPC siguen siendo fuentes de confianza; distintos nombres no garantizan infraestructura independiente. El cambio USD y las comisiones L1 pueden variar después del envío y no quedan limitados por EIP-1559: es protección conservadora, no un depósito en garantía con límite absoluto en dólares.

[Chainlink ETH/USD — Base](https://data.chain.link/feeds/base/base/eth-usd) · [L2 sequencer](https://docs.chain.link/data-feeds/l2-sequencer-feeds).

El archivo de recuperación se reemplaza atómicamente con permisos 0600 y fsync; un bloqueo separado impide usar la misma ruta simultáneamente. Contiene credenciales limitadas del pedido y transacciones firmadas ejecutables: mantenlo privado. No contiene la clave privada. Tras guardar el paquete, resume no necesita firmante ni elige nuevos nonces o pagos. Si la interrupción fue anterior a la firma, sigue haciendo falta el firmante original. Perder la respuesta de preparación puede dejar una cotización sin usar; todavía no existe pago ni job raíz. No realices otras transacciones simultáneas con ese monedero.

La espera está activada por defecto. HTTP 202 continúa el mismo pedido; tras un error de transporte se consulta el estado antes de reenviar el payload original. `PipelinePending` conserva la ruta del estado cuando se agota la espera o hace falta conciliación. Un registro ocupado se consulta en modo de solo lectura, sin desbloquearlo. `wait=False` devuelve un resultado pendiente para reanudarlo. Un archivo local completado devuelve el resultado guardado sin red. Un hijo fallido no se vuelve a comprar ni ejecutar automáticamente. Al reanudar, omite el grafo y las opciones de presupuesto/RPC: se mantienen el grafo y la política guardados.

```python
result = await run_pipeline(resume=True, state_path="order.private.json")
```

```bash
python examples/pipeline-run/run.py --resume --state order.private.json
```

[Codex: una operación del cliente y dos subcontratistas pagados](case-study-codex-one-call.es.md) — 2026-09-30.

## Acceso de agentes: actualización 3.9.0

El cliente se instala desde un wheel versionado sin clonar el repositorio. El manifiesto firmado publica `pipeline_execution.client.distribution`, con URL y SHA-256. El Hub distribuye el paquete; esto no afirma que PyPI ya tenga esta versión.

```bash
pip install "aimarket-hub[client] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
aimarket-pipeline --help
```

`aimarket-pipeline` admite los mismos argumentos que `examples/pipeline-run/run.py`. El extra `client` incluye firma de pagos y verificación ML-DSA. Requiere Python 3.11+. Linux/macOS están probados; el bloqueo para Windows está implementado, pero no probado en esta versión. HTTP/MCP permite usar cualquier lenguaje con un firmante local.

MCP incorpora `pipeline_prepare`, `pipeline_invoke` y `pipeline_status`. Preparar recibe grafo, límite de servicios y monedero opcional; ejecutar recibe `run_id`, `access_token` y el paquete firmado localmente; estado recibe ID y token. Un grafo gratuito no requiere firmante ni fondos. El servidor MCP remoto no puede firmar por un monedero ajeno: conecta un firmante local o usa Python. Nunca envíes la clave privada como argumento. Estas herramientas conservan firmas y ofertas completas.

El SDK verifica la preparación firmada, la factura y el recibo raíz, sus vínculos al grafo/pedido/monedero y los hashes de resultado/factura, incluso en caché. Fija las claves del Hub en la primera preparación HTTPS. Para confianza independiente, pasa `trusted_hub_key` y `trusted_hub_pq_key` (CLI: `--trusted-hub-key`, `--trusted-hub-pq-key`). Fijada la clave PQ, eliminar su firma se rechaza. Se verifica el informe firmado del Hub, no la identidad independiente de cada dispositivo.

`GET /studio/paid-runs/{run_id}/pipeline` con `X-Studio-Run-Token` lee sin pagar ni invocar hijos. Tras perder una respuesta o reanudar, el SDK consulta primero este estado, antes de RPC/gas. Puede recuperar un resultado terminado aunque RPC falle o las comisiones suban. El trabajo ocupado se consulta sin modificarlo. Los reintentos 429/5xx aumentan el intervalo y respetan `Retry-After` numérico dentro del tiempo restante. `PipelineHTTPError` conserva `status_code`, `detail` y `state_path`.

Una reserva persistente del monedero evita rangos de nonce solapados entre archivos de estado del mismo host. Se guarda en `~/.aimarket/wallets`; `AIMARKET_WALLET_STATE_DIR` permite elegir un directorio común. Todos los clientes cooperantes deben compartirlo. El éxito libera la reserva; un fallo espera a que todos los nonces se consuman o las autorizaciones caduquen sin transacciones pendientes. Conserva el archivo original. Entre hosts o programas distintos, usa un firmante/coordinador compartido o monederos dedicados; los archivos locales no coordinan firmantes externos arbitrarios.

Preflight devuelve `blockers[].code`: `settlement_route_unsupported`, `route_unavailable`, `mixed_assets_unsupported`, `service_budget_exceeded`. Las rutas externas admiten vendedor de registro, reventa configurada y peers independientes con SELLER-OP/1. El manifiesto explicita este límite. Un grafo pagado usa una red/token; Python admite Base USDC. Estar en el catálogo no garantiza compatibilidad de pago.

Si un proveedor ejecutó y se perdió la respuesta, no se vuelve a comprar automáticamente. `recovery.action` indica `wait`, `resume_same_run` o `contact_operator`, sin pago sustitutorio. La conciliación necesita un recibo o evidencia del proveedor. Los hijos no enviados no se pagan; los pagos externos confirmados no se reembolsan automáticamente. La incertidumbre se expone sin repetir trabajo silenciosamente.


Prueba adicional en producción, 2026-09-30: el Hub vendedor separado `https://independentai.network/hub` completó `kova.network.status@v1` por 0.002 USDC en Base. El cliente perdió intencionadamente la primera respuesta y retomó la misma operación sin otro pago. Ambos Hubs tienen el mismo administrador; se demuestra un despliegue y destinatario separados, no propietarios comerciales independientes.

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · [Evidence](evidence/independent-seller-mainnet-2026-09-30.json) · [Oracle RPC evidence — SDK 3.10.2](evidence/native-price-oracle-2026-09-30.json).


Prueba del proveedor prepagado en producción, 2026-09-30: `weather.witness@v1` publica su dirección real de cobro y funciona a precio fijo. Su cuenta separada empezó en cero, sin subvenciones ni garantía. Un depósito real de 0.02 USDC mediante EIP-3009 la financió; el comprador pagó después 0.002 USDC por el SKU raíz. El proveedor compró clima y aire de GAIA por 0.001 cada uno, dejando 0.018. Es contabilidad interna prepagada tras un depósito real, no dos transferencias adicionales en cadena ni una línea de crédito. El límite diario del proveedor es 0.02 y no hay recarga automática. Berlín devolvió agreement=true, 14.5°C, humedad 64%, PM2.5 9.9 µg/m³ y US AQI 33, con fecha 2026-09-30T07:01:32Z. La ejecución `paid_580f85c4a2f4deba7a83bc26140fc558` corresponde al job `job_db9c841f8a360f04c891a68b` y conserva ambos recibos hijos. Un HTTP 429 del RPC después de firmar detuvo el envío; reanudar el paquete guardado completó el mismo pedido. Depósito y compra usaron la valoración del oráculo. El gasto acumulado conservador es $0.047149423922618862625 del límite $1, incluyendo todo el depósito sin contar otra vez los débitos hijos.

[Evidence](evidence/witness-prepaid-mainnet-2026-09-30.json) · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


SDK 3.10.3 intenta la misma solicitud RPC hasta tres veces ante HTTP 429/5xx o un fallo de transporte, con pausas limitadas a cinco segundos. Si se agotan los intentos, detiene el envío y conserva el pedido: no sustituye la cotización por un valor fijo ni crea otro pago.

## Estado de publicación de paquetes — comprobado el 2026-09-30

PyPI ya contiene wheel y archivo fuente de `aimarket-hub==3.10.3`; sus 131 archivos del paquete coinciden con la compilación de producción. La versión 3.11.0 añade patrocinio de gas y necesita una nueva publicación, sin reemplazar archivos 3.10.3. Sigue pendiente comprobar la publicación separada de `aimarket-agent==2.5.0`. Publicación y despliegue son operaciones distintas. Recuperación de proveedores, reembolsos y más redes/tokens son las siguientes etapas.

## Patrocinio de gas — SDK 3.11.0

El SDK usa `gas_mode="auto"` por defecto. La preparación firmada por el Hub indica si puede patrocinar todo el grafo. El comprador firma localmente solo las autorizaciones EIP-3009 exactas de USDC; una cartera separada del operador firma las transacciones y paga el gas. El comprador no necesita ETH, firma de transacciones ni configuración RPC. `gas_mode="required"` rechaza el grafo pagado durante la preparación si el patrocinio no está disponible. `gas_mode="buyer"` conserva el pago de gas por el comprador. HTTP y MCP mantienen `buyer` por defecto por compatibilidad. CLI: `--gas-mode required`.

La preparación devuelve `gas_sponsorship`; la invocación raíz acepta `authorizations: {step_id: signature}` en lugar de `transactions`. No se pueden enviar ambos. La cotización fija modo, comprador, destinatarios, importes, nonces y vencimientos; los reintentos no pueden cambiar las firmas. El Hub nunca recibe la clave privada del comprador. La factura firmada identifica el patrocinio y el pagador de gas; la comisión de gas del comprador es cero. Los grafos gratuitos siguen funcionando sin firmante ni patrocinador, incluso con `required`.

La primera versión admite pagos directos de USDC en Base 8453, también a vendedores independientes compatibles. El MarketSplitter actual vincula al pagador con `msg.sender`, por lo que excluye explícitamente pagos con reparto de comisión. La ruta directa no necesita redesplegar contratos. `auto` puede recurrir al gas del comprador; `required` nunca lo hace. Saldo insuficiente del patrocinador, límite diario agotado, oráculo no disponible o nonce ocupado dejan el mismo pedido pendiente, sin crear otro pago.

Antes de cada nuevo pago, el Hub comprueba el oráculo ETH/USD, una estimación conservadora, el saldo y los límites por pago y día. Tras resolver y validar la entrada del paso, reserva un nonce y guarda los bytes firmados atómicamente en la base de datos compartida. Solo hay una transacción pendiente por cartera. Los trabajadores comparten nonce y presupuesto; los reintentos retransmiten bytes idénticos. Un fallo tras guardar la transacción se recupera incluso después del vencimiento, pues el pago puede haberse realizado. Los resultados finales guardados no necesitan RPC. Bases de datos separadas no deben compartir una cartera de gas.

Configuración: `AIMARKET_PIPELINE_RELAY_ENABLED=1`, `AIMARKET_PIPELINE_RELAY_KEY_FILE` (archivo privado, no enlace simbólico), `AIMARKET_PIPELINE_RELAY_RPC`, opcional `AIMARKET_PIPELINE_RELAY_PRICE_RPC`, `AIMARKET_PIPELINE_RELAY_DAILY_WEI` (20000000000000 por defecto) y `AIMARKET_PIPELINE_RELAY_MAX_GAS_USD` (0.10). Financiar una cartera dedicada, nunca instalar la clave del comprador. El contador diario reserva límites conservadores en ETH y no libera diferencias tras minar. La estimación USD no es un límite USD inmutable en cadena. Las transacciones guardadas siguen siendo recuperables al desactivar nuevas operaciones patrocinadas.

Pruebas: trabajadores concurrentes con conexiones separadas, reversión de reservas, firmas inválidas, recuperación inmutable, grafos gratuitos y una transferencia EIP-3009 real en Anvil con cero ETH del comprador. Estas pruebas no certifican despliegue en producción ni finalización de recuperación de proveedores, reembolsos o soporte multired.

Prueba en producción del 2026-09-30: un paso gratuito de LOGOS y después `kova.network.status@v1` en `https://independentai.network/hub`, con firma solo de mensajes y sin RPC configurado en el SDK. Coste del comprador: **0.002 USDC** de servicio y **0** de gas; saldo ETH y nonce sin cambios. La pérdida deliberada de la primera respuesta invoke recuperó el mismo pedido. KOVA devolvió `pass`, puntuación 100, bloque Base 51983924. El patrocinador pagó 516607663289 wei. Se contabilizó íntegramente su financiación de 0.00002 ETH, sin sumar el gas dos veces. Gasto conservador acumulado: **$0.1163241752052936711504319125 de $1**, incluidas pruebas anteriores. Las pruebas adjuntas no contienen tokens de acceso ni claves privadas.

`run_id: paid_38c0a7c6c2fe992186116a2822205d3d` · `job_id: job_dc0b37b785a7f358bfb30b23`

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · [Evidence](evidence/gas-sponsorship-mainnet-2026-09-30.json)

## Recuperación del resultado del proveedor — SDK/Hub 3.12.0

`PROVIDER-OP/1` resuelve el caso en que el proveedor termina pero el Hub vendedor pierde la respuesta. El proveedor registra ID y hash de producto, capability y entrada antes de ejecutar, y guarda resultado y firma antes de responder. Repetir la misma operación devuelve el resultado guardado; cambiar la entrada se rechaza. Las solicitudes concurrentes no duplican el trabajo. KOVA conserva el diario en su base SQLite.

El vendedor habilita explícitamente productos compatibles: `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. Las nuevas ofertas firmadas `SELLER-OP/1` anuncian `provider_recovery: PROVIDER-OP/1`; URL y clave pública originales quedan fijadas en el estado privado. Tras perder la respuesta o quedar una ejecución obsoleta, consulta `GET <invoke_url>/operations/<operation_id>`. Verifica firma, ID, producto, capability, hash exacto de entrada y firma separada del resultado. Recuperar trabajo pagado exige una verificación del pago original guardada. La respuesta terminal es inmutable incluso ante un trabajador tardío. No hay segundo POST al proveedor ni otro pago.

Invoke y status de KOVA requieren el token privado compartido: `AIMARKET_CAPABILITY_TOKEN` y `KOVA_CAPABILITY_TOKEN`; `AIMARKET_INVOKE_HOST_GATEWAY` permite solo el host del proveedor del operador. No se publican claves ni tokens. Los compradores siguen usando los controles de pago del Hub.

Es recuperación cooperativa, no una garantía universal de efectos externos exactamente una vez. Si el proveedor cae después de un efecto y antes de guardar el resultado, la operación permanece incierta y no se repite automáticamente. Debe ligar su transacción comercial al ID o reconciliar el efecto. Los proveedores antiguos conservan reconciliación manual; KOVA bloquea las entradas inciertas para evitar escrituras duplicadas.

Una factura ya pagada puede recuperarse después de vencer si la marca temporal del bloque es estrictamente anterior al vencimiento. Pagos posteriores siguen rechazados y los nonces siguen siendo de un uso. Los RPC explícitos separados por comas forman una lista exclusiva. La factura pública omite el campo interno de concesión del job. Las pruebas cubren reinicio, concurrencia, entrada cambiada, autenticación, firmas manipuladas, dos Hubs sin segundo pago, efecto incierto y límites de vencimiento.

Prueba en producción, 2026-09-30: LOGOS → KOVA por 0.002 USDC, sin gas del comprador. Tras reiniciar KOVA, se recuperó por GET el resultado firmado de su diario persistente. La pérdida de respuesta se simuló en una copia aislada de la operación; no se modificaron registros de producción. No hubo otra invocación ni pago. Se conservó el bloque Base 51984647. Status sin token devolvió 401; una consulta autorizada de una operación inexistente, 404. Gasto acumulado conservador: $0.1183241752052936711504319125 de $1. Reembolsos y más redes/tokens siguen como próximas etapas.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · [Evidence](evidence/provider-recovery-mainnet-2026-09-30.json)


## Reembolso aprobado por el vendedor — SDK/Hub 3.13.0

`SELLER-REFUND/1` permite devolver un pago directo confirmado en USDC de Base. El comprador solicita una oferta para un paso de una cadena terminada; el vendedor original firma localmente la autorización EIP-3009. El patrocinador paga el gas. Nadie entrega claves privadas al Hub y ninguna de las dos partes necesita ETH para esta ruta. Preparar una oferta no mueve fondos ni obliga al vendedor a aceptarla.

HTTP utiliza el `X-Studio-Run-Token` original: `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` crea o recupera la oferta firmada; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` recibe `{"authorization":"0x…"}` y continúa el mismo reembolso; `GET` consulta su estado. HTTP 202 indica espera. MCP ofrece `pipeline_refund_prepare`, `pipeline_refund` y `pipeline_refund_status`, con run ID, token limitado y step ID. Envíe únicamente la firma del vendedor, nunca su clave.

`refund_pipeline(state_path=..., step_id=...)` devuelve la oferta sin transferir dinero. Comparta únicamente su objeto `offer` con el vendedor, no el archivo privado del comprador. El vendedor usa `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` de `aimarket_hub.refund_client`. El destinatario autorizado, el pago original, el límite de importe, token, red y firma del Hub se verifican localmente. Envíe la firma resultante mediante `refund_pipeline(..., authorization=signature)`. Repetir con el mismo archivo recupera el mismo reembolso; `RefundPending` conserva su identidad. La aplicación del vendedor decide si corresponde devolver el pago antes de firmar.

Solo se aceptan el vendedor original, el comprador original y el importe completo exacto de un pago verificado. La cadena debe estar completed o failed; un resultado desconocido del proveedor requiere conciliación previa. La firma presentada es inmutable. Los bytes de transacción se guardan antes de transmitir y comparten el coordinador de nonce y presupuesto del patrocinador en la base de datos. Respuestas perdidas y reinicios reutilizan la misma transacción. Una aprobación caducada solo se renueva antes de que el Hub firme una transacción, manteniendo refund ID y nonce de autorización para impedir dos transferencias.

La factura y el resultado originales permanecen inmutables. Una nota de crédito firmada `pipeline.refund/1` enlaza ambos hashes, importe, token, red, partes y pagador del gas. Consultar el estado no transfiere fondos. Esta versión admite un reembolso completo por pago directo Base USDC sin comisión de reparto y con patrocinador disponible. No implementa devoluciones parciales, recuperación de comisiones MarketSplitter, débitos forzosos ni tokens arbitrarios. El vendedor puede rechazar o carecer de fondos; un patrocinador sin capacidad deja pendiente el mismo reembolso. El gas consumido no se devuelve. Las cadenas gratuitas siguen funcionando sin fuente de pago.

Las pruebas cubren firmantes incorrectos, importes alterados, protección concurrente, aprobaciones caducadas, transacciones persistidas, respuestas perdidas, SDK/MCP y compra más reembolso en Anvil sin ETH del comprador ni vendedor. La verificación mainnet se documenta por separado una vez completada.


Verificación mainnet, 2026-09-30: un SKU estático temporal del operador entregó el resultado por 0.001 USDC y su cartera de vendedor separada aprobó la devolución completa. Es una prueba de liquidación y reembolso reales, no de un vendedor comercial independiente. Los saldos USDC de ambas partes volvieron a sus valores iniciales; ETH y nonce del comprador no cambiaron. El patrocinador pagó ambos gases. La pérdida deliberada de la respuesta recuperó la misma nota de crédito; después de reiniciar el Hub, resultado y reembolso conservaron exactamente los mismos valores JSON. Se eliminó el listado temporal. Gasto acumulado conservador: $0.1193241752052936711504319125 de $1, incluyendo toda la financiación del patrocinador y la compra bruta aunque se devolvió. No se desplegaron contratos nuevos.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · [Evidence](evidence/refund-mainnet-2026-09-30.json)


## Más perfiles de pago y varios equipos — SDK/Hub 3.14.0

El SDK acepta USDC nativo en **Base 8453 y Ethereum 1**, con direcciones fijadas, seis decimales y dominio EIP-712 `USD Coin` / `2`. Cada grafo pagado conserva una sola red y activo; divida los grafos mixtos en pedidos separados. El Hub debe ofrecer esa ruta: aceptar una red no transfiere saldos entre cadenas ni cambia la moneda del vendedor. Los grafos gratuitos siguen iguales. Patrocinio y reembolsos siguen limitados a pagos directos Base USDC; en Ethereum el comprador paga gas. `gas_mode="required"` rechaza una ruta pagada sin patrocinador antes de firmar.

`accepted_assets=[...]` sustituye la lista predeterminada. Cada entrada fija `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true` y `authorization: "EIP-3009"`. Es una política del comprador para un token dólar auditado, no una garantía de propiedades de cualquier ERC-20. El Hub no puede ampliarla. Los importes usan aritmética decimal. Activos no denominados en dólares, ERC-20 que solo admiten approve, otras redes y grafos atómicos entre cadenas se rechazan. CLI: `--accepted-assets approved-assets.json`. La política queda fijada en el archivo de recuperación y no cambia con resume.

Un vendedor local Ethereum configura `AIMARKET_X402_CHAIN=ethereum`. Envío y verificación usan el chain ID firmado; `AIMARKET_SETTLE_RPC_1` y `AIMARKET_SETTLE_RPC_8453` seleccionan RPC por red. `AIMARKET_SETTLE_RPC_URL` conserva su lista exclusiva de respaldo: una lista solo Base no sirve para Ethereum. Cada RPC debe declarar la red de la factura antes de verificar o transmitir. Un activo personalizado exige dirección, símbolo, decimales, `AIMARKET_X402_EIP712_NAME` y `AIMARKET_X402_EIP712_VERSION` correctos, además de la lista coincidente del comprador. No valore como dólar un token que no lo sea.

Ethereum comprueba ETH/USD fresco en dos hosts RPC, margen 25%, gas limitado y reserva de $0.05. No añade la comisión L1 de Base. El feed Chainlink fijado es `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, ocho decimales, heartbeat 3600 s y edad máxima 3900 s. Base mantiene control del secuenciador y reserva L1. Red incorrecta, bloques o precios antiguos y desacuerdo mayor del 2% detienen el pago. Un precio manual solo puede aumentar el techo.

Para varios equipos, instale el extra `postgres` y configure el mismo **PostgreSQL del comprador** mediante `AIMARKET_WALLET_DATABASE_URL` antes de crear pedidos. Utilice conexión directa o session pooling; el modo transaction de PgBouncer no conserva advisory locks de sesión. El coordinador serializa cada `(chain_id, wallet)` entre conexiones y guarda el estado privado, token limitado del Hub y bytes firmados antes del envío, nunca la clave privada. Limite el acceso a los agentes colaboradores del comprador. El DSN no se guarda en el pedido ni se transmite al Hub.

Copie de forma segura el archivo privado al siguiente equipo y use `run_pipeline(resume=True, state_path=...)`. Una copia anterior a la firma recupera de PostgreSQL el paquete ya guardado; un pedido terminado se consulta antes de firmar. Otro pedido no toma una reserva sin terminar. Tras un fallo terminal, solo se libera cuando todos los nonces firmados se consumieron, o las autorizaciones caducaron y no hay transacciones pendientes. Si falla la BD, no hay nuevos envíos; los resultados locales terminados siguen disponibles. Todos los clientes deben usar la misma BD y esquema, sin coordinadores separados ni otro software usando esa cartera. Los archivos locales siguen siendo el valor predeterminado; compradores patrocinados no necesitan PostgreSQL.

Se probó PostgreSQL real con conexiones independientes, caída del cliente, copias obsoletas y fallos de guardado. Una EVM local con chain ID 1 ejecutó una compra EIP-3009 real mediante el SDK; el oráculo se prueba aparte. En Ethereum mainnet solo se hicieron lecturas: coincidieron las dos observaciones de precio y name/version/decimals de USDC. No se afirma una compra mainnet Ethereum ni hubo gasto adicional.

[Contratos Circle](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · [Verificación de lectura](evidence/ethereum-profile-2026-09-30.json)

Entrega: Hub y wheel descargable 3.14.0. PyPI, consultado el 2026-09-30, aún muestra `aimarket-hub==3.10.3` y `aimarket-agent==2.4.0`. Los artefactos nuevos son `aimarket-hub==3.14.0` y el SDK de proveedor separado `aimarket-agent==2.5.0`. No hay credenciales de publicación en este entorno; subirlos a PyPI queda a cargo del operador. El wheel fijado del Hub ya se puede instalar. No es necesario redesplegar contratos.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```
