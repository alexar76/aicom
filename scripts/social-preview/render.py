#!/usr/bin/env python3
"""Social preview cards (1280×640) for the GitHub satellites, from cards.json.

GitHub shows a repository's "social preview" wherever a link to it is pasted (dev.to, Bluesky,
LinkedIn, chats); without one it is a grey generated card. Uploading is manual (Settings →
General → Social preview, PNG under 1 MB), so this only renders the files:

    python3 scripts/social-preview/render.py            # every card → scripts/social-preview/out/<repo>.png
    python3 scripts/social-preview/render.py warden     # one card

Rendering is headless Chrome over an HTML page; fonts are HISTOR's vendored IBM Plex and Fraunces.
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FONTS = ROOT / "histor" / "docs" / "landing" / "assets" / "fonts" / "fonts.css"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
W, H = 1280, 640

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{fonts}">
<style>
:root {{ --void:#05080d; --ink:#efe9dc; --muted:#9aa6b8; --faint:#5f6b7d; --accent:{accent}; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html,body {{ width:{w}px; height:{h}px; overflow:hidden; background:var(--void); }}
body {{ position:relative; font-family:"IBM Plex Sans",system-ui,sans-serif; color:var(--ink); }}
.art {{ position:absolute; top:0; right:0; width:{art_w}px; height:100%;
  background:url("{image}") center/cover no-repeat; }}
.art::after {{ content:""; position:absolute; inset:0;
  background:linear-gradient(90deg, var(--void) 0%, rgba(5,8,13,.55) 28%, rgba(5,8,13,0) 60%); }}
.grid {{ position:absolute; inset:0;
  background-image:radial-gradient(circle at 1px 1px, rgba(255,255,255,.07) 1px, transparent 0);
  background-size:28px 28px; }}
.glow {{ position:absolute; right:-160px; top:-120px; width:760px; height:760px; border-radius:50%;
  background:radial-gradient(circle, color-mix(in srgb, var(--accent) 30%, transparent) 0%, transparent 62%); }}
.text {{ position:absolute; left:72px; top:64px; bottom:64px; width:{text_w}px; display:flex; flex-direction:column; }}
.kicker {{ font-family:"IBM Plex Mono",monospace; font-size:21px; letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }}
h1 {{ font-family:"Fraunces",Georgia,serif; font-weight:700; font-size:{title_px}px; line-height:1.02; letter-spacing:-.015em; margin-top:18px; }}
.line {{ font-size:31px; line-height:1.34; color:#d6cfbf; margin-top:22px; text-wrap:balance; }}
.panel {{ position:absolute; right:72px; top:118px; width:{panel_w}px; }}
.big {{ font-family:"Fraunces",Georgia,serif; font-weight:700; font-size:104px; line-height:1; color:var(--accent); }}
.big-sub {{ font-size:27px; color:var(--muted); margin-top:12px; line-height:1.3; }}
.chips {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:34px; }}
.chip {{ font-family:"IBM Plex Mono",monospace; font-size:21px; padding:8px 14px; border-radius:10px;
  border:1px solid color-mix(in srgb, var(--accent) 45%, transparent); color:var(--ink);
  background:rgba(255,255,255,.03); }}
.foot {{ margin-top:auto; display:flex; flex-direction:column; gap:14px; }}
.cmd {{ align-self:flex-start; font-family:"IBM Plex Mono",monospace; font-size:24px; padding:12px 18px;
  border-radius:12px; background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.1); }}
.cmd b {{ color:var(--accent); font-weight:500; }}
.url {{ font-family:"IBM Plex Mono",monospace; font-size:21px; color:var(--faint); }}
</style></head><body>
{background}
<div class="text">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="line">{line}</div>
  <div class="foot">{cmd}<div class="url">{url}</div></div>
</div>
{panel}
</body></html>"""


def page(card: dict) -> str:
    image = card.get("image")
    esc = html.escape
    if image:
        art_w = card.get("art_width", 700)
        background = f'<div class="art"></div>'
        text_w = W - 72 - 64 - art_w + 200
        panel = ""
    else:
        art_w = 0
        background = '<div class="grid"></div><div class="glow"></div>'
        text_w = 640
        big = card.get("big")
        chips = "".join(f'<span class="chip">{esc(c)}</span>' for c in card.get("chips", []))
        panel = (f'<div class="panel">'
                 + (f'<div class="big">{esc(big)}</div><div class="big-sub">{esc(card.get("big_sub", ""))}</div>' if big else "")
                 + (f'<div class="chips">{chips}</div>' if chips else "")
                 + "</div>")
    cmd = card.get("cmd")
    # "$" marks a shell command; a card whose line is an address names what it is instead.
    prompt = card.get("prompt", "$")
    cmd_html = f'<div class="cmd"><b>{esc(prompt)}</b> {esc(cmd)}</div>' if cmd else ""
    return PAGE.format(
        fonts=FONTS.as_uri(), accent=card.get("accent", "#5fe3ff"), w=W, h=H, art_w=art_w,
        image=(ROOT / image).as_uri() if image else "", text_w=text_w, panel_w=W - 72 - 72 - 640 - 40,
        title_px=card.get("title_px", 92), background=background, kicker=esc(card["kicker"]),
        title=esc(card["title"]), line=esc(card["line"]), cmd=cmd_html, url=esc(card["url"]), panel=panel,
    )


def render(card: dict, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "card.html"
        src.write_text(page(card), encoding="utf-8")
        raw = Path(tmp) / "card.png"
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        f"--window-size={W},{H}", "--allow-file-access-from-files", "--virtual-time-budget=3000",
                        f"--screenshot={raw}", src.as_uri()],
                       check=True, capture_output=True, timeout=120)
        from PIL import Image

        im = Image.open(raw).convert("RGB").crop((0, 0, W, H))
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, optimize=True)
        if out.stat().st_size > 1_000_000:  # GitHub refuses a social preview over 1 MB
            im.save(out.with_suffix(".jpg"), quality=88, optimize=True)
            out.unlink()


def main(argv: list[str]) -> int:
    cards = json.loads((HERE / "cards.json").read_text(encoding="utf-8"))
    wanted = set(argv)
    for card in cards:
        if wanted and card["repo"] not in wanted:
            continue
        out = HERE / "out" / f"{card['repo']}.png"
        render(card, out)
        done = out if out.exists() else out.with_suffix(".jpg")
        print(f"{card['repo']}: {done.relative_to(ROOT)} ({done.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
