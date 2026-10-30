"""Matches-only Reel cover from the exact filmed picks, never markets/prices/model fields."""
from datetime import datetime
from pathlib import Path
import json
import hashlib
from urllib.error import HTTPError
import re
import uuid
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent


def match_rows(picks):
    rows=[];seen=set()
    for pick in picks:
        home,away=pick.get('home'),pick.get('away')
        if not isinstance(home,str) or not home.strip() or not isinstance(away,str) or not away.strip():
            raise ValueError('Cover requires real team names')
        pair=(home.strip(),away.strip())
        if pair in seen:raise ValueError('Cover cannot repeat a match')
        seen.add(pair)
        # Whitelist these fields. In particular, no sel, odds, price, probabilities or reasons.
        rows.append({'home':pair[0],'away':pair[1]})
    if not 1<=len(rows)<=8:raise ValueError('Cover supports one to eight actual filmed matches')
    return rows


def render_matches(picks,path,*,now=None):
    from PIL import Image,ImageDraw,ImageFont
    rows=match_rows(picks)
    today=now or datetime.now(ZoneInfo('Africa/Johannesburg'))
    if today.tzinfo is not None:today=today.astimezone(ZoneInfo('Africa/Johannesburg'))
    image=Image.new('RGB',(1080,1920),'#091726');draw=ImageDraw.Draw(image)
    def font(size,bold=False):return ImageFont.truetype(str(ROOT/'assets/fonts'/('LiberationSans-Bold.ttf' if bold else 'LiberationSans-Regular.ttf')),size)
    def wrap(text,size,width=860):
        lines=[];line=''
        for word in text.split():
            if draw.textlength(word,font=font(size,True))>width:raise ValueError('Team name cannot fit readable cover')
            joined=(line+' '+word).strip()
            if draw.textlength(joined,font=font(size,True))>width:lines.append(line);line=word
            else:line=joined
        if line:lines.append(line)
        return lines
    draw.rounded_rectangle((35,75,1045,1845),radius=35,outline='#20d4b4',width=4)
    draw.text((85,155),'MATCHES IN THIS VIDEO',font=font(53,True),fill='#ffffff')
    draw.text((85,235),today.strftime('%d %B %Y'),font=font(34),fill='#20d4b4')
    top=350;available=1270;row_height=min(205,available//len(rows))
    for i,row in enumerate(rows):
        lines=wrap(f"{row['home']} vs {row['away']}",39)
        if len(lines)*49+38>row_height:raise ValueError('Match names need editorial review to fit cover')
        y=top+i*row_height
        draw.rounded_rectangle((70,y,1010,y+row_height-16),radius=18,fill='#18334e')
        text_top=y+(row_height-16-len(lines)*49)//2
        for line in lines:
            draw.text((105,text_top),line,font=font(39,True),fill='#ffffff');text_top+=49
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    image.save(path,quality=93)
    return path


def apply_preferred(opener,video_id,token,cover,graph_version):
    """One best-effort cover upload after native publication. Never reuploads a video.

    Meta's Video Thumbnails edge requires permissions beyond some Reel tokens.
    A rejected/ambiguous request is reported, not allowed to fail/retry the Reel.
    """
    cover=Path(cover)
    if not cover.is_file():return None
    if not re.fullmatch(r'[1-9]\d*',str(video_id)):return 'unconfirmed'
    try:
        if cover.stat().st_size>8*1024*1024:return 'unconfirmed'
        url=f'https://graph.facebook.com/{graph_version}/{video_id}/thumbnails'
        def read():
            with opener.open(Request(url+'?fields=id,is_preferred',headers={'Authorization':f'Bearer {token}'}),timeout=30) as response:
                value=json.loads(response.read(256*1024))
            if not isinstance(value,dict) or 'error' in value or not isinstance(value.get('data'),list):raise ValueError('Thumbnail read unavailable')
            return value.get('data',[])
        digest=hashlib.sha256(cover.read_bytes()).hexdigest()
        checkpoint=cover.with_name(cover.stem.replace('.cover','')+'.cover-state.json')
        try:state=json.loads(checkpoint.read_text())
        except (OSError,ValueError):state={}
        if state.get('video_id')!=str(video_id):state={}
        def save(phase):
            state.update(video_id=str(video_id),sha256=digest,phase=phase)
            temp=checkpoint.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.replace(checkpoint)
        if state.get('sha256')==digest and state.get('phase') in ('attempting','accepted','verified'):
            after=read()
            verified=any(row.get('id') and row.get('is_preferred') is True and str(row['id']) not in state.get('before',[]) for row in after)
            if verified:save('verified');return 'verified'
            return 'unconfirmed'  # Ambiguous POST/processing: read only, not another thumbnail POST.
        if state.get('phase') in ('attempting','accepted'):return 'unconfirmed'
        initial=read()
        state['before']=[str(row['id']) for row in initial]
        save('attempting')  # Durable before mutation, so a timeout cannot cause a blind duplicate POST.
        boundary='ReelCover'+uuid.uuid4().hex
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="is_preferred"\r\n\r\ntrue\r\n'
              f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="matches.jpg"\r\nContent-Type: image/jpeg\r\n\r\n').encode()
        body+=cover.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        request=Request(url,data=body,method='POST',headers={'Authorization':f'Bearer {token}',
            'Content-Type':f'multipart/form-data; boundary={boundary}','Content-Length':str(len(body))})
        try:
            with opener.open(request,timeout=45) as response:result=json.loads(response.read(65536))
        except HTTPError as error:
            if error.code in (400,401,403,404):save('rejected')
            raise
        if not isinstance(result,dict) or result.get('success') is not True:return 'unconfirmed'
        save('accepted')
        after=read()
        if any(row.get('id') and row.get('is_preferred') is True and str(row['id']) not in state['before'] for row in after):
            save('verified');return 'verified'
        return 'unconfirmed'
    except Exception:
        # No raw HTTP exceptions, bodies, signed URLs or credentials enter logs/state.
        return 'unconfirmed'
