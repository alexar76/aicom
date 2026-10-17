# Pon en marcha tu propio hub de sensores gratis

[English](sensor-operator.md) · [Русский](sensor-operator.ru.md) · [Español](sensor-operator.es.md) · [Français](sensor-operator.fr.md) · [中文](sensor-operator.zh.md)

**Despliega y utiliza Hub + GAIA gratis en tu propia infraestructura**, manteniendo el control de tus claves, datos y servicios. Esta guía está dirigida a propietarios de estaciones, comunidades locales de sensores y pequeños integradores de IoT. Tú proporcionas la infraestructura; no nos pagas una licencia ni una suscripción por el uso autoalojado.

Tras la admisión habitual, la federación AIMarket es un mercado potencial para tus ofertas. Vender acceso es opcional y tú eliges los precios; no se garantizan compradores ni ingresos. El ejemplo de servicio de pago que sigue describe esa opción. No necesitas comprar datos ni realizar una venta para empezar a utilizar tu propio hub.

Un buen primer servicio es una observación local real donde el comprador solo dispone de un pronóstico o de pocas mediciones. Describe la ubicación, las variables, el intervalo de actualización y las limitaciones del sensor. Una copia de una fuente pública necesita una razón adicional para resultar útil.

Esta es una guía reproducible, no un informe de un despliegue físico ya realizado ni una promesa de ingresos. Tras la admisión, la federación permite descubrir el servicio; el comprador sigue decidiendo si lo necesita.

## Qué operas

El recorrido es **tu sensor → tu adaptador → GAIA → tu Hub → comprador**. GAIA recibe las lecturas y firma el resultado; Hub publica el servicio, procesa la vía de pago configurada y devuelve un recibo. La firma acredita procedencia e integridad, no demuestra por sí sola la exactitud de la medición.

No necesitas tener un negocio de API. Sí necesitas exportar las mediciones al JSON indicado abajo. El punto de ingestión no es un conector automático para cualquier dispositivo Tasmota, ESPHome, Home Assistant, TTN o SenML: el adaptador debe convertir el formato de cada equipo.

El receptor genérico actual acepta `temperature_c`, `humidity_pct`, `pressure_hpa`, `pm2_5_ugm3` y las coordenadas obligatorias `latitude` y `longitude`. Envía solo variables realmente medidas. El dispositivo es `feeder-iot-01` y la capacidad vendida es `gaia.iot.read@v1`. Cada instancia dispone actualmente de un solo receptor IoT genérico; varias estaciones requieren una extensión explícita o instancias separadas, no identificadores inventados.

## 1. Inicia un proveedor GAIA privado

Requisitos: Docker, `curl`, `jq`, un adaptador que exporte mediciones reales y un Hub inicializado según la [guía del operador](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.es.md). El ejemplo ejecuta GAIA en Docker y Hub directamente en **la misma máquina**. Construye la imagen desde la raíz de AICOM, en una revisión que hayas comprobado:

```bash
docker build -f gaia/Dockerfile -t local/gaia-sensor .
export GAIA_FEEDER_TOKEN="$(openssl rand -hex 32)"
docker run -d --name gaia-sensor \
  -p 127.0.0.1:9320:9320 \
  -v gaia-sensor-data:/data \
  -e GAIA_FEEDER_TOKEN \
  -e GAIA_ENABLE_LIVE=1 -e GAIA_FEEDER_ENABLED=1 \
  -e GAIA_SIM_CONTROL=0 -e AIFACTORY_PROD=1 \
  -e GAIA_PUBLIC_URL=http://127.0.0.1:9320 \
  -e GAIA_KEY_DIR=/data/devices \
  -e GAIA_SIGNING_KEY_PATH=/data/gaia_signing_key \
  local/gaia-sensor
```

Guarda el token generado en tu configuración privada; el cliente de envío debe usar el mismo valor. Conserva el volumen `/data`, incluidas las claves del gateway y los dispositivos. GAIA queda vinculada a loopback: los compradores acceden a Hub. Un sensor remoto necesita HTTPS protegido o una red privada hasta la ingestión, no el puerto del proveedor expuesto públicamente.

El arranque actual requiere tanto `GAIA_ENABLE_LIVE=1` como `GAIA_FEEDER_ENABLED=1`. GAIA también registra fuentes retransmitidas y simuladores integrados; aquí solo se publica tu servicio `gaia.iot.read@v1` en Hub. No presentes las estaciones simuladas como equipos reales.

## 2. Envía una observación real

El adaptador debe escribir `station-reading.json` con esta estructura. Sustituye cada marcador entre comillas por un **número JSON** real antes del envío: la plantilla no es una medición. `observed_at` es la hora de observación en segundos Unix, no la hora de retransmisión de un dato antiguo.

```json
{
  "device_id": "feeder-iot-01",
  "observed_at": "<observed_at>",
  "fields": {
    "latitude": "<latitude>",
    "longitude": "<longitude>",
    "temperature_c": "<temperature_c>"
  }
}
```

Envía los datos y consulta el mismo dispositivo localmente:

```bash
curl --fail-with-body -sS http://127.0.0.1:9320/feeder/v1/ingest \
  -H "Authorization: Bearer $GAIA_FEEDER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @station-reading.json

curl --fail-with-body -sS http://127.0.0.1:9320/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","input":{"device_id":"feeder-iot-01"}}'
```

La ingestión debe devolver `ok: true`, y la invocación un resultado con la lectura y la atestación. Comprueba el dispositivo, los valores y la fuente. Revisa también el JSON: una lectura no disponible puede devolver `ok: false` con HTTP 200. Esta llamada local al proveedor comprueba la conexión; no es una venta.

Actualiza con más frecuencia que el límite actual de frescura de 600 segundos. Sin datos, o con datos antiguos, el receptor queda no disponible. Actualmente conserva solo la última observación **en memoria del proceso**: después de reiniciarlo, envía una lectura nueva antes de aceptar compras. Las claves persistentes no crean un archivo histórico.

## 3. Publica la lectura en tu propio Hub

En el directorio y entorno del Hub inicializado, asigna a `SENSOR_PAY_TO` **la dirección de tu cartera receptora**, nunca una clave privada. El precio de ejemplo es $0.002 por llamada; elige el tuyo. Obtén localmente la clave pública del gateway GAIA y fíjala en la publicación:

```bash
: "${SENSOR_PAY_TO:?Set SENSOR_PAY_TO to your receiving wallet address}"
GAIA_PROVIDER_KEY="$(curl -fsS http://127.0.0.1:9320/.well-known/ai-market.json | jq -er .signer_public_key)"
export AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1
aimarket add gaia.iot.read@v1 \
  --product gaia.gateway \
  --url http://127.0.0.1:9320/ai-market/v2/invoke \
  --provider-pubkey "$GAIA_PROVIDER_KEY" \
  --price 0.002 --pay-to "$SENSOR_PAY_TO" \
  --name "Local station readings" \
  --description "Current measurements from the operator's own station" \
  --input-schema '{"type":"object","properties":{"device_id":{"type":"string","enum":["feeder-iot-01"]}},"required":["device_id"],"additionalProperties":false}'
```

Inicia o reinicia `aimarket serve` con la misma base de datos y `AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1` en el entorno del servicio. Esto autoriza explícitamente al Hub a llamar a su proveedor local. Para un Hub en contenedor o en otra máquina, sigue la red de la [guía de producción](https://github.com/alexar76/aimarket-hub/blob/main/docs/production-deployment.md); el loopback del contenedor apunta al propio contenedor.

GAIA ya firma las respuestas del proveedor; `--provider-pubkey` permite verificarlas. `aimarket add` publica tu propio servicio localmente. Publicar en el Hub de otro operador sigue otra vía de admisión.

## 4. Comprueba el requisito de pago

Llama al Hub sin pago ni cabecera de sandbox:

```bash
curl -sS -i http://127.0.0.1:9083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","source_hub":"local","input":{"device_id":"feeder-iot-01"}}'
```

Un servicio con precio y pagos configurados debe responder `402` con una oferta de pago. Comprueba importe, red, activo y destinatario antes de pagar. Entregar la lectura sin pago no supera esta comprobación.

`--pay-to` declara el destinatario; completa la configuración de pago directo al vendedor de la [guía del operador](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.es.md) antes del lanzamiento público. El comprador sigue la oferta, autoriza el pago y repite la invocación mediante un cliente compatible. Conserva el recibo y confirma la recepción de fondos. Los créditos locales creados para pruebas no son ingresos externos.

Este ejemplo no activa Pay-on-Verified. Una lectura firmada no implica liquidación condicionada a una verificación ni devolución automática de un pago directo ya completado. El ingreso neto depende del uso pagado real, las comisiones, el alojamiento y el mantenimiento; pertenecer a la federación no garantiza ventas.

## 5. Únete a la federación con las reglas habituales

Despliega Hub con HTTPS público siguiendo la guía de producción, mantén GAIA privada y sustituye `hub.example.com` por tu dirección. Conserva la capacidad gratuita y firmada `hub.ping@v1` creada por quickstart para la admisión. Mantén las claves y la base de datos al pasar a producción.

```bash
aimarket quickstart --url https://hub.example.com --no-buyer
aimarket doctor --url https://hub.example.com
curl --fail-with-body -sS https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url":"https://hub.example.com","hub_name":"My sensor hub"}'
```

Consulta el veredicto en el `assay_url` devuelto. Ser visible en el monitor o tener un anuncio pending **no** concede admisión, indexación ni enrutamiento. Debes corregir cualquier comprobación fallida según las reglas existentes. Consulta [cómo unirse a la federación](join-the-federation.es.md). El comprador debe conservar el `source_hub` obtenido en la búsqueda al invocar.

El marcador del sensor en ATLAS es independiente de la admisión del Hub. No se promete una aparición automática en el mapa: usa la [guía GAIA → ATLAS](i18n/add-gaia-atlas-sensor.es.md) para tipos compatibles o una nueva integración revisada.

## Conecta tu estación

Para hablar de una primera conexión, abre una [GitHub Discussion](https://github.com/alexar76/aicom/discussions). Incluye modelo, variables disponibles, zona aproximada, intervalos de observación y actualización, formato de exportación y posibilidad de operar un Hub. No publiques tokens ni claves privadas.

El primer resultado útil es una lectura reciente de tu equipo, comprada por un cliente externo, con recibo y pago confirmado. Después mide compras repetidas y continuidad del servicio. Identifica por separado las compras de prueba. Un operador comunitario puede coordinar varios propietarios, pero el receptor actual de una sola estación requiere una extensión o una instancia separada por estación independiente.

Más información: [fuentes y receptores GAIA](https://github.com/alexar76/gaia/blob/main/docs/i18n/LIVE-RELAYS.es.md) · [guía del operador Hub](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.es.md) · [indicadores públicos de demanda](https://verify.modelmarket.dev/demand.json).
