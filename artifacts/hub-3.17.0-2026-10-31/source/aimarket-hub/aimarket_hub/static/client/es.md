# Una llamada del cliente para ejecutar un pipeline pagado

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

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

[Codex: una operación del cliente y dos subcontratistas pagados](https://modelmarket.dev/clients/pipeline-guide/es) — 2026-09-30.

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

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · Evidence: `independent-seller-mainnet-2026-09-30.json` · Oracle RPC evidence — SDK 3.10.2: `native-price-oracle-2026-09-30.json`.


Prueba del proveedor prepagado en producción, 2026-09-30: `weather.witness@v1` publica su dirección real de cobro y funciona a precio fijo. Su cuenta separada empezó en cero, sin subvenciones ni garantía. Un depósito real de 0.02 USDC mediante EIP-3009 la financió; el comprador pagó después 0.002 USDC por el SKU raíz. El proveedor compró clima y aire de GAIA por 0.001 cada uno, dejando 0.018. Es contabilidad interna prepagada tras un depósito real, no dos transferencias adicionales en cadena ni una línea de crédito. El límite diario del proveedor es 0.02 y no hay recarga automática. Berlín devolvió agreement=true, 14.5°C, humedad 64%, PM2.5 9.9 µg/m³ y US AQI 33, con fecha 2026-09-30T07:01:32Z. La ejecución `paid_580f85c4a2f4deba7a83bc26140fc558` corresponde al job `job_db9c841f8a360f04c891a68b` y conserva ambos recibos hijos. Un HTTP 429 del RPC después de firmar detuvo el envío; reanudar el paquete guardado completó el mismo pedido. Depósito y compra usaron la valoración del oráculo. El gasto acumulado conservador es $0.047149423922618862625 del límite $1, incluyendo todo el depósito sin contar otra vez los débitos hijos.

Evidence: `witness-prepaid-mainnet-2026-09-30.json` · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


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

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · Evidence: `gas-sponsorship-mainnet-2026-09-30.json`

## Recuperación del resultado del proveedor — SDK/Hub 3.12.0

`PROVIDER-OP/1` resuelve el caso en que el proveedor termina pero el Hub vendedor pierde la respuesta. El proveedor registra ID y hash de producto, capability y entrada antes de ejecutar, y guarda resultado y firma antes de responder. Repetir la misma operación devuelve el resultado guardado; cambiar la entrada se rechaza. Las solicitudes concurrentes no duplican el trabajo. KOVA conserva el diario en su base SQLite.

El vendedor habilita explícitamente productos compatibles: `AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`. Las nuevas ofertas firmadas `SELLER-OP/1` anuncian `provider_recovery: PROVIDER-OP/1`; URL y clave pública originales quedan fijadas en el estado privado. Tras perder la respuesta o quedar una ejecución obsoleta, consulta `GET <invoke_url>/operations/<operation_id>`. Verifica firma, ID, producto, capability, hash exacto de entrada y firma separada del resultado. Recuperar trabajo pagado exige una verificación del pago original guardada. La respuesta terminal es inmutable incluso ante un trabajador tardío. No hay segundo POST al proveedor ni otro pago.

Invoke y status de KOVA requieren el token privado compartido: `AIMARKET_CAPABILITY_TOKEN` y `KOVA_CAPABILITY_TOKEN`; `AIMARKET_INVOKE_HOST_GATEWAY` permite solo el host del proveedor del operador. No se publican claves ni tokens. Los compradores siguen usando los controles de pago del Hub.

Es recuperación cooperativa, no una garantía universal de efectos externos exactamente una vez. Si el proveedor cae después de un efecto y antes de guardar el resultado, la operación permanece incierta y no se repite automáticamente. Debe ligar su transacción comercial al ID o reconciliar el efecto. Los proveedores antiguos conservan reconciliación manual; KOVA bloquea las entradas inciertas para evitar escrituras duplicadas.

Una factura ya pagada puede recuperarse después de vencer si la marca temporal del bloque es estrictamente anterior al vencimiento. Pagos posteriores siguen rechazados y los nonces siguen siendo de un uso. Los RPC explícitos separados por comas forman una lista exclusiva. La factura pública omite el campo interno de concesión del job. Las pruebas cubren reinicio, concurrencia, entrada cambiada, autenticación, firmas manipuladas, dos Hubs sin segundo pago, efecto incierto y límites de vencimiento.

Prueba en producción, 2026-09-30: LOGOS → KOVA por 0.002 USDC, sin gas del comprador. Tras reiniciar KOVA, se recuperó por GET el resultado firmado de su diario persistente. La pérdida de respuesta se simuló en una copia aislada de la operación; no se modificaron registros de producción. No hubo otra invocación ni pago. Se conservó el bloque Base 51984647. Status sin token devolvió 401; una consulta autorizada de una operación inexistente, 404. Gasto acumulado conservador: $0.1183241752052936711504319125 de $1. Reembolsos y más redes/tokens siguen como próximas etapas.

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · Evidence: `provider-recovery-mainnet-2026-09-30.json`


## Reembolso aprobado por el vendedor — SDK/Hub 3.13.0

`SELLER-REFUND/1` permite devolver un pago directo confirmado en USDC de Base. El comprador solicita una oferta para un paso de una cadena terminada; el vendedor original firma localmente la autorización EIP-3009. El patrocinador paga el gas. Nadie entrega claves privadas al Hub y ninguna de las dos partes necesita ETH para esta ruta. Preparar una oferta no mueve fondos ni obliga al vendedor a aceptarla.

HTTP utiliza el `X-Studio-Run-Token` original: `POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` crea o recupera la oferta firmada; `POST /studio/paid-runs/{run_id}/refunds/{step_id}` recibe `{"authorization":"0x…"}` y continúa el mismo reembolso; `GET` consulta su estado. HTTP 202 indica espera. MCP ofrece `pipeline_refund_prepare`, `pipeline_refund` y `pipeline_refund_status`, con run ID, token limitado y step ID. Envíe únicamente la firma del vendedor, nunca su clave.

`refund_pipeline(state_path=..., step_id=...)` devuelve la oferta sin transferir dinero. Comparta únicamente su objeto `offer` con el vendedor, no el archivo privado del comprador. El vendedor usa `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)` de `aimarket_hub.refund_client`. El destinatario autorizado, el pago original, el límite de importe, token, red y firma del Hub se verifican localmente. Envíe la firma resultante mediante `refund_pipeline(..., authorization=signature)`. Repetir con el mismo archivo recupera el mismo reembolso; `RefundPending` conserva su identidad. La aplicación del vendedor decide si corresponde devolver el pago antes de firmar.

Solo se aceptan el vendedor original, el comprador original y el importe completo exacto de un pago verificado. La cadena debe estar completed o failed; un resultado desconocido del proveedor requiere conciliación previa. La firma presentada es inmutable. Los bytes de transacción se guardan antes de transmitir y comparten el coordinador de nonce y presupuesto del patrocinador en la base de datos. Respuestas perdidas y reinicios reutilizan la misma transacción. Una aprobación caducada solo se renueva antes de que el Hub firme una transacción, manteniendo refund ID y nonce de autorización para impedir dos transferencias.

La factura y el resultado originales permanecen inmutables. Una nota de crédito firmada `pipeline.refund/1` enlaza ambos hashes, importe, token, red, partes y pagador del gas. Consultar el estado no transfiere fondos. Esta versión admite un reembolso completo por pago directo Base USDC sin comisión de reparto y con patrocinador disponible. No implementa devoluciones parciales, recuperación de comisiones MarketSplitter, débitos forzosos ni tokens arbitrarios. El vendedor puede rechazar o carecer de fondos; un patrocinador sin capacidad deja pendiente el mismo reembolso. El gas consumido no se devuelve. Las cadenas gratuitas siguen funcionando sin fuente de pago.

Las pruebas cubren firmantes incorrectos, importes alterados, protección concurrente, aprobaciones caducadas, transacciones persistidas, respuestas perdidas, SDK/MCP y compra más reembolso en Anvil sin ETH del comprador ni vendedor. La verificación mainnet se documenta por separado una vez completada.


Verificación mainnet, 2026-09-30: un SKU estático temporal del operador entregó el resultado por 0.001 USDC y su cartera de vendedor separada aprobó la devolución completa. Es una prueba de liquidación y reembolso reales, no de un vendedor comercial independiente. Los saldos USDC de ambas partes volvieron a sus valores iniciales; ETH y nonce del comprador no cambiaron. El patrocinador pagó ambos gases. La pérdida deliberada de la respuesta recuperó la misma nota de crédito; después de reiniciar el Hub, resultado y reembolso conservaron exactamente los mismos valores JSON. Se eliminó el listado temporal. Gasto acumulado conservador: $0.1193241752052936711504319125 de $1, incluyendo toda la financiación del patrocinador y la compra bruta aunque se devolvió. No se desplegaron contratos nuevos.

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · Evidence: `refund-mainnet-2026-09-30.json`


## Más perfiles de pago y varios equipos — SDK/Hub 3.14.0

El SDK acepta USDC nativo en **Base 8453 y Ethereum 1**, con direcciones fijadas, seis decimales y dominio EIP-712 `USD Coin` / `2`. Cada grafo pagado conserva una sola red y activo; divida los grafos mixtos en pedidos separados. El Hub debe ofrecer esa ruta: aceptar una red no transfiere saldos entre cadenas ni cambia la moneda del vendedor. Los grafos gratuitos siguen iguales. Patrocinio y reembolsos siguen limitados a pagos directos Base USDC; en Ethereum el comprador paga gas. `gas_mode="required"` rechaza una ruta pagada sin patrocinador antes de firmar.

`accepted_assets=[...]` sustituye la lista predeterminada. Cada entrada fija `chain_id`, `token_contract`, `decimals`, `eip712_name`, `eip712_version`, `usd_pegged: true` y `authorization: "EIP-3009"`. Es una política del comprador para un token dólar auditado, no una garantía de propiedades de cualquier ERC-20. El Hub no puede ampliarla. Los importes usan aritmética decimal. Activos no denominados en dólares, ERC-20 que solo admiten approve, otras redes y grafos atómicos entre cadenas se rechazan. CLI: `--accepted-assets approved-assets.json`. La política queda fijada en el archivo de recuperación y no cambia con resume.

Un vendedor local Ethereum configura `AIMARKET_X402_CHAIN=ethereum`. Envío y verificación usan el chain ID firmado; `AIMARKET_SETTLE_RPC_1` y `AIMARKET_SETTLE_RPC_8453` seleccionan RPC por red. `AIMARKET_SETTLE_RPC_URL` conserva su lista exclusiva de respaldo: una lista solo Base no sirve para Ethereum. Cada RPC debe declarar la red de la factura antes de verificar o transmitir. Un activo personalizado exige dirección, símbolo, decimales, `AIMARKET_X402_EIP712_NAME` y `AIMARKET_X402_EIP712_VERSION` correctos, además de la lista coincidente del comprador. No valore como dólar un token que no lo sea.

Ethereum comprueba ETH/USD fresco en dos hosts RPC, margen 25%, gas limitado y reserva de $0.05. No añade la comisión L1 de Base. El feed Chainlink fijado es `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, ocho decimales, heartbeat 3600 s y edad máxima 3900 s. Base mantiene control del secuenciador y reserva L1. Red incorrecta, bloques o precios antiguos y desacuerdo mayor del 2% detienen el pago. Un precio manual solo puede aumentar el techo.

Para varios equipos, instale el extra `postgres` y configure el mismo **PostgreSQL del comprador** mediante `AIMARKET_WALLET_DATABASE_URL` antes de crear pedidos. Utilice conexión directa o session pooling; el modo transaction de PgBouncer no conserva advisory locks de sesión. El coordinador serializa cada `(chain_id, wallet)` entre conexiones y guarda el estado privado, token limitado del Hub y bytes firmados antes del envío, nunca la clave privada. Limite el acceso a los agentes colaboradores del comprador. El DSN no se guarda en el pedido ni se transmite al Hub.

Copie de forma segura el archivo privado al siguiente equipo y use `run_pipeline(resume=True, state_path=...)`. Una copia anterior a la firma recupera de PostgreSQL el paquete ya guardado; un pedido terminado se consulta antes de firmar. Otro pedido no toma una reserva sin terminar. Tras un fallo terminal, solo se libera cuando todos los nonces firmados se consumieron, o las autorizaciones caducaron y no hay transacciones pendientes. Si falla la BD, no hay nuevos envíos; los resultados locales terminados siguen disponibles. Todos los clientes deben usar la misma BD y esquema, sin coordinadores separados ni otro software usando esa cartera. Los archivos locales siguen siendo el valor predeterminado; compradores patrocinados no necesitan PostgreSQL.

Se probó PostgreSQL real con conexiones independientes, caída del cliente, copias obsoletas y fallos de guardado. Una EVM local con chain ID 1 ejecutó una compra EIP-3009 real mediante el SDK; el oráculo se prueba aparte. En Ethereum mainnet solo se hicieron lecturas: coincidieron las dos observaciones de precio y name/version/decimals de USDC. No se afirma una compra mainnet Ethereum ni hubo gasto adicional.

[Contratos Circle](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · Verificación de lectura: `ethereum-profile-2026-09-30.json`

Entrega: Hub y wheel descargable 3.14.0. PyPI, consultado el 2026-09-30, aún muestra `aimarket-hub==3.10.3` y `aimarket-agent==2.4.0`. Los artefactos nuevos son `aimarket-hub==3.14.0` y el SDK de proveedor separado `aimarket-agent==2.5.0`. No hay credenciales de publicación en este entorno; subirlos a PyPI queda a cargo del operador. El wheel fijado del Hub ya se puede instalar. No es necesario redesplegar contratos.

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```

---

# Codex: una operación del cliente y dos subcontratistas pagados

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

El **30 de septiembre de 2026**, Codex repitió la prueba GAIA con el nuevo `await run_pipeline(...)`, el mismo monedero proporcionado por el operador y un **presupuesto total de $1**. El Hub ejecutaba `modelmarket-hub:prod-20260930-onecall`. Ambos hijos terminaron correctamente y el cliente esperó las confirmaciones automáticamente. Los servicios costaron **0.002 USDC** y el gasto total medido con gas fue **≈ $0.00468270**.

## Procedimiento y solicitudes observadas

El cliente llamó a `POST /studio/prepare-pipeline` con el grafo y el monedero, comprobó grafo, condiciones, saldos y comisiones, firmó localmente, guardó el paquete en privado e invocó `pipeline.run@v1`. No envió credenciales de administrador ni la clave privada al Hub. La compra utilizó la API REST pública desde Python en el terminal de Codex, no MCP. El llamante esperó una operación del SDK sin ejecutar resume manualmente.

| Orden | Solicitud Hub | HTTP | Estado |
|---|---|---:|---|
| 1 | `POST /studio/prepare-pipeline` | 200 | `ready` |
| 2 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 3 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 4 | `POST /ai-market/v2/invoke` | 200 | `completed` |

La prueba pagada hizo **cuatro solicitudes al Hub**, no exactamente dos. Las llamadas RPC y de cotización son adicionales. La primera respuesta reunió cotización y autorizaciones. Cada 202 continuó el mismo run con idéntico paquete firmado. Hubo un job raíz y dos llamadas hijas correctas. Después, `run_pipeline(resume=True, ...)` devolvió el mismo resultado local con **cero solicitudes adicionales al Hub**. La prueba y sus verificaciones duraron 11.872 segundos: una observación, no una garantía de latencia.

## Grafo y resultado

El grafo compró `gaia.weather.read@v1` y después `gaia.air.read@v1`, del producto `gaia.gateway`, con `source_hub: https://iot.modelmarket.dev` y `city: Berlin`. `air` esperaba a que terminara `weather`; no recibía los valores meteorológicos. El resultado final fue una lectura firmada de **GAIA-AQ1 (retransmisor Open-Meteo AQ)**, dispositivo `om-aq-01`, a las **2026-09-30 04:24:34 UTC**. Las pruebas registran el éxito meteorológico, pero no su lectura intermedia. Son datos del retransmisor, no prueba de un sensor físico separado en Berlín.

| Indicador | Valor |
|---|---:|
| PM2.5 | 8.8 µg/m³ |
| PM10 | 11.1 µg/m³ |
| US AQI | 33 |
| European AQI | 24 |

## Presupuesto y liquidación

El pagador fue `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c` y el destinatario USDC, `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`. Se usó el USDC existente en Base mainnet, chain ID 8453. El comprador eligió un techo ETH/USD de 6000; la última estimación conservadora registrada fue $0.1195256567368, inferior a $1. El gasto real en dólares usa la cotización Coinbase **$2673.555/ETH** observada en la prueba. Ni esta cotización ni la estimación son un límite estricto en dólares impuesto en cadena.

| Concepto | Importe |
|---|---:|
| Servicios / USDC | 0.002 USDC |
| Gas (L2 + L1) | 0.000001003418744789 ETH |
| Gas / USD | ≈ $0.00268270 |
| Total / USD | ≈ $0.00468270 |

## Pruebas adicionales y verificación

Un grafo LOGOS gratuito de dos pasos terminó con el mismo SDK sin monedero, RPC ni techo de cotización, en dos solicitudes al Hub. Un grafo pagado con presupuesto total $0.003 superó la cotización de servicios, pero se rechazó localmente por no cubrir la reserva de comisiones: una preparación, ninguna invocación raíz ni pago. Pasaron **84 pruebas locales** y **4 pruebas de pago Anvil**. Cubren pérdida de respuesta, reintentos idénticos, recuperación sin firmante después de firmar, rechazo por gas, red o autorización incorrecta, bloqueo de archivo y fallo terminal de un hijo.

La CLI también completó un grafo gratuito en producción y devolvió el mismo resultado guardado al reanudar sin clave del monedero.

Ambas transacciones tuvieron éxito. Los importes USDC y comisiones coincidieron con los cambios de saldo. Se verificaron firmas raíz y de factura con la clave del Hub registrada antes del test, hashes de factura/resultado y dos referencias a recibos hijos. La firma del aire se comprobó con su clave incluida, sin fijar una identidad de dispositivo de forma independiente. Las pruebas públicas contienen resultados firmados y recibos de red, no clave privada, token de ejecución ni transacciones firmadas en bruto.

Sigue siendo una prueba autorizada por el operador: GAIA y Hub pertenecen al mismo ecosistema y el Hub es el vendedor responsable del cobro. Demuestra pago y subcontratación reales, no demanda independiente. SUB/1 vincula trabajos; la financiación es `buyer_wallet`, los hijos indican `funded_by: own` y no se usó allowance de crédito. No se redesplegaron contratos. La prueba gratuita del SDK no certifica la ruta anterior `/studio/run`, configurada por separado.

## Pruebas y reproducción

- JSON: `codex-one-call-2026-09-30.json` · Blueprint: `codex-one-call-2026-09-30-blueprint.json`
- [API / SDK](https://modelmarket.dev/clients/pipeline-guide/es)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Verificación posterior del acceso de agentes (3.9.0): pasaron 175 pruebas específicas y cuatro pruebas de pago locales con Anvil. Una instalación limpia ejecutó un grafo gratuito por SDK en dos solicitudes al Hub. MCP prepare/invoke/status completó otro grafo gratuito. El pedido pagado original se recuperó con dos GET (manifiesto y estado raíz), sin clave del monedero ni RPC. El propio SDK verificó los recibos del Hub. No hubo nuevos pagos mainnet en esta comprobación. El Hub distribuye el wheel, con SHA-256 en el manifiesto firmado; no se publicó en PyPI.

JSON: `agent-rails-2026-09-30.json`

## Continuación: vendedor independiente, 3.10.1

Codex añadió SELLER-OP/1 y desplegó Hub con migraciones 44–45. La guía de cadenas detalla protocolo y límites. Pasaron **223 pruebas específicas y 6 escenarios locales Anvil**, incluyendo dos liquidaciones entre hubs separados con un token desechable, una con respuesta perdida. En cada escenario independiente el comprador pagó exactamente 4.000 unidades una sola vez; el vendedor creó y consumió su factura. Son pruebas locales de integración, no nuevas compras mainnet.

En producción se verificaron manifiesto firmado, wheel y cinco guías, una cadena gratuita MCP, otra SDK con dos solicitudes principales y recuperación del pedido pagado original solo mediante GET. No hubo nuevos pagos mainnet desde el monedero de prueba. El listing local weather.witness no tiene una ruta de cobro directo compatible: la preparación devuelve ahora 409/settlement_route_unsupported en lugar de 500, antes de ejecutar o pagar. Su contrato SUB/1 con crédito no cambia. No se actualizó ni compró a un peer independiente de producción; esa ruta se probó con dos hubs controlados en Anvil.

Evidencia depurada: `seller-operations-2026-09-30.json`. No se publican claves privadas, tokens de operación ni paquetes de transacciones firmadas.

### codex-one-call-2026-09-30-blueprint.json

```json
{
  "nodes": [
    {
      "id": "weather",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.weather.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "input": {
        "city": "Berlin"
      }
    },
    {
      "id": "air",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.air.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "depends_on": [
        "weather"
      ],
      "input": {
        "city": "Berlin"
      }
    }
  ]
}
```

### agent-rails-2026-09-30.json

```json
{
  "version": "3.9.0",
  "wheel_sha256": "b5a3ccc3ec10be2a2c4ae01dd052d60216e1834751550ba206f63b2446ae4014",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "mcp_free_run_id": "paid_838b4c9fceefadc04daee59599a8ff2e",
  "mcp_free_job_id": "job_f3dbbfcd48b38769c2bc5959",
  "sdk_free_run_id": "paid_c997741497bb4fad3c0a6c8183cddea1",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true
}
```

### seller-operations-2026-09-30.json

```json
{
  "version": "3.10.1",
  "wheel_sha256": "32dd7e248a05f9c4052d7d3dd71470e6b3d183d73a786c7795f1e7f4b87c8d94",
  "protocol": "SELLER-OP/1",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "older_wheel_preserved": true,
  "mcp_free_run_id": "paid_20e4b10e6eafcb80199cce1b34a759e2",
  "mcp_free_job_id": "job_78bb0fc253938109f00762c1",
  "sdk_free_run_id": "paid_0d1a123a53176be3c66490aef8e35b46",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true,
  "local_tests": {
    "focused": 223,
    "anvil": 6,
    "independent_seller_anvil": 2,
    "mainnet_independent_seller_test": false
  },
  "seller_quote_smoke": {
    "sku": "weather.witness@v1",
    "status": "preflight_refused",
    "reason": "listing has no supported seller payout or token",
    "http_status": 409,
    "invoke_sent": false,
    "payment_sent": false,
    "invalid_token_rejected": true,
    "recursive_pipeline_rejected": true
  },
  "production_migrations": [
    44,
    45
  ]
}
```

### independent-seller-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "buyer_hub": "https://modelmarket.dev",
  "seller_hub": "https://independentai.network/hub",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "run_id": "paid_356c3e6931dc6a7f4b3bd2640881e04b",
  "job_id": "job_b9aebbd2aa412d310b14c91e",
  "operation_id": "op_c6d88ad6d742603073eaa6eab5326d38",
  "source_hub": "https://independentai.network/hub",
  "payment_rail": "independent_seller",
  "pay_to": "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",
  "tx_hash": "0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919",
  "success": true,
  "status": "completed",
  "final_result": {
    "block_number": 51980340,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "service_usdc": ".002",
  "gas_wei": "603167313432",
  "usd_policy_ceiling": 6000,
  "prior_cost_at_ceiling_usd": "0.016197102150400000",
  "new_cost_at_ceiling_usd": "0.005619003880592000",
  "cumulative_cost_at_ceiling_usd": "0.021816106030992000",
  "approved_total_usd": "1",
  "new_order_limit_usd": ".15",
  "controlled_client_response_loss": true,
  "signed_result_verified": true,
  "http_requests": [
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "modelmarket.dev",
      "path": "/ai-market/v2/invoke",
      "http_status": 200
    },
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    }
  ],
  "operator_note": "Separate production hub, keys, database and seller wallet; both deployments administered by the same user. Not evidence of an independently owned customer."
}
```

### native-price-oracle-2026-09-30.json

```json
{
  "source": "chainlink_base_eth_usd",
  "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
  "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
  "observations": [
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    },
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    }
  ],
  "margin_percent": 25,
  "max_age_s": 1500,
  "manual_floor_usd": null,
  "native_usd_ceiling": "3323.4373758875",
  "checked_at": 1790750864.630485,
  "rpc_providers": [
    "mainnet.base.org",
    "base-rpc.publicnode.com"
  ],
  "new_mainnet_payments": 0,
  "private_key_used": false,
  "client_version": "3.10.2"
}
```

### witness-prepaid-mainnet-2026-09-30.json

```json
{
  "topup": {
    "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
    "amount_usdc": ".02",
    "fee_wei": "500743844349",
    "budget_check": {
      "service_usdc": "0.02",
      "native_fee_bound_wei": "4832812118600",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751427.5852952
      },
      "l1_upper_bound_wei": "12328121186",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.08608637759766899500",
      "checked_at": 1790751427.585309
    },
    "redeem_status": 200,
    "redeem_result": {
      "success": true,
      "status": "credited",
      "nonce": "0x9078baf0077009ef3f0c29a7baea1458ec130c16600df38260e1e71153e763a1",
      "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
      "credited_usd": 0.02,
      "chain": "base",
      "paid_usd": 0.02,
      "idempotent_replay": false,
      "protocol_version": "v2"
    }
  },
  "purchase": {
    "result": {
      "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
      "status": "completed",
      "busy": false,
      "bill_of_materials": {
        "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "funding": "buyer_wallet",
        "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
        "status": "completed",
        "budget_usd": 0.002,
        "total_usd": 0.002,
        "remaining_budget_usd": 0.0,
        "payment_unresolved": [],
        "steps": [
          {
            "id": "witness",
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "source_hub": "local",
            "status": "succeeded",
            "quoted_usd": 0.002,
            "payment_rail": "seller_direct",
            "terms": {
              "amount_units": "2000",
              "amount_usd": 0.002,
              "chain": "base",
              "chain_id": 8453,
              "decimals": 6,
              "eip712_name": "USD Coin",
              "eip712_version": "2",
              "fee_to": "",
              "fee_units": "0",
              "min_confirmations": 1,
              "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "seller_units": "2000",
              "token": "USDC",
              "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            },
            "success": true,
            "status_code": 200,
            "receipt": {
              "capability_id": "weather.witness@v1",
              "latency_ms": 1738,
              "list_price_usd": 0.002,
              "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
              "price_usd": 0.002,
              "product_id": "weather-witness",
              "signature": {
                "algorithm": "ed25519",
                "pq_algorithm": "ml-dsa-65",
                "pq_public_key": "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",
                "pq_value": "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",
                "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
              },
              "success": true,
              "timestamp": "2026-09-30T07:01:33Z"
            },
            "job": {
              "depth": 1,
              "funded_by": "own",
              "job_id": "job_db9c841f8a360f04c891a68b",
              "node": "node_228186546b7fac0f4d89706a",
              "parent": "node_ba3a877444eda0486258c30b"
            },
            "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
            "payment": {
              "amount_usd": 0.002,
              "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
              "block_number": 51981171,
              "chain": "base",
              "confirmations": 2,
              "fee_units": "0",
              "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
              "paid_units": "2000",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "token": "USDC",
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "verified_at": 1790751691.358382
            },
            "started_at": 1790751691.358526,
            "finished_at": 1790751693.5381346,
            "price_usd": 0.002
          }
        ],
        "created_at": 1790751593.7525403,
        "completed_at": 1790751693.53815,
        "job_id": "job_db9c841f8a360f04c891a68b",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      },
      "next_step": null,
      "final_result": {
        "agreement": {
          "agree": true,
          "location_km": 0.0,
          "max_km": 75.0,
          "max_time_apart_s": 7200,
          "reasons": [],
          "time_apart_s": 0
        },
        "air": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
            "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
          },
          "capability_id": "gaia.air.read@v1",
          "reading": {
            "device_id": "om-aq-01",
            "firmware": "1.0.0",
            "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
            "seq": 184,
            "site": "live-air-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "co2_ppm": "ppm",
              "european_aqi": "EAQI",
              "pm10_ugm3": "ug/m3",
              "pm2_5_ugm3": "ug/m3",
              "us_aqi": "US AQI"
            },
            "values": {
              "european_aqi": 22.0,
              "pm10_ugm3": 12.8,
              "pm2_5_ugm3": 9.9,
              "us_aqi": 33.0
            }
          },
          "resolved": {
            "device_id": "om-aq-01",
            "latitude": 52.52,
            "longitude": 13.41,
            "matched_place": "Berlin",
            "requested": "Berlin"
          }
        },
        "children": [
          {
            "capability_id": "gaia.weather.read@v1",
            "funded_by": "own",
            "node": "node_766d429147ff1048f8f0fc11",
            "price_usd": 0.001,
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
          },
          {
            "capability_id": "gaia.air.read@v1",
            "funded_by": "own",
            "node": "node_db5caa18e04cca2e44466d23",
            "price_usd": 0.001,
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
          }
        ],
        "funding": "fixed-price",
        "job": {
          "depth": 1,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "node": "node_228186546b7fac0f4d89706a"
        },
        "place": {
          "city": "Berlin"
        },
        "weather": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
            "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
          },
          "capability_id": "gaia.weather.read@v1",
          "reading": {
            "device_id": "om-wx-01",
            "firmware": "1.0.0",
            "model": "GAIA-WS1 (Open-Meteo relay)",
            "seq": 231,
            "site": "live-weather-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "humidity_pct": "percent",
              "pressure_hpa": "hPa",
              "temperature_c": "cel",
              "wind_mps": "m/s"
            },
            "values": {
              "humidity_pct": 64.0,
              "pressure_hpa": 1020.3,
              "temperature_c": 14.5,
              "wind_mps": 2.82
            }
          },
          "resolved": {
            "device_id": "om-wx-01",
            "distance_km": 0.0,
            "matched_place": "Berlin",
            "relay_latitude": 52.52,
            "relay_longitude": 13.41,
            "requested": "Berlin"
          }
        },
        "witness": "weather-witness/1"
      },
      "detail": "",
      "success": true,
      "price_usd": 0,
      "product_id": "hephaestus",
      "capability_id": "pipeline.run@v1",
      "result": {
        "status": "completed",
        "final_result": {
          "agreement": {
            "agree": true,
            "location_km": 0.0,
            "max_km": 75.0,
            "max_time_apart_s": 7200,
            "reasons": [],
            "time_apart_s": 0
          },
          "air": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
              "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
            },
            "capability_id": "gaia.air.read@v1",
            "reading": {
              "device_id": "om-aq-01",
              "firmware": "1.0.0",
              "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
              "seq": 184,
              "site": "live-air-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "co2_ppm": "ppm",
                "european_aqi": "EAQI",
                "pm10_ugm3": "ug/m3",
                "pm2_5_ugm3": "ug/m3",
                "us_aqi": "US AQI"
              },
              "values": {
                "european_aqi": 22.0,
                "pm10_ugm3": 12.8,
                "pm2_5_ugm3": 9.9,
                "us_aqi": 33.0
              }
            },
            "resolved": {
              "device_id": "om-aq-01",
              "latitude": 52.52,
              "longitude": 13.41,
              "matched_place": "Berlin",
              "requested": "Berlin"
            }
          },
          "children": [
            {
              "capability_id": "gaia.weather.read@v1",
              "funded_by": "own",
              "node": "node_766d429147ff1048f8f0fc11",
              "price_usd": 0.001,
              "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
            },
            {
              "capability_id": "gaia.air.read@v1",
              "funded_by": "own",
              "node": "node_db5caa18e04cca2e44466d23",
              "price_usd": 0.001,
              "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
            }
          ],
          "funding": "fixed-price",
          "job": {
            "depth": 1,
            "job_id": "job_db9c841f8a360f04c891a68b",
            "node": "node_228186546b7fac0f4d89706a"
          },
          "place": {
            "city": "Berlin"
          },
          "weather": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
              "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
            },
            "capability_id": "gaia.weather.read@v1",
            "reading": {
              "device_id": "om-wx-01",
              "firmware": "1.0.0",
              "model": "GAIA-WS1 (Open-Meteo relay)",
              "seq": 231,
              "site": "live-weather-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "humidity_pct": "percent",
                "pressure_hpa": "hPa",
                "temperature_c": "cel",
                "wind_mps": "m/s"
              },
              "values": {
                "humidity_pct": 64.0,
                "pressure_hpa": 1020.3,
                "temperature_c": 14.5,
                "wind_mps": 2.82
              }
            },
            "resolved": {
              "device_id": "om-wx-01",
              "distance_km": 0.0,
              "matched_place": "Berlin",
              "relay_latitude": 52.52,
              "relay_longitude": 13.41,
              "requested": "Berlin"
            }
          },
          "witness": "weather-witness/1"
        },
        "bill_of_materials": {
          "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
          "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
          "funding": "buyer_wallet",
          "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
          "status": "completed",
          "budget_usd": 0.002,
          "total_usd": 0.002,
          "remaining_budget_usd": 0.0,
          "payment_unresolved": [],
          "steps": [
            {
              "id": "witness",
              "product_id": "weather-witness",
              "capability_id": "weather.witness@v1",
              "source_hub": "local",
              "status": "succeeded",
              "quoted_usd": 0.002,
              "payment_rail": "seller_direct",
              "terms": {
                "amount_units": "2000",
                "amount_usd": 0.002,
                "chain": "base",
                "chain_id": 8453,
                "decimals": 6,
                "eip712_name": "USD Coin",
                "eip712_version": "2",
                "fee_to": "",
                "fee_units": "0",
                "min_confirmations": 1,
                "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "seller_units": "2000",
                "token": "USDC",
                "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
              },
              "success": true,
              "status_code": 200,
              "receipt": {
                "capability_id": "weather.witness@v1",
                "latency_ms": 1738,
                "list_price_usd": 0.002,
                "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
                "price_usd": 0.002,
                "product_id": "weather-witness",
                "signature": {
                  "algorithm": "ed25519",
                  "pq_algorithm": "ml-dsa-65",
                  "pq_public_key": "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",
                  "pq_value": "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",
                  "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
                },
                "success": true,
                "timestamp": "2026-09-30T07:01:33Z"
              },
              "job": {
                "depth": 1,
                "funded_by": "own",
                "job_id": "job_db9c841f8a360f04c891a68b",
                "node": "node_228186546b7fac0f4d89706a",
                "parent": "node_ba3a877444eda0486258c30b"
              },
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "payment": {
                "amount_usd": 0.002,
                "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
                "block_number": 51981171,
                "chain": "base",
                "confirmations": 2,
                "fee_units": "0",
                "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
                "paid_units": "2000",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "token": "USDC",
                "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
                "verified_at": 1790751691.358382
              },
              "started_at": 1790751691.358526,
              "finished_at": 1790751693.5381346,
              "price_usd": 0.002
            }
          ],
          "created_at": 1790751593.7525403,
          "completed_at": 1790751693.53815,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "signature": {
            "algorithm": "ed25519",
            "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
            "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
            "pq_algorithm": "ml-dsa-65",
            "pq_public_key": "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",
            "pq_value": "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"
          }
        }
      },
      "subcontracting": {
        "job_id": "job_db9c841f8a360f04c891a68b",
        "funding": "buyer_wallet",
        "nodes": [
          {
            "node": "node_ba3a877444eda0486258c30b",
            "parent": "",
            "depth": 0,
            "product_id": "hephaestus",
            "capability_id": "pipeline.run@v1",
            "price_usd": 0.0,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-yKlROh9qyPfcrewL0EbuIbu7PLEh4omMZDqPYz4aNbA=",
            "receipt_id": "urn:aimarket:pipeline:paid_580f85c4a2f4deba7a83bc26140fc558"
          },
          {
            "node": "node_228186546b7fac0f4d89706a",
            "parent": "node_ba3a877444eda0486258c30b",
            "depth": 1,
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "price_usd": 0.002,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY=",
            "receipt_id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e"
          },
          {
            "node": "node_db5caa18e04cca2e44466d23",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.air.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY=",
            "receipt_id": "urn:uuid:645e7e42-42fa-4e42-91d6-b84cb2344b67"
          },
          {
            "node": "node_766d429147ff1048f8f0fc11",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.weather.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY=",
            "receipt_id": "urn:uuid:c18abe0c-33aa-4ea7-9a25-97c7f167293f"
          }
        ],
        "budget_usd": 0.002,
        "spent_usd": 0.002,
        "unspent_budget_usd": 0.0
      },
      "protocol_version": "v2",
      "receipt": {
        "kind": "pipeline.run/1",
        "run_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "job_id": "job_db9c841f8a360f04c891a68b",
        "product_id": "hephaestus",
        "capability_id": "pipeline.run@v1",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "success": true,
        "parents": [
          {
            "id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e",
            "digestSRI": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY="
          }
        ],
        "result_digest": "04b959e9264be0c3203b005819cd8ded9e468532e94647122fba0004aa26571a",
        "bill_digest": "7bb9257690299bad9d875484b5f4741c0a39a6a781bab36b647e5d333744fd4e",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "rSfbsQKIdwcJccPjytyKVqcvOZ4Lk1pcQWDm5RnuWIyGA/Y3cCmqNs1I/6kGVQQmRwtj6USCIo+LXip0UgMMCQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      }
    },
    "tx_hashes": {
      "witness": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272"
    },
    "fee_wei": "500681057186",
    "budget_check": {
      "service_usdc": "0.002",
      "native_fee_bound_wei": "4774506722000",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751690.875712
      },
      "l1_upper_bound_wei": "11745067220",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.0678923037121811500",
      "checked_at": 1790751690.875724
    }
  },
  "account_starting_grant_usd": 0,
  "conservative_cumulative_usd": "0.047149423922618862625",
  "cumulative_limit_usd": "1",
  "accounting_note": "Earlier runs retain their historical 6000 USD/ETH ceiling; new gas is valued at the saved oracle price plus 25%. Entire 0.02 USDC deposit is counted; later prepaid child debits are not counted twice.",
  "provider_account_after": {
    "balance_usd": 0.018,
    "spent_usd": 0.002,
    "granted_usd": 0,
    "topped_up_usd": 0.02,
    "collateral_usd": 0
  }
}
```

### gas-sponsorship-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.11.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_38c0a7c6c2fe992186116a2822205d3d",
  "job_id": "job_dc0b37b785a7f358bfb30b23",
  "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516607663289",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1163241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_38c0a7c6c2fe992186116a2822205d3d/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "funding": {
    "sponsor": "0x663E0C31925EAd877fD9414C2e1862fa50b2650b",
    "payer": "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
    "tx_hash": "0x73cff1e1da3242a2f3c77e1f7389fc5ed23f7625634975d7dbef2086bcfcfc78",
    "funding_wei": "20000000000000",
    "funding_fee_wei": "133597605703",
    "budget_check": {
      "service_usdc": "0",
      "native_fee_bound_wei": "6235958489800",
      "native_usd_ceiling": "3336.4504743875",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3336.4504743875",
        "checked_at": 1790756935.732915
      },
      "l1_upper_bound_wei": "26359584898",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.07080596666155396807999750",
      "checked_at": 1790756935.7329228
    },
    "prior_total_usd": "0.047149423922618862625",
    "cumulative_conservative_usd": "0.1143241752052936711504319125",
    "budget_limit_usd": "1",
    "funding_counted_in_full": true
  },
  "local_validation": {
    "focused_regression_passed": 178,
    "mcp_after_static_card_sync_passed": 81,
    "oracle_and_relay_passed": 37,
    "anvil_zero_eth_buyer_passed": 1
  },
  "final_result": {
    "block_number": 51983924,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "steps": [
    {
      "id": "summary",
      "product_id": "prod-logos",
      "capability_id": "logos.federation.summary@v1",
      "source_hub": "https://logos.modelmarket.dev",
      "status": "succeeded",
      "price_usd": 0.0
    },
    {
      "id": "network",
      "product_id": "kova-network",
      "capability_id": "kova.network.status@v1",
      "source_hub": "https://independentai.network/hub",
      "status": "succeeded",
      "price_usd": 0.002,
      "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857"
    }
  ]
}
```

### provider-recovery-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.12.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_7f29b95f0ebf51092a52883053172f93",
  "job_id": "job_4ca838ba5866031111ed1778",
  "tx_hash": "0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516795861906",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1183241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_7f29b95f0ebf51092a52883053172f93/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "final_result": {
    "block_number": 51984647,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "recovery_proof": {
    "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
    "isolated_copy_recovered": true,
    "production_ledgers_modified": false,
    "new_payments": 0,
    "new_provider_invokes": 0,
    "status_reads": [
      {
        "method": "GET",
        "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5"
      }
    ],
    "provider_result": {
      "capability_id": "kova.network.status@v1",
      "input_sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
      "product_id": "kova-network",
      "protocol": "PROVIDER-OP/1",
      "result": {
        "block_number": 51984647,
        "chain": "base",
        "chain_id": 8453,
        "findings": [],
        "score": 100,
        "summary": "Base mainnet is reachable through KOVA.",
        "verdict": "pass"
      },
      "result_signature": "SDpaLWz7Xvwpa4jVM515EFOVv3rtqUUH8skEbfXBShKDEQ8vuvgy6rraGxFNXJr9eOZevFArDr7Z3Hxk36BECQ==",
      "signature": "4i9lfCn+KRuVi2NUW49E2DsnziK2nbFivGD+Ciex8VwFkBVZUFDXVedYIvgCSoU2H4ZaVhf7Rp7WLflOsl1lCA==",
      "status": "completed"
    }
  },
  "scope": "Live provider journal after restart; lost seller response simulated in an isolated database copy. Production ledgers were not altered.",
  "provider_gateway_authenticated": true,
  "local_validation": {
    "recovery_payment_and_peer_tests": 76,
    "recovery_and_pipeline_tests": 36,
    "kova_operations_and_api_tests": 22,
    "kova_bound_signature_followup_tests": 9
  }
}
```

### refund-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.13.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "seller": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
  "operator_owned_fixture": true,
  "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
  "job_id": "job_da32d04e2b39e575684e9d50",
  "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
  "service_usdc": ".001",
  "refunded_usdc": ".001",
  "buyer_gas_wei": "0",
  "transactions": [
    {
      "tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "620782210434"
    },
    {
      "tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "487781767367"
    }
  ],
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "buyer_usdc_balance_restored": true,
  "seller_usdc_balance_restored": true,
  "controlled_refund_reply_loss": true,
  "original_bill_unchanged": true,
  "same_refund_retry": true,
  "credit_note": {
    "amount_units": "1000",
    "amount_usdc": "0.001",
    "buyer_gas_fee_units": "0",
    "chain_id": 8453,
    "from": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
    "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
    "kind": "pipeline.refund/1",
    "original_tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
    "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
    "refund_tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
    "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
    "signature": {
      "algorithm": "ed25519",
      "pq_algorithm": "ml-dsa-65",
      "pq_public_key": "rlbjoYoMxak6Xkzq71s4pmSk9Zs8ViCHbt4rOmgOOVw9qftYL2L09AIksUkASfiCpuoNSNH38vbWr2w2r9ODwR/go8O1EfMh0l9Ag8FhjOZAcglPoC1FDPuBISP6W2Ab8olpAluiGg6qydCe1sq7l5/yo+cVISqqg7jYs7os27z5Gy1kbmu+SquK20lzKdg606El8uph8yD+d/FJ5FCYfIxATS0RpPMTXgqHWKz+NcFM8lQe1Jofe6Ef51uUtSPn5E6nsHTyT1XRRMl0jCZTcFrsQ7s4mwleDWfd+LvmZZgMu9O2H13hM27QKa7fV9SLqGYnzd8PF/mDoHXKUTOx14re0quFRS/ZiwHLlmQA5E+X4EeOWeggRcTusHM6gXMqNyfwdSBPpalNMNlNgbDz0o0AxsrY0nGR4Get05zyejIHpxxdjBJBGej2a59V5s27UkqY6DB0R5LjuR1Udol5hSA78jB7Q/HvTPiebVs9dNkqlTudRToLE08EULaHw1V6GssR3OXrvii6kKKIuHY0buml2ttBuHtV/OGqUHbhx2DFx/rEx0i4rSfl/Iyc/UbjomHBPzqwbh4O8pki4C5jBICKNzJIJSfELxMGb0pydoCqqXAC/JX8L7FsZKUQivAffeFQzJE8nPACkbvCRlHahBfs9JBCuZBCKxOzurvUQbMahPMkxk9LyBGn3nFjgXQ+VH8xcR99Rx50H0DoHPd0b9Z5duC/GApik2FGFBMDvRkzrsfQqzL18nQBt/i2mTPFMjsM0GrZOoPRbkzX6sIMiP2iJmUZiwYGtz/gLkj8W1jXV6MUksJXTVoBjJn/EuLp0/57hk6cB/XWwPbMOSoQII1zPWEksxbkiT324Kz3rxHsN/cLNJU3U32EHnCX1i5xj5WCb6fSbcT9HC2EZB6k9q4HVBitcrFZD8Z75C6kj6nXD6PpWjmQ8OJQv7hdMzH0DQryNFwwqbsJwJrtId99nCl/gL5QeiOG6SCpSs9nIX1IYGtpTPd3tXiPyvC5wlM97WbyIxo73pkz3zkkzcqQHESzc4PzzOq+Qo5irrB4H/Vhg2+zOgo37pRKWz3BpaZEAsmep2nN+Unv3dfamP3j/SfVPA2bgUupcJXziks7cCEvZGC2PmrSqpk8qSHoo2nlEv6WiR7iplp6GreQ4KLFRJxGx2fvOGfM5BjndJFsMazKSvOZGOCzz2pHMK6hH9YUl1dtC56l02kX8NvldyjD6jpveEiZe9mtSFIwQdanpCfgPH+ts08bxYn9gVwgxgftx22KupnRDOs8PntO6lM8oWXLmxLa1/LkWtW5OJfvNJ7eB4nDaU0JmSzhZ5yINFEeZoZ93PBA114taTQQiUL416RXI59SNv/h+OQfz366mXb5RuWyfX/qh/nJ6176QkdDJsmoX2wSbsmXO2I/GqzfnD18K0OlwkBF4FF2IG70/NVTB3fTQDHVsFAXjzT9P56k25oCsLeQ/l0pUFx7Nz1iw3TOI5iDgrilpoIzifd4j/piNthWRRcfrAXwU/oRHH1RyMJkm7zJ70vQ9AKf1r6orNA5X7XFDH6ZY/9OrEpgSNCSMH22jc3ukDKtsqj9/goipxoqqHQecH7WJl8FGHdlfhnKW0aFodCsaJ9KEwMsBB2RSWyHoPtvdaX9V3AAAcsINYU1ZbLavSng9UDTRyTw1wpCcIANNLT6ir+XIYsO675MQMgIt5i0pYJR87eITjv1aQhOicyzFdisj5GjGZqt6/pc/rActbK+N0gokCA7Rp2/ilWQxoUnsW/v6QCHTYfiqsJmtpnpstanP7YkVMWfveMzAcov/J7cRgQjaPCJ2AFymoIiMdYnI4h4Om2WDCy77O9wlXmXraQHilNoUn7aXLteHdEYt/wGEm0jzbUh2FsdFPDllmvm9muFCwlvm+rgM9wLcOOAwy+gcDwy+hVyuSBLygMpy63EGZG1TcPyantmSUINAdv+HwJZXkc72BvQgvX1B7Kdi9IwMpicvfaU0z9ztqo8rzbPTVU+ef6nMf2Dq2GNOLKJQv6HY1xS1LH51FMEC2lJM1iOi4aszLUxNonB+gsVMBI7oCgY4nC5Cfrcy8G1+GPh2tkk471lUEZWYBC0jvtg1oiFHmutJ19uPz1GHNhC/wItSt5seJ5SveU/puFm1Mmcr/RdmNF9n2rm0z3N6oU7mDZ5dXna8DjSprT4DQU3iIv0fNFZ7PxMkaUTcvoOVSuMA9cOq6LM9EKaECweNpsxwNnD6KJGqbYWBQs2oDcRdPFmXk0Qq17GatW2x6ipoHUNrwWbUJtNnFtHgNRdQCldDrlaOepc0qd+m0V4cuQzLzy/cuDnyv59kPm5ASRqT3GlSt7gLvd5TyQiQbZAOzCCwBfUS+rQfY0U9YNCQZ+ca1d6chqakPaiooFTpEL1AfBuz8u8gUaR4mwe40CYcuNvpX32Mz+A55ENxTlRyZLCnuZ5ik+pK+OHxFVieL3WO7YgoiQIE7FNI/DOonTTff72OOhCJn+VonC+MXQZb2hFeQiY5S/6NrgueNhoEvio2ICzAuzccFACPjPLnUDcH2pOjNEtHLLWYeIzUVDyFzOt2a9IocTNnoKRaio=",
      "pq_value": "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",
      "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
      "value": "uCRKNXnCxZpCl+4d2SitFnEX6PjvYdqq3trKwowCGjPDm7QPKT2SzWzSJJgJ81FI9fekrgy9ti+HIuhSxGcrDA=="
    },
    "step_id": "proof",
    "to": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
    "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
  },
  "final_result": {
    "operator_owned_fixture": true,
    "refund_test": "2026-09-30",
    "result": "delivered"
  },
  "cumulative_conservative_usd": "0.1193241752052936711504319125",
  "gross_purchase_counted_despite_refund": true,
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "same_refund_after_hub_restart": true,
  "original_result_after_hub_restart": true,
  "temporary_listing_removed": true
}
```

### ethereum-profile-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.14.0",
  "chain_id": 1,
  "token_contract": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "token_metadata": {
    "name": "USD Coin",
    "version": "2",
    "decimals": 6
  },
  "native_price": {
    "source": "chainlink_ethereum_eth_usd",
    "feed": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "sequencer_feed": null,
    "observations": [
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      },
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      }
    ],
    "margin_percent": 25,
    "max_age_s": 3900,
    "manual_floor_usd": null,
    "native_usd_ceiling": "3354.3941056125",
    "checked_at": 1790761170.358094
  },
  "read_only": true,
  "new_mainnet_transactions": 0,
  "sources": [
    "https://developers.circle.com/stablecoins/usdc-contract-addresses",
    "https://data.chain.link/feeds/ethereum/mainnet/eth-usd",
    "https://reference-data-directory.vercel.app/feeds-mainnet.json"
  ]
}
```
