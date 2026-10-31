"""Original single-match score artwork. No external photos, logos or extra API calls."""
from pathlib import Path
from .content import local
from .live_presentation import pair

ROOT=Path(__file__).resolve().parents[1]


def render_score(spec,path):
    if spec.get('style')=='stadium':
        from .stadium_graphic import render_stadium
        return render_stadium(spec,path)
    from PIL import Image,ImageDraw,ImageFont
    m=spec['match']
    has_score=pair([m.get('home_goals'),m.get('away_goals')])
    status_only=spec.get('status_only') is True and m.get('status') in ('PST','CANC','ABD','SUSP','INT')
    if not has_score and not status_only:
        raise ValueError('Live picture requires a verified score')
    im=Image.new('RGB',(1080,1350));d=ImageDraw.Draw(im)
    for y in range(1350):
        t=y/1350
        d.line((0,y,1080,y),fill=(int(7+5*t),int(20+24*t),int(36+17*t)))
    green='#34e1aa';white='#f5f9ff';muted='#a5c0d0'
    def font(n,bold=False):return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),n)
    def center(text,y,size=36,fill=white,x=540,bold=False):
        f=font(size,bold);width=d.textlength(text,font=f)
        d.text((x-width/2,y),text,font=f,fill=fill)
    def wrap(text,width,size):
        if not isinstance(text,str) or not text.strip():raise ValueError('Live picture missing team/competition')
        lines=[];line='';f=font(size,True)
        for word in text.split():
            if d.textlength(word,font=f)>width:raise ValueError('Team name cannot fit legibly in score picture')
            if line and d.textlength(line+' '+word,font=f)>width:lines.append(line);line=word
            else:line=(line+' '+word).strip()
        return lines+[line]
    d.rounded_rectangle((35,35,1045,1315),32,outline='#285266',width=2)
    d.rectangle((75,70,81,131),fill=green)
    from football_artwork import brand
    brand(im,d,y=82,size=29)
    center(f"{local(spec['checked_at']):%d %b %Y  |  %H:%M} SAST",151,27,muted)
    league=f"{m.get('country','')} | {m.get('competition','')}"
    league_lines=wrap(league,900,30)
    if len(league_lines)>2:raise ValueError('Competition name too long for live picture')
    for i,line in enumerate(league_lines):center(line,225+i*38,30,green)
    d.rounded_rectangle((65,345,1015,805),28,fill='#112e42',outline='#285266',width=2)
    for x,label,side in ((285,'HOME','home'),(795,'AWAY','away')):
        center(label,375,23,muted,x=x)
        size=48
        while True:
            try:lines=wrap(m[side],400,size)
            except ValueError:
                if size<=34:raise
                size-=2;continue
            if len(lines)<=3:break
            size-=2
            if size<34:raise ValueError('Team name exceeds legible score picture area')
        for i,line in enumerate(lines):center(line,430+i*(size+10),size,x=x,bold=True)
    score=f"{m['home_goals']}  -  {m['away_goals']}" if has_score else {'PST':'POSTPONED','CANC':'CANCELLED','ABD':'ABANDONED','SUSP':'SUSPENDED','INT':'INTERRUPTED'}[m['status']]
    score_size=142 if has_score else 70
    if d.textlength(score,font=font(score_size,True))>900:raise ValueError('Score exceeds picture bounds')
    center(score,620,score_size,green,bold=True)
    elapsed=m.get('elapsed')
    phase=m['status']
    if phase in ('1H','2H','ET') and type(elapsed) is int:phase+=f"  |  {elapsed}'"
    if m['status']=='PEN' and pair(m.get('penalties')):phase+=f"  |  pens {m['penalties'][0]} - {m['penalties'][1]}"
    center(phase,857,40,bold=True)
    stats=m.get('statistics') or {}
    cells=[]
    for key,label in (('corners','CORNERS'),('shots_on_target','ON TARGET'),('yellow_cards','YELLOW CARDS'),('red_cards','RED CARDS')):
        values=stats.get(key)
        if pair(values):cells.append((label,f'{values[0]} - {values[1]}'))
    for i,(label,value) in enumerate(cells):
        x=285 if i%2==0 else 795;y=960+(i//2)*125
        center(label,y,22,muted,x=x);center(value,y+32,38,white,x=x,bold=True)
    # Geometric pitch motif, not a photograph or a third-party asset.
    d.rounded_rectangle((110,1235,970,1280),8,outline='#285266',width=2)
    d.line((540,1235,540,1280),fill='#285266',width=2)
    d.ellipse((520,1237,560,1277),outline='#285266',width=2)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    im.save(path,quality=94)
    return path
