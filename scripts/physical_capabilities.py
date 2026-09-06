"""Physical/map SKU roster generated from ATLAS catalog — not a hand-typed list.

Source of truth: ``atlas.stations.STATION_CATALOG`` + ``LAYER_META`` +
``atlas.products.PRODUCT_CAPS``. A new pin in the catalog appears here on the next
``python3 scripts/sync_knowledge_base.py --write``. ``--check`` fails if any knowledge
base still has the previous table.

Rendering constraints match ``ecosystem_knowledge.py``: no backticks, no ``${``,
no triple quotes — the block is embedded in ARGUS's TS template literal and ATLAS's
Python triple-quoted brief.
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "atlas"))

from atlas.products import PRODUCT_CAPS  # noqa: E402
from atlas.stations import LAYER_META, STATION_CATALOG  # noqa: E402

BEGIN = "BEGIN GENERATED physical-capabilities"
END = "END GENERATED physical-capabilities"

# Plumbing SKUs that are not map pins. Stable; not a layer roster.
_GAIA_META: tuple[tuple[str, str], ...] = (
    ("gaia.window@v1", "N readings of one device_id in one invoke"),
    ("gaia.verify@v1", "plausibility verdict as a sellable good"),
    ("gaia.fleet.status@v1", "device registry incl. pinned pubkeys — free"),
)

# Honesty notes that the catalog cannot infer (licence / not-X). A SKU without a
# row still appears — the overlay is optional, the roster is not.
_HONEST: dict[str, dict[str, str]] = {
    "gaia.smoke.read@v1": {
        "en": "full signed polygon rings + holes, not just centroids; qualitative density, not PM2.5",
        "ru": "подписанные контуры полигонов с отверстиями, не только центроиды; качественная плотность, не PM2.5",
        "es": "anillos de polígono firmados con huecos, no solo centroides; densidad cualitativa, no PM2.5",
        "fr": "anneaux de polygones signés avec trous, pas seulement les centroïdes ; densité qualitative, pas PM2.5",
        "zh": "完整签名多边形环及内环，不只是质心；定性浓度等级，不是 PM2.5",
    },
    "gaia.water_quality.read@v1": {
        "en": "fresh (48h default) paginated latest-continuous observations joined to the official USGS monitoring-locations registry; filters and per-series approval/qualifiers; one station = one coordinate",
        "ru": "свежие (48 ч по умолчанию) постраничные latest-continuous наблюдения с join к USGS monitoring-locations; фильтры и approval/qualifiers по рядам; одна станция = одна координата",
        "es": "observaciones latest-continuous frescas (48 h por defecto), paginadas y unidas a USGS monitoring-locations; filtros y approval/qualifiers; una estación = una coordenada",
        "fr": "observations latest-continuous fraîches (48 h par défaut), paginées et jointes à USGS monitoring-locations ; filtres et approval/qualifiers ; une station = une coordonnée",
        "zh": "新鲜（默认 48 小时）分页 latest-continuous 观测联接官方 USGS monitoring-locations；筛选及逐序列 approval/qualifiers；一站一坐标",
    },
    "gaia.dart.read@v1": {
        "en": "all active stations in the NDBC directory; gauge, not a tsunami warning",
        "ru": "все активные станции каталога NDBC; уровнемер, не предупреждение о цунами",
        "es": "todas las estaciones activas del directorio NDBC; medidor, no alerta de tsunami",
        "fr": "toutes les stations actives du répertoire NDBC ; jauge, pas alerte tsunami",
        "zh": "NDBC 目录中的全部活动站；是水位计，不是海啸警报",
    },
    "gaia.radnet.read@v1": {
        "en": "all 140 official EPA monitor coordinates; cite EPA RadNet",
        "ru": "все 140 официальных координат мониторов EPA; атрибуция EPA RadNet",
        "es": "las 140 coordenadas oficiales de monitores EPA; atribuir EPA RadNet",
        "fr": "les 140 coordonnées officielles des moniteurs EPA ; attribuer EPA RadNet",
        "zh": "全部 140 个 EPA 官方监测点坐标；注明 EPA RadNet",
    },
    "gaia.radar.status.read@v1": {
        "en": "all WSR-88D sites returned at their own coordinates; status, not reflectivity",
        "ru": "все станции WSR-88D в собственных координатах; статус, не отражаемость",
        "es": "todos los sitios WSR-88D en sus coordenadas; estado, no reflectividad",
        "fr": "tous les sites WSR-88D à leurs coordonnées ; état, pas réflectivité",
        "zh": "全部 WSR-88D 站点按各自坐标返回；是状态，不是反射率",
    },
    "gaia.precipitation.read@v1": {
        "en": "any buyer coordinate; returned IMERG source cell; preliminary",
        "ru": "любая координата покупателя; возвращается ячейка IMERG; предварительные данные",
        "es": "cualquier coordenada del comprador; celda IMERG devuelta; preliminar",
        "fr": "toute coordonnée acheteur ; cellule IMERG renvoyée ; préliminaire",
        "zh": "任意买方坐标；返回 IMERG 源网格；初步数据",
    },
    "gaia.atmosphere.read@v1": {
        "en": "any buyer coordinate; CAMS data CC BY 4.0; commercial hosting required",
        "ru": "любая координата покупателя; CAMS CC BY 4.0; нужен коммерческий хостинг",
        "es": "cualquier coordenada del comprador; CAMS CC BY 4.0; requiere hosting comercial",
        "fr": "toute coordonnée acheteur ; CAMS CC BY 4.0 ; hébergement commercial requis",
        "zh": "任意买方坐标；CAMS 数据 CC BY 4.0；需商业托管",
    },
    "gaia.soil_moisture.read@v1": {
        "en": "any buyer coordinate; returned CLMS source/query cell",
        "ru": "любая координата покупателя; возвращается исходная/расчётная ячейка CLMS",
        "es": "cualquier coordenada del comprador; celda fuente/consulta CLMS devuelta",
        "fr": "toute coordonnée acheteur ; cellule source/requête CLMS renvoyée",
        "zh": "任意买方坐标；返回 CLMS 源/查询网格",
    },
    "gaia.solar.read@v1": {
        "en": "any buyer coordinate; returned NASA POWER source coordinate",
        "ru": "любая координата покупателя; возвращается координата источника NASA POWER",
        "es": "cualquier coordenada del comprador; coordenada fuente NASA POWER devuelta",
        "fr": "toute coordonnée acheteur ; coordonnée source NASA POWER renvoyée",
        "zh": "任意买方坐标；返回 NASA POWER 源坐标",
    },
    "gaia.snow.read@v1": {
        "en": "any buyer coordinate in CONUS; returned exact SNODAS cell",
        "ru": "любая координата покупателя в CONUS; возвращается точная ячейка SNODAS",
        "es": "cualquier coordenada del comprador en CONUS; celda SNODAS exacta",
        "fr": "toute coordonnée acheteur en CONUS ; cellule SNODAS exacte renvoyée",
        "zh": "CONUS 内任意买方坐标；返回精确 SNODAS 网格",
    },
    "gaia.sea_ice.read@v1": {
        "en": "any Arctic buyer coordinate; returned exact 25-km cell; not for navigation",
        "ru": "любая арктическая координата; точная ячейка 25 км; не для навигации",
        "es": "cualquier coordenada ártica; celda exacta de 25 km; no para navegación",
        "fr": "toute coordonnée arctique ; cellule exacte de 25 km ; pas pour la navigation",
        "zh": "任意北极买方坐标；返回精确 25 公里网格；不可用于导航",
    },
    "gaia.land_temperature.read@v1": {
        "en": "any buyer coordinate; returned Sentinel-3 SLSTR source cell",
        "ru": "любая координата покупателя; возвращается ячейка Sentinel-3 SLSTR",
        "es": "cualquier coordenada del comprador; celda Sentinel-3 SLSTR devuelta",
        "fr": "toute coordonnée acheteur ; cellule Sentinel-3 SLSTR renvoyée",
        "zh": "任意买方坐标；返回 Sentinel-3 SLSTR 源网格",
    },
    "gaia.fire.read@v1": {
        "en": "cite NASA FIRMS; not a fire perimeter",
        "ru": "цитировать NASA FIRMS; не периметр пожара",
        "es": "citar NASA FIRMS; no es un perímetro de incendio",
        "fr": "citer NASA FIRMS; pas un périmètre d'incendie",
        "zh": "须注明 NASA FIRMS；不是火场周界",
    },
    "gaia.lightning.read@v1": {
        "en": "GOES GLM CONUS; not Blitzortung",
        "ru": "GOES GLM CONUS; не Blitzortung",
        "es": "GOES GLM CONUS; no Blitzortung",
        "fr": "GOES GLM CONUS; pas Blitzortung",
        "zh": "GOES GLM（CONUS）；不是 Blitzortung",
    },
    "gaia.flood.read@v1": {
        "en": "NWS CAP US and/or UK EA OGL England; not GloFAS; not an in-situ gauge",
        "ru": "NWS CAP США и/или EA OGL Англия; не GloFAS; не in-situ уровнемер",
        "es": "NWS CAP EE.UU. y/o EA OGL Inglaterra; no GloFAS; no un aforo in situ",
        "fr": "NWS CAP USA et/ou EA OGL Angleterre; pas GloFAS; pas un limnimètre",
        "zh": "NWS CAP（美国）和/或 EA OGL（英格兰）；不是 GloFAS；不是现场水位计",
    },
    "gaia.ais.read@v1": {
        "en": "own-edge feeder; not Fintraffic public AIS",
        "ru": "свой edge; не публичный AIS Fintraffic",
        "es": "feeder propio; no es el AIS público Fintraffic",
        "fr": "feeder opérateur; pas l'AIS public Fintraffic",
        "zh": "自有边缘 feeder；不是 Fintraffic 公共 AIS",
    },
    "gaia.ais.public.read@v1": {
        "en": "Fintraffic CC BY 4.0 (FI) or Kystverket NLOD (NO); not own-edge gaia.ais.read",
        "ru": "Fintraffic CC BY 4.0 (FI) или Kystverket NLOD (NO); не own-edge gaia.ais.read",
        "es": "Fintraffic CC BY 4.0 (FI) o Kystverket NLOD (NO); no gaia.ais.read propio",
        "fr": "Fintraffic CC BY 4.0 (FI) ou Kystverket NLOD (NO); pas gaia.ais.read edge",
        "zh": "Fintraffic CC BY 4.0（芬兰）或 Kystverket NLOD（挪威）；不是自有 gaia.ais.read",
    },
    "gaia.tsunami.read@v1": {
        "en": "NWS CAP and/or PTWC Atom warning product, not a tide gauge; empty = offline",
        "ru": "NWS CAP и/или PTWC Atom, не мареограф; пустая лента = offline",
        "es": "producto CAP NWS y/o Atom PTWC, no un mareógrafo; vacío = offline",
        "fr": "CAP NWS et/ou Atom PTWC, pas un marégraphe; vide = offline",
        "zh": "NWS CAP 和/或 PTWC Atom 警报产品，不是验潮仪；空源=离线",
    },
    "gaia.cyclone.read@v1": {
        "en": "NHC/CPHC AL+EP+CP only; not JTWC; not EONET; empty season = offline",
        "ru": "только NHC/CPHC AL+EP+CP; не JTWC; не EONET; пустой сезон = offline",
        "es": "solo NHC/CPHC AL+EP+CP; no JTWC; no EONET; temporada vacía = offline",
        "fr": "NHC/CPHC AL+EP+CP uniquement; pas JTWC; pas EONET; saison vide = offline",
        "zh": "仅 NHC/CPHC AL+EP+CP；不是 JTWC；不是 EONET；空季=离线",
    },
    "gaia.adsb.public.read@v1": {
        "en": "ADSB.lol ODbL 1.0; isolate derived DB; not own-edge; no OpenSky/ADSBx fallback",
        "ru": "ADSB.lol ODbL 1.0; изолировать производную БД; не own-edge; без OpenSky/ADSBx",
        "es": "ADSB.lol ODbL 1.0; aislar BD derivada; no edge propio; sin OpenSky/ADSBx",
        "fr": "ADSB.lol ODbL 1.0; isoler la BD dérivée; pas edge; pas OpenSky/ADSBx",
        "zh": "ADSB.lol ODbL 1.0；隔离派生库；不是自有边缘；不回退 OpenSky/ADSBx",
    },
    "gaia.geomag.read@v1": {
        "en": "USGS F only; not INTERMAGNET",
        "ru": "только USGS F; не INTERMAGNET",
        "es": "solo USGS F; no INTERMAGNET",
        "fr": "USGS F uniquement; pas INTERMAGNET",
        "zh": "仅 USGS F；不是 INTERMAGNET",
    },
    "gaia.effis.read@v1": {
        "en": "Copernicus EFFIS EU, CC BY 4.0; not FIRMS",
        "ru": "Copernicus EFFIS ЕС, CC BY 4.0; не FIRMS",
        "es": "Copernicus EFFIS UE, CC BY 4.0; no FIRMS",
        "fr": "Copernicus EFFIS UE, CC BY 4.0; pas FIRMS",
        "zh": "Copernicus EFFIS（欧盟）CC BY 4.0；不是 FIRMS",
    },
    "gaia.adsb.read@v1": {
        "en": "own-edge dump1090; opt-in; offline until ingest",
        "ru": "свой dump1090; opt-in; offline до ingest",
        "es": "dump1090 propio; opt-in; offline hasta ingest",
        "fr": "dump1090 opérateur; opt-in; offline jusqu'à ingest",
        "zh": "自有 dump1090；opt-in；未 ingest 前离线",
    },
    "gaia.iot.read@v1": {
        "en": "own-edge Tasmota/TTN/SenML; opt-in",
        "ru": "свой Tasmota/TTN/SenML; opt-in",
        "es": "Tasmota/TTN/SenML propio; opt-in",
        "fr": "Tasmota/TTN/SenML opérateur; opt-in",
        "zh": "自有 Tasmota/TTN/SenML；opt-in",
    },
    "gaia.spacewx.read@v1": {
        "en": "NOAA SWPC Kp; Boulder pin, planetary index",
        "ru": "NOAA SWPC Kp; пин Boulder, планетарный индекс",
        "es": "NOAA SWPC Kp; pin Boulder, índice planetario",
        "fr": "NOAA SWPC Kp; pin Boulder, indice planétaire",
        "zh": "NOAA SWPC Kp；Boulder 针脚，行星指数",
    },
    "gaia.volcano.read@v1": {
        "en": "USGS elevated volcanoes; not a global ash forecast",
        "ru": "USGS elevated volcanoes; не глобальный прогноз пепла",
        "es": "volcanes elevados USGS; no un pronóstico global de ceniza",
        "fr": "volcans élevés USGS; pas une prévision mondiale de cendres",
        "zh": "USGS 升高火山；不是全球火山灰预报",
    },
    "gaia.argo.read@v1": {
        "en": "official GDAC floats; cite DOI 10.17882/42182",
        "ru": "официальные поплавки GDAC; цитировать DOI 10.17882/42182",
        "es": "flotadores GDAC oficiales; citar DOI 10.17882/42182",
        "fr": "flotteurs GDAC officiels; citer DOI 10.17882/42182",
        "zh": "官方 GDAC 浮标；注明 DOI 10.17882/42182",
    },
    "gaia.jamming.read@v1": {
        "en": "CyberNews GNSS CC BY 4.0; not GPSJam; not RF sensing",
        "ru": "CyberNews GNSS CC BY 4.0; не GPSJam; не RF-сенсорика",
        "es": "CyberNews GNSS CC BY 4.0; no GPSJam; no sensing RF",
        "fr": "CyberNews GNSS CC BY 4.0; pas GPSJam; pas de sensing RF",
        "zh": "CyberNews GNSS CC BY 4.0；不是 GPSJam；不是射频传感",
    },
    "atlas.situation.brief@v1": {
        "en": "defaults include flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B; not spacewx/geomag/argo",
        "ru": "по умолчанию flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B; не spacewx/geomag/argo",
        "es": "por defecto flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B; no spacewx/geomag/argo",
        "fr": "par défaut flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B; pas spacewx/geomag/argo",
        "zh": "默认含 flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B；不含 spacewx/geomag/argo",
    },
    "atlas.smoke.operations@v1": {
        "en": "point-in-polygon against the signed HMS ring + colocated PM2.5/AQI; refuses on a truncated inventory; not measured PM2.5 and not an evacuation order",
        "ru": "point-in-polygon по подписанному контуру HMS + PM2.5/AQI в той же точке; отказ при неполной выгрузке; не измеренный PM2.5 и не приказ об эвакуации",
        "es": "point-in-polygon contra el contorno HMS firmado + PM2.5/AQI colocalizado; rechaza si el inventario está truncado; no es PM2.5 medido ni una orden de evacuación",
        "fr": "point-in-polygon sur le contour HMS signé + PM2.5/AQI au même point ; refus si l'inventaire est tronqué ; ni PM2.5 mesuré ni ordre d'évacuation",
        "zh": "对已签名 HMS 多边形做点面判断 + 同坐标 PM2.5/AQI；清单不完整则拒答；不是实测 PM2.5，也不是疏散命令",
    },
    "atlas.fire.weather@v1": {
        "en": "FIRMS and/or EFFIS + nearby weather; two lists; not a forecast",
        "ru": "FIRMS и/или EFFIS + погода; два списка; не прогноз",
        "es": "FIRMS y/o EFFIS + clima cercano; dos listas; no un pronóstico",
        "fr": "FIRMS et/ou EFFIS + météo proche; deux listes; pas une prévision",
        "zh": "FIRMS 和/或 EFFIS + 附近天气；两个列表；不是预报",
    },
    "atlas.geomag.window@v1": {
        "en": "SWPC planetary Kp → NOAA state/G-scale + nearest USGS observatory F; total field only, NOT a declination correction and not safety-of-life",
        "ru": "планетарный Kp SWPC → состояние/G-шкала NOAA + F ближайшей обсерватории USGS; только полное поле, НЕ поправка на склонение и не safety-of-life",
        "es": "Kp planetario de SWPC → estado/escala G de NOAA + F del observatorio USGS más cercano; solo campo total, NO una corrección de declinación ni safety-of-life",
        "fr": "Kp planétaire SWPC → état/échelle G NOAA + F de l'observatoire USGS le plus proche ; champ total seulement, PAS une correction de déclinaison ni safety-of-life",
        "zh": "SWPC 行星 Kp → NOAA 状态/G 级 + 最近 USGS 观测台 F；仅总场，不是磁偏角改正，也不是生命安全服务",
    },
    "atlas.route.integrity@v1": {
        "en": "per-segment corridor brief: GNSS field + reported interference zones + AIS/ADS-B presence + hazard pins; reported interference is NOT proof of jamming, not safety-of-life",
        "ru": "посегментный брифинг по коридору: поле GNSS + заявленные зоны помех + присутствие AIS/ADS-B + пины опасностей; заявленные помехи НЕ доказательство глушения, не safety-of-life",
        "es": "brief de corredor por segmento: campo GNSS + zonas de interferencia reportadas + presencia AIS/ADS-B + pines de peligro; la interferencia reportada NO es prueba de jamming ni safety-of-life",
        "fr": "brief de corridor par segment : champ GNSS + zones d'interférence signalées + présence AIS/ADS-B + pins de danger ; une interférence signalée n'est PAS une preuve de brouillage, ni safety-of-life",
        "zh": "逐段走廊简报：GNSS 场 + 已报告干扰区 + AIS/ADS-B 存在 + 危险点位；已报告干扰不是干扰证据，也不是生命安全服务",
    },
    "atlas.observability.attest@v1": {
        "en": "data-availability attestation: nearest NEXRAD + ARCHIVED status samples in a window; an archive gap is absence of evidence, NOT evidence the radar was down; U.S. only",
        "ru": "аттестация наличия данных: ближайшие NEXRAD + АРХИВНЫЕ выборки статуса в окне; пробел в архиве это отсутствие доказательства, а НЕ доказательство простоя радара; только США",
        "es": "atestación de disponibilidad de datos: NEXRAD más cercano + muestras de estado ARCHIVADAS en una ventana; un hueco en el archivo es ausencia de evidencia, NO evidencia de que el radar estuviera caído; solo EE. UU.",
        "fr": "attestation de disponibilité des données : NEXRAD le plus proche + échantillons de statut ARCHIVÉS sur une fenêtre ; un trou dans l'archive est une absence de preuve, PAS la preuve d'une panne radar ; États-Unis seulement",
        "zh": "数据可得性证明：最近的 NEXRAD + 窗口内的归档状态样本；归档缺口是证据缺失，而不是雷达停机的证据；仅限美国",
    },
    "atlas.pv.irradiance.record@v1": {
        "en": "NASA POWER daily all-sky vs clear-sky + CAMS aerosol/dust at the plant coordinate; a retrospective record of fact, NOT a yield forecast or a soiling-loss model",
        "ru": "суточная инсоляция NASA POWER (all-sky против clear-sky) + аэрозоль/пыль CAMS в точке площадки; протокол факта задним числом, НЕ прогноз выработки и не модель потерь на запылении",
        "es": "irradiación diaria NASA POWER (all-sky vs clear-sky) + aerosol/polvo CAMS en la coordenada de la planta; registro retrospectivo de hechos, NO un pronóstico de producción ni un modelo de pérdidas por suciedad",
        "fr": "irradiation quotidienne NASA POWER (all-sky vs clear-sky) + aérosol/poussière CAMS à la coordonnée de la centrale ; relevé factuel rétrospectif, PAS une prévision de production ni un modèle de pertes par salissure",
        "zh": "电站坐标处 NASA POWER 日总辐照（全天空对晴空）+ CAMS 气溶胶/沙尘；回溯性事实记录，不是发电量预报，也不是积灰损失模型",
    },
}

_COPY: dict[str, dict[str, str]] = {
    "en": {
        "blurb": (
            "Generated from ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS — do not hand-edit. "
            "Run: python3 scripts/sync_knowledge_base.py --write. "
            "Live Hub search is the ceiling (GET https://modelmarket.dev/ai-market/v2/search). "
            "This table is the floor. Do not invent SKUs absent here or from Hub search. "
            "LIVE only with provenance source. Never present SIM as LIVE. "
            "Physical/map SKUs are Hub invoke, not oracle_call."
        ),
        "gaia": "GAIA (iot.modelmarket.dev) — device_id-anchored, ~$0.002 unless noted.",
        "meta": "GAIA plumbing (not a map pin)",
        "atlas": "ATLAS composites (atlas.modelmarket.dev) — billable decision artifacts.",
        "layers": "Map layers",
        "sku": "SKU",
        "layer": "layer",
        "devices": "example devices",
        "limit": "honest limit",
        "price": "USD",
        "what": "artifact",
        "fallback": "operator-anchored device_id; LIVE only with provenance source",
    },
    "ru": {
        "blurb": (
            "Сгенерировано из ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS — не править руками. "
            "Команда: python3 scripts/sync_knowledge_base.py --write. "
            "Живой поиск Hub — потолок (GET https://modelmarket.dev/ai-market/v2/search). "
            "Эта таблица — пол. Не выдумывать SKU, которых нет здесь или в поиске Hub. "
            "LIVE только с provenance source. SIM никогда не выдавать за LIVE. "
            "Физические SKU — Hub invoke, не oracle_call."
        ),
        "gaia": "GAIA (iot.modelmarket.dev) — якорь device_id, ~$0.002 если не указано иное.",
        "meta": "GAIA plumbing (не пин на карте)",
        "atlas": "Композиты ATLAS (atlas.modelmarket.dev) — платные артефакты решения.",
        "layers": "Слои карты",
        "sku": "SKU",
        "layer": "слой",
        "devices": "примеры устройств",
        "limit": "честный предел",
        "price": "USD",
        "what": "артефакт",
        "fallback": "якорь device_id оператора; LIVE только с provenance source",
    },
    "es": {
        "blurb": (
            "Generado desde ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS — no editar a mano. "
            "Comando: python3 scripts/sync_knowledge_base.py --write. "
            "La búsqueda viva del Hub es el techo (GET https://modelmarket.dev/ai-market/v2/search). "
            "Esta tabla es el suelo. No inventar SKUs ausentes aquí o en la búsqueda Hub. "
            "LIVE solo con provenance source. Nunca presentar SIM como LIVE. "
            "Los SKU físicos son Hub invoke, no oracle_call."
        ),
        "gaia": "GAIA (iot.modelmarket.dev) — anclado a device_id, ~$0.002 salvo nota.",
        "meta": "GAIA plumbing (no es un pin del mapa)",
        "atlas": "Composites ATLAS (atlas.modelmarket.dev) — artefactos de decisión de pago.",
        "layers": "Capas del mapa",
        "sku": "SKU",
        "layer": "capa",
        "devices": "dispositivos de ejemplo",
        "limit": "límite honesto",
        "price": "USD",
        "what": "artefacto",
        "fallback": "device_id anclado por el operador; LIVE solo con provenance source",
    },
    "fr": {
        "blurb": (
            "Généré depuis ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS — ne pas éditer à la main. "
            "Commande : python3 scripts/sync_knowledge_base.py --write. "
            "La recherche Hub en direct est le plafond (GET https://modelmarket.dev/ai-market/v2/search). "
            "Cette table est le plancher. Ne pas inventer de SKU absents ici ou de la recherche Hub. "
            "LIVE seulement avec provenance source. Jamais présenter SIM comme LIVE. "
            "Les SKU physiques sont Hub invoke, pas oracle_call."
        ),
        "gaia": "GAIA (iot.modelmarket.dev) — ancré device_id, ~$0.002 sauf mention.",
        "meta": "GAIA plumbing (pas un pin carte)",
        "atlas": "Composites ATLAS (atlas.modelmarket.dev) — artefacts de décision facturables.",
        "layers": "Couches carte",
        "sku": "SKU",
        "layer": "couche",
        "devices": "appareils d'exemple",
        "limit": "limite honnête",
        "price": "USD",
        "what": "artefact",
        "fallback": "device_id ancré par l'opérateur; LIVE seulement avec provenance source",
    },
    "zh": {
        "blurb": (
            "由 ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS 生成 — 请勿手改。 "
            "命令：python3 scripts/sync_knowledge_base.py --write。 "
            "Hub 实时搜索是上限（GET https://modelmarket.dev/ai-market/v2/search）。 "
            "本表是下限。不要捏造此处或 Hub 搜索中不存在的 SKU。 "
            "仅在有 provenance source 时为 LIVE。永远不要把 SIM 说成 LIVE。 "
            "物理/地图 SKU 走 Hub invoke，不是 oracle_call。"
        ),
        "gaia": "GAIA（iot.modelmarket.dev）— 锚定 device_id，未注明时约 $0.002。",
        "meta": "GAIA 管道（不是地图针脚）",
        "atlas": "ATLAS 组合（atlas.modelmarket.dev）— 可计费的决策产物。",
        "layers": "地图图层",
        "sku": "SKU",
        "layer": "图层",
        "devices": "示例设备",
        "limit": "诚实边界",
        "price": "USD",
        "what": "产物",
        "fallback": "运营方锚定 device_id；仅在有 provenance source 时为 LIVE",
    },
}


def _safe(text: str) -> str:
    return (
        str(text)
        .replace("`", "'")
        .replace("${", "{")
        .replace('"""', "''")
        .replace("|", "/")
        .strip()
    )


def _copy(lang: str) -> dict[str, str]:
    return _COPY.get((lang or "en").lower()[:2], _COPY["en"])


def _honest(sku: str, lang: str, fallback: str) -> str:
    row = _HONEST.get(sku) or {}
    loc = (lang or "en").lower()[:2]
    return _safe(row.get(loc) or row.get("en") or fallback)


def _layer_label(layer: str, lang: str) -> str:
    meta = LAYER_META.get(layer) or {}
    labels = meta.get("labels") if isinstance(meta.get("labels"), dict) else {}
    loc = (lang or "en").lower()[:2]
    if loc in labels and labels[loc]:
        return _safe(str(labels[loc]))
    return _safe(str(meta.get("label") or layer))


def catalog_rows() -> list[dict[str, Any]]:
    """One row per Hub SKU currently plotted on ATLAS pins."""
    by_cap: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for sid, meta in STATION_CATALOG.items():
        cap = str(meta.get("capability") or "").strip()
        if not cap:
            continue
        row = by_cap.get(cap)
        if row is None:
            by_cap[cap] = {
                "capability": cap,
                "layer": str(meta.get("layer") or ""),
                "devices": [sid],
            }
        else:
            row["devices"].append(sid)
    return list(by_cap.values())


def catalog_sku_ids() -> list[str]:
    ids = [r["capability"] for r in catalog_rows()]
    ids.extend(c for c, _ in _GAIA_META)
    ids.extend(
        str(p["capability_id"])
        for p in PRODUCT_CAPS
        if p.get("capability_id")
    )
    # stable unique
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


_DEVICE_SUMMARY: dict[str, dict[str, str]] = {
    "gaia.water_quality.read@v1": {
        "en": "usgs-wq-01 (bbox → complete qualified station registry)", "ru": "usgs-wq-01 (bbox → полный реестр подходящих станций)",
        "es": "usgs-wq-01 (bbox → registro completo de estaciones aptas)", "fr": "usgs-wq-01 (bbox → registre complet des stations qualifiées)",
        "zh": "usgs-wq-01（bbox → 完整合格站点注册表）",
    },
    "gaia.dart.read@v1": {
        "en": "noaa-dart-01, dart-* (all 43 active)", "ru": "noaa-dart-01, dart-* (все 43 активных)",
        "es": "noaa-dart-01, dart-* (los 43 activos)", "fr": "noaa-dart-01, dart-* (les 43 actifs)",
        "zh": "noaa-dart-01, dart-*（全部 43 个活动站）",
    },
    "gaia.radnet.read@v1": {
        "en": "radnet-* (all 140 official monitors)", "ru": "radnet-* (все 140 официальных мониторов)",
        "es": "radnet-* (los 140 monitores oficiales)", "fr": "radnet-* (les 140 moniteurs officiels)",
        "zh": "radnet-*（全部 140 个官方监测点）",
    },
    "gaia.radar.status.read@v1": {
        "en": "nexrad-status-01 (all WSR-88D sites)", "ru": "nexrad-status-01 (все станции WSR-88D)",
        "es": "nexrad-status-01 (todos los sitios WSR-88D)", "fr": "nexrad-status-01 (tous les sites WSR-88D)",
        "zh": "nexrad-status-01（全部 WSR-88D 站点）",
    },
    "gaia.precipitation.read@v1": {
        "en": "imerg-01 + buyer lat/lon", "ru": "imerg-01 + lat/lon покупателя",
        "es": "imerg-01 + lat/lon del comprador", "fr": "imerg-01 + lat/lon acheteur",
        "zh": "imerg-01 + 买方 lat/lon",
    },
    "gaia.atmosphere.read@v1": {
        "en": "cams-* + buyer lat/lon", "ru": "cams-* + lat/lon покупателя",
        "es": "cams-* + lat/lon del comprador", "fr": "cams-* + lat/lon acheteur",
        "zh": "cams-* + 买方 lat/lon",
    },
    "gaia.soil_moisture.read@v1": {
        "en": "soil-* + buyer lat/lon", "ru": "soil-* + lat/lon покупателя",
        "es": "soil-* + lat/lon del comprador", "fr": "soil-* + lat/lon acheteur",
        "zh": "soil-* + 买方 lat/lon",
    },
    "gaia.solar.read@v1": {
        "en": "solar-* + buyer lat/lon", "ru": "solar-* + lat/lon покупателя",
        "es": "solar-* + lat/lon del comprador", "fr": "solar-* + lat/lon acheteur",
        "zh": "solar-* + 买方 lat/lon",
    },
    "gaia.snow.read@v1": {
        "en": "snow-* + buyer CONUS lat/lon", "ru": "snow-* + lat/lon покупателя в CONUS",
        "es": "snow-* + lat/lon del comprador en CONUS", "fr": "snow-* + lat/lon acheteur en CONUS",
        "zh": "snow-* + CONUS 内买方 lat/lon",
    },
    "gaia.sea_ice.read@v1": {
        "en": "nsidc-ice-01 + buyer Arctic lat/lon", "ru": "nsidc-ice-01 + арктические lat/lon покупателя",
        "es": "nsidc-ice-01 + lat/lon árticos del comprador", "fr": "nsidc-ice-01 + lat/lon arctique acheteur",
        "zh": "nsidc-ice-01 + 买方北极 lat/lon",
    },
    "gaia.land_temperature.read@v1": {
        "en": "lst-* + buyer lat/lon", "ru": "lst-* + lat/lon покупателя",
        "es": "lst-* + lat/lon del comprador", "fr": "lst-* + lat/lon acheteur",
        "zh": "lst-* + 买方 lat/lon",
    },
}


def _devices_cell(capability: str, ids: list[str], lang: str) -> str:
    summary = _DEVICE_SUMMARY.get(capability) or {}
    loc = (lang or "en").lower()[:2]
    if summary:
        return _safe(summary.get(loc) or summary.get("en") or "")
    shown = ids[:4]
    extra = len(ids) - len(shown)
    cell = ", ".join(_safe(x) for x in shown)
    if extra > 0:
        cell += f" +{extra}"
    return cell


def render_block(*, lang: str = "en", heading: str = "### Physical and map SKUs") -> str:
    c = _copy(lang)
    fallback = c["fallback"]
    lines = [heading, "", _safe(c["blurb"]), "", _safe(c["gaia"]), ""]
    lines.append(
        f"| {c['sku']} | {c['layer']} | {c['devices']} | {c['limit']} |"
    )
    lines.append("|---|---|---|---|")
    for row in catalog_rows():
        cap = row["capability"]
        layer = row["layer"]
        label = f"{layer} ({_layer_label(layer, lang)})" if layer else "—"
        lines.append(
            f"| {cap} | {_safe(label)} | {_devices_cell(cap, row['devices'], lang)} | "
            f"{_honest(cap, lang, fallback)} |"
        )

    lines.extend(["", _safe(c["meta"]), ""])
    lines.append(f"| {c['sku']} | {c['what']} |")
    lines.append("|---|---|")
    for sku, note in _GAIA_META:
        lines.append(f"| {sku} | {_safe(note)} |")

    lines.extend(["", _safe(c["atlas"]), ""])
    lines.append(f"| {c['sku']} | {c['price']} | {c['what']} |")
    lines.append("|---|---|---|")
    for spec in PRODUCT_CAPS:
        sku = str(spec.get("capability_id") or "")
        if not sku:
            continue
        price = spec.get("price_per_call_usd")
        price_s = f"{float(price):.2f}" if isinstance(price, (int, float)) else "—"
        desc = _safe(str(spec.get("description") or "").split(".")[0])
        note = _honest(sku, lang, desc)
        lines.append(f"| {sku} | {price_s} | {note} |")

    layer_bits = []
    for key in LAYER_META:
        layer_bits.append(f"{key}={_layer_label(key, lang)}")
    lines.extend(["", f"{c['layers']} ({len(LAYER_META)}): " + "; ".join(layer_bits), ""])
    return "\n".join(lines) + "\n"
