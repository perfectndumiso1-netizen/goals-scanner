"""Deterministic typography over the existing stadium asset; no generated art.

Reference-inspired comparison layout, without copying its unverified statistics,
crests, third-party ratings, or bottom-of-picture trend claims.
"""
from pathlib import Path
from .content import local
ROOT=Path(__file__).resolve().parents[1]


def render(spec,path):
    from PIL import Image,ImageDraw,ImageFont,ImageOps
    image=ImageOps.fit(Image.open(ROOT/'assets/reel/bg_stadium.jpg').convert('RGB'),(1080,1350))
    shade=Image.new('RGBA',image.size,(3,10,14,155));image=Image.alpha_composite(image.convert('RGBA'),shade)
    draw=ImageDraw.Draw(image);white='#eeeedd';gold='#d6d7a2';muted='#b5c4c6'
    def font(size,bold=False):
        return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),size)
    def centered(value,y,size=30,bold=False,color=white,x=540,maxwidth=940):
        text=str(value);f=font(size,bold)
        while draw.textlength(text,font=f)>maxwidth and size>22:
            size-=1;f=font(size,bold)
        if draw.textlength(text,font=f)>maxwidth:raise ValueError('Comparison text too long; editorial review required')
        draw.text((x,y),text,font=f,anchor='mt',fill=color)
    # Branding deliberately restricted to the picture; no branded caption/tag.
    centered('PLAYREPORT ZA',45,25,True,color=muted)
    centered(spec['home'].upper(),105,48,True)
    centered('VS',165,27,color=gold)
    centered(spec['away'].upper(),208,48,True)
    draw.line((75,285,1005,285),fill=gold,width=2)
    centered('TEAM COMPARISON',305,28,True,color=gold)
    centered(spec['league'],352,25)
    centered(local(spec['kickoff']).strftime('%d %b %Y · %H:%M SAST'),391,26,color=muted)
    centered(spec['period'],449,23,color=gold)
    draw.rounded_rectangle((52,512,1028,1110),radius=12,fill=(5,17,21,225),outline=(115,145,140,200),width=2)
    centered(spec['home'],543,25,True,x=250,maxwidth=340)
    centered(spec['away'],543,25,True,x=830,maxwidth=340)
    for idx,(label,left,right) in enumerate(spec['rows']):
        y=625+idx*76
        draw.line((80,y-18,1000,y-18),fill=(102,128,128,160),width=1)
        centered(left,y,36,True,x=175,maxwidth=160)
        centered(label,y+5,23,x=540,maxwidth=480)
        centered(right,y,36,True,x=905,maxwidth=160)
    centered('Source: Highlightly · list/detail cross-checked',1170,23,color=muted)
    centered('Checked '+local(spec['checked_at']).strftime('%d %b %Y, %H:%M SAST'),1210,22,color=muted)
    centered('Different team samples · same league / season · no forecasts',1260,22,color=muted)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(path,quality=94)
    return path
