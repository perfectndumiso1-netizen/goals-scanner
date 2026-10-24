#!/usr/bin/env python3
"""
Generate 40 high-quality black-and-white colouring illustrations for African wildlife book.
Each image: 2550x3300 (8.5x11 @300 DPI), white background, crisp black outlines, child-friendly line weight.
"""
from PIL import Image, ImageDraw, ImageFont
import os, math, random

W, H = 2550, 3300
CENTER_X, CENTER_Y = W//2, H//2 + 80
BG = (255,255,255)
BLACK = (0,0,0)

OUT = "../illustrations"

# Use default font for labels, will draw text with ImageDraw

def new_canvas():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    return img, draw

def thick_ellipse(draw, bbox, width=12, fill=None):
    draw.ellipse(bbox, outline=BLACK, width=width, fill=fill)

def thick_rect(draw, bbox, width=10, fill=None, radius=0):
    if radius:
        draw.rounded_rectangle(bbox, radius=radius, outline=BLACK, width=width, fill=fill)
    else:
        draw.rectangle(bbox, outline=BLACK, width=width, fill=fill)

def ground_line(draw, y=2600, width=14):
    # wavy ground
    points = []
    for x in range(0, W+20, 40):
        yy = y + math.sin(x*0.01)*18 + random.randint(-6,6)
        points.append((x, yy))
    # baseline
    draw.line(points, fill=BLACK, width=width, joint="round")
    # grass tufts
    for x in [300, 600, 900, 1300, 1700, 2000, 2300]:
        gx = x + random.randint(-40,40)
        draw.line([(gx, y), (gx-18, y-45), (gx, y-30), (gx+18, y-45), (gx, y)], fill=BLACK, width=7, joint="round")

def acacia_tree(draw, x=400, y=2600, scale=1.0):
    # trunk
    trunk_w = int(30*scale)
    draw.line([(x, y), (x, y- int(420*scale))], fill=BLACK, width=trunk_w)
    # flat top canopy - typical acacia
    canopy_y = y - int(420*scale)
    # several flat umbrella shapes
    for ox, oy, w, h in [(-180,-20, 360,80), (-220,-60, 440,70), (-150,-90, 300,60)]:
        w2=int(w*scale); h2=int(h*scale)
        ox2=int(ox*scale); oy2=int(oy*scale)
        bbox=[x+ox2-w2//2+180, canopy_y+oy2, x+ox2+w2//2+180, canopy_y+oy2+h2]
        # adjust center
        bbox=[x+ox2, canopy_y+oy2, x+ox2+w2, canopy_y+oy2+h2]
        draw.ellipse(bbox, outline=BLACK, width=int(10*scale))
        # texture lines inside
        for tx in range(bbox[0]+20, bbox[2]-20, 40):
            draw.line([(tx, bbox[1]+10),(tx+10, bbox[3]-10)], fill=BLACK, width=4)

def baobab_tree(draw, x=2100, y=2600, scale=1.1):
    trunk_w = int(110*scale)
    trunk_h = int(480*scale)
    # huge trunk
    draw.rectangle([x-trunk_w//2, y-trunk_h, x+trunk_w//2, y], outline=BLACK, width=12, fill=BG)
    # texture lines on trunk
    for yy in range(y-trunk_h+40, y-20, 45):
        draw.line([(x-trunk_w//2+8, yy), (x+trunk_w//2-8, yy+6)], fill=BLACK, width=4)
    # crown - stubby branches with foliage clumps
    crown_y = y-trunk_h
    for (ox, oy, r) in [(-40,-40,90), (30,-55,75), (0,-95,65)]:
        draw.ellipse([x+ox*scale -r*scale, crown_y+oy*scale -r*scale, x+ox*scale +r*scale, crown_y+oy*scale +r*scale], outline=BLACK, width=10)

def sun(draw, x=2100, y=520, r=110):
    thick_ellipse(draw, [x-r, y-r, x+r, y+r], width=10)
    # rays
    for angle in range(0, 360, 30):
        rad = math.radians(angle)
        x1 = x + math.cos(rad)*(r+12)
        y1 = y + math.sin(rad)*(r+12)
        x2 = x + math.cos(rad)*(r+42)
        y2 = y + math.sin(rad)*(r+42)
        draw.line([(x1,y1),(x2,y2)], fill=BLACK, width=7)

def clouds(draw):
    for (cx, cy, rw, rh) in [(450, 480, 320, 120), (1200, 430, 380, 110), (1900, 500, 280, 100)]:
        # puffy cloud from overlapping ellipses
        for (ox, oy, w, h) in [(-rw//2,0,rw,rh),( -rw//3, -rh//2, rw*0.7, rh*0.9), (rw//4, -rh//3, rw*0.6, rh*0.8)]:
            draw.ellipse([cx+ox-w//2, cy+oy-h//2, cx+ox+w//2, cy+oy+h//2], outline=BLACK, width=8, fill=BG)

def rocks(draw, x=600, y=2500):
    # kopje rocks
    for (ox, oy, w, h) in [(0,0,340,130),(120,-70,280,110),( -80,-50,220,95)]:
        draw.ellipse([x+ox-w//2, y+oy-h//2, x+ox+w//2, y+oy+h//2], outline=BLACK, width=10, fill=BG)

def water_hole(draw, y=2650):
    # oval water
    draw.ellipse([400, y-45, W-400, y+55], outline=BLACK, width=10)
    # ripples
    for yy in [y-15, y+5, y+20]:
        draw.ellipse([700, yy-6, W-700, yy+6], outline=BLACK, width=5)

def draw_title(draw, text, y=H-260):
    # simple hand-drawn looking title bar
    # use default font - we'll draw text via ImageDraw with large font if available
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 68)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font = ImageFont.load_default()
        font_small = font
    # banner
    # measure
    bbox = draw.textbbox((0,0), text, font=font)
    tw = bbox[2]-bbox[0]
    th = bbox[3]-bbox[1]
    x = W//2 - tw//2
    # underline
    draw.text((x, y), text, fill=BLACK, font=font)
    # small subtitle
    subs = ["Colour me! • Ages 5-10", "African Wildlife • Colour me!"]
    sub = subs[0]
    bbox2 = draw.textbbox((0,0), sub, font=font_small)
    tw2 = bbox2[2]-bbox2[0]
    draw.text((W//2 - tw2//2, y+78), sub, fill=BLACK, font=font_small)

def add_border(draw):
    draw.rectangle([40,40,W-40,H-40], outline=BLACK, width=8)

# ==================== ANIMAL DRAWING PRIMITIVES ====================

def draw_lion(draw, cx, cy, scale=1.0, facing=1):
    s=scale
    # body oval
    thick_ellipse(draw, [cx-260*s, cy-40*s, cx+220*s, cy+160*s], width=12, fill=BG)
    # chest
    thick_ellipse(draw, [cx-120*s, cy-80*s, cx+140*s, cy+120*s], width=10, fill=BG)
    # head
    hx = cx+240*s if facing==1 else cx-240*s
    hy = cy-30*s
    # mane - big fluffy circle with spiky edge
    mane_r = 190*s
    thick_ellipse(draw, [hx-mane_r, hy-mane_r, hx+mane_r, hy+mane_r], width=11, fill=BG)
    # mane spikes
    for ang in range(0,360,22):
        rad=math.radians(ang)
        x1=hx+math.cos(rad)*mane_r
        y1=hy+math.sin(rad)*mane_r
        x2=hx+math.cos(rad)*(mane_r+34*s)
        y2=hy+math.sin(rad)*(mane_r+34*s)
        draw.line([(x1,y1),(x2,y2)], fill=BLACK, width=7)
    # face
    face_r = 115*s
    thick_ellipse(draw, [hx-face_r, hy-face_r, hx+face_r, hy+face_r], width=10, fill=BG)
    # ears
    for ex in [-55*s, 55*s]:
        thick_ellipse(draw, [hx+ex-32*s, hy-85*s, hx+ex+32*s, hy-25*s], width=8, fill=BG)
        thick_ellipse(draw, [hx+ex-16*s, hy-65*s, hx+ex+16*s, hy-35*s], width=5)
    # eyes
    for ex in [-32*s, 32*s]:
        thick_ellipse(draw, [hx+ex-22*s, hy-18*s, hx+ex+22*s, hy+18*s], width=8, fill=BG)
        draw.ellipse([hx+ex-9*s, hy-8*s, hx+ex+9*s, hy+8*s], fill=BLACK)
    # nose
    thick_ellipse(draw, [hx-26*s, hy+18*s, hx+26*s, hy+42*s], width=7, fill=BG)
    draw.ellipse([hx-8*s, hy+24*s, hx+8*s, hy+32*s], fill=BLACK)
    # mouth smile
    draw.arc([hx-38*s, hy+38*s, hx+38*s, hy+78*s], start=20, end=160, fill=BLACK, width=7)
    # legs
    for lx in [-150*s, -60*s, 60*s, 150*s]:
        draw.rounded_rectangle([cx+lx-38*s, cy+80*s, cx+lx+38*s, cy+210*s], radius=18*s, outline=BLACK, width=10, fill=BG)
        # paws
        thick_ellipse(draw, [cx+lx-44*s, cy+190*s, cx+lx+44*s, cy+230*s], width=8, fill=BG)
        # toes lines
        for tx in [-14*s,14*s]:
            draw.line([(cx+lx+tx, cy+205*s),(cx+lx+tx, cy+220*s)], fill=BLACK, width=4)
    # tail
    tail_x = cx-270*s if facing==1 else cx+270*s
    draw.line([(tail_x, cy+30*s),(tail_x-110*s, cy-40*s)], fill=BLACK, width=14)
    thick_ellipse(draw, [tail_x-140*s, cy-85*s, tail_x-80*s, cy-35*s], width=8, fill=BG)

def draw_elephant(draw, cx, cy, scale=1.0, baby=False):
    s=scale* (0.58 if baby else 1.0)
    # body large
    thick_ellipse(draw, [cx-300*s, cy-90*s, cx+210*s, cy+150*s], width=12, fill=BG)
    # head
    hx = cx+210*s
    hy = cy-40*s
    # huge ear - Africa shape, must be large and wavy
    ear_w = 190*s
    ear_h = 220*s
    # ear outline - africa-like with lobed bottom
    ear_bbox = [hx-40*s, hy-150*s, hx+170*s, hy+140*s]
    # draw ear as rounded shape with indentation
    points = [
        (hx-10*s, hy-130*s), (hx+50*s, hy-150*s), (hx+150*s, hy-100*s),
        (hx+170*s, hy-20*s), (hx+140*s, hy+80*s), (hx+60*s, hy+130*s),
        (hx-20*s, hy+90*s), (hx-30*s, hy-20*s)
    ]
    draw.polygon(points, outline=BLACK, width=11, fill=BG)
    # ear inner line
    draw.line([(hx+20*s, hy-90*s),(hx+90*s, hy-60*s),(hx+110*s, hy+10*s),(hx+70*s, hy+70*s)], fill=BLACK, width=6)
    # head oval
    thick_ellipse(draw, [hx-110*s, hy-110*s, hx+90*s, hy+110*s], width=11, fill=BG)
    # trunk - long S shape
    tx, ty = hx+60*s, hy+40*s
    # trunk as thick polyline with width
    trunk_pts = [(tx,ty),(tx+50*s, ty+70*s),(tx+20*s, ty+150*s),(tx-20*s, ty+210*s)]
    for i in range(len(trunk_pts)-1):
        w = int(46*s - i*8*s)
        draw.line([trunk_pts[i], trunk_pts[i+1]], fill=BLACK, width=w)
        # draw white inner to create outline effect? Instead draw double lines
    # redraw with white inner to make hollow trunk illusion - actually keep solid with outline
    # trunk tip
    thick_ellipse(draw, [tx-40*s, ty+190*s, tx+10*s, ty+230*s], width=8, fill=BG)
    # nostrils
    draw.ellipse([tx-22*s, ty+210*s, tx-10*s, ty+222*s], fill=BLACK)
    draw.ellipse([tx-6*s, ty+210*s, tx+6*s, ty+222*s], fill=BLACK)
    # tusk
    draw.ellipse([hx+25*s, hy+30*s, hx+75*s, hy+75*s], outline=BLACK, width=8, fill=BG)
    # tusk curves
    draw.arc([hx+10*s, hy+35*s, hx+90*s, hy+95*s], start=300, end=30, fill=BLACK, width=7)
    # eye
    thick_ellipse(draw, [hx-45*s, hy-35*s, hx-5*s, hy+5*s], width=7, fill=BG)
    draw.ellipse([hx-30*s, hy-20*s, hx-15*s, hy-5*s], fill=BLACK)
    draw.ellipse([hx-26*s, hy-18*s, hx-20*s, hy-12*s], fill=BG) # highlight
    # legs - thick pillars
    for lx in [-190*s, -70*s, 70*s, 170*s]:
        draw.rectangle([cx+lx-62*s, cy+70*s, cx+lx+62*s, cy+210*s], outline=BLACK, width=10, fill=BG)
        # toenails
        for tx2 in [-30*s, 0, 30*s]:
            draw.arc([cx+lx+tx2-18*s, cy+200*s, cx+lx+tx2+18*s, cy+225*s], start=10, end=170, fill=BLACK, width=4)
    # tail
    draw.line([(cx-300*s, cy+20*s),(cx-360*s, cy+80*s)], fill=BLACK, width=12)
    thick_ellipse(draw, [cx-385*s, cy+62*s, cx-345*s, cy+98*s], width=7, fill=BG)
    for i in range(5):
        draw.line([(cx-375*s+i*8*s, cy+95*s),(cx-378*s+i*8*s, cy+118*s)], fill=BLACK, width=4)

def draw_giraffe(draw, cx, cy, scale=1.0):
    s=scale
    # body
    thick_ellipse(draw, [cx-220*s, cy-30*s, cx+120*s, cy+150*s], width=11, fill=BG)
    # giraffe spots - irregular polygons
    for (ox,oy,w,h) in [(-120,-10,70,55),(30,20,60,50),(-60,60,65,45),(70,70,55,40),(-150,45,45,35)]:
        draw.polygon([(cx+ox,cy+oy),(cx+ox+w,cy+oy+10),(cx+ox+w-8,cy+oy+h),(cx+ox-5,cy+oy+h-8)], outline=BLACK, width=5)
    # neck long
    neck_top_y = cy-240*s
    neck_bottom_y = cy-30*s
    draw.polygon([(cx+40*s, neck_top_y+30*s),(cx+110*s, neck_top_y+30*s),(cx+60*s, neck_bottom_y),(cx-10*s, neck_bottom_y)], outline=BLACK, width=11, fill=BG)
    # neck spots
    for ny in [neck_top_y+80*s, neck_top_y+130*s, neck_top_y+180*s]:
        draw.polygon([(cx+30*s, ny),(cx+70*s, ny+6*s),(cx+55*s, ny+30*s),(cx+18*s, ny+22*s)], outline=BLACK, width=5)
    # head
    hx = cx+75*s
    hy = neck_top_y
    thick_ellipse(draw, [hx-70*s, hy-50*s, hx+90*s, hy+50*s], width=10, fill=BG)
    # ossicones (horns)
    for ox in [-22*s, 22*s]:
        draw.line([(hx+ox, hy-45*s),(hx+ox-6*s, hy-95*s)], fill=BLACK, width=10)
        thick_ellipse(draw, [hx+ox-18*s, hy-115*s, hx+ox+10*s, hy-85*s], width=7, fill=BG)
    # ears large
    thick_ellipse(draw, [hx-75*s, hy-30*s, hx-35*s, hy+6*s], width=7, fill=BG)
    thick_ellipse(draw, [hx+45*s, hy-28*s, hx+82*s, hy+8*s], width=7, fill=BG)
    # eye
    thick_ellipse(draw, [hx+16*s, hy-12*s, hx+52*s, hy+18*s], width=7, fill=BG)
    draw.ellipse([hx+28*s, hy-4*s, hx+43*s, hy+10*s], fill=BLACK)
    draw.ellipse([hx+30*s, hy-2*s, hx+36*s, hy+4*s], fill=BG)
    # muzzle
    thick_ellipse(draw, [hx+50*s, hy+10*s, hx+105*s, hy+38*s], width=7, fill=BG)
    draw.ellipse([hx+88*s, hy+18*s, hx+98*s, hy+28*s], fill=BLACK)
    # legs tall and slender
    for lx in [-140*s, -50*s, 30*s, 100*s]:
        draw.polygon([(cx+lx-32*s, cy+120*s),(cx+lx+32*s, cy+120*s),(cx+lx+26*s, cy+320*s),(cx+lx-26*s, cy+320*s)], outline=BLACK, width=10, fill=BG)
        thick_ellipse(draw, [cx+lx-34*s, cy+300*s, cx+lx+34*s, cy+330*s], width=8, fill=BG)
    # tail with tuft
    draw.line([(cx-220*s, cy+60*s),(cx-280*s, cy+140*s)], fill=BLACK, width=10)
    for i in range(6):
        draw.line([(cx-285*s+i*5, cy+140*s),(cx-290*s+i*5, cy+170*s)], fill=BLACK, width=4)

def draw_zebra(draw, cx, cy, scale=1.0):
    s=scale
    # body - horse shape
    thick_ellipse(draw, [cx-250*s, cy-60*s, cx+180*s, cy+130*s], width=11, fill=BG)
    # neck
    draw.polygon([(cx+60*s, cy-80*s),(cx+140*s, cy-110*s),(cx+90*s, cy+20*s),(cx+20*s, cy+10*s)], outline=BLACK, width=10, fill=BG)
    # head
    hx = cx+160*s
    hy = cy-130*s
    thick_ellipse(draw, [hx-60*s, hy-45*s, hx+80*s, hy+45*s], width=10, fill=BG)
    # muzzle
    thick_ellipse(draw, [hx+45*s, hy-10*s, hx+95*s, hy+30*s], width=8, fill=BG)
    draw.ellipse([hx+78*s, hy+4*s, hx+88*s, hy+14*s], fill=BLACK)
    # ears pointy
    thick_ellipse(draw, [hx-35*s, hy-52*s, hx-5*s, hy-18*s], width=7, fill=BG)
    thick_ellipse(draw, [hx+10*s, hy-58*s, hx+38*s, hy-22*s], width=7, fill=BG)
    # mane striped
    for my in [-105*s, -85*s, -65*s, -45*s]:
        draw.line([(cx+85*s, cy-105*s + (my+105*s)),(cx+105*s, cy-95*s + (my+105*s))], fill=BLACK, width=6)
    # stripes on body - zebra distinctive
    for sx in [-150*s, -95*s, -40*s, 15*s, 80*s]:
        # curved stripes
        draw.line([(cx+sx, cy-55*s),(cx+sx-18*s, cy+20*s),(cx+sx+6*s, cy+110*s)], fill=BLACK, width=8)
        # branch
        draw.line([(cx+sx+6*s, cy+40*s),(cx+sx+30*s, cy+60*s)], fill=BLACK, width=6)
    # neck stripes
    for ny in [-80*s, -50*s, -20*s]:
        draw.line([(cx+90*s, cy+ny),(cx+55*s, cy+ny+12*s)], fill=BLACK, width=7)
    # leg stripes
    for lx in [-150*s, -60*s, 50*s, 130*s]:
        draw.polygon([(cx+lx-34*s, cy+60*s),(cx+lx+34*s, cy+60*s),(cx+lx+30*s, cy+210*s),(cx+lx-30*s, cy+210*s)], outline=BLACK, width=10, fill=BG)
        # horizontal leg stripes
        for ly in [90*s,120*s,150*s,180*s]:
            draw.line([(cx+lx-30*s, cy+ly),(cx+lx+30*s, cy+ly+6*s)], fill=BLACK, width=6)
        thick_ellipse(draw, [cx+lx-32*s, cy+195*s, cx+lx+32*s, cy+220*s], width=7, fill=BG)
    # tail
    draw.line([(cx-250*s, cy+10*s),(cx-305*s, cy+70*s)], fill=BLACK, width=10)
    for i in range(7):
        draw.line([(cx-310*s+i*6, cy+70*s),(cx-315*s+i*6, cy+105*s)], fill=BLACK, width=4)
    # eye
    thick_ellipse(draw, [hx-8*s, hy-14*s, hx+28*s, hy+14*s], width=7, fill=BG)
    draw.ellipse([hx+6*s, hy-6*s, hx+18*s, hy+6*s], fill=BLACK)

def draw_leopard(draw, cx, cy, scale=1.0):
    s=scale
    # sleek body
    thick_ellipse(draw, [cx-270*s, cy-20*s, cx+170*s, cy+120*s], width=11, fill=BG)
    # head
    hx = cx+190*s
    hy = cy-20*s
    thick_ellipse(draw, [hx-85*s, hy-65*s, hx+85*s, hy+65*s], width=10, fill=BG)
    # muzzle
    thick_ellipse(draw, [hx+25*s, hy+6*s, hx+92*s, hy+42*s], width=8, fill=BG)
    # ears
    for ex in [-45*s, 35*s]:
        thick_ellipse(draw, [hx+ex-26*s, hy-70*s, hx+ex+26*s, hy-28*s], width=7, fill=BG)
    # rosettes spots
    for (ox,oy) in [(-180,30),(-120,60),(-60,20),(0,70),(60,40),(-150,-5),(-90,90)]:
        # outer circle
        x=cx+ox*s; y=cy+oy*s
        thick_ellipse(draw, [x-20*s, y-16*s, x+20*s, y+16*s], width=5, fill=BG)
        # inner dots
        for (ix,iy) in [(-8,-4),(8,-4),(0,6)]:
            draw.ellipse([x+ix*s-4*s, y+iy*s-4*s, x+ix*s+4*s, y+iy*s+4*s], fill=BLACK)
    # tail long curved
    points = [(cx-270*s, cy+30*s),(cx-340*s, cy+0*s),(cx-390*s, cy+50*s),(cx-360*s, cy+110*s)]
    for i in range(len(points)-1):
        draw.line([points[i], points[i+1]], fill=BLACK, width=12)
    thick_ellipse(draw, [cx-375*s, cy+95*s, cx-345*s, cy+125*s], width=7, fill=BG)
    # legs
    for lx in [-140*s, -40*s, 70*s, 150*s]:
        draw.polygon([(cx+lx-28*s, cy+60*s),(cx+lx+28*s, cy+60*s),(cx+lx+24*s, cy+200*s),(cx+lx-24*s, cy+200*s)], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-28*s, cy+185*s, cx+lx+28*s, cy+210*s], width=7, fill=BG)
    # eye
    thick_ellipse(draw, [hx+6*s, hy-18*s, hx+42*s, hy+10*s], width=7, fill=BG)
    draw.ellipse([hx+18*s, hy-8*s, hx+32*s, hy+4*s], fill=BLACK)
    # nose
    thick_ellipse(draw, [hx+58*s, hy+10*s, hx+78*s, hy+24*s], width=5, fill=BG)
    draw.ellipse([hx+64*s, hy+14*s, hx+72*s, hy+20*s], fill=BLACK)

def draw_buffalo(draw, cx, cy, scale=1.0):
    s=scale
    # massive body
    thick_ellipse(draw, [cx-320*s, cy-70*s, cx+220*s, cy+140*s], width=12, fill=BG)
    # hump on back
    draw.arc([cx-120*s, cy-130*s, cx+80*s, cy-10*s], start=180, end=0, fill=BLACK, width=11)
    # head large
    hx = cx+240*s
    hy = cy-10*s
    thick_ellipse(draw, [hx-90*s, hy-85*s, hx+80*s, hy+85*s], width=11, fill=BG)
    # horns - huge curved
    # left horn curve outward then up
    draw.arc([hx-140*s, hy-120*s, hx+40*s, hy+10*s], start=120, end=220, fill=BLACK, width=16)
    draw.arc([hx-160*s, hy-100*s, hx+20*s, hy+30*s], start=125, end=215, fill=BLACK, width=12)
    # right side mirror
    # Actually buffalo horns are continuous across forehead - boss
    thick_rect(draw, [hx-70*s, hy-95*s, hx+50*s, hy-60*s], width=9, fill=BG, radius=12*s)
    # second horn
    draw.arc([hx-40*s, hy-120*s, hx+160*s, hy+10*s], start=320, end=70, fill=BLACK, width=16)
    # muzzle broad
    thick_ellipse(draw, [hx+35*s, hy+16*s, hx+95*s, hy+58*s], width=8, fill=BG)
    draw.ellipse([hx+68*s, hy+30*s, hx+82*s, hy+42*s], fill=BLACK)
    # eyes
    thick_ellipse(draw, [hx-14*s, hy-18*s, hx+22*s, hy+12*s], width=7, fill=BG)
    draw.ellipse([hx-2*s, hy-8*s, hx+12*s, hy+4*s], fill=BLACK)
    # legs sturdy
    for lx in [-170*s, -60*s, 60*s, 160*s]:
        draw.rectangle([cx+lx-44*s, cy+60*s, cx+lx+44*s, cy+210*s], outline=BLACK, width=10, fill=BG)
        thick_ellipse(draw, [cx+lx-46*s, cy+195*s, cx+lx+46*s, cy+220*s], width=8, fill=BG)
        # dewlap
    # beard/tuft on chest
    for i in range(5):
        draw.line([(cx-40*s+i*12*s, cy+90*s),(cx-45*s+i*12*s, cy+115*s)], fill=BLACK, width=4)
    # tail
    draw.line([(cx-320*s, cy+20*s),(cx-360*s, cy+90*s)], fill=BLACK, width=12)
    for i in range(6):
        draw.line([(cx-365*s+i*7, cy+90*s),(cx-370*s+i*7, cy+120*s)], fill=BLACK, width=4)

def draw_rhino(draw, cx, cy, scale=1.0):
    s=scale
    # body bulky, armor plates suggested with lines
    thick_ellipse(draw, [cx-300*s, cy-70*s, cx+200*s, cy+150*s], width=12, fill=BG)
    # skin folds
    for sx in [-120*s, 0*s, 90*s]:
        draw.arc([cx+sx-40*s, cy-40*s, cx+sx+40*s, cy+100*s], start=90, end=270, fill=BLACK, width=5)
    # head
    hx = cx+220*s
    hy = cy-30*s
    thick_ellipse(draw, [hx-95*s, hy-75*s, hx+85*s, hy+75*s], width=11, fill=BG)
    # horns - two, front larger
    # front horn
    draw.polygon([(hx+55*s, hy-20*s),(hx+85*s, hy-80*s),(hx+95*s, hy-75*s),(hx+65*s, hy-10*s)], outline=BLACK, width=8, fill=BG)
    draw.line([(hx+70*s, hy-60*s),(hx+60*s, hy-25*s)], fill=BLACK, width=4)
    # second horn smaller
    draw.polygon([(hx+15*s, hy-30*s),(hx+35*s, hy-60*s),(hx+42*s, hy-56*s),(hx+22*s, hy-22*s)], outline=BLACK, width=7, fill=BG)
    # ear
    thick_ellipse(draw, [hx-55*s, hy-78*s, hx-15*s, hy-38*s], width=7, fill=BG)
    # eye small
    thick_ellipse(draw, [hx-18*s, hy-12*s, hx+12*s, hy+12*s], width=6, fill=BG)
    draw.ellipse([hx-8*s, hy-6*s, hx+4*s, hy+6*s], fill=BLACK)
    # nostril
    draw.ellipse([hx+55*s, hy+12*s, hx+68*s, hy+26*s], outline=BLACK, width=5)
    # legs short thick
    for lx in [-170*s, -60*s, 60*s, 150*s]:
        draw.rectangle([cx+lx-52*s, cy+60*s, cx+lx+52*s, cy+210*s], outline=BLACK, width=10, fill=BG)
        # skin folds on legs
        draw.line([(cx+lx-40*s, cy+110*s),(cx+lx+40*s, cy+115*s)], fill=BLACK, width=4)
        draw.line([(cx+lx-38*s, cy+150*s),(cx+lx+38*s, cy+155*s)], fill=BLACK, width=4)
        thick_ellipse(draw, [cx+lx-54*s, cy+195*s, cx+lx+54*s, cy+220*s], width=8, fill=BG)
    # tail
    draw.line([(cx-300*s, cy+10*s),(cx-330*s, cy+70*s)], fill=BLACK, width=10)
    thick_ellipse(draw, [cx-345*s, cy+62*s, cx-315*s, cy+88*s], width=7, fill=BG)

def draw_cheetah(draw, cx, cy, scale=1.0):
    s=scale
    # lean body running
    thick_ellipse(draw, [cx-250*s, cy-30*s, cx+140*s, cy+90*s], width=11, fill=BG)
    # head
    hx=cx+170*s
    hy=cy-50*s
    thick_ellipse(draw, [hx-70*s, hy-55*s, hx+70*s, hy+55*s], width=10, fill=BG)
    # tear lines characteristic
    draw.line([(hx-10*s, hy-6*s),(hx-22*s, hy+38*s)], fill=BLACK, width=7)
    draw.line([(hx+22*s, hy-6*s),(hx+10*s, hy+38*s)], fill=BLACK, width=7)
    # spots solid small
    for (ox,oy) in [(-150,10),(-110,40),(-70,5),(-40,45),(0,20),(30,50),(-130,-10),(-60,65)]:
        draw.ellipse([cx+ox*s-12*s, cy+oy*s-12*s, cx+ox*s+12*s, cy+oy*s+12*s], fill=BLACK)
    # tail long with rings
    for i, (tx, ty) in enumerate([(-270,10),(-310, -10),(-350,15),(-380,40)]):
        draw.ellipse([cx+tx*s-20*s, cy+ty*s-10*s, cx+tx*s+20*s, cy+ty*s+10*s], outline=BLACK, width=7, fill=BG if i%2==0 else BG)
        if i%2==1:
            for k in range(2):
                draw.ellipse([cx+tx*s-6*s+k*10*s, cy+ty*s-4*s, cx+tx*s+2*s+k*10*s, cy+ty*s+4*s], fill=BLACK)
    draw.line([(cx-250*s, cy+20*s),(cx-290*s, cy+0*s)], fill=BLACK, width=10)
    # legs extended running
    for (lx, dy, ang) in [(-120*s, 60*s, -12), (-40*s, 70*s, 12), (40*s, 60*s, -10), (110*s, 70*s, 10)]:
        # draw as capsule
        draw.line([(cx+lx, cy+60*s),(cx+lx+20*s, cy+190*s)], fill=BLACK, width=14)
        thick_ellipse(draw, [cx+lx-18*s, cy+175*s, cx+lx+38*s, cy+205*s], width=7, fill=BG)
    # ears
    thick_ellipse(draw, [hx-35*s, hy-62*s, hx-5*s, hy-32*s], width=7, fill=BG)
    thick_ellipse(draw, [hx+20*s, hy-64*s, hx+50*s, hy-34*s], width=7, fill=BG)
    # eyes
    thick_ellipse(draw, [hx-18*s, hy-14*s, hx+6*s, hy+10*s], width=6, fill=BG)
    thick_ellipse(draw, [hx+18*s, hy-14*s, hx+42*s, hy+10*s], width=6, fill=BG)
    draw.ellipse([hx-10*s, hy-6*s, hx-2*s, hy+4*s], fill=BLACK)
    draw.ellipse([hx+26*s, hy-6*s, hx+34*s, hy+4*s], fill=BLACK)
    # nose
    draw.ellipse([hx+10*s, hy+12*s, hx+34*s, hy+26*s], outline=BLACK, width=5)
    draw.ellipse([hx+18*s, hy+16*s, hx+26*s, hy+22*s], fill=BLACK)

def draw_hyena(draw, cx, cy, scale=1.0):
    s=scale
    thick_ellipse(draw, [cx-220*s, cy-50*s, cx+160*s, cy+130*s], width=11, fill=BG)
    # sloping back
    draw.line([(cx-100*s, cy-50*s),(cx+80*s, cy+10*s)], fill=BLACK, width=9)
    # head large
    hx=cx+190*s
    hy=cy-20*s
    thick_ellipse(draw, [hx-85*s, hy-65*s, hx+75*s, hy+65*s], width=10, fill=BG)
    # muzzle blunt
    thick_ellipse(draw, [hx+30*s, hy+5*s, hx+85*s, hy+45*s], width=8, fill=BG)
    draw.ellipse([hx+58*s, hy+18*s, hx+72*s, hy+30*s], fill=BLACK)
    # spots
    for (ox,oy) in [(-120,20),(-80,50),(-40,10),(0,60),(40,20)]:
        draw.ellipse([cx+ox*s-13*s, cy+oy*s-13*s, cx+ox*s+13*s, cy+oy*s+13*s], fill=BLACK)
    # ears rounded
    thick_ellipse(draw, [hx-45*s, hy-72*s, hx-5*s, hy-32*s], width=7, fill=BG)
    thick_ellipse(draw, [hx+15*s, hy-74*s, hx+55*s, hy-34*s], width=7, fill=BG)
    # legs
    for lx in [-120*s, -30*s, 60*s, 140*s]:
        h = 180*s if lx<0 else 200*s
        draw.rectangle([cx+lx-30*s, cy+60*s, cx+lx+30*s, cy+h], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-32*s, cy+h-15*s, cx+lx+32*s, cy+h+10*s], width=7, fill=BG)
    # tail bushy short
    draw.ellipse([cx-240*s, cy+20*s, cx-190*s, cy+90*s], outline=BLACK, width=8, fill=BG)
    for i in range(5):
        draw.line([(cx-230*s+i*10*s, cy+80*s),(cx-235*s+i*10*s, cy+100*s)], fill=BLACK, width=3)

def draw_warthog(draw, cx, cy, scale=1.0):
    s=scale
    thick_ellipse(draw, [cx-240*s, cy-40*s, cx+180*s, cy+130*s], width=11, fill=BG)
    # warts bumps
    thick_ellipse(draw, [cx+40*s, cy-10*s, cx+90*s, cy+25*s], width=6, fill=BG)
    thick_ellipse(draw, [cx+70*s, cy+20*s, cx+110*s, cy+50*s], width=6, fill=BG)
    # head
    hx=cx+210*s
    hy=cy-10*s
    thick_ellipse(draw, [hx-70*s, hy-55*s, hx+70*s, hy+55*s], width=10, fill=BG)
    # snout long
    thick_ellipse(draw, [hx+45*s, hy-12*s, hx+105*s, hy+32*s], width=8, fill=BG)
    draw.ellipse([hx+82*s, hy+4*s, hx+94*s, hy+16*s], fill=BLACK)
    draw.ellipse([hx+82*s, hy+18*s, hx+94*s, hy+30*s], fill=BLACK)
    # tusks curved up
    draw.arc([hx+20*s, hy+10*s, hx+70*s, hy+60*s], start=10, end=90, fill=BLACK, width=9)
    draw.arc([hx+18*s, hy+18*s, hx+68*s, hy+68*s], start=15, end=85, fill=BLACK, width=6)
    # mane bristly along back
    for mx in [-180*s, -140*s, -100*s, -60*s, -20*s]:
        draw.line([(cx+mx, cy-40*s),(cx+mx-10*s, cy-80*s)], fill=BLACK, width=7)
    # tusks second side smaller
    # legs
    for lx in [-130*s, -50*s, 50*s, 130*s]:
        draw.rectangle([cx+lx-30*s, cy+70*s, cx+lx+30*s, cy+200*s], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-32*s, cy+185*s, cx+lx+32*s, cy+210*s], width=7, fill=BG)
    # tail with tuft
    draw.line([(cx-240*s, cy+20*s),(cx-285*s, cy+60*s)], fill=BLACK, width=9)
    for i in range(5):
        draw.line([(cx-290*s+i*6, cy+60*s),(cx-295*s+i*6, cy+85*s)], fill=BLACK, width=4)
    # eye
    thick_ellipse(draw, [hx-12*s, hy-18*s, hx+18*s, hy+6*s], width=6, fill=BG)
    draw.ellipse([hx-4*s, hy-10*s, hx+8*s, hy+0*s], fill=BLACK)
    # ear
    thick_ellipse(draw, [hx-35*s, hy-58*s, hx+5*s, hy-22*s], width=7, fill=BG)

def draw_meerkat(draw, cx, cy, scale=1.15):
    s=scale
    # upright body
    thick_ellipse(draw, [cx-100*s, cy-20*s, cx+100*s, cy+150*s], width=10, fill=BG)
    # belly
    draw.ellipse([cx-60*s, cy+40*s, cx+60*s, cy+130*s], outline=BLACK, width=6)
    # head
    hx=cx
    hy=cy-60*s
    thick_ellipse(draw, [hx-90*s, hy-70*s, hx+90*s, hy+60*s], width=10, fill=BG)
    # muzzle
    thick_ellipse(draw, [hx-35*s, hy+6*s, hx+35*s, hy+36*s], width=7, fill=BG)
    draw.ellipse([hx-8*s, hy+14*s, hx+8*s, hy+24*s], fill=BLACK)
    # eye patches dark
    for ex in [-36*s, 36*s]:
        thick_ellipse(draw, [hx+ex-28*s, hy-18*s, hx+ex+28*s, hy+18*s], width=7, fill=BG)
        draw.ellipse([hx+ex-10*s, hy-6*s, hx+ex+10*s, hy+6*s], fill=BLACK)
        draw.ellipse([hx+ex-4*s, hy-4*s, hx+ex+2*s, hy+2*s], fill=BG)
    # ears small
    thick_ellipse(draw, [hx-82*s, hy-48*s, hx-48*s, hy-14*s], width=7, fill=BG)
    thick_ellipse(draw, [hx+48*s, hy-48*s, hx+82*s, hy-14*s], width=7, fill=BG)
    # arms little
    thick_ellipse(draw, [cx-110*s, cy+30*s, cx-65*s, cy+90*s], width=7, fill=BG)
    thick_ellipse(draw, [cx+65*s, cy+30*s, cx+110*s, cy+90*s], width=7, fill=BG)
    # legs
    for lx in [-40*s, 40*s]:
        draw.rectangle([cx+lx-30*s, cy+110*s, cx+lx+30*s, cy+210*s], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-32*s, cy+195*s, cx+lx+32*s, cy+220*s], width=7, fill=BG)
    # tail
    draw.line([(cx, cy+140*s),(cx-10*s, cy+200*s)], fill=BLACK, width=10)
    thick_ellipse(draw, [cx-28*s, cy+190*s, cx+8*s, cy+225*s], width=7, fill=BG)
    # extra meerkat pups nearby small
    for (ox, s2) in [(-260,0.55),(260,0.5)]:
        draw_meerkat_small(draw, cx+ox*s, cy+60*s, s2)

def draw_meerkat_small(draw, cx, cy, scale):
    s=scale
    thick_ellipse(draw, [cx-60*s, cy-10*s, cx+60*s, cy+90*s], width=7, fill=BG)
    hx=cx; hy=cy-30*s
    thick_ellipse(draw, [hx-50*s, hy-40*s, hx+50*s, hy+30*s], width=7, fill=BG)
    for ex in [-20*s,20*s]:
        draw.ellipse([hx+ex-12*s, hy-8*s, hx+ex+12*s, hy+8*s], fill=BLACK)
    thick_ellipse(draw, [hx-15*s, hy+4*s, hx+15*s, hy+18*s], width=5, fill=BG)

def draw_wilddog(draw, cx, cy, scale=1.0):
    s=scale
    thick_ellipse(draw, [cx-230*s, cy-30*s, cx+160*s, cy+120*s], width=11, fill=BG)
    # mottled patches
    for (ox,oy,w,h) in [(-120,10,80,50),(-40,40,70,45),(30,60,60,40),(-80,-10,50,35)]:
        draw.ellipse([cx+ox*s, cy+oy*s, cx+ox*s+w*s, cy+oy*s+h*s], outline=BLACK, width=5, fill=BG)
        draw.arc([cx+ox*s+8*s, cy+oy*s+8*s, cx+ox*s+w*s-8*s, cy+oy*s+h*s-8*s], start=20, end=160, fill=BLACK, width=4)
    # head
    hx=cx+190*s
    hy=cy-10*s
    thick_ellipse(draw, [hx-80*s, hy-55*s, hx+70*s, hy+55*s], width=10, fill=BG)
    # muzzle
    thick_ellipse(draw, [hx+30*s, hy-6*s, hx+85*s, hy+32*s], width=8, fill=BG)
    # ears huge round
    thick_ellipse(draw, [hx-55*s, hy-78*s, hx-10*s, hy-28*s], width=8, fill=BG)
    thick_ellipse(draw, [hx+10*s, hy-82*s, hx+58*s, hy-30*s], width=8, fill=BG)
    # inner ear
    draw.ellipse([hx-42*s, hy-60*s, hx-22*s, hy-38*s], outline=BLACK, width=4)
    draw.ellipse([hx+22*s, hy-64*s, hx+42*s, hy-42*s], outline=BLACK, width=4)
    # legs
    for lx in [-120*s, -30*s, 60*s, 130*s]:
        draw.rectangle([cx+lx-28*s, cy+60*s, cx+lx+28*s, cy+200*s], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-30*s, cy+185*s, cx+lx+30*s, cy+210*s], width=7, fill=BG)
    # tail bushy with white tip
    draw.line([(cx-230*s, cy+30*s),(cx-295*s, cy+70*s)], fill=BLACK, width=11)
    thick_ellipse(draw, [cx-310*s, cy+55*s, cx-270*s, cy+85*s], width=8, fill=BG)
    thick_ellipse(draw, [cx-315*s, cy+60*s, cx-285*s, cy+88*s], width=5, fill=BG)

def draw_ostrich(draw, cx, cy, scale=1.0):
    s=scale
    # body big oval fluffy
    thick_ellipse(draw, [cx-210*s, cy-20*s, cx+80*s, cy+170*s], width=11, fill=BG)
    # feathers texture - wavy lines
    for yy in [-10*s, 20*s, 50*s, 80*s, 110*s]:
        draw.arc([cx-190*s, cy+yy, cx+60*s, cy+yy+40*s], start=180, end=0, fill=BLACK, width=5)
    # neck long S
    neck_pts = [(cx+20*s, cy-20*s),(cx+60*s, cy-90*s),(cx+80*s, cy-170*s)]
    for i in range(len(neck_pts)-1):
        draw.line([neck_pts[i], neck_pts[i+1]], fill=BLACK, width=18)
    # head small
    hx=cx+90*s
    hy=cy-200*s
    thick_ellipse(draw, [hx-55*s, hy-40*s, hx+55*s, hy+40*s], width=9, fill=BG)
    # beak
    draw.polygon([(hx+40*s, hy-10*s),(hx+105*s, hy+4*s),(hx+40*s, hy+18*s)], outline=BLACK, width=8, fill=BG)
    # eye large
    thick_ellipse(draw, [hx-10*s, hy-18*s, hx+28*s, hy+12*s], width=7, fill=BG)
    draw.ellipse([hx+4*s, hy-8*s, hx+18*s, hy+4*s], fill=BLACK)
    draw.ellipse([hx+6*s, hy-6*s, hx+12*s, hy+0*s], fill=BG)
    # legs very long scaly
    for lx in [-60*s, 20*s]:
        draw.line([(cx+lx, cy+140*s),(cx+lx+16*s, cy+300*s)], fill=BLACK, width=16)
        # scales
        for sy in [170*s,200*s,230*s,260*s]:
            draw.line([(cx+lx-6*s, cy+sy),(cx+lx+22*s, cy+sy+6*s)], fill=BLACK, width=4)
        # foot with two toes
        thick_ellipse(draw, [cx+lx-30*s, cy+285*s, cx+lx+45*s, cy+315*s], width=8, fill=BG)
        draw.line([(cx+lx+10*s, cy+300*s),(cx+lx+55*s, cy+295*s)], fill=BLACK, width=8)
        draw.line([(cx+lx+10*s, cy+305*s),(cx+lx+45*s, cy+315*s)], fill=BLACK, width=8)
    # wings small
    thick_ellipse(draw, [cx-80*s, cy+30*s, cx+40*s, cy+110*s], width=9, fill=BG)
    # tail
    for i in range(5):
        draw.line([(cx-210*s+i*18*s, cy+80*s),(cx-230*s+i*18*s, cy+40*s)], fill=BLACK, width=5)

def draw_impala(draw, cx, cy, scale=1.0):
    s=scale
    thick_ellipse(draw, [cx-200*s, cy-30*s, cx+140*s, cy+110*s], width=11, fill=BG)
    # head slender
    hx=cx+170*s
    hy=cy-30*s
    thick_ellipse(draw, [hx-65*s, hy-50*s, hx+55*s, hy+50*s], width=9, fill=BG)
    # muzzle
    thick_ellipse(draw, [hx+30*s, hy+6*s, hx+75*s, hy+34*s], width=7, fill=BG)
    # horns lyre-shaped
    for ox in [-10*s, 10*s]:
        pts=[(hx+ox, hy-45*s),(hx+ox-8*s, hy-110*s),(hx+ox, hy-150*s)]
        draw.line(pts, fill=BLACK, width=9, joint="round")
        # ridges
        for ry in [-130*s,-110*s,-90*s]:
            draw.line([(hx+ox-10*s, hy+ry),(hx+ox+10*s, hy+ry+6*s)], fill=BLACK, width=5)
    # ears
    thick_ellipse(draw, [hx-45*s, hy-52*s, hx-15*s, hy-22*s], width=6, fill=BG)
    thick_ellipse(draw, [hx+15*s, hy-52*s, hx+45*s, hy-22*s], width=6, fill=BG)
    # legs slender leaping
    for lx, yy in [(-120*s, 70*s),(-50*s, 85*s),(40*s, 65*s),(110*s, 80*s)]:
        draw.line([(cx+lx, cy+70*s),(cx+lx+12*s, cy+yy+130*s)], fill=BLACK, width=11)
        thick_ellipse(draw, [cx+lx-14*s, cy+yy+120*s, cx+lx+26*s, cy+yy+145*s], width=6, fill=BG)
    # tail
    draw.line([(cx-200*s, cy+30*s),(cx-235*s, cy+70*s)], fill=BLACK, width=9)
    thick_ellipse(draw, [cx-245*s, cy+60*s, cx-225*s, cy+88*s], width=6, fill=BG)
    # side stripe
    draw.arc([cx-100*s, cy+30*s, cx+60*s, cy+90*s], start=0, end=180, fill=BLACK, width=6)
    # markings on face
    draw.line([(hx+10*s, hy-10*s),(hx+10*s, hy+18*s)], fill=BLACK, width=5)

def draw_hippo(draw, cx, cy, is_water=False, scale=1.0):
    s=scale
    # huge barrel body
    thick_ellipse(draw, [cx-310*s, cy-60*s, cx+250*s, cy+140*s], width=12, fill=BG)
    # head massive
    hx=cx+280*s
    hy=cy-10*s
    thick_ellipse(draw, [hx-110*s, hy-85*s, hx+90*s, hy+85*s], width=11, fill=BG)
    # nostrils on top
    for nx in [20*s, 60*s]:
        draw.ellipse([hx+nx-14*s, hy-78*s, hx+nx+14*s, hy-50*s], outline=BLACK, width=6, fill=BG)
        draw.ellipse([hx+nx-5*s, hy-68*s, hx+nx+5*s, hy-58*s], fill=BLACK)
    # ears small
    for ex in [-50*s, -10*s]:
        thick_ellipse(draw, [hx+ex-18*s, hy-88*s, hx+ex+18*s, hy-58*s], width=6, fill=BG)
    # eyes on top
    for ex in [-40*s, 0*s]:
        thick_ellipse(draw, [hx+ex-18*s, hy-42*s, hx+ex+18*s, hy-12*s], width=6, fill=BG)
        draw.ellipse([hx+ex-7*s, hy-30*s, hx+ex+7*s, hy-18*s], fill=BLACK)
    # mouth wide
    draw.line([(hx+30*s, hy+30*s),(hx+70*s, hy+55*s)], fill=BLACK, width=8)
    # legs short stumpy
    for lx in [-180*s, -70*s, 70*s, 180*s]:
        draw.rectangle([cx+lx-44*s, cy+70*s, cx+lx+44*s, cy+210*s], outline=BLACK, width=10, fill=BG)
        thick_ellipse(draw, [cx+lx-46*s, cy+195*s, cx+lx+46*s, cy+220*s], width=8, fill=BG)
    # if water, draw water line halfway
    if is_water:
        # water waves covering bottom half
        wy = cy+60*s
        draw.rectangle([0, wy, W, H], fill=BG, outline=None)
        # water surface wavy
        points=[]
        for x in range(0, W+10, 30):
            yy = wy + math.sin(x*0.02)*10
            points.append((x,yy))
        draw.line(points, fill=BLACK, width=10)
        # ripples
        for rx in [600, 1100, 1600]:
            draw.ellipse([rx-80, wy+30, rx+80, wy+50], outline=BLACK, width=5)
        # re-draw hippo upper part outline above water - already done, but need to clean lower
        # add small bird on hippo
        bird_x = cx+20*s
        bird_y = cy-90*s
        draw.ellipse([bird_x-30*s, bird_y-18*s, bird_x+30*s, bird_y+18*s], outline=BLACK, width=6, fill=BG)
        draw.polygon([(bird_x+22*s, bird_y-4*s),(bird_x+42*s, bird_y),(bird_x+22*s, bird_y+4*s)], outline=BLACK, width=5)

def draw_crocodile(draw, cx, cy, scale=1.0):
    s=scale
    # long body low
    thick_ellipse(draw, [cx-320*s, cy-10*s, cx+180*s, cy+110*s], width=11, fill=BG)
    # back scutes
    for sx in [-220*s, -160*s, -100*s, -40*s, 20*s, 80*s]:
        draw.polygon([(cx+sx, cy-10*s),(cx+sx+18*s, cy-30*s),(cx+sx+34*s, cy-10*s)], outline=BLACK, width=6, fill=BG)
    # head long flat
    hx=cx+220*s
    hy=cy+20*s
    draw.polygon([(hx-90*s, hy-35*s),(hx+110*s, hy-25*s),(hx+110*s, hy+25*s),(hx-90*s, hy+35*s)], outline=BLACK, width=10, fill=BG)
    # teeth
    for tx in [ -40*s, -10*s, 20*s, 50*s, 80*s]:
        draw.polygon([(hx+tx, hy+20*s),(hx+tx+8*s, hy+38*s),(hx+tx+16*s, hy+20*s)], outline=BLACK, width=5, fill=BG)
    # nostrils at tip
    draw.ellipse([hx+90*s, hy-10*s, hx+100*s, hy+0*s], fill=BLACK)
    draw.ellipse([hx+90*s, hy+8*s, hx+100*s, hy+18*s], fill=BLACK)
    # eyes on top
    thick_ellipse(draw, [hx-50*s, hy-45*s, hx-20*s, hy-20*s], width=6, fill=BG)
    draw.ellipse([hx-42*s, hy-38*s, hx-28*s, hy-24*s], fill=BLACK)
    # legs short sprawled
    for (lx, ly) in [(-140*s,70*s),(-20*s,80*s),(50*s,70*s),(130*s,80*s)]:
        draw.ellipse([cx+lx-34*s, cy+ly-18*s, cx+lx+34*s, cy+ly+18*s], outline=BLACK, width=8, fill=BG)
        draw.line([(cx+lx, cy+ly),(cx+lx-10*s, cy+ly+40*s)], fill=BLACK, width=7)
    # tail long tapering
    tail_pts=[(cx-320*s, cy+30*s),(cx-400*s, cy+20*s),(cx-460*s, cy+40*s),(cx-420*s, cy+70*s),(cx-330*s, cy+60*s)]
    draw.polygon(tail_pts, outline=BLACK, width=10, fill=BG)
    # tail segments
    for tx in [-380*s, -360*s, -340*s]:
        draw.line([(cx+tx, cy+25*s),(cx+tx+6*s, cy+65*s)], fill=BLACK, width=4)
    # water ripples below
    wy=cy+130*s
    for rx in [500, 900, 1400]:
        draw.ellipse([rx-70, wy, rx+70, wy+18], outline=BLACK, width=5)

def draw_eagle(draw, cx, cy, scale=1.0):
    s=scale
    # body
    thick_ellipse(draw, [cx-90*s, cy-40*s, cx+90*s, cy+110*s], width=11, fill=BG)
    # wings spread wide
    # left wing
    draw.polygon([(cx-90*s, cy-10*s),(cx-350*s, cy-80*s),(cx-370*s, cy-30*s),(cx-280*s, cy+40*s),(cx-110*s, cy+30*s)], outline=BLACK, width=11, fill=BG)
    # right wing mirrored
    draw.polygon([(cx+90*s, cy-10*s),(cx+350*s, cy-80*s),(cx+370*s, cy-30*s),(cx+280*s, cy+40*s),(cx+110*s, cy+30*s)], outline=BLACK, width=11, fill=BG)
    # wing feathers
    for wx in [-300*s, -250*s, -200*s, 200*s, 250*s, 300*s]:
        draw.line([(cx+wx, cy-50*s),(cx+wx+10*s, cy+20*s)], fill=BLACK, width=6)
    # head
    hx=cx
    hy=cy-80*s
    thick_ellipse(draw, [hx-55*s, hy-45*s, hx+55*s, hy+45*s], width=9, fill=BG)
    # beak hooked
    draw.polygon([(hx+30*s, hy-6*s),(hx+90*s, hy+8*s),(hx+30*s, hy+22*s)], outline=BLACK, width=8, fill=BG)
    draw.ellipse([hx+42*s, hy+0*s, hx+52*s, hy+10*s], fill=BLACK)
    # eye fierce
    thick_ellipse(draw, [hx+6*s, hy-14*s, hx+32*s, hy+8*s], width=6, fill=BG)
    draw.ellipse([hx+16*s, hy-6*s, hx+26*s, hy+4*s], fill=BLACK)
    # crest feathers
    for i in range(4):
        draw.line([(hx-10*s+i*10*s, hy-40*s),(hx-14*s+i*10*s, hy-62*s)], fill=BLACK, width=6)
    # legs talons extended
    for lx in [-22*s,22*s]:
        draw.line([(cx+lx, cy+90*s),(cx+lx*1.6, cy+155*s)], fill=BLACK, width=10)
        # talons
        draw.arc([cx+lx*1.6-18*s, cy+155*s-10*s, cx+lx*1.6+18*s, cy+155*s+18*s], start=200, end=360, fill=BLACK, width=7)
    # tail forked
    draw.polygon([(cx-45*s, cy+95*s),(cx-55*s, cy+150*s),(cx+0*s, cy+135*s),(cx+55*s, cy+150*s),(cx+45*s, cy+95*s)], outline=BLACK, width=9, fill=BG)
    for tx in [-30*s,0,30*s]:
        draw.line([(cx+tx, cy+105*s),(cx+tx, cy+145*s)], fill=BLACK, width=5)

def draw_secretarybird(draw, cx, cy, scale=1.0):
    s=scale
    # body upright
    thick_ellipse(draw, [cx-90*s, cy-30*s, cx+90*s, cy+110*s], width=11, fill=BG)
    # long legs crane-like
    for lx in [-30*s,30*s]:
        draw.line([(cx+lx, cy+90*s),(cx+lx+6*s, cy+290*s)], fill=BLACK, width=14)
        # scales
        for sy in [140*s,190*s,240*s]:
            draw.line([(cx+lx-8*s, cy+sy),(cx+lx+14*s, cy+sy+5*s)], fill=BLACK, width=4)
        thick_ellipse(draw, [cx+lx-28*s, cy+275*s, cx+lx+34*s, cy+300*s], width=7, fill=BG)
        # toes forward
        draw.line([(cx+lx+10*s, cy+290*s),(cx+lx+50*s, cy+285*s)], fill=BLACK, width=7)
        draw.line([(cx+lx+10*s, cy+290*s),(cx+lx+10*s, cy+315*s)], fill=BLACK, width=7)
    # neck
    draw.line([(cx, cy-30*s),(cx+10*s, cy-90*s)], fill=BLACK, width=16)
    # head
    hx=cx+15*s
    hy=cy-125*s
    thick_ellipse(draw, [hx-55*s, hy-40*s, hx+55*s, hy+40*s], width=9, fill=BG)
    # crest quills
    for i in range(6):
        draw.line([(hx-20*s+i*9*s, hy-30*s),(hx-30*s+i*10*s, hy-66*s)], fill=BLACK, width=6)
    # beak short hooked
    draw.polygon([(hx+30*s, hy-8*s),(hx+70*s, hy+4*s),(hx+30*s, hy+14*s)], outline=BLACK, width=7, fill=BG)
    # eye
    thick_ellipse(draw, [hx+6*s, hy-12*s, hx+30*s, hy+10*s], width=6, fill=BG)
    draw.ellipse([hx+14*s, hy-6*s, hx+24*s, hy+4*s], fill=BLACK)
    # eyelashes
    draw.line([(hx+8*s, hy-12*s),(hx+26*s, hy-16*s)], fill=BLACK, width=3)
    # wings folded
    thick_ellipse(draw, [cx-85*s, cy+10*s, cx+0*s, cy+80*s], width=8, fill=BG)
    thick_ellipse(draw, [cx+0*s, cy+10*s, cx+85*s, cy+80*s], width=8, fill=BG)
    # tail long
    draw.line([(cx-10*s, cy+100*s),(cx-30*s, cy+160*s)], fill=BLACK, width=10)
    draw.line([(cx+10*s, cy+100*s),(cx+30*s, cy+160*s)], fill=BLACK, width=10)
    thick_ellipse(draw, [cx-40*s, cy+155*s, cx+40*s, cy+180*s], width=7, fill=BG)

def draw_hornbill(draw, cx, cy, scale=1.0):
    s=scale
    # body plump
    thick_ellipse(draw, [cx-130*s, cy-40*s, cx+110*s, cy+110*s], width=11, fill=BG)
    # wing
    thick_ellipse(draw, [cx-90*s, cy+10*s, cx+50*s, cy+90*s], width=9, fill=BG)
    # feathers
    for wx in [-60*s, -30*s, 0*s, 20*s]:
        draw.line([(cx+wx, cy+20*s),(cx+wx+10*s, cy+70*s)], fill=BLACK, width=5)
    # head large
    hx=cx+90*s
    hy=cy-60*s
    thick_ellipse(draw, [hx-65*s, hy-50*s, hx+65*s, hy+50*s], width=10, fill=BG)
    # huge casque and beak
    # upper casque
    draw.polygon([(hx-10*s, hy-45*s),(hx+60*s, hy-60*s),(hx+85*s, hy-30*s),(hx+10*s, hy-20*s)], outline=BLACK, width=9, fill=BG)
    # lower beak
    draw.polygon([(hx+20*s, hy-6*s),(hx+130*s, hy+6*s),(hx+20*s, hy+22*s)], outline=BLACK, width=9, fill=BG)
    # nostril
    draw.ellipse([hx+10*s, hy-10*s, hx+22*s, hy+0*s], outline=BLACK, width=5)
    # eye
    thick_ellipse(draw, [hx-18*s, hy-12*s, hx+12*s, hy+12*s], width=6, fill=BG)
    draw.ellipse([hx-8*s, hy-6*s, hx+4*s, hy+6*s], fill=BLACK)
    # tail long
    draw.line([(cx-130*s, cy+50*s),(cx-180*s, cy+90*s)], fill=BLACK, width=11)
    thick_ellipse(draw, [cx-200*s, cy+80*s, cx-160*s, cy+110*s], width=8, fill=BG)
    # legs short
    for lx in [-30*s,20*s]:
        draw.line([(cx+lx, cy+95*s),(cx+lx, cy+150*s)], fill=BLACK, width=11)
        draw.line([(cx+lx-18*s, cy+145*s),(cx+lx+18*s, cy+145*s)], fill=BLACK, width=7)

def draw_flamingos(draw, cx, cy, scale=1.0):
    s=scale
    # draw 3 flamingos at different heights to create flock
    positions = [(cx-280*s, cy+40*s, 0.9),(cx, cy+20*s, 1.0),(cx+280*s, cy+50*s, 0.85)]
    for (fx, fy, sc) in positions:
        sc2=sc*s
        # body oval sideways
        thick_ellipse(draw, [fx-80*sc2, fy-20*sc2, fx+60*sc2, fy+60*sc2], width=9, fill=BG)
        # neck S curvy - iconic
        neck_pts = [(fx+20*sc2, fy-20*sc2),(fx+30*sc2, fy-80*sc2),(fx-10*sc2, fy-120*sc2),(fx+10*sc2, fy-170*sc2)]
        for i in range(len(neck_pts)-1):
            draw.line([neck_pts[i], neck_pts[i+1]], fill=BLACK, width=int(14*sc2))
        # head
        hx = fx+10*sc2
        hy = fy-190*sc2
        thick_ellipse(draw, [hx-30*sc2, hy-22*sc2, hx+30*sc2, hy+22*sc2], width=7, fill=BG)
        # beak bent
        draw.polygon([(hx+18*sc2, hy-6*sc2),(hx+50*sc2, hy+2*sc2),(hx+18*sc2, hy+12*sc2)], outline=BLACK, width=6, fill=BG)
        draw.line([(hx+28*sc2, hy+0*sc2),(hx+38*sc2, hy+4*sc2)], fill=BLACK, width=5)
        # eye
        draw.ellipse([hx-6*sc2, hy-8*sc2, hx+10*sc2, hy+4*sc2], fill=BLACK)
        # legs thin long
        for lx in [-12*sc2,12*sc2]:
            draw.line([(fx+lx, fy+50*sc2),(fx+lx*0.5, fy+200*sc2)], fill=BLACK, width=7)
            draw.line([(fx+lx*0.5, fy+195*sc2),(fx+lx*0.5+22*sc2, fy+192*sc2)], fill=BLACK, width=5)
        # wing feather
        draw.arc([fx-60*sc2, fy+0*sc2, fx+30*sc2, fy+40*sc2], start=0, end=180, fill=BLACK, width=5)
    # water line
    wy=cy+200*s
    draw.line([(200, wy),(W-200, wy)], fill=BLACK, width=8)
    for rx in [600,1200,1800]:
        draw.ellipse([rx-60, wy-8, rx+60, wy+8], outline=BLACK, width=4)

def draw_chameleon(draw, cx, cy, scale=1.0):
    s=scale
    # branch horizontal
    draw.line([(300, cy+30*s),(W-300, cy+30*s)], fill=BLACK, width=16)
    for bx in [600,1000,1400,1800]:
        draw.line([(bx, cy+30*s),(bx-14*s, cy+55*s)], fill=BLACK, width=6)
    # body arched
    thick_ellipse(draw, [cx-150*s, cy-60*s, cx+110*s, cy+40*s], width=10, fill=BG)
    # back crest spikes
    for sx in [-110*s, -70*s, -30*s, 10*s, 50*s]:
        draw.polygon([(cx+sx, cy-60*s),(cx+sx+10*s, cy-95*s),(cx+sx+22*s, cy-60*s)], outline=BLACK, width=6, fill=BG)
    # head with helmet casque
    hx=cx+130*s
    hy=cy-40*s
    draw.polygon([(hx-50*s, hy-35*s),(hx-20*s, hy-65*s),(hx+20*s, hy-65*s),(hx+40*s, hy-20*s),(hx+30*s, hy+25*s),(hx-50*s, hy+15*s)], outline=BLACK, width=10, fill=BG)
    # eye turret large independently rotating
    thick_ellipse(draw, [hx-18*s, hy-18*s, hx+32*s, hy+32*s], width=8, fill=BG)
    # eye concentric circles
    draw.ellipse([hx-6*s, hy-6*s, hx+20*s, hy+20*s], outline=BLACK, width=6)
    draw.ellipse([hx+4*s, hy+4*s, hx+12*s, hy+12*s], fill=BLACK)
    # mouth
    draw.line([(hx+20*s, hy+12*s),(hx+45*s, hy+6*s)], fill=BLACK, width=6)
    # legs gripping branch
    for lx in [-80*s,20*s]:
        draw.ellipse([cx+lx-30*s, cy-10*s, cx+lx+30*s, cy+35*s], outline=BLACK, width=8, fill=BG)
        draw.line([(cx+lx, cy+25*s),(cx+lx-12*s, cy+50*s)], fill=BLACK, width=7)
        draw.line([(cx+lx, cy+25*s),(cx+lx+12*s, cy+50*s)], fill=BLACK, width=7)
    # tail curled spiral
    tail_cx = cx-150*s
    tail_cy = cy-10*s
    # spiral
    for i, r in enumerate([55*s,42*s,32*s,22*s,14*s]):
        ang = 180 + i*55
        rad=math.radians(ang)
        x=tail_cx+math.cos(rad)*r
        y=tail_cy+math.sin(rad)*r
        draw.ellipse([x-r, y-r, x+r, y+r], outline=BLACK, width=7)
    # tail line connecting
    draw.line([(cx-150*s, cy+0*s),(tail_cx+55*s, tail_cy)], fill=BLACK, width=10)

def draw_tortoise(draw, cx, cy, scale=1.0):
    s=scale
    # shell dome high
    thick_ellipse(draw, [cx-220*s, cy-70*s, cx+220*s, cy+110*s], width=12, fill=BG)
    # shell pattern - hex-like scutes
    # central line
    for (ox,oy,w,h) in [(-100,-30,90,70),(-10,-40,90,75),(80,-25,80,60),(-70,40,80,50),(20,30,80,50)]:
        draw.polygon([(cx+ox,cy+oy),(cx+ox+w,cy+oy),(cx+ox+w-12,cy+oy+h),(cx+ox-8,cy+oy+h)], outline=BLACK, width=6, fill=BG)
        # inner
        draw.polygon([(cx+ox+12,cy+oy+12),(cx+ox+w-12,cy+oy+12),(cx+ox+w-18,cy+oy+h-8),(cx+ox+4,cy+oy+h-8)], outline=BLACK, width=4)
    # head
    hx=cx+240*s
    hy=cy+10*s
    thick_ellipse(draw, [hx-55*s, hy-40*s, hx+55*s, hy+40*s], width=9, fill=BG)
    # nostrils
    draw.ellipse([hx+28*s, hy-4*s, hx+38*s, hy+6*s], fill=BLACK)
    draw.ellipse([hx+28*s, hy+12*s, hx+38*s, hy+22*s], fill=BLACK)
    # eye
    thick_ellipse(draw, [hx-12*s, hy-16*s, hx+14*s, hy+6*s], width=6, fill=BG)
    draw.ellipse([hx-4*s, hy-8*s, hx+6*s, hy+2*s], fill=BLACK)
    # legs stumpy elephantine
    for lx in [-140*s, -40*s, 60*s]:
        draw.ellipse([cx+lx-44*s, cy+70*s, cx+lx+44*s, cy+140*s], outline=BLACK, width=9, fill=BG)
        # claws
        for clx in [-18*s,6*s,30*s]:
            draw.polygon([(cx+lx+clx, cy+125*s),(cx+lx+clx+10*s, cy+145*s),(cx+lx+clx-4*s, cy+145*s)], outline=BLACK, width=5, fill=BG)
    # tail short
    draw.ellipse([cx-220*s, cy+30*s, cx-190*s, cy+60*s], outline=BLACK, width=7, fill=BG)
    # plants around
    for px in [400, W-500]:
        for i in range(3):
            draw.line([(px+i*18*s, cy+110*s),(px+i*18*s-10*s, cy+55*s)], fill=BLACK, width=5)
        draw.ellipse([px-30*s, cy+40*s, px+50*s, cy+70*s], outline=BLACK, width=5, fill=BG)

def draw_pangolin(draw, cx, cy, scale=1.0):
    s=scale
    # body curled slightly
    thick_ellipse(draw, [cx-200*s, cy-50*s, cx+180*s, cy+110*s], width=11, fill=BG)
    # scales overlapping
    for row in range(3):
        for col in range(5):
            sx = cx-150*s + col*65*s + (row*12*s)
            sy = cy-30*s + row*45*s
            # scale shape - like leaf
            draw.polygon([(sx, sy),(sx+32*s, sy-18*s),(sx+52*s, sy),(sx+32*s, sy+18*s)], outline=BLACK, width=6, fill=BG)
    # head small pointed
    hx=cx+200*s
    hy=cy-10*s
    draw.polygon([(hx-30*s, hy-25*s),(hx+40*s, hy-10*s),(hx+40*s, hy+10*s),(hx-30*s, hy+25*s)], outline=BLACK, width=9, fill=BG)
    # eye
    draw.ellipse([hx-12*s, hy-8*s, hx+2*s, hy+6*s], fill=BLACK)
    # tail long scaled curled
    for i, (tx, ty, scw, sch) in enumerate([(-210,20,70,40),(-270,30,65,38),(-310,45,55,34),(-340,62,44,30)]):
        draw.polygon([(cx+tx*s, cy+ty*s),(cx+tx*s+scw*s, cy+ty*s-10*s),(cx+tx*s+scw*s, cy+ty*s+10*s),(cx+tx*s, cy+ty*s+18*s)], outline=BLACK, width=6, fill=BG)
    # legs small
    for lx in [-80*s,20*s]:
        draw.ellipse([cx+lx-28*s, cy+70*s, cx+lx+28*s, cy+120*s], outline=BLACK, width=8, fill=BG)
        draw.line([(cx+lx, cy+110*s),(cx+lx, cy+135*s)], fill=BLACK, width=7)

def draw_landscape_acacia():
    img, d = new_canvas()
    add_border(d)
    ground_line(d, y=2750)
    acacia_tree(d, x=480, y=2750, scale=1.45)
    acacia_tree(d, x=1450, y=2750, scale=1.15)
    acacia_tree(d, x=2050, y=2750, scale=0.85)
    sun(d, x=2120, y=500, r=125)
    clouds(d)
    # distant hills
    d.arc([ -300, 2100, 1400, 2700], start=180, end=0, fill=BLACK, width=8)
    d.arc([ 900, 2150, 2600, 2750], start=180, end=0, fill=BLACK, width=8)
    # small animals silhouettes distant
    for (ax,ay,sc) in [(800, 2580, 0.32),(1150, 2600,0.28),(1700,2590,0.30)]:
        draw_giraffe_small(d, ax, ay, sc)
    draw_title(d, "Acacia Trees of the Savannah")
    return img

def draw_giraffe_small(draw, cx, cy, scale):
    s=scale
    draw.ellipse([cx-20*s, cy-10*s, cx+20*s, cy+10*s], outline=BLACK, width=3, fill=BG)
    draw.line([(cx+10*s, cy-10*s),(cx+15*s, cy-35*s)], fill=BLACK, width=3)
    draw.ellipse([cx+8*s, cy-42*s, cx+22*s, cy-28*s], outline=BLACK, width=2)

def draw_landscape_baobab():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2750)
    baobab_tree(d, x=1350, y=2750, scale=1.55)
    acacia_tree(d, x=480, y=2750, scale=0.85)
    sun(d, 2140, 520, 110)
    clouds(d)
    # elephants near baobab
    draw_elephant(d, cx=820, cy=2520, scale=0.42)
    draw_elephant(d, cx=620, cy=2550, scale=0.30)
    # birds on tree
    for bx, by in [(1330, 2180),(1380, 2140)]:
        d.ellipse([bx-18, by-10, bx+18, by+10], outline=BLACK, width=5, fill=BG)
        d.line([(bx+14, by),(bx+28, by+4)], fill=BLACK, width=4)
    draw_title(d, "The Mighty Baobab Tree")
    return img

def draw_watering_hole():
    img,d=new_canvas()
    add_border(d)
    water_hole(d, y=2450)
    # animals around: elephant drinking, giraffe drinking, zebras, birds
    draw_elephant(d, cx=650, cy=2120, scale=0.52)
    # trunk down to water
    d.line([(650+60*0.52, 2120+40*0.52),(700, 2430)], fill=BLACK, width=12)
    draw_giraffe(d, cx=1320, cy=2180, scale=0.58)
    # giraffe neck bent to water
    d.line([(1320+75*0.58, 2180-110*0.58),(1180, 2420)], fill=BLACK, width=12)
    draw_zebra(d, cx=1920, cy=2220, scale=0.48)
    # birds
    for bx in [1050, 1250]:
        d.ellipse([bx-22, 2360-12, bx+22, 2360+12], outline=BLACK, width=5)
        d.line([(bx,2352),(bx+18,2335)], fill=BLACK, width=4)
    acacia_tree(d, 320, 2450, 0.75)
    acacia_tree(d, 2240, 2450, 0.62)
    draw_title(d, "Watering Hole Gathering")
    return img

def draw_grasslands():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2760)
    # tall grass tufts foreground
    for gx in [250, 480, 700, 920, 1250, 1480, 1720, 1950, 2200]:
        for i in range(3):
            d.line([(gx+i*14, 2760),(gx+i*14-12, 2660+i*8)], fill=BLACK, width=6)
    # rolling hills
    d.arc([-400, 2050, 1300, 2700], start=180, end=0, fill=BLACK, width=8)
    d.arc([800, 2100, 2700, 2760], start=180, end=0, fill=BLACK, width=8)
    # wildlife dots distant
    for (ax,ay,sc) in [(600,2620,0.28),(900,2600,0.25),(1400,2610,0.30),(1800,2595,0.26)]:
        d.ellipse([ax-16, ay-10, ax+16, ay+10], outline=BLACK, width=4)
        d.line([(ax+8, ay-8),(ax+14, ay-22)], fill=BLACK, width=3)
    sun(d, 2100, 520, 115)
    clouds(d)
    # butterflies
    for bx,by in [(720, 1100),(1480, 1000)]:
        thick_ellipse(d, [bx-32, by-16, bx+32, by+16], width=6, fill=BG)
        for ox in [-18,18]:
            thick_ellipse(d, [bx+ox-22, by-28, bx+ox+22, by+28], width=5, fill=BG)
        d.line([(bx, by-12),(bx, by+12)], fill=BLACK, width=5)
    draw_title(d, "Golden African Grasslands")
    return img

def draw_riverbank():
    img,d=new_canvas()
    add_border(d)
    # river
    d.rectangle([0, 2350, W, 2700], outline=BLACK, width=10, fill=BG)
    d.line([(0,2420),(W,2420)], fill=BLACK, width=6)
    for rx in [600,1100,1600]:
        d.ellipse([rx-50,2390,rx+50,2405], outline=BLACK, width=4)
        d.ellipse([rx-35,2430,rx+35,2442], outline=BLACK, width=4)
    # hippos in water
    draw_hippo(d, cx=850, cy=2360, is_water=False, scale=0.55)
    draw_hippo(d, cx=1550, cy=2380, is_water=False, scale=0.48)
    # croc on bank
    draw_crocodile(d, cx=1200, cy=2680, scale=0.45)
    # birds: fish eagle on branch overhanging
    d.line([(420,2100),(680,2250)], fill=BLACK, width=12)
    draw_eagle(d, cx=520, cy=2020, scale=0.38)
    # reeds
    for rx in [280, 340, 400, 2100, 2160, 2220]:
        d.line([(rx,2350),(rx-8,2200)], fill=BLACK, width=7)
        d.line([(rx,2200),(rx+12,2160)], fill=BLACK, width=4)
    # hippo nostrils above water
    d.ellipse([850-12,2360-78*0.55,850+12,2360-50*0.55], outline=BLACK, width=4)
    draw_title(d, "Riverbank with Hippos and Birds")
    return img

def draw_kopjes():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2760)
    rocks(d, x=1280, y=2520)
    # lions resting on rocks
    draw_lion(d, cx=1250, cy=2220, scale=0.52, facing=1)
    draw_lion(d, cx=870, cy=2300, scale=0.36, facing=-1)
    acacia_tree(d, 360, 2760, 0.82)
    sun(d, 2100, 520, 112)
    clouds(d)
    draw_title(d, "Rocky Kopjes — Lion Lookout")
    return img

def draw_waterfall():
    img,d=new_canvas()
    add_border(d)
    # waterfall cliffs
    d.rectangle([900, 900, W-900, 2400], outline=BLACK, width=12, fill=BG)
    # cliff texture
    for yy in [1100,1300,1500,1700,1900]:
        d.line([(920, yy),(W-920, yy+12)], fill=BLACK, width=5)
    # water falling
    for wx in [1020,1180,1340,1480,1640]:
        d.line([(wx, 900),(wx-14, 2400)], fill=BLACK, width=9)
        d.line([(wx+8, 900),(wx-6, 2400)], fill=BLACK, width=5)
    # pool at bottom
    d.ellipse([700, 2380, W-700, 2560], outline=BLACK, width=10, fill=BG)
    d.ellipse([900, 2420, W-900, 2520], outline=BLACK, width=5)
    # lush vegetation around
    for vx, vy in [(680,2450),(W-680,2450),(580,2100),(W-580,2100)]:
        for i in range(4):
            d.line([(vx+i*16, vy),(vx+i*16-12, vy-90-i*10)], fill=BLACK, width=6)
        d.ellipse([vx-40, vy-100, vx+60, vy-60], outline=BLACK, width=6, fill=BG)
    # birds
    for bx,by in [(650, 800),(1750, 850)]:
        d.line([(bx-30, by),(bx, by+12),(bx+30, by)], fill=BLACK, width=6)
    draw_title(d, "Waterfall in Lush Vegetation")
    return img

def draw_sunrise():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2720)
    sun(d, 1280, 680, 165)
    # sun rays long
    for ang in range(0,360,28):
        if 70 < ang < 290: continue
        rad=math.radians(ang)
        x1=1280+math.cos(rad)*175
        y1=680+math.sin(rad)*175
        x2=1280+math.cos(rad)*340
        y2=680+math.sin(rad)*340
        d.line([(x1,y1),(x2,y2)], fill=BLACK, width=7)
    # silhouetted giraffes walking toward sunrise - as outlines but simple
    for (gx, sc) in [(620,0.52),(980,0.60),(1480,0.56),(1920,0.48)]:
        # silhouette style - filled outline but we keep line art: just giraffe outline
        draw_giraffe(d, cx=gx, cy=2510, scale=sc)
    # acacias silhouettes
    acacia_tree(d, 360, 2720, 0.72)
    acacia_tree(d, 2200, 2720, 0.62)
    draw_title(d, "Peaceful Safari Sunrise")
    return img

def draw_forest():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2760)
    # dense forest - many tall trees with foliage
    for tx in [380, 620, 860, 1420, 1680, 1920, 2160]:
        th=random.randint(520,680)
        d.line([(tx,2760),(tx+random.randint(-18,18),2760-th)], fill=BLACK, width=22)
        # canopy
        cr=random.randint(110,150)
        d.ellipse([tx-cr,2760-th-cr//2, tx+cr,2760-th+cr//2], outline=BLACK, width=10, fill=BG)
        d.ellipse([tx-cr+30,2760-th-cr, tx+cr-20,2760-th-cr+40], outline=BLACK, width=8, fill=BG)
    # forest floor plants
    for px in [500, 1100, 1750]:
        for i in range(5):
            d.line([(px+i*14,2760),(px+i*14-16,2680)], fill=BLACK, width=5)
    # gorilla family
    draw_gorilla(d, cx=1120, cy=2520, scale=0.62)
    draw_gorilla(d, cx=840, cy=2560, scale=0.38)
    # okapi hidden
    d.ellipse([W-520, 2580-30, W-380, 2580+30], outline=BLACK, width=6, fill=BG)
    draw_title(d, "African Rainforest Canopy")
    return img

def draw_gorilla(draw, cx, cy, scale=1.0):
    s=scale
    # bulky body
    thick_ellipse(draw, [cx-140*s, cy-40*s, cx+140*s, cy+110*s], width=10, fill=BG)
    # chest
    thick_ellipse(draw, [cx-90*s, cy-10*s, cx+90*s, cy+80*s], width=7, fill=BG)
    # head large with crest
    hx=cx
    hy=cy-60*s
    thick_ellipse(draw, [hx-75*s, hy-55*s, hx+75*s, hy+55*s], width=10, fill=BG)
    # sagittal crest
    draw.arc([hx-45*s, hy-70*s, hx+45*s, hy-25*s], start=180, end=0, fill=BLACK, width=9)
    # brow ridge
    draw.line([(hx-50*s, hy-12*s),(hx+50*s, hy-12*s)], fill=BLACK, width=8)
    # nostrils large
    thick_ellipse(draw, [hx-22*s, hy+6*s, hx-6*s, hy+22*s], width=5, fill=BG)
    thick_ellipse(draw, [hx+6*s, hy+6*s, hx+22*s, hy+22*s], width=5, fill=BG)
    draw.ellipse([hx-16*s, hy+10*s, hx-9*s, hy+16*s], fill=BLACK)
    draw.ellipse([hx+9*s, hy+10*s, hx+16*s, hy+16*s], fill=BLACK)
    # eyes deep set
    for ex in [-26*s,26*s]:
        thick_ellipse(draw, [hx+ex-18*s, hy-18*s, hx+ex+18*s, hy+6*s], width=6, fill=BG)
        draw.ellipse([hx+ex-7*s, hy-8*s, hx+ex+7*s, hy+2*s], fill=BLACK)
    # arms long
    thick_ellipse(draw, [cx-155*s, cy+10*s, cx-95*s, cy+140*s], width=9, fill=BG)
    thick_ellipse(draw, [cx+95*s, cy+10*s, cx+155*s, cy+140*s], width=9, fill=BG)
    # legs
    for lx in [-60*s,60*s]:
        draw.ellipse([cx+lx-42*s, cy+90*s, cx+lx+42*s, cy+160*s], outline=BLACK, width=9, fill=BG)
        thick_ellipse(draw, [cx+lx-38*s, cy+145*s, cx+lx+38*s, cy+170*s], width=7, fill=BG)

def draw_safari_panorama():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2740)
    # horizon hills
    d.arc([-300,2080,1400,2680], start=180, end=0, fill=BLACK, width=8)
    d.arc([800,2120,2700,2750], start=180, end=0, fill=BLACK, width=8)
    # scattered acacias
    acacia_tree(d, 400, 2740, 0.68)
    acacia_tree(d, 2100, 2740, 0.58)
    baobab_tree(d, 1350, 2740, 0.82)
    sun(d, 2120, 520, 105)
    clouds(d)
    # panorama animals - many small across scene
    draw_elephant(d, cx=650, cy=2500, scale=0.38)
    draw_giraffe(d, cx=980, cy=2520, scale=0.36)
    draw_zebra(d, cx=1280, cy=2540, scale=0.32)
    draw_lion(d, cx=1680, cy=2530, scale=0.36, facing=1)
    draw_rhino(d, cx=1950, cy=2550, scale=0.30)
    draw_ostrich(d, cx=420, cy=2530, scale=0.32)
    # birds in sky
    for bx,by in [(700,820),(1050,760),(1500,800)]:
        d.line([(bx-28,by),(bx,by+10),(bx+28,by)], fill=BLACK, width=6)
    draw_title(d, "Safari Panorama — All Together!")
    return img


# ==================== BABY / FAMILY SCENES ====================

def draw_baby_scene_elephant():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2720)
    acacia_tree(d, 420, 2720, 0.92)
    draw_elephant(d, cx=1080, cy=2450, scale=0.95)
    draw_elephant(d, cx=1650, cy=2520, scale=0.48) # calf beside mother, trunk touching
    d.line([(1080+60*0.95,2450+40*0.95),(1650-40*0.48,2520-10*0.48)], fill=BLACK, width=8)
    sun(d, 2120, 540, 105)
    draw_title(d, "Elephant Mother and Calf — Walking Together")
    return img

def draw_baby_scene_lion():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2730)
    rocks(d, 1280, 2560)
    draw_lion(d, cx=1120, cy=2330, scale=0.62, facing=1) # lioness
    # cubs playing
    for (cx,cy,sc,fac) in [(1520,2450,0.42,1),(1380,2500,0.36,-1),(860,2470,0.38,1)]:
        draw_lion(d, cx=cx, cy=cy, scale=sc, facing=fac)
        # playful pounce
        d.ellipse([cx-18*sc, cy+65*sc, cx+18*sc, cy+85*sc], outline=BLACK, width=4, fill=BG)
    acacia_tree(d, 360, 2730, 0.72)
    draw_title(d, "Lion Cubs Playing Together")
    return img

def draw_baby_scene_giraffe():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2740)
    acacia_tree(d, 420, 2740, 1.1)
    draw_giraffe(d, cx=1080, cy=2400, scale=0.92)
    # baby giraffe beside adult, neck nuzzling
    draw_giraffe(d, cx=1680, cy=2520, scale=0.52)
    # adult bending neck to baby
    d.line([(1080+60*0.92,2400-20*0.92),(1680-20*0.52,2520-80*0.52)], fill=BLACK, width=7)
    sun(d, 2120, 540, 108)
    draw_title(d, "Baby Giraffe Beside Mother")
    return img

def draw_baby_scene_zebra():
    img,d=new_canvas()
    add_border(d)
    ground_line(d, y=2720)
    draw_zebra(d, cx=1020, cy=2370, scale=0.78)
    draw_zebra(d, cx=1580, cy=2470, scale=0.48)
    # foal stripes slightly different - wavy
    # already drawn
    acacia_tree(d, 380, 2720, 0.78)
    sun(d, 2140, 540, 110)
    clouds(d)
    draw_title(d, "Zebra Foal with Mother")
    return img

def draw_baby_scene_rhino():
    img,d=new_canvas()
    add_border(d)
    ground_line(d,y=2720)
    water_hole(d, y=2480)
    draw_rhino(d, cx=960, cy=2200, scale=0.72)
    draw_rhino(d, cx=1520, cy=2320, scale=0.44)
    # mother nuzzling calf
    d.line([(960+80*0.72,2200-10*0.72),(1520-40*0.44,2320-10*0.44)], fill=BLACK, width=7)
    acacia_tree(d, 380, 2720, 0.62)
    draw_title(d, "Baby Rhinos with Mother — White Rhinoceros")
    return img

def draw_baby_scene_monkeys():
    img,d=new_canvas()
    add_border(d)
    # tree with branches
    d.line([(1280,2720),(1280,1800)], fill=BLACK, width=28)
    for (bx,by,ang) in [(1280,2100,-28),(1280,1960,32)]:
        rad=math.radians(ang)
        x2=bx+math.cos(rad)*320
        y2=by+math.sin(rad)*120
        d.line([(bx,by),(x2,y2)], fill=BLACK, width=14)
        d.ellipse([x2-90, y2-55, x2+90, y2+55], outline=BLACK, width=10, fill=BG)
    # foliage clumps
    for fx,fy in [(520,1650),(900,1480),(1650,1520),(2020,1680)]:
        d.ellipse([fx-140,fy-80,fx+140,fy+80], outline=BLACK, width=10, fill=BG)
        d.ellipse([fx-90,fy-110,fx+90,fy+10], outline=BLACK, width=8, fill=BG)
    # monkeys
    for (mx,my,sc) in [(1080,2020,0.52),(1480,1980,0.48),(1280,2380,0.62),(860,2450,0.38)]:
        draw_monkey(d, mx, my, sc)
    ground_line(d, y=2720)
    draw_title(d, "Vervet Monkey Family in the Trees")
    return img

def draw_monkey(draw, cx, cy, scale):
    s=scale
    # body
    thick_ellipse(draw, [cx-60*s, cy-20*s, cx+60*s, cy+70*s], width=8, fill=BG)
    # head round with ears
    hx=cx
    hy=cy-45*s
    thick_ellipse(draw, [hx-55*s, hy-40*s, hx+55*s, hy+40*s], width=8, fill=BG)
    # face mask
    thick_ellipse(draw, [hx-32*s, hy-12*s, hx+32*s, hy+28*s], width=6, fill=BG)
    # ears big
    thick_ellipse(draw, [hx-66*s, hy-18*s, hx-40*s, hy+12*s], width=6, fill=BG)
    thick_ellipse(draw, [hx+40*s, hy-18*s, hx+66*s, hy+12*s], width=6, fill=BG)
    # eyes
    for ex in [-14*s,14*s]:
        draw.ellipse([hx+ex-10*s, hy-8*s, hx+ex+10*s, hy+8*s], fill=BLACK)
        draw.ellipse([hx+ex-3*s, hy-6*s, hx+ex+3*s, hy-0*s], fill=BG)
    # nose
    draw.ellipse([hx-6*s, hy+4*s, hx+6*s, hy+14*s], outline=BLACK, width=4)
    # arms
    for lx in [-45*s,45*s]:
        thick_ellipse(draw, [cx+lx-18*s, cy+6*s, cx+lx+18*s, cy+62*s], width=6, fill=BG)
    # tail long curled
    d=draw
    d.line([(cx-60*s, cy+40*s),(cx-95*s, cy+60*s),(cx-80*s, cy+90*s)], fill=BLACK, width=7)

def draw_baby_scene_gorilla_family():
    img,d=new_canvas()
    add_border(d)
    ground_line(d,y=2720)
    # forest behind
    for tx in [420, 2100]:
        d.line([(tx,2720),(tx,2100)], fill=BLACK, width=18)
        d.ellipse([tx-100,2100-60,tx+100,2100+60], outline=BLACK, width=9, fill=BG)
    draw_gorilla(d, cx=1180, cy=2480, scale=0.72)
    draw_gorilla(d, cx=820, cy=2560, scale=0.40)
    # baby clinging
    d.line([(820+30*0.4,2560-10*0.4),(1180-60*0.72,2480+20*0.72)], fill=BLACK, width=7)
    draw_title(d, "Gorilla Mother and Baby — Forest Family")
    return img


# ==================== MAIN GENERATOR ====================

ALL_TASKS = [
    # A. Big Five (5)
    ("01_lion_majestic", "African Lion — King of the Savannah", lambda d: (new_canvas()[0], new_canvas()[1]) and None), # placeholder filled below
]

# Proper task definitions as functions that return Image
def task_lion():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,400,2600,1.15); sun(d,2140,520,112); clouds(d); draw_lion(d,1280,2220,1.0,1); return img
def task_leopard():
    img,d=new_canvas(); add_border(d); # tree branch
    d.line([(300,1520),(W-300,1380)], fill=BLACK, width=22)
    d.line([(720,1520),(680,1650)], fill=BLACK, width=12)
    d.ellipse([280,1450,420,1550], outline=BLACK, width=9, fill=BG)
    d.ellipse([W-420,1310,W-280,1410], outline=BLACK, width=9, fill=BG)
    # foliage
    d.ellipse([340,1280,620,1420], outline=BLACK, width=10, fill=BG)
    d.ellipse([W-620,1160,W-340,1300], outline=BLACK, width=10, fill=BG)
    ground_line(d, y=2720); acacia_tree(d,480,2720,0.82); draw_leopard(d,1220,1320,0.96); return img
def task_elephant():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2600,1.08); acacia_tree(d,2100,2600,0.82); sun(d,2140,520,112); clouds(d); draw_elephant(d,1380,2220,1.06); return img
def task_buffalo():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,400,2600,0.92); water_hole(d, y=2480); draw_buffalo(d,1420,2220,1.02); return img
def task_rhino():
    img,d=new_canvas(); add_border(d); ground_line(d); water_hole(d, y=2500); acacia_tree(d,400,2720,0.78); sun(d,2140,520,108); draw_rhino(d,1380,2260,1.04); return img

def task_giraffe():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,520,2600,1.22); acacia_tree(d,2020,2600,0.88); sun(d,2140,520,112); clouds(d); draw_giraffe(d,1280,2220,1.02); return img
def task_zebra():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2600,0.92); sun(d,2140,520,110); clouds(d); draw_zebra(d,1320,2280,1.0); draw_zebra(d, 840, 2320, 0.82); return img
def task_cheetah():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2720,0.82); rocks(d, 1780,2520); sun(d,2140,520,108); draw_cheetah(d,1220,2280,1.02); return img
def task_hyena():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2600,0.88); rocks(d, 1820,2540); sun(d,2140,520,108); draw_hyena(d,1320,2300,0.98); return img
def task_warthog():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2720,0.82); water_hole(d, y=2460); draw_warthog(d,1320,2280,0.98); return img
def task_meerkat():
    img,d=new_canvas(); add_border(d); ground_line(d); rocks(d,1280,2500); sun(d,2140,520,110); draw_meerkat(d,1280,2220,1.0); return img
def task_wilddog():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2600,0.88); draw_wilddog(d,1320,2300,0.98); draw_wilddog(d, 820, 2340, 0.62); return img
def task_ostrich():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2600,0.92); sun(d,2140,520,110); clouds(d); draw_ostrich(d,1320,2280,1.02); return img
def task_impala():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2720,0.88); draw_impala(d,1320,2260,0.96); draw_impala(d, 820, 2320,0.58); return img
def task_hippo():
    img,d=new_canvas(); add_border(d); draw_hippo(d,1280,2180,is_water=True,scale=0.95); # water already in function
    acacia_tree(d,380,2600,0.72); acacia_tree(d,2180,2600,0.62); sun(d,2140,500,110); # keep water visuals
    return img

def task_eagle():
    img,d=new_canvas(); add_border(d); d.line([(420,2400),(780,2300)], fill=BLACK, width=14); d.line([(W-480,2400),(W-820,2300)], fill=BLACK, width=14); # lake edges
    d.ellipse([380,2380,W-380,2580], outline=BLACK, width=10, fill=BG); d.ellipse([560,2410,W-560,2540], outline=BLACK, width=6); water_hole(d,y=2400);
    draw_eagle(d,1280,1620,1.0); acacia_tree(d,380,2600,0.72); acacia_tree(d,2180,2600,0.62); sun(d,2140,520,105); return img
def task_secretary():
    img,d=new_canvas(); add_border(d); ground_line(d); acacia_tree(d,420,2720,0.82); sun(d,2140,520,108); clouds(d); draw_secretarybird(d,1280,2220,1.02); return img
def task_hornbill():
    img,d=new_canvas(); add_border(d); d.line([(720,1520),(W-720,1520)], fill=BLACK, width=18); d.ellipse([680,1450,820,1550], outline=BLACK, width=9); d.ellipse([W-820,1450,W-680,1550], outline=BLACK, width=9);
    d.ellipse([1080,1360,1480,1520], outline=BLACK, width=10, fill=BG); # foliage
    ground_line(d,y=2720); draw_hornbill(d,1280,1400,1.02); return img
def task_flamingos():
    img,d=new_canvas(); add_border(d); draw_flamingos(d,1280,1920,1.0); acacia_tree(d,380,2600,0.58); acacia_tree(d,2180,2600,0.52); sun(d,2140,520,108); return img
def task_croc():
    img,d=new_canvas(); add_border(d); draw_crocodile(d,1280,2220,1.04); acacia_tree(d,380,2720,0.68); sun(d,2140,520,108); return img
def task_chameleon():
    img,d=new_canvas(); add_border(d); draw_chameleon(d,1280,1750,1.02); ground_line(d,y=2720); d.ellipse([820,2200,1220,2360], outline=BLACK, width=9, fill=BG); d.ellipse([1320,2240,1720,2380], outline=BLACK, width=9, fill=BG); return img
def task_tortoise():
    img,d=new_canvas(); add_border(d); ground_line(d,y=2720); draw_tortoise(d,1280,2320,1.0); acacia_tree(d,380,2720,0.62); sun(d,2140,520,108); return img
def task_pangolin():
    img,d=new_canvas(); add_border(d); ground_line(d,y=2720); draw_pangolin(d,1320,2280,1.02); acacia_tree(d,380,2720,0.62); sun(d,2140,520,108); return img

TASKS = [
    # A - Big Five (5)
    ("01_lion", "African Lion — King of the Savannah", task_lion),
    ("02_leopard", "African Leopard — Spotted Climber", task_leopard),
    ("03_elephant", "African Bush Elephant — Gentle Giant", task_elephant),
    ("04_buffalo", "African Buffalo — Strong Herd Member", task_buffalo),
    ("05_rhino", "White Rhinoceros — Horned Grazer", task_rhino),
    # B - Savannah (10)
    ("06_giraffe", "Giraffe — Tallest Animal on Earth", task_giraffe),
    ("07_zebra", "Plains Zebra — Striped Beauty", task_zebra),
    ("08_cheetah", "Cheetah — Fastest Land Animal", task_cheetah),
    ("09_hyena", "Spotted Hyena — Laughing Hunter", task_hyena),
    ("10_warthog", "Warthog — Tusks and Warts", task_warthog),
    ("11_meerkat", "Meerkat Family — Standing Guard", task_meerkat),
    ("12_wilddog", "African Wild Dog — Painted Pack", task_wilddog),
    ("13_ostrich", "Ostrich — Giant Flightless Bird", task_ostrich),
    ("14_impala", "Impala — Graceful Leaper", task_impala),
    ("15_hippo", "Hippopotamus — River Giant", task_hippo),
    # C - Babies (7)
    ("16_elephant_calf", "Elephant Calf with Mother", draw_baby_scene_elephant),
    ("17_lion_cubs", "Lion Cubs at Play", draw_baby_scene_lion),
    ("18_baby_giraffe", "Baby Giraffe with Mother", draw_baby_scene_giraffe),
    ("19_zebra_foal", "Zebra Foal with Mother", draw_baby_scene_zebra),
    ("20_baby_rhino", "Baby Rhinos with Mother", draw_baby_scene_rhino),
    ("21_monkeys", "Vervet Monkey Family", draw_baby_scene_monkeys),
    ("22_gorilla_family", "Gorilla Family in the Forest", draw_baby_scene_gorilla_family),
    # D - Birds/Reptiles (8)
    ("23_fish_eagle", "African Fish Eagle — Sky Hunter", task_eagle),
    ("24_secretarybird", "Secretarybird — Striding Hunter", task_secretary),
    ("25_hornbill", "Southern Ground Hornbill — Big Beak", task_hornbill),
    ("26_flamingos", "Flamingos — Pink Wading Birds", task_flamingos),
    ("27_crocodile", "Nile Crocodile — River Predator", task_croc),
    ("28_chameleon", "Chameleon — Colour-Changing Climber", task_chameleon),
    ("29_tortoise", "Leopard Tortoise — Shelled Walker", task_tortoise),
    ("30_pangolin", "Pangolin — Scaly Anteater", task_pangolin),
    # E - Landscapes (10)
    ("31_acacia_savannah", "Acacia Trees on the Savannah", draw_landscape_acacia),
    ("32_baobab", "Baobab Tree — Tree of Life", draw_landscape_baobab),
    ("33_watering_hole", "Watering Hole Gathering", draw_watering_hole),
    ("34_grasslands", "African Grasslands — Wide and Golden", draw_grasslands),
    ("35_riverbank", "Riverbank with Hippos and Birds", draw_riverbank),
    ("36_kopjes", "Rocky Kopjes — Lion Lookout", draw_kopjes),
    ("37_waterfall", "Waterfall and Lush Vegetation", draw_waterfall),
    ("38_sunrise", "Peaceful Safari Sunrise", draw_sunrise),
    ("39_forest", "African Forest — Congo Rainforest", draw_forest),
    ("40_panorama", "Safari Panorama — All Together!", draw_safari_panorama),
]

def main():
    os.makedirs(OUT, exist_ok=True)
    # also need to re-create helper that draws title inside each task? Currently tasks don't call draw_title except landscapes.
    # Let's patch: we'll add title drawing wrapper
    for slug, title, func in TASKS:
        img = func()
        # add title if not already present - check by seeing if bottom area has text
        # we'll always ensure title at bottom
        d = ImageDraw.Draw(img)
        add_border(d)
        draw_title(d, title, y=H-260)
        # also page number small at bottom
        try:
            font_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        except:
            font_num = ImageFont.load_default()
        num = slug.split("_")[0]
        d.text((W-120, H-80), num, fill=BLACK, font=font_num)
        out_path = os.path.join(OUT, f"{slug}.png")
        img.save(out_path, "PNG", dpi=(300,300))
        print(f"Saved {out_path}  Title: {title}")

if __name__ == "__main__":
    main()
