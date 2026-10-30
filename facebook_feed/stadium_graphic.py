"""Template-inspired 4:5 live score card. All numbers come from the verified snapshot.

Rendering is offline: only existing local stadium artwork and validated local crest
files are used. Optional crest retrieval belongs to the prepare phase, never render.
"""
from pathlib import Path
from .content import local
from .live_presentation import pair

ROOT=Path(__file__).resolve().parents[1]
LABELS={'PST':'POSTPONED','CANC':'CANCELLED','ABD':'ABANDONED','SUSP':'SUSPENDED','INT':'INTERRUPTED'}


def clock(match):
    status=match['status'];minute=match.get('elapsed')
    if status in ('1H','2H','ET') and type(minute) is int:
        extra=match.get('added_time')
        return str(minute)+(f'+{extra}' if type(extra) is int and extra>0 else '')+'′'
    return {'P':'PENALTIES','PEN':'FT · PEN','AET':'FT · AET'}.get(status,LABELS.get(status,status))


def render_stadium(spec,path):
    from PIL import Image,ImageDraw,ImageFont,ImageOps
    m=spec['match'];scored=pair([m.get('home_goals'),m.get('away_goals')])
    if not scored and not (spec.get('status_only') is True and m.get('status') in LABELS):
        raise ValueError('Live picture requires a verified score or confirmed interruption status')
    im=ImageOps.fit(Image.open(ROOT/'assets/reel/bg_stadium.jpg').convert('RGB'),(1080,1350),centering=(.5,.6)).convert('RGBA')
    veil=Image.new('RGBA',im.size);v=ImageDraw.Draw(veil)
    for y in range(1350):
        # Keep the grass/lights recognisable, but never behind unreadable white text.
        opacity=int(145+45*max(0,1-abs(y-640)/520))
        v.line((0,y,1080,y),fill=(0,19,35,opacity))
    im=Image.alpha_composite(im,veil);d=ImageDraw.Draw(im)
    white='#f9fcff';green='#00e4a0';muted='#a7bdcb';line='#50879a'
    def font(size,bold=True):
        return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),size)
    def text(value,x,y,size=40,fill=white,bold=True):
        d.text((x+1,y+3),value,font=font(size,bold),anchor='mm',fill='#00121f',stroke_width=1)
        d.text((x,y),value,font=font(size,bold),anchor='mm',fill=fill)
    def fitted(value,width,maximum,minimum):
        for size in range(maximum,minimum-1,-2):
            if d.textlength(value,font=font(size))<=width:return size
        raise ValueError('Score/status exceeds legible live picture bounds')
    def wrapped(value,width,maximum=44,minimum=30,max_lines=3):
        if not isinstance(value,str) or not value.strip():raise ValueError('Live picture missing team/competition')
        for size in range(maximum,minimum-1,-2):
            rows=[];current='';f=font(size)
            if any(d.textlength(word,font=f)>width for word in value.split()):continue
            for word in value.split():
                if current and d.textlength(current+' '+word,font=f)>width:rows.append(current);current=word
                else:current=(current+' '+word).strip()
            rows.append(current)
            if len(rows)<=max_lines:return rows,size
        raise ValueError('Team/competition name cannot fit legibly in live picture')
    # Angled framing echoes the supplied template, without copying its match data.
    d.polygon([(0,330),(95,560),(95,1030),(0,850)],fill='#074150')
    d.polygon([(1080,330),(985,560),(985,1030),(1080,850)],fill='#074150')
    d.line([(0,440),(68,610),(68,1020)],fill='#137583',width=3)
    d.line([(1080,440),(1012,610),(1012,1020)],fill='#137583',width=3)
    text('PLAYREPORT ZA',540,100,31,muted)
    d.line((340,143,740,143),fill=green,width=3)
    competition,size=wrapped(m.get('competition','').upper(),900,42,30,2)
    for i,row in enumerate(competition):text(row,540,225+i*52,size)
    d.line((100,320,420,320),fill=line,width=2);d.line((660,320,980,320),fill=line,width=2)
    # Simple neutral football icon; not a fabricated league/club logo.
    d.ellipse((521,300,559,338),outline=white,width=2)
    d.polygon([(540,310),(549,317),(546,328),(534,328),(531,317)],fill=white)
    badge=clock(m);badge_size=fitted(badge,390,49,25)
    d.polygon([(335,375),(755,375),(735,453),(315,453)],fill='#006c52',outline=green,width=2)
    text(badge,535,414,badge_size)
    # A failed/missing CDN crest is omitted, never replaced by an invented crest.
    from .crest_cache import read_crest
    for side,x in (('home',200),('away',880)):
        crest=read_crest((spec.get('crests') or {}).get(side))
        if crest is not None:
            crest.thumbnail((280,310),Image.Resampling.LANCZOS)
            im.alpha_composite(crest,(int(x-crest.width/2),int(615-crest.height/2)))
        else:text('HOME' if side=='home' else 'AWAY',x,615,26,muted)
    # Drawing context must be refreshed after alpha-compositing the transparent crests.
    d=ImageDraw.Draw(im)
    score=f"{m['home_goals']} - {m['away_goals']}" if scored else LABELS[m['status']]
    text(score,540,615,fitted(score,420,210,38 if not scored else 80),white)
    if pair(m.get('halftime')):
        ht=f"HT {m['halftime'][0]} - {m['halftime'][1]}"
        text(ht,540,766,fitted(ht,390,37,25),muted)
    if m['status'] in ('P','PEN') and pair(m.get('penalties')):
        penalties=f"PENS {m['penalties'][0]} - {m['penalties'][1]}"
        text(penalties,540,1034,fitted(penalties,820,35,25),muted)
    for side,x in (('home',205),('away',875)):
        rows,size=wrapped(m[side].upper(),390)
        for i,row in enumerate(rows):text(row,x,835+i*(size+12),size)
        d.polygon([(x-155,1000),(x+162,1000),(x+155,1007),(x-162,1007)],fill=green)
    footer=Image.new('RGBA',im.size);f=ImageDraw.Draw(footer)
    f.rectangle((0,1120,1080,1305),fill=(0,19,27,218));im=Image.alpha_composite(im,footer);d=ImageDraw.Draw(im)
    checked=local(spec['checked_at'])
    # Actual observation date/time, not kickoff time or the supplied reference's clock.
    text(checked.strftime('%d %B %Y').upper(),565,1173,35,bold=False)
    text(checked.strftime('%H:%M')+' SAST',570,1249,37,bold=False)
    d.rounded_rectangle((291,1156,325,1188),4,outline=white,width=3)
    d.line((291,1166,325,1166),fill=white,width=3)
    d.line((300,1151,300,1161),fill=white,width=3);d.line((316,1151,316,1161),fill=white,width=3)
    d.ellipse((357,1231,389,1263),outline=white,width=3)
    d.line((373,1236,373,1248,383,1254),fill=white,width=3)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    im.convert('RGB').save(path,quality=94)
    return path
