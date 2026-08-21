# Добавить датчик в GAIA + ATLAS

**Языки:** [EN](../add-gaia-atlas-sensor.md) · [RU](add-gaia-atlas-sensor.ru.md) · [ES](add-gaia-atlas-sensor.es.md) · [FR](add-gaia-atlas-sensor.fr.md) · [ZH](add-gaia-atlas-sensor.zh.md)

> ## ДИСКЛЕЙМЕР — прочитайте сначала
>
> **Одна команда добавляет датчик только если kind уже есть в коде GAIA**
> (Open-Meteo, NWS, openSenseMap, NOAA tide, USGS river, NDBC, OpenAQ, UK grid,
> USGS quake, NASA FIRMS, Safecast, CyberNews GNSS или SIM).
>
> Она **не** создаёт новый upstream API, **не** расширяет allowlist и **не**
> придумывает новые поля. Для нового публичного API нужен подкласс
> `LiveDevice` (рецепт B). **LIVE** без provenance `source` запрещён.
>
> **Лицензии:** только свободно коммерциализируемые источники как Hub SKU
> (FIRMS / Safecast CC0 / CyberNews CC BY / свой feeder). Не добавлять GFW,
> Stanford CC BY-NC, ADSBx commercial — см. [`LIVE-RELAYS`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md).
>
> Термины: [`localization-glossary.md`](../localization-glossary.md)

## Одна команда

```bash
python3 scripts/add_gaia_atlas_sensor.py --help

python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-weather \
  --device-id om-wx-seoul \
  --lat 37.5665 --lon 126.9780 \
  --place Seoul \
  --alias seoul --alias сеул --alias 서울

python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-pair \
  --slug seoul --place Seoul \
  --lat 37.5665 --lon 126.9780 \
  --alias seoul --alias сеул
```

Команда пишет `gaia/config/extra_sensors.yaml`, зеркалит в ATLAS. Дальше: **redeploy GAIA → ATLAS** (`GAIA_ENABLE_LIVE=1` для LIVE).

## Что поддерживается

См. таблицу kinds в [EN-версии](../add-gaia-atlas-sensor.md#supported---kind-values).

## Рецепт B — новый upstream API

Код `LiveDevice` в `live.py` **или** `live_p2.py` (реле с зафиксированной лицензией) + allowlist + PHYSICS + (желательно) новый `--kind` в CLI. Зеркалить в ATLAS `STATION_CATALOG`. Analyst видит слой сразу; `python3 scripts/sync_knowledge_base.py --write` — чтобы ARGUS, Monitor и базы знаний ×5 узнали SKU.
