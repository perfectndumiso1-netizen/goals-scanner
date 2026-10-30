"""Offline contracts for the requested three-video schedule and separate score/results feed.
Synthetic fixtures are NOT evidence of live data, publication rights or an actual Facebook post.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import pytest

from facebook_feed import cli, content, policy, storage
from facebook_feed.app_scores import AppScores, status
from facebook_feed.provider import ProviderError
import shortlist_reel as reel
import video_schedule

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,30,8,0,tzinfo=content.SAST)

@pytest.fixture
def cfg():
    config=cli.config(ROOT/'config/facebook-feed.json')
    config['event_monitor']['mode']='legacy'  # Explicitly selectable old reader regression.
    config['live'].update(max_posts_per_day=3,publish_every_poll=False,image_required=False)
    config['live_post_cooldown_minutes']=60
    config['score_source']='app'  # Retain independent tests for the old explicitly selectable reader.
    config['live']['app_coverage_only']=False
    return config


def root(tmp_path):
    root=tmp_path/'data/app';root.mkdir(parents=True)
    f=dict(id='2026-10-30|Test|Home|Away',home='Home',away='Away',livescore_id='123',
           date='2026-10-30',kickoff='2026-10-30 07:00',country='Test',competition='Test league')
    storage.write(root/'latest.json',{'meta':{'generated':NOW.isoformat()},'fixtures':[f]})
    return root


def result_source(tmp_path):
    r=root(tmp_path)
    picks=[dict(home=f'Home {i}',away='Away',sel='O15',label='Over 1.5 goals',odds=1.2,
                kickoff='2026-10-29 18:00') for i in range(4)]
    storage.write(r/'telegram_state.json',{'briefing_history':{'2026-10-29':picks+picks[:1]}})
    book=[{**p,'match_date':'2026-10-29','status':s,'score':'2-1' if s=='hit' else '0-0','odds':9}
          for p,s in zip(picks,['hit','miss','void','pending'])]
    storage.write(r.parent/'advisor_ledger.json',book)
    return r


def test_exact_three_windows_and_timezone():
    for hour,key in [(5,'morning'),(11,'noon'),(16,'evening')]:
        assert video_schedule.slot(NOW.replace(hour=hour))==key
    assert video_schedule.slot(NOW.replace(hour=3,tzinfo=timezone.utc))=='morning'
    assert video_schedule.slot(NOW.replace(hour=8)) is None


def test_morning_results_include_losses_void_and_unsettled_and_original_prices(tmp_path,cfg):
    post=content.morning_results(result_source(tmp_path),NOW,cfg)
    assert post['key']=='video-results:2026-10-29'
    assert '1 won · 1 lost · 1 void · 1 not yet settled' in post['caption']
    assert 'All 4 filmed selections' in post['caption']
    assert all(text in post['caption'] for text in ('WON','LOST','VOID','NOT YET SETTLED','@ 1.20'))
    assert '@ 9.00' not in post['caption']
    assert 'FT goals 2-1' in post['caption']
    state={'posts':[]};policy.reserve(post,state,NOW)
    assert not policy.allowed(post,state,NOW+timedelta(minutes=1),cfg)[0]


def test_missing_or_stale_history_does_not_fallback_to_current_shortlist(tmp_path,cfg):
    r=root(tmp_path)
    assert content.morning_results(r,NOW,cfg) is None
    r=result_source(tmp_path/'another')
    assert content.morning_results(r,NOW+timedelta(hours=13),cfg) is None


def test_only_requested_feeds_are_authorized_and_live_approvals_remain_false(cfg):
    assert cli.is_due('results',NOW,cfg)
    for kind in ('community','card','weekly','roundup'):assert not cli.is_due(kind,NOW,cfg)
    assert not cli.scores_approved(cfg)
    cfg['provider']['rights_confirmed']=cfg['provider']['account_coverage_verified']=True
    assert not cli.scores_approved(cfg)  # Another provider's approvals cannot authorize this source.
    cfg['app_scores']['rights_confirmed']=cfg['app_scores']['coverage_verified']=True
    assert cli.scores_approved(cfg)
    assert not cfg['live']['edit_existing']


class Response(io.BytesIO):
    def __init__(self,data,stamp=NOW):
        super().__init__(json.dumps(data).encode());self.headers={'Date':format_datetime(stamp.astimezone(timezone.utc))}


def event(**changes):
    value={'Eid':'123','T1':[{'Nm':'Home'}],'T2':[{'Nm':'Away'}],'Esd':'20261030070000','Eps':'45+2', 'Tr1':'1','Tr2':'0'}
    return {**value,**changes}


def app_source(tmp_path,cfg,events=None,stamp=NOW):
    calls=[]
    def open(req,**kw):
        calls.append(req.full_url)
        return Response({'Stages':[{'Events':events if events is not None else [event()]}]},stamp)
    state={};reader=AppScores(root(tmp_path),cfg,state,NOW,opener=SimpleNamespace(open=open))
    return reader,state,calls


def test_app_score_uses_same_endpoint_and_only_exact_published_fixture_ids(tmp_path,cfg):
    reader,state,calls=app_source(tmp_path,cfg,[event(),event(Eid='999',Tr1='9')])
    matches,stamp=reader.fixtures()
    assert len(matches)==1 and matches[0]['fixture_id']=='2026-10-30|Test|Home|Away'
    assert matches[0]['home_goals']==1 and matches[0]['away_goals']==0
    assert matches[0]['status']=='1H'
    assert '/date/soccer/20261030/2?MD=1' in calls[0]
    assert reader.fixtures()[0]==matches and len(calls)==1
    reader.now+=timedelta(seconds=181)
    with pytest.raises(ProviderError,match='fresh'):reader.fixtures()
    assert len(calls)==1  # Cooldown does not rebrand old cached data as fresh.


@pytest.mark.parametrize('changes',[{'Eid':'999'},{'T1':[{'Nm':'Wrong club'}]}, {'Esd':'20261029070000'},
    {'Eps':'unknown'},{'Tr1':None},{'Tr1':True},{'Tr2':-1},{'Eps':'AP'}])
def test_app_scores_fail_closed_on_identity_date_score_and_penalty_ambiguity(tmp_path,cfg,changes):
    reader,_,_=app_source(tmp_path,cfg,[event(**changes)])
    assert reader.fixtures()[0]==[]


def test_stale_http_header_cannot_be_called_live(tmp_path,cfg):
    reader,_,_=app_source(tmp_path,cfg,stamp=NOW-timedelta(seconds=181))
    with pytest.raises(ProviderError,match='stale'):reader.fixtures()


def test_rate_limit_persists_cooldown_without_retrying(tmp_path,cfg):
    reader,state,calls=app_source(tmp_path,cfg)
    def open(req,**kw):
        calls.append(req.full_url)
        raise HTTPError(req.full_url,429,'limited',{'Retry-After':'1200'},io.BytesIO())
    reader.opener=SimpleNamespace(open=open)
    with pytest.raises(ProviderError,match='429'):reader.fixtures()
    with pytest.raises(ProviderError,match='cooldown'):reader.fixtures()
    assert len(calls)==1


def test_existing_score_caps_preserved_and_app_scope_does_not_use_editorial_competitions(tmp_path,cfg):
    reader,_,_=app_source(tmp_path,cfg);matches,_=reader.fixtures()
    cfg['live']['competitions']=[]
    assert policy.selected_matches(matches,cfg)==matches
    state={'posts':[]};post=policy.score_post(matches,state,NOW,cfg)
    assert post
    entry=policy.reserve(post,state,NOW-timedelta(hours=2));entry.update(status='published',post_id='123_456')
    assert policy.score_post(matches,state,NOW,cfg) is None
    changed=[{**matches[0],'away_goals':1}]
    assert policy.score_post(changed,state,NOW,cfg) is not None  # A single app score change is significant.
    assert cfg['live']['max_posts_per_day']==3 and cfg['live_post_cooldown_minutes']==60


def test_footer_is_continuous_with_fixed_age_and_pillow_type_not_voice(monkeypatch,tmp_path):
    calls=[];monkeypatch.setattr(reel,'_run',lambda cmd,label:calls.append((cmd,label)))
    monkeypatch.setattr(reel,'_ACTIVE_SIZE',(1080,1920))
    reel.animated_warning(tmp_path/'in.mp4',tmp_path/'out.mp4',123,'ffmpeg',work=tmp_path)
    cmd,label=calls[0]
    assert 'continuous' in label and cmd[cmd.index('-t')+1]=='123.000'
    filter=cmd[cmd.index('-filter_complex')+1]
    assert 'mod(t*60,' in filter and 'crop=' in filter
    assert cmd.count('-i')==3 and '-an' in cmd  # still silent picture; original music is muxed afterward
    assert 'No guaranteed wins' in reel.WARNING_TEXT and 'not betting advice' in reel.WARNING_TEXT
    from PIL import Image
    assert Image.open(tmp_path/'warning-base.png').size==(1080,80)


def test_revalidation_before_send_blocks_unauthorized_live_plan(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true');monkeypatch.setenv('GITHUB_RUN_ID','1')
    now=datetime.now(content.SAST)
    post=content.candidate('live','key','topic','safe text',expires_at=(now+timedelta(minutes=3)).isoformat())
    state={'posts':[]};entry=policy.reserve(post,state,now);entry['run_key']='1-1'
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Facebook request may happen before approvals'))
    assert cli.main(['send','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    assert content.load(tmp_path/'checkpoint/state.json')['posts'][0]['status']=='cancelled'


def test_publish_preview_cannot_unpause_unrequested_editorial_types(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    storage.write(tmp_path/'config.json',cfg)
    monkeypatch.setattr(cli,'build',lambda *a,**k:pytest.fail('Unauthorised type must be stopped before building'))
    assert cli.main(['prepare','--kind','community','--preview','--publish','--bootstrap',
                     '--config',str(tmp_path/'config.json'),'--work',str(tmp_path/'work')])==0
    assert content.load(tmp_path/'work/report.json')[0]['status']=='blocked'


def test_unapproved_scheduled_live_job_skips_without_provider_or_live_bootstrap(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    storage.write(tmp_path/'config.json',cfg)
    monkeypatch.setattr(cli,'build',lambda *a,**k:pytest.fail('Blocked source must not be polled by scheduled publishing'))
    assert cli.main(['prepare','--kind','live','--publish','--config',str(tmp_path/'config.json'),'--work',str(tmp_path/'work')])==0
    report=content.load(tmp_path/'work/report.json')
    assert report[0]['status']=='blocked'
