"""Latest owner request: Reels only, exact captions and filmed-match covers."""
from datetime import datetime,timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from facebook_captions import reel_caption,HASHTAGS
from facebook_cover import match_rows,render_matches,apply_preferred

ROOT=Path(__file__).resolve().parents[1]


def picks(n=5):
    return [{'home':f'Home Club {i}','away':f'Away Club {i}','sel':'POISON SELECTION','odds':'ODDS POISON',
             'p':0.99,'reasons':['UNWANTED MARKET']} for i in range(n)]


def test_caption_is_exact_title_local_date_and_relevant_tags_only():
    caption=reel_caption('Any old branded caption',now=datetime(2026,10,29,23,10,tzinfo=timezone.utc))
    assert caption=="Today's Football Predictions\n30 October 2026\n\n"+' '.join(HASHTAGS)
    assert all(x not in caption for x in ('PlayReport','Source:','selection','18+','Yesterday','odds'))
    assert len(HASHTAGS)==5 and '#FootballPredictions' in HASHTAGS
    assert all(x not in ' '.join(HASHTAGS).lower() for x in ('surebet','guaranteed','viral','fyp'))


def test_cover_whitelists_names_only_not_markets_prices_or_probabilities(tmp_path,monkeypatch):
    from PIL import Image,ImageDraw
    rows=match_rows(picks(8));assert len(rows)==8 and set(rows[0])=={'home','away'}
    drawn=[];original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*a,**kw):drawn.append(str(text));return original(self,xy,text,*a,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    file=render_matches(picks(8),tmp_path/'cover.jpg',now=datetime(2026,10,30))
    assert Image.open(file).size==(1080,1920)
    text=' '.join(drawn)
    for row in rows:assert row['home'] in text and row['away'] in text
    assert all(x not in text for x in ('POISON','0.99','odds','Over','BTTS','PlayReport','Source:'))


@pytest.mark.parametrize('items',[[],picks(9),[{'home':'','away':'A'}],picks(1)*2])
def test_invalid_or_duplicate_match_covers_fail_closed(items):
    with pytest.raises(ValueError):match_rows(items)


class Response(io.BytesIO):
    def __init__(self,value):super().__init__(json.dumps(value).encode())


def test_thumbnail_upload_verified_by_new_preferred_id_and_uses_header_auth(tmp_path):
    path=tmp_path/'cover.jpg';path.write_bytes(b'image-for-offline-contract-test');calls=[]
    results=[{'data':[{'id':'old','is_preferred':True}]},{'success':True},{'data':[{'id':'new','is_preferred':True}]}]
    def open(request,**kw):calls.append(request);return Response(results.pop(0))
    assert apply_preferred(SimpleNamespace(open=open),'123','synthetic',path,'v25.0')=='verified'
    assert [r.get_method() for r in calls]==['GET','POST','GET']
    assert all('synthetic' not in r.full_url and r.get_header('Authorization')=='Bearer synthetic' for r in calls)
    assert b'is_preferred' in calls[1].data and b'image-for-offline-contract-test' in calls[1].data
    assert all('/video_reels' not in r.full_url for r in calls)


def test_cover_failure_does_not_retry_or_reupload_video(tmp_path):
    cover=tmp_path/'cover.jpg';cover.write_bytes(b'image');calls=[]
    def open(request,**kw):calls.append(request);raise OSError('private details must not escape')
    assert apply_preferred(SimpleNamespace(open=open),'123','synthetic',cover,'v25.0')=='unconfirmed'
    assert len(calls)==1


def test_missing_cover_never_calls_meta(tmp_path):
    assert apply_preferred(SimpleNamespace(open=lambda *a,**kw:pytest.fail('network')),'123','synthetic',tmp_path/'none.jpg','v25.0') is None


def test_only_requested_feeds_authorized_and_music_remains_locked():
    config=json.loads((ROOT/'config/facebook-feed.json').read_text())
    assert set(config['authorized_kinds'])=={'results','live'}
    assert not config['app_scores']['rights_confirmed'] and not config['app_scores']['coverage_verified']
    assert not config['live']['edit_existing']
    baseline=json.loads((ROOT/'tests/fixtures/facebook-feed-reel-invariants.json').read_text())
    import hashlib
    for name in ('.github/workflows/scan.yml','music.py','assets/reel/under_the_stadium_lights.mp3'):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==baseline[name]


def test_facebook_caption_change_keeps_telegram_and_media_unchanged(monkeypatch,tmp_path):
    import scanner
    old='🎬 PlayReport 16:9 widescreen shortlist — Fri 30 Oct. Today: 5 selection(s). 18+.'
    landscape=tmp_path/'landscape.mp4';landscape.write_bytes(b'landscape')
    portrait=tmp_path/'portrait.mp4';portrait.write_bytes(b'portrait');seen={}
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','synthetic');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.setattr(scanner.facebook_mod,'requested',lambda:True)
    def publish(path,caption):seen['facebook']=(path,caption);return scanner.facebook_mod.UploadResult('uploaded','456')
    monkeypatch.setattr(scanner.facebook_mod,'publish',publish)
    def send(url,**kw):seen['telegram']=kw['data']['caption'];return SimpleNamespace(status_code=200,text='')
    monkeypatch.setattr(scanner.SESSION,'post',send)
    assert scanner.send_telegram_video(landscape,old,width=1920,height=1080,facebook_path=portrait,delete_after=False)
    assert seen['facebook'][0]==portrait and seen['facebook'][1].startswith("Today's Football Predictions\n")
    assert seen['telegram']==old and portrait.read_bytes()==b'portrait' and landscape.read_bytes()==b'landscape'


def test_cover_problem_never_turns_a_published_reel_into_a_duplicate_retry(monkeypatch,tmp_path):
    import facebook_post as fb
    from test_facebook_post import configure,fake_upload,video
    configure(monkeypatch)
    monkeypatch.setattr(fb,'dimensions',lambda *a:(1080,1920))
    monkeypatch.setattr(fb.time,'sleep',lambda *a:None)
    path=video(tmp_path);path.with_suffix('.cover.jpg').write_bytes(b'cover')
    calls=fake_upload(monkeypatch)
    assert fb.publish(path,'Caption').status=='uploaded'
    receipt=json.loads(fb._receipt(path).read_text())
    assert receipt['phase']=='published' and receipt['cover_status']=='unconfirmed'
    count=len(calls)
    assert fb.publish(path,'Caption').status=='uploaded'
    assert all(request.get_method()=='GET' for request in calls[count:])  # Only the cover may be checked again.
    assert sum('/video_reels' in r.full_url and r.get_method()=='POST' for r in calls)==2
