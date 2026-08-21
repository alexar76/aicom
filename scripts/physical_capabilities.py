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
    "atlas.fire.weather@v1": {
        "en": "FIRMS and/or EFFIS + nearby weather; two lists; not a forecast",
        "ru": "FIRMS и/или EFFIS + погода; два списка; не прогноз",
        "es": "FIRMS y/o EFFIS + clima cercano; dos listas; no un pronóstico",
        "fr": "FIRMS et/ou EFFIS + météo proche; deux listes; pas une prévision",
        "zh": "FIRMS 和/或 EFFIS + 附近天气；两个列表；不是预报",
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


def _devices_cell(ids: list[str]) -> str:
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
            f"| {cap} | {_safe(label)} | {_devices_cell(row['devices'])} | "
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
