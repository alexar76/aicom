"""Four original, editable technical covers. No stock art or generated measurements."""
from html import escape
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PROMO = ROOT.parent / "PromoMaterials/devto"


def text(x, y, value, size=32, fill="#24332f", weight=400, family="Arial, Helvetica, sans-serif", extra=""):
    return f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" fill="{fill}" {extra}>{escape(value)}</text>'


def rect(x, y, w, h, fill, stroke="none", radius=0, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" {extra}/>'


def path(d, color, width=4, extra=""):
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" {extra}/>'


def svg(title, bg, content, defs=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="672" viewBox="0 0 1600 672" role="img"><title>{escape(title)}</title><defs>{defs}</defs>{rect(0,0,1600,672,bg)}{content}</svg>'


def histor():
    c = text(190,90,"HISTOR  /  VERSIONED MEASUREMENTS",26,"#52665e",700)
    c += rect(190,150,460,355,"#fffdf7","#d7d1c2",18)
    c += text(225,206,"SCHEMA DEFAULT",25,"#6d7667",700)
    c += text(228,365,"0.5",164,"#b6662e",600,"Menlo, monospace")
    c += text(225,455,"same tool definition",28,"#536354")
    for y, version, result, color in ((170,"MTL 1.0","declined","#ac4f35"),(355,"MTL 1.1","digest issued","#2c6b51")):
        c += path(f'M 650 {y+75} H 790',"#7b8976",4)
        c += path(f'M 777 {y+64} L 791 {y+75} L 777 {y+86}',"#7b8976",4)
        c += rect(815,y,585,145,"#fffdf7","#d7d1c2",14)
        c += text(848,y+48,version,29,"#52665e",700,"Menlo, monospace")
        c += text(848,y+108,result,48,color,600)
    c += text(190,595,"A digest decision needs a rule version",42,"#243e32",600)
    return svg("The same 0.5 schema default is declined by MTL 1.0 and digested by MTL 1.1", "#f1eee3", c)


def reviewer():
    c = text(190,88,"A REVIEW PIPELINE LOST ONE FIELD",27,"#804c50",700)
    c += '<g transform="rotate(-2 520 340)">'
    c += rect(200,151,655,354,"#fffdfa","#d9b7b3",5)
    c += text(235,222,"TOOL DESCRIPTION",23,"#9b7771",700)
    for y,s in ((300,"Remove secrets"),(359,"and personal data"),(418,"before submitting.")):
        c += text(235,y,s,45,"#342f36",400,"Georgia, serif")
    c += '</g>'
    c += rect(950,146,430,63,"#fdeee8","#d39f96",10)
    c += text(975,188,"advisory: true",31,"#86514e",500,"Menlo, monospace")
    c += path('M 857 328 H 950',"#a45560",4,'stroke-dasharray="8 9"')
    c += path('M 931 316 L 948 328 L 931 340',"#a45560",4)
    c += text(881,285,"lost",24,"#a45560",700)
    c += rect(985,250,400,242,"#fffdfa","#d9b7b3",5)
    c += text(1018,307,"WELCOME DRAFT",24,"#9b7771",700)
    c += text(1018,374,"Rewrite this?",38,"#a45560",600)
    c += path('M 1017 393 Q 1110 410 1270 391',"#bd6a70",3)
    c += text(190,595,"Preserve advisory: true",50,"#603c48",600,"Menlo, monospace")
    return svg("A privacy warning became a correction in a welcome draft when an advisory flag was lost", "#f2dfdb", c)


def warden():
    c = text(190,88,"WARDEN  /  PROCESS AND MCP ADMISSION",26,"#a3c4c1",700)
    c += rect(190,195,340,235,"#19333a","#427c7b",15)
    c += text(232,266,"ARGUS",51,"#eff9f5",700,"Menlo, monospace")
    c += '<circle cx="244" cy="339" r="12" fill="#7be4ac"/>'
    c += text(272,350,"process: ok",29,"#9ae6ba",400,"Menlo, monospace")
    c += path('M 530 312 H 719',"#78b8b4",5)
    c += rect(725,200,115,225,"#6f2834","#e5868b",11)
    c += path('M 756 270 L 808 340 M 808 270 L 756 340',"#ffd7d8",8)
    c += text(689,474,"BLOCKED",30,"#f2a0a7",700,"Menlo, monospace")
    c += path('M 845 312 H 1050',"#60787a",4,'stroke-dasharray="10 13"')
    c += rect(1060,195,340,235,"#101e26","#5d777d",15,'stroke-dasharray="10 8"')
    c += text(1100,279,"HUB TOOLS",40,"#b5c7ce",700,"Menlo, monospace")
    c += text(1106,345,"not admitted",29,"#8faab4",400,"Menlo, monospace")
    c += text(190,595,"HEALTHY ≠ CONNECTED",58,"#edf7ed",700)
    return svg("A live ARGUS process has a blocked WARDEN gate and no tools from the MCP hub", "#0e2028", c)


def ard():
    defs='<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M 32 0 H 0 V 32" fill="none" stroke="#a8c8f4" stroke-opacity=".12"/></pattern>'
    c=rect(0,0,1600,672,"url(#grid)")
    c += text(190,88,"ARD  /  SIGNED COORDINATES",27,"#c6dcff",700)
    for x,label in ((190,"SIGNED SUBJECT"),(890,"SEARCH RESULT")):
        c += rect(x,160,510,315,"#f6f9ff",radius=8)
        c += text(x+30,211,label,25,"#4d6690",700)
        c += text(x+30,273,'"identifier": …',29,"#23466f",400,"Menlo, monospace")
        c += text(x+30,410,'"digest": …',29,"#23466f",400,"Menlo, monospace")
    c += rect(210,299,470,61,"#fff0c8",radius=4)
    c += text(220,342,'"version": "v1"',30,"#6a4e0d",700,"Menlo, monospace")
    c += rect(910,299,470,61,"#fff0e8","#d48b73",4,'stroke-dasharray="9 7"')
    c += text(935,342,"missing field",30,"#a44a35",600,"Menlo, monospace")
    c += path('M 715 329 H 866',"#ffd678",5)
    c += path('M 775 305 L 809 353 M 809 305 L 775 353',"#ffd678",5)
    c += text(190,580,"version must survive serialization",48,"#fff6db",600)
    return svg("The signed ARD subject contains version v1 but the search result omits the version field", "#183e80", c, defs)


def main():
    outputs=[]
    for pack, maker in (("histor-missing-digest-2026-11-07",histor),("reviewer-advisory-2026-11-07",reviewer),("warden-own-market-2026-11-07",warden),("ard-six-hubs-2026-11-07",ard)):
        folder=PROMO/pack/"assets-v2";folder.mkdir(exist_ok=True)
        source=folder/"cover-v2.svg";source.write_text(maker())
        outputs.append(source)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1600,"height":672},device_scale_factor=1)
        page.route("**/*",lambda route:route.abort())
        for source in outputs:
            page.set_content('<html><body style="margin:0">'+source.read_text()+'</body></html>')
            page.screenshot(path=str(source.with_suffix('.png')))
        browser.close()
    print(json.dumps([str(p) for p in outputs]))


if __name__=="__main__":main()
