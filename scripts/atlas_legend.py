#!/usr/bin/env python3
"""Generate the five ATLAS map-legend documents from the runtime catalog.

The map itself gets layer labels and colours from ``atlas.stations.LAYER_META``.
Documentation must use the same source or it will inevitably drift.

    python3 scripts/atlas_legend.py --check
    python3 scripts/atlas_legend.py --write
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Monorepo: scripts/atlas_legend.py → ROOT=aicom, package at ROOT/atlas
# Satellite: atlas/scripts/atlas_legend.py → ROOT=atlas-repo, package at ROOT
if (ROOT / "atlas" / "pyproject.toml").is_file():
    sys.path.insert(0, str(ROOT / "atlas"))
    _DOC = {
        "en": "atlas/docs/LEGEND.md",
        "ru": "atlas/docs/i18n/LEGEND.ru.md",
        "es": "atlas/docs/i18n/LEGEND.es.md",
        "fr": "atlas/docs/i18n/LEGEND.fr.md",
        "zh": "atlas/docs/i18n/LEGEND.zh.md",
    }
elif (ROOT / "pyproject.toml").is_file() and (ROOT / "atlas").is_dir():
    sys.path.insert(0, str(ROOT))
    _DOC = {
        "en": "docs/LEGEND.md",
        "ru": "docs/i18n/LEGEND.ru.md",
        "es": "docs/i18n/LEGEND.es.md",
        "fr": "docs/i18n/LEGEND.fr.md",
        "zh": "docs/i18n/LEGEND.zh.md",
    }
else:
    raise SystemExit(f"Cannot resolve ATLAS package root from {ROOT}")

from atlas.stations import LAYER_META, STATION_CATALOG  # noqa: E402


@dataclass(frozen=True)
class LegendTarget:
    lang: str
    path: str

    @property
    def full(self) -> Path:
        return ROOT / self.path


TARGETS = tuple(LegendTarget(lang, path) for lang, path in _DOC.items())

COPY: dict[str, dict[str, str]] = {
    "en": {
        "title": "ATLAS map legend",
        "languages": "Languages",
        "generated": (
            "This legend is generated from `atlas.stations.LAYER_META` and "
            "`STATION_CATALOG`; do not edit it by hand. Regenerate it with "
            "`python3 scripts/atlas_legend.py --write`."
        ),
        "contract": (
            "**Coordinate contract:** one visible map point is one reading coordinate. "
            "A fixed station uses its official anchor; an on-demand grid read uses the returned "
            "source/query cell. Dense and event feeds are expanded into child points at the reading coordinate or cell centre; their "
            "parent object is not plotted as a duplicate point."
        ),
        "same_color": (
            "Colour identifies the layer, not severity or sensor health. Some related layers "
            "intentionally share a colour; use the layer key and filter to distinguish them. "
            "LIVE/SIM state and availability are shown separately."
        ),
        "summary": "The catalog currently defines {layers} layers and {devices} configured devices. Event and dense feeds may create additional reading points at runtime.",
        "color": "Colour",
        "key": "Layer key",
        "meaning": "Meaning",
        "devices": "Example device IDs",
    },
    "ru": {
        "title": "Легенда карты ATLAS",
        "languages": "Языки",
        "generated": (
            "Легенда генерируется из `atlas.stations.LAYER_META` и `STATION_CATALOG`; "
            "не редактируйте её вручную. Команда обновления: "
            "`python3 scripts/atlas_legend.py --write`."
        ),
        "contract": (
            "**Координатный контракт:** одна видимая точка карты — одна координата показания. "
            "Стационарная станция использует официальную координату, а запрошенное чтение сетки — "
            "координату возвращённой исходной/расчётной ячейки. "
            "Плотные и событийные источники разворачиваются в дочерние точки по координате "
            "показания или центру ячейки; родительский объект не рисуется второй точкой."
        ),
        "same_color": (
            "Цвет обозначает слой, а не опасность или исправность датчика. Некоторые родственные "
            "слои намеренно используют одинаковый цвет; различайте их по ключу и фильтру слоя. "
            "Состояния LIVE/SIM и доступность показываются отдельно."
        ),
        "summary": "Сейчас каталог задаёт {layers} слоёв и {devices} настроенных устройств. Событийные и плотные источники могут добавлять точки показаний во время работы.",
        "color": "Цвет",
        "key": "Ключ слоя",
        "meaning": "Что изображает",
        "devices": "Примеры device_id",
    },
    "es": {
        "title": "Leyenda del mapa ATLAS",
        "languages": "Idiomas",
        "generated": (
            "Esta leyenda se genera desde `atlas.stations.LAYER_META` y `STATION_CATALOG`; "
            "no se edita a mano. Regenerar con `python3 scripts/atlas_legend.py --write`."
        ),
        "contract": (
            "**Contrato de coordenadas:** un punto visible del mapa corresponde a una coordenada "
            "de lectura. Una estación fija usa su coordenada oficial; una lectura de cuadrícula "
            "bajo demanda usa la celda de origen/consulta devuelta. Las "
            "fuentes densas y de eventos se expanden en puntos hijos en la coordenada de la "
            "lectura o el centro de celda; el objeto padre no se dibuja como punto duplicado."
        ),
        "same_color": (
            "El color identifica la capa, no la gravedad ni la salud del sensor. Algunas capas "
            "relacionadas comparten color intencionadamente; se distinguen por la clave y el "
            "filtro de capa. Los estados LIVE/SIM y la disponibilidad se muestran por separado."
        ),
        "summary": "El catálogo define actualmente {layers} capas y {devices} dispositivos configurados. Las fuentes densas y de eventos pueden crear puntos de lectura adicionales en ejecución.",
        "color": "Color",
        "key": "Clave de capa",
        "meaning": "Qué representa",
        "devices": "Ejemplos de device_id",
    },
    "fr": {
        "title": "Légende de la carte ATLAS",
        "languages": "Langues",
        "generated": (
            "Cette légende est générée depuis `atlas.stations.LAYER_META` et "
            "`STATION_CATALOG` ; ne pas la modifier à la main. Régénération : "
            "`python3 scripts/atlas_legend.py --write`."
        ),
        "contract": (
            "**Contrat de coordonnées :** un point visible sur la carte correspond à une "
            "coordonnée de lecture. Une station fixe utilise sa coordonnée officielle ; une lecture "
            "de grille à la demande utilise la cellule source/requête renvoyée. Les flux denses et événementiels sont développés en points enfants à "
            "la coordonnée de lecture ou au centre de cellule ; l’objet parent n’est pas tracé "
            "comme point en double."
        ),
        "same_color": (
            "La couleur identifie la couche, pas la gravité ni l’état du capteur. Certaines "
            "couches liées partagent volontairement une couleur ; la clé et le filtre de couche "
            "les distinguent. Les états LIVE/SIM et la disponibilité sont affichés séparément."
        ),
        "summary": "Le catalogue définit actuellement {layers} couches et {devices} appareils configurés. Les flux denses et événementiels peuvent créer des points de lecture supplémentaires à l’exécution.",
        "color": "Couleur",
        "key": "Clé de couche",
        "meaning": "Signification",
        "devices": "Exemples de device_id",
    },
    "zh": {
        "title": "ATLAS 地图图例",
        "languages": "语言",
        "generated": (
            "本图例由 `atlas.stations.LAYER_META` 和 `STATION_CATALOG` 生成；请勿手工编辑。"
            "使用 `python3 scripts/atlas_legend.py --write` 重新生成。"
        ),
        "contract": (
            "**坐标约定：**地图上一个可见点只代表一个读数坐标。固定站点使用其官方坐标；"
            "按需网格读数使用数据源返回的源/查询网格单元。密集数据源和事件数据源按读数坐标或网格中心展开为子点；"
            "父对象不会再绘制为重复点。"
        ),
        "same_color": (
            "颜色标识图层，不表示严重程度或传感器健康状态。部分相关图层有意共用颜色；"
            "请通过图层键和筛选器区分。LIVE/SIM 状态与可用性另行显示。"
        ),
        "summary": "当前目录定义了 {layers} 个图层和 {devices} 个已配置设备。事件和密集数据源可在运行时创建更多读数点。",
        "color": "颜色",
        "key": "图层键",
        "meaning": "表示内容",
        "devices": "device_id 示例",
    },
}


def _links(lang: str) -> str:
    prefix = "" if lang == "en" else "../"
    local_prefix = "i18n/" if lang == "en" else ""
    return " · ".join(
        (
            f"[EN]({prefix}LEGEND.md)",
            f"[RU]({local_prefix}LEGEND.ru.md)",
            f"[ES]({local_prefix}LEGEND.es.md)",
            f"[FR]({local_prefix}LEGEND.fr.md)",
            f"[ZH]({local_prefix}LEGEND.zh.md)",
        )
    )


def _label(layer: str, lang: str) -> str:
    meta = LAYER_META[layer]
    labels = meta.get("labels") or {}
    return str(labels.get(lang) or meta.get("label") or layer)


def _device_cell(layer: str) -> str:
    ids = [did for did, meta in STATION_CATALOG.items() if meta.get("layer") == layer]
    shown = ids[:4]
    cell = ", ".join(f"`{did}`" for did in shown) or "—"
    if len(ids) > len(shown):
        cell += f" +{len(ids) - len(shown)}"
    return cell


def render_legend(lang: str) -> str:
    c = COPY[lang]
    lines = [
        f"# {c['title']}",
        "",
        f"**{c['languages']}:** {_links(lang)}",
        "",
        c["generated"],
        "",
        c["contract"],
        "",
        c["same_color"],
        "",
        c["summary"].format(layers=len(LAYER_META), devices=len(STATION_CATALOG)),
        "",
        f"| {c['color']} | {c['key']} | {c['meaning']} | {c['devices']} |",
        "|---|---|---|---|",
    ]
    for layer, meta in LAYER_META.items():
        color = str(meta.get("color") or "#888888")
        swatch = f'<span style="color:{color}">●</span> `{color}`'
        lines.append(
            f"| {swatch} | `{layer}` | {_label(layer, lang)} | {_device_cell(layer)} |"
        )
    return "\n".join(lines) + "\n"


def run(write: bool) -> int:
    drift = False
    for target in TARGETS:
        wanted = render_legend(target.lang)
        current = target.full.read_text(encoding="utf-8") if target.full.is_file() else ""
        if current == wanted:
            print(f"ok      {target.path}")
            continue
        drift = True
        if write:
            target.full.parent.mkdir(parents=True, exist_ok=True)
            target.full.write_text(wanted, encoding="utf-8")
            print(f"written {target.path}")
        else:
            print(f"DRIFT   {target.path}")
    return 0 if write or not drift else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    return run(write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
