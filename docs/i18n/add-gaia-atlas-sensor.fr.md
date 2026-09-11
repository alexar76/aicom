# Ajouter un capteur à GAIA + ATLAS

**Langues :** [EN](../add-gaia-atlas-sensor.md) · [RU](add-gaia-atlas-sensor.ru.md) · [ES](add-gaia-atlas-sensor.es.md) · [FR](add-gaia-atlas-sensor.fr.md) · [ZH](add-gaia-atlas-sensor.zh.md)

> ## AVERTISSEMENT — à lire d’abord
>
> **Une seule commande ajoute un capteur seulement si le kind existe déjà dans le code GAIA**
> (Open-Meteo, NWS, openSenseMap, NOAA tide, USGS river, NDBC, OpenAQ, UK grid,
> USGS quake, NASA FIRMS, Safecast, CyberNews GNSS ou SIM).
>
> Elle **n’invente pas** une nouvelle API upstream, **n’étend pas** l’allowlist et
> **ne crée pas** de nouveaux champs. Pour une nouvelle API publique : sous-classe
> `LiveDevice` (recette B). Interdit de marquer **LIVE** sans provenance `source`.
>
> **Licences :** uniquement des sources librement commercialisables comme SKU Hub
> (FIRMS / Safecast CC0 / CyberNews CC BY / feeder propre). Ne pas ajouter GFW,
> Stanford CC BY-NC, ADSBx commercial — voir [`LIVE-RELAYS`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md).
>
> Termes : [`localization-glossary.md`](../localization-glossary.md)

## Une commande

```bash
python3 scripts/add_gaia_atlas_sensor.py --help

python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-pair \
  --slug seoul --place Seoul \
  --lat 37.5665 --lon 126.9780 \
  --alias seoul
```

Écrit `gaia/config/extra_sensors.yaml` et le miroir ATLAS. Ensuite : **redeploy GAIA → ATLAS**.

Table des kinds : [version EN](../add-gaia-atlas-sensor.md#supported---kind-values).

## Recette B — nouvelle API upstream

`LiveDevice` dans `live.py` **ou** `live_p2.py` (relais à licence épinglée) + allowlist + PHYSICS. Miroir dans ATLAS `STATION_CATALOG`. Analyst voit la couche immédiatement ; `python3 scripts/sync_knowledge_base.py --write` pour qu'ARGUS, le Monitor et les bases ×5 apprennent le SKU. Détail : [EN](../add-gaia-atlas-sensor.md#recipe-b--brand-new-upstream-api-not-one-command).
