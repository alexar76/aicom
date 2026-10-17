# Run your own sensor hub for free

[English](sensor-operator.md) · [Русский](sensor-operator.ru.md) · [Español](sensor-operator.es.md) · [Français](sensor-operator.fr.md) · [中文](sensor-operator.zh.md)

**Deploy and use Hub + GAIA for free on your own infrastructure**, keeping control of your keys, sensor data and services. This guide is for station owners, local sensor communities and small IoT integrators. You provide the infrastructure; there is no software license or subscription fee to us for self-hosted use.

After normal admission, the AIMarket federation is a potential market for your offerings. Selling access is optional and you choose your prices; buyers and revenue are not guaranteed. The paid-service example below describes that optional path. You do not need to buy data or make a sale to begin using your own hub.

A useful first service is an actual local observation where a buyer otherwise has only a forecast or sparse coverage. Describe the location, measured fields, update interval and sensor limitations. A copy of a public feed needs its own reason to be useful.

This is a repeatable setup guide, not a report of a completed hardware deployment or a promise of revenue. Federation makes your service discoverable after admission; buyers still have to choose it.

## What you operate

The path is **your sensor → your adapter → GAIA → your Hub → buyer**. GAIA accepts readings and signs the result; the Hub publishes the service, handles the configured payment path and returns a receipt. A signature establishes provenance and integrity, not independent proof of measurement accuracy.

An existing API business is not required. You do need a way to export your device's measurements into the JSON format below. The ingest endpoint is not an automatic connector for every Tasmota, ESPHome, Home Assistant, TTN or SenML device. Hardware-specific conversion remains part of the adapter.

For a JSON MQTT source with an actual observation timestamp, use the [single-station MQTT adapter](https://github.com/alexar76/gaia/blob/main/docs/mqtt-feeder.md). Configure its field paths and units from your own payload before connecting it.

The current generic feeder accepts `temperature_c`, `humidity_pct`, `pressure_hpa`, `pm2_5_ugm3`, plus required `latitude` and `longitude`. Only send fields you actually measure. Its identifier is `feeder-iot-01`, and the sold capability is `gaia.iot.read@v1`. One instance currently provides one generic IoT feeder slot; a multi-station installation needs an explicit extension or separate instances, not invented device IDs.

## 1. Start a private GAIA provider

Prerequisites: Docker, `curl`, `jq`, an adapter that can export real readings, and an initialized Hub following the [operator quickstart](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md). The example runs GAIA in Docker and the Hub directly on the **same machine**. Build from the root of an AICOM checkout at a revision you have reviewed:

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

Keep the generated feeder token in your private configuration; the upload client must use the same value. Persist the `/data` volume, including gateway and device keys. The example binds GAIA to loopback: buyers use the Hub. A remote sensor needs a protected HTTPS or private-network path to ingest, not a publicly exposed raw provider port.

Both `GAIA_ENABLE_LIVE=1` and `GAIA_FEEDER_ENABLED=1` are required by the current startup path. GAIA also registers built-in relays and simulators; this guide lists only your own `gaia.iot.read@v1` service on the Hub. Do not present simulated stations as your hardware.

## 2. Send a real observation

Have your adapter write `station-reading.json` in this shape. Replace every quoted placeholder with an actual **JSON number** before sending; this template is not a measurement. `observed_at` is the sensor observation time in Unix seconds, not the time an old reading was retransmitted.

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

Upload, then read the same device locally:

```bash
curl --fail-with-body -sS http://127.0.0.1:9320/feeder/v1/ingest \
  -H "Authorization: Bearer $GAIA_FEEDER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @station-reading.json

curl --fail-with-body -sS http://127.0.0.1:9320/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","input":{"device_id":"feeder-iot-01"}}'
```

Expect `ok: true` from ingest and a result containing the reading and attestation from invoke. Check the returned device, values and source. Inspect the JSON too: an unavailable reading can return `ok: false` with HTTP 200. This local provider call is a connectivity check, not a sale.

Send updates more frequently than the current 600-second freshness limit. Missing or stale data makes the feeder unavailable. The current feeder keeps only the latest observation **in process memory**: after a restart, send a fresh reading before accepting purchases. Persistent keys do not make it a historical archive.

## 3. List the reading on your own Hub

In the initialized Hub's working directory and environment, set `SENSOR_PAY_TO` to **your receiving wallet address** (never a private key). The example price is $0.002 per call; choose your own price. Read the GAIA gateway public key locally and pin it on the listing:

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

Run or restart `aimarket serve` with the same Hub database and `AIMARKET_INVOKE_HOST_GATEWAY=127.0.0.1` in its service environment. This explicitly permits the Hub to call its local provider. For a containerized Hub or a different host, use the network layout in the [production deployment guide](https://github.com/alexar76/aimarket-hub/blob/main/docs/production-deployment.md); loopback inside a container is a different machine.

GAIA already signs its provider responses; `--provider-pubkey` lets the Hub check them. The local `aimarket add` command lists your own service. Publishing on somebody else's Hub is a separate admission path.

## 4. Check the payment boundary

Call the Hub without payment or a sandbox header:

```bash
curl -sS -i http://127.0.0.1:9083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"gaia.gateway","capability_id":"gaia.iot.read@v1","source_hub":"local","input":{"device_id":"feeder-iot-01"}}'
```

For a priced service with payment configured, expect `402` and a payment offer. Confirm the amount, accepted network/asset and recipient before funding a purchase. An unpaid response that delivers the reading is not a passed payment check.

`--pay-to` declares the recipient; complete the seller-direct payment configuration in the [operator guide](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md) before going live. A real buyer follows the offer, authorizes payment and invokes again through the supported client. Record the returned receipt and verify receipt of funds. Local credit balances created for testing are not external revenue.

This example does not enable Pay-on-Verified. Signed readings alone do not imply verification-dependent settlement or an automatic refund after a completed seller-direct payment. Net income depends on actual paid usage, fees, hosting and device maintenance; federation membership guarantees no sales.

## 5. Join the federation under the normal rules

Deploy the Hub on public HTTPS following the production guide, keep GAIA private, and replace `hub.example.com` below with your actual Hub address. Retain the free signed `hub.ping@v1` created by quickstart for admission checks. Keep the same keys and database when moving to production.

```bash
aimarket quickstart --url https://hub.example.com --no-buyer
aimarket doctor --url https://hub.example.com
curl --fail-with-body -sS https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url":"https://hub.example.com","hub_name":"My sensor hub"}'
```

Read the verdict at the returned `assay_url`. Visibility in the monitor and a pending announcement do **not** grant admission, indexing or routing. A failed check must be corrected under the existing rules. See [join the federation](join-the-federation.md). Buyers should preserve the `source_hub` returned by search when invoking your listing.

A sensor pin on ATLAS is separate from Hub admission. Do not promise automatic map placement: use the [GAIA → ATLAS guide](add-gaia-atlas-sensor.md) for supported kinds or a reviewed new integration.

## Bring your station

To discuss a first connection, open a [GitHub Discussion](https://github.com/alexar76/aicom/discussions). Include the device model, available fields, approximate coverage area, observation/update interval, export format and whether you can run a Hub. Share no tokens or private keys.

The first useful milestone is a fresh reading from your device, bought by an external client, with a receipt and confirmed payment. Then measure repeat purchases and continued operation. Label test purchases separately. A community operator can coordinate several owners, but the current one-slot feeder must be extended or deployed separately for each independent station.

See also: [GAIA live sources and feeders](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md) · [Hub operator guide](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.md) · [public demand counters](https://verify.modelmarket.dev/demand.json).
