#!/usr/bin/env python3
"""
Build full-wrap cover PDF for 8.5x11 64-page book, white paper, white interior.
Dimensions with bleed: W = 17.3941", H = 11.25"  @300 DPI = 5218 x 3375 px
Structure: Back cover (8.5" + bleed) + Spine (0.1441") + Front cover (8.5" + bleed) ; height with bleed top+bottom 0.125 each
Safe zones: Keep text 0.25" inside trim, gutter 0.125" from spine fold
"""
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import inch
from reportlab.lib.colors import HexColor
import os, math, pathlib, random

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "cover"
OUT_PDF = OUT_DIR / "African_Wildlife_FullWrapCover_17.394x11.25.pdf"
OUT_JPG = OUT_DIR / "FrontCover_8.5x11_300DPI.jpg"

# Dimensions inches
TRIM_W = 8.5
TRIM_H = 11.0
PAGE_COUNT = 64
SPINE_W = PAGE_COUNT * 0.002252  # white paper
BLEED = 0.125
COVER_W = (TRIM_W*2) + SPINE_W + (BLEED*2)
COVER_H = TRIM_H + (BLEED*2)
DPI = 300

print(f"Trim {TRIM_W}x{TRIM_H}, pages {PAGE_COUNT}, spine {SPINE_W:.4f}in, bleed {BLEED}")
print(f"Full cover {COVER_W:.4f} x {COVER_H:.4f} in = {int(COVER_W*DPI)} x {int(COVER_H*DPI)} px @ {DPI} DPI")

# Colors
SAFARI_GREEN = (46, 83, 57)
SAFARI_GOLD = (183, 121, 43)
EARTH_BROWN = (139, 69, 19)
SKY_TOP = (135, 206, 235)
SKY_MID = (255, 228, 181)
SAVANNA_GOLD = (244, 193, 83)
WHITE = (255,255,255)
BLACK = (0,0,0)

# Create high-res image
Wpx = int(COVER_W*DPI)
Hpx = int(COVER_H*DPI)
print(f"Canvas {Wpx}x{Hpx}")

img = Image.new("RGB", (Wpx, Hpx), WHITE)
draw = ImageDraw.Draw(img)

# Helper to load fonts
def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    # also try Liberation in assets
    candidates += ["/home/user/goals-scanner/assets/fonts/LiberationSans-Bold.ttf" if bold else "/home/user/goals-scanner/assets/fonts/LiberationSans-Regular.ttf"]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except:
            continue
    return ImageFont.load_default()

# ---- Background gradient: sky top to savanna gold bottom ----
for y in range(Hpx):
    ratio = y / Hpx
    if ratio < 0.45:
        # sky top to mid
        r = int(SKY_TOP[0]*(1-ratio/0.45) + SKY_MID[0]*(ratio/0.45))
        g = int(SKY_TOP[1]*(1-ratio/0.45) + SKY_MID[1]*(ratio/0.45))
        b = int(SKY_TOP[2]*(1-ratio/0.45) + SKY_MID[2]*(ratio/0.45))
    elif ratio < 0.58:
        r,g,b = SKY_MID
    else:
        # ground
        sub = (ratio-0.58)/0.42
        r = int(SKY_MID[0]*(1-sub) + SAVANNA_GOLD[0]*sub)
        g = int(SKY_MID[1]*(1-sub) + SAVANNA_GOLD[1]*sub)
        b = int(SKY_MID[2]*(1-sub) + SAVANNA_GOLD[2]*sub)
    draw.line([(0,y),(Wpx,y)], fill=(r,g,b))

# Define key X coordinates in pixels
# Total cover with bleed: left bleed 0.125, then back cover 8.5, spine 0.144, front 8.5, right bleed 0.125
bleed_px = int(BLEED*DPI)
spine_px = int(SPINE_W*DPI)
trim_w_px = int(TRIM_W*DPI)
back_start = bleed_px
back_end = back_start + trim_w_px
spine_start = back_end
spine_end = spine_start + spine_px
front_start = spine_end
front_end = front_start + trim_w_px
# back+spine+front = bleed + trim + spine + trim + bleed

print(f"back {back_start}-{back_end}, spine {spine_start}-{spine_end} ({spine_px}px), front {front_start}-{front_end}")

# Ground line across
ground_y = int(Hpx*0.68)
draw.rectangle([0, ground_y, Wpx, Hpx], fill=(232, 184, 92))
# ground texture lines
for i in range(0, Wpx, 80):
    draw.line([(i, ground_y),(i+18, ground_y+14)], fill=(180,140,60), width=3)
    draw.line([(i+30, ground_y+6),(i+38, ground_y+18)], fill=(200,160,70), width=2)

# Draw acacia trees silhouettes across back+front
def draw_acacia_silhouette(x, y, scale, color=SAFARI_GREEN):
    trunk_w = int(16*scale)
    trunk_h = int(210*scale)
    # trunk
    draw.line([(x, y),(x, y-trunk_h)], fill=color, width=trunk_w)
    # canopy flat
    cy = y-trunk_h
    for (ox, oy, w, h) in [(-120,-8,240,48), (-155,-28,310,42), (-100,-46,200,36)]:
        w2=int(w*scale); h2=int(h*scale); ox2=int(ox*scale); oy2=int(oy*scale)
        bbox=[x+ox2, cy+oy2, x+ox2+w2, cy+oy2+h2]
        draw.ellipse(bbox, fill=color, outline=None)

# Baobab silhouette for front
def draw_baobab_silhouette(x, y, scale, color=SAFARI_GREEN):
    trunk_w=int(58*scale)
    trunk_h=int(260*scale)
    draw.rectangle([x-trunk_w//2, y-trunk_h, x+trunk_w//2, y], fill=color, outline=None)
    cy=y-trunk_h
    for (ox,oy,r) in [(-18,-18,56),(14,-28,48),(2,-48,38)]:
        draw.ellipse([x+int(ox*scale)-int(r*scale), cy+int(oy*scale)-int(r*scale), x+int(ox*scale)+int(r*scale), cy+int(oy*scale)+int(r*scale)], fill=color)

# Place trees
draw_acacia_silhouette(back_start+120, ground_y, 0.72, SAFARI_GREEN)
draw_acacia_silhouette(back_start+420, ground_y, 0.52, (60,105,70))
draw_acacia_silhouette(front_start+420, ground_y, 0.82, SAFARI_GREEN)
draw_acacia_silhouette(front_start+820, ground_y, 0.58, (60,105,70))
draw_baobab_silhouette(front_start+trim_w_px-220, ground_y, 0.85, SAFARI_GREEN)
draw_baobab_silhouette(back_start+680, ground_y, 0.58, (60,105,70))

# Sun
sun_x = front_start + trim_w_px - 320
sun_y = int(Hpx*0.22)
sun_r = 145
draw.ellipse([sun_x-sun_r, sun_y-sun_r, sun_x+sun_r, sun_y+sun_r], fill=(255, 242, 120), outline=(255,225,80), width=5)
# sun rays
for ang in range(0,360,22):
    rad=math.radians(ang)
    x1 = sun_x + math.cos(rad)*(sun_r+10)
    y1 = sun_y + math.sin(rad)*(sun_r+10)
    x2 = sun_x + math.cos(rad)*(sun_r+38)
    y2 = sun_y + math.sin(rad)*(sun_r+38)
    draw.line([(x1,y1),(x2,y2)], fill=(255,235,100), width=4)

# Clouds - fluffy
def fluffy_cloud(cx, cy, scale, color=(255,255,255)):
    for (ox,oy,w,h) in [(-70,0,140,52),(-46,-18,96,42),(28,-10,88,40),(0,10,110,38)]:
        draw.ellipse([cx+int(ox*scale)-int(w*scale)//2, cy+int(oy*scale)-int(h*scale)//2, cx+int(ox*scale)+int(w*scale)//2, cy+int(oy*scale)+int(h*scale)//2], fill=color, outline=None)

fluffy_cloud(back_start+340, int(Hpx*0.18), 0.85)
fluffy_cloud(front_start+380, int(Hpx*0.16), 1.05)
fluffy_cloud(front_start+720, int(Hpx*0.19), 0.72)

# Animals on front cover - we will draw cute simplified animals in colour-ish flat fills (but cover is colour)
# Front cover animals: elephant, giraffe, lion, zebra, rhino small parade near ground

def draw_colour_elephant(x, y, scale, facing=1):
    s=scale
    # body
    draw.ellipse([x-int(88*s), y-int(46*s), x+int(68*s), y+int(38*s)], fill=(160,160,160), outline=SAFARI_GREEN, width=int(6*s))
    # head
    hx = x+int(58*s)
    hy = y-int(8*s)
    draw.ellipse([hx-int(38*s), hy-int(32*s), hx+int(32*s), hy+int(32*s)], fill=(160,160,160), outline=SAFARI_GREEN, width=int(5*s))
    # ear large
    ear_pts=[(hx-int(12*s), hy-int(28*s)), (hx+int(38*s), hy-int(32*s)), (hx+int(42*s), hy+int(14*s)), (hx+int(10*s), hy+int(26*s))]
    draw.polygon(ear_pts, fill=(175,175,175), outline=SAFARI_GREEN, width=int(4*s))
    # trunk
    draw.line([(hx+int(18*s), hy+int(10*s)),(hx+int(28*s), hy+int(32*s)),(hx+int(12*s), hy+int(48*s))], fill=SAFARI_GREEN, width=int(10*s), joint="round")
    # tusk
    draw.ellipse([hx-int(2*s), hy+int(6*s), hx+int(18*s), hy+int(18*s)], fill=(255,250,210), outline=SAFARI_GREEN, width=int(3*s))
    # eye
    draw.ellipse([hx-int(14*s), hy-int(10*s), hx-int(4*s), hy-int(0*s)], fill=BLACK)
    draw.ellipse([hx-int(11*s), hy-int(7*s), hx-int(7*s), hy-int(3*s)], fill=WHITE)
    # leg
    draw.rectangle([x-int(42*s), y+int(10*s), x-int(22*s), y+int(48*s)], fill=(140,140,140), outline=SAFARI_GREEN, width=int(4*s))
    draw.rectangle([x+int(8*s), y+int(10*s), x+int(28*s), y+int(48*s)], fill=(140,140,140), outline=SAFARI_GREEN, width=int(4*s))
    # tail
    draw.line([(x-int(88*s), y-int(4*s)),(x-int(108*s), y+int(10*s))], fill=SAFARI_GREEN, width=int(5*s))

def draw_colour_giraffe(x, y, scale):
    s=scale
    # body
    draw.ellipse([x-int(62*s), y-int(18*s), x+int(42*s), y+int(28*s)], fill=(255,220,110), outline=SAFARI_GREEN, width=int(6*s))
    # spots
    for (ox,oy,w,h) in [(-32,-8,18,14),(-8,6,16,12),(12,-4,14,12)]:
        draw.ellipse([x+int(ox*s), y+int(oy*s), x+int((ox+w)*s), y+int((oy+h)*s)], fill=(210,130,40), outline=None)
    # neck
    hx = x+int(32*s)
    hy = y-int(72*s)
    draw.polygon([(x+int(10*s), y-int(8*s)), (x+int(32*s), y-int(8*s)), (hx+int(8*s), hy+int(12*s)), (hx-int(8*s), hy+int(12*s))], fill=(255,220,110), outline=SAFARI_GREEN, width=int(5*s))
    # head
    draw.ellipse([hx-int(22*s), hy-int(18*s), hx+int(22*s), hy+int(16*s)], fill=(255,220,110), outline=SAFARI_GREEN, width=int(5*s))
    # ossicones
    draw.line([(hx-int(8*s), hy-int(16*s)),(hx-int(10*s), hy-int(32*s))], fill=SAFARI_GREEN, width=int(5*s))
    draw.line([(hx+int(8*s), hy-int(16*s)),(hx+int(10*s), hy-int(32*s))], fill=SAFARI_GREEN, width=int(5*s))
    draw.ellipse([hx-int(14*s)-4, hy-int(36*s), hx-int(6*s)+4, hy-int(28*s)], fill=(180,110,30), outline=SAFARI_GREEN, width=2)
    draw.ellipse([hx+int(6*s)-4, hy-int(36*s), hx+int(14*s)+4, hy-int(28*s)], fill=(180,110,30), outline=SAFARI_GREEN, width=2)
    # eye
    draw.ellipse([hx-int(4*s), hy-int(4*s), hx+int(6*s), hy+int(4*s)], fill=BLACK)
    draw.ellipse([hx-int(1*s), hy-int(1*s), hx+int(3*s), hy+int(1*s)], fill=WHITE)
    # legs
    for lx in [-28*s, -4*s, 18*s]:
        draw.line([(x+int(lx), y+int(10*s)),(x+int(lx+4*s), y+int(48*s))], fill=SAFARI_GREEN, width=int(7*s))
    # tail
    draw.line([(x-int(62*s), y+int(6*s)),(x-int(72*s), y+int(18*s))], fill=SAFARI_GREEN, width=int(5*s))
    draw.ellipse([x-int(78*s), y+int(14*s), x-int(68*s), y+int(22*s)], fill=(60,40,10), outline=None)

def draw_colour_lion(x, y, scale):
    s=scale
    # body
    draw.ellipse([x-int(72*s), y-int(22*s), x+int(58*s), y+int(26*s)], fill=(255,200,80), outline=SAFARI_GREEN, width=int(6*s))
    # head with mane
    hx = x+int(62*s)
    hy = y-int(10*s)
    # mane
    draw.ellipse([hx-int(48*s), hy-int(44*s), hx+int(48*s), hy+int(44*s)], fill=(180,110,25), outline=SAFARI_GREEN, width=int(5*s))
    draw.ellipse([hx-int(32*s), hy-int(28*s), hx+int(32*s), hy+int(28*s)], fill=(255,230,140), outline=SAFARI_GREEN, width=int(4*s))
    # ears
    draw.ellipse([hx-int(28*s)-8, hy-int(34*s), hx-int(12*s)+8, hy-int(18*s)], fill=(180,110,25), outline=SAFARI_GREEN, width=3)
    draw.ellipse([hx+int(12*s)-8, hy-int(34*s), hx+int(28*s)+8, hy-int(18*s)], fill=(180,110,25), outline=SAFARI_GREEN, width=3)
    # eyes
    draw.ellipse([hx-int(10*s), hy-int(6*s), hx-int(0*s), hy+int(4*s)], fill=BLACK)
    draw.ellipse([hx+int(0*s), hy-int(6*s), hx+int(10*s), hy+int(4*s)], fill=BLACK)
    # nose
    draw.ellipse([hx-int(6*s), hy+int(4*s), hx+int(6*s), hy+int(10*s)], fill=(80,40,20), outline=None)
    draw.line([(hx, hy+int(10*s)),(hx-int(8*s), hy+int(18*s))], fill=SAFARI_GREEN, width=2)
    draw.line([(hx, hy+int(10*s)),(hx+int(8*s), hy+int(18*s))], fill=SAFARI_GREEN, width=2)
    # paws
    for lx in [-32*s, 12*s]:
        draw.ellipse([x+int(lx)-10, y+int(16*s), x+int(lx)+10, y+int(28*s)], fill=(255,230,140), outline=SAFARI_GREEN, width=3)

def draw_colour_zebra(x, y, scale):
    s=scale
    draw.ellipse([x-int(68*s), y-int(20*s), x+int(52*s), y+int(24*s)], fill=WHITE, outline=SAFARI_GREEN, width=int(6*s))
    # stripes
    for sx in [-42*s, -22*s, -2*s, 18*s]:
        draw.line([(x+int(sx), y-int(18*s)),(x+int(sx-6*s), y+int(20*s))], fill=BLACK, width=int(5*s))
    # head
    hx = x+int(56*s)
    hy = y-int(12*s)
    draw.ellipse([hx-int(26*s), hy-int(18*s), hx+int(26*s), hy+int(18*s)], fill=WHITE, outline=SAFARI_GREEN, width=int(5*s))
    draw.ellipse([hx+int(10*s), hy-int(4*s), hx+int(22*s), hy+int(6*s)], fill=BLACK, outline=None)
    # mane
    for my in [-14*s, -6*s, 2*s]:
        draw.line([(x+int(18*s), y-int(18*s)+int(my)),(x+int(28*s), y-int(18*s)+int(my))], fill=BLACK, width=int(4*s))
    # eye
    draw.ellipse([hx-int(6*s), hy-int(4*s), hx+int(4*s), hy+int(4*s)], fill=BLACK)
    # legs
    for lx in [-28*s, 8*s]:
        draw.line([(x+int(lx), y+int(8*s)),(x+int(lx), y+int(42*s))], fill=BLACK, width=int(6*s))
        for ly in [18*s, 28*s]:
            draw.line([(x+int(lx)-6, y+int(ly)),(x+int(lx)+6, y+int(ly))], fill=BLACK, width=3)

def draw_colour_rhino(x, y, scale):
    s=scale
    draw.ellipse([x-int(76*s), y-int(22*s), x+int(52*s), y+int(26*s)], fill=(150,150,150), outline=SAFARI_GREEN, width=int(6*s))
    # horn
    draw.polygon([(x+int(42*s), y-int(6*s)),(x+int(62*s), y-int(32*s)),(x+int(52*s), y-int(4*s))], fill=(240,240,220), outline=SAFARI_GREEN, width=int(4*s))
    # ear
    draw.ellipse([x-int(8*s)-10, y-int(24*s), x-int(8*s)+10, y-int(10*s)], fill=(140,140,140), outline=SAFARI_GREEN, width=3)
    # eye
    draw.ellipse([x+int(2*s), y-int(6*s), x+int(10*s), y+int(2*s)], fill=BLACK)
    # legs
    for lx in [-32*s, 8*s]:
        draw.rectangle([x+int(lx)-10, y+int(6*s), x+int(lx)+10, y+int(42*s)], fill=(140,140,140), outline=SAFARI_GREEN, width=3)

# Front cover parade
ele_x = front_start + 320
ele_y = ground_y - 32
draw_colour_elephant(ele_x, ele_y, 0.92)
gira_x = front_start + 620
gira_y = ground_y - 40
draw_colour_giraffe(gira_x, gira_y, 0.88)
lion_x = front_start + 960
lion_y = ground_y - 28
draw_colour_lion(lion_x, lion_y, 0.82)
zebra_x = front_start + 1280
zebra_y = ground_y - 30
draw_colour_zebra(zebra_x, zebra_y, 0.78)
rhino_x = front_start + 1560
rhino_y = ground_y - 26
draw_colour_rhino(rhino_x, rhino_y, 0.72)

# Front cover text - must be readable at thumbnail
# Title box with semi-transparent white backing
front_center = front_start + trim_w_px//2
# Title
title_font = get_font(132, bold=True)
subtitle_font = get_font(54, bold=True)
age_font = get_font(38, bold=True)
author_font = get_font(32, bold=False)

# Draw rounded rect backing for title
title_text = "AFRICAN WILDLIFE"
title2_text = "AND NATURE"
subtitle_text = "A Safari Colouring Adventure"
# Measure
def text_size(txt, font):
    bbox = draw.textbbox((0,0), txt, font=font)
    return bbox[2]-bbox[0], bbox[3]-bbox[1]

tw, th = text_size(title_text, title_font)
tw2, th2 = text_size(title2_text, title_font)
sw, sh = text_size(subtitle_text, subtitle_font)
# Backing rectangle
pad_x = 48
pad_y = 22
back_top = int(Hpx*0.34)
back_bottom = int(Hpx*0.66)
# white translucent backing - we will draw white rectangle with slight transparency (opaque)
# Draw with border
back_left = front_center - max(tw, tw2)//2 - pad_x
back_right = front_center + max(tw, tw2)//2 + pad_x
draw.rounded_rectangle([back_left, back_top, back_right, back_bottom], radius=28, fill=(255,255,255,230), outline=SAFARI_GREEN, width=6)
# Add inner gold line
draw.rounded_rectangle([back_left+8, back_top+8, back_right-8, back_bottom-8], radius=20, outline=SAFARI_GOLD, width=3)

# Now draw text
# Title lines
y = back_top + 42
draw.text((front_center - tw//2, y), title_text, fill=SAFARI_GREEN, font=title_font, stroke_width=2, stroke_fill=WHITE)
draw.text((front_center - tw//2, y), title_text, fill=SAFARI_GREEN, font=title_font) # double for boldness
y += th + 8
draw.text((front_center - tw2//2, y), title2_text, fill=SAFARI_GREEN, font=title_font)
y += th2 + 18
# gold line separator
draw.line([(front_center-220, y), (front_center+220, y)], fill=SAFARI_GOLD, width=5)
y += 22
draw.text((front_center - sw//2, y), subtitle_text, fill=EARTH_BROWN, font=subtitle_font)
y += sh + 28
# badge: 40 illustrations + ages
badge_text = "40 SAFARI ILLUSTRATIONS  •  10 WILD FACTS  •  5 FUN ACTIVITIES"
badge_font = get_font(26, bold=True)
bw,bh = text_size(badge_text, badge_font)
# badge background
badge_y = y
draw.rounded_rectangle([front_center - bw//2 - 20, badge_y-10, front_center + bw//2 + 20, badge_y+bh+12], radius=14, fill=SAFARI_GREEN, outline=None)
draw.text((front_center - bw//2, badge_y), badge_text, fill=WHITE, font=badge_font)
y += bh + 28
age_text = "For Explorers Ages 5 to 10  •  Single-Sided Pages"
aw, ah = text_size(age_text, age_font)
draw.text((front_center - aw//2, y), age_text, fill=SAFARI_GREEN, font=age_font)

# Bottom front: Safari Wonders Press
press_text = "Safari Wonders Press"
press_font = get_font(30, bold=True)
pw, ph = text_size(press_text, press_font)
press_y = int(Hpx*0.88)
draw.text((front_center - pw//2, press_y), press_text, fill=WHITE, font=press_font, stroke_width=3, stroke_fill=SAFARI_GREEN)
draw.text((front_center - pw//2, press_y), press_text, fill=WHITE, font=press_font)

# Spine - very thin, just color and maybe small text vertical
if spine_px > 24:
    draw.rectangle([spine_start, 0, spine_end, Hpx], fill=SAFARI_GREEN, outline=None)
    # spine text vertical if enough width - our spine is only ~43px (0.144in*300) ~ too narrow for readable text
    # Instead just put small dots pattern
    for sy in range(120, Hpx-120, 28):
        draw.ellipse([spine_start+spine_px//2-4, sy-4, spine_start+spine_px//2+4, sy+4], fill=SAFARI_GOLD, outline=None)
    # try tiny text rotated? skip
    spine_font = get_font(22, bold=True)
    # draw vertical text by rotating? PIL doesn't easily rotate text without extra, skip for now
    pass
else:
    draw.rectangle([spine_start, 0, spine_end, Hpx], fill=SAFARI_GREEN)

# Back cover
back_center = back_start + trim_w_px//2
# Back cover title small
back_title = "Explore Africa's Wild Wonders!"
bt_font = get_font(46, bold=True)
btw, bth = text_size(back_title, bt_font)
bt_y = int(Hpx*0.14)
draw.text((back_center - btw//2, bt_y), back_title, fill=SAFARI_GREEN, font=bt_font, stroke_width=2, stroke_fill=WHITE)
draw.text((back_center - btw//2, bt_y), back_title, fill=SAFARI_GREEN, font=bt_font)

# Back description box
box_left = back_start + int(0.42*DPI)
box_right = back_end - int(0.42*DPI)
box_top = int(Hpx*0.23)
box_bottom = int(Hpx*0.82)
draw.rounded_rectangle([box_left, box_top, box_right, box_bottom], radius=18, fill=(255,255,255,242), outline=SAFARI_GREEN, width=4)
draw.rounded_rectangle([box_left+6, box_top+6, box_right-6, box_bottom-6], radius=12, outline=SAFARI_GOLD, width=2)

# Back cover paragraphs
def draw_wrapped_text(text, x, y, max_width, font, fill, spacing=6, align="left"):
    # simple word wrap
    words = text.split()
    lines = []
    cur=""
    for w in words:
        test = cur + " " + w if cur else w
        wpx = draw.textbbox((0,0), test, font=font)[2]
        if wpx <= max_width:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    yy = y
    for line in lines:
        if align=="center":
            lw = draw.textbbox((0,0), line, font=font)[2]
            draw.text((x + (max_width-lw)//2, yy), line, fill=fill, font=font)
        else:
            draw.text((x, yy), line, fill=fill, font=font)
        yy += font.size + spacing
    return yy

inner_left = box_left + 32
inner_width = box_right - box_left - 64
yy = box_top + 36
small_font = get_font(28, bold=False)
small_bold = get_font(28, bold=True)
desc1 = "Join a safari adventure across Africa — from golden savannahs and misty wetlands to baobab forests and rocky kopjes. Meet the Big Five, tower with giraffes, count zebra stripes, and discover baby animals with their families."
yy = draw_wrapped_text(desc1, inner_left, yy, inner_width, small_font, (45,45,45), spacing=8)

yy += 18
# bullet points
bullets = [
    "40 unique colouring illustrations — no duplicates, one per page",
    "The Big Five, savannah favourites, baby animals, birds & reptiles",
    "Stunning landscapes: acacia plains, baobabs, waterfalls & sunrises",
    "10 verified wildlife facts written in simple, friendly language",
    "5 bonus activities: matching, counting, spot-the-difference, maze & drawing",
    "Large, bold outlines perfect for crayons & coloured pencils (ages 5–10)",
]
bullet_font = get_font(26, bold=False)
check_font = get_font(26, bold=True)
for b in bullets:
    # checkmark
    draw.text((inner_left, yy), "✓", fill=SAFARI_GREEN, font=check_font)
    draw_wrapped_text(b, inner_left+36, yy, inner_width-36, bullet_font, (45,45,45), spacing=6)
    yy += bullet_font.size + 14

yy += 8
draw.line([(inner_left, yy),(box_right-32, yy)], fill=SAFARI_GOLD, width=2)
yy += 14
closing = "A respectful, educational celebration of African nature — created to inspire curiosity, creativity, and care for wildlife."
closing_font = get_font(26, bold=False)
# italic style via regular but we treat as italic
yy = draw_wrapped_text(closing, inner_left, yy, inner_width, closing_font, (80,60,30), spacing=7)
yy += 12
# Publisher at bottom of box
pub_text = "Safari Wonders Press  •  First Edition 2025  •  64 pages  •  8.5×11 in"
pub_font = get_font(22, bold=False)
pw = draw.textbbox((0,0), pub_text, font=pub_font)[2]
draw.text((back_center - pw//2, box_bottom - 38), pub_text, fill=(100,100,100), font=pub_font)

# Barcode placeholder
barcode_x = back_start + 60
barcode_y = Hpx - int(1.15*DPI)
barcode_w = int(2.0*DPI)
barcode_h = int(1.2*DPI)
draw.rectangle([barcode_x, barcode_y-barcode_h, barcode_x+barcode_w, barcode_y], fill=WHITE, outline=BLACK, width=2)
draw.text((barcode_x+18, barcode_y-barcode_h+18), "ISBN 979-8-XXXX-XXXX-X", fill=BLACK, font=get_font(20, bold=True))
for i in range(28):
    h = barcode_h-36 if i%3==0 else barcode_h-52
    draw.line([(barcode_x+14+i*18, barcode_y-barcode_h+28),(barcode_x+14+i*18, barcode_y-10)], fill=BLACK, width=2 if i%2==0 else 4)
draw.text((barcode_x+18, barcode_y-26), "BARCODE HERE", fill=(120,120,120), font=get_font(16, bold=False))

# Price hint
price_text = "U.S. $9.99"
price_font = get_font(28, bold=True)
pw2 = draw.textbbox((0,0), price_text, font=price_font)[2]
draw.text((barcode_x+barcode_w+28, barcode_y-barcode_h+42), price_text, fill=SAFARI_GREEN, font=price_font)

# Small KDP disclosure at very bottom back
disclose = "AI-assisted illustrations disclosed per KDP guidelines • Human-authored text & design • Printed on demand"
disclose_font = get_font(16, bold=False)
dw = draw.textbbox((0,0), disclose, font=disclose_font)[2]
draw.text((back_center - dw//2, Hpx - int(0.42*DPI)), disclose, fill=(120,120,120), font=disclose_font)

# Trim marks & safe zone guides - faint for printer reference (not part of final design but helpful)
# We'll add faint lines at trims
for x in [back_start, back_end, spine_start, spine_end, front_start, front_end]:
    draw.line([(x, 0),(x, 24)], fill=(200,200,200), width=1)
    draw.line([(x, Hpx-24),(x, Hpx)], fill=(200,200,200), width=1)
for y in [bleed_px, Hpx-bleed_px]:
    draw.line([(0,y),(24,y)], fill=(200,200,200), width=1)
    draw.line([(Wpx-24,y),(Wpx,y)], fill=(200,200,200), width=1)

# Save high-res jpg for front cover
front_crop_left = front_start  # includes bleed? Actually front trim with bleed: front_start to front_end includes trim+bleed right
# For front cover image we want only trim area plus bleed: front_start to front_end (which already includes right bleed? Let's check: front_end = front_start+trim_w_px, but bleed is not included in that trim - we need to include bleed on right and bottom/top
# Actually our cover includes left bleed only as back_start-bleed_px, but we didn't explicitly keep left bleed area? We set back_start=bleed_px, so left bleed is 0-bleed_px area which we filled with background, good.
# For front cover isolate: left = front_start, right = front_end + bleed_px, top 0 bottom Hpx, but also need top/bottom bleed
front_left = front_start
front_right = front_end + bleed_px
front_img = img.crop((front_left, 0, front_right, Hpx))
# Resize to 2550x3300 exact trim+bleed? front_right-front_left = trim_w_px+bleed_px = 2550+38 =2588, Hpx 3375, close
# We will resize to 2588x3375 and also save as is
front_img.save(OUT_DIR / "FrontCover_8.5x11_withBleed_300DPI.jpg", "JPEG", quality=95, dpi=(300,300))
# Also save exact trim size without bleed for thumbnail
front_trim = img.crop((front_start, bleed_px, front_start+trim_w_px, Hpx-bleed_px))
front_trim.save(OUT_JPG, "JPEG", quality=95, dpi=(300,300))
print(f"Saved front cover JPG {OUT_JPG} and with bleed")

# Now create PDF via reportlab
# Cover PDF is single page size = COVER_W x COVER_H inches at 72 dpi
from reportlab.lib.utils import ImageReader
OUT_DIR.mkdir(parents=True, exist_ok=True)
# Save temp full image for PDF embedding
temp_full = OUT_DIR / "full_cover_temp.jpg"
img.save(temp_full, "JPEG", quality=92, dpi=(300,300))
c = canvas.Canvas(str(OUT_PDF), pagesize=(COVER_W*inch, COVER_H*inch))
# Draw image stretched to cover
c.drawImage(str(temp_full), 0, 0, width=COVER_W*inch, height=COVER_H*inch, preserveAspectRatio=False, anchor='c')
# Add metadata
c.setTitle("African Wildlife and Nature: A Safari Colouring Adventure - Full Wrap Cover")
c.setAuthor("Safari Wonders Press")
c.setSubject("Full wrap cover 8.5x11 64 pages white paper, spine 0.144in, with bleed")
c.setKeywords("safari, colouring book, African wildlife, cover, KDP")
c.save()
print(f"Saved cover PDF {OUT_PDF}  size {COVER_W:.4f}x{COVER_H:.4f} in")
# file sizes
import os as _os
print(f"  JPG front trim { _os.path.getsize(OUT_JPG)/1024:.1f} KB")
print(f"  PDF full wrap { _os.path.getsize(OUT_PDF)/1024:.1f} KB")
print(f"  Temp full { _os.path.getsize(temp_full)/1024:.1f} KB")
# keep temp for reference, but also remove? keep for GDrive upload if needed
# Don't delete temp
