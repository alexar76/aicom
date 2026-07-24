# GAIA v0.1.0

First public release of **GAIA** — physical-world oracle gateway for the AICOM / AIMarket ecosystem.

## Highlights

- **Virtual IoT fleet** — weather, air quality, energy meters with shared site truth
- **Ed25519 attestation** — every reading signed; gateway countersignature on invoke
- **Plausibility verify** — Metis-envelope `/v1/verify` for Pay-on-Verified escrow
- **Live relays** — NOAA / OpenSenseMap / OGC SensorThings public sensors
- **W3C WoT** — Thing Descriptions per device
- **3D landing** — R3F cosmic canvas of the demo fleet

## Install

```bash
docker pull ghcr.io/alexar76/gaia:v0.1.0
# or
pip install gaia-gateway==0.1.0   # needs oracle-core
```

Live demo: https://iot.modelmarket.dev/  
Landing: https://alexar76.github.io/gaia/
