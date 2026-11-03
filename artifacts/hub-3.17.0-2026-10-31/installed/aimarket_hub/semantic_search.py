"""Fast multilingual intent search for a small federated capability catalogue.

The hub must be able to answer natural-language discovery requests without making an
LLM call (or downloading a model) in the request path.  For the current catalogue that
means a hybrid sparse representation works better operationally than a neural service:

* exact, field-weighted lexical matching keeps capability IDs deterministic;
* all shipped EN/RU/ES/FR/ZH descriptions become one searchable document;
* multilingual intent aliases project both query and document into a compact concept
  vector (weather, wildfire, GNSS interference, randomness, VDF, ...);
* typo-tolerant token similarity provides a small recall fallback;
* trust, success, latency and price may break close relevance ties, but can never make an
  irrelevant capability outrank a relevant one.

This is deliberately dependency-free.  The current small catalogue is ranked in memory
in a few milliseconds, there is no private query sent to a third party, and every score
can be explained to an agent or rendered by the terminal.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from aimarket_hub.models import Capability


_TOKEN_RE = re.compile(r"[a-z0-9]+|[а-яё]+|[\u4e00-\u9fff]+", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def normalize_text(value: object) -> str:
    """Case/diacritic/punctuation normalization shared by aliases and live queries."""
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[_/.:@+→—–-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_STOPWORDS = frozenset(
    normalize_text(
        """
        a an and the of for to in on with my me our your is are be get how what which
        that this it its from by as at or i we need want find show give use using looking
        protect help please current now
        и или но в во на с со для к ко по из у о об от до за что как какой какая какие
        мне нам мой моя мои наш наша нужно хочу найти покажи дай использовать помощью
        текущий сейчас рядом
        el la los las un una unos unas y o de del para por en con mi mis quiero necesito
        buscar mostrar dame usar actual ahora
        le la les un une des et ou de du pour par dans avec mon mes je veux besoin trouver
        montrer donne utiliser actuel maintenant
        的 了 和 与 或 在 为 给 用 我 我们 想要 需要 查找 显示 当前 现在
        """
    ).split()
)


# Aliases are intent phrases, not translations of UI labels.  Multi-word phrases are
# important: "fair draw" is a randomness intent, while "fair" alone is not.
_CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "randomness": (
        "random", "randomness", "random number", "fair draw", "lottery", "raffle",
        "vrf", "beacon", "commit reveal", "chance", "lotto",
        "случайность", "случайные числа", "честный розыгрыш", "лотерея", "жребий",
        "aleatorio", "aleatoriedad", "numeros aleatorios", "loteria", "sorteo", "azar",
        "aleatoire", "alea", "nombres aleatoires", "loterie", "tirage", "hasard",
        "随机", "随机数", "抽签", "彩票", "公平抽取",
    ),
    "verification": (
        "verify", "verification", "verifiable", "proof", "validate", "trustless",
        "signed", "signature", "receipt", "certificate", "audit trail",
        "проверить", "проверка", "доказательство", "проверяемый", "подпись", "квитанция",
        "verificar", "verificacion", "prueba", "firma", "recibo", "certificado",
        "verifier", "verification", "preuve", "signature", "recu", "certificat",
        "验证", "校验", "证明", "签名", "收据", "证书",
    ),
    "delay": (
        "delay", "vdf", "sequential time", "time lock", "timelock", "elapsed time",
        "wait proof", "задержка", "последовательное время", "таймлок", "блокировка времени",
        "прошло время", "retardo", "tiempo secuencial", "bloqueo temporal",
        "delai", "temps sequentiel", "verrou temporel", "延迟", "顺序时间", "时间锁",
    ),
    "weather": (
        "weather", "forecast", "temperature", "humidity", "wind", "meteorology", "storm",
        "погода", "прогноз", "температура", "влажность", "ветер", "шторм",
        "clima", "pronostico", "temperatura", "humedad", "viento", "tormenta",
        "meteo", "prevision", "temperature", "humidite", "vent", "tempete",
        "天气", "预报", "温度", "湿度", "风", "风暴",
    ),
    # Its own concept, not a flavour of "weather". Folding these words into
    # weather made every weather SKU match them equally, so "ураган" ranked the
    # generic weather relay above the actual NHC cyclone feed. A US desk types
    # "hurricane" and a RU one "ураган" — neither ever types "cyclone".
    "cyclone": (
        "cyclone", "hurricane", "typhoon", "tropical storm", "tropical cyclone",
        "nhc", "cphc", "storm track", "landfall",
        "циклон", "ураган", "тайфун", "тропический шторм", "тропический циклон",
        "ciclon", "huracan", "tifon", "tormenta tropical", "ciclon tropical",
        "ouragan", "typhon", "tempete tropicale", "cyclone tropical",
        "气旋", "飓风", "台风", "热带风暴", "热带气旋",
    ),
    "wildfire": (
        "wildfire", "forest fire", "fire", "hotspot", "burning", "smoke", "firms",
        "effis", "copernicus",
        "лесной пожар", "пожар", "очаг", "возгорание", "горит", "дым",
        "incendio forestal", "incendio", "foco", "humo",
        "feu de foret", "incendie", "point chaud", "fumee",
        "森林火灾", "火灾", "热点", "烟雾",
    ),
    "geospatial": (
        "nearby", "nearest", "closest", "location", "geographic", "geospatial", "bbox",
        "coordinate", "latitude", "longitude", "map", "radius", "distance", "facility",
        "site", "area", "zone", "object",
        "ближайший", "местоположение", "география", "координаты", "карта", "радиус",
        "расстояние", "рядом", "объект", "площадка", "территория", "зона",
        "cercano", "mas cercano", "ubicacion", "geografico", "coordenadas", "mapa",
        "radio", "distancia", "instalacion", "zona",
        "proche", "plus proche", "emplacement", "geographique", "coordonnees", "carte",
        "rayon", "distance", "installation", "zone",
        "附近", "最近", "位置", "地理", "坐标", "地图", "半径", "距离", "设施", "区域",
    ),
    "monitoring": (
        "monitor", "monitoring", "watch", "watchbox", "alert", "warning", "notify",
        "notification", "subscribe", "track", "detect", "anomaly",
        "мониторинг", "наблюдение", "контроль", "оповещение", "тревога", "уведомление",
        "подписка", "отслеживать", "обнаружить",
        "monitorear", "vigilancia", "alerta", "aviso", "notificar", "suscribir", "detectar",
        "surveiller", "suivi", "alerte", "avertissement", "notifier", "abonner", "detecter",
        "监控", "观察", "警报", "预警", "通知", "订阅", "跟踪", "检测",
    ),
    "navigation": (
        "gnss", "gps", "navigation", "jamming", "jammed", "spoofing", "interference",
        "positioning", "satellite signal", "signal disruption",
        "гнсс", "навигация", "глушение", "спуфинг", "помеха", "позиционирование",
        "спутниковый сигнал", "interferencia", "navegacion", "inhibicion", "suplantacion gps",
        "positionnement", "brouillage", "interference gps", "usurpation gps", "导航", "干扰",
        "欺骗", "定位", "卫星信号",
    ),
    "maritime": (
        "ship", "vessel", "maritime", "marine", "port", "sea", "ocean", "ais", "tide",
        "river", "flood", "buoy", "waves", "water level",
        "судно", "корабль", "морской", "порт", "море", "океан", "аис", "прилив", "река",
        "буй", "волны", "уровень воды",
        "barco", "buque", "maritimo", "puerto", "mar", "oceano", "marea", "rio", "olas",
        "navire", "bateau", "maritime", "port", "mer", "ocean", "maree", "riviere", "vagues",
        "船", "船舶", "海事", "港口", "海洋", "潮汐", "河流", "浮标", "波浪", "水位",
    ),
    "aviation": (
        "aircraft", "airplane", "plane", "flight", "aviation", "ads b", "adsb", "transponder",
        "air traffic", "самолет", "борт", "полет", "авиация", "адс б", "транспондер",
        "воздушный трафик", "avion", "vuelo", "aviacion", "trafico aereo",
        "aeronef", "vol", "aviation", "trafic aerien", "飞机", "航班", "航空", "空中交通",
    ),
    "air_quality": (
        "air quality", "pollution", "pm2 5", "pm10", "co2", "voc", "emissions",
        "качество воздуха", "загрязнение", "выбросы", "calidad del aire", "contaminacion",
        "qualite de l air", "pollution", "空气质量", "污染", "排放",
    ),
    "energy": (
        "energy", "electricity", "power", "meter", "grid", "carbon intensity", "voltage",
        "энергия", "электричество", "мощность", "счетчик", "сеть", "углеродоемкость", "напряжение",
        "energia", "electricidad", "potencia", "contador", "red electrica", "intensidad de carbono",
        "energie", "electricite", "puissance", "compteur", "reseau", "intensite carbone",
        "能源", "电力", "功率", "电表", "电网", "碳强度", "电压",
    ),
    "seismic": (
        "earthquake", "quake", "seismic", "tremor", "magnitude", "usgs",
        "землетрясение", "сейсмический", "толчок", "магнитуда",
        "terremoto", "sismico", "temblor", "magnitud", "seisme", "tremblement", "magnitude",
        "地震", "震动", "震级",
    ),
    "radiation": (
        "radiation", "radioactive", "dosimeter", "cpm", "safecast",
        "радиация", "радиоактивность", "дозиметр", "radiacion", "radiactivo", "dosimetro",
        "rayonnement", "radioactif", "dosimetre", "辐射", "放射性", "剂量计",
    ),
    "trust": (
        "trust", "reputation", "pagerank", "eigentrust", "score", "rank", "credibility",
        "доверие", "репутация", "рейтинг", "надёжность", "confianza", "reputacion", "rango",
        "confiance", "reputation", "classement", "信任", "信誉", "声誉", "排名",
    ),
    "consensus": (
        "consensus", "aggregate", "quorum", "multiple agents", "robust average",
        "консенсус", "агрегация", "кворум", "несколько агентов", "consenso", "agregado",
        "consensus", "agregat", "共识", "聚合", "法定人数",
    ),
    "routing": (
        "route", "routing", "path", "shortest path", "least time", "tour", "itinerary",
        "маршрут", "путь", "кратчайший путь", "быстрейший", "обход", "ruta", "camino",
        "ruta mas corta", "itineraire", "chemin", "plus court", "路线", "路径", "最短路径",
    ),
    "optimization": (
        "optimize", "optimization", "best solution", "minimum", "optimal", "suggest parameters",
        "оптимизация", "оптимальный", "минимум", "лучшее решение", "подобрать параметры",
        "optimizar", "optimizacion", "solucion optima", "optimiser", "optimisation", "solution optimale",
        "优化", "最优", "最佳方案", "最小值",
    ),
    "cascade_risk": (
        "cascade", "systemic risk", "contagion", "exposure", "failure propagation", "sandpile",
        "каскад", "системный риск", "заражение", "экспозиция", "цепочка отказов",
        "cascada", "riesgo sistemico", "contagio", "exposicion",
        "cascade", "risque systemique", "contagion", "exposition", "级联", "系统性风险", "传染", "风险暴露",
    ),
    "graph": (
        "graph", "network", "node", "edge", "connectivity", "topology", "laplacian",
        "граф", "сеть", "узел", "ребро", "связность", "топология", "лапласиан",
        "grafo", "red", "nodo", "arista", "conectividad", "topologia",
        "graphe", "reseau", "noeud", "arete", "connectivite", "topologie",
        "图", "网络", "节点", "边", "连通性", "拓扑",
    ),
    "compute_cost": (
        "thermodynamic", "computation cost", "compute cost", "erasure", "landauer", "energy cost",
        "термодинамика", "стоимость вычисления", "стирание", "энергозатраты",
        "termodinamico", "coste computacional", "borrado", "thermodynamique", "cout du calcul", "effacement",
        "热力学", "计算成本", "擦除", "能耗",
    ),
    "sampling": (
        "sample", "sampling", "point sequence", "low discrepancy", "blue noise", "halton",
        "выборка", "последовательность точек", "низкое расхождение", "синий шум",
        "muestreo", "secuencia de puntos", "baja discrepancia", "ruido azul",
        "echantillonnage", "suite de points", "faible discrepance", "bruit bleu",
        "采样", "点序列", "低差异", "蓝噪声",
    ),
    "geometry": (
        "geometry", "point cloud", "homology", "betti", "persistence diagram", "distance",
        "projection", "manifold", "stiefel",
        "геометрия", "облако точек", "гомология", "диаграмма персистентности", "проекция",
        "geometria", "nube de puntos", "homologia", "diagrama de persistencia", "proyeccion",
        "geometrie", "nuage de points", "homologie", "diagramme de persistance", "projection",
        "几何", "点云", "同调", "持久性图", "投影", "流形",
    ),
    "transport": (
        "optimal transport", "source distribution", "sink distribution", "earth mover",
        "оптимальный транспорт", "распределение источника", "распределение стока",
        "transporte optimo", "distribucion fuente", "transport optimal", "distribution source",
        "最优传输", "源分布", "目标分布",
    ),
    "spectrum": (
        "spectrum", "spectral", "fourier", "frequency", "eigenvalue", "eigenvector", "oscillation",
        "спектр", "спектральный", "частота", "собственное значение", "колебание",
        "espectro", "frecuencia", "autovalor", "spectre", "frequence", "valeur propre",
        "频谱", "频率", "特征值", "振荡",
    ),
    "privacy_lock": (
        "seal", "unlock", "open time lock", "secret", "encrypted", "commit reveal",
        "запечатать", "разблокировать", "секрет", "зашифрованный", "раскрытие",
        "sellar", "desbloquear", "secreto", "cifrado", "revelar",
        "sceller", "deverrouiller", "secret", "chiffre", "reveler", "密封", "解锁", "秘密", "加密", "揭示",
    ),
    "physical_data": (
        "sensor", "device", "telemetry", "reading", "attested", "physical data", "fleet status",
        "датчик", "устройство", "телеметрия", "показание", "аттестованный", "физические данные",
        "sensor", "dispositivo", "telemetria", "lectura", "atestado",
        "capteur", "appareil", "telemetrie", "mesure", "atteste", "传感器", "设备", "遥测", "读数", "认证数据",
    ),
    "briefing": (
        "brief", "briefing", "situation report", "risk report", "cross layer", "summary",
        "сводка", "ситуационный отчет", "отчет о рисках", "кросс слой", "резюме",
        "informe", "resumen", "situacion", "rapport", "synthese", "situation", "简报", "态势报告", "摘要",
    ),
}

# Alias normalization is invariant. Doing it inside every query/document comparison made
# a catalogue search spend hundreds of milliseconds re-normalizing the same phrases.
_NORMALIZED_CONCEPT_ALIASES: dict[str, tuple[tuple[str, str], ...]] = {
    concept: tuple((alias, normalize_text(alias)) for alias in aliases)
    for concept, aliases in _CONCEPT_ALIASES.items()
}


# Product IDs are themselves strong semantics.  Hints guarantee that sparse upstream
# descriptions do not make a capability invisible, while the query still has to express
# the same concept before the hint can contribute.
_CAPABILITY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("platon.random", ("randomness", "verification")),
    ("platon.beacon", ("randomness", "verification")),
    ("platon.commit", ("randomness", "privacy_lock", "verification")),
    ("platon.reveal", ("randomness", "privacy_lock", "verification")),
    ("chronos.", ("delay", "verification")),
    ("lattice.", ("sampling",)),
    ("turing.", ("sampling",)),
    ("murmuration.", ("consensus",)),
    ("lumen.", ("trust", "graph")),
    ("colony.", ("optimization", "routing")),
    ("percola.threshold", ("graph", "cascade_risk")),
    ("percola.verify", ("graph", "cascade_risk", "verification")),
    ("fermat.route", ("routing", "optimization")),
    ("fermat.verify", ("routing", "optimization", "verification")),
    ("ablation.cascade", ("cascade_risk", "graph")),
    ("ablation.verify", ("cascade_risk", "graph", "verification")),
    ("landauer.", ("compute_cost", "verification")),
    ("sortes.", ("randomness", "verification")),
    ("gauss.field", ("optimization", "geometry")),
    ("gauss.suggest", ("optimization", "geometry")),
    ("gauss.verify", ("optimization", "geometry", "verification")),
    ("aestus.", ("delay", "privacy_lock", "verification")),
    ("betti.", ("geometry", "graph")),
    ("kantor.transport", ("transport", "optimization")),
    ("kantor.verify", ("transport", "optimization", "verification")),
    ("fourier.spectrum", ("spectrum", "graph")),
    ("fourier.verify", ("spectrum", "graph", "verification")),
    ("gaia.weather.", ("weather", "physical_data")),
    ("gaia.air.", ("air_quality", "physical_data")),
    ("gaia.energy.", ("energy", "physical_data")),
    ("gaia.grid.", ("energy", "physical_data")),
    ("gaia.quake.", ("seismic", "geospatial", "physical_data")),
    ("gaia.tide.", ("maritime", "geospatial", "physical_data")),
    ("gaia.river.", ("maritime", "geospatial", "physical_data")),
    ("gaia.marine.", ("maritime", "weather", "geospatial", "physical_data")),
    ("gaia.fire.", ("wildfire", "geospatial", "physical_data")),
    ("gaia.effis.", ("wildfire", "geospatial", "physical_data")),
    ("gaia.flood.", ("maritime", "geospatial", "monitoring", "physical_data")),
    ("gaia.lightning.", ("geospatial", "monitoring", "physical_data")),
    ("gaia.volcano.", ("geospatial", "monitoring", "physical_data")),
    ("gaia.events.", ("geospatial", "monitoring", "physical_data")),
    ("gaia.alerts.", ("monitoring", "geospatial", "physical_data")),
    ("gaia.radiation.", ("radiation", "geospatial", "physical_data")),
    ("gaia.jamming.", ("navigation", "geospatial", "monitoring", "physical_data")),
    # More specific prefix first — the table is matched in order, and
    # "gaia.adsb." alone would swallow the public relay before it is reached.
    ("gaia.adsb.public", ("aviation", "geospatial", "monitoring", "physical_data")),
    ("gaia.adsb.", ("aviation", "geospatial", "physical_data")),
    ("gaia.cyclone.", ("cyclone", "weather", "maritime", "geospatial", "monitoring", "physical_data")),
    ("gaia.ais.public", ("maritime", "geospatial", "physical_data")),
    ("gaia.ais.", ("maritime", "geospatial", "physical_data")),
    ("gaia.tsunami.", ("maritime", "geospatial", "monitoring", "physical_data")),
    ("atlas.watchbox.", ("monitoring", "geospatial", "physical_data")),
    ("atlas.fire.weather", ("wildfire", "weather", "geospatial", "briefing", "physical_data")),
    ("atlas.situation.brief", ("briefing", "monitoring", "geospatial", "maritime", "physical_data")),
    ("atlas.mesh.sample", ("geospatial", "physical_data", "monitoring")),
    ("atlas.field.consensus", ("geospatial", "physical_data", "briefing", "monitoring")),
    ("atlas.field.posterior", ("geospatial", "physical_data", "briefing")),
    ("atlas.field.shape", ("geospatial", "physical_data", "monitoring")),
    ("atlas.nearest.", ("geospatial", "physical_data")),
    ("gaia.window", ("physical_data",)),
    ("gaia.verify", ("physical_data", "verification")),
    ("gaia.fleet", ("physical_data", "monitoring")),
)

# Operational intent is usually more discriminative than the subject alone.  "Monitor a
# wildfire" should prefer a watchbox over a one-shot hotspot read; "verify elapsed time"
# should prefer a verifier/VDF over any capability that merely mentions time.
_CONCEPT_QUERY_BOOST: dict[str, float] = {
    "monitoring": 1.45,
    "navigation": 1.30,
    "verification": 1.18,
    "delay": 1.15,
    "briefing": 1.20,
}

_CAPABILITY_CONCEPT_EXCLUSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("betti.", ("geospatial",)),  # bottleneck distance is geometric, not physical proximity
    ("gaia.adsb.", ("graph",)),  # "edge" means an owned feeder, not a graph edge
    ("gaia.ais.", ("graph",)),
    # "Trustless verification" is not a reputation/trust-scoring product.
    ("chronos.", ("trust",)),
    ("percola.", ("trust",)),
    ("fermat.", ("trust",)),
    ("ablation.", ("trust",)),
    ("landauer.", ("trust",)),
    ("sortes.", ("trust",)),
    ("gauss.", ("trust",)),
    ("fourier.", ("trust",)),
)


@dataclass(frozen=True)
class IntentInterpretation:
    normalized: str
    tokens: tuple[str, ...]
    concepts: tuple[str, ...]
    aliases_by_concept: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class SearchMatch:
    capability: "Capability"
    score: float
    lexical_score: float
    semantic_score: float
    quality_score: float
    match_type: str
    matched_concepts: tuple[str, ...]
    matched_terms: tuple[str, ...]
    # The same answer whatever it is asked (answer_dependence.py): listed, but after every match whose
    # answer is computed from the request.
    input_independent: bool = False


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(t for t in _TOKEN_RE.findall(normalize_text(text)) if len(t) > 1 and t not in _STOPWORDS)


def _alias_found(normalized_text: str, needle: str) -> bool:
    if not needle:
        return False
    if _CJK_RE.search(needle):
        return needle in normalized_text
    if f" {needle} " in f" {normalized_text} ":
        return True
    # Lightweight morphology for the supported Latin/Cyrillic languages.  Capability
    # discovery cares about stable stems, not grammatical endings: RU "навигационных
    # помех" must match aliases "навигация" / "помеха", just as ES plural forms should.
    # Keep the stem long (word minus at most three letters, never under five) to avoid
    # broad prefix matches such as "air" -> "aircraft".
    if " " not in needle and len(needle) >= 5 and needle.isalpha():
        stem = needle[:max(5, len(needle) - 3)]
        return any(token.startswith(stem) for token in normalized_text.split())
    return False


def interpret_intent(query: str) -> IntentInterpretation:
    normalized = normalize_text(str(query or "")[:500])
    aliases: dict[str, tuple[str, ...]] = {}
    for concept, options in _NORMALIZED_CONCEPT_ALIASES.items():
        hits = tuple(alias for alias, needle in options if _alias_found(normalized, needle))
        if hits:
            aliases[concept] = hits
    return IntentInterpretation(
        normalized=normalized,
        tokens=_tokens(normalized),
        concepts=tuple(aliases),
        aliases_by_concept=aliases,
    )


def _description_paths() -> Iterable[Path]:
    configured = os.getenv("AIMARKET_CAP_DESCRIPTIONS_PATH", "").strip()
    if configured:
        yield Path(configured)
    yield Path.cwd() / "cap-descriptions-i18n.json"
    yield Path(__file__).resolve().parent.parent / "cap-descriptions-i18n.json"


@lru_cache(maxsize=1)
def load_localized_descriptions() -> dict[str, dict[str, str]]:
    """Load the static multilingual corpus; search still works if it is absent."""
    for path in _description_paths():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            descriptions = raw.get("descriptions", {})
            if isinstance(descriptions, dict):
                return {
                    str(cid): {str(lang): str(text) for lang, text in values.items()}
                    for cid, values in descriptions.items()
                    if isinstance(values, dict)
                }
        except (OSError, ValueError, TypeError):
            continue
    return {}


def _hinted_concepts(capability_id: str) -> set[str]:
    # normalize_text turns punctuation into spaces; compare a punctuation-normalized prefix.
    cid_words = normalize_text(capability_id)
    out: set[str] = set()
    for prefix, concepts in _CAPABILITY_HINTS:
        if cid_words.startswith(normalize_text(prefix)):
            out.update(concepts)
    return out


def _excluded_concepts(capability_id: str) -> set[str]:
    cid_words = normalize_text(capability_id)
    out: set[str] = set()
    for prefix, concepts in _CAPABILITY_CONCEPT_EXCLUSIONS:
        if cid_words.startswith(normalize_text(prefix)):
            out.update(concepts)
    return out


@dataclass(frozen=True)
class _Document:
    capability: "Capability"
    id_text: str
    name_text: str
    description_text: str
    id_tokens: frozenset[str]
    name_tokens: frozenset[str]
    description_tokens: frozenset[str]
    concepts: frozenset[str]


@lru_cache(maxsize=10_000)
def _document_features(
    cid: str,
    product_id: str,
    name: str,
    description: str,
) -> tuple[str, str, str, frozenset[str], frozenset[str], frozenset[str], frozenset[str]]:
    """Cache immutable search features across the terminal's repeated queries."""
    concepts: set[str] = set()
    # A single translated word can be polysemous (RU "прогноз" in a chaos model is not
    # necessarily weather; ZH "位置" may mean an abstract position, not geolocation).
    # Require two independent description aliases before inferring a document concept.
    # Localized product descriptions naturally satisfy this across languages, while one
    # accidental word does not. Product hints below remain authoritative.
    described = interpret_intent(description)
    for concept, aliases in described.aliases_by_concept.items():
        if len({normalize_text(alias) for alias in aliases}) >= 2:
            concepts.add(concept)
    concepts.update(_hinted_concepts(cid))
    concepts.difference_update(_excluded_concepts(cid))
    identity = f"{product_id} {name}"
    return (
        normalize_text(cid),
        normalize_text(identity),
        normalize_text(description),
        frozenset(_tokens(cid)),
        frozenset(_tokens(identity)),
        frozenset(_tokens(description)),
        frozenset(concepts),
    )


def _document_for(capability: "Capability", localized: dict[str, dict[str, str]]) -> _Document:
    cid = capability.capability_id
    local_texts = tuple(localized.get(cid, {}).values())
    description = " ".join((capability.description, *local_texts))
    features = _document_features(cid, capability.product_id, capability.name, description)
    return _Document(capability, *features)


def _idf(total: int, frequency: int) -> float:
    return math.log((total + 1.0) / (frequency + 1.0)) + 1.0


def _closest_token(query_token: str, candidates: frozenset[str]) -> float:
    if len(query_token) < 4:
        return 0.0
    best = 0.0
    for candidate in candidates:
        if abs(len(candidate) - len(query_token)) > max(3, len(query_token) // 2):
            continue
        ratio = SequenceMatcher(None, query_token, candidate).ratio()
        if ratio > best:
            best = ratio
    return best if best >= 0.78 else 0.0


def _quality_score(capability: "Capability") -> float:
    trust = min(1.0, max(0.0, float(capability.trust_score or 0.0)))
    success = min(1.0, max(0.0, float(capability.success_rate_30d or 0.0)))
    latency = max(0.0, float(capability.p50_latency_ms or 0.0))
    latency_score = 0.5 if latency <= 0 else 1.0 / (1.0 + latency / 1000.0)
    price = capability.routed_price_usd
    if price is None:
        price = capability.price_per_call_usd
    price_score = 1.0 / (1.0 + max(0.0, float(price or 0.0)) * 20.0)
    return 0.35 * trust + 0.25 * success + 0.20 * latency_score + 0.20 * price_score


def rank_capabilities(
    query: str,
    capabilities: Iterable["Capability"],
    *,
    limit: int | None = 20,
    localized_descriptions: dict[str, dict[str, str]] | None = None,
) -> tuple[IntentInterpretation, list[SearchMatch]]:
    """Return explainable hybrid matches, ordered by applicability then quality."""
    interpretation = interpret_intent(query)
    if not interpretation.normalized:
        return interpretation, []
    if limit is not None and limit <= 0:
        return interpretation, []

    localized = localized_descriptions if localized_descriptions is not None else load_localized_descriptions()
    documents = [_document_for(cap, localized) for cap in capabilities]
    if not documents:
        return interpretation, []

    total = len(documents)
    token_df = {
        token: sum(
            1
            for doc in documents
            if token in doc.id_tokens or token in doc.name_tokens or token in doc.description_tokens
        )
        for token in interpretation.tokens
    }
    concept_df = {
        concept: sum(1 for doc in documents if concept in doc.concepts)
        for concept in interpretation.concepts
    }

    ranked: list[SearchMatch] = []
    for doc in documents:
        token_weight_total = sum(_idf(total, token_df[token]) for token in interpretation.tokens) or 1.0
        lexical_weight = 0.0
        identity_weight = 0.0
        literal_hits: list[str] = []
        all_doc_tokens = doc.id_tokens | doc.name_tokens | doc.description_tokens
        for token in interpretation.tokens:
            weight = _idf(total, token_df[token])
            field_score = 0.0
            if token in doc.id_tokens:
                field_score = 1.0
            elif token in doc.name_tokens:
                field_score = 0.82
            elif token in doc.description_tokens:
                field_score = 0.62
            if field_score:
                lexical_weight += field_score * weight
                literal_hits.append(token)
                if field_score > 0.62:
                    identity_weight += field_score * weight
        lexical_score = min(1.0, lexical_weight / token_weight_total)
        # Lexical evidence from the capability's own id/name only. A description word is
        # too cheap to earn a bonus: an inflection accident ("показаний") or one stray word
        # ("optimization" in a tour optimiser) outranked the right capability with it.
        identity_score = min(1.0, identity_weight / token_weight_total)

        matched_concepts = tuple(c for c in interpretation.concepts if c in doc.concepts)
        semantic_score = 0.0
        if interpretation.concepts and matched_concepts:
            def concept_weight(concept: str) -> float:
                return _idf(total, concept_df[concept]) * _CONCEPT_QUERY_BOOST.get(concept, 1.0)

            query_weight = sum(concept_weight(c) for c in interpretation.concepts)
            matched_weight = sum(concept_weight(c) for c in matched_concepts)
            recall = matched_weight / query_weight if query_weight else 0.0
            # A concise capability profile should win over a broad, vaguely related one.
            doc_weight = sum(_idf(total, concept_df.get(c, total)) for c in doc.concepts) or 1.0
            precision = min(1.0, matched_weight / doc_weight)
            semantic_score = min(1.0, 0.88 * recall + 0.12 * precision)

        # Fuzzy comparison is the expensive fallback. Natural-language intents already
        # have semantic concepts, so running SequenceMatcher for every unmatched filler
        # word only adds latency and noise. Reserve it for genuinely unrecognised/typo
        # queries such as "wether".
        fuzzy_score = 0.0
        if not interpretation.concepts and not literal_hits:
            fuzzy_weight = sum(
                _closest_token(token, all_doc_tokens) * _idf(total, token_df[token])
                for token in interpretation.tokens
            )
            fuzzy_score = min(1.0, fuzzy_weight / token_weight_total)

        exact_id = bool(
            interpretation.normalized == doc.id_text
            or (len(interpretation.normalized) >= 4 and interpretation.normalized in doc.id_text)
        )
        if not exact_id and not literal_hits and not matched_concepts and fuzzy_score < 0.82:
            continue

        if exact_id:
            relevance = 1.0
        else:
            blended = 0.54 * lexical_score + 0.42 * semantic_score + 0.04 * fuzzy_score
            strongest = max(lexical_score, semantic_score * 0.94, fuzzy_score * 0.64)
            # A concept the query and the capability's own NAME agree on earns a bonus over
            # the semantic floor. Without it every doc sharing a concept tied at
            # `strongest * 0.76` and quality alone decided: "current weather in Berlin" put
            # gaia.spacewx and gaia.water_quality above gaia.weather.read, whose id says
            # weather. Description-only and concept-only matches get nothing, so this can
            # neither invent relevance nor be bought by stuffing words into a description.
            relevance = min(1.0, max(
                blended, strongest * 0.76 + 0.20 * min(identity_score, semantic_score),
            ))
        if relevance < 0.14:
            continue

        quality = _quality_score(doc.capability)
        # Business quality can move close matches, never manufacture relevance.
        final_score = min(1.0, relevance * (0.95 + 0.05 * quality))

        if exact_id or lexical_score >= 0.90:
            match_type = "exact"
        elif semantic_score >= 0.45 and lexical_score >= 0.18:
            match_type = "hybrid"
        elif semantic_score >= max(0.30, lexical_score * 1.15):
            match_type = "semantic"
        elif fuzzy_score >= 0.82 and lexical_score == 0:
            match_type = "fuzzy"
        else:
            match_type = "lexical"

        matched_terms: list[str] = []
        for concept in matched_concepts:
            for alias in interpretation.aliases_by_concept.get(concept, ()):
                if normalize_text(alias) not in {normalize_text(term) for term in matched_terms}:
                    matched_terms.append(alias)
        for token in literal_hits:
            normalized_token = normalize_text(token)
            existing = {normalize_text(term) for term in matched_terms}
            same_stem = any(
                min(len(normalized_token), len(term)) >= 4
                and (normalized_token.startswith(term) or term.startswith(normalized_token))
                for term in existing
            )
            if normalized_token not in existing and not same_stem:
                matched_terms.append(token)

        ranked.append(SearchMatch(
            capability=doc.capability,
            score=round(final_score, 4),
            lexical_score=round(lexical_score, 4),
            semantic_score=round(semantic_score, 4),
            quality_score=round(quality, 4),
            match_type=match_type,
            matched_concepts=matched_concepts[:5],
            matched_terms=tuple(matched_terms[:5]),
        ))

    ranked.sort(
        key=lambda item: (
            item.score,
            item.semantic_score,
            item.lexical_score,
            item.quality_score,
            item.capability.trust_score,
        ),
        reverse=True,
    )
    return interpretation, ranked if limit is None else ranked[:limit]
