#!/usr/bin/env python3
"""Render ARGUS user-guide, developer-guide + humor markdown from argus/docs/i18n/*.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "argus" / "docs" / "i18n"
GUIDE_DIR = ROOT / "argus" / "docs" / "user-guide"
DEV_GUIDE_DIR = ROOT / "argus" / "docs" / "developer-guide"
HUMOR_DIR = GUIDE_DIR / "humor"

SKIP_GUIDES = {"en"}  # en.md maintained by hand (full canonical)
SKIP_DEV_GUIDES = {"en"}

WATCH_CARTOON = {
    "en": "Watch the animated cartoon →",
    "zh": "观看动画短片 →",
    "es": "Ver el cartoon animado →",
    "hi": "एनिमेटेड कार्टून देखें →",
    "ar": "شاهد الرسوم المتحركة →",
    "pt": "Assistir ao cartoon animado →",
    "ru": "Смотреть анимированный мульт →",
    "ja": "アニメーションを見る →",
    "fr": "Voir le cartoon animé →",
    "de": "Animierten Cartoon ansehen →",
    "ko": "애니메이션 보기 →",
    "it": "Guarda il cartoon animato →",
    "tr": "Animasyonu izle →",
    "id": "Tonton kartun animasi →",
    "vi": "Xem hoạt hình →",
    "th": "ดูการ์ตูนแอนิเมชัน →",
    "hr": "Pogledaj animirani cartoon →",
    "sk": "Pozrieť animovaný cartoon →",
    "nl": "Bekijk de animatie →",
    "fa": "تماشای کارتون انیمیشنی →",
}


def render_humor(lang: str, data: dict) -> str:
    lines = [
        f"# {data['title']}",
        "",
        f"> {data['tagline']}",
        "",
        data["intro"],
        "",
    ]
    for i, s in enumerate(data["situations"], 1):
        lines += [f"## {i}. {s['title']}", "", s["body"], ""]
    watch = data.get("cartoon_watch") or WATCH_CARTOON.get(lang, WATCH_CARTOON["en"])
    lines += [
        f"## {data['will_help_title']}",
        "",
        data["will_help_body"],
        "",
        "---",
        "",
        data["cta"],
        "",
        f"🎬 **[{watch}](./cartoon.html?lang={lang})** · ~40s · subtitles in 20 languages",
        "",
        f"← [User guide ({data.get('lang_name', lang)})](../{lang}.md) · [All languages](./README.md)",
        "",
    ]
    return "\n".join(lines)


def render_guide(lang: str, data: dict) -> str:
    h = data["humor_link"]
    lines = [
        f"# {data['title']}",
        "",
        f"> {data['subtitle']}",
        "",
        "---",
        "",
        f"## {data['s1_title']}",
        "",
        data["s1_body"],
        "",
        f"```bash\n{data['install_cmd']}\n```",
        "",
        f"## {data['s2_title']}",
        "",
        data["s2_body"],
        "",
        f"## {data['s3_title']}",
        "",
        data["s3_body"],
        "",
        f"## {data['s4_title']}",
        "",
        data["s4_body"],
        "",
        f"## {data['s5_title']}",
        "",
        data["s5_body"],
        "",
        "---",
        "",
        f"## 😈 {h['title']}",
        "",
        h["teaser"],
        "",
        f"🎬 [{WATCH_CARTOON.get(lang, WATCH_CARTOON['en'])}](./humor/cartoon.html?lang={lang}) · **[{h['read']}](./humor/{lang}.md)**",
        "",
        "---",
        "",
        data["footer"],
        "",
    ]
    return "\n".join(lines)


def render_developer_guide(lang: str, data: dict) -> str:
    lines = [
        f"# {data['title']}",
        "",
        f"> {data['subtitle']}",
        "",
        "---",
        "",
        f"## {data['s1_title']}",
        "",
        data["s1_body"],
        "",
        f"```bash\n{data['server_cmd']}\n```",
        "",
        f"## {data['s2_title']}",
        "",
        data["s2_body"],
        "",
    ]
    if data.get("s2_sec_title"):
        lines += [
            f"## {data['s2_sec_title']}",
            "",
            data["s2_sec_body"],
            "",
        ]
        if data.get("stake_cmd"):
            lines += [f"```bash\n{data['stake_cmd']}\n```", ""]
    lines += [
        f"## {data['s3_title']}",
        "",
        data["s3_body"],
        "",
        f"```bash\n{data['publish_cmd']}\n```",
        "",
        f"## {data['s4_title']}",
        "",
        data["s4_body"],
        "",
        f"```bash\n{data['invoke_cmd']}\n```",
        "",
        f"## {data['s5_title']}",
        "",
        data["s5_body"],
        "",
        "---",
        "",
        data["footer"],
        "",
    ]
    if lang != "en":
        lines.insert(4, f"📖 [Full guide (English)](./en.md)")
        lines.insert(5, "")
    return "\n".join(lines)


def main() -> None:
    humor = json.loads((I18N / "humor.json").read_text(encoding="utf-8"))
    guides = json.loads((I18N / "guides.json").read_text(encoding="utf-8"))
    dev_guides_path = I18N / "developer-guides.json"
    dev_guides = json.loads(dev_guides_path.read_text(encoding="utf-8")) if dev_guides_path.is_file() else {}

    HUMOR_DIR.mkdir(parents=True, exist_ok=True)
    DEV_GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    for lang, payload in humor.items():
        out = HUMOR_DIR / f"{lang}.md"
        out.write_text(render_humor(lang, payload), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")

    for lang, payload in guides.items():
        if lang in SKIP_GUIDES:
            continue
        out = GUIDE_DIR / f"{lang}.md"
        out.write_text(render_guide(lang, payload), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")

    for lang, payload in dev_guides.items():
        if lang in SKIP_DEV_GUIDES:
            continue
        out = DEV_GUIDE_DIR / f"{lang}.md"
        out.write_text(render_developer_guide(lang, payload), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
