from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import ast, os, math, random
ROOT='/mnt/data/vldst_full'
SRC='/mnt/data/a_highly_detailed_promotional_poster_game_ui_con.png'
OUT_CASE=os.path.join(ROOT,'frontend/public/assets/cases')
OUT_ITEM=os.path.join(ROOT,'frontend/public/assets/items')
os.makedirs(OUT_CASE,exist_ok=True); os.makedirs(OUT_ITEM,exist_ok=True)

# Read catalog
src=open(os.path.join(ROOT,'backend/app/game_data.py'),encoding='utf-8').read()
mod=ast.parse(src); vals={}
for n in mod.body:
    if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name):
        try: vals[n.targets[0].id]=ast.literal_eval(n.value)
        except: pass
cases=vals['CASES']

# Source poster crops: 5 top + 5 bottom cases.
poster=Image.open(SRC).convert('RGB')
case_boxes=[(10,120,310,385),(315,120,615,385),(620,120,920,385),(925,120,1225,385),(1230,120,1530,385),
           (10,380,310,640),(315,380,615,640),(620,380,920,640),(925,380,1225,640),(1230,380,1530,640)]
source_theme=['inferno','neon','cyber','ice','toxic','void','gold','shadow','storm','dragon']
case_source={t:poster.crop(b) for t,b in zip(source_theme,case_boxes)}

# Theme palettes
pal={
 'bronze':('#b86b2d','#5a2c12'), 'silver':('#d9e7f2','#607487'), 'gold':('#ffd34a','#6a3d00'),
 'diamond':('#8be9ff','#145d86'), 'royal':('#d8a8ff','#4b1e77'), 'galaxy':('#8d6cff','#24104d'),
 'cyber':('#20e8ff','#064b64'), 'inferno':('#ff5a19','#641300'), 'shadow':('#a7b0bd','#12151b'),
 'dragon':('#ff3c2e','#4a0705')}
rarity={
 'COMMON':('#aab0b8','#20242a'), 'UNCOMMON':('#70d7a5','#0c3324'), 'RARE':('#2bb9ff','#082b55'),
 'EPIC':('#cf5cff','#35105b'), 'LEGENDARY':('#ffca32','#5b3500'), 'MYTHIC':('#ff3f36','#5a0808')}

font_b='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
font_r='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

def fit_font(text, maxw, start, path=font_b):
    size=start
    while size>12:
        f=ImageFont.truetype(path,size)
        if f.getbbox(text)[2]-f.getbbox(text)[0] <= maxw: return f
        size-=1
    return ImageFont.truetype(path,12)

def hexrgb(h): return tuple(int(h[i:i+2],16) for i in (1,3,5))

def glow_line(base, xy, fill, width=3, blur=10):
    layer=Image.new('RGBA',base.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
    d.line(xy,fill=hexrgb(fill)+(150,),width=width)
    gl=layer.filter(ImageFilter.GaussianBlur(blur)); base.alpha_composite(gl); base.alpha_composite(layer)

def make_case(c, idx):
    theme=c['theme']; name=c['name']
    im=case_source[source_theme[idx]].resize((900,650),Image.Resampling.LANCZOS)
    # map non-generated themes to closest generated visual while recoloring border.
    tint, dark=pal[theme]
    overlay=Image.new('RGBA',im.size,hexrgb(dark)+(70,)); im=Image.alpha_composite(im.convert('RGBA'),overlay)
    d=ImageDraw.Draw(im)
    # actual title plate to ensure correct catalog name
    d.rounded_rectangle((28,24,872,96),radius=18,fill=(8,10,15,210),outline=hexrgb(tint)+(230,),width=3)
    f=fit_font(name,790,38)
    bb=d.textbbox((0,0),name,font=f); tw=bb[2]-bb[0]
    d.text(((900-tw)//2,37),name,font=f,fill=hexrgb(tint)+(255,),stroke_width=1,stroke_fill=(0,0,0,255))
    # VLDST badge
    d.rounded_rectangle((36,560,260,620),radius=14,fill=(8,10,15,225),outline=hexrgb(tint)+(200,),width=2)
    d.text((55,575),'VLDST CASE X',font=ImageFont.truetype(font_b,20),fill=(240,245,250,255))
    return im.convert('RGB')

for i,c in enumerate(cases):
    img=make_case(c,i)
    img.save(os.path.join(OUT_CASE,c['case_code']+'.png'),quality=95)

# Preserve fallback theme filenames by aliasing the closest new case visuals.
for c in cases:
    theme=c['theme']; src=os.path.join(OUT_CASE,c['case_code']+'.png')
    fallback=os.path.join(OUT_CASE,theme+'.png')
    Image.open(src).save(fallback,quality=95)

# Crop 12 source item renders from the poster's item strip.
# centers approximately across x; all are in y=675..895.
centers=[72,210,348,485,623,760,898,1035,1173,1310,1448]
item_src={}
for i,x in enumerate(centers):
    box=(max(0,x-63),675,min(1536,x+63),895)
    item_src[i]=poster.crop(box).resize((512,512),Image.Resampling.LANCZOS)

# Category -> source index
cat_map={'blade':0,'weapon':1,'agent':2,'gloves':10,'crown':4,'dragon':5,'core':8,'shield':9,'crystal':8,'coin':10,'chip':10,'gear':6,'bolt':7,'token':10,'ring':4,'scepter':4,'heart':8,'scale':5,'hammer':4,'phoenix':5,'default':10}

def cat(name):
    n=name.lower()
    for k in ['blade','knife','bowe','saber','dagger','karambit','scepter','crown','dragon','agent','gloves','shield','core','crystal','coin','chip','gear','bolt','token','ring','hammer','heart','scale','phoenix']:
        if k in n: return k
    if any(k in n for k in ['phantom','rifle','pistol','smg','m4','awp','glock','mp7','ak','sniper','deagle','famas','scar']): return 'weapon'
    return 'default'

# Render each item as a polished 512x512 card using generated source art + theme/rarity treatment.
for ci,c in enumerate(cases):
    tint,tdark=pal[c['theme']]
    for j,it in enumerate(c['items']):
        rcol,rdark=rarity[it['rarity']]
        base=Image.new('RGBA',(512,512),(6,8,12,255))
        # subtle radial-like bands
        bg=Image.new('RGBA',(512,512),(0,0,0,0)); bd=ImageDraw.Draw(bg)
        for rr in range(360,20,-18):
            alpha=max(0,int(80*(1-rr/380)))
            bd.ellipse((256-rr,256-rr,256+rr,256+rr),fill=hexrgb(tdark)+(alpha,))
        base=Image.alpha_composite(base,bg)
        # source render
        si=cat_map.get(cat(it['name']),cat_map['default'])
        # rotate source selection by deterministic offset to avoid repetition
        src=item_src[si].copy()
        if (ci+j)%3==1: src=ImageEnhance.Contrast(src).enhance(1.08)
        # colorize slightly toward theme
        tint_layer=Image.new('RGBA',src.size,hexrgb(tint)+(45,)); src=Image.alpha_composite(src.convert('RGBA'),tint_layer)
        # fit within central panel
        src.thumbnail((400,330),Image.Resampling.LANCZOS)
        sx=(512-src.width)//2; sy=88
        base.alpha_composite(src,(sx,sy))
        # glow border
        d=ImageDraw.Draw(base)
        d.rounded_rectangle((10,10,502,502),radius=26,outline=hexrgb(rcol)+(230,),width=4)
        d.rounded_rectangle((20,20,492,492),radius=20,outline=hexrgb(tint)+(100,),width=2)
        # rarity chip
        d.rounded_rectangle((28,28,205,72),radius=12,fill=hexrgb(rdark)+(220,),outline=hexrgb(rcol)+(240,),width=2)
        rf=fit_font(it['rarity'],155,22)
        d.text((42,39),it['rarity'],font=rf,fill=hexrgb(rcol)+(255,))
        # item name plate
        d.rounded_rectangle((28,422,484,486),radius=14,fill=(4,6,10,225),outline=hexrgb(tint)+(190,),width=2)
        nf=fit_font(it['name'],420,25,font_r)
        bb=d.textbbox((0,0),it['name'],font=nf); tw=bb[2]-bb[0]
        d.text(((512-tw)//2,438),it['name'],font=nf,fill=(242,245,248,255))
        # tiny VLDST code
        cf=ImageFont.truetype(font_r,14)
        d.text((32,486),it['item_code'],font=cf,fill=(155,165,178,255))
        # theme dot
        d.ellipse((466,482,490,506),fill=hexrgb(tint)+(255,),outline=(255,255,255,160),width=1)
        base.convert('RGB').save(os.path.join(OUT_ITEM,it['item_code']+'.png'),quality=94)

# Visual metadata / color map for future UI use
meta=os.path.join(ROOT,'frontend/public/assets','visual_theme_map.json')
import json
json.dump({'themes':{k:{'primary':v[0],'dark':v[1]} for k,v in pal.items()},'rarities':{k:{'primary':v[0],'dark':v[1]} for k,v in rarity.items()}},open(meta,'w'),ensure_ascii=False,indent=2)
print('generated',len(cases),'cases and',sum(len(c['items']) for c in cases),'items')
