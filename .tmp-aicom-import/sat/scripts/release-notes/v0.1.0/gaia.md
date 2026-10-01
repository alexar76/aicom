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
```

<!-- No pip line. This file used to carry `pip install gaia-gateway==0.1.0 # needs oracle-core`,
     and BOTH names were wrong in a way that matters:

     * `oracle-core` is a live package belonging to somebody else, and it installs the same
       top-level `oracle_core` module this project imports. Anyone following that line today
       gets a stranger's code — no attacker required, it is simply the wrong package.
     * `gaia-gateway` was our own name until 2026-07-30, when it was renamed to
       `aimarket-gaia-gateway`. The old name is now unregistered, which means claimable: whoever
       takes it decides what `pip install gaia-gateway` delivers to a reader of these notes.

     And `aimarket-gaia-gateway` has never been published, so there is no correct pip line to
     write yet. Docker is the real install path. Restore a pip line only after the package is
     actually on PyPI, and then use the prefixed name. -->

Live demo: https://iot.modelmarket.dev/

Live demo: https://iot.modelmarket.dev/  
Landing: https://alexar76.github.io/gaia/
