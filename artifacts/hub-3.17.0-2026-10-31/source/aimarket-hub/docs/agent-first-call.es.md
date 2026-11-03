# Primera llamada del agente: descubrir → invocar → verificar

[English](agent-first-call.md) · [Русский](agent-first-call.ru.md) · [Español](agent-first-call.es.md) · [Français](agent-first-call.fr.md) · [中文](agent-first-call.zh.md)

Elija el cliente que ya utiliza. MCP y A2A acceden al mismo marketplace y a los mismos controles de invocación; no necesita adoptar ambos.

## Cliente MCP

Añada `https://modelmarket.dev/mcp` a un cliente MCP compatible con Streamable-HTTP. Consulte `tools/list` para obtener los esquemas actuales de los argumentos y encargue al agente esta tarea:

> Busque el servicio meteorológico GAIA Open-Meteo con `market_search`. Muestre el precio y el esquema de entrada de la oferta elegida. Ejecute `market_invoke` para `device_id` `om-wx-01`, copiando `product_id`, `capability_id` y `source_hub` de esa oferta. Utilice la prueba gratuita y deténgase si se requiere un pago. Muestre el resultado y el recibo. Indique la verificación del recibo por separado del éxito de la ejecución: un campo de firma no equivale a una verificación satisfactoria.

Conserve `source_hub`: las ofertas federadas requieren indicar su origen al invocarlas. El servicio alojado puede devolver `429 trial_quota_exhausted` cuando se agota la prueba gratuita. Consulte los [detalles de MCP](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md). El ejemplo A2A siguiente realiza una verificación explícita de la firma en el cliente.

## Agente A2A

El [ejemplo compartido en Python](../examples/first-agent-call.py) obtiene la Agent Card, busca `gaia.weather.read@v1`, conserva el hub de origen y limita una llamada a $0.01. Ejecútelo desde el directorio `aimarket-hub` con Python 3.11+:

```bash
python -m pip install 'aimarket-agent>=2.4.0'
```

```bash
python examples/first-agent-call.py
python examples/first-agent-call.py --invoke
```

El primer comando solo busca. El segundo realiza una invocación. Sin `AIMARKET_KEY`, utiliza una prueba gratuita disponible. Para probar el pago con créditos prepagados, asigne a `AIMARKET_KEY` la clave API de una cuenta con saldo: la llamada puede descontar hasta $0.01. No guarde la clave en scripts ni commits. La variable `AIMARKET_HUB_URL` permite elegir otro hub.

El ejemplo envía `device_id` `om-wx-01` a la oferta GAIA Open-Meteo. Si cambia el catálogo, revise el esquema de entrada devuelto por la búsqueda. Si no hay una oferta coincidente, el ejemplo termina sin invocar.

## Continuar una Task con x402

Después del código `2`, revise las condiciones de pago de la Task. Pague la factura una sola vez con su cartera (wallet), espere la liquidación y utilice el mismo Task ID y hash de transacción. El ejemplo presenta una transferencia ya realizada; no firma, envía ni reemplaza transacciones. Una Task de cuenta requiere el mismo `AIMARKET_KEY`. Leer una Task completada no repite el pago ni la invocación.

La corrección de la continuación x402 está en este checkout de `aicom`. Hasta su publicación en el SDK, instale el cliente local desde el directorio `aimarket-hub`:

```bash
python -m pip install -e ../aimarket-agent
```

```bash
python examples/first-agent-call.py --task-id a2at_... --payment-tx 0x...
python examples/first-agent-call.py --task-id a2at_...
```

## Interpretar el resultado

- Código `0` después de `--invoke`: la Task tiene `TASK_STATE_COMPLETED` y `receipt_verified` es true. El SDK verificó el recibo con la clave del firmante; para una oferta federada, utiliza la clave del proveedor. Solo entonces muestra el resultado.
- Código `1`: la oferta meteorológica no estaba disponible.
- Código `2`: la Task no se completó. `TASK_STATE_INPUT_REQUIRED` puede solicitar un pago; `TASK_STATE_AUTH_REQUIRED`, credenciales. Consulte el estado mostrado y la [guía de pagos](a2a.md#invoke).
- Código `3`: la ejecución terminó, pero falló la verificación del recibo o no se recibió ningún recibo. No considere el resultado verificado.
- Código `4`: el recibo es válido, pero falta el resultado meteorológico. La ejecución y la verificación de la firma por sí solas no bastan para completar el ejemplo correctamente.

El código `0` sin `--invoke` solo confirma el descubrimiento. Los errores de red o protocolo también detienen el ejemplo. No recarga cuentas, transfiere fondos, reanuda pagos ni reintenta automáticamente. Una Task incompleta no demuestra que no haya habido un cargo; revise su estado antes de reintentar. Para reintentos deliberados, reutilice el mismo `message_id` según la [guía A2A](a2a.md).

Un recibo válido autentica un registro firmado. No demuestra de forma independiente que los datos meteorológicos sean correctos. El hub determina los límites de la prueba gratuita y la disponibilidad de las ofertas; el ejemplo no los garantiza.
