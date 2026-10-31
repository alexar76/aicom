"""Render the local DEV.to draft for desktop and mobile visual review."""
import argparse
import html
import json
from pathlib import Path
import re

import markdown


def render(pack):
    source = (pack / "article.md").read_text()
    _, frontmatter, body = source.split("---", 2)
    title = json.loads(re.search(r'^title: (.+)$', frontmatter, re.M)[1])
    tags = re.search(r'^tags: (.+)$', frontmatter, re.M)[1].split(", ")
    plain = re.sub(r"```[\s\S]*?```", "", body)
    words = len(re.findall(r"\b[\w'-]+\b", plain))
    content = markdown.markdown(body, extensions=["tables", "fenced_code", "codehilite"])
    content = content.replace("<table>", '<div class="table-scroll"><table>').replace("</table>", "</table></div>")
    badges = " ".join(f"<span>#{html.escape(t)}</span>" for t in tags)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme:light; --ink:#162d3b; --muted:#566b72; --accent:#357d7b; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; color:var(--ink); background:#f5f0e6; font:19px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
.draft {{ max-width:1060px; margin:auto; padding:18px 30px; font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }}
article {{ max-width:1000px; margin:0 auto 70px; padding:48px 62px 60px; background:#fffefa; border:1px solid #e4ded2; border-radius:12px; }}
h1 {{ font-size:46px; line-height:1.14; letter-spacing:-.035em; margin:0 0 18px; max-width:800px; }}
h2 {{ font-size:29px; line-height:1.28; letter-spacing:-.02em; margin:48px 0 20px; }}
p {{ margin:22px 0; }}
header p {{ margin:0 0 28px; color:var(--muted); font-size:14px; }}
.tags {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:30px; font-size:15px; color:var(--accent); }}
a {{ color:#246f7c; text-underline-offset:3px; }}
img {{ display:block; max-width:100%; height:auto; border-radius:7px; }}
strong {{ font-weight:720; }}
p>em:only-child {{ display:block; color:var(--muted); font-size:15px; line-height:1.55; }}
code {{ font: .88em/1.6 ui-monospace,"SFMono-Regular",Consolas,monospace; background:#edf1ee; padding:.12em .28em; border-radius:4px; overflow-wrap:anywhere; }}
pre {{ margin:26px 0; padding:24px; overflow:auto; background:#122832; color:#edf4ef; border-radius:8px; line-height:1.6; font-size:14px; }}
pre code {{ padding:0; border:0; color:inherit; background:transparent; overflow-wrap:normal; white-space:pre; font-size:inherit; }}
.table-scroll {{ overflow-x:auto; margin:26px 0; }}
table {{ border-collapse:collapse; width:100%; font-size:15px; line-height:1.5; min-width:540px; }}
th,td {{ text-align:left; vertical-align:top; padding:13px 14px; border-bottom:1px solid #dce3dd; }}
th {{ background:#e7efeb; font-weight:700; }}
th:last-child,td:last-child {{ text-align:right; width:120px; }}
tr:nth-child(even) td {{ background:#f8f8f2; }}
.codehilite .k,.codehilite .kn,.codehilite .kd {{ color:#73c6c0; }}
.codehilite .s,.codehilite .s1,.codehilite .s2,.codehilite .sd {{ color:#f3c297; }}
.codehilite .c,.codehilite .c1 {{ color:#9db2b6; }}
.codehilite .nf,.codehilite .nc {{ color:#d6e9e2; }}
@media(max-width:700px) {{
body {{ font-size:17px; line-height:1.65; background:#fffefa; }}
.draft {{ padding:16px 20px; font-size:11px; }}
article {{ padding:20px 20px 42px; border:0; border-radius:0; margin-bottom:0; }}
h1 {{ font-size:35px; }} h2 {{ font-size:25px; margin-top:38px; }}
pre {{ font-size:12px; padding:18px; }}
.tags {{ gap:12px; font-size:13px; }}
}}
</style></head><body>
<div class="draft">Local draft · DEV.to · alexar76</div>
<article><header><h1>{html.escape(title)}</h1><p>Alex · Prepared 29 October 2026 · {words:,} words excluding code</p><div class="tags">{badges}</div></header>
{content}</article></body></html>'''
    (pack / "preview.html").write_text(page)
    return {"title": title, "wordsExcludingCode": words, "images": len(re.findall(r'!\[', body)), "tags": tags}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    args = parser.parse_args()
    print(json.dumps(render(args.pack), indent=2))
