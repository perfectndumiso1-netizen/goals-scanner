"""Template styling and public crest transport tests; offline only, never Page evidence."""
from datetime import datetime
import io
from pathlib import Path
from time import time
from urllib.error import HTTPError
import pytest
from PIL import Image,ImageDraw
from facebook_feed import cli,crest_cache,graphics,stadium_graphic,storage

ROOT=Path(__file__).resolve().parents[1]


def match(**overrides):
    return dict(home='Synthetic Home',away='Synthetic Away',home_goals=1,away_goals=0,
                status='2H',elapsed=90,added_time=2,halftime=[0,0],competition='Synthetic League',**overrides)


def spec(m=None):return {'kind':'live-score','style':'stadium','match':m or match(),'checked_at':'2026-10-30T17:51:00+02:00'}


def png(size=(150,150)):
    out=io.BytesIO();Image.new('RGBA',size,(20,180,100,255)).save(out,format='PNG');return out.getvalue()


class Response:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.body[:n]


class Opener:
    def __init__(self,*responses):self.responses=list(responses);self.calls=[]
    def open(self,request,timeout=0):
        self.calls.append((request,timeout));response=self.responses.pop(0)
        if isinstance(response,Exception):raise response
        return response


def test_template_renders_portrait_native_jpeg_and_never_downloads(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Renderer must stay offline')
    monkeypatch.setattr(crest_cache,'fetch_crest',forbidden)
    path=graphics.render(spec(),tmp_path/'score.jpg')
    im=Image.open(path)
    assert im.size==(1080,1350) and im.format=='JPEG' and path.stat().st_size<8*1024*1024


def rendered_text(tmp_path,monkeypatch,value):
    strings=[];original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*args,**kwargs):strings.append(text);return original(self,xy,text,*args,**kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    graphics.render(value,tmp_path/'render.jpg')
    return strings


def test_score_clock_half_time_and_observation_time_use_only_source_fields(tmp_path,monkeypatch):
    strings=rendered_text(tmp_path,monkeypatch,spec())
    for value in ('1 - 0','90+2′','HT 0 - 0','SYNTHETIC','HOME','AWAY','SYNTHETIC LEAGUE','30 OCTOBER 2026','17:51 SAST'):assert value in strings


def test_unknown_half_time_not_filled_with_fake_zero(tmp_path,monkeypatch):
    value=spec();value['match']['halftime']=None
    strings=rendered_text(tmp_path,monkeypatch,value)
    assert not any(v.startswith('HT ') for v in strings)


@pytest.mark.parametrize('status,label',[('FT','FT'),('HT','HT'),('PEN','FT · PEN'),('P','PENALTIES'),('SUSP','SUSPENDED')])
def test_terminal_or_significant_status_is_not_drawn_as_live_minute(status,label):
    value=match();value['status']=status
    assert stadium_graphic.clock(value)==label


def test_null_cancelled_score_is_status_panel_not_zero(tmp_path,monkeypatch):
    value=spec();value['status_only']=True;value['match'].update(status='CANC',home_goals=None,away_goals=None,halftime=None)
    strings=rendered_text(tmp_path,monkeypatch,value)
    assert 'CANCELLED' in strings and '0 - 0' not in strings
    value['match']['status']='2H'
    with pytest.raises(ValueError):graphics.render(value,tmp_path/'invalid.jpg')


def test_missing_or_invalid_crests_do_not_fabricate_badges(tmp_path):
    value=spec();value['crests']={'home':str(tmp_path/'missing.png')}
    assert graphics.render(value,tmp_path/'score.jpg').is_file()
    (tmp_path/'bad.png').write_bytes(b'not an image')
    assert crest_cache.read_crest(tmp_path/'bad.png') is None


def test_real_local_png_crests_are_accepted(tmp_path):
    crest=tmp_path/'crest.png';crest.write_bytes(png())
    value=spec();value['crests']={'home':str(crest),'away':str(crest)}
    assert graphics.render(value,tmp_path/'with-crests.jpg').is_file()


def test_long_names_fail_closed_instead_of_clipping(tmp_path):
    value=spec();value['match']['home']='X'*500
    with pytest.raises(ValueError,match='fit legibly'):graphics.render(value,tmp_path/'long.jpg')


def test_crest_fetch_uses_exact_public_team_path_without_any_credentials(tmp_path,monkeypatch):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic-private-football')
    monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic-private-page')
    opener=Opener(Response(png()))
    result=crest_cache.fetch_crest(42,tmp_path,opener)
    request,timeout=opener.calls[0]
    assert request.full_url=='https://media.api-sports.io/football/teams/42.png' and timeout==4
    assert request.header_items()==[('Accept','image/png')]
    assert crest_cache.read_crest(result).size==(150,150)
    assert crest_cache.fetch_crest(42,tmp_path,opener)==result and len(opener.calls)==1


@pytest.mark.parametrize('team_id',[None,True,0,-1,2**63,'42','https://untrusted.invalid/x.png','../outside'])
def test_untrusted_crest_ids_never_make_requests_or_paths(tmp_path,team_id):
    opener=Opener()
    assert crest_cache.fetch_crest(team_id,tmp_path,opener) is None and not opener.calls


def test_failed_cdn_request_backs_off_and_then_can_retry(tmp_path):
    opener=Opener(HTTPError('https://media.api-sports.io/',404,'unavailable',{},io.BytesIO()),Response(png()))
    assert crest_cache.fetch_crest(42,tmp_path,opener) is None
    assert crest_cache.fetch_crest(42,tmp_path,opener) is None and len(opener.calls)==1
    assert crest_cache.fetch_crest(42,tmp_path,opener,now=time()+7*3600)
    assert len(opener.calls)==2


@pytest.mark.parametrize('data',[b'<svg></svg>',b'x'*(crest_cache.MAX_BYTES+1),png((1025,1))])
def test_unsafe_oversized_or_invalid_image_does_not_enter_positive_cache(tmp_path,data):
    assert crest_cache.fetch_crest(42,tmp_path,Opener(Response(data))) is None
    assert not (tmp_path/'42.png').exists()


def test_prepare_uses_only_selected_match_team_ids(monkeypatch,tmp_path):
    calls=[]
    def fake(team,directory):calls.append(team);return str(tmp_path/f'{team}.png') if team else None
    monkeypatch.setattr(crest_cache,'fetch_crest',fake)
    value=spec();value['match'].update(home_team_id=42,away_team_id=77)
    crest_cache.prepare(value,tmp_path)
    assert calls==[42,77] and set(value['crests'])=={'home','away'}


def test_crest_cache_is_bounded_for_success_and_failure(tmp_path,monkeypatch):
    monkeypatch.setattr(crest_cache,'MAX_CACHE_FILES',2)
    for team in range(1,5):crest_cache.fetch_crest(team,tmp_path,Opener(Response(b'bad image')))
    assert len(list(tmp_path.glob('*.missing')))==2


def test_confirmed_independent_allocations_have_separate_preserved_budgets():
    cfg=cli.config(ROOT/'config/facebook-feed.json')
    assert cfg['event_monitor']['failover_permitted'] and cfg['event_monitor']['permission_reference']
    assert {slot['quota_group'] for slot in cfg['event_monitor']['key_slots'].values()}=={'primary','backup-1','backup-2'}
    assert not cfg['event_monitor']['publish_enabled'] and cfg['event_monitor']['daily_request_budget']==90
    assert cfg['live']['graphic_style']=='stadium' and cfg['live']['crests_enabled']


@pytest.mark.parametrize('field,value',[('graphic_style','untrusted'),('crests_enabled','true')])
def test_invalid_picture_config_rejected(tmp_path,field,value):
    cfg=cli.config(ROOT/'config/facebook-feed.json');cfg['live'][field]=value
    storage.write(tmp_path/'cfg.json',cfg)
    with pytest.raises(ValueError):cli.config(tmp_path/'cfg.json')
