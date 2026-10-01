# 向 GAIA + ATLAS 添加传感器

**语言：** [EN](../add-gaia-atlas-sensor.md) · [RU](add-gaia-atlas-sensor.ru.md) · [ES](add-gaia-atlas-sensor.es.md) · [FR](add-gaia-atlas-sensor.fr.md) · [ZH](add-gaia-atlas-sensor.zh.md)

> ## 免责声明 — 请先阅读
>
> **一条命令只能添加 GAIA 代码里已经存在的 kind**
>（Open-Meteo、NWS、openSenseMap、NOAA tide、USGS river、NDBC、OpenAQ、UK grid、
> USGS quake、NASA FIRMS、Safecast、CyberNews GNSS 或 SIM）。
>
> 它**不会**发明新的上游 API、**不会**扩展 allowlist、**不会**创建新的测量字段。
> 若要接入全新公共 API，仍需编写 `LiveDevice` 子类（方案 B）。
> 没有 provenance `source` 时禁止标为 **LIVE**。
>
> **许可过滤：** 仅可自由商用的来源可作为 Hub SKU
>（FIRMS / Safecast CC0 / CyberNews CC BY / 自有 feeder）。不要加入 GFW、
> Stanford CC BY-NC、ADSBx commercial — 见 [`LIVE-RELAYS`](https://github.com/alexar76/gaia/blob/main/docs/LIVE-RELAYS.md)。
>
> 术语：[`localization-glossary.md`](../localization-glossary.md)

## 一条命令

```bash
python3 scripts/add_gaia_atlas_sensor.py --help

python3 scripts/add_gaia_atlas_sensor.py \
  --kind open-meteo-pair \
  --slug seoul --place Seoul \
  --lat 37.5665 --lon 126.9780 \
  --alias seoul --alias 首尔
```

写入 `gaia/config/extra_sensors.yaml` 并镜像到 ATLAS。然后：**先部署 GAIA，再部署 ATLAS**。

kinds 表见 [英文版](../add-gaia-atlas-sensor.md#supported---kind-values)。

## 方案 B — 全新上游 API

在 `live.py` **或** `live_p2.py`（许可证已钉死的额外中继）写 `LiveDevice` + allowlist + PHYSICS。镜像到 ATLAS `STATION_CATALOG`。Analyst 立即看到图层；运行 `python3 scripts/sync_knowledge_base.py --write`，ARGUS、Monitor 与五种语言知识库才会自动学会该 SKU。详情：[EN](../add-gaia-atlas-sensor.md#recipe-b--brand-new-upstream-api-not-one-command)。
