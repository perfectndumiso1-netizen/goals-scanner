"""Approved crest-led comparison layout; deterministic, no AI-generated artwork."""
from pathlib import Path
from .content import local
from football_artwork import background,text,GOLD,MUTED
from club_crests import paste


def render(spec,path):
    rows=spec['rows']
    if not isinstance(rows,list) or not 1<=len(rows)<=10:
        raise ValueError('Comparison supports at most ten readable verified statistic rows')
    image,draw=background(1350)
    text(draw,'PLAYREPORT ZA',540,82,27,True,fill=MUTED)
    from player_photos import read as player_photo, paste as paste_player
    from football_derbies import label as derby_label
    derby=derby_label(spec['home'],spec['away'],spec.get('country'))
    text(draw,(derby or 'TEAM COMPARISON').upper(),540,139,51,True)
    for side,cx in (('home',275),('away',805)):
        portrait=player_photo(spec[side],spec.get('country'),on=spec['kickoff'])
        if portrait:
            # Dedicated header space only. No portrait pixel reaches team names,
            # kickoff, sample description or any of the ten statistic rows.
            paste_player(image,portrait,(cx-112,195,cx+112,389))
            text(draw,portrait[1],cx,395,22,True,width=360)
            paste(image,spec[side],spec.get('country'),(105 if side=='home' else 975,330),90)
        else:
            paste(image,spec[side],spec.get('country'),(cx,320),160)
    text(draw,'VS',540,307,35,True,fill=GOLD)
    text(draw,spec['home'].upper(),275,435,37,True,width=420)
    text(draw,spec['away'].upper(),805,435,37,True,width=420)
    text(draw,spec['league'],540,480,25,True)
    text(draw,local(spec['kickoff']).strftime('%d %b %Y · %H:%M SAST'),540,520,24,fill=MUTED)
    draw.line((80,565,1000,565),fill=GOLD,width=2)
    text(draw,spec['period'],540,582,23,True,fill=GOLD)
    top=637;bottom=1218
    draw.rounded_rectangle((64,top-16,1016,bottom),radius=18,fill=(6,20,29,230),outline=(75,99,101,255),width=1)
    step=min(76,(bottom-top-10)//len(rows))
    for index,(label,left,right) in enumerate(rows):
        y=top+index*step+7
        if index:draw.line((90,y-12,990,y-12),fill=(72,92,96,255),width=1)
        text(draw,left,180,y,32,True,fill=GOLD,width=165)
        text(draw,label,540,y+4,24,width=530)
        text(draw,right,900,y,32,True,fill=GOLD,width=165)
    text(draw,'Different team samples · same league / season · no forecasts',540,1255,22,fill=MUTED)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(path,quality=95)
    return path
