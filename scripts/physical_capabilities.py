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
    ("gaia.place.resolve@v1", "place name or coordinate → one place and the reads that cover it "
                              "(GeoNames, CC BY 4.0) — free"),
    ("gaia.power.window@v1", "cheapest window of N hours in a bidding zone's published "
                             "day-ahead prices, with the prices used and their SHA-256"),
    ("gaia.actuator.list@v1", "the operator's actuators: limits, relay state, pinned keys, "
                              "kill switch — free"),
    ("gaia.actuate@v1", "switch a plug on for N s or off; $0.05, paid only for the effect "
                        "its own meter measures (pay-on-verified)"),
)

# Honesty notes that the catalog cannot infer (licence / not-X). A SKU without a
# row still appears — the overlay is optional, the roster is not.
_HONEST: dict[str, dict[str, str]] = {
    "gaia.ev.charging.read@v1": {
        "en": "NDW DOT-NL public charging connector availability and rated power, with bbox and page scope",
        "ru": "доступность и мощность разъёмов NDW DOT-NL, с областью выборки и пагинацией",
        "es": "disponibilidad y potencia de conectores NDW DOT-NL, con área y paginación",
        "fr": "disponibilité et puissance des connecteurs NDW DOT-NL, avec zone et pagination",
        "zh": "NDW DOT-NL 充电接口可用数量与额定功率，支持区域查询及分页",
    },
    "gaia.fire.perimeters.read@v1": {
        "en": "BC Wildfire active incidents and separately dated official fire outlines",
        "ru": "активные пожары BC Wildfire и опубликованные контуры с отдельной датой наблюдения",
        "es": "incendios activos de BC Wildfire y perímetros oficiales con fecha propia",
        "fr": "feux actifs de BC Wildfire et périmètres officiels datés séparément",
        "zh": "BC Wildfire 活跃火情与独立标注观测日期的官方边界",
    },
    "gaia.pollen.read@v1": {
        "en": "hourly measured airborne pollen for seven taxa at MeteoSwiss automatic stations",
        "ru": "почасовые замеры семи типов пыльцы на автоматических станциях MeteoSwiss",
        "es": "mediciones horarias de siete tipos de polen en estaciones automáticas de MeteoSwiss",
        "fr": "mesures horaires de sept types de pollen par les stations automatiques de MétéoSuisse",
        "zh": "MeteoSwiss 自动站每小时实测七类空气花粉浓度",
    },
    "gaia.storm.reports.read@v1": {
        "en": "NOAA SPC preliminary local tornado, hail and wind reports in a rolling 24-hour window",
        "ru": "предварительные локальные сообщения NOAA SPC о торнадо, граде и шквалах за последние 24 часа",
        "es": "informes preliminares NOAA SPC de tornados, granizo y viento en las últimas 24 horas",
        "fr": "signalements locaux provisoires NOAA SPC de tornades, grêle et vents sur 24 heures glissantes",
        "zh": "NOAA SPC 最近 24 小时的龙卷风、冰雹和强风初步报告",
    },
    "gaia.volcanic.ash.read@v1": {
        "en": "NOAA Washington VAAC ash contours with altitude and separate observation and forecast validity",
        "ru": "контуры пепла NOAA Washington VAAC с высотой и отдельными сроками наблюдений и прогнозов",
        "es": "contornos de ceniza NOAA Washington VAAC con altitud y vigencia de observación y pronóstico",
        "fr": "contours de cendres NOAA Washington VAAC avec altitude et validité des observations et prévisions",
        "zh": "NOAA Washington VAAC 火山灰轮廓，含高度及观测与预报时效",
    },
    "gaia.fire.hotspots.read@v1": {
        "en": "DEA satellite thermal detections in Australia with a three-hour window, bbox and completeness",
        "ru": "спутниковые тепловые детекции DEA в Австралии за три часа с областью и признаком полноты",
        "es": "detecciones térmicas satelitales DEA en Australia durante tres horas, con área e indicador de completitud",
        "fr": "détections thermiques satellitaires DEA en Australie sur trois heures, avec zone et indicateur de complétude",
        "zh": "DEA 澳大利亚三小时卫星热异常，含查询区域与完整性标记",
    },
    "gaia.power.outages.read@v1": {
        "en": "UK Power Networks current incidents at approximate area coordinates, with operator status and restoration estimates",
        "ru": "текущие отключения UK Power Networks с примерными координатами района, статусом и оценкой времени восстановления",
        "es": "cortes vigentes de UK Power Networks con coordenadas aproximadas, estado y hora estimada de reposición",
        "fr": "coupures en cours de UK Power Networks avec localisation approximative, état et heure estimée de rétablissement",
        "zh": "英国 UK Power Networks 当前停电事件，提供近似区域坐标、状态和预计恢复时间",
    },
    "gaia.bridge.clearance.read@v1": {
        "en": "NOAA PORTS preliminary measured distance between a bridge reference point and the water at three US sites",
        "ru": "предварительные замеры NOAA PORTS от контрольной точки моста до воды на трёх объектах США",
        "es": "medición preliminar NOAA PORTS de la distancia del punto de referencia del puente al agua en tres sitios de EE. UU.",
        "fr": "distance mesurée provisoire entre le repère du pont et l’eau sur trois sites américains NOAA PORTS",
        "zh": "NOAA PORTS 在美国三处桥梁参考点测得的水面净空初步观测",
    },
    "gaia.ocean.drifters.read@v1": {
        "en": "NOAA AOML OSMC latest observed positions and sea-surface temperatures for drifting buoys within six hours",
        "ru": "позиции и температура поверхности моря по замерам дрейфующих буёв NOAA AOML OSMC за последние шесть часов",
        "es": "posiciones observadas y temperatura superficial del mar de boyas a la deriva NOAA AOML OSMC de las últimas seis horas",
        "fr": "positions observées et température de surface des bouées dérivantes NOAA AOML OSMC des six dernières heures",
        "zh": "NOAA AOML OSMC 漂流浮标最近六小时的实测位置和海表温度",
    },
    "gaia.bikeshare.read@v1": {
        "en": "Bike Share Toronto GBFS station reports with bikes, free docks and rental and return status, up to five minutes old",
        "ru": "данные станций Bike Share Toronto GBFS о велосипедах, свободных доках и доступности аренды и возврата за последние пять минут",
        "es": "datos GBFS de estaciones Bike Share Toronto con bicicletas, anclajes libres y estado de alquiler y devolución de hasta cinco minutos",
        "fr": "état GBFS des stations Bike Share Toronto, vélos, bornes libres, location et retour, datant de cinq minutes au plus",
        "zh": "Bike Share Toronto GBFS 最近五分钟的车辆、空泊位和租还状态",
    },
    "gaia.power.price.read@v1": {
        "en": "wholesale day-ahead price per bidding zone (SMARD, CC BY 4.0; 15 zones); not a retail tariff",
        "ru": "оптовая цена на сутки вперёд по зоне торгов (SMARD, CC BY 4.0; 15 зон); не розничный тариф",
        "es": "precio mayorista del día siguiente por zona de oferta (SMARD, CC BY 4.0; 15 zonas); no es una tarifa minorista",
        "fr": "prix de gros du lendemain par zone de dépôt (SMARD, CC BY 4.0 ; 15 zones) ; pas un tarif de détail",
        "zh": "按竞价区的日前批发电价（SMARD，CC BY 4.0；15 个区）；不是零售电价",
    },
    "gaia.imagery.read@v1": {
        "en": "any land coordinate; one 10–20 m pixel of the latest cloud-free Sentinel-2 L2A scene; read indices with the scene class; contains modified Copernicus Sentinel data",
        "ru": "любая координата суши; один пиксель 10–20 м последнего безоблачного снимка Sentinel-2 L2A; индексы читать вместе с классом поверхности; содержит изменённые данные Copernicus Sentinel",
        "es": "cualquier coordenada terrestre; un píxel de 10–20 m de la última escena Sentinel-2 L2A sin nubes; leer los índices con la clase de escena; contiene datos Copernicus Sentinel modificados",
        "fr": "toute coordonnée terrestre ; un pixel de 10–20 m de la dernière scène Sentinel-2 L2A sans nuages ; lire les indices avec la classe de scène ; contient des données Copernicus Sentinel modifiées",
        "zh": "任意陆地坐标；最新无云 Sentinel-2 L2A 影像的一个 10–20 米像元；指数须结合场景分类解读；含经修改的 Copernicus Sentinel 数据",
    },
    "gaia.smoke.read@v1": {
        "en": "full signed polygon rings + holes, not just centroids; qualitative density, not PM2.5",
        "ru": "подписанные контуры полигонов с отверстиями, не только центроиды; качественная плотность, не PM2.5",
        "es": "anillos de polígono firmados con huecos, no solo centroides; densidad cualitativa, no PM2.5",
        "fr": "anneaux de polygones signés avec trous, pas seulement les centroïdes ; densité qualitative, pas PM2.5",
        "zh": "完整签名多边形环及内环，不只是质心；定性浓度等级，不是 PM2.5",
    },
    "gaia.smoke.forecast.read@v1": {
        "en": "ECCC FireWork next-hour modelled PM2.5 within a smoke plume at three pilot cells, with run and valid times",
        "ru": "прогноз PM2.5 на ближайший час в дымовом шлейфе ECCC FireWork для трёх ячеек, со временем расчёта и действия",
        "es": "pronóstico ECCC FireWork de PM2.5 para la próxima hora dentro de una pluma de humo en tres celdas piloto, con horas de ejecución y validez",
        "fr": "prévision ECCC FireWork de PM2.5 pour la prochaine heure dans un panache de fumée sur trois mailles pilotes, avec heures de calcul et de validité",
        "zh": "ECCC FireWork 对三个试点网格烟羽内下一小时 PM2.5 的预报，含起报和有效时间",
    },
    "gaia.radiation.ambient.read@v1": {
        "en": "German BfS hourly validated gamma dose rate in nSv/h at station coordinates, up to 2h old",
        "ru": "валидированные часовые измерения мощности дозы гамма-излучения BfS в нЗв/ч по координатам станций, давность до 2 ч",
        "es": "tasa de dosis gamma horaria validada del BfS alemán en nSv/h en las estaciones, con hasta 2 h de antigüedad",
        "fr": "débit de dose gamma horaire validé du BfS allemand en nSv/h aux stations, datant de 2 h au plus",
        "zh": "德国 BfS 测站经验证的每小时伽马剂量率，单位 nSv/h，观测距今不超过两小时",
    },
    "gaia.hf.absorption.read@v1": {
        "en": "NOAA SWPC D-RAP modeled HF frequency threshold at 1 dB, 8,100 native 2° × 4° cells and a map overview of 900 cell maxima",
        "ru": "модельный порог частоты КВ NOAA SWPC D-RAP при 1 дБ, 8 100 исходных ячеек 2° × 4° и 900 максимумов для обзора карты",
        "es": "umbral de frecuencia HF de NOAA SWPC D-RAP a 1 dB, 8 100 celdas originales de 2° × 4° y 900 máximos en la vista general",
        "fr": "seuil de fréquence HF NOAA SWPC D-RAP à 1 dB, 8 100 mailles d’origine de 2° × 4° et 900 maxima sur la vue d’ensemble",
        "zh": "NOAA SWPC D-RAP 模拟短波吸收 1 dB 对应频率，8 100 个原始 2° × 4° 网格及地图总览的 900 个网格最大值",
    },
    "gaia.ocean.observations.read@v1": {
        "en": "SMHI Swedish coastal measurements of currents, salinity and oxygen with station depth and observation time, up to 3h old",
        "ru": "прибрежные замеры течений, солёности и кислорода SMHI в Швеции с глубиной и временем измерения, давность до 3 ч",
        "es": "mediciones costeras suecas del SMHI de corrientes, salinidad y oxígeno, con profundidad y hora de observación y hasta 3 h de antigüedad",
        "fr": "mesures côtières suédoises SMHI de courant, salinité et oxygène avec profondeur et heure d’observation, datant de 3 h au plus",
        "zh": "SMHI 瑞典沿岸海流、盐度和溶解氧实测数据，含测量深度和时间，观测距今不超过三小时",
    },
    "gaia.river.read@v1": {
        "en": "fixed river gauges include preliminary paired stage and discharge observations from Czech ČHMÚ and Slovenia ARSO",
        "ru": "стационарные речные посты включают предварительные синхронные замеры уровня и расхода ČHMÚ в Чехии и ARSO в Словении",
        "es": "estaciones fluviales fijas con medidas preliminares simultáneas de nivel y caudal de ČHMÚ en Chequia y ARSO en Eslovenia",
        "fr": "stations fluviales fixes avec mesures préliminaires simultanées de niveau et de débit de ČHMÚ en Tchéquie et d’ARSO en Slovénie",
        "zh": "固定河流测站含捷克 ČHMÚ 和斯洛文尼亚 ARSO 的同期初步水位和流量观测",
    },
    "gaia.tide.read@v1": {
        "en": "fixed coastal gauges include GeoNet height above local pressure sensors and Norwegian Kartverket levels in NN2000",
        "ru": "среди береговых постов GeoNet с высотой над местными датчиками давления и Kartverket с уровнем в системе NN2000",
        "es": "mareógrafos fijos con alturas de GeoNet sobre sensores locales y niveles de Kartverket en NN2000",
        "fr": "marégraphes fixes avec hauteurs GeoNet au-dessus des capteurs locaux et niveaux norvégiens Kartverket en NN2000",
        "zh": "固定沿岸站含 GeoNet 相对当地压力传感器的水位和挪威 Kartverket 的 NN2000 水位",
    },
    "gaia.water_quality.read@v1": {
        "en": "fresh (48h default) paginated latest-continuous observations joined to the official USGS monitoring-locations registry; filters and per-series approval/qualifiers; one station = one coordinate",
        "ru": "свежие (48 ч по умолчанию) постраничные latest-continuous наблюдения с join к USGS monitoring-locations; фильтры и approval/qualifiers по рядам; одна станция = одна координата",
        "es": "observaciones latest-continuous frescas (48 h por defecto), paginadas y unidas a USGS monitoring-locations; filtros y approval/qualifiers; una estación = una coordenada",
        "fr": "observations latest-continuous fraîches (48 h par défaut), paginées et jointes à USGS monitoring-locations ; filtres et approval/qualifiers ; une station = une coordonnée",
        "zh": "新鲜（默认 48 小时）分页 latest-continuous 观测联接官方 USGS monitoring-locations；筛选及逐序列 approval/qualifiers；一站一坐标",
    },
    "gaia.groundwater.read@v1": {
        "en": "USGS depth below ground, Hub’Eau depth from measuring reference and NGF elevation, up to 24h old",
        "ru": "USGS: глубина от земли, Hub’Eau: глубина от измерительной отметки и высота NGF, давность до 24 ч",
        "es": "USGS: profundidad bajo el terreno, Hub’Eau: profundidad desde la referencia y cota NGF, hasta 24 h",
        "fr": "USGS : profondeur sous le sol, Hub’Eau : profondeur depuis le repère et altitude NGF, 24 h maximum",
        "zh": "USGS 为地表以下水深，Hub’Eau 为测量基准以下水深与 NGF 高程，观测时间不超过 24 小时",
    },
    "gaia.river.forecast.read@v1": {
        "en": "NOAA NWPS forecast peak among available samples in the next 72h, local gauge datum, issue and valid times",
        "ru": "пик среди доступных точек прогноза NOAA NWPS на 72 ч, местный нуль поста, время выпуска и пика",
        "es": "máximo entre las muestras previstas por NOAA NWPS en 72 h, datum local, horas de emisión y máximo",
        "fr": "pic parmi les points prévus par NOAA NWPS dans les 72 h, repère local, heures d’émission et du pic",
        "zh": "NOAA NWPS 未来 72 小时可用预报点的峰值，采用测站基准，提供发布时间和峰值时间",
    },
    "gaia.road.events.read@v1": {
        "en": "Fintraffic, NDW and City of Toronto road notices within published validity, with source geometry",
        "ru": "дорожные сообщения Fintraffic, NDW и Торонто в пределах опубликованных сроков, с исходной геометрией",
        "es": "avisos de Fintraffic, NDW y Toronto dentro de su periodo de validez, con geometría de origen",
        "fr": "avis routiers de Fintraffic, NDW et Toronto dans leur période de validité, avec géométrie source",
        "zh": "Fintraffic、NDW 与多伦多公布的有效道路通告，保留源几何形状",
    },
    "gaia.marine.read@v1": {
        "en": "includes wave observations from FMI Baltic, Irish Marine Institute and Australian AODN/IMOS buoys",
        "ru": "включает замеры волн с балтийских буёв FMI, ирландских буёв Marine Institute и австралийских AODN/IMOS",
        "es": "incluye observaciones del oleaje de boyas bálticas FMI, irlandesas Marine Institute y australianas AODN/IMOS",
        "fr": "inclut les observations de vagues des bouées baltiques FMI, irlandaises Marine Institute et australiennes AODN/IMOS",
        "zh": "包括 FMI 波罗的海、爱尔兰 Marine Institute 和澳大利亚 AODN/IMOS 浮标的海浪实测",
    },
    "gaia.aviation.hazards.read@v1": {
        "en": "NOAA CONUS G-AIRMET forecast geometry, issue and valid times",
        "ru": "контуры прогноза NOAA G-AIRMET для континентальных США, время выпуска и действия",
        "es": "geometría de pronóstico G-AIRMET de NOAA para Estados Unidos continental, emisión y validez",
        "fr": "géométrie des prévisions G-AIRMET NOAA pour les États-Unis continentaux, émission et validité",
        "zh": "美国本土 NOAA G-AIRMET 预报几何形状、发布时间和有效时间",
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
        "en": "exact SNODAS cell at any CONUS coordinate, or fixed SNOTEL station by device_id with paired measured depth and water equivalent",
        "ru": "точная ячейка SNODAS по координатам в CONUS или парные замеры глубины и водного эквивалента на посту SNOTEL по device_id",
        "es": "celda SNODAS exacta en CONUS o estación SNOTEL fija por device_id con profundidad y equivalente en agua medidos",
        "fr": "cellule SNODAS exacte en CONUS ou station SNOTEL fixe par device_id avec mesures appariées de profondeur et d’équivalent en eau",
        "zh": "美国本土任意坐标的精确 SNODAS 网格，或按 device_id 选择 SNOTEL 固定站的成对实测雪深与雪水当量",
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
        "en": "regional alerts, observed flood products, and USGS RT-FI provisional gage threshold exceedances",
        "ru": "региональные предупреждения, наблюдения затопления и предварительные превышения порогов USGS RT-FI",
        "es": "alertas regionales, inundación observada y superaciones provisionales de umbrales USGS RT-FI",
        "fr": "alertes régionales, inondation observée et dépassements provisoires de seuil USGS RT-FI",
        "zh": "区域预警、洪水观测和 USGS RT-FI 临时水位超阈值数据",
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
        "en": "USGS elevated volcanoes and GeoNet New Zealand alert levels with timestamped camera snapshots",
        "ru": "повышенные статусы USGS и уровни GeoNet в Новой Зеландии со временем съёмки кадров",
        "es": "volcanes en alerta de USGS y niveles de GeoNet en Nueva Zelanda con imágenes fechadas",
        "fr": "volcans en alerte USGS et niveaux GeoNet de Nouvelle-Zélande avec images horodatées",
        "zh": "USGS 火山警戒状态以及新西兰 GeoNet 火山警戒级别和带时间戳的相机快照",
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
    "gaia.aviation.read@v1": {
        "en": "NOAA AWC METAR (U.S. PD); in-situ ASOS pin, not a TAF",
        "ru": "NOAA AWC METAR (U.S. PD); in-situ ASOS, не TAF",
        "es": "METAR NOAA AWC (U.S. PD); pin ASOS in situ, no un TAF",
        "fr": "METAR NOAA AWC (U.S. PD); pin ASOS in situ, pas un TAF",
        "zh": "NOAA AWC METAR（美国公有领域）；现场 ASOS，不是 TAF",
    },
    "gaia.road.read@v1": {
        "en": "Fintraffic Digitraffic road weather CC BY 4.0; Finnish roads only",
        "ru": "Fintraffic Digitraffic дорожная погода CC BY 4.0; только Финляндия",
        "es": "clima vial Fintraffic Digitraffic CC BY 4.0; solo carreteras finlandesas",
        "fr": "météo routière Fintraffic Digitraffic CC BY 4.0 ; routes finlandaises seulement",
        "zh": "Fintraffic Digitraffic 道路天气 CC BY 4.0；仅芬兰公路",
    },
    "gaia.rail.read@v1": {
        "en": "Finnish train locations from Fintraffic Digitraffic (CC BY 4.0) and Norwegian Vy positions from Entur (NLOD)",
        "ru": "финские поезда Fintraffic Digitraffic (CC BY 4.0) и норвежские поезда Vy из Entur (NLOD)",
        "es": "posiciones de trenes finlandeses de Fintraffic Digitraffic (CC BY 4.0) y de trenes noruegos de Vy de Entur (NLOD)",
        "fr": "positions des trains finlandais de Fintraffic Digitraffic (CC BY 4.0) et des trains norvégiens Vy d’Entur (NLOD)",
        "zh": "Fintraffic Digitraffic 芬兰列车位置（CC BY 4.0）与 Entur 挪威 Vy 列车位置（NLOD）",
    },
    "gaia.drought.read@v1": {
        "en": "U.S. Drought Monitor weekly state stats; attribute NDMC/USDA/NOAA/NASA",
        "ru": "U.S. Drought Monitor, недельная статистика штатов; атрибуция NDMC/USDA/NOAA/NASA",
        "es": "U.S. Drought Monitor, stats semanales por estado; atribuir NDMC/USDA/NOAA/NASA",
        "fr": "U.S. Drought Monitor, stats hebdo par État ; créditer NDMC/USDA/NOAA/NASA",
        "zh": "美国干旱监测周报州统计；注明 NDMC/USDA/NOAA/NASA",
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
    "atlas.mesh.sample@v1": {
        "en": "Halton sample of a licensed in-situ mesh; not ECVRF; not Open-Meteo",
        "ru": "Halton-выборка licensed in-situ mesh; не ECVRF; не Open-Meteo",
        "es": "muestra Halton de malla in-situ licenciada; no ECVRF; no Open-Meteo",
        "fr": "échantillon Halton d’un maillage in-situ licencié ; pas ECVRF ; pas Open-Meteo",
        "zh": "对已授权 in-situ 网格做 Halton 抽样；不是 ECVRF；不是 Open-Meteo",
    },
    "atlas.field.consensus@v1": {
        "en": "robust consensus of LIVE in-situ readings; one broken station cannot move the number; not a forecast",
        "ru": "робастный консенсус LIVE in-situ; одна сломанная станция не двигает число; не прогноз",
        "es": "consenso robusto de lecturas in-situ LIVE; una estación rota no mueve el número; no un pronóstico",
        "fr": "consensus robuste de lectures in-situ LIVE ; une station cassée ne déplace pas le chiffre ; pas une prévision",
        "zh": "LIVE in-situ 读数的稳健共识；单站故障带不动结果；不是预报",
    },
    "atlas.field.posterior@v1": {
        "en": "spatial GP posterior of the current LIVE snapshot; interpolates now, not a forecast",
        "ru": "пространственный GP-постер текущего LIVE-снимка; интерполяция, не прогноз",
        "es": "posterior GP espacial del snapshot LIVE; interpola ahora, no un pronóstico",
        "fr": "postérieur GP spatial du snapshot LIVE ; interpolation, pas une prévision",
        "zh": "当前 LIVE 快照的空间 GP 后验；是插值，不是预报",
    },
    "atlas.field.shape@v1": {
        "en": "H0 persistence of LIVE in-situ pins; not Betti-1; not an AQI",
        "ru": "H0-персистентность LIVE in-situ пинов; не Betti-1; не AQI",
        "es": "persistencia H0 de pines in-situ LIVE; no Betti-1; no un AQI",
        "fr": "persistance H0 des pins in-situ LIVE ; pas Betti-1 ; pas un AQI",
        "zh": "LIVE in-situ 针脚的 H0 持续同调；不是 Betti-1；不是 AQI",
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
    "gaia.imagery.read@v1": {
        "en": "s2-l2a-01 + buyer lat/lon (5 showcase pins)", "ru": "s2-l2a-01 + lat/lon покупателя (5 витринных точек)",
        "es": "s2-l2a-01 + lat/lon del comprador (5 puntos de muestra)", "fr": "s2-l2a-01 + lat/lon acheteur (5 points vitrine)",
        "zh": "s2-l2a-01 + 买方 lat/lon（5 个示例点）",
    },
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
        "en": "snow-* + buyer CONUS lat/lon; snotel-335, snotel-415 by ID",
        "ru": "snow-* + lat/lon покупателя в CONUS; snotel-335, snotel-415 по ID",
        "es": "snow-* + lat/lon del comprador en CONUS; snotel-335, snotel-415 por ID",
        "fr": "snow-* + lat/lon acheteur en CONUS ; snotel-335, snotel-415 par ID",
        "zh": "snow-* + CONUS 内买方 lat/lon；按 ID 选择 snotel-335、snotel-415",
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
