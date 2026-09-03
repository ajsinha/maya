"""Five logo directions for MAYA, rendered for comparison."""
import math
from PIL import Image, ImageDraw, ImageFont

CRIMSON=(0xA5,0x1C,0x30); INK=(0x1C,0x1C,0x1E); WHITE=(255,255,255); MUTED=(0x7A,0x7F,0x87)
FAINT=(255,255,255,120)
S=4
SANS="/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
SANSB="/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"

def canvas(size, bg=CRIMSON, r=0.203):
    n=size*S
    img=Image.new("RGBA",(n,n),(0,0,0,0)); d=ImageDraw.Draw(img,"RGBA")
    if bg: d.rounded_rectangle([0,0,n-1,n-1],radius=int(n*r),fill=bg)
    return img,d,n/512.0

def poly_pts(cx,cy,r,n,rot=0):
    return [(cx+r*math.cos(rot+2*math.pi*i/n), cy+r*math.sin(rot+2*math.pi*i/n)) for i in range(n)]

# ---------------------------------------------------------------- 1 INSCRIBED
def inscribed(size):
    img,d,u=canvas(size)
    P=lambda x,y:(x*u,y*u)
    R=152
    d.ellipse([P(256-R,256-R),P(256+R,256+R)],outline=FAINT,width=int(11*u))
    v=poly_pts(256,256,R,4,rot=-math.pi/2)
    d.line([P(*p) for p in v]+[P(*v[0])],fill=WHITE,width=int(32*u),joint="curve")
    for p in v:
        d.ellipse([P(p[0]-17,p[1]-17),P(p[0]+17,p[1]+17)],fill=WHITE)
    return img.resize((size,size),Image.LANCZOS)

# ---------------------------------------------------------------- 2 STEPWISE
def stepwise(size):
    img,d,u=canvas(size)
    P=lambda x,y:(x*u,y*u)
    curve=[(110+i*(300/60), 380-260*((i/60)**1.35)) for i in range(61)]
    d.line([P(*p) for p in curve],fill=FAINT,width=int(11*u),joint="curve")
    steps=[(110,380),(182,380),(182,306),(254,306),(254,226),(326,226),(326,132),(400,132)]
    d.line([P(*p) for p in steps],fill=WHITE,width=int(30*u),joint="curve")
    return img.resize((size,size),Image.LANCZOS)

# ---------------------------------------------------------------- 3 VEIL
def veil(size):
    img,d,u=canvas(size)
    P=lambda x,y:(x*u,y*u)
    d.rounded_rectangle([P(108,108),P(360,360)],radius=int(42*u),outline=FAINT,width=int(24*u))
    d.rounded_rectangle([P(152,152),P(404,404)],radius=int(42*u),outline=WHITE,width=int(32*u))
    return img.resize((size,size),Image.LANCZOS)

# ---------------------------------------------------------------- 4 MONOGRAM
def monogram(size):
    img,d,u=canvas(size)
    P=lambda x,y:(x*u,y*u)
    pts=[(118,392),(118,142),(256,300),(394,142),(394,392)]
    d.line([P(*p) for p in pts],fill=WHITE,width=int(36*u),joint="curve")
    d.ellipse([P(256-24,300-24),P(256+24,300+24)],fill=CRIMSON)
    d.ellipse([P(256-24,300-24),P(256+24,300+24)],outline=WHITE,width=int(14*u))
    return img.resize((size,size),Image.LANCZOS)

# ---------------------------------------------------------------- 5 OFFSET
def offset(size):
    img,d,u=canvas(size)
    P=lambda x,y:(x*u,y*u)
    R=140
    d.ellipse([P(200-R,256-R),P(200+R,256+R)],outline=FAINT,width=int(14*u))
    d.arc([P(312-R,256-R),P(312+R,256+R)],start=-215,end=35,fill=WHITE,width=int(34*u))
    d.ellipse([P(312-R-18,256-18),P(312-R+18,256+18)],fill=WHITE)
    return img.resize((size,size),Image.LANCZOS)

CONCEPTS=[("1  INSCRIBED","a square inscribed in a circle —\nthe model that approximates the world",inscribed),
          ("2  STEPWISE","a stepped approximation tracking\na smooth curve",stepwise),
          ("3  VEIL","two offset frames — the appearance\nand the thing it stands for",veil),
          ("4  MONOGRAM","a geometric M whose apex is a node\nin a diagram",monogram),
          ("5  APERTURE","an arc displaced from its true circle —\nthe gap between map and territory",offset)]

W,H=1560,760
sheet=Image.new("RGB",(W,H),(250,249,247)); d=ImageDraw.Draw(sheet)
f_t=ImageFont.truetype(SANSB,20); f_d=ImageFont.truetype(SANS,15); f_s=ImageFont.truetype(SANS,13)
d.text((40,34),"MAYA — logo directions",font=ImageFont.truetype(SANSB,30),fill=INK)
d.text((40,74),"large  ·  48 px  ·  on white",font=f_d,fill=MUTED)
x=40
for title,desc,fn in CONCEPTS:
    big=fn(210); sheet.paste(big,(x,120),big)
    sm=fn(48);  sheet.paste(sm,(x,350),sm)
    lt=fn(72)
    bgw=Image.new("RGBA",(96,96),(255,255,255,255)); bgw.alpha_composite(lt,(12,12))
    sheet.paste(bgw,(x+70,332),bgw)
    d.text((x,432),title,font=f_t,fill=CRIMSON)
    for i,line in enumerate(desc.split("\n")):
        d.text((x,460+i*20),line,font=f_s,fill=INK)
    x+=296
d.text((40,560),"All five: crimson rounded square, white knockout, no gradients, legible at 20 px.",font=f_d,fill=MUTED)
d.text((40,586),"Rendered at 210 px, 48 px, and 72 px on white to test small-size legibility.",font=f_d,fill=MUTED)
sheet.save("/tmp/logo-concepts.png")
print("contact sheet written")
