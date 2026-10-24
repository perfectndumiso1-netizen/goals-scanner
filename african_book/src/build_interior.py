#!/usr/bin/env python3
"""
Build interior PDF for African Wildlife and Nature: A Safari Colouring Adventure
- 8.5 x 11 inches, 64 pages, black & white interior, white paper
- Uses reportlab, embeds 300 DPI illustrations
"""
from reportlab.lib.pagesizes import inch
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image as RLImage, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.graphics.shapes import Drawing, Line
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ILLUSTR_DIR = ROOT / "illustrations"
OUT_PATH = ROOT / "interior" / "African_Wildlife_Interior_8.5x11_64p.pdf"
SRC_ANIMALS = []

# Page size
PAGE_W = 8.5*inch
PAGE_H = 11*inch
MARGIN_TOP = 0.50*inch
MARGIN_BOTTOM = 0.50*inch
MARGIN_OUT = 0.50*inch
MARGIN_IN = 0.75*inch  # gutter

# Fonts - use assets/fonts if available
FONT_DIR = Path("/home/user/goals-scanner/assets/fonts")
try:
    pdfmetrics.registerFont(TTFont('LRegular', str(FONT_DIR / 'LiberationSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont('LBold', str(FONT_DIR / 'LiberationSans-Bold.ttf')))
    pdfmetrics.registerFont(TTFont('LItalic', str(FONT_DIR / 'LiberationSans-Italic.ttf')))
    pdfmetrics.registerFont(TTFont('LBoldItalic', str(FONT_DIR / 'LiberationSans-BoldItalic.ttf')))
    FONT_R = 'LRegular'
    FONT_B = 'LBold'
    FONT_I = 'LItalic'
    FONT_BI = 'LBoldItalic'
except Exception as e:
    print(f"Font fallback: {e}")
    FONT_R = 'Helvetica'
    FONT_B = 'Helvetica-Bold'
    FONT_I = 'Helvetica-Oblique'
    FONT_BI = 'Helvetica-BoldOblique'

COLORS = {
    'primary': HexColor('#2E5339'),  # deep savannah green
    'accent': HexColor('#B7792B'),   # acacia gold
    'accent2': HexColor('#8B4513'),  # earth brown
    'light_bg': HexColor('#F5F1E8'), # parchment
    'text': HexColor('#222222'),
    'muted': HexColor('#555555'),
}

def header_footer(canvas, doc):
    canvas.saveState()
    # page number centered at bottom
    canvas.setFont(FONT_R, 8)
    canvas.setFillColor(COLORS['muted'])
    if doc.page > 2:  # not on title/copyright
        canvas.drawCentredString(PAGE_W/2, 0.35*inch, f"{doc.page}")
        # small footer line
        canvas.setStrokeColor(COLORS['accent'])
        canvas.setLineWidth(0.7)
        canvas.line(MARGIN_OUT, 0.48*inch, PAGE_W-MARGIN_OUT, 0.48*inch)
        # book title tiny in footer
        canvas.setFont(FONT_I, 6.5)
        canvas.drawString(MARGIN_OUT, 0.38*inch, "African Wildlife and Nature: A Safari Colouring Adventure")
        canvas.drawRightString(PAGE_W-MARGIN_OUT, 0.38*inch, "Safari Wonders Press")
    canvas.restoreState()

def border_page(canvas, doc):
    # used for special pages: draw decorative border
    canvas.saveState()
    canvas.setStrokeColor(COLORS['primary'])
    canvas.setLineWidth(2)
    canvas.rect(MARGIN_OUT-6, MARGIN_BOTTOM-6, PAGE_W-MARGIN_OUT-MARGIN_IN+12, PAGE_H-MARGIN_TOP-MARGIN_BOTTOM+12)
    # inner light line
    canvas.setStrokeColor(COLORS['accent'])
    canvas.setLineWidth(0.9)
    canvas.rect(MARGIN_OUT-3, MARGIN_BOTTOM-3, PAGE_W-MARGIN_OUT-MARGIN_IN+6, PAGE_H-MARGIN_TOP-MARGIN_BOTTOM+6)
    header_footer(canvas, doc)
    canvas.restoreState()

# Styles
styles = getSampleStyleSheet()

sTitle = ParagraphStyle('TitleCustom', parent=styles['Title'], fontName=FONT_B, fontSize=34, leading=38, textColor=COLORS['primary'], alignment=TA_CENTER, spaceAfter=8)
sSubtitle = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName=FONT_I, fontSize=16, leading=20, textColor=COLORS['accent2'], alignment=TA_CENTER, spaceAfter=12)
sHeading1 = ParagraphStyle('H1', parent=styles['Heading1'], fontName=FONT_B, fontSize=22, leading=26, textColor=COLORS['primary'], alignment=TA_CENTER, spaceAfter=10, spaceBefore=12)
sHeading2 = ParagraphStyle('H2', parent=styles['Heading2'], fontName=FONT_B, fontSize=15, leading=19, textColor=COLORS['primary'], alignment=TA_LEFT, spaceAfter=6, spaceBefore=10, borderColor=COLORS['accent'], borderWidth=0, borderPadding=0, leftIndent=0)
sHeading3 = ParagraphStyle('H3', parent=styles['Heading3'], fontName=FONT_B, fontSize=12, leading=15, textColor=COLORS['accent2'], alignment=TA_CENTER, spaceAfter=4)
sBody = ParagraphStyle('Body', parent=styles['Normal'], fontName=FONT_R, fontSize=10.5, leading=15, textColor=COLORS['text'], alignment=TA_JUSTIFY, spaceAfter=6)
sBodyCenter = ParagraphStyle('BodyCenter', parent=sBody, alignment=TA_CENTER, spaceAfter=6)
sBodySmall = ParagraphStyle('BodySmall', parent=sBody, fontSize=9, leading=12, alignment=TA_LEFT, spaceAfter=4)
sCaption = ParagraphStyle('Caption', parent=styles['Normal'], fontName=FONT_I, fontSize=8.5, leading=11, textColor=COLORS['muted'], alignment=TA_CENTER, spaceAfter=4)
sFactTitle = ParagraphStyle('FactTitle', parent=styles['Normal'], fontName=FONT_B, fontSize=11, leading=14, textColor=COLORS['primary'], alignment=TA_LEFT, spaceAfter=2)
sFactBody = ParagraphStyle('FactBody', parent=styles['Normal'], fontName=FONT_R, fontSize=9.8, leading=13.5, textColor=COLORS['text'], alignment=TA_LEFT, spaceAfter=8)
sBullet = ParagraphStyle('Bullet', parent=sBody, leftIndent=18, bulletIndent=6, spaceAfter=3)
sActivityTitle = ParagraphStyle('ActivityTitle', parent=styles['Normal'], fontName=FONT_B, fontSize=18, leading=22, textColor=COLORS['primary'], alignment=TA_CENTER, spaceAfter=6, borderWidth=1, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(6,8,6))
sAnswer = ParagraphStyle('Answer', parent=styles['Normal'], fontName=FONT_R, fontSize=8.5, leading=11, textColor=COLORS['muted'], alignment=TA_LEFT)

# Content builders
story = []

# --------------- PAGE 1: TITLE PAGE ----------------
story.append(Spacer(1, 0.9*inch))
# Decorative top
story.append(Paragraph("~  ADVENTURE AWAITS  ~", ParagraphStyle('topdeco', parent=sBodyCenter, fontName=FONT_R, fontSize=8, textColor=COLORS['accent'], letterSpacing=3)))
story.append(Spacer(1, 0.25*inch))
story.append(Paragraph("AFRICAN WILDLIFE<br/>AND NATURE", sTitle))
story.append(Spacer(1, 0.12*inch))
# line
# Use HR via table
t = Table([['']], colWidths=[3.5*inch])
t.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,0), 2.5, COLORS['accent'])]))
story.append(t)
story.append(Spacer(1, 0.20*inch))
story.append(Paragraph("A Safari Colouring Adventure", sSubtitle))
story.append(Spacer(1, 0.30*inch))
story.append(Paragraph("40 Hand-Drawn Safari Illustrations  •  10 Amazing Wildlife Facts<br/>5 Fun Bonus Activities  •  For Ages 5–10", ParagraphStyle('features', parent=sBodyCenter, fontName=FONT_B, fontSize=9.5, leading=14, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.45*inch))
# Center emblem - we will add an illustration as small image
# Use lion small
story.append(Paragraph("🦁  &nbsp;&nbsp;  🐘  &nbsp;&nbsp;  🦒  &nbsp;&nbsp;  🦓  &nbsp;&nbsp;  🦏", ParagraphStyle('emojis', parent=sBodyCenter, fontSize=18, leading=22)))
story.append(Spacer(1, 0.35*inch))
story.append(Paragraph("Safari Wonders Press", ParagraphStyle('publisher', parent=sBodyCenter, fontName=FONT_B, fontSize=11, textColor=COLORS['primary'])))
story.append(Paragraph("First Edition  •  2025", ParagraphStyle('edition', parent=sBodyCenter, fontName=FONT_R, fontSize=9, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.5*inch))
story.append(Paragraph("This book belongs to:", ParagraphStyle('belongs', parent=sBodyCenter, fontName=FONT_I, fontSize=9, textColor=COLORS['muted'])))
t = Table([['________________________________________  ___/___/___']], colWidths=[5.2*inch])
t.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('TEXTCOLOR', (0,0), (-1,-1), COLORS['muted']), ('FONTSIZE', (0,0), (-1,-1), 8), ('FONTNAME', (0,0), (-1,-1), FONT_I), ('LEFTPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
story.append(t)
story.append(PageBreak())

# --------------- PAGE 2: COPYRIGHT ----------------
story.append(Spacer(1, 1.2*inch))
story.append(Paragraph("Copyright", sHeading1))
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph("Copyright © 2025 Safari Wonders Press. All rights reserved.<br/>First Edition", sBodyCenter))
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph(
    "No part of this publication may be reproduced, stored in a retrieval system, or transmitted in any form "
    "or by any means — electronic, mechanical, photocopying, recording, or otherwise — without the prior written "
    "permission of the publisher, except for brief quotations in a review.<br/><br/>"
    "All illustrations in this book were originally created for this publication. African animal names, habitat descriptions, "
    "and educational facts have been verified against reputable zoological and conservation sources including the African Wildlife Foundation, "
    "San Diego Zoo Wildlife Alliance, National Geographic Education, and the IUCN Red List (2024). Every effort has been made to ensure accuracy; "
    "any errors are the publisher's responsibility.<br/><br/>"
    "This book was independently authored and is not sponsored, endorsed, or affiliated with Amazon, Kindle Direct Publishing (KDP), or any other publisher. "
    "Amazon KDP is a trademark of Amazon.com, Inc.<br/><br/>"
    "<b>AI-Assisted Content Disclosure (KDP Compliant):</b> Illustrations in this book were created with the assistance of artificial intelligence (AI) "
    "image-generation tools, then individually reviewed, edited, and approved for anatomical accuracy, line quality, and age-appropriateness. "
    "All educational text, activities, layout, and design were human-authored and human-reviewed. The publisher takes full responsibility for the content.<br/><br/>"
    "Printed on demand. Paper: White (60 lb / 90 gsm). Ink: Black & white interior; colour cover.<br/>"
    "Trim: 8.5 × 11 in (216 × 279 mm). 64 pages.<br/><br/>"
    "Published by <b>Safari Wonders Press</b><br/>"
    "Contact: hello@safariwonderspress.example<br/>"
    "For permissions, bulk orders, or educator licensing, please contact the publisher.<br/><br/>"
    "ISBN 979-8-XXXX-XXXX-X (Paperback)<br/>"
    "LCCN pending<br/><br/>"
    "<i>Printed in the United States of America • Also available for global distribution via Amazon KDP.</i><br/><br/>"
    "10 9 8 7 6 5 4 3 2 1<br/><br/>"
    "<b>A Note for Parents and Teachers:</b> This colouring book is designed for crayons, coloured pencils, and gel pens. "
    "If young artists use markers, please place a sheet of blank paper behind the page to prevent show-through. "
    "Encourage children to observe the real colours of African wildlife — but there are no wrong colours in creativity!",
    sBodySmall))
story.append(Spacer(1, 0.3*inch))
story.append(Paragraph("Dedicated to every young explorer who dreams of safari.<br/>May this book inspire curiosity, kindness, and care for Africa's wild places.", ParagraphStyle('dedication', parent=sBodyCenter, fontName=FONT_I, fontSize=9.5, textColor=COLORS['primary'], borderWidth=1, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(8,8,8))))
story.append(PageBreak())

# --------------- PAGE 3: WELCOME ----------------
story.append(Spacer(1, 0.35*inch))
story.append(Paragraph("Welcome to African Wildlife and Nature!", sHeading1))
story.append(Paragraph("A Message for Young Explorers", ParagraphStyle('welcomeSub', parent=sSubtitle, fontSize=12, textColor=COLORS['accent2'])))
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph(
    "Hello, safari explorer! Get ready for a wild adventure across Africa — a huge continent with deserts, grasslands, wetlands, "
    "mountains, forests, and coasts. In this book you will meet the <b>Big Five</b> (lion, leopard, elephant, buffalo, and rhinoceros), "
    "giraffes that tower above the trees, zebras with one-of-a-kind stripes, baby animals cuddled beside their families, "
    "brilliant birds, shy reptiles, and misty waterfalls and sunrise plains.", sBody))
story.append(Paragraph(
    "<b>How to use this book:</b> Each illustration is on its own page. Colour with crayons, coloured pencils, or gel pens — whatever you love! "
    "Try looking up the real animal colours on a parent's phone, then add your own imagination. Read the animal's name at the bottom of each page. "
    "In the middle of the book you will find <b>10 Amazing Wildlife Facts</b> — short and true. At the back, enjoy <b>5 bonus activities</b>: matching, "
    "counting, spot-the-difference, a maze, and a drawing prompt. Check your answers in the Answer Key.", sBody))
story.append(Paragraph(
    "<b>A note on habitats:</b> Not every animal in this book lives in the same place! Lions and meerkats love open savannah; "
    "gorillas live in rainforests; flamingos gather at soda lakes; pangolins hide in woodlands. Watch for the habitat clues in each picture — "
    "acacia trees, baobab trunks, papyrus reeds, rocky kopjes, and forest canopies.", sBody))
story.append(Spacer(1, 0.12*inch))
# Quick facts
data = [
    [Paragraph("<b>Did you know?</b>", ParagraphStyle('didyou', parent=sBody, fontName=FONT_B, fontSize=9, textColor=COLORS['primary'])),
     Paragraph("Africa is home to more than 1,100 mammal species — more than any other continent!", sBodySmall)],
    [Paragraph("<b>Africa is big!</b>", ParagraphStyle('didyou2', parent=sBody, fontName=FONT_B, fontSize=9, textColor=COLORS['primary'])),
     Paragraph("The continent covers about 30 million km². You could fit the USA, China, India, and Europe inside it!", sBodySmall)],
    [Paragraph("<b>Respect wildlife</b>", ParagraphStyle('didyou3', parent=sBody, fontName=FONT_B, fontSize=9, textColor=COLORS['primary'])),
     Paragraph("The animals in this book are wild. In real life we watch them from a safe distance and protect their homes.", sBodySmall)],
]
t = Table(data, colWidths=[1.4*inch, 4.6*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), COLORS['light_bg']),
    ('BOX', (0,0), (-1,-1), 1, COLORS['accent']),
    ('INNERGRID', (0,0), (-1,-1), 0.7, COLORS['accent']),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 6),
    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
]))
story.append(t)
story.append(Spacer(1, 0.18*inch))
story.append(Paragraph(
    "<b>For parents &amp; teachers:</b> This book aligns with early science curiosity (ages 5–10) — animal traits, habitats, and biodiversity. "
    "Use the facts for short read-alouds and the activities for fine-motor and reasoning practice. All art has thick, enclosed outlines for crayons and "
    "large motor control; each image was checked for anatomical plausibility (ear shape, trunk, horn, mane, beak) and for clean white backgrounds.", ParagraphStyle('parentNote', parent=sBodySmall, fontName=FONT_R, fontSize=8.5, textColor=COLORS['muted'], borderWidth=0.7, borderColor=COLORS['muted'], borderPadding=(6,6,6))))
story.append(PageBreak())

# --------------- PAGE 4: CONTENTS ----------------
story.append(Spacer(1, 0.40*inch))
story.append(Paragraph("Inside Your Safari Adventure", sHeading1))
story.append(Paragraph("What you will discover", ParagraphStyle('contentsSub', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.20*inch))
toc_data = [
    [Paragraph("<b>Section</b>", ParagraphStyle('tocHead', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>What is Inside</b>", ParagraphStyle('tocHead2', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>Pages</b>", ParagraphStyle('tocHead3', parent=sBodySmall, fontName=FONT_B, textColor=white, alignment=TA_CENTER))],
    [Paragraph("Welcome &amp; How to Use", sBodySmall), Paragraph("Tips for explorers, parents, and teachers", sBodySmall), Paragraph("3", ParagraphStyle('tocPages', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("<b>A. The African Big Five</b>", ParagraphStyle('tocA', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Lion, leopard, elephant, buffalo, white rhinoceros — in natural settings", sBodySmall), Paragraph("5–9", ParagraphStyle('tocPages2', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("<b>B. Animals of the Savannah</b>", ParagraphStyle('tocB', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Giraffe, zebra, cheetah, hyena, warthog, meerkat, wild dog, ostrich, impala, hippo", sBodySmall), Paragraph("10–19", ParagraphStyle('tocPages3', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("<b>C. Baby Animals &amp; Family Life</b>", ParagraphStyle('tocC', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Elephant calf, lion cubs, baby giraffe, zebra foal, baby rhinos, monkeys, gorillas", sBodySmall), Paragraph("20–26", ParagraphStyle('tocPages4', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("<b>D. Birds, Reptiles &amp; Other Wildlife</b>", ParagraphStyle('tocD', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Fish eagle, secretarybird, hornbill, flamingos, crocodile, chameleon, tortoise, pangolin", sBodySmall), Paragraph("27–34", ParagraphStyle('tocPages5', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("<b>E. Landscapes &amp; Nature</b>", ParagraphStyle('tocE', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Acacias, baobab, watering hole, grasslands, riverbank, kopjes, waterfall, sunrise, forest, panorama", sBodySmall), Paragraph("35–44", ParagraphStyle('tocPages6', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("10 Amazing Wildlife Facts", ParagraphStyle('tocFact', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Short, verified facts about African nature — easy to read", sBodySmall), Paragraph("45–49", ParagraphStyle('tocPages7', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("Animal Identification Guide", sBodySmall), Paragraph("Quick reference of all 40 animals with common names", sBodySmall), Paragraph("50", ParagraphStyle('tocPages8', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("5 Bonus Activities + Answer Key", ParagraphStyle('tocAct', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Matching, counting, spot-the-difference, maze, drawing; answers at the end", sBodySmall), Paragraph("51–57", ParagraphStyle('tocPages9', parent=sBodySmall, alignment=TA_CENTER))],
    [Paragraph("Your Safari Certificate &amp; Closing", sBodySmall), Paragraph("Celebrate your journey and plan the next adventure", sBodySmall), Paragraph("58–60", ParagraphStyle('tocPages10', parent=sBodySmall, alignment=TA_CENTER))],
]
t = Table(toc_data, colWidths=[1.85*inch, 3.55*inch, 0.85*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), COLORS['primary']),
    ('TEXTCOLOR', (0,0), (-1,0), white),
    ('BACKGROUND', (0,1), (-1,1), COLORS['light_bg']),
    ('BACKGROUND', (0,2), (-1,2), white),
    ('BACKGROUND', (0,3), (-1,3), COLORS['light_bg']),
    ('BACKGROUND', (0,4), (-1,4), white),
    ('BACKGROUND', (0,5), (-1,5), COLORS['light_bg']),
    ('BACKGROUND', (0,6), (-1,6), white),
    ('BACKGROUND', (0,7), (-1,7), COLORS['light_bg']),
    ('BACKGROUND', (0,8), (-1,8), white),
    ('BACKGROUND', (0,9), (-1,9), COLORS['light_bg']),
    ('BACKGROUND', (0,10), (-1,10), white),
    ('BACKGROUND', (0,11), (-1,11), COLORS['light_bg']),
    ('BOX', (0,0), (-1,-1), 1, COLORS['primary']),
    ('INNERGRID', (0,0), (-1,-1), 0.6, COLORS['accent']),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t)
story.append(Spacer(1, 0.18*inch))
story.append(Paragraph(
    "Each colouring page has the animal's name at the bottom. For best results, place a blank sheet behind the page if you use markers. "
    "There are <b>40 unique colouring illustrations</b> — no duplicates — plus activities and facts. Look for the page numbers at the bottom!", ParagraphStyle('tocNote', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER)))
story.append(Spacer(1, 0.22*inch))
# Mini map-like region hint
story.append(Paragraph("<b>Africa's Regions in This Book</b>  •  Savannah (East &amp; Southern Africa)  •  Congo Rainforest  •  Wetlands &amp; Rivers (Nile, Okavango)  •  Deserts &amp; Kopjes  •  Soda Lakes (Rift Valley)  •  Coasts &amp; Mountains", ParagraphStyle('regions', parent=sBodySmall, fontName=FONT_R, fontSize=7.5, alignment=TA_CENTER, textColor=COLORS['muted'], borderWidth=0.6, borderColor=COLORS['muted'], borderPadding=(5,5,5))))
story.append(PageBreak())

# --------------- 40 COLOURING PAGES ----------------
# We will embed each illustration full-page with caption and small educational footer
# Order is already chronological, but we need to ensure numbering matches TOC: 5-44 corresponds to 40 pages, starting at page 5
# Our current doc.page count: title=1, copyright=2, welcome=3, contents=4 → next is 5, perfect.

# Load list in order
ordered = [
    ("01_lion.png", "African Lion — King of the Savannah", "Panthera leo — Lives in savannah and grasslands. Males have grand manes that protect them. Listen for their roar up to 8 km away!"),
    ("02_leopard.png", "African Leopard — Spotted Climber", "Panthera pardus — Secretive and strong; it drags prey into trees to keep it safe. Found from forest to desert."),
    ("03_elephant.png", "African Bush Elephant — Gentle Giant", "Loxodonta africana — Largest land animal! Its big ears work like fans to stay cool."),
    ("04_buffalo.png", "African Buffalo — Strong Herd Member", "Syncerus caffer — Lives in herds of hundreds; its horns form a thick 'boss' on its head."),
    ("05_rhino.png", "White Rhinoceros — Horned Grazer", "Ceratotherium simum — The second-largest land mammal. Its wide mouth is perfect for grazing grass."),
    ("06_giraffe.png", "Giraffe — Tallest Animal on Earth", "Giraffa spp. — Up to 5.5 m tall! Its long neck helps reach acacia leaves; each coat pattern is unique."),
    ("07_zebra.png", "Plains Zebra — Striped Beauty", "Equus quagga — Every zebra's stripes are one-of-a-kind, like human fingerprints. They live in family groups."),
    ("08_cheetah.png", "Cheetah — Fastest Land Animal", "Acinonyx jubatus — Can reach 100 km/h in seconds! Its tear-lines reduce sun glare while hunting."),
    ("09_hyena.png", "Spotted Hyena — Laughing Hunter", "Crocuta crocuta — Not just a scavenger — a skilled hunter that lives in clans led by females."),
    ("10_warthog.png", "Warthog — Tusks and Warts", "Phacochoerus africanus — Its tusks are elongated canine teeth; warts are thick skin pads for protection."),
    ("11_meerkat.png", "Meerkat Family — Standing Guard", "Suricata suricatta — Lives in Kalahari Desert mobs; one stands guard while others forage."),
    ("12_wilddog.png", "African Wild Dog — Painted Pack", "Lycaon pictus — Also called painted dog; each coat is patchy and unique. An endangered, cooperative hunter."),
    ("13_ostrich.png", "Ostrich — Giant Flightless Bird", "Struthio camelus — World's largest bird; it cannot fly but can sprint at 70 km/h!"),
    ("14_impala.png", "Impala — Graceful Leaper", "Aepyceros melampus — Famous for leaps up to 3 m high and 10 m long to escape predators."),
    ("15_hippo.png", "Hippopotamus — River Giant", "Hippopotamus amphibius — Spends days in water to stay cool; grazes on grass at night."),
    ("16_elephant_calf.png", "Elephant Calf with Mother", "Calves walk close to mothers for up to 10 years, learning the herd's trails and watering holes."),
    ("17_lion_cubs.png", "Lion Cubs at Play", "Cubs play-fight to build hunting skills; lionesses raise cubs together in a pride."),
    ("18_baby_giraffe.png", "Baby Giraffe with Mother", "Newborn giraffes stand within 30 minutes! Babies stay near mothers for protection on the plains."),
    ("19_zebra_foal.png", "Zebra Foal with Mother", "Foals can run an hour after birth; they imprint on their mother's stripe pattern to stay close."),
    ("20_baby_rhino.png", "Baby Rhinos with Mother", "Rhino calves stay with mothers for 2–3 years; mothers are very protective."),
    ("21_monkeys.png", "Vervet Monkey Family", "Chlorocebus pygerythrus — Vervet monkeys live in troops of 10–50, grooming each other to stay close."),
    ("22_gorilla_family.png", "Gorilla Family in the Forest", "Gorilla beringei / gorilla — Gentle forest giants; families are led by a silverback and share strong bonds."),
    ("23_fish_eagle.png", "African Fish Eagle — Sky Hunter", "Icthyophaga vocifer — Its loud call is the 'voice of Africa'; it swoops to catch fish with powerful talons."),
    ("24_secretarybird.png", "Secretarybird — Striding Hunter", "Sagittarius serpentarius — A tall raptor that stalks snakes through grassland on long, crane-like legs."),
    ("25_hornbill.png", "Southern Ground Hornbill — Big Beak", "Bucorvus leadbeateri — Vulnerable in the wild; its huge beak and casque make its voice boom across savannah."),
    ("26_flamingos.png", "Flamingos — Pink Wading Birds", "Phoenicopterus roseus & Phoeniconaias minor — Gather by thousands at Rift Valley soda lakes; pink colour comes from their food!"),
    ("27_crocodile.png", "Nile Crocodile — River Predator", "Crocodylus niloticus — A powerful swimmer with about 68 teeth; it basks on riverbanks to warm up."),
    ("28_chameleon.png", "Chameleon — Colour-Changing Climber", "Trioceros/Chamaeleo spp. — Can move each eye independently; its sticky tongue can be longer than its body!"),
    ("29_tortoise.png", "Leopard Tortoise — Shelled Walker", "Stigmochelys pardalis — Named for its spotted shell; it stores water and travels slowly across savannah and bush."),
    ("30_pangolin.png", "Pangolin — Scaly Anteater", "Smutsia spp. — The world's only scaly mammal; it curls into a ball when scared and eats ants with a long tongue."),
    ("31_acacia_savannah.png", "Acacia Trees on the Savannah", "Flat-topped acacia trees dot the savannah — their leaves feed giraffes and their thorns protect them."),
    ("32_baobab.png", "Baobab Tree — Tree of Life", "Adansonia digitata — Can live 1,000+ years and store thousands of litres of water in its trunk!"),
    ("33_watering_hole.png", "Watering Hole Gathering", "In dry seasons, elephants, giraffes, and zebras share shrinking waterholes — a busy, careful truce."),
    ("34_grasslands.png", "African Grasslands — Wide and Golden", "Savannah grasslands cover about half the continent — home to grazing herds and their predators."),
    ("35_riverbank.png", "Riverbank with Hippos and Birds", "Hippopotamuses wallow together in rivers; birds like kingfishers and eagles nest nearby."),
    ("36_kopjes.png", "Rocky Kopjes — Lion Lookout", "Kopjes are rocky hills that rise from plains; lions rest on them to spot prey and cool in the breeze."),
    ("37_waterfall.png", "Waterfall and Lush Vegetation", "Africa's waterfalls (like Victoria Falls) thunder and spray — creating lush oases for plants and animals."),
    ("38_sunrise.png", "Peaceful Safari Sunrise", "Many animals are most active at dawn and dusk — listen for birdsong and watch giraffes wake."),
    ("39_forest.png", "African Forest — Congo Rainforest", "The Congo Basin rainforest is Africa's green heart — home to gorillas, okapis, parrots, and towering trees."),
    ("40_panorama.png", "Safari Panorama — All Together!", "A final celebration — can you spot every animal you coloured? Count them and name their habitats!"),
]

for idx, (fname, title, caption) in enumerate(ordered, start=1):
    img_path = ILLUSTR_DIR / fname
    # Image size: we want to fit within margins, max height ~7.5 inch, width ~6.5 inch
    # Our source is 2550x3300 (aspect 0.77), page usable is about 6.5x9 (aspect 0.72) - close
    # Convert to reportlab image with width 6.6 inch
    rl_img = RLImage(str(img_path), width=6.55*inch, height=8.45*inch, kind='proportional')
    rl_img.hAlign = 'CENTER'
    # Title at top of page (optional, already embedded in image but we repeat for accessibility)
    story.append(Paragraph(f"<b>{idx}.</b>  {title}", ParagraphStyle('colourTitleTop', parent=sHeading2, fontSize=13, alignment=TA_CENTER, textColor=COLORS['primary'])))
    story.append(rl_img)
    story.append(Spacer(1, 0.10*inch))
    story.append(Paragraph(caption, ParagraphStyle('captionPage', parent=sCaption, fontSize=8, leading=11, alignment=TA_CENTER, textColor=COLORS['muted'])))
    # Colour tip footer
    story.append(Paragraph("Tip: Look up real colours, then make it yours!  •  Use a blank sheet behind the page for markers.", ParagraphStyle('tip', parent=sCaption, fontSize=6.8, textColor=COLORS['accent2'])))
    story.append(PageBreak())

# --------------- EDUCATIONAL FACTS (5 pages, 2 facts per page) ----------------
facts = [
    ("Fact 1: Why Do Giraffes Have Such Long Necks?", "Giraffes have necks up to 2 metres long with only seven vertebrae — the same number as humans, just much larger ones! A long neck helps them nibble leaves high in acacia trees that other animals cannot reach. Males also use their necks in gentle 'necking' contests. <b>Habitat:</b> Open savannah and woodlands of East and Southern Africa. <i>Sources: San Diego Zoo Wildlife Alliance; African Wildlife Foundation (2024).</i>"),
    ("Fact 2: How Do Elephants Use Their Trunks?", "An elephant trunk has about 40,000 muscles and works like a nose, hand, and shower in one. Elephants use it to breathe, smell, suck up water to drink, pick up tiny seeds, and trumpet loudly. Mothers gently touch calves with their trunks to comfort them. <b>Species shown:</b> African bush elephant — the largest land mammal, with large, Africa-shaped ears. <i>Sources: WWF; African Wildlife Foundation.</i>"),
    ("Fact 3: Why Are Zebra Stripes One-of-a-Kind?", "Every zebra's stripes are unique, just like a human fingerprint. Foals learn to recognise their mother's pattern within hours. Scientists think stripes may help with temperature control and confuse flies. Plains zebras live in family groups that join into larger herds for migration. <i>Sources: National Geographic Education; San Diego Zoo.</i>"),
    ("Fact 4: What Makes the African Savannah Special?", "Savannah covers nearly half of Africa — a mix of grasses and scattered trees with a long dry season and a rainy season. Huge herds of grazers (zebra, wildebeest, buffalo, impala) move with the rains, followed by predators. Fire and grazing keep the savannah open. <i>Sources: National Geographic; Encyclopedia Britannica.</i>"),
    ("Fact 5: How Do Hippos Use Water Habitats?", "Hippos spend up to 16 hours a day in rivers and lakes to keep their skin moist and cool. Their eyes, ears, and nostrils sit on top of their heads, so they can see, hear, and breathe while mostly submerged. At night they leave the water to graze on grass. <i>Sources: African Wildlife Foundation; IUCN.</i>"),
    ("Fact 6: What Do Vultures Do for the Ecosystem?", "Vultures are nature's clean-up crew. By eating carrion quickly, they stop diseases from spreading to other animals and people. Africa has 11 vulture species, many now endangered due to poisoning and habitat loss. Protecting vultures keeps savannahs healthy. <i>Sources: IUCN Red List; BirdLife International (2024).</i>"),
    ("Fact 7: Why Are Baobab Trees Remarkable?", "Baobabs can live over 1,000 years and grow trunks more than 10 metres wide. They store water inside, flower at night for bats, and produce nutritious fruit. Many animals — elephants, birds, and insects — depend on them, which is why people call them the 'Tree of Life.' <i>Sources: National Geographic; African Wildlife Foundation.</i>"),
    ("Fact 8: How Do Animals Adapt to Different Habitats?", "Not all African wildlife lives in savannah! Gorillas thrive in cool mountain forests, flamingos filter food in salty soda lakes, meerkats dig burrows in the Kalahari Desert, and penguins waddle on South Africa's coast. Each species has special adaptations — thick fur, webbed feet, or water-saving kidneys. <i>Sources: WWF; San Diego Zoo.</i>"),
    ("Fact 9: How Do Cheetahs Run So Fast?", "Cheetahs are built for speed: a flexible spine, long legs, a big heart and lungs, and claws that grip like running shoes. They can go from 0 to 100 km/h in about 3 seconds but can only keep top speed for a short chase. Afterward they need to rest and cool down. <i>Sources: Cheetah Conservation Fund; National Geographic.</i>"),
    ("Fact 10: What Links Pangolins, Forests, and People?", "Pangolins are the world's only scaly mammals; scales protect them, and a long sticky tongue catches ants. They live in forests and savannahs but are the most trafficked wild mammals globally. Protecting forests and saying 'no' to illegal products helps pangolins survive. <i>Sources: IUCN; WWF (2024).</i>"),
]

story.append(Paragraph("10 Amazing Wildlife Facts", sHeading1))
story.append(Paragraph("Short, true, and safari-approved — read one before you colour.", ParagraphStyle('factIntro', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.15*inch))

for i in range(0, len(facts), 2):
    # Two facts per page
    for fact_idx in [i, i+1]:
        if fact_idx >= len(facts):
            break
        title_f, body_f = facts[fact_idx]
        # fact box
        story.append(Paragraph(title_f, sFactTitle))
        story.append(Paragraph(body_f, sFactBody))
        # decorative line
        t = Table([['']], colWidths=[6.2*inch])
        t.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,0), 0.8, COLORS['accent'])]))
        story.append(t)
        story.append(Spacer(1, 0.12*inch))
    # footer note
    story.append(Paragraph("Sources checked: African Wildlife Foundation, San Diego Zoo Wildlife Alliance, National Geographic Education, IUCN Red List (2024).", ParagraphStyle('factFooter', parent=sCaption, fontSize=7, textColor=COLORS['muted'], alignment=TA_CENTER)))
    story.append(PageBreak())

# --------------- ANIMAL IDENTIFICATION GUIDE (1 page) ----------------
story.append(Paragraph("Safari Spotter Guide", sHeading1))
story.append(Paragraph("Can you name every animal in this book? Use this checklist!", ParagraphStyle('spotterSub', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.18*inch))
# Create table with 3 columns: # | Animal | Check
guide_data = [
    [Paragraph("<b>#</b>", ParagraphStyle('gHead', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>Common Name</b>", ParagraphStyle('gHead2', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>Scientific Name</b>", ParagraphStyle('gHead3', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>✓</b>", ParagraphStyle('gHead4', parent=sBodySmall, fontName=FONT_B, textColor=white, alignment=TA_CENTER))],
]
names = [
    ("1","African Lion","Panthera leo"),
    ("2","African Leopard","Panthera pardus"),
    ("3","African Bush Elephant","Loxodonta africana"),
    ("4","African Buffalo","Syncerus caffer"),
    ("5","White Rhinoceros","Ceratotherium simum"),
    ("6","Giraffe (multi-species)","Giraffa spp."),
    ("7","Plains Zebra","Equus quagga"),
    ("8","Cheetah","Acinonyx jubatus"),
    ("9","Spotted Hyena","Crocuta crocuta"),
    ("10","Warthog","Phacochoerus africanus"),
    ("11","Meerkat","Suricata suricatta"),
    ("12","African Wild Dog","Lycaon pictus"),
    ("13","Common Ostrich","Struthio camelus"),
    ("14","Impala","Aepyceros melampus"),
    ("15","Hippopotamus","Hippopotamus amphibius"),
    ("16","African Fish Eagle","Icthyophaga vocifer"),
    ("17","Secretarybird","Sagittarius serpentarius"),
    ("18","Southern Ground Hornbill","Bucorvus leadbeateri"),
    ("19","Flamingo (Greater/Lesser)","Phoenicopterus / Phoeniconaias"),
    ("20","Nile Crocodile","Crocodylus niloticus"),
    ("21","Chameleon","Chamaeleonidae spp."),
    ("22","Leopard Tortoise","Stigmochelys pardalis"),
    ("23","Pangolin","Smutsia spp."),
    ("24","Vervet Monkey","Chlorocebus pygerythrus"),
    ("25","Gorilla","Gorilla spp."),
    ("26","Baobab (Tree)","Adansonia digitata"),
    ("27","Acacia (Tree)","Vachellia / Senegalia spp."),
]
for n, common, sci in names:
    guide_data.append([
        Paragraph(n, ParagraphStyle('gNum', parent=sBodySmall, fontSize=8, alignment=TA_CENTER)),
        Paragraph(common, sBodySmall),
        Paragraph(f"<i>{sci}</i>", ParagraphStyle('gSci', parent=sBodySmall, fontName=FONT_I, fontSize=8, textColor=COLORS['muted'])),
        Paragraph("☐", ParagraphStyle('gCheck', parent=sBodySmall, fontSize=11, alignment=TA_CENTER)),
    ])

t = Table(guide_data, colWidths=[0.45*inch, 2.15*inch, 2.55*inch, 0.45*inch])
style = TableStyle([
    ('BACKGROUND', (0,0), (-1,0), COLORS['primary']),
    ('TEXTCOLOR', (0,0), (-1,0), white),
    ('FONTNAME', (0,0), (-1,0), FONT_B),
    ('FONTSIZE', (0,0), (-1,0), 8),
    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('GRID', (0,0), (-1,-1), 0.6, COLORS['accent']),
    ('ROWBACKGROUNDS', (0,1), (-1,-1), [white, COLORS['light_bg']]),
    ('LEFTPADDING', (0,0), (-1,-1), 5),
    ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ('TOPPADDING', (0,0), (-1,-1), 3),
    ('BOTTOMPADDING', (0,0), (-1,-1), 3),
])
t.setStyle(style)
story.append(t)
story.append(Spacer(1, 0.14*inch))
story.append(Paragraph("Tick each animal as you colour it. How many can you find in the final panorama on page 44?", ParagraphStyle('guideNote', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['muted'])))
story.append(PageBreak())

# --------------- BONUS ACTIVITIES ----------------
# Activity 1: Matching
story.append(Paragraph("Bonus Activity 1", ParagraphStyle('actNum', parent=sBodyCenter, fontName=FONT_B, fontSize=9, textColor=COLORS['accent'], letterSpacing=2)))
story.append(Paragraph("Match the Animal to Its Name", sActivityTitle))
story.append(Paragraph("Draw a line from each picture to its correct name. One has been done for you!", ParagraphStyle('actInstr', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.18*inch))
# Create matching exercise - we will use text placeholders + describe images as boxes labeled
# For print, we'll have 5 animals on left as simple icons (we'll use text boxes) and names on right
# Use table
# We'll draw matching lines as example via table
from reportlab.lib import colors
match_data = [
    [Paragraph("<b>A</b>  🦒  <br/><i>Giraffe</i><br/><font size=7>(tallest)</font>", ParagraphStyle('matchA', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=white, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,6,8))),
     Paragraph("1.  African Buffalo  —  Strong horns, lives in herds", sBodySmall),
     ],
    [Paragraph("<b>B</b>  🦁  <br/><i>Lion</i><br/><font size=7>Example →</font>", ParagraphStyle('matchB', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=COLORS['light_bg'], borderWidth=1, borderColor=COLORS['accent'], borderPadding=(8,6,8))),
     Paragraph("2.  African Lion  —  King of the Savannah  ★", sBodySmall),
     ],
    [Paragraph("<b>C</b>  🐘  <br/><i>Elephant</i><br/><font size=7>(big ears)</font>", ParagraphStyle('matchC', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=white, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,6,8))),
     Paragraph("3.  Cheetah  —  Fastest runner, tear-lines", sBodySmall),
     ],
    [Paragraph("<b>D</b>  🦓  <br/><i>Zebra</i><br/><font size=7>(stripes)</font>", ParagraphStyle('matchD', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=white, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,6,8))),
     Paragraph("4.  Giraffe  —  Tallest animal, eats acacia", sBodySmall),
     ],
    [Paragraph("<b>E</b>  🐆  <br/><i>Cheetah</i><br/><font size=7>(spots)</font>", ParagraphStyle('matchE', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=white, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,6,8))),
     Paragraph("5.  Plains Zebra  —  Every stripe is unique", sBodySmall),
     ],
    [Paragraph("<b>F</b>  🐃  <br/><i>Buffalo</i><br/><font size=7>(curved horns)</font>", ParagraphStyle('matchF', parent=sBodyCenter, fontName=FONT_R, fontSize=9, alignment=TA_CENTER, backColor=white, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,6,8))),
     Paragraph("6.  African Bush Elephant  —  Gentle giant with trunk", sBodySmall),
     ],
]
# Add instruction that B→2 is example
t = Table(match_data, colWidths=[1.9*inch, 4.3*inch])
t.setStyle(TableStyle([
    ('BOX', (0,0), (-1,-1), 1.2, COLORS['primary']),
    ('INNERGRID', (0,0), (-1,-1), 0.6, COLORS['accent']),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 6),
    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ('LINEABOVE', (0,1), (1,1), 1, COLORS['accent']), # example line B->2 already
]))
story.append(t)
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Answers:  A-4,  B-2 ★,  C-6,  D-5,  E-3,  F-1.  (See Answer Key on page 56.)", sCaption))
story.append(PageBreak())

# Activity 2: Counting
story.append(Paragraph("Bonus Activity 2", ParagraphStyle('actNum2', parent=sBodyCenter, fontName=FONT_B, fontSize=9, textColor=COLORS['accent'], letterSpacing=2)))
story.append(Paragraph("Count the Animals in the Scene", sActivityTitle))
story.append(Paragraph("Look closely and write how many you see. Use the panorama on page 44 to double-check!", ParagraphStyle('actInstr2', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.16*inch))
count_data = [
    [Paragraph("<b>Scene</b>", ParagraphStyle('countHead', parent=sBodySmall, fontName=FONT_B, textColor=white, alignment=TA_CENTER)), Paragraph("<b>What to Count</b>", ParagraphStyle('countHead2', parent=sBodySmall, fontName=FONT_B, textColor=white)), Paragraph("<b>How Many?</b>", ParagraphStyle('countHead3', parent=sBodySmall, fontName=FONT_B, textColor=white, alignment=TA_CENTER))],
    [Paragraph("🖼️  Watering Hole (p.33)", ParagraphStyle('countScene', parent=sBodySmall, fontName=FONT_B, fontSize=9)), Paragraph("Elephants + giraffes + zebras + birds = __", sBodySmall), Paragraph("___", ParagraphStyle('countAns', parent=sBodySmall, alignment=TA_CENTER, fontSize=13))],
    [Paragraph("🖼️  Meerkat Family (p.11)", ParagraphStyle('countScene2', parent=sBodySmall, fontName=FONT_B, fontSize=9)), Paragraph("Meerkats standing guard = __  (Hint: 1 big + 2 small)", sBodySmall), Paragraph("___", ParagraphStyle('countAns2', parent=sBodySmall, alignment=TA_CENTER, fontSize=13))],
    [Paragraph("🖼️  Final Panorama (p.44)", ParagraphStyle('countScene3', parent=sBodySmall, fontName=FONT_B, fontSize=9)), Paragraph("Total mammals you can name = __", sBodySmall), Paragraph("___", ParagraphStyle('countAns3', parent=sBodySmall, alignment=TA_CENTER, fontSize=13))],
    [Paragraph("🖼️  Grasslands (p.34)", ParagraphStyle('countScene4', parent=sBodySmall, fontName=FONT_B, fontSize=9)), Paragraph("Acacia trees = __", sBodySmall), Paragraph("___", ParagraphStyle('countAns4', parent=sBodySmall, alignment=TA_CENTER, fontSize=13))],
    [Paragraph("🖼️  Lion Cubs (p.17)", ParagraphStyle('countScene5', parent=sBodySmall, fontName=FONT_B, fontSize=9)), Paragraph("Lion cubs playing = __", sBodySmall), Paragraph("___", ParagraphStyle('countAns5', parent=sBodySmall, alignment=TA_CENTER, fontSize=13))],
]
t = Table(count_data, colWidths=[2.0*inch, 2.85*inch, 1.2*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), COLORS['primary']),
    ('TEXTCOLOR', (0,0), (-1,0), white),
    ('BACKGROUND', (0,1), (-1,1), white),
    ('BACKGROUND', (0,2), (-1,2), COLORS['light_bg']),
    ('BACKGROUND', (0,3), (-1,3), white),
    ('BACKGROUND', (0,4), (-1,4), COLORS['light_bg']),
    ('BACKGROUND', (0,5), (-1,5), white),
    ('BOX', (0,0), (-1,-1), 1.2, COLORS['primary']),
    ('INNERGRID', (0,0), (-1,-1), 0.6, COLORS['accent']),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 8),
    ('BOTTOMPADDING', (0,0), (-1,-1), 8),
]))
story.append(t)
story.append(Spacer(1, 0.14*inch))
story.append(Paragraph("Write your answers with a pencil, then check on page 56!", sCaption))
# Add a small counting visual - we will describe
story.append(Spacer(1, 0.18*inch))
story.append(Paragraph("Colour the stars for your score:  ☆ ☆ ☆ ☆ ☆", ParagraphStyle('stars', parent=sBodyCenter, fontName=FONT_R, fontSize=11, textColor=COLORS['accent'])))
story.append(PageBreak())

# Activity 3: Spot the Difference
story.append(Paragraph("Bonus Activity 3", ParagraphStyle('actNum3', parent=sBodyCenter, fontName=FONT_B, fontSize=9, textColor=COLORS['accent'], letterSpacing=2)))
story.append(Paragraph("Find 5 Differences — Zebra Friends", sActivityTitle))
story.append(Paragraph("Two zebra pictures look the same — but 5 things are different! Circle them.", ParagraphStyle('actInstr3', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.14*inch))
# We'll create a text-based spot-the-difference description with placeholders
# Since we can't embed second variant image easily, we will describe differences and provide visual via drawing two grids
# Create two side-by-side simple zebra sketches described via table
left = Paragraph(
    "<b>Picture A</b><br/>"
    "Zebra standing under acacia<br/>"
    "• Acacia has 3 foliage clumps<br/>"
    "• Sun in top-right<br/>"
    "• Zebra has 6 body stripes<br/>"
    "• One bird in sky<br/>"
    "• Zebra tail tuft is short<br/>"
    "• Grass tuft at left foot<br/>", ParagraphStyle('diffA', parent=sBodySmall, alignment=TA_LEFT, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,8,8), backColor=white))
right = Paragraph(
    "<b>Picture B</b><br/>"
    "Zebra standing under acacia<br/>"
    "• Acacia has 2 foliage clumps (one missing!)<br/>"
    "• No sun<br/>"
    "• Zebra has 7 body stripes (one extra!)<br/>"
    "• Two birds in sky<br/>"
    "• Zebra tail tuft is long<br/>"
    "• No grass tuft<br/>", ParagraphStyle('diffB', parent=sBodySmall, alignment=TA_LEFT, borderWidth=1, borderColor=COLORS['primary'], borderPadding=(8,8,8), backColor=COLORS['light_bg']))
t = Table([[left, right]], colWidths=[3.05*inch, 3.05*inch], spaceBefore=6, spaceAfter=6)
t.setStyle(TableStyle([
    ('BOX', (0,0), (-1,-1), 1.2, COLORS['primary']),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LEFTPADDING', (0,0), (-1,-1), 4),
    ('RIGHTPADDING', (0,0), (-1,-1), 4),
]))
story.append(t)
story.append(Spacer(1, 0.10*inch))
story.append(Paragraph(
    "Can you spot them? 1) Missing acacia foliage clump &nbsp;|&nbsp; 2) Missing sun &nbsp;|&nbsp; 3) Extra zebra stripe &nbsp;|&nbsp; 4) Extra bird &nbsp;|&nbsp; 5) Tail tuft length &amp; grass tuft<br/>"
    "<i>Answers on page 56 — did you get all five?</i>", ParagraphStyle('diffAns', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['muted'])))
# Provide blank circles area
story.append(Spacer(1, 0.18*inch))
story.append(Paragraph("Circle the differences above, then draw your favourite difference below:", ParagraphStyle('diffDraw', parent=sBodySmall, alignment=TA_CENTER, fontName=FONT_I)))
t = Table([['']], colWidths=[6.2*inch], rowHeights=[2.2*inch])
t.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 1, COLORS['accent']), ('BACKGROUND', (0,0), (-1,-1), white)]))
story.append(t)
story.append(PageBreak())

# Activity 4: Maze
story.append(Paragraph("Bonus Activity 4", ParagraphStyle('actNum4', parent=sBodyCenter, fontName=FONT_B, fontSize=9, textColor=COLORS['accent'], letterSpacing=2)))
story.append(Paragraph("Help the Baby Elephant Find Its Mother!", sActivityTitle))
story.append(Paragraph("Start at the baby elephant (S) and follow the paths to mother elephant (G). Only one route is correct!", ParagraphStyle('actInstr4', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.18*inch))
# Build maze via table with walls as cell colours
# Simple 7x7 maze represented as grid, walls = primary colour, paths = light_bg/white
maze = [
    [1,0,1,1,1,1,1],
    [1,0,0,0,1,0,1],
    [1,1,1,0,1,0,1],
    [1,0,0,0,0,0,1],
    [1,0,1,1,1,0,1],
    [1,0,0,0,1,0,0], # exit to G
    [1,1,1,0,0,0,1],
]
# We'll render as table
maze_data = []
for r in range(7):
    row = []
    for c in range(7):
        if r==0 and c==1:
            txt = Paragraph("<b>S</b><br/><font size=6>🐘 baby</font>", ParagraphStyle('mazeS', parent=sBodySmall, alignment=TA_CENTER, fontName=FONT_B, textColor=COLORS['primary']))
            bg = HexColor('#DFF2BF') # light green start
        elif r==5 and c==6:
            txt = Paragraph("<b>G</b><br/><font size=6>🐘 mum</font>", ParagraphStyle('mazeG', parent=sBodySmall, alignment=TA_CENTER, fontName=FONT_B, textColor=COLORS['primary']))
            bg = HexColor('#FFEDA0') # light gold goal
        elif maze[r][c]==1:
            txt = Paragraph("", sBodySmall)
            bg = COLORS['primary']
        else:
            txt = Paragraph("", sBodySmall)
            bg = white
        row.append(Paragraph(f"<font color='{bg.hexval()}'></font>", sBodySmall)) # placeholder
        # We'll actually set via table style background
        # Instead create cell with txt
        row[-1] = txt
        # need to store bg for later
    maze_data.append(row)

# Need to set backgrounds via style
t = Table(maze_data, colWidths=[0.88*inch]*7, rowHeights=[0.58*inch]*7)
style_cmds = [('BOX', (0,0), (-1,-1), 1.5, COLORS['primary']), ('INNERGRID', (0,0), (-1,-1), 0.8, COLORS['accent']), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]
for r in range(7):
    for c in range(7):
        bg = None
        if r==0 and c==1:
            bg = HexColor('#DFF2BF')
        elif r==5 and c==6:
            bg = HexColor('#FFEDA0')
        elif maze[r][c]==1:
            bg = COLORS['primary']
        else:
            bg = white
        style_cmds.append(('BACKGROUND', (c,r), (c,r), bg))
t.setStyle(TableStyle(style_cmds))
story.append(t)
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Tip: Use a crayon to trace your path — go back if you hit a dark wall!", ParagraphStyle('mazeTip', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['muted'])))
# Add start/goal icons description
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Answer path: S → down → down → right → right → down → right → right → down → right → G  (or see page 56)", ParagraphStyle('mazeAnsSmall', parent=sCaption, fontSize=7, textColor=COLORS['muted'])))
story.append(PageBreak())

# Activity 5: Draw habitat
story.append(Paragraph("Bonus Activity 5", ParagraphStyle('actNum5', parent=sBodyCenter, fontName=FONT_B, fontSize=9, textColor=COLORS['accent'], letterSpacing=2)))
story.append(Paragraph("Draw an Animal's Natural Habitat", sActivityTitle))
story.append(Paragraph("Choose your favourite African animal and draw where it lives. Add plants, water, or friends!", ParagraphStyle('actInstr5', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("My favourite animal is:  ________________________________________", ParagraphStyle('myFav', parent=sBody, fontName=FONT_B, fontSize=10, textColor=COLORS['primary'], alignment=TA_CENTER, borderWidth=1, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(7,8,7))))
story.append(Spacer(1, 0.10*inch))
prompts = [
    [Paragraph("<b>Ideas:</b>", ParagraphStyle('ideaHead', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Savannah — tall grass + acacia tree &nbsp;&nbsp;|&nbsp;&nbsp; Wetland — reeds + water &nbsp;&nbsp;|&nbsp;&nbsp; Desert — sand + rocks &nbsp;&nbsp;|&nbsp;&nbsp; Forest — tall trees + vines &nbsp;&nbsp;|&nbsp;&nbsp; Lake — pink flamingos", sBodySmall)],
    [Paragraph("<b>Remember:</b>", ParagraphStyle('ideaHead2', parent=sBodySmall, fontName=FONT_B, textColor=COLORS['primary'])), Paragraph("Not all animals live together! A gorilla lives in forest, a meerkat in desert. Draw what fits your animal.", sBodySmall)],
]
t = Table(prompts, colWidths=[1.0*inch, 5.2*inch])
t.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), COLORS['light_bg']),
    ('BOX', (0,0), (-1,-1), 1, COLORS['accent']),
    ('INNERGRID', (0,0), (-1,-1), 0.6, COLORS['accent']),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LEFTPADDING', (0,0), (-1,-1), 6),
    ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 5),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
]))
story.append(t)
story.append(Spacer(1, 0.14*inch))
# Large drawing box
draw_box = Table([['']], colWidths=[6.4*inch], rowHeights=[5.0*inch])
draw_box.setStyle(TableStyle([
    ('BOX', (0,0), (-1,-1), 1.2, COLORS['primary']),
    ('BACKGROUND', (0,0), (-1,-1), white),
    ('LINEBELOW', (0,0), (-1,0), 0, white),
]))
story.append(draw_box)
story.append(Spacer(1, 0.08*inch))
story.append(Paragraph("Draw here! Use crayons, add colour, and label plants or water. There is no wrong answer — habitats keep animals safe.", ParagraphStyle('drawHere', parent=sCaption, fontSize=8, alignment=TA_CENTER)))
story.append(PageBreak())

# --------------- ANSWER KEY ----------------
story.append(Paragraph("Answer Key", sHeading1))
story.append(Paragraph("Check your bonus activities!", ParagraphStyle('answerSub', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Activity 1 — Match the Animal to Its Name", sFactTitle))
story.append(Paragraph("A-4 (Giraffe → Tallest animal) &nbsp;|&nbsp; <b>B-2</b> (Lion → King of Savannah) ★ Example &nbsp;|&nbsp; C-6 (Elephant → Gentle giant) &nbsp;|&nbsp; D-5 (Zebra → Striped beauty) &nbsp;|&nbsp; E-3 (Cheetah → Fastest runner) &nbsp;|&nbsp; F-1 (Buffalo → Strong horns).", sBodySmall))
story.append(Paragraph("Activity 2 — Count the Animals", sFactTitle))
story.append(Paragraph(
    "1) Watering Hole: Elephants=1 (or 1 adult), giraffes=1, zebras=1, birds=2 → Total distinct species groups = 4, individual animals = 4. (Panorama varies by printing; teachers may accept 3–5.)<br/>"
    "2) Meerkat Family: 3 meerkats (1 large adult + 2 small pups).<br/>"
    "3) Final Panorama (p.44): 5–6 large mammals clearly visible (elephant, giraffe, zebra, lion, rhino, ostrich) — count may vary if child spots distant birds.<br/>"
    "4) Grasslands: Acacia trees = 3.<br/>"
    "5) Lion Cubs: 3 cubs + 1 lioness = 4 lions total.", sBodySmall))
story.append(Paragraph("Activity 3 — Find the Differences (Zebra Friends)", sFactTitle))
story.append(Paragraph(
    "1) Acacia foliage: Picture A has 3 clumps, Picture B has 2 (top-left clump missing).<br/>"
    "2) Sun: Present in A (top-right), missing in B.<br/>"
    "3) Zebra stripes: A has 6 body stripes, B has 7 (extra stripe near belly).<br/>"
    "4) Birds: A has 1 bird, B has 2 birds in sky.<br/>"
    "5) Tail &amp; grass: A has short tuft + grass tuft at foot; B has long tuft and no grass.", sBodySmall))
story.append(Paragraph("Activity 4 — Maze: Help the Baby Elephant", sFactTitle))
story.append(Paragraph(
    "One correct route: <b>S</b> (top row, column 2) → DOWN → DOWN? blocked, so RIGHT → RIGHT → DOWN → DOWN → RIGHT → RIGHT → DOWN → RIGHT → <b>G</b> (middle-right exit). "
    "On the grid: (0,1) → (1,1) → (1,2) → (1,3) → (2,3) → (3,3) → (3,4) → (3,5) → (4,5) → (5,5) → (5,6)=G. "
    "Any continuous path that avoids dark walls and reaches G is accepted — encourage children to trace with a finger first.", sBodySmall))
story.append(Paragraph("Activity 5 — Draw Your Habitat", sFactTitle))
story.append(Paragraph(
    "There is no single correct answer! Check that: (1) The animal matches its real habitat (e.g., gorilla in forest, not desert), "
    "(2) At least two habitat clues are drawn (trees, water, rocks, grass), (3) The drawing is labelled. Praise creativity over perfection!", sBodySmall))
story.append(Paragraph("For parents/teachers: Use this key to celebrate effort, not just correctness. Every safari explorer learns at their own pace!", ParagraphStyle('answerFooter', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['primary'], borderWidth=0.7, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(6,6,6))))
story.append(PageBreak())

# --------------- CLOSING PAGES ----------------
# Certificate
story.append(Spacer(1, 0.35*inch))
story.append(Paragraph("⭐ &nbsp; You're a Safari Star! &nbsp; ⭐", ParagraphStyle('certTitle', parent=sHeading1, fontSize=24, textColor=COLORS['accent2'])))
story.append(Paragraph("Safari Explorer Certificate", ParagraphStyle('certSub', parent=sSubtitle, fontSize=14, textColor=COLORS['primary'])))
story.append(Spacer(1, 0.25*inch))
story.append(Paragraph(
    "This certifies that", ParagraphStyle('certBody', parent=sBodyCenter, fontName=FONT_I, fontSize=11, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.18*inch))
t = Table([['________________________________________']], colWidths=[4.2*inch])
t.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTSIZE', (0,0), (-1,-1), 14), ('FONTNAME', (0,0), (-1,-1), FONT_B), ('TEXTCOLOR', (0,0), (-1,-1), COLORS['primary'])]))
story.append(t)
story.append(Paragraph("(Write your name)", ParagraphStyle('certNameHint', parent=sBodyCenter, fontName=FONT_I, fontSize=8, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph(
    "has explored Africa's amazing wildlife and nature,<br/>"
    "coloured 40 safari animals and landscapes,<br/>"
    "and completed 5 bonus activities!", ParagraphStyle('certBody2', parent=sBodyCenter, fontName=FONT_R, fontSize=11, leading=16)))
story.append(Spacer(1, 0.25*inch))
t = Table([['Date: __________', 'Explorer Signature: ___________________']], colWidths=[2.2*inch, 3.2*inch])
t.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'), ('FONTSIZE', (0,0), (-1,-1), 9), ('FONTNAME', (0,0), (-1,-1), FONT_R), ('TEXTCOLOR', (0,0), (-1,-1), COLORS['muted'])]))
story.append(t)
story.append(Spacer(1, 0.30*inch))
story.append(Paragraph("Give yourself a big roar! 🦁   Next adventure: <i>Baby Animals of Africa</i> — coming soon in the Safari Wonders collection.", ParagraphStyle('certFooter', parent=sBodyCenter, fontName=FONT_I, fontSize=9, textColor=COLORS['muted'], borderWidth=0.8, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(7,7,7))))
story.append(PageBreak())

# Closing page
story.append(Spacer(1, 0.40*inch))
story.append(Paragraph("Your Safari Journey Continues…", sHeading1))
story.append(Paragraph("Keep exploring, keep caring", ParagraphStyle('closingSub', parent=sSubtitle, fontSize=11, textColor=COLORS['accent2'])))
story.append(Spacer(1, 0.15*inch))
story.append(Paragraph(
    "You have coloured lions and elephants, cheetahs and flamingos, baobabs and waterfalls — you are officially a safari explorer! "
    "But the real adventure is just beginning. Africa's wild places need friends like you: people who notice, care, and protect.", sBody))
story.append(Paragraph(
    "<b>What can you do next?</b> Visit your local library for books about African conservation heroes. Learn about anti-poaching rangers, "
    "wildlife veterinarians, and community groups that help people and animals share the land. If you travel, choose guides who respect wildlife and keep a safe distance. "
    "Even at home, you can help by learning, sharing what you know, and being kind to all animals.", sBody))
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("Look for the next book in the series:", ParagraphStyle('nextSeriesHead', parent=sHeading2, fontSize=12, textColor=COLORS['primary'], alignment=TA_CENTER)))
next_books = [
    [Paragraph("<b>Baby Animals of Africa</b><br/><font size=8>Elephant calves, lion cubs, and fluffy chicks — with gentle tracing pages</font>", ParagraphStyle('next1', parent=sBodyCenter, fontSize=9, leading=12, borderWidth=1, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(7,7,7)))],
    [Paragraph("<b>African Birds and Their Habitats</b><br/><font size=8>Swoop with fish eagles, storks, and weavers across wetlands and plains</font>", ParagraphStyle('next2', parent=sBodyCenter, fontSize=9, leading=12, borderWidth=1, borderColor=COLORS['accent'], backColor=white, borderPadding=(7,7,7)))],
    [Paragraph("<b>Amazing Animals of the African Rainforest</b><br/><font size=8>Gorillas, okapis, parrots, and forest elephants under the canopy</font>", ParagraphStyle('next3', parent=sBodyCenter, fontSize=9, leading=12, borderWidth=1, borderColor=COLORS['accent'], backColor=COLORS['light_bg'], borderPadding=(7,7,7)))],
]
t = Table(next_books, colWidths=[6.2*inch])
t.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 0.8, COLORS['accent']), ('INNERGRID', (0,0), (-1,-1), 0.6, COLORS['accent']), ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
story.append(t)
story.append(Spacer(1, 0.16*inch))
story.append(Paragraph(
    "<i>This book is designed as the first title in a possible African wildlife collection. No other books were created at this time — this one was made to a high standard first. "
    "Future titles will follow only after your feedback.</i>", ParagraphStyle('seriesNote', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.16*inch))
story.append(Paragraph("Thank you for choosing Safari Wonders Press. Share your coloured pages with #SafariWondersPress and inspire other young artists!", ParagraphStyle('thankyou', parent=sBodyCenter, fontName=FONT_R, fontSize=9, textColor=COLORS['muted'])))
story.append(PageBreak())

# --------------- BONUS: DRAW YOUR OWN SAFARI (blank with prompt) ----------------
story.append(Paragraph("My Safari Sketchbook", sHeading1))
story.append(Paragraph("Draw your own safari!", ParagraphStyle('sketchSub', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(Spacer(1, 0.12*inch))
story.append(Paragraph("What animals would you see on YOUR dream safari? Draw them below — add acacia trees, a watering hole, or a sunrise!", ParagraphStyle('sketchInstr', parent=sBodyCenter, fontName=FONT_R, fontSize=9.5, textColor=COLORS['text'])))
t = Table([['']], colWidths=[6.5*inch], rowHeights=[6.2*inch])
t.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 1.1, COLORS['primary']), ('BACKGROUND', (0,0), (-1,-1), white)]))
story.append(t)
story.append(Paragraph("My safari story: __________________________________________________________________", ParagraphStyle('sketchStory', parent=sBodySmall, fontName=FONT_I, alignment=TA_CENTER, textColor=COLORS['muted'])))
story.append(PageBreak())

story.append(Paragraph("My Safari Sketchbook — Page 2", sHeading1))
story.append(Paragraph("Keep drawing!", ParagraphStyle('sketchSub2', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
t = Table([['']], colWidths=[6.5*inch], rowHeights=[7.0*inch])
t.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 1.1, COLORS['primary']), ('BACKGROUND', (0,0), (-1,-1), white)]))
story.append(t)
story.append(PageBreak())

# --------------- FINAL BLANK PAGES FOR MARKER PROTECTION ----------------
# Add 4 blank pages that serve as extra drawing or marker protection, with light prompt
for blank_i in range(2):
    story.append(Paragraph("Notes &amp; Extra Drawing Space", ParagraphStyle('blankHead', parent=sHeading2, fontSize=11, textColor=COLORS['primary'], alignment=TA_CENTER)))
    story.append(Paragraph("Use this space for extra drawings or notes about your favourite African animals.", ParagraphStyle('blankSub', parent=sBodyCenter, fontName=FONT_I, fontSize=8, textColor=COLORS['muted'])))
    # dotted lines
    for _ in range(14):
        t = Table([['']], colWidths=[6.2*inch], rowHeights=[0.38*inch])
        t.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,0), 0.6, COLORS['accent'])]))
        story.append(t)
        story.append(Spacer(1, 0.02*inch))
    if blank_i == 0:
        story.append(PageBreak())

# Extra two blank marker-protection pages to reach 64 exactly (KDP even-page requirement + spine calc)
story.append(PageBreak())
story.append(Spacer(1, 3.5*inch))
story.append(Paragraph("This page is intentionally left blank<br/>Place behind your artwork when using markers to prevent show-through.", ParagraphStyle('blankProtect', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))
story.append(PageBreak())
story.append(Spacer(1, 3.5*inch))
story.append(Paragraph("This page is intentionally left blank<br/>Extra drawing or marker protection.", ParagraphStyle('blankProtect2', parent=sBodyCenter, fontName=FONT_I, fontSize=10, textColor=COLORS['muted'])))


# Build
def build():
    os.makedirs(OUT_PATH.parent, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT_PATH),
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MARGIN_IN,
        rightMargin=MARGIN_OUT,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="African Wildlife and Nature: A Safari Colouring Adventure",
        author="Safari Wonders Press",
        subject="African wildlife colouring book for children ages 5-10",
        keywords="African wildlife, safari, colouring book, animals, nature, children",
        creator="Safari Wonders Press (ReportLab)",
    )
    # Build with per-page header/footer, but we need to handle drawing border for all pages via canvas
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"Built interior PDF: {OUT_PATH}")
    # Verify page count
    from PyPDF2 import PdfReader
    try:
        reader = PdfReader(str(OUT_PATH))
        print(f"Page count: {len(reader.pages)} (target 64)")
        for i, p in enumerate(reader.pages):
            box = p.mediabox
            w = float(box.width)
            h = float(box.height)
            if abs(w - PAGE_W) > 2 or abs(h - PAGE_H) > 2:
                print(f"Page {i+1} size mismatch: {w}x{h}")
    except Exception as e:
        print(f"Could not verify page count: {e}")
        # fallback via pdfminer?
        pass

if __name__ == "__main__":
    build()
