from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
import hashlib, math

ROOT=Path(__file__).resolve().parents[1]
CASES={
'BR':('bronze','#a86b32','#ffd08a'), 'SI':('silver','#73839a','#e7f1ff'),
'GO':('gold','#b37a19','#ffe08a'), 'DI':('diamond','#35bfe8','#d9fbff'),
'RO':('royal','#7b4bd4','#f1d7ff'), 'GA':('galaxy','#4d5ce8','#bcd1ff'),
'CY':('cyber','#0fb6a0','#7dfff0'), 'IN':('inferno','#e34b24','#ffb05e'),
'SH':('shadow','#4a3d6f','#cbbcff'), 'DR':('dragon','#a32636','#ffb46a')}
RARITY={'001':('COMMON','#c8d0dc'),'002':('COMMON','#c8d0dc'),'003':('UNCOMMON','#43e0a2'),'004':('UNCOMMON','#43e0a2'),'005':('RARE','#55b3ff'),'006':('RARE','#55b3ff'),'007':('EPIC','#b789ff'),'008':('LEGENDARY','#ff9a3d'),'009':('MYTHIC','#ff6680')}

try: font_big=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',44); font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',22); font_sm=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',15)
except: font_big=font=font_sm=None

def hexrgb(h): return tuple(int(h[i:i+2],16) for i in (1,3,5))
def lerp(a,b,t): return tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
def bg(size,c1,c2,seed):
    a=np.array(hexrgb(c1),dtype=float); b=np.array(hexrgb(c2),dtype=float)
    yy,xx=np.mgrid[0:size,0:size]; t=(xx+yy)/(2*(size-1)); noise=((xx*17+yy*31+seed*13)%37)/37*.10
    arr=a[None,None,:]*(1-t[...,None])+b[None,None,:]*t[...,None]
    arr=np.clip(arr*(.9+noise[...,None]),0,255).astype('uint8')
    return Image.fromarray(arr,'RGB')

def glow(im, center, radius, color, strength=0.65):
    layer=Image.new('RGBA',im.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
    x,y=center
    for r in range(radius,0,-8):
        alpha=int(255*strength*(1-r/radius)**1.5)
        d.ellipse((x-r,y-r,x+r,y+r),fill=(*hexrgb(color),alpha))
    return Image.alpha_composite(im.convert('RGBA'),layer)

def label(draw,text,y,fill=(255,255,255,230)):
    box=draw.textbbox((0,0),text,font=font_sm); w=box[2]-box[0]
    draw.text(((512-w)/2,y),text,font=font_sm,fill=fill)

def make_case(code,name,c1,c2):
    im=bg(512,c1,c2,int(hashlib.md5(code.encode()).hexdigest()[:6],16)); im=glow(im,(256,210),190,c2,.9)
    d=ImageDraw.Draw(im)
    # rings
    for r in (170,140,110): d.ellipse((256-r,210-r,256+r,210+r),outline=(*hexrgb(c2),75),width=3)
    # central case cube
    poly=[(145,165),(256,125),(367,165),(367,340),(256,390),(145,340)]
    d.polygon(poly,fill=(*hexrgb(c1),235),outline=(*hexrgb(c2),255),width=5)
    d.line((256,125,256,390),fill=(*hexrgb(c2),180),width=3)
    d.line((145,165,256,210,367,165),fill=(*hexrgb(c2),160),width=3)
    d.polygon([(176,190),(256,165),(336,190),(256,218)],fill=(*hexrgb(c2),80))
    d.text((256,245),'V',font=font_big,anchor='mm',fill=(*hexrgb(c2),255),stroke_width=2,stroke_fill=(0,0,0,100))
    label(d,name,408,(*hexrgb(c2),255))
    im.convert('RGB').save(ROOT/'frontend/public/assets/cases'/f'VLDST-{code}.png',quality=94)

def make_item(code,name,c1,c2,rarity,idx):
    im=bg(512,c1,'#070b12',idx*19); im=glow(im,(256,235),170,rarity,.85)
    d=ImageDraw.Draw(im)
    rc=hexrgb(rarity)
    # unique symbol by index
    cx,cy=256,235
    if idx in (1,2):
      d.ellipse((155,135,357,337),fill=(*hexrgb(c1),180),outline=(*rc,255),width=8)
      d.ellipse((195,175,317,297),fill=(8,12,20),outline=(*rc,180),width=4)
      d.text((256,236),str(idx),font=font_big,anchor='mm',fill=(*rc,255))
    elif idx in (3,4):
      d.rounded_rectangle((145,145,367,325),radius=35,fill=(*hexrgb(c1),210),outline=(*rc,255),width=7)
      for k in range(3): d.line((185+k*55,180,185+k*55,290),fill=(*rc,120),width=5)
      d.text((256,235),'GEAR',font=font,anchor='mm',fill=(*rc,255))
    elif idx in (5,6):
      pts=[]
      for k in range(8):
        a=math.radians(45*k-22.5); r=110 if k%2==0 else 55; pts.append((cx+math.cos(a)*r,cy+math.sin(a)*r))
      d.polygon(pts,fill=(*hexrgb(c1),190),outline=(*rc,255)); d.ellipse((225,204,287,266),fill=(*rc,230))
      d.text((256,305),str(idx),font=font,anchor='mm',fill=(*rc,255))
    elif idx==7:
      d.regular_polygon((cx,cy,120),6,rotation=30,fill=(*hexrgb(c1),210),outline=(*rc,255),width=7)
      d.regular_polygon((cx,cy,70),6,rotation=30,fill=(9,12,20),outline=(*rc,200),width=4)
      d.text((256,235),'X',font=font_big,anchor='mm',fill=(*rc,255))
    elif idx==8:
      d.polygon([(256,120),(285,205),(375,205),(304,258),(330,345),(256,292),(182,345),(208,258),(137,205),(227,205)],fill=(*rc,230),outline=(255,255,255,190))
    else:
      # crown/core
      d.ellipse((145,130,367,352),fill=(*hexrgb(c1),160),outline=(*rc,255),width=8)
      d.polygon([(170,260),(200,170),(256,235),(312,170),(342,260),(256,335)],fill=(*rc,190),outline=(255,255,255,150))
      d.ellipse((225,204,287,266),fill=(8,10,18),outline=(255,255,255,180),width=4)
    # top rarity strip and bottom name
    d.rounded_rectangle((24,22,488,62),radius=18,fill=(5,8,14,190),outline=(*rc,150),width=2)
    label(d,rarity,29,(*rc,255))
    # shorten long names visually
    shown=name if len(name)<=23 else name[:21]+'…'
    d.text((256,445),shown,font=font_sm,anchor='mm',fill=(240,244,250,240))
    im.convert('RGB').save(ROOT/'frontend/public/assets/items'/f'{code}.png',quality=94)

# parse game_data safely without importing app deps
text=(ROOT/'backend/app/game_data.py').read_text()
import ast
m=ast.literal_eval(text.split('CASES=',1)[1])
for c in m:
    code=c['case_code'].split('-')[1]
    make_case(code,c['name'],CASES[code][1],CASES[code][2])
    for it in c['items']:
        idx=int(it['item_code'][-3:]); rarity_color=RARITY[it['item_code'][-3:]][1]
        make_item(it['item_code'],it['name'],CASES[code][1],CASES[code][2],rarity_color,idx)
print('Generated 10 case + 90 item original assets')
