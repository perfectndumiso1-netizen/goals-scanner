"""Approved portrait Reel cover: exact filmed matches and verified combined price."""
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


def cover_total(picks):
    """Validate every real filmed price, then match the existing video calculation.

    Missing/ambiguous prices never become a sample total or an invented price.
    Do not apply new selection/model rules or alter the filmed pick set here.
    """
    import math
    from video_card import combined_odds
    picks=list(picks)
    if not picks:raise ValueError('Cover requires filmed selections')
    for pick in picks:
        value=pick.get('odds')
        if isinstance(value,bool) or not isinstance(value,(str,int,float)):
            raise ValueError('Cover requires the exact filmed selection prices')
        try:price=float(value)
        except (ValueError,TypeError):raise ValueError('Cover requires valid filmed prices') from None
        if not math.isfinite(price) or not 1<price<=1000:
            raise ValueError('Cover price missing, nonfinite or outside safe bounds')
    total=combined_odds(picks)
    if not math.isfinite(total) or total>1e12:raise ValueError('Cover combined price outside safe bounds')
    return f'{total:.2f}'


def render_matches(picks,path,*,now=None):
    from football_artwork import background,text,GOLD,MUTED,GREEN
    from club_crests import paste
    picks=list(picks);rows=match_rows(picks);total=cover_total(picks)
    today=now or datetime.now(ZoneInfo('Africa/Johannesburg'))
    if today.tzinfo is not None:today=today.astimezone(ZoneInfo('Africa/Johannesburg'))
    image,draw=background(1920)
    from football_artwork import brand
    brand(image,draw,y=83,size=29)
    text(draw,'FOOTBALL PICKS',540,145,66,True)
    text(draw,today.strftime('%d %B %Y'),540,234,28,fill=GOLD)
    draw.rounded_rectangle((76,300,1004,598),radius=32,fill=(8,25,34,230),outline=GOLD,width=2)
    text(draw,total,540,326,170,True,fill=GOLD)
    text(draw,'Odds combined',540,515,51,True)
    from player_photos import read as player_photo, paste as paste_player
    from football_derbies import label as derby_label
    featured=None
    # One actual filmed matchup only, never ten competing portraits. For six to
    # eight matches retain the spacious crest-only cover rather than shrink text.
    if len(rows)<=5:
        for row,pick in zip(rows,picks):
            home=player_photo(row['home'],pick.get('country'),on=pick.get('kickoff') or today)
            away=player_photo(row['away'],pick.get('country'),on=pick.get('kickoff') or today)
            if home and away:
                featured=(row,pick,home,away);break
    start,room=722,930
    if featured:
        row,pick,home,away=featured
        name=derby_label(row['home'],row['away'],pick.get('country')) or 'FEATURED MATCH'
        text(draw,name.upper(),540,622,29,True,fill=GREEN)
        paste_player(image,home,(145,675,405,945))
        paste_player(image,away,(675,675,935,945))
        text(draw,'VS',540,785,35,True,fill=GOLD)
        text(draw,home[1],275,953,24,True,width=380)
        text(draw,away[1],805,953,24,True,width=380)
        start,room=1060,610
    text(draw,'MATCHES IN THIS VIDEO',540,start-60,26,True,fill=GREEN)
    # Up to eight still fit without inventing/omitting any filmed selections.
    step=min(174,room//len(rows));height=step-18;size=min(94,height-28)
    for index,(row,pick) in enumerate(zip(rows,picks)):
        y=start+index*step
        draw.rounded_rectangle((76,y,1004,y+height),radius=19,fill=(9,25,34,225),outline=(71,94,99,255),width=1)
        paste(image,row['home'],pick.get('country'),(162,y+height/2),size)
        paste(image,row['away'],pick.get('country'),(918,y+height/2),size)
        derby=derby_label(row['home'],row['away'],pick.get('country'))
        offset=12 if derby else 0
        text(draw,row['home'],365,y+height/2-17-offset,30,True,width=280)
        text(draw,'vs',540,y+height/2-14-offset,25,fill=MUTED)
        text(draw,row['away'],715,y+height/2-17-offset,30,True,width=280)
        if derby:text(draw,derby.upper(),540,y+height/2+19,22,True,fill=GREEN,width=500)
    text(draw,'No outcome is guaranteed.',540,1780,25,fill=MUTED)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    image.convert('RGB').save(path,quality=95)
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
