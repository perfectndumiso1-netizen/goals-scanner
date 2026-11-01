"""Original 4:5 editorial artwork; no external pictures, badges, crests or paid services."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def render(spec,path):
    if spec.get('kind') in ('recent-results','venue-form'):
        from .recent_results_graphic import render as render_results
        return render_results(spec,path)
    if spec.get('kind')=='recent-h2h':
        from .h2h_graphic import render as render_h2h
        return render_h2h(spec,path)
    if spec.get('kind')=='team-comparison':
        from .comparison_graphic import render as render_comparison
        return render_comparison(spec,path)
    if spec.get('kind')=='live-score':
        from .score_graphic import render_score
        return render_score(spec,path)
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1080,1350),'#081425');draw=ImageDraw.Draw(image)
    def font(size,bold=False):
        return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),size)
    def wrapped(text,size,width=900,bold=False):
        f=font(size,bold);lines=[]
        for part in str(text).splitlines():
            line=''
            for word in part.split():
                if draw.textlength(word,font=f)>width:
                    raise ValueError('Graphic contains an unbreakable overlong name; caption needs editorial review')
                if line and draw.textlength(line+' '+word,font=f)>width:
                    lines.append(line);line=word
                else:line=(line+' '+word).strip()
            lines.append(line)
        return lines
    def text_block(text,x,y,size=30,bold=False,fill='#f4f7fd',width=900):
        lines=wrapped(text,size,width,bold)
        for line in lines:
            draw.text((x,y),line,font=font(size,bold),fill=fill)
            y+=size+9
        return y
    draw.rounded_rectangle((30,30,1050,1320),radius=28,fill='#12243b',outline='#24dbb8',width=3)
    draw.rectangle((70,73,82,126),fill='#24dbb8')
    from football_artwork import brand
    brand(image,draw,y=82,size=29)
    y=text_block(spec['title'],72,175,size=35,bold=True,fill='#24dbb8')+20
    y=text_block(spec['subtitle'],72,y,size=33,bold=True)+10
    y=text_block(spec['context'],72,y,size=25,fill='#c3d1e2')+30
    for row in spec['rows']:
        lines=wrapped(row,29)
        bottom=y+len(lines)*38+25
        if bottom>1080:
            raise ValueError('Graphic too dense for a readable mobile card; skip rather than shrink illegibly')
        draw.rounded_rectangle((62,y-9,1018,bottom),radius=12,fill='#1a3451')
        text_block(row,80,y,size=29)
        y=bottom+28
    for note in spec.get('notes',[]):
        y=text_block(note,75,y,size=23,fill='#c3d1e2')+6
        if y>1100:
            raise ValueError('Graphic notes overflow; needs editorial review')
    question=spec.get('question') or ('Which team will you watch this week?' if 'TEAMS' in spec['title'] else 'Which pattern will matter most?')
    text_block(question,75,1150,size=31,bold=True,fill='#24dbb8')
    text_block('Observed results — not guaranteed outcomes.',75,1210,size=23,fill='#c3d1e2')
    draw.text((75,1265),spec.get('footer','Source: Mr 2 Odds fixture archive | Full samples in caption'),font=font(21),fill='#c3d1e2')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);image.save(path,quality=92)
    return path
