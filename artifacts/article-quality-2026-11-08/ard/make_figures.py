#!/usr/bin/env python3
"""Generate native SVG and matching antialiased PNG explanatory figures.

Pillow rasterization uses the same primitives as the SVG. No external assets,
image generator, screenshot, browser or network request is involved.
"""
from html import escape
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PACK = Path('/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/devto/ard-six-hubs-2026-11-07/assets-v2')
SCALE = 2
BG = '#f5f6f8'
INK = '#14283f'
MUTED = '#516579'
BLUE = '#195fc4'
LINE = '#b8c6d5'
ORANGE = '#a94b08'
RED = '#a51d35'
GREEN = '#17644d'
FONT = '/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'


class Canvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.image = Image.new('RGB', (width*SCALE, height*SCALE), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
                      f'<rect width="{width}" height="{height}" fill="{BG}"/>']
        self.text_bounds = []

    def rect(self, x, y, w, h, fill='white', stroke=LINE, radius=14):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        self.draw.rounded_rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE),radius=radius*SCALE,fill=fill,outline=stroke,width=2*SCALE)

    def text(self, x, y, value, size=28, color=INK, bold=False, mono=False):
        # y is the top edge, not the baseline; SVG hanging alignment and Pillow lt agree.
        font = ImageFont.truetype(MONO if mono else BOLD if bold else FONT, size*SCALE)
        bounds = self.draw.textbbox((x*SCALE, y*SCALE), value, font=font, anchor='lt')
        assert bounds[0] >= 0 and bounds[1] >= 0 and bounds[2] <= self.width*SCALE and bounds[3] <= self.height*SCALE, (value,bounds)
        self.text_bounds.append({'text':value,'x':x,'y':y,'size':size,'bounds':[v/SCALE for v in bounds]})
        self.draw.text((x*SCALE,y*SCALE),value,font=font,fill=color,anchor='lt')
        family = 'Menlo, monospace' if mono else 'Arial, sans-serif'
        self.parts.append(f'<text x="{x}" y="{y}" dominant-baseline="hanging" font-family="{family}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}">{escape(value)}</text>')

    def line(self, x1,y1,x2,y2,color=LINE,width=3,dashed=False):
        dash = ' stroke-dasharray="10 10"' if dashed else ''
        self.parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"{dash}/>')
        if dashed:
            if y1 == y2:
                for x in range(int(x1),int(x2),20):
                    self.draw.line((x*SCALE,y1*SCALE,min(x+10,x2)*SCALE,y2*SCALE),fill=color,width=width*SCALE)
            else:
                raise ValueError('Only horizontal dashed lines are used')
        else:
            self.draw.line((x1*SCALE,y1*SCALE,x2*SCALE,y2*SCALE),fill=color,width=width*SCALE)

    def arrow(self, x1,y1,x2,y2,color=BLUE):
        self.line(x1,y1,x2,y2,color,4)
        if y1 == y2:
            pts=[(x2,y2),(x2-14,y2-9),(x2-14,y2+9)]
        elif x1 == x2:
            pts=[(x2,y2),(x2-9,y2-14),(x2+9,y2-14)]
        else:
            raise ValueError('Only axis-aligned arrows are used')
        self.parts.append(f'<polygon points="'+ ' '.join(f'{x},{y}' for x,y in pts)+f'" fill="{color}"/>')
        self.draw.polygon([(x*SCALE,y*SCALE) for x,y in pts],fill=color)

    def save(self, name):
        PACK.mkdir(parents=True,exist_ok=True)
        (PACK/f'{name}.svg').write_text('\n'.join(self.parts)+ '\n</svg>\n')
        self.image.resize((self.width,self.height),Image.Resampling.LANCZOS).save(PACK/f'{name}.png')
        (HERE/f'{name}-text-bounds.json').write_text(json.dumps(self.text_bounds,indent=2)+'\n')


def discovery():
    c=Canvas(1600,1000)
    c.text(60,48,'From a domain to a call',46,bold=True)
    c.text(60,112,'The walkthrough follows catalog documents; execution starts at a separate endpoint.',28,color=MUTED)
    boxes=[(60,220,220,390),(340,220,340,390),(740,220,340,390),(1140,220,400,390)]
    for box in boxes:c.rect(*box)
    for x in [290,690,1090]:c.arrow(x,400,x+40,400)
    c.text(80,246,'ORIGIN',28,color=BLUE,bold=True)
    c.text(80,316,'HTTPS origin',26)
    c.text(80,390,'Starting point',26)
    c.text(80,432,'for discovery',26)

    c.text(366,246,'MANIFEST',28,color=BLUE,bold=True)
    c.text(366,306,'GET',28,bold=True)
    c.text(366,352,'/.well-known/',26,mono=True)
    c.text(366,390,'ard.json',26,mono=True)
    c.text(366,456,'Registry entry:',28)
    c.text(366,502,'application/',26,mono=True)
    c.text(366,540,'ai-registry+json',26,mono=True)

    c.text(766,246,'REGISTRY',28,color=BLUE,bold=True)
    c.text(766,306,'POST',28,bold=True)
    c.text(766,352,'/ard/v1/search',26,mono=True)
    c.text(766,414,'query.text + pageSize',26)
    c.text(766,474,'Result gives:',28)
    c.text(766,518,'url, source, digest',26,mono=True)
    c.text(766,558,'and signed subject*',26)

    c.text(1166,246,'DESCRIPTOR',28,color=BLUE,bold=True)
    c.text(1166,306,'GET result.url',28,mono=True)
    c.text(1166,378,'Input / output schemas',28)
    c.text(1166,428,'Prices and access mode',28)
    c.text(1166,478,'invoke.method / url',26,mono=True)
    c.text(1166,522,'invoke.body + input',26,mono=True)
    c.text(60,642,'* Own published entries are signed on the five domain-root hubs; peer rows are hints.',26,color=MUTED)

    c.line(60,718,1540,718,color=ORANGE,dashed=True)
    c.text(60,748,'DISCOVERY ABOVE · EXECUTION BELOW',27,color=ORANGE,bold=True)
    c.arrow(1340,610,1340,820,color=ORANGE)
    c.rect(1110,820,430,130,fill='#fff4e9',stroke=ORANGE)
    c.text(1136,842,'POST',28,color=ORANGE,bold=True)
    c.text(1136,892,'/ai-market/v2/invoke',26,mono=True)
    c.text(60,822,'curl stops at the descriptor.',32,bold=True)
    c.text(60,880,'Calling and paying still use AIMarket v2.',28,color=MUTED)
    c.save('ard-discovery-boundary')


def binding():
    c=Canvas(1600,1050)
    c.text(60,48,'Where verification broke',46,bold=True)
    c.text(60,112,'Controlled reproduction: remove only version from the outer search result.',28,color=MUTED)
    # A field-by-field representation avoids an unreadably wide JSON listing.
    c.rect(60,182,1480,390)
    c.rect(60,182,1480,72,fill='#e7edf5',radius=12)
    c.text(84,205,'COORDINATE',27,bold=True)
    c.text(386,205,'SIGNED SUBJECT',27,bold=True)
    c.text(990,205,'OUTER SEARCH RESULT',27,bold=True)
    for y in [254,334,414,494]:c.line(60,y,1540,y,width=2)
    c.line(356,182,356,572,width=2)
    c.line(960,182,960,572,width=2)
    rows=[('identifier','<same resource URN>','<same resource URN>'),
          ('type','<same media type>','<same media type>'),
          ('version','"v1"','FIELD OMITTED'),
          ('digest','sha256:<same digest>','sha256:<same digest>')]
    for i,(label,left,right) in enumerate(rows):
        y=278+i*80
        if label=='version':
            c.rect(962,y-18,576,77,fill='#ffe9ee',stroke='#ffe9ee',radius=0)
        c.text(84,y,label,28,mono=True)
        c.text(386,y,left,28,mono=True)
        c.text(990,y,right,28,mono=True,color=RED if label=='version' else INK,bold=label=='version')
    c.text(60,594,'The values are abbreviated; the missing field is the only change.',26,color=MUTED)
    c.rect(60,650,1480,120,fill='#eaf0f8',stroke=BLUE)
    c.text(88,673,'subject == coordinates(search_result)',32,mono=True)
    c.text(88,722,'Fails because version appears on only one side.',28,color=RED,bold=True)
    cards=[(60,'JWS SIGNATURE','still valid',GREEN),(564,'SUBJECT BINDING','FAILS',RED),(1068,'DESCRIPTOR DIGEST','still matches',GREEN)]
    for x,label,status,color in cards:
        c.rect(x,814,472,120,fill='white',stroke=color)
        c.text(x+24,836,label,26,bold=True)
        c.text(x+24,881,status,30,color=color,bold=True)
    c.text(60,980,'Fix: keep version in the result and compare every signed coordinate.',28,bold=True)
    c.save('ard-subject-binding')


if __name__=='__main__':
    discovery()
    binding()
    print(PACK)
