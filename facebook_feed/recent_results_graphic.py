"""Second package card: the exact last-five samples used for comparison, not predictions."""
from pathlib import Path
from football_artwork import background,text,GOLD,MUTED,GREEN
from club_crests import paste
from .content import local


def render(spec,path):
    samples=[]
    for side in ('home','away'):
        rows=spec[side+'_results']
        if not isinstance(rows,list) or len(rows)!=5:raise ValueError('Recent-results card requires five verified results per club')
        seen=set();previous=None
        for row in rows:
            if type(row.get('id')) is not int or row['id']<=0 or row['id'] in seen:raise ValueError('Duplicate/unverified recent match')
            seen.add(row['id'])
            if any(type(row.get(k)) is not int or not 0<=row[k]<=99 for k in ('gf','ga')):raise ValueError('Unverified result score')
            if row.get('venue') not in ('H','A') or not isinstance(row.get('opponent'),str) or not row['opponent'].strip():raise ValueError('Recent opponent/venue missing')
            stamp=local(row['date'])
            if stamp>=local(spec['kickoff']) or previous and stamp>previous:raise ValueError('Recent results must be completed and newest first')
            previous=stamp
        samples.append(rows)
    image,draw=background(1350)
    from football_artwork import brand
    brand(image,draw)
    text(draw,'RECENT LEAGUE RESULTS',540,137,45,True)
    text(draw,spec['period'],540,199,24,True,fill=GOLD)
    for index,(side,rows) in enumerate(zip(('home','away'),samples)):
        base=242+index*476
        paste(image,spec[side],spec.get('country'),(115,base+31),68)
        text(draw,spec[side].upper(),575,base+10,35,True,width=810)
        draw.rounded_rectangle((64,base+79,1016,base+434),radius=18,fill=(6,20,29,245),outline=(75,99,101,255))
        text(draw,'DATE',160,base+94,21,True,fill=MUTED,width=175)
        text(draw,'H/A',285,base+94,21,True,fill=MUTED,width=50)
        text(draw,'OPPONENT',535,base+94,21,True,fill=MUTED,width=365)
        text(draw,'SCORE',847,base+94,21,True,fill=MUTED,width=115)
        text(draw,'W/D/L',952,base+94,21,True,fill=MUTED,width=80)
        for n,row in enumerate(rows):
            y=base+141+n*56
            if n:draw.line((84,y-10,996,y-10),fill=(72,92,96,255))
            text(draw,local(row['date']).strftime('%d %b %Y'),160,y+3,23,width=175)
            text(draw,row['venue'],285,y+3,24,True,width=50)
            text(draw,row['opponent'],535,y+3,25,True,width=365)
            text(draw,f"{row['gf']}–{row['ga']}",847,y,29,True,fill=GOLD,width=115)
            outcome='W' if row['gf']>row['ga'] else 'L' if row['gf']<row['ga'] else 'D'
            text(draw,outcome,952,y+2,26,True,fill=GREEN if outcome=='W' else GOLD if outcome=='D' else '#f0a6a6',width=80)
    text(draw,spec['league'],540,1195,25,True)
    text(draw,'Newest first · H home / A away · team score first',540,1243,23,fill=MUTED)
    text(draw,'Same five-match samples as the comparison picture',540,1272,22,fill=MUTED)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);image.convert('RGB').save(path,quality=95)
    return path
