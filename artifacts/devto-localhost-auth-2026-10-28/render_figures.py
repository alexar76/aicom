"""Render exact editorial diagrams from the local demonstration evidence."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = Path('/private/tmp/devto-localhost-auth-2026-10-28/assets')
OUT.mkdir(parents=True, exist_ok=True)
INK, MUTED, PAPER, LINE = '#252a2c', '#62696b', '#f4f0e8', '#d4d0c8'
AMBER, BLUE = '#a85b16', '#365b6e'
REG = '/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'

def font(size, bold=False, mono=False):
    return ImageFont.truetype(MONO if mono else BOLD if bold else REG, size)

def text(d, xy, value, size=32, fill=INK, bold=False, mono=False):
    d.text(xy, value, font=font(size, bold, mono), fill=fill)

def arrow(d, points, fill=INK, width=7):
    d.line(points, fill=fill, width=width, joint='curve')
    x,y=points[-1];px,py=points[-2]
    if x>px: tri=[(x,y),(x-19,y-12),(x-19,y+12)]
    elif x<px:tri=[(x,y),(x+19,y-12),(x+19,y+12)]
    elif y>py:tri=[(x,y),(x-12,y-19),(x+12,y-19)]
    else:tri=[(x,y),(x-12,y+19),(x+12,y+19)]
    d.polygon(tri, fill=fill)

def node(d, box, title, note, fill='white'):
    d.rounded_rectangle(box, radius=20, fill=fill, outline=LINE, width=2)
    x,y,_,_=box
    text(d,(x+26,y+25),title,34,bold=True)
    text(d,(x+26,y+80),note,27,fill=MUTED)

im=Image.new('RGB',(1800,960),PAPER);d=ImageDraw.Draw(im)
text(d,(80,53),'LOCAL HTTP / AUTHORIZATION',25,fill=MUTED,bold=True)
text(d,(80,105),'The backend sees the final hop',56,bold=True)
text(d,(80,183),'A relay creates its own connection to a loopback service.',33,fill=MUTED)
d.rounded_rectangle((620,268,1720,806),radius=28,fill='#faf8f4',outline=LINE,width=3)
text(d,(650,282),'SERVER MACHINE',22,fill=MUTED,bold=True)
node(d,(690,349,1105,497),'Local client','Direct connection')
node(d,(690,594,1105,742),'Local relay','May receive outside traffic',fill='#fff0dc')
node(d,(1320,455,1665,644),'Backend','Loopback listener')
node(d,(80,594,440,742),'Outside caller','Upstream request')
arrow(d,[(440,670),(690,670)],AMBER)
arrow(d,[(1105,423),(1210,423),(1210,493),(1320,493)],BLUE)
arrow(d,[(1105,670),(1210,670),(1210,604),(1320,604)],AMBER)
text(d,(1120,366),'127.0.0.1',26,fill=BLUE,mono=True)
text(d,(1120,702),'127.0.0.1',26,fill=AMBER,mono=True)
text(d,(1350,574),'same peer IP',26,fill=MUTED)
text(d,(80,848),'The forwarding process owns the new socket.',32,bold=True)
text(d,(80,899),'Conceptual deployment. The executable reconstruction uses loopback for every client and listener.',25,fill=MUTED)
im.save(OUT/'02-last-hop.png',optimize=True)

evidence=json.loads((ROOT/'demo-result.json').read_text())
rows=evidence['results'];assert len(rows)==8
im=Image.new('RGB',(1800,1150),PAPER);d=ImageDraw.Draw(im)
text(d,(80,51),'LOCAL RECONSTRUCTION / 8 REQUESTS',25,fill=MUTED,bold=True)
text(d,(80,105),'One peer address. Different decisions.',54,bold=True)
text(d,(80,182),'The credential requirement decides which requests are accepted.',33,fill=MUTED)
d.rounded_rectangle((80,261,1720,956),radius=18,fill='white',outline=LINE,width=2)
d.rounded_rectangle((80,261,1720,337),radius=18,fill=INK)
d.rectangle((80,310,1720,337),fill=INK)
cols=[110,460,1050,1285]
for x,label in zip(cols,['GATE','REQUEST PATH','HTTP','BACKEND PEER']):
    text(d,(x,285),label,24,fill='white',bold=True)
for i,row in enumerate(rows):
    y=337+i*76
    if i%2==1:d.rectangle((82,y,1718,y+76),fill='#f9f7f3')
    if i==2:d.line((82,y,1718,y),fill=LINE,width=3)
    status=row['status'];pill='#fff0dc' if status==200 else '#e7eef1'
    color=AMBER if status==200 else BLUE
    text(d,(cols[0],y+24),row['gate'],28,bold=True)
    text(d,(cols[1],y+24),row['path'],28)
    d.rounded_rectangle((cols[2]-7,y+13,cols[2]+112,y+63),radius=10,fill=pill)
    text(d,(cols[2]+10,y+20),str(status),29,fill=color,bold=True)
    text(d,(cols[3],y+24),row['backend_peer'],27,mono=True)
text(d,(80,992),'All listeners: 127.0.0.1   |   Fixed relay target   |   In-memory test key',28,fill=MUTED)
text(d,(80,1040),'The relay forwards a client-supplied key. It never adds a backend key of its own.',27,fill=MUTED)
text(d,(80,1088),'Teaching HTTP example; no MCP package or public deployment was tested.',27,fill=MUTED)
im.save(OUT/'03-demo-results.png',optimize=True)
print('Rendered two figures from the saved 8-request result.')
