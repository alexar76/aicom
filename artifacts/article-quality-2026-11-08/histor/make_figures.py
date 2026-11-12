"""Figures from measured local fixture outcomes and the label state model."""
from html import escape
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT.parent/'PromoMaterials/devto/histor-missing-digest-2026-11-07/assets-v2'


def t(x,y,s,n=29,c='#23352f',weight=400):
    return f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{n}" font-weight="{weight}" fill="{c}">{escape(s)}</text>'


def r(x,y,w,h,c,stroke='none',radius=10):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{c}" stroke="{stroke}"/>'


def line(d,c='#7d8f82'):
    return f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3"/>'


def doc(w,h,title,body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img"><title>{escape(title)}</title>{r(0,0,w,h,"#fbfaf5",radius=0)}{body}</svg>'


def matrix():
    rows=json.loads((HERE/'fixture-results.json').read_text())['rows']
    s=t(48,65,'The same inputs under two MTL revisions',38,weight=700)
    s+=t(48,109,'Eight local fixtures, not a production survey',27,'#68796b')
    s+=r(40,143,1120,67,'#e8eddf')+t(63,187,'Input',29,weight=700)+t(673,187,'MTL 1.0',29,weight=700)+t(927,187,'MTL 1.1',29,weight=700)
    for i,row in enumerate(rows):
        y=222+i*70
        s+=r(40,y,1120,62,'#f0f0e8' if i%2==0 else '#fbfaf5',radius=2)
        s+=t(62,y+42,row['fixture'],29)
        for x,rev in ((675,'1.0'),(929,'1.1')):
            ok=row[rev]['status']=='digested';s+=t(x,y+42,'DIGEST' if ok else 'declined',29,'#2d7455' if ok else '#9d4e36',700)
    s+=t(48,824,'1.2 keeps the 1.1 digest calculation and records revision / reason.',27,'#4b6153')
    return doc(1200,862,'MTL digest eligibility on eight offline fixtures',s)


def states():
    s=t(46,64,'Where an absent digest comes from',38,weight=700)
    s+=r(45,135,285,115,'#e5e9dc')+t(73,181,'tools/list',34,weight=700)+t(73,221,'read attempt',27,'#63735d')
    s+=line('M 330 192 H 542')+t(370,166,'failed',27,'#925b40')
    s+=r(558,117,492,140,'#f1e0d8')+t(584,164,'not_observed',34,'#894e35',700)+t(584,210,'no tool set read',29,'#70574b')
    s+=line('M 187 250 V 355')+t(211,310,'read OK',27,'#3e6d4f')
    s+=r(45,373,285,115,'#e5e9dc')+t(73,419,'Apply profile',31,weight=700)+t(73,459,'versioned rules',26,'#63735d')
    s+=line('M 330 430 H 428 V 385 H 542')+t(362,353,'declined',26,'#925b40')
    s+=r(558,319,492,147,'#f4e9ce')+t(584,365,'not_digestible',34,'#865e23',700)+t(584,410,'code + revision',29,'#74603e')
    s+=line('M 428 430 V 596 H 542')+t(338,554,'accepted',26,'#3e6d4f')
    s+=r(558,530,492,134,'#dfeee1')+t(584,578,'tool-set digest',34,'#2f6b48',700)+t(584,621,'canonical bytes → SHA-256',27,'#476952')
    s+=t(46,727,'A successfully read empty list is observed and digestible.',27,'#4b6153')
    return doc(1100,768,'Read failure and profile refusal are distinct states',s)


OUT.mkdir(exist_ok=True)
outputs=[]
for name,source in (('histor-digest-fixtures',matrix()),('histor-observation-states',states())):
    file=OUT/(name+'.svg');file.write_text(source);outputs.append(file)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(device_scale_factor=1)
    page.route('**/*',lambda route:route.abort())
    for file in outputs:
        source=file.read_text();import re
        w,h=map(int,re.search(r'width="(\d+)" height="(\d+)"',source).groups())
        page.set_viewport_size({'width':w,'height':h})
        page.set_content('<html><body style="margin:0">'+source+'</body></html>')
        page.screenshot(path=str(file.with_suffix('.png')))
    browser.close()
print(json.dumps([str(p) for p in outputs]))
