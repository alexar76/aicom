# Codex: una operación del cliente y dos subcontratistas pagados

[English](case-study-codex-one-call.md) · [Русский](case-study-codex-one-call.ru.md) · [Español](case-study-codex-one-call.es.md) · [Français](case-study-codex-one-call.fr.md) · [中文](case-study-codex-one-call.zh.md)

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

- [JSON](evidence/codex-one-call-2026-09-30.json) · [Blueprint](evidence/codex-one-call-2026-09-30-blueprint.json)
- [API / SDK](one-call-pipelines.es.md)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

Verificación posterior del acceso de agentes (3.9.0): pasaron 175 pruebas específicas y cuatro pruebas de pago locales con Anvil. Una instalación limpia ejecutó un grafo gratuito por SDK en dos solicitudes al Hub. MCP prepare/invoke/status completó otro grafo gratuito. El pedido pagado original se recuperó con dos GET (manifiesto y estado raíz), sin clave del monedero ni RPC. El propio SDK verificó los recibos del Hub. No hubo nuevos pagos mainnet en esta comprobación. El Hub distribuye el wheel, con SHA-256 en el manifiesto firmado; no se publicó en PyPI.

[JSON](evidence/agent-rails-2026-09-30.json)

## Continuación: vendedor independiente, 3.10.1

Codex añadió SELLER-OP/1 y desplegó Hub con migraciones 44–45. La guía de cadenas detalla protocolo y límites. Pasaron **223 pruebas específicas y 6 escenarios locales Anvil**, incluyendo dos liquidaciones entre hubs separados con un token desechable, una con respuesta perdida. En cada escenario independiente el comprador pagó exactamente 4.000 unidades una sola vez; el vendedor creó y consumió su factura. Son pruebas locales de integración, no nuevas compras mainnet.

En producción se verificaron manifiesto firmado, wheel y cinco guías, una cadena gratuita MCP, otra SDK con dos solicitudes principales y recuperación del pedido pagado original solo mediante GET. No hubo nuevos pagos mainnet desde el monedero de prueba. El listing local weather.witness no tiene una ruta de cobro directo compatible: la preparación devuelve ahora 409/settlement_route_unsupported en lugar de 500, antes de ejecutar o pagar. Su contrato SUB/1 con crédito no cambia. No se actualizó ni compró a un peer independiente de producción; esa ruta se probó con dos hubs controlados en Anvil.

[Evidencia depurada](evidence/seller-operations-2026-09-30.json). No se publican claves privadas, tokens de operación ni paquetes de transacciones firmadas.
