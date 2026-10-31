"""Offline synthetic editorial tests; no real fixtures, key access or Graph calls."""
from copy import deepcopy
from datetime import timedelta,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs,urlparse
import pytest
import yaml
from PIL import Image
from facebook_feed import cli,content,editorial as e,graphics,policy,storage
from facebook_feed.provider import ProviderError
from test_event_monitor import NOW as OLD_NOW,Opener
from test_highlightly import Response,envelope

ROOT=Path(__file__).resolve().parents[1]
NOW=OLD_NOW.replace(hour=10,minute=0)

@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def raw(mid=1,league='psl',when=None,home=10,away=20,score=None,status='Not started'):
    label,country,aliases=e.LEAGUES[league]
    return {'id':mid,'date':(when or NOW+timedelta(hours=10)).isoformat(),
            'league':{'id':100+list(e.LEAGUES).index(league),'name':aliases[0],'season':2026},
            'country':{'name':country},'homeTeam':{'id':home,'name':f'Example Club {home}'},
            'awayTeam':{'id':away,'name':f'Example Club {away}'},
            'state':{'description':status,'score':{'current':score}},'events':[]}


def history(league='psl'):
    rows=[]
    for index in range(5):
        for team in (10,20):
            rows.append(raw(list(e.LEAGUES).index(league)*10000+1000+index*100+team,league,NOW-timedelta(days=7+index*7),team,100+index+team,'2 - 0','Finished'))
    return rows


class Fake:
    def __init__(self,now=NOW,today=None,previous=None):
        self.at=now.isoformat();self.now=now;self.calls=[]
        self.today=[raw()] if today is None else today
        self.previous=[raw(88,when=now-timedelta(days=1),score='1 - 0',status='Finished')] if previous is None else previous
        self.hist={key:history(key) for key in e.LEAGUES}
        self.details={m['id']:deepcopy(m) for m in self.today+self.previous+sum(self.hist.values(),[])}
        self.second_changes=None
    def catalog(self,params):
        self.calls.append(('catalog',params))
        if 'date' in params:return deepcopy(self.today if params['date']==self.now.date().isoformat() else self.previous)
        key=list(e.LEAGUES)[params['leagueId']-100]
        rows=deepcopy(self.hist[key])
        if self.second_changes and sum(c[0]=='catalog' and 'leagueId' in c[1] for c in self.calls)%2==0:
            self.second_changes(rows)
        return rows
    def raw_detail(self,mid):
        self.calls.append(('detail',mid))
        result=self.details[mid]
        if isinstance(result,Exception):raise result
        return deepcopy(result)


@pytest.mark.parametrize('clock,slot',e.SLOTS)
def test_all_ten_exact_sast_slots(clock,slot):
    at=NOW.replace(hour=int(clock[:2]),minute=int(clock[3:]))
    assert e.due(at)==slot and e.due(at+timedelta(minutes=44))==slot
    assert e.due(at+timedelta(minutes=45)) is None
    assert e.due(at.astimezone(timezone.utc))==slot


def test_live_paused_no_provider_access_and_editorial_730_is_not_live_window(cfg,monkeypatch):
    assert not cfg['live']['enabled'] and not cfg['event_monitor']['enabled'] and not cfg['event_monitor']['publish_enabled']
    assert cfg['authorized_kinds']==['editorial']
    for hour in (0,8,12,23):assert not cli.is_due('live',NOW.replace(hour=hour),cfg)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Page access'))
    assert cli.build('live',ROOT,NOW,cfg,{},preview=True)[0] is None
    assert cli.is_due('editorial',NOW.replace(hour=7,minute=30),cfg)
    assert all(not x['authorised'] for x in cfg['event_monitor']['key_slots'].values())


def test_workflow_schedule_is_ten_not_live_and_uses_same_checkpoint_mutex():
    load=lambda p:yaml.safe_load((ROOT/p).read_text())
    wf=load('.github/workflows/facebook-editorial.yml');on=wf.get('on',wf.get(True))
    assert [x['cron'] for x in on['schedule']]==['30 5,6,17 * * *','0 8-13,21 * * *']
    assert wf['jobs']['content']['with']=={'kind':'editorial','publish':"${{ github.event_name == 'schedule' || inputs.publish }}",'preview':False,'bootstrap':False}
    live=load('.github/workflows/facebook-live.yml');assert 'schedule' not in live.get('on',live.get(True))
    assert 'inputs.diagnostic' in live['jobs']['content']['if']
    engine=(ROOT/'.github/workflows/facebook-feed-run.yml').read_text()
    assert 'group: facebook-feed-' in engine and 'checkpoint/state.json' in engine
    assert "inputs.kind == 'editorial'" in engine and "inputs.kind != 'editorial'" in engine


def test_pre_match_comparison_crosschecks_last_five_and_captions_unbranded(cfg):
    api=Fake();post,reason=e.build(cfg,{},NOW,api)
    assert post and len(post['graphic']['rows'])==6 and len(post['snapshot'][0]['home_sample']['matches'])==5
    assert len([c for c in api.calls if c[0]=='catalog' and 'leagueId' in c[1]])==2
    assert len([c for c in api.calls if c[0]=='detail'])==3 # Upcoming fixture + newest result of each team.
    assert post['caption'].count('• ')==3 and 'Your pick:' in post['caption']
    assert '#PSL' in post['caption'] and '#ExampleClub10' in post['caption']
    assert 'PLAYREPORT' not in post['caption'].upper() and 'MR 2 ODDS' not in post['caption'].upper()
    assert 'same provider' in post['caption'] and 'last five' in post['caption']
    assert all('RATING' not in r[0] and 'BIG CHANCES' not in r[0] for r in post['graphic']['rows'])
    assert post['graphic']['rows'][0][1:]==(10,10) and post['graphic']['rows'][4][1:]==(5,5)


@pytest.mark.parametrize('change',['score','name','id','league','kickoff','state'])
def test_upcoming_detail_conflict_blocks_card(cfg,change):
    api=Fake();m=api.details[1]
    if change=='score':m['state']['score']['current']='3 - 0'
    elif change=='name':m['homeTeam']['name']='Different Club'
    elif change=='id':m['id']=2
    elif change=='league':m['country']['name']='Brazil'
    elif change=='kickoff':m['date']=(NOW+timedelta(days=1)).isoformat()
    else:m['state']['description']='Postponed'
    assert e.build(cfg,{},NOW,api)[0] is None


@pytest.mark.parametrize('change',['missing','different_score','newest_detail','wrong_season','future','stale'])
def test_unsafe_history_cannot_generate_photo(cfg,change):
    api=Fake()
    if change=='missing':api.hist['psl']=api.hist['psl'][:4]
    if change=='different_score':api.second_changes=lambda rows:rows[0]['state']['score'].update(current='9 - 0')
    if change=='newest_detail':api.details[1010]['state']['score']['current']='1 - 0'
    if change=='wrong_season':api.hist['psl'][0]['league']['season']=2025
    if change=='future':api.hist['psl'][0]['date']=(NOW+timedelta(days=1)).isoformat()
    if change=='stale':api.hist['psl'][0]['date']=(NOW-timedelta(days=181)).isoformat()
    post,_=e.build(cfg,{},NOW,api)
    assert post is None


@pytest.mark.parametrize('field,value',[('id',True),('date','2026-10-31T10:00:00'),('date','not a date')])
def test_invalid_identity_or_naive_dates_fail_closed(field,value):
    r=raw();r[field]=value
    with pytest.raises(ProviderError):e.fixture(r)


def test_no_fixture_or_insufficient_season_does_not_reuse_old_watchlist_or_invent(cfg):
    state={'posts':[{'status':'unknown','key':'old'}],'highlightly_watchlist':{'sentinel':True}}
    api=Fake(today=[]);assert e.build(cfg,state,NOW,api)[0] is None
    assert state['posts']==[{'status':'unknown','key':'old'}] and state['highlightly_watchlist']=={'sentinel':True}
    api=Fake();api.today[0]['league'].pop('season');api.details[1]=api.today[0]
    assert e.build(cfg,{},NOW,api)[0] is None


def test_combined_fixtures_at_730_contains_all_league_sections_and_no_fake_zeroes(cfg):
    at=NOW.replace(hour=7,minute=30);api=Fake(at)
    post,_=e.build(cfg,{},at,api)
    assert post and len([c for c in api.calls if c[0]=='catalog'])==1
    for label,_,_ in e.LEAGUES.values():assert label in post['caption']
    assert '0–0' not in post['caption'] and '#FootballFixtures' in post['caption']
    assert post['slot_key'].endswith(':fixtures')


def test_results_accept_only_explicit_finals_not_missing_or_active(cfg):
    at=NOW.replace(hour=8,minute=30);api=Fake(at)
    api.previous+=[raw(99,when=at-timedelta(days=1),score='3 - 0',status='Second half')]
    post,_=e.build(cfg,{},at,api)
    assert post and post['fixture_ids']==[88] and '1–0' in post['caption']
    assert '#FootballResults' in post['caption'] and '3–0' not in post['caption']


def test_evening_filters_already_bulletined_results_and_partial_scans_do_not_replace_cache(cfg):
    at=NOW.replace(hour=23);m=raw(33,when=at-timedelta(hours=3),score='2 - 1',status='Finished')
    api=Fake(at,today=[m]);state={'posts':[{'kind':'editorial','topic':'results:earlier','status':'published','fixture_ids':[33]}]}
    assert e.build(cfg,state,at,api)[0] is None
    book=e.cache({},at);book['fixtures']['2026-10-30']={'at':at.isoformat(),'rows':[]}
    api.catalog=lambda p: (_ for _ in ()).throw(ProviderError('Synthetic failure'))
    before=deepcopy(book)
    with pytest.raises(ProviderError):e.day_rows(api,book,at.date(),at,refresh=True)
    assert book==before


def test_daily_cache_rollover_preserves_all_post_and_unknown_history():
    state={'posts':[{'status':'unknown'}],'highlightly_api':{'requests':99}}
    old=e.cache(state,NOW);old['histories']['x']='old'
    e.cache(state,NOW+timedelta(days=1))
    assert state['posts']==[{'status':'unknown'}] and state['highlightly_api']=={'requests':99}
    assert state['football_editorial']['histories']=={}


def test_daily_slot_once_and_policy_does_not_weaken_unknown_guards(cfg):
    post,_=e.build(cfg,{},NOW,Fake());state={'posts':[]}
    assert policy.allowed(post,state,NOW,cfg)[0]
    entry=policy.reserve(post,state,NOW);assert entry['slot_key']==post['slot_key']
    assert not policy.allowed(dict(post,key='other',topic='other'),state,NOW+timedelta(hours=1),cfg)[0]
    entry['status']='published'
    assert e.build(cfg,state,NOW,Fake())[0] is None
    state={'posts':[{'status':'unknown','kind':'live','key':'old','at':NOW.isoformat()}]}
    assert not policy.allowed(post,state,NOW,cfg)[0]


def test_hourly_policy_overrides_old_two_post_cap_and_quiet_windows_only_for_editorial(cfg):
    state={'posts':[]}
    for index in range(10):
        at=NOW+timedelta(hours=index)
        post=content.candidate('editorial',f'k{index}',f't{index}','different caption '+str(index),slot_key=f's{index}')
        assert policy.allowed(post,state,at,cfg)[0]
        policy.reserve(post,state,at)['status']='published'
    last=content.candidate('editorial','other','other','other',slot_key='other')
    assert not policy.allowed(last,state,at+timedelta(hours=1),cfg)[0]
    assert cfg['max_ordinary_posts_per_day']==2 and cfg['min_feed_interval_minutes']==120


@pytest.mark.parametrize('remaining',[1,50])
def test_shared_transport_100th_request_is_valid_no_101st(cfg,monkeypatch,remaining):
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-editorial')
    state={'highlightly_api':{'utc_date':NOW.astimezone(timezone.utc).date().isoformat(),'requests':100-remaining,'remaining':remaining}}
    opener=Opener(Response(envelope([raw()]),remaining-1,stamp=NOW))
    api=e.Source(cfg,state,NOW,opener)
    assert api.catalog({'date':NOW.date().isoformat()})[0]['id']==1
    if remaining==1:
        with pytest.raises(ProviderError):api.raw_detail(1)
        assert len(opener.calls)==1 and state['highlightly_api']['requests']==100
    q=parse_qs(urlparse(opener.calls[0].full_url).query)
    assert q['timezone']==['Africa/Johannesburg'] and q['limit']==['100']


@pytest.mark.parametrize('defect',['duplicate','partial','paid','huge','wrong_offset'])
def test_catalog_transport_rejects_invalid_pages(cfg,monkeypatch,defect):
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-editorial')
    body=envelope([raw()])
    if defect=='duplicate':body=envelope([raw(),raw()])
    if defect=='partial':body['pagination']['totalCount']=3
    if defect=='paid':body['plan']['tier']='PRO'
    if defect=='huge':body['pagination']['totalCount']=1001
    if defect=='wrong_offset':body['pagination']['offset']=100
    api=e.Source(cfg,{},NOW,Opener(Response(body,stamp=NOW)))
    with pytest.raises(ProviderError):api.catalog({'date':NOW.date().isoformat()})


def test_reference_inspired_card_renders_readably_without_crests_or_trends(cfg,tmp_path):
    post,_=e.build(cfg,{},NOW,Fake());path=graphics.render(post['graphic'],tmp_path/'comparison.jpg')
    assert Image.open(path).size==(1080,1350) and path.stat().st_size>40000
    assert 'trends' not in post['graphic'] and 'question' not in post['graphic']
    post['graphic']['home']='X'*600
    with pytest.raises(ValueError):graphics.render(post['graphic'],path)


def test_goal_story_is_distinct_dated_and_withholds_unreconciled_event_counts(cfg):
    at=NOW.replace(hour=19,minute=30);api=Fake(at)
    m=api.details[88];m['events']=[{'type':'Goal','time':'44','team':{'id':10}}]
    post,_=e.build(cfg,{},at,api)
    assert post and '44' in post['caption'] and post['caption'].count('• ')==1
    assert at.date().isoformat() not in post['caption'] # Match is explicitly yesterday, not today's match.
    api.details[88]['events']=[]
    assert e.build(cfg,{},at,api)[0] is None


@pytest.mark.parametrize('gate',['rights_confirmed','account_coverage_verified','verification_only'])
def test_approval_gates_block_all_api_calls(cfg,gate):
    cfg['highlightly'][gate]=gate=='verification_only'
    class NoAPI:
        def __getattr__(self,key):pytest.fail('No API access when source blocked')
    assert e.build(cfg,{},NOW,NoAPI())[0] is None


def test_full_ten_slot_day_reuses_shared_transport_and_durable_policy(cfg,monkeypatch):
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-editorial')
    today=[raw(index+1,key) for index,key in enumerate(e.LEAGUES)]
    previous=raw(88,when=NOW-timedelta(days=1),score='1 - 0',status='Finished')
    previous['events']=[{'type':'Goal','time':'44','team':{'id':10}}]
    histories={100+index:history(key) for index,key in enumerate(e.LEAGUES)}
    all_details={m['id']:m for m in today+[previous]+sum(histories.values(),[])}
    class Transport:
        def __init__(self):self.calls=[];self.now=NOW
        def open(self,request,timeout):
            self.calls.append(request);q=parse_qs(urlparse(request.full_url).query)
            if '/matches/' in request.full_url:value=[all_details[int(request.full_url.rsplit('/',1)[1])]]
            elif 'leagueId' in q:value=envelope(histories[int(q['leagueId'][0])])
            elif q['date'][0]==self.now.date().isoformat():
                rows=deepcopy(today)
                if self.now.hour==23:
                    for row in rows:row['state']={'description':'Finished','score':{'current':'2 - 1'}}
                value=envelope(rows)
            else:value=envelope([previous])
            return Response(value,100-len(self.calls),stamp=self.now)
    transport=Transport();state={'posts':[]};posts=[]
    for clock,slot in e.SLOTS:
        at=NOW.replace(hour=int(clock[:2]),minute=int(clock[3:]));transport.now=at
        api=e.Source(cfg,state,at,transport)
        post,reason=e.build(cfg,state,at,api)
        assert post, (slot,reason)
        assert policy.allowed(post,state,at,cfg)[0]
        policy.reserve(post,state,at)['status']='published';posts.append(post)
    assert len(posts)==10 and len([p for p in posts if p.get('graphic')])==6
    assert state['highlightly_api']['requests']==34 and len(transport.calls)==34
    assert all('PLAYREPORT' not in p['caption'].upper() and '#' in p['caption'] for p in posts)
    assert len({p['slot_key'] for p in posts})==10


def test_cli_prepares_graphic_hashes_reservation_and_preserves_production_namespace(cfg,tmp_path,monkeypatch):
    from datetime import datetime
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setenv('GH_READ_TOKEN','synthetic-read');monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo')
    state={'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[],'event_api':{'sentinel':True}}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(state))
    real=e.build
    monkeypatch.setattr(e,'build',lambda cfg,state,now:real(cfg,state,now,Fake()))
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('Prepare must not access Page'))
    storage.write(tmp_path/'config.json',cfg)
    assert cli.main(['prepare','--kind','editorial','--publish','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    stored=json.loads((tmp_path/'checkpoint/state.json').read_text());plan=json.loads((tmp_path/'plans.json').read_text())[0]
    assert stored['namespace']==state['namespace'] and stored['event_api']==state['event_api']
    entry=stored['posts'][0]
    assert entry['status']=='reserved' and entry['slot_key']==plan['slot_key']
    assert entry['image_sha256']==hashlib.sha256(Path(plan['image']).read_bytes()).hexdigest()
    assert 'PLAYREPORT' not in (tmp_path/'editorial.txt').read_text().upper()


def test_tampered_editorial_picture_is_blocked_before_page_access(cfg,tmp_path,monkeypatch):
    from datetime import datetime
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock);monkeypatch.setenv('GITHUB_REF_NAME','main')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Page access after image tampering'))
    post,_=e.build(cfg,{},NOW,Fake());post['expires_at']=(NOW+timedelta(minutes=3)).isoformat()
    post['image']=str(tmp_path/'photo.jpg');Path(post['image']).write_bytes(b'original')
    post['image_sha256']=hashlib.sha256(b'original').hexdigest()
    state={'posts':[]};entry=policy.reserve(post,state,NOW)
    entry['run_key']='local-1'
    storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post]);storage.write(tmp_path/'config.json',cfg)
    Path(post['image']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='picture'):
        cli.main(['send','--kind','editorial','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])


def test_no_api_spend_while_unknown_send_is_unresolved(cfg):
    class NoAPI:
        def __getattr__(self,name):pytest.fail('No API access until unknown send resolved')
    assert e.build(cfg,{'posts':[{'status':'unknown'}]},NOW,NoAPI())[0] is None


def test_missing_final_is_omitted_from_bulletin_not_zero_or_replaced_with_older_sample(cfg):
    at=NOW.replace(hour=8,minute=30);api=Fake(at)
    api.previous.append(raw(99,when=at-timedelta(days=1),status='Finished',score=None))
    post,_=e.build(cfg,{},at,api)
    assert post['fixture_ids']==[88] and '0–0' not in post['caption']
    api=Fake();api.hist['psl'][0]['state']['score']['current']=None
    assert e.build(cfg,{},NOW,api)[0] is None


def test_source_change_and_editorial_disable_make_no_requests(cfg):
    class NoAPI:
        def __getattr__(self,name):pytest.fail('No API request')
    cfg['score_source']='api-football'
    assert e.build(cfg,{},NOW,NoAPI())[0] is None
    cfg['score_source']='highlightly';cfg['editorial']['enabled']=False
    assert e.build(cfg,{},NOW,NoAPI())[0] is None
