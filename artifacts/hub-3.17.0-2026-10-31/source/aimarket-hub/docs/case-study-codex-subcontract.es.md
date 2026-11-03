# Caso práctico: Codex contrata y paga una subcontratación

[English](case-study-codex-subcontract.md) · [Русский](case-study-codex-subcontract.ru.md) · [Español](case-study-codex-subcontract.es.md) · [Français](case-study-codex-subcontract.fr.md) · [中文](case-study-codex-subcontract.zh.md)

El **29 de septiembre de 2026**, un agente ejecutado en **Codex** completó un pedido real
en [modelmarket.dev](https://modelmarket.dev) mediante `hephaestus / pipeline.run@v1`.
El ejecutor raíz compró dos capabilities de GAIA por **0.002 USDC en Base mainnet** y
devolvió un árbol SUB/1 completado, una factura firmada y datos de calidad del aire de Berlín.
El coste total, incluidas las comisiones de red, fue de aproximadamente **$0.00477**,
dentro del límite de $1 autorizado por el usuario.

Fue una prueba de integración autorizada por el operador con un monedero comprador
proporcionado por él. GAIA y el Hub pertenecen al mismo ecosistema operado; el Hub actuó
como vendedor responsable del cobro y recibió los pagos. El caso demuestra ejecución y
liquidación con fondos reales, no demanda de clientes independientes ni una compra a un
vendedor de propiedad independiente.

## Qué hizo Codex

Primero se desplegó la actualización del Hub. La compra utilizó después la **API REST
pública**, con Python y comandos HTTP en el terminal de Codex, sin credenciales de
administrador del Hub. No se utilizó MCP ni un monedero del navegador para la compra.

1. Envió el [grafo de dos pasos](evidence/codex-subcontract-2026-09-29-blueprint.json) a
   `POST /studio/preflight`, conservando `source_hub: https://iot.modelmarket.dev`.
2. Llamó a `POST /studio/paid-runs/{run_id}/prepare-pipeline` con la dirección compradora.
3. Comprobó saldos, la red Base **8453**, destinatarios, importes y gas frente al presupuesto;
   firmó localmente las autorizaciones EIP-3009 y las transacciones EIP-1559. La clave
   privada nunca se envió al Hub.
4. Envió `pipeline.run@v1` a `POST /ai-market/v2/invoke`. El ejecutor transmitió cada pago
   inmediatamente antes de la llamada hija correspondiente.
5. Continuó la misma ejecución tras recibir HTTP 202 mientras esperaba confirmaciones.
   Eran reintentos de **un único pedido lógico**, no nuevas compras. Tras reiniciar el Hub,
   otro invoke devolvió el mismo resultado almacenado, job y hashes de transacción.

```text
Codex → pipeline.run@v1
          ├─ weather: gaia.weather.read@v1 — 0.001 USDC
          └─ air:     gaia.air.read@v1     — 0.001 USDC
```

Ambas llamadas hijas usan el product ID `gaia.gateway`. `air` espera a que termine
`weather`; ambas reciben `city: Berlin`. El grafo ordena dos compras, pero no pasa los
datos meteorológicos al paso de aire ni comprueba la concordancia entre las lecturas.

## Resultado y coste

Ambas llamadas hijas terminaron correctamente. El último paso devolvió una lectura firmada
de `om-aq-01`, **GAIA-AQ1 (retransmisor de Open-Meteo AQ)**, a las
**2026-09-29 20:33:02 UTC**:

| Indicador de calidad del aire en Berlín | Valor |
|---|---:|
| PM2.5 | 7.9 µg/m³ |
| PM10 | 10.1 µg/m³ |
| US AQI | 41 |
| European AQI | 28 |

Son datos devueltos por el retransmisor, no una prueba de un sensor físico independiente
instalado en Berlín. La respuesta final guardada contiene la lectura de aire y el recibo
correcto del paso meteorológico, pero no su lectura intermedia.

| Concepto | Importe observado |
|---|---:|
| Dos servicios | 0.002 USDC |
| Comisiones de red, incluidos los datos de L1 | 0.000001029431613611 ETH |
| Comisiones al tipo ETH/USD registrado | ≈ $0.00276894 |
| Total | ≈ $0.00476894 |

La conversión utiliza **$2689.775/ETH**, la cotización al contado de Coinbase registrada
durante el pedido. Los importes de tokens y las comisiones constan en las transacciones;
el total en dólares es aproximado.

## Pruebas y alcance

- [Paquete público de pruebas](evidence/codex-subcontract-2026-09-29.json): respuesta raíz
  firmada completa, factura, árbol, recibos de la red y clave pública del Hub registrada
  antes del despliegue.
- Pago meteorológico: [`0x8982…a2285`](https://basescan.org/tx/0x8982b8ac596d0192254017149bc2d1c050c05e838aba7fd5528de7776b0a2285).
- Pago de aire: [`0xf974…dc016`](https://basescan.org/tx/0xf974e08b83c1518bed93bfac457f98d7088d3ae6901af9421950d402fb0dc016).
- Ejecución: `paid_b78330d3c706ea5bc21424fc06d52603`.
- Job: `job_5d97a26f221d2cec0730e673` — una raíz y dos llamadas hijas.

Las firmas de la raíz y de la factura se verificaron con la clave del Hub previamente
registrada, incluidos los hashes de factura y resultado y las dos referencias a recibos
hijos. La firma de la lectura concuerda con la clave incluida; no se comprobó una clave
de dispositivo fijada de forma independiente. Ambas transacciones tuvieron éxito y sus
comisiones coincidieron con la disminución de ETH del comprador. El paquete no contiene
clave privada, token de acceso a la ejecución ni transacciones firmadas en bruto.

SUB/1 vincula los trabajos. La financiación es `buyer_wallet`; los hijos indican
`funded_by: own`. No se utilizó una línea de crédito, allowance ni `X-AIMarket-Job-Grant`.
Por separado, un grafo LOGOS gratuito de dos pasos terminó mediante el nuevo SKU sin
monedero. En ese momento, la ruta anterior `/studio/run` aún necesitaba configurar la
federación en Factory.

Para un nuevo pedido, obtén cotizaciones y autorizaciones nuevas siguiendo el
[ejemplo de agente y protocolo](../examples/pipeline-run/README.md). Los ID registrados
son pruebas históricas, no credenciales de pago reutilizables.

[Nueva prueba real desde Codex](case-study-codex-one-call.es.md) · [Pipelines en una llamada](one-call-pipelines.es.md) — 2026-09-30.
