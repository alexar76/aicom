# Add a sensor to GAIA + ATLAS

**Languages:** [EN](add-gaia-atlas-sensor.md) · [RU](i18n/add-gaia-atlas-sensor.ru.md) · [ES](i18n/add-gaia-atlas-sensor.es.md) · [FR](i18n/add-gaia-atlas-sensor.fr.md) · [ZH](i18n/add-gaia-atlas-sensor.zh.md)

> ## DISCLAIMER — read this first
>
> **One command adds a sensor only when the kind already exists in GAIA code**
> (Open-Meteo weather/air/marine, NWS, openSenseMap, NOAA tide, USGS river,
> NDBC buoy, OpenAQ, UK grid, USGS quake, NASA FIRMS fire, Safecast radiation,
> CyberNews GNSS jamming, or SIM campus).
>
> It does **not** invent a new upstream API, allowlist a new host, or invent new
> measurement fields. For a brand-new public API you still write a `LiveDevice`
> subclass (Recipe B below). Claiming **LIVE** without a provenance `source` is forbidden.
>
> **Commercial license filter:** only freely commercializeable upstreams are
> registered as Hub SKUs (FIRMS / Safecast CC0 / CyberNews CC BY / own edge
> feeders). Do not add GFW, Stanford CC BY-NC, or ADSBx commercial as paid relays —
> see [`gaia/docs/LIVE-RELAYS.md`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md).
>
> Terms: [`localization-glossary.md`](localization-glossary.md) · Operator catalog: [`gaia/docs/LIVE-RELAYS.md`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md) · Map: [`atlas/docs/GUIDE.md`](https://github.com/alexar76/atlas/blob/main/docs/GUIDE.md) · Operator use cases: [`atlas/docs/OPERATOR-USE-CASES.md`](https://github.com/alexar76/atlas/blob/main/docs/OPERATOR-USE-CASES.md)

## One command

```bash
# List kinds
python3 scripts/add_gaia_atlas_sensor.py --help

# Example — Open-Meteo weather pin
python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-weather \
  --device-id om-wx-seoul \
  --lat 37.5665 --lon 126.9780 \
  --place Seoul \
  --alias seoul --alias сеул --alias 서울

# Example — weather + air pair (two pins, one place)
python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-pair \
  --slug seoul --place Seoul \
  --lat 37.5665 --lon 126.9780 \
  --alias seoul --alias сеул

# Example — NWS station
python3 scripts/add_gaia_atlas_sensor.py \
  --kind nws --device-id nws-ksfo --station KSFO \
  --lat 37.6196 --lon -122.3748 --place "SFO Airport"

# Example — SIM only (no upstream → badge SIM, never LIVE)
python3 scripts/add_gaia_atlas_sensor.py \
  --kind sim-weather --device-id ws-lab-01 \
  --lat 46.95 --lon 7.45 --place "Lab campus"
```

What the command does:

1. Appends to `gaia/config/extra_sensors.yaml`
2. Mirrors to `atlas/config/extra_sensors.yaml`
3. On next deploy, GAIA registers the device in the **fleet**; ATLAS shows the **pin**

Then: **redeploy GAIA → ATLAS**. LIVE kinds need `GAIA_ENABLE_LIVE=1`.

## Supported `--kind` values

| kind | Mode | Needs |
|------|------|-------|
| `open-meteo-weather` | LIVE | `--device-id` `--lat` `--lon` |
| `open-meteo-air` | LIVE | idem |
| `open-meteo-pair` | LIVE ×2 | `--slug` `--lat` `--lon` → `om-wx-*` + `om-aq-*` |
| `nws` | LIVE | `--device-id` `--station` `--lat` `--lon` |
| `opensensemap` | LIVE | `--device-id` `--box-id` `--lat` `--lon` |
| `noaa-tide` | LIVE | `--device-id` `--station?` `--lat` `--lon` |
| `usgs-river` | LIVE | `--device-id` `--usgs-site?` `--lat` `--lon` |
| `ndbc-buoy` | LIVE | `--device-id` `--station?` `--lat` `--lon` |
| `open-meteo-marine` | LIVE | `--device-id` `--lat` `--lon` |
| `openaq` | LIVE | `--device-id` + host `GAIA_OPENAQ_API_KEY` |
| `uk-grid` | LIVE | `--device-id` (lat/lon default UK) |
| `usgs-quake` | LIVE | `--device-id` |
| `firms-fire` | LIVE | `--device-id` (optional `params.map_key`) |
| `safecast` | LIVE | `--device-id` `--lat` `--lon` (CC0) |
| `cybernews-jamming` | LIVE | `--device-id` (CC BY 4.0) |
| `sim-weather` / `sim-air` / `sim-energy` | SIM | `--device-id` `--lat` `--lon` |

## Mental model

```
GAIA device (reading + optional source)
        │  gaia.fleet.status@v1
        ▼
ATLAS pin (catalog ∩ fleet) ── LIVE iff source is set; else SIM
```

| Term | Meaning |
|------|---------|
| **sensor** | Physical claim or relay. RU: **датчик**. |
| **relay** | LIVE public-API upstream — key attests custody, not ownership. |
| **device_id** | Id in the **fleet** / on the **pin**. |
| **LIVE** / **SIM** | Mode badges — **never translate** in UI. |
| **anchor** | Operator lat/lon — buyers never pass coordinates into invoke. |

## Recipe B — brand-new upstream API (not one-command)

1. Subclass `LiveDevice` in `gaia/gaia/devices/live.py` **or** `live_p2.py` (licence-pinned extra relays) + set `source`.
2. Allowlist host in `_ALLOWED_HOSTS`.
3. Register in `build_live_fleet()` (or add a new `--kind` to `extra_sensors` + CLI).
4. New fields → `PHYSICS` + `_FIELD_UNITS`.
5. Capability SKU if needed (`build_spec`).
6. Prefer exposing the new kind via `scripts/add_gaia_atlas_sensor.py` so the next person gets one command.
7. Mirror into ATLAS `STATION_CATALOG` / `LAYER_META`. Analyst learns the layer at request time; run `python3 scripts/sync_knowledge_base.py --write` so ARGUS, Alien Monitor, web support, and the 5-language knowledge bases learn the SKU automatically.
8. Docs row in LIVE-RELAYS (+ i18n) · tests · honesty (offline → no debit).

## Sync & CI

```bash
./scripts/sync_physical_sensor_catalogs.sh        # gaia → atlas
./scripts/sync_physical_sensor_catalogs.sh --check
python3 -m pytest tests/test_om_mesh_catalog_sync.py tests/test_extra_sensors_catalog_sync.py -q
```

(`scripts/add_om_mesh_city.py` remains as a thin helper; prefer `add_gaia_atlas_sensor.py --kind open-meteo-pair`.)

## Related

| Surface | URL |
|---------|-----|
| GAIA | [iot.modelmarket.dev](https://iot.modelmarket.dev/) |
| ATLAS | [atlas.modelmarket.dev](https://atlas.modelmarket.dev/) |
| Alien Monitor | `atlas` on [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) |
