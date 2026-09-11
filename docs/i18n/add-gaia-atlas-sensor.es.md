# Añadir un sensor a GAIA + ATLAS

**Idiomas:** [EN](../add-gaia-atlas-sensor.md) · [RU](add-gaia-atlas-sensor.ru.md) · [ES](add-gaia-atlas-sensor.es.md) · [FR](add-gaia-atlas-sensor.fr.md) · [ZH](add-gaia-atlas-sensor.zh.md)

> ## AVISO — léelo primero
>
> **Un solo comando añade un sensor solo si el kind ya existe en el código de GAIA**
> (Open-Meteo, NWS, openSenseMap, NOAA tide, USGS river, NDBC, OpenAQ, UK grid,
> USGS quake, NASA FIRMS, Safecast, CyberNews GNSS o SIM).
>
> **No** inventa una API upstream nueva, **no** amplía el allowlist ni crea campos
> nuevos. Para una API pública nueva hace falta una subclase `LiveDevice`
> (receta B). Está prohibido marcar **LIVE** sin provenance `source`.
>
> **Licencias:** solo fuentes libremente comercializables como SKU del Hub
> (FIRMS / Safecast CC0 / CyberNews CC BY / feeder propio). No añadir GFW,
> Stanford CC BY-NC, ADSBx commercial — ver [`LIVE-RELAYS`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md).
>
> Términos: [`localization-glossary.md`](../localization-glossary.md)

## Un comando

```bash
python3 scripts/add_gaia_atlas_sensor.py --help

python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-pair \
  --slug seoul --place Seoul \
  --lat 37.5665 --lon 126.9780 \
  --alias seoul
```

Escribe `gaia/config/extra_sensors.yaml` y lo espeja en ATLAS. Luego: **redeploy GAIA → ATLAS**.

Tabla de kinds: [versión EN](../add-gaia-atlas-sensor.md#supported---kind-values).

## Receta B — API upstream nueva

`LiveDevice` en `live.py` **o** `live_p2.py` (relés con licencia fijada) + allowlist + PHYSICS. Espejar en ATLAS `STATION_CATALOG`. Analyst ve la capa al instante; `python3 scripts/sync_knowledge_base.py --write` para que ARGUS, Monitor y las bases ×5 aprendan el SKU. Detalle: [EN](../add-gaia-atlas-sensor.md#recipe-b--brand-new-upstream-api-not-one-command).
