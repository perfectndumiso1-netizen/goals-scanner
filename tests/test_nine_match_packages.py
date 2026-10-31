"""Nine real-match opportunities and durable two-photo publication; entirely offline."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image
from facebook_feed import cli,editorial as e,match_packages as packages,policy,storage,watchdog as w,photo_package
from facebook_feed.publisher import PageFeed,PublishError
from facebook_feed.recent_results_graphic import render
from test_football_editorial import NOW,Fake,raw

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


@pytest.mark.parametrize('hour',range(8,17))
def test_nine_exact_sast_hours_and_one_hour_window(cfg,hour):
    at=NOW.replace(hour=hour,minute=0,second=0)
    slot=f'match{hour-7:02d}'
    assert e.due(at,cfg)==slot and cli.is_due('editorial',at,cfg)
    assert e.due(at+timedelta(minutes=59,seconds=59),cfg)==slot
    assert e.due(at.astimezone(timezone.utc),cfg)==slot
    assert e.due(at+timedelta(hours=1),cfg)!=slot


@pytest.mark.parametrize('hour,minute',[(7,29),(17,0),(19,30),(23,0)])
def test_legacy_bulletins_no_longer_overlap_nine_match_posts(cfg,hour,minute):
    assert not cli.is_due('editorial',NOW.replace(hour=hour,minute=minute),cfg)


def test_config_and_workflow_only_nine_primary_plus_same_slot_backups(cfg):
    assert cfg['editorial']['max_posts_per_day']==10 and cfg['editorial']['match_posts_per_day']==9 and cfg['editorial']['package_mode'] is True
    assert cfg['editorial']['schedule_sast']==dict(packages.SLOTS)
    wf=yaml.safe_load((ROOT/'.github/workflows/facebook-editorial.yml').read_text())
    on=wf.get('on',wf.get(True))
    assert on['schedule']==[{'cron':'30 5 * * *'},{'cron':'50 5 * * *'},{'cron':'0 6-14 * * *'},{'cron':'50 6-14 * * *'}]
    assert wf['jobs']['content']['with']['bootstrap'] is False
    assert cfg['authorized_kinds']==['editorial'] and cfg['highlightly']['daily_request_budget']==100


def test_comparison_and_results_use_identical_verified_sample_with_no_extra_api(cfg):
    api=Fake();post,reason=e.build(cfg,{},NOW,api)
    assert post,reason
    assert [g['kind'] for g in post['graphics']]==['team-comparison','recent-results']
    assert len(api.calls)==6 and post['caption'].count('• ')==3
    recent=post['graphics'][1];evidence=post['snapshot'][0]
    for side in ('home','away'):
        assert recent[side+'_results']==evidence[side+'_sample']['matches']
        assert len(recent[side+'_results'])==5
        assert all(r['opponent'] and r['venue'] in ('H','A') for r in recent[side+'_results'])
    assert post['slot_key']==f'editorial:{NOW.date()}:match03'


def test_away_results_keep_team_score_first_and_correct_opponent(cfg):
    api=Fake()
    for r in api.hist['psl']:
        r['homeTeam'],r['awayTeam']=r['awayTeam'],r['homeTeam'];api.details[r['id']]=deepcopy(r)
    post,reason=e.build(cfg,{},NOW,api);assert post,reason
    rows=post['graphics'][1]['home_results']
    assert all(r['venue']=='A' and r['gf']==0 and r['ga']==2 for r in rows)
    assert all(r['opponent']!='Example Club 10' for r in rows)


def test_earliest_safe_kickoff_not_arbitrary_league_or_duplicate(cfg):
    later=raw(1,when=NOW+timedelta(hours=6));earlier=raw(2,league='epl',when=NOW+timedelta(hours=3))
    api=Fake(today=[later,earlier]);s={};post,reason=e.build(cfg,s,NOW,api);assert post,reason
    assert post['fixture_ids']==[2]
    policy.reserve(post,s,NOW)['status']='published'
    post,reason=e.build(cfg,s,NOW+timedelta(hours=1),api);assert post,reason
    assert post['fixture_ids']==[1]


def test_nine_distinct_matches_league_coverage_and_daily_cap_with_shared_cached_data(cfg):
    at=NOW.replace(hour=8);matches=[]
    leagues=list(e.LEAGUES)
    # Earlier PSL games plus all six leagues: reserve remaining places for coverage.
    for i in range(9):
        league=leagues[0] if i<4 else leagues[i-3]
        matches.append(raw(i+1,league=league,when=at+timedelta(hours=10,minutes=i)))
    api=Fake(at,today=matches);s={};ids=[];represented=set()
    for hour in range(8,17):
        now=at.replace(hour=hour);api.at=now.isoformat()
        post,reason=e.build(cfg,s,now,api);assert post,reason
        assert policy.allowed(post,s,now,cfg)[0]
        ids+=post['fixture_ids'];represented.add(post['snapshot'][0]['fixture']['league'])
        policy.reserve(post,s,now)['status']='published'
    assert len(ids)==len(set(ids))==9 and represented==set(e.LEAGUES)
    assert sum(c[0]=='catalog' and 'leagueId' in c[1] for c in api.calls)==12
    # Same underlying history is reused for both pictures, never fetched twice.
    assert len(api.calls)<100
    extra_feature=dict(post,key='extra-match',topic='feature:extra',slot_key='extra',caption_hash=hashlib.sha256(b'new caption').hexdigest())
    assert policy.allowed(extra_feature,s,now+timedelta(hours=1),cfg)==(False,'editorial nine-match cap')
    bulletin={'kind':'editorial','status':'published','at':at.replace(hour=7,minute=30).isoformat(),'key':'fixtures','topic':'fixtures','caption_hash':'fixture-hash','slot_key':'fixtures'}
    s['posts'].insert(0,bulletin)
    extra=dict(post,key='extra',topic='extra',slot_key='extra')
    assert not policy.allowed(extra,s,now+timedelta(hours=1),cfg)[0]


def test_unusable_fixture_does_not_starve_every_later_slot(cfg):
    a=raw(1,when=NOW+timedelta(hours=7));b=raw(2,league='epl',when=NOW+timedelta(hours=8))
    api=Fake(today=[a,b]);api.hist['psl']=[];s={}
    assert e.build(cfg,s,NOW,api)[0] is None
    post,reason=e.build(cfg,s,NOW+timedelta(hours=1),api)
    assert post,reason
    assert post['fixture_ids']==[2] and s['football_editorial']['package_unavailable']=={'1':'verified_sample_unavailable'}


def test_missing_facts_never_create_a_package_or_fabricated_results(cfg):
    api=Fake();api.hist['psl'][0]['state']['score']['current']=None
    post,reason=e.build(cfg,{},NOW,api)
    assert post is None and 'missing' in reason


def test_recent_card_real_dates_scores_opponents_and_orientation(cfg,tmp_path,monkeypatch):
    post,_=e.build(cfg,{},NOW,Fake());spec=post['graphics'][1];texts=[]
    from PIL import ImageDraw
    original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*a,**kw):texts.append(str(text));return original(self,xy,text,*a,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    out=render(spec,tmp_path/'recent.jpg')
    assert Image.open(out).size==(1080,1350)
    assert '2–0' in texts and 'W' in texts
    assert all(r['opponent'] in texts for r in spec['home_results'])
    assert any('team score first' in t for t in texts)
    assert not any('Source:' in t or 'Checked' in t or 'assessed' in t.lower() for t in texts)


@pytest.mark.parametrize('bad',['count','score','opponent','venue','duplicate','future','order'])
def test_recent_card_fails_closed_on_unverified_or_misordered_results(cfg,tmp_path,bad):
    post,_=e.build(cfg,{},NOW,Fake());spec=deepcopy(post['graphics'][1]);rows=spec['home_results']
    if bad=='count':rows.pop()
    if bad=='score':rows[0]['gf']=None
    if bad=='opponent':rows[0]['opponent']=''
    if bad=='venue':rows[0]['venue']='?'
    if bad=='duplicate':rows[1]['id']=rows[0]['id']
    if bad=='future':rows[0]['date']=spec['kickoff']
    if bad=='order':rows.reverse()
    with pytest.raises(ValueError):render(spec,tmp_path/'bad.jpg')


def test_watchdog_timetable_migration_preserves_history_quota_unknowns_and_old_evidence(cfg):
    s={'posts':[{'kind':'editorial','status':'unknown','at':NOW.isoformat(),'key':'old','slot_key':'old'}],
       'highlightly_api':{'requests':55},'editorial_delivery':{'version':1,'since':NOW.isoformat(),'slots':{'old':{'start':NOW.isoformat(),'attempts':2,'status':'verifying'}}}}
    w.book(s,NOW,e.schedule(cfg))
    assert s['highlightly_api']['requests']==55 and s['posts'][0]['status']=='unknown'
    assert s['editorial_delivery']['slots']['old']['attempts']==2
    assert w.current_slot(s,NOW)[0].endswith(':match03')
    assert not w.assess(s,NOW,'new')[0]


def env(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock);monkeypatch.setattr(photo_package,'datetime',Clock)
    for key,value in {'GITHUB_REF_NAME':'main','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_REPOSITORY':'owner/repo','FACEBOOK_FEED_PUBLISH':'true','GH_READ_TOKEN':'synthetic'}.items():monkeypatch.setenv(key,value)


def prepare(cfg,tmp_path,monkeypatch):
    env(monkeypatch)
    s={'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[]}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(s))
    from facebook_feed import match_packages
    real=match_packages.build
    monkeypatch.setattr(match_packages,'build',lambda cfg,state,now,api=None:real(cfg,state,now,Fake()))
    storage.write(tmp_path/'config.json',cfg)
    common=['--kind','editorial','--publish','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)]
    assert cli.main(['prepare',*common])==0
    return common


def test_prepare_binds_both_pictures_to_one_reservation(cfg,tmp_path,monkeypatch):
    prepare(cfg,tmp_path,monkeypatch)
    post=json.loads((tmp_path/'plans.json').read_text())[0]
    s=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert len(s['posts'])==1 and len(post['images'])==2
    assert s['posts'][0]['image_sha256s']==post['image_sha256s']
    assert [hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in post['images']]==post['image_sha256s']


@pytest.mark.parametrize('tamper',['remove','swap','bytes','media_checkpoint'])
def test_single_picture_fallback_or_tampering_never_contacts_page(cfg,tmp_path,monkeypatch,tamper):
    common=prepare(cfg,tmp_path,monkeypatch)
    post=json.loads((tmp_path/'plans.json').read_text())[0]
    if tamper=='remove':del post['images']
    if tamper=='swap':post['images'].reverse()
    if tamper=='bytes':Path(post['images'][1]).write_bytes(b'changed')
    storage.write(tmp_path/'plans.json',[post])
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Page contact'))
    with pytest.raises(ValueError):cli.main(['send',*common,'--checkpoint'])


def test_two_unpublished_uploads_then_durable_media_gate_then_one_feed_creation(cfg,tmp_path,monkeypatch):
    common=prepare(cfg,tmp_path,monkeypatch);calls=[]
    class Page:
        def stage_package(self,images,checkpoint):
            calls.append('stage');checkpoint(['41']);checkpoint(['41','42']);return ['41','42']
        def send_package(self,post,ids):calls.append(('feed',ids));return '123_99'
        def verify_package_hash(self,identity,hash,ids):calls.append(('verify',ids));return True
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(['stage',*common,'--checkpoint'])==0
    s=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert s['posts'][0]['media_phase']=='staged' and s['posts'][0]['media_ids']==['41','42']
    with pytest.raises(ValueError):cli.main(['send',*common,'--checkpoint'])
    assert calls==['stage']
    assert cli.main(['send',*common,'--checkpoint','--media-checkpoint'])==0
    assert calls==['stage',('feed',['41','42']),('verify',['41','42'])]
    assert json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]['status']=='published'
    with pytest.raises(ValueError):cli.main(['send',*common,'--checkpoint','--media-checkpoint'])
    assert len(calls)==3


@pytest.mark.parametrize('failure',['first_photo','second_photo','feed','verify'])
def test_partial_or_ambiguous_package_never_reuploads(cfg,tmp_path,monkeypatch,failure):
    common=prepare(cfg,tmp_path,monkeypatch);calls=[]
    class Page:
        def stage_package(self,images,checkpoint):
            calls.append('upload1')
            if failure=='first_photo':raise PublishError('uncertain')
            checkpoint(['41']);calls.append('upload2')
            if failure=='second_photo':raise PublishError('uncertain')
            checkpoint(['41','42']);return ['41','42']
        def send_package(self,post,ids):
            calls.append('feed')
            if failure=='feed':raise PublishError('uncertain')
            return '123_99'
        def verify_package_hash(self,*args):raise PublishError('both photos not yet verified')
    monkeypatch.setattr(cli,'PageFeed',Page)
    result=cli.main(['stage',*common,'--checkpoint'])
    if failure in ('feed','verify'):
        assert result==0
        assert cli.main(['send',*common,'--checkpoint','--media-checkpoint'])==1
    else:assert result==1
    before=list(calls)
    with pytest.raises(ValueError):cli.main(['stage',*common,'--checkpoint'])
    assert calls==before
    assert json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]['status']==('cancelled' if failure in ('first_photo','second_photo') else 'unknown')


def page_with_call(fn):
    p=PageFeed.__new__(PageFeed);p.page='123';p.call=fn
    return p


def test_actual_multi_photo_protocol_is_unpublished_then_attached_in_order(tmp_path):
    paths=[]
    for n in range(2):p=tmp_path/f'{n}.jpg';p.write_bytes(b'image'+bytes([n]));paths.append(str(p))
    calls=[];answers=iter([{'id':'41'},{'id':'42'},{'id':'123_99'}])
    def call(*a,**kw):calls.append((a,kw));return next(answers)
    p=page_with_call(call);saved=[]
    ids=p.stage_package(paths,lambda values:saved.append(values))
    assert saved==[['41'],['41','42']]
    assert p.send_package({'caption':'Caption'},ids)=='123_99'
    assert [c[0][:2] for c in calls]==[('POST','123/photos'),('POST','123/photos'),('POST','123/feed')]
    assert all(b'\r\nfalse\r\n' in c[1]['body'] and b'\r\ntrue\r\n' not in c[1]['body'] for c in calls[:2])
    assert json.loads(calls[2][0][2]['attached_media'])==[{'media_fbid':'41'},{'media_fbid':'42'}]


@pytest.mark.parametrize('shape',['album','flat'])
def test_verify_both_attachment_shapes_not_just_caption(shape):
    photos=[{'target':{'id':'41'}},{'target':{'id':'42'}}]
    data={'id':'123_99','message':'Caption','is_published':True,'attachments':{'data':photos if shape=='flat' else [{'subattachments':{'data':photos}}]}}
    p=page_with_call(lambda *a,**kw:data)
    assert p.verify_package_hash('123_99',hashlib.sha256(b'Caption').hexdigest(),['41','42'])
    photos.pop()
    with pytest.raises(PublishError):p.verify_package_hash('123_99',hashlib.sha256(b'Caption').hexdigest(),['41','42'])


@pytest.mark.parametrize('bad',['wrong_caption','not_published','wrong_order','missing','partial','wrong_id'])
def test_incomplete_or_changed_readback_does_not_claim_success(bad):
    data={'id':'123_99','message':'Caption','is_published':True,'attachments':{'data':[{'target':{'id':'41'}},{'target':{'id':'42'}}]}}
    if bad=='wrong_caption':data['message']='Other'
    if bad=='not_published':data['is_published']=False
    if bad=='wrong_order':data['attachments']['data'].reverse()
    if bad=='missing':del data['attachments']
    if bad=='partial':data['attachments']['paging']={'next':'not-followed'}
    if bad=='wrong_id':data['id']='123_100'
    with pytest.raises(PublishError):page_with_call(lambda *a,**k:data).verify_package_hash('123_99',hashlib.sha256(b'Caption').hexdigest(),['41','42'])


def test_watchdog_requires_media_readback_for_unknown_package():
    s={'posts':[{'kind':'editorial','status':'unknown','post_id':'123_99','caption_hash':'hash','image_sha256s':['a','b'],'media_ids':['41','42']}]};calls=[]
    class P:
        def verify_package_hash(self,*a):calls.append(a)
        def verify_hash(self,*a):pytest.fail('Caption-only confirmation forbidden')
    w.reconcile_known(s,NOW,P)
    assert calls==[('123_99','hash',['41','42'])] and s['posts'][0]['status']=='published'


def test_workflow_durable_media_upload_precedes_feed_creation():
    doc=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    steps=doc['jobs']['feed']['steps'];ids=[s.get('id') for s in steps]
    assert ids.index('reserve')<ids.index('stage_media')<ids.index('media_checkpoint')<ids.index('send')
    send=next(s for s in steps if s.get('id')=='send')
    assert "steps.media_checkpoint.conclusion == 'success'" in send['if']
    assert '--media-checkpoint' in send['run']


def test_combined_730_fixtures_are_preserved_and_first_match_respects_spacing(cfg):
    at=NOW.replace(hour=7,minute=30);api=Fake(at);s={}
    post,reason=e.build(cfg,s,at,api);assert post,reason
    assert not post.get('graphics') and post['topic'].startswith('fixtures:')
    policy.reserve(post,s,at)['status']='published'
    w.book(s,at,e.schedule(cfg))
    assert not w.assess(s,at.replace(hour=8,minute=0),'early')[0]
    assert w.assess(s,at.replace(hour=8,minute=33),'ready')[0]
    assert w.current_slot(s,at.replace(hour=8,minute=0))[0].endswith(':match01')


def test_handled_unpublished_staging_failure_is_bounded_retry_not_public_resend(cfg,tmp_path,monkeypatch):
    common=prepare(cfg,tmp_path,monkeypatch)
    class Page:
        def stage_package(self,images,checkpoint):checkpoint(['41']);raise PublishError('staging network failure')
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(['stage',*common,'--checkpoint'])==1
    s=json.loads((tmp_path/'checkpoint/state.json').read_text())
    entry=s['posts'][0]
    assert entry['status']=='cancelled' and entry['media_ids']==['41']
    assert entry['delivery_failure']=='unpublished_staging_incomplete'
    w.book(s,NOW,e.schedule(cfg))
    key=w.current_slot(s,NOW)[0]
    w.sync(s,NOW)['slots'][key].update(status='reserved',attempts=1)
    report=w.audit(s,NOW,False)
    assert s['editorial_delivery']['slots'][key]['status']=='waiting' and not report['incidents']


def test_schedule_migration_positive_reconciliation_clears_old_incident(cfg):
    old=f'editorial:{NOW.date()}:psl'
    s={'posts':[{'kind':'editorial','slot_key':old,'status':'published'}],
       'editorial_delivery':{'version':1,'since':NOW.isoformat(),'slots':{old:{'start':NOW.isoformat(),'status':'needs_attention','attempts':2,'diagnosis':'ambiguous_publication_no_resend'}}}}
    w.book(s,NOW,e.schedule(cfg));w.sync(s,NOW)
    assert s['editorial_delivery']['slots'][old]['status']=='delivered'
