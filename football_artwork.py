"""Shared deterministic stadium typography for owner-approved football layouts."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WHITE='#f1f3ed';MUTED='#a1b3b7';GOLD='#e3d797';GREEN='#91e3c1'


def background(height):
    from PIL import Image,ImageOps,ImageDraw
    image=ImageOps.fit(Image.open(ROOT/'assets/reel/bg_stadium.jpg').convert('RGB'),(1080,height),centering=(.5,.52)).convert('RGBA')
    image=Image.alpha_composite(image,Image.new('RGBA',image.size,(3,11,18,184)))
    draw=ImageDraw.Draw(image)
    draw.line((54,54,1026,54),fill=GOLD,width=2)
    draw.line((54,height-54,1026,height-54),fill='#62756e',width=1)
    return image,draw


def text(draw,value,x,y,size=30,bold=False,fill=WHITE,width=950):
    from PIL import ImageFont
    def font(n):return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),n)
    value=str(value);f=font(size)
    while draw.textlength(value,font=f)>width and size>22:size-=1;f=font(size)
    if draw.textlength(value,font=f)>width:raise ValueError('Football artwork text too long; editorial review required')
    draw.text((x,y),value,font=f,fill=fill,anchor='mt')
