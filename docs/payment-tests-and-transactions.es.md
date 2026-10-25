# Pruebas de pagos y transacciones

**EN** [English](payment-tests-and-transactions.md) · **RU** [Русский](payment-tests-and-transactions.ru.md) · **ES** [Español](payment-tests-and-transactions.es.md) · **FR** [Français](payment-tests-and-transactions.fr.md) · **ZH** [中文](payment-tests-and-transactions.zh.md)

Verificación registrada: **2026-10-23**. Esta guía explica el checkout, la asignación de
transacciones, el libro interno UNI, las pruebas de recuperación y el alcance de sus resultados.

## 1. Evidencia y alcance

La tabla conserva la verificación inicial; los resultados más recientes figuran inmediatamente después.

| Verificación | Resultado registrado | Qué fue real y qué se simuló |
| --- | --- | --- |
| Pruebas de recuperación de pagos | **50 passed, sin omisiones**: 25 casos SQLite + 25 PostgreSQL | Almacenes, firmas, concurrencia y terminación de procesos hijos reales; transacciones sintéticas y respuestas simuladas de cadena/proveedor |
| Conjunto principal de Factory | **5 828 passed**, 60 omitidos | Selección principal; sus pruebas de pagos no deben sumarse otra vez a este número |
| Ejecución adicional PostgreSQL | PostgreSQL **18.3**, clúster temporal detenido al finalizar | Base local independiente; no se utilizó una base de producción |

Evidencia: [JUnit de pagos](../artifacts/quality-audit-2026-10-23/payments-sqlite-postgres.xml),
[manifiesto de verificación](../artifacts/quality-audit-2026-10-23/verification.json),
[informe completo de calidad](quality-audit-2026-10-23.md).
Un resultado local en verde **no demuestra una nueva transferencia de dinero real**. El
[registro de despliegue fechado](../artifacts/payment-production-deploy-2026-10-23/deployment-summary.json)
también indica que no se ejecutó un pago positivo de extremo a extremo ni un reembolso en cadena con fondos reales.
Las transacciones históricas reales están en el [diario en cadena](onchain-journal.md) y el
[caso de una invocación pagada](case-study-paid-invoke.md); son evidencias fechadas, no una comprobación de disponibilidad actual.

La parametrización PostgreSQL corresponde al libro UNI. Commerce de Factory y los almacenes KOVA/SaaS mantienen sus propias bases SQLite; no se afirma haber probado pedidos checkout sobre PostgreSQL.

### Auditoría de seguimiento: fallos y escenarios críticos

Última verificación: **6 139 passed, 84 subpruebas; 24 omisiones intencionadas de sondas live** en la suite local completa; **450 comprobaciones de pagos/UNI sin omisiones financieras**. Una ejecución separada en producción superó **32 pruebas: 24 live y 8 contratos, sin omisiones**. Las **13 funciones financieras críticas** alcanzaron 100% de líneas/ramas con umbrales obligatorios. Cobertura global: **60.8% líneas / 50.0% ramas**. La auditoría de dependencias sigue limpia.

Las pruebas finales añaden siete escenarios con ambas variantes de almacenamiento: hash vacío o de otra red, cotización consumida durante la espera del bloqueo asíncrono real, cotización antigua sin importe, reintento del hash fijado, red persistida no admitida y conflicto al insertar el pedido. Un pedido competidor realmente confirmado devuelve **409**, sin otra licencia ni exposición de su clave. Véanse los [límites de confirmación](../tests/test_payment_confirmation_boundaries.py) y la [evidencia actual](quality-audit-2026-10-23.md#braces-resolution). La función de finalización no tiene ramas estáticas; se prueba su limpieza ante excepciones. El porcentaje corresponde a las funciones críticas indicadas, no a todas las integraciones o fallos posibles en producción.

Se añaden pruebas HTTP de fallos antes/después del commit del pedido, escritura del almacén pendiente,
clave de cotización ausente/truncada e indisponibilidad de RPC e historial. Un **503** conserva la recuperación
con la misma transacción; un commit ambiguo mantiene su asignación de uso único. Un estado `confirmed`
sin pedido confirmado en la base nunca se considera éxito. Restaure la clave original desde una copia;
no la sustituya por otra.
El historial vacío/con tipo incorrecto y el historial UNI inaccesible bloquean la liquidación. Un archivo pendiente corrupto se conserva hasta restaurarlo; las credenciales RPC no aparecen en errores públicos ni en los registros del checkout.
Los saldos Solana deben ser finitos y no negativos; se validan el importe SPL bruto y sus decimales.
Las pruebas Ed25519 reales rechazan firmas malformadas, claves de orden pequeño y pruebas de otro cliente,
sitio o transferencia. Las pruebas de reembolso rechazan retiros desconocidos, no elegibles,
ya difundidos o con importes inválidos sin acreditar fondos.

Véanse [resultados de seguimiento y límites](quality-audit-2026-10-23.md#follow-up).

### Producción y las 34 omisiones originales

Se ejecutaron **los 34 casos originalmente omitidos**. Cinco casos de archivos usaron un volumen temporal sensible a mayúsculas; tres casos Compose procesan las configuraciones reales con valores sintéticos, sin resolver archivos secretos del despliegue; dos controles CSS comprueban las importaciones actuales y los tipos locales; el badge de KOVA refleja **59 pruebas realmente superadas**. Los errores de configuración ahora fallan en vez de omitir pruebas.

Los 23 casos live originales se ejecutaron en producción, junto con un nuevo control de invoke sin pago. Se comprueba la privacidad del health público de SKOPOS; el estado de la flota se consulta con la clave del operador y una petición sin pago debe devolver **402**. El runner SSH mantiene las claves en memoria, limita los túneles a loopback y los cierra al terminar. No se activan canales de pago, transferencias, licencias ni LLM. La suite local conserva sus 24 sondas live desactivadas por defecto; esos mismos casos pasaron en producción. Las selecciones se solapan y sus cifras no deben sumarse indiscriminadamente.

Se añaden **88 casos de liquidación** en SQLite y PostgreSQL: fallos de firma y de triggers reales, ocho salidas abruptas de procesos hijos tras insertar el recibo, reintentos concurrentes, reservas agotadas e historial antiguo incompleto. Saldo, libro mayor, retiro/reserva y recibo firmado se confirman juntos; un fallo revierte todo. El reintento devuelve el recibo almacenado; las claves completas siguen siendo distintas aunque compartan los primeros 128 caracteres. Los recibos JSON de tipo incorrecto y los saldos desconocidos bloquean la operación. La ausencia de un recibo o reserva antiguos bloquea la operación hasta su conciliación. Los siete objetivos nuevos al 100% son `charge`, `withdraw_to_chain`, `hold`, `spend_hold`, `release_hold`, `_credit` de `UniWalletService`, e `issue_receipt`.

**Los cambios UNI son locales y esta auditoría no los ha desplegado.** Las sondas verifican la versión activa, no la presencia de estos cambios. Véanse las [pruebas por cada omisión](quality-audit-2026-10-23.md#skip-resolution).

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-live-contracts \
  "$PYTHON" scripts/run_ecosystem_live_tests.py --ssh-host factory-vps \
  --skopos-ssh-host skopos-vps
```

## 2. Una compra, paso a paso

1. Un cliente autenticado llama a `POST /api/payment/create`. El servidor toma el precio del catálogo,
   ignora el importe enviado por el cliente y emite una **cotización de una hora** vinculada al cliente,
   producto, sitio, red, token y destinatario. Factory acepta **USDT/USDC**, no ETH/SOL como un importe en USD.
2. El cliente transfiere el token cotizado en la red indicada. `payment_id` identifica la cotización
   interna; `tx_hash` identifica la transacción de blockchain. Un hash o una respuesta HTTP exitosa no prueban el pago.
3. `GET /api/payment/proof/{payment_id}?tx_hash=...` devuelve el mensaje que se debe firmar.
   `POST /api/payment/confirm/{payment_id}` recibe `tx_hash` y `payer_signature`. La prueba vincula
   la transferencia con la compra de ese cliente y su sitio. EVM admite EIP-191 y la comprobación EIP-1271 de carteras de contrato.
4. Se comprueban el recibo, la red, el token, el destinatario, el importe y las confirmaciones.
   La tolerancia de importe de Factory es **0,1%**; `AIFACTORY_PAYMENT_MIN_CONFIRMATIONS` vale **2**
   por defecto, con mínimo 1. Consulte la configuración mediante `GET /api/payment/chains`;
   los demás servicios aplican sus propias reglas.
5. El registro persistente de asignaciones impide gastar de nuevo una transferencia por checkout,
   pilot, financiación de canal, invoke pagado o recarga UNI. Cambiar mayúsculas del hash EVM o quitar
   `0x` no evita la protección; las firmas Solana conservan sus mayúsculas/minúsculas. Una compra válida crea **un pedido y una licencia**.

| Resultado / estado | Significado y acción |
| --- | --- |
| `pending` | La cotización existe; la liquidación no ha terminado |
| `pending_confirmation` | La misma transacción espera confirmaciones; reintentar con el mismo hash |
| `confirmed` | Pedido/licencia creados o recuperados; conservar la respuesta y `order_id` |
| Metadatos `claim_review` | Falta una firma válida del pagador, o la hora de pago es tardía/desconocida; conservar el caso para revisión |
| `confirming` antiguo tras reinicio | Se recupera a un estado reintentable; no bloquea permanentemente al cliente que ya pagó |

Las cotizaciones completadas salen del almacén pendiente: una consulta posterior puede devolver **404**.
No demuestra que se perdió el pago; revise los pedidos del cliente. El reintento recupera un pedido ya
confirmado en la base. Un cambio del catálogo o la rotación de la clave de acceso no modifica la cotización sellada.
Una cotización vencida puede recuperar una transferencia realizada a tiempo al precio original;
una hora tardía o desconocida exige revisión. Respalde `checkout_quote.key` junto con las cotizaciones;
no copie su contenido en registros ni documentación.

## 3. Separar compra, crédito y reembolso

- Checkout compra una licencia y **no añade además UNI gastables**. La financiación de cartera usa
  `/api/uni/topup/confirm` y participa en la protección de uso único de transferencias.
- La recarga por tarjeta del hub verifica la firma del webhook Stripe y recupera la sesión checkout
  guardada; el evento no puede elegir el cliente ni el importe acreditado. Entregas duplicadas o concurrentes
  acreditan una sola vez; sesiones impagadas y dinero de prueba en un hub live no acreditan nada.
  Se prueban también recuperación de webhooks perdidos, comisiones/impuestos, reembolsos, disputas y reversión anterior al pago.
- En el libro UNI, `balance_uni` representa dinero **no reservado** y `hold_uni`, dinero reservado.
  Reservar 600 de 1 000 deja 400 disponibles, sin restar la reserva otra vez hasta cero. `hold_charge`
  consume la reserva; `charge` consume el saldo disponible. El libro debe reflejar el estado de la cartera.
- Un retiro fallido usa `refund_due` persistente: saldo, asiento del reembolso y estado final se
  confirman atómicamente. Reintentos, reinicios y workers concurrentes deben reembolsar una sola vez.
  La comisión no es ingreso antes de una salida exitosa; las comisiones antiguas se revierten al reembolsar.
- Una transacción de cadena enviada o de resultado desconocido **no se reembolsa automáticamente**:
  primero se concilia para evitar pagar tanto la salida como el reembolso interno. El registro actual
  del despliegue indica que el adaptador de salida real UNI no está implementado; una solicitud en cola no prueba difusión.
- KOVA rechaza transferencias anteriores a la factura. SaaS vincula factura/pago con una sola clave API.
  eSIM persiste la intención de compra antes de llamar al proveedor: un timeout ambiguo se convierte en
  `procurement_pending` y se concilia por el ID de transacción del proveedor antes de comprar otra vez.

## 4. Matriz de regresión

| Invariante | Pruebas principales |
| --- | --- |
| Precio del servidor, destinatario, stablecoin, recibo, importe y confirmaciones | [Precio](../tests/test_payment_price_control.py), [seguridad](../tests/test_payment_security.py), [regresiones de auditoría](../tests/test_payment_audit_regressions.py) |
| Una transferencia entre entradas; pagador/sitio; revisión del operador | [Uso único](../tests/test_payment_transfer_single_use.py) |
| Confirmaciones pendientes, reintento y visibilidad del pedido | [API pendiente](../tests/test_payment_confirm_pending_api.py) |
| KOVA → SaaS; cotizaciones; `os._exit(9)` real antes/después del commit de licencia; reservas/reembolsos/comisiones UNI | [Recuperación SQLite/PostgreSQL](../tests/test_payment_chain_recovery.py) |
| Resultado ambiguo del proveedor eSIM, reinicio y protección contra compras duplicadas | [Recuperación de tienda](https://github.com/alexar76/esim-operator-kit/blob/main/store/test/procurement-recovery.test.js), [liquidación rails](https://github.com/alexar76/esim-operator-kit/blob/main/rails/test/settlement.test.js) |
| Aislamiento de credenciales Stripe, firmas webhook, crédito único y reversiones | [Integración de secretos](../tests/test_hub_card_secret_scope.py), [tarjetas del hub](https://github.com/alexar76/aimarket-hub/blob/main/tests/test_card_topup.py) |
| Recuperación ante fallos HTTP/almacén/RPC; historial corrupto; campos sellados | [Integración de fallos](../tests/test_payment_failure_recovery.py) |
| Ed25519 real, codificaciones inválidas, fallo de contrato; elegibilidad y rollback de reembolso | [Pruebas criptográficas](../tests/test_payment_claim_crypto.py), [guardas de reembolso](../tests/test_payment_refund_guards.py) |
| Copia de la clave, corrupción y publicación atómica entre workers | [Pruebas de clave persistente](../tests/test_payment_quote_key.py) |

## 5. Ejecutar localmente

Desde la raíz del repositorio, use Python 3.12, los requirements de la raíz y el código local de
`aimarket-hub` instalados en el entorno de pruebas. El entorno auditado es `.venv-quality`;
`AIFACTORY_TEST_PYTHON` permite elegir otro entorno preparado. La preparación figura en el
[informe de calidad](quality-audit-2026-10-23.md#reproduction). Los fixtures aíslan los almacenes y simulan
los pagos externos; no copie sus opciones stub a producción.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q -ra --timeout=60 \
  tests/test_payment_chain_recovery.py \
  tests/test_payment_failure_recovery.py \
  tests/test_payment_confirmation_boundaries.py \
  tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py \
  tests/test_payment_claim_crypto.py \
  tests/test_payment_quote_key.py \
  tests/test_payment_refund_guards.py \
  tests/test_payment_security.py \
  tests/test_payment_price_control.py \
  tests/test_payment_transfer_single_use.py \
  tests/test_payment_confirm_pending_api.py \
  tests/test_payment_audit_regressions.py
```

Sin `PAYMENT_FIX_TEST_PG_URL`, los casos PostgreSQL se **omiten**, no se aprueban. Para los 50 casos originales y los nuevos escenarios de fallo,
use un clúster PostgreSQL local desechable. El fixture crea y elimina esquemas: **nunca apunte a una
base de producción**. El bloque requiere herramientas PostgreSQL en `PATH` y el puerto local 55487 libre;
la subcapa de shell detiene el clúster incluso si fallan las pruebas.

```bash
(
  set -eu
  PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
  payment_pg_dir=$(mktemp -d /tmp/aicom-payment-pg.XXXXXX)
  initdb -D "$payment_pg_dir/db" -U aicom_test \
    --auth-local=trust --auth-host=trust --no-locale --encoding=UTF8
  pg_ctl -D "$payment_pg_dir/db" -l "$payment_pg_dir/server.log" \
    -o "-h 127.0.0.1 -p 55487 -k $payment_pg_dir" -w start
  trap 'pg_ctl -D "$payment_pg_dir/db" -m fast -w stop' EXIT
  PAYMENT_FIX_TEST_PG_URL=postgresql://aicom_test@127.0.0.1:55487/postgres \
    USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
    "$PYTHON" -m pytest -q -ra --timeout=60 tests/test_payment_chain_recovery.py \
      tests/test_payment_failure_recovery.py tests/test_payment_claim_crypto.py \
      tests/test_payment_refund_guards.py tests/test_payment_quote_key.py \
      tests/test_payment_confirmation_boundaries.py \
      tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py
)
```

Ejecute también los escenarios separados de hub y eSIM. Los casos Node.js requieren Node 20+ y las dependencias instaladas desde el lockfile de cada paquete. Stripe y el proveedor se simulan: estas pruebas no cobran una tarjeta ni compran una eSIM.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
hub_test_python=$("$PYTHON" -c 'import sys; print(sys.executable)')
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q --timeout=60 tests/test_hub_card_secret_scope.py
(
  cd aimarket-hub
  "$hub_test_python" -m pytest -q tests/test_card_topup.py
)
node --test esim-kit/store/test/procurement-recovery.test.js
node --test esim-kit/rails/test/settlement.test.js
```

Un código de salida distinto de cero, timeout, error de recolección u omisión no demuestra que pasó
el escenario correspondiente. Estos comandos no difunden transacciones blockchain.

Los runners Factory exigen **100% de líneas y ramas medidas para las 13 funciones enumeradas en el coverage gate**. CI dispone ahora de PostgreSQL aislado; la selección de 450 casos financieros también pasó en PostgreSQL 16. El control local completo necesita `PAYMENT_FIX_TEST_PG_URL` hacia un clúster temporal de pruebas. Un informe ausente, malformado o sin ramas falla. La cobertura global se publica por separado.

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
PAYMENT_FIX_TEST_PG_URL="${PAYMENT_FIX_TEST_PG_URL:?use a disposable PostgreSQL test cluster}" \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  "$PYTHON" scripts/run_factory_pytest_ci.py --timeout-method=signal
```

## 6. Conciliar una transacción real

Conserve red/chain ID, hash canónico, contrato del token o mint, destinatario, importe bruto y decimales,
recibo/bloque/confirmaciones, hora del bloque, `payment_id`, `order_id`, entrada de asignación e IDs del
libro/recibos. Compárelos con la cotización y el cliente autenticado; no publique claves privadas, tokens
ni contenido de licencias. HTTP **400/422** indica datos inválidos/no verificados; **401/403**, un problema de
autenticación, titularidad o prueba; **409**, conflicto de uso/revisión; **503**, verificación o almacén
deshabilitado/no disponible. Lea el detalle: ningún error justifica por sí solo pedir al cliente que pague otra vez.

Un administrador autorizado revisa `/api/payment/admin/claims` y aprueba mediante
`/api/payment/admin/claims/{payment_id}/approve`; siguen aplicándose las verificaciones de cotización,
cadena y uso único. Revertir el software no revierte una transferencia blockchain: concilie antes de
reembolsar o crear otro pago. Configuración: [habilitar pagos](payment-enable-runbook.md),
[redes](chain-networks.md), [UNI y LIVE](uni-and-live.es.md), [recargas por tarjeta del hub](https://github.com/alexar76/aimarket-hub/blob/main/docs/card-topup.md).
