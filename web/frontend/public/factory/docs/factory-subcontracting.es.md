# AICOM: compra de diagnósticos externos

> 🌐 [English](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.md) · [Русский](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.ru.md) · [Español](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.es.md) · [Français](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.fr.md) · [中文](https://github.com/alexar76/aicom/blob/main/docs/factory-subcontracting.zh.md)

AICOM desarrolla productos con sus propios agentes. Ahora puede comprar un diagnóstico acotado mediante AIMarket antes de otro intento interno de reparación. El proveedor devuelve recomendaciones; el desarrollador de AICOM modifica el código y las comprobaciones QA existentes deciden el avance.

La función está **desactivada por defecto**. Instalarla no activa compras reales, carga saldo, registra proveedores ni envía código fuente.

## Algoritmo de decisión

1. Antes de una tarea de desarrollo, seleccionar incidencias QA high/critical que indiquen un archivo.
2. Asociar cada incidencia (archivo + título) a la última tarea de desarrollo completada. Repetir esa tarea no incrementa el contador. La compra es elegible tras tres observaciones: generación inicial y dos reparaciones internas completadas.
3. Respetar la parada de emergencia, los estados de bloqueo o presupuesto, la ausencia de código generado y `external_diagnostics_allowed: false`. Se mantienen las pausas del operador y los límites de reparación.
4. Preparar una solicitud con **un archivo autorizado**, la incidencia y los criterios de aceptación. Su huella incluye el código y el contrato.
5. Verificar el documento well-known firmado del Hub con claves fijadas por el operador. Buscar capacidades autorizadas, excluir demostraciones, ofertas no disponibles y entradas incompatibles; preferir la menor cotización.
6. Reservar el importe atómicamente dentro de los límites del producto y del día, dejando presupuesto para terminar. Se permite una compra con pago desconocido por producto y dos proveedores por incidencia; no se repite el mismo proveedor. Otra compra requiere una nueva reparación interna completada, incluso después de un informe rechazado.
7. Invocar una sola vez, verificar el recibo y validar el informe. Un tiempo de espera agotado o un pago incierto conserva la reserva y no provoca un reintento pagado automático.
8. Entregar el informe aceptado como datos externos no confiables al desarrollador interno. Registrar la siguiente QA después de una tarea de desarrollo exitosa. El informe no cambia estados ni elimina controles.

Sin oferta, permiso o presupuesto, continúa el proceso interno con sus límites originales. No se vuelve a comprar un diagnóstico aceptado para la misma incidencia. Tras reiniciar, se puede recuperar antes de ejecutarlo internamente si coincide la huella.

## Configuración

Copiar [el ejemplo](https://github.com/alexar76/aicom/blob/main/config/procurement.example.json) a `<AIFACTORY_DATA_ROOT>/config/procurement.json`.

| Parámetro | Significado |
|---|---|
| `enabled` | `true` después de configurar un proveedor probado |
| `hub_url` | Hub HTTPS; sin seguir redirecciones |
| `hub_public_key` | Clave Ed25519 base64 verificada y fijada |
| `hub_pq_public_key` | Clave ML-DSA-65 fijada para firmas híbridas; vacía si solo se usa Ed25519 |
| `providers` | Hasta 10 pares autorizados `product_id` / `capability_id` |
| `share_globs` | Rutas autorizadas relativas al código del producto |
| `per_call_usd` | Máximo por compra: $0.25 inicialmente |
| `per_product_usd` | Gastos y reservas externos: $0.50 |
| `per_day_usd` | $2.00 por día UTC para el diario compartido |
| `completion_reserve_usd` | $0.50 para completar y validar internamente |

Usar una cuenta credits dedicada con saldo mediante `AIFACTORY_PROCUREMENT_API_KEY`; configurar saldo y permisos en el Hub. Esta versión no crea ni firma mandates: una cuenta que los exija rechazará el cliente. Configurar un `AIFACTORY_MAX_PIPELINE_COST_USD` positivo; desactivar el límite general no permite compras ilimitadas.

La configuración se lee para cada tarea elegible. No guardar la API key en JSON. Todos los procesos de la empresa deben compartir directorio de datos y diario para aplicar el mismo límite diario. Instalaciones separadas tienen límites separados.

Solo se admiten servicios ejecutados por el Hub configurado (`source_hub: local`), incluidos endpoints externos que ese Hub invoca. No se compran ofertas federadas ni se entrega presupuesto para subcontratación posterior.

La búsqueda debe devolver explícitamente `credits_eligible: true`. Se excluyen vendedores que exigen pago directo en cadena. Un Hub antiguo sin este campo no ofrece candidatos elegibles: desplegar primero la actualización del Hub. Probar tanto la compatibilidad credits como el contrato de diagnóstico del proveedor.

## Código compartido y contrato

El proveedor debe implementar **`aicom.diagnosis/1`**. Una oferta llamada `code.review@v1` no es automáticamente compatible; debe probarse antes de autorizarla.

La entrada contiene `contract`, `issue`, `fingerprint`, `finding`, `files` y `acceptance`. Se comparte un archivo UTF-8 de hasta 16 000 bytes. Extensiones: py, ts, tsx, js, jsx, go, rs, java, cs, html, css. Se rechazan rutas ocultas, directorios de secretos, enlaces simbólicos, recorridos fuera del ámbito y patrones comunes de credenciales. No se envía el repositorio completo, credenciales, especificación ni logs.

`share_globs` utiliza Python fnmatch: `*` puede incluir separadores de ruta. Definir ámbitos estrechos. La detección de secretos es heurística; el operador debe aprobar el código que pueda compartirse.

Las rutas QA relativas al producto, con el prefijo `code/<product_id>/` o `data/code/<product_id>/`, y las rutas absolutas dentro de su directorio de código se normalizan a la misma identidad. Se rechazan las rutas fuera de ese directorio.

El campo `result` del Hub debe tener esta forma; el ejemplo cita `return 1 / x`:
```json
{
  "contract": "aicom.diagnosis/1",
  "issue": "COPY_FROM_REQUEST",
  "fingerprint": "COPY_FROM_REQUEST",
  "diagnosis": [{
    "file": "app/main.py",
    "line": 2,
    "evidence": "return 1 / x",
    "explanation": "Zero input divides by zero.",
    "suggested_check": "Test divide(0) against the required error contract."
  }]
}
```

Repetir los identificadores de la solicitud y devolver 1–5 observaciones. Cada cita debe coincidir con un fragmento no vacío de la línea indicada del archivo compartido. Explicación y comprobación sugerida son obligatorias y tienen un máximo de 2000 caracteres cada una. Se rechazan versiones obsoletas. Las sugerencias no se ejecutan como comandos.

Aceptar significa validar estructura y referencias al código, no demostrar la corrección del diagnóstico. El desarrollador debe comprobarlo y se mantienen los tests y QA. El recibo firma datos de facturación, no el texto del diagnóstico. Se verifican Ed25519 y la capa ML-DSA-65 presente o requerida con claves fijadas.

## Pagos y recuperación

`state/procurement.sqlite3` guarda compras, huellas, informes, reservas y resultados QA. La ejecución (`in_flight`, `accepted`, `rejected`, `unresolved`) es independiente del pago (`unknown`, `paid`, `not_charged`).

Un informe rechazado puede estar pagado. Este flujo credits no promete reembolsos Pay-on-Verified. Errores HTTP, recibos ausentes o inválidos, desconexiones y procesos interrumpidos dejan el pago desconocido. Bloquean nuevas compras del producto; el trabajo interno puede continuar si queda presupuesto.

Tras comprobar la facturación en el Hub:
```bash
.venv/bin/python scripts/procurement_orders.py list --product PRODUCT_ID
.venv/bin/python scripts/procurement_orders.py reconcile \
  --order PURCHASE_ID --charged-usd 0.10 \
  --evidence "Hub billing reference and reconciliation reason"
```

`list` expresa importes en micro-USD: 100 000 = $0.10. Para otra instalación, usar `--data-root PATH` antes del subcomando. La conciliación registra el cargo observado y su evidencia, libera la reserva y no repite la compra ni inventa un informe aceptado. Usar cero solo tras confirmar que no hubo cargo.

El límite general suma **costes LLM observados + compras cobradas + reservas desconocidas**. SQLite serializa compras concurrentes. Las reservas pendientes de días anteriores consumen también el límite diario actual. Una llamada LLM ya en curso puede superar la estimación restante: no es una preautorización estricta de todos los tokens.

## Pruebas y alcance

Las pruebas usan el firmante real del Hub y HTTP simulado, sin pagos reales. Cubren entrega al desarrollador, firmas, versiones obsoletas, rutas, políticas desactivadas, concurrencia, pagos ambiguos, reinicio, conciliación y conservación de QA.

Se registra la siguiente QA y el número de incidencias pendientes, sin atribuir ahorros causales ni aprender automáticamente rankings. Conciliación automática, desarrollo completo externo, federación, subcontratación posterior y tareas largas quedan fuera de esta versión.

Código: [contrato](https://github.com/alexar76/aicom/blob/main/core/procurement_contract.py), [diario](https://github.com/alexar76/aicom/blob/main/core/procurement_store.py), [orquestación](https://github.com/alexar76/aicom/blob/main/orchestrator/procurement.py), [recibos](https://github.com/alexar76/aicom/blob/main/core/procurement_receipt.py).

## Prueba con llamadas reales — 2026-10-11

La [evidencia guardada](https://github.com/alexar76/aicom/blob/main/docs/evidence/factory-subcontracting-live-2026-10-11.json) registra HTTPS real contra un Hub temporal y una llamada real a `minimax/minimax-m3` mediante la cuenta OpenRouter configurada en la fábrica. Se aceptó el informe vinculado al código, se verificaron Ed25519 y ML-DSA-65, el saldo **de prueba** pasó de $0.50 a $0.40 y la repetición no generó tráfico. La llamada aceptada declaró un coste de $0.00033588. No se modificaron cuentas ni catálogo de producción; no demuestra una compra en producción ni la construcción completa de un producto.

Dos ejecuciones anteriores detectaron un timeout y un informe con formato incorrecto. El timeout conservó la reserva sin reintento; el informe incorrecto quedó pagado pero rechazado. La solicitud ahora exige explícitamente un array de 1–5 hallazgos. La primera llamada no devolvió datos de uso, por lo que el gasto total del modelo no está conciliado.

El Hub público `modelmarket.dev` respondió HTTP 200, pero su búsqueda desplegada carecía de `credits_eligible` y no se encontró un proveedor compatible. La compra en producción queda pendiente de verificar tras actualizar el Hub y desplegar un proveedor compatible.

Repetir con [el script](https://github.com/alexar76/aicom/blob/main/scripts/procurement_live_probe.py):
```bash
.venv/bin/python scripts/procurement_live_probe.py \
  --ssh-host YOUR_FACTORY_SSH_ALIAS --container aicom-app-1 \
  --output /tmp/procurement-live-result.json
```
Cada ejecución puede facturar una llamada real; la estimación según las tarifas del modelo debe ser como máximo $0.25. La clave permanece en el contenedor remoto. Hub, claves TLS, catálogo y créditos de prueba son temporales.

## Activado en producción — 2026-10-11

La fábrica compra `aicom.diagnose@v1` al servicio aprobado `aicom-diagnostics` mediante `https://modelmarket.dev`. Este primer proveedor pertenece al operador, funciona separado de la fábrica y usa `minimax/minimax-m3`. El Hub verifica la firma Ed25519 del proveedor ligada a la solicitud; la fábrica verifica el recibo Ed25519 + ML-DSA-65 del Hub. Metis sigue en arquitectura y metodología, tareas distintas del diagnóstico de defectos repetidos.

Límites: $0,25 por llamada, $0,50 por producto, $2 por día UTC y $0,50 de reserva para completar el trabajo interno. Se conserva el límite total de $40. Solo se comparten `backend/app/*.py` y `frontend/src/*.tsx`. La cuenta recibió un crédito operativo único de $2, sin recarga automática. La compra válida costó $0,10 y dejó $1,90. Son créditos concedidos por el operador, no un depósito fiat ni ingresos de un cliente independiente.

La prueba utilizó un defecto sintético y una respuesta real del modelo. La entrega firmada reutilizó el informe guardado en la prueba anterior de firma, sin otra inferencia. Repetir la tarea aceptada no produjo tráfico. Cinco intentos rechazados se conciliaron sin cargos. El adaptador admite un bloque JSON Markdown completo y la variante `suggest_check`, manteniendo la validación estricta de citas y contrato. Pasaron 45 pruebas; no se afirma una reparación completa de un producto real.

[Evidencias](https://github.com/alexar76/aicom/blob/main/docs/evidence/procurement-production-2026-10-11/README.md). Para desactivar compras nuevas: `enabled: false` en `data/config/procurement.json`, sin reiniciar. Fuentes y reversión: `/root/procurement-release-20261011/`. No se hizo push a GitHub.
