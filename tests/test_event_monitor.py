"""Offline synthetic replay only. No API/Graph calls, real clubs, or real Page posts."""
from copy import deepcopy
from datetime import datetime,timedelta
from email.utils import format_datetime
import io
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
import pytest
from facebook_feed import cli,content,event_monitor,match_events,policy,storage,graphics
from facebook_feed.event_provider import EventAPI,QuotaExceeded,daily_quota
from facebook_feed.provider import ProviderError
from facebook_feed.publisher import PublishError

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,30,20,0,tzinfo=content.SAST)

@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def raw(fid=1,score=(0,0),minute=50,status='2H',events=None):
    return {'fixture':{'id':fid,'date':(NOW-timedelta(minutes=65)).isoformat(),'status':{'short':status,'elapsed':minute}},
            'teams':{'home':{'id':fid*10,'name':f'Synthetic Home {fid}'},'away':{'id':fid*10+1,'name':f'Synthetic Away {fid}'}},
            'league':{'id':900,'name':'Synthetic League','country':'Test'},'goals':dict(zip(('home','away'),score)),
            'events':events or []}


def event(fid=1,kind='Goal',detail='Normal Goal',minute=54,player='Synthetic Scorer',pid=33):
    return {'type':kind,'detail':detail,'time':{'elapsed':minute,'extra':None},'team':{'id':fid*10},'player':{'id':pid,'name':player}}


def observation(state,rows,now=NOW):
    normalized=[match_events.normalise_observation(row,now) for row in rows]
    assert all(normalized),'invalid synthetic fixture'
    return match_events.observe(state,normalized,now.isoformat(),now)


class Replay:
    def __init__(self,now,responses):self.at=now.isoformat();self.responses=list(responses);self.calls=[]
    def get(self,endpoint,params=None):
        self.calls.append((endpoint,params))
        result=self.responses.pop(0)
        if isinstance(result,Exception):raise result
        return result


def baseline(cfg,rows=None):
    state={'posts':[]}
    rows=rows or [raw()]
    api=Replay(NOW,[rows,rows])
    post,_=event_monitor.build(cfg,state,NOW,api)
    assert post is None
    return state


def test_production_is_event_driven_and_activated(cfg):
    assert cfg['event_monitor']['enabled'] and cfg['event_monitor']['publish_enabled']
    assert cfg['live']['image_required'] and cfg['event_monitor']['failover_permitted']
    assert cfg['event_monitor']['permission_reference']
    assert {v['quota_group'] for v in cfg['event_monitor']['key_slots'].values()}=={'primary','backup-1','backup-2'}
    assert cli.is_due('live',NOW.replace(hour=2),cfg)


def test_baseline_and_minute_ticks_never_post(cfg):
    state=baseline(cfg)
    now=NOW+timedelta(minutes=5)
    post,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(minute=55)]]))
    assert post is None and not state['live_event_ledger']['events']


def test_existing_goals_and_red_cards_are_baseline_not_backfill(cfg):
    state=baseline(cfg,[raw(score=(2,1),events=[event(minute=30),event(kind='Card',detail='Red Card',minute=40)])])
    assert not state['live_event_ledger']['events']


def test_goal_multiple_matches_and_unchanged_filler_excluded(cfg,tmp_path):
    state=baseline(cfg,[raw(1),raw(2),raw(3)])
    now=NOW+timedelta(minutes=5)
    post,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(1,(1,0),55,events=[event()]),raw(2,(0,1),55),raw(3,minute=55)]]))
    assert len(post['event_ids'])==2 and len(post['snapshot'])==2
    assert 'Synthetic Home 3' not in post['caption'] and 'Synthetic Scorer' in post['caption']
    assert post['caption'].startswith('PLAYREPORT ZA | LIVE SCORES\n\nLIVE MATCH UPDATES')
    assert post['caption'].count('Synthetic League')==1
    assert '#PlayReportZA #LiveScores' in post['caption']
    assert '54\' | Goal — Synthetic Scorer' in post['caption']
    assert post['graphic']['match'] in post['snapshot']
    assert graphics.render(post['graphic'],tmp_path/'preview.jpg').is_file()


@pytest.mark.parametrize('status,minute,label',[('HT',45,'Half-time'),('FT',90,'Full-time'),('PST',None,'Postponed'),('CANC',None,'Cancelled'),('ABD',None,'Abandoned'),('SUSP',55,'Suspended')])
def test_status_changes_once(cfg,status,minute,label):
    state={'posts':[]}
    observation(state,[raw(minute=40,status='1H')])
    now=NOW+timedelta(minutes=40 if status=='FT' else 5)
    after=raw(status=status,minute=minute,score=(None,None) if status in ('PST','CANC','ABD') else (0,0))
    observation(state,[after],now)
    events=list(state['live_event_ledger']['events'].values())
    assert any(e['change'].get('status')==status for e in events)
    before=len(events);observation(state,[after],now+timedelta(minutes=5))
    assert len(state['live_event_ledger']['events'])==before
    assert label in event_monitor.caption([state['live_event_ledger']['matches']['1']['snapshot']],events,now.isoformat())


def test_red_verified_duplicate_and_yellow_not_alerts(cfg):
    state=baseline(cfg);now=NOW+timedelta(minutes=5)
    red=event(kind='Card',detail='Red Card')
    yellow=event(kind='Card',detail='Yellow Card')
    observation(state,[raw(minute=55,events=[red,deepcopy(red),yellow])],now)
    assert len(state['live_event_ledger']['events'])==1
    observation(state,[raw(minute=60,events=[red])],now+timedelta(minutes=5))
    assert len(state['live_event_ledger']['events'])==1


def test_missed_penalty_and_late_old_scorer_not_invented():
    state={'posts':[]};observation(state,[raw(score=(1,0))])
    observation(state,[raw(score=(2,0),minute=55,events=[event(minute=20),event(detail='Missed Penalty')])],NOW+timedelta(minutes=5))
    change=next(iter(state['live_event_ledger']['events'].values()))['change']
    assert change['kind']=='score_update' and change['scorers']==[]


def test_restart_retains_pending_and_event_identity(cfg,tmp_path):
    state=baseline(cfg);now=NOW+timedelta(minutes=5)
    p,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(score=(1,0),minute=55)]]))
    storage.write(tmp_path/'state.json',state)
    restarted=content.load(tmp_path/'state.json')
    later=now+timedelta(minutes=5)
    retry,_=event_monitor.build(cfg,restarted,later,Replay(later,[[raw(score=(1,0),minute=60)]]))
    assert retry['event_ids']==p['event_ids'] and retry['key']==p['key']
    match_events.publication_state(restarted,retry,'published',later)
    later+=timedelta(minutes=5)
    assert event_monitor.build(cfg,restarted,later,Replay(later,[[raw(score=(1,0),minute=65)]]))[0] is None


def test_disappearance_requires_targeted_confirmation_then_no_historical_refetch(cfg):
    state=baseline(cfg);now=NOW+timedelta(minutes=40)
    api=Replay(now,[[],[raw(status='FT',minute=90)]])
    p,_=event_monitor.build(cfg,state,now,api)
    assert any(e['change'].get('status')=='FT' for e in state['live_event_ledger']['events'].values())
    assert api.calls[1][1]['ids']=='1'
    match_events.publication_state(state,p,'published',now)
    later=now+timedelta(minutes=5);api=Replay(later,[])
    assert event_monitor.build(cfg,state,later,api)[0] is None and api.calls==[]


def test_missing_details_not_inferred_fulltime(cfg):
    state=baseline(cfg);now=NOW+timedelta(minutes=5)
    assert event_monitor.build(cfg,state,now,Replay(now,[[],ProviderError('unavailable')]))[0] is None
    assert state['live_event_ledger']['matches']['1']['snapshot']['status']=='2H'
    assert not state['live_event_ledger']['events']


def test_terminal_refresh_batches_twenty_and_rotates(cfg):
    state=baseline(cfg,[raw(fid=i) for i in range(1,26)])
    now=NOW+timedelta(minutes=5);api=Replay(now,[[],[]]);event_monitor.build(cfg,state,now,api)
    assert len(api.calls[1][1]['ids'].split('-'))==20
    later=now+timedelta(minutes=5);api=Replay(later,[[],[]]);event_monitor.build(cfg,state,later,api)
    assert len(api.calls[1][1]['ids'].split('-'))==5


def test_empty_calendar_still_global_discovery_and_backoff(cfg):
    state={'posts':[]};api=Replay(NOW,[[],[]]);assert event_monitor.build(cfg,state,NOW,api)[0] is None
    assert api.calls[1][1]['live']=='all'
    later=NOW+timedelta(minutes=5);api=Replay(later,[])
    assert event_monitor.build(cfg,state,later,api)[0] is None and not api.calls
    later=NOW+timedelta(minutes=60);api=Replay(later,[[]])
    event_monitor.build(cfg,state,later,api);assert len(api.calls)==1


def test_stale_and_regressing_observations_preserve_confirmed_snapshot():
    state={'posts':[]};observation(state,[raw()])
    observation(state,[raw(minute=40,score=(1,0))],NOW+timedelta(minutes=5))
    assert state['live_event_ledger']['matches']['1']['snapshot']['home_goals']==0
    with pytest.raises(ValueError,match='Stale'):match_events.observe(state,[],(NOW-timedelta(minutes=10)).isoformat(),NOW)
    observation(state,[raw()],NOW+timedelta(minutes=40))
    assert state['live_event_ledger']['matches']['1']['observed_at']==NOW.isoformat()


def test_no_score_status_graphic_does_not_fake_zero(tmp_path):
    m=match_events.normalise_observation(raw(status='CANC',minute=None,score=(None,None)),NOW)
    assert graphics.render({'kind':'live-score','match':m,'checked_at':NOW.isoformat(),'status_only':True},tmp_path/'cancelled.jpg').is_file()
    with pytest.raises(ValueError):graphics.render({'kind':'live-score','match':m,'checked_at':NOW.isoformat()},tmp_path/'bad.jpg')


class Response:
    def __init__(self,response,remaining=99,errors=None):
        self.headers={'Date':format_datetime(NOW),'x-ratelimit-requests-remaining':str(remaining)}
        self.value={'response':response,'errors':errors or [],'paging':{'total':1}}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):return json.dumps(self.value).encode()


class Opener:
    def __init__(self,*responses):self.responses=list(responses);self.calls=[]
    def open(self,request,timeout=0):
        self.calls.append(request)
        value=self.responses.pop(0)
        if isinstance(value,Exception):raise value
        return value


def account():return {'subscription':{'plan':'Free','active':True},'requests':{'current':1,'limit':100}}


def keys(monkeypatch):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic-private-primary')
    monkeypatch.setenv('API_FOOTBALL_KEY_1','synthetic-private-secondary')
    monkeypatch.setenv('API_FOOTBALL_KEY_2','synthetic-private-third')


def allow_failover(cfg):
    cfg['event_monitor'].update(failover_permitted=True,permission_reference='Synthetic test-only provider written permission')
    cfg['event_monitor']['key_slots']['API_FOOTBALL_KEY_1']['quota_group']='separately-authorised'


def test_default_daily_quota_never_pools_keys_and_utc_resets(cfg,monkeypatch):
    keys(monkeypatch);state={}
    for slot in cfg['event_monitor']['key_slots'].values():slot['quota_group']='primary'  # Shared-account regression: never pool keys.
    opener=Opener(Response(account()),HTTPError('https://example',429,'quota',{'x-ratelimit-requests-remaining':'0'},io.BytesIO()))
    with pytest.raises(QuotaExceeded):EventAPI(cfg,state,NOW,opener).get('fixtures',{'live':'all'})
    assert len(opener.calls)==2
    with pytest.raises(QuotaExceeded):EventAPI(cfg,state,NOW+timedelta(minutes=5),Opener()).get('fixtures')
    midnight=(NOW+timedelta(days=1)).replace(hour=3)
    api=EventAPI(cfg,state,midnight,Opener())
    assert api.group('primary')['requests']==0 and not api.group('primary').get('exhausted')
    assert 'synthetic-private' not in json.dumps(state)


def test_only_explicitly_permitted_independent_quota_failover(cfg,monkeypatch):
    keys(monkeypatch);allow_failover(cfg)
    opener=Opener(Response(account()),Response([],remaining=0,errors={'requests':'You have reached the request limit for the day'}),Response(account()),Response([{'verified':True}],98))
    state={};assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'verified':True}]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-primary']*2+['synthetic-private-secondary']*2
    assert state['event_api']['groups']['primary']['exhausted']
    assert not any('synthetic-private' in str(v) for v in state.values())


@pytest.mark.parametrize('error',[TimeoutError('synthetic-private-primary'),HTTPError('https://example',400,'bad',{},io.BytesIO()),HTTPError('https://example',500,'bad',{},io.BytesIO()),HTTPError('https://example',429,'minute',{'Retry-After':'300','x-ratelimit-requests-remaining':'80'},io.BytesIO())])
def test_no_key_switch_on_network_bad_request_server_or_minute_limit(cfg,monkeypatch,error):
    keys(monkeypatch);allow_failover(cfg);opener=Opener(Response(account()),error)
    with pytest.raises(ProviderError) as caught:EventAPI(cfg,{},NOW,opener).get('fixtures')
    assert len(opener.calls)==2 and 'synthetic-private' not in str(caught.value)


def test_local_90_ceiling_not_daily_quota_evidence(cfg,monkeypatch):
    cfg['event_monitor'].update(daily_request_budget=90,daily_request_reserve=10)
    keys(monkeypatch);allow_failover(cfg);state={};api=EventAPI(cfg,state,NOW,Opener())
    api.group('primary').update(requests=90,allocation=100,plan_checked=api.day)
    with pytest.raises(ProviderError,match='local request ceiling'):api.get('fixtures')
    assert not api.opener.calls


@pytest.mark.parametrize('errors,remaining,expected',[({'requests':'limit for the minute'},30,False),({'token':'invalid'},0,False),({'requests':'You have reached the request limit for the day'},10,True)])
def test_daily_quota_classifier(errors,remaining,expected):assert daily_quota(errors,remaining)==expected


def prepare_send(cfg,tmp_path,monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ID','local');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    now=datetime.now(content.SAST);state={'posts':[]}
    # Inject real-time synthetic snapshots directly; no external publication endpoint.
    m=raw();m['fixture']['date']=(now-timedelta(minutes=65)).isoformat()
    observation(state,[m],now)
    m['goals']['home']=1;m['fixture']['status']['elapsed']=55
    observation(state,[m],now+timedelta(seconds=1))
    book=state['live_event_ledger'];eid=next(iter(book['events']))
    post=content.candidate('live','send-test','send-test','Synthetic offline caption',event_ids=[eid],snapshot=[book['matches']['1']['snapshot']],expires_at=(now+timedelta(minutes=2)).isoformat())
    cfg['event_monitor']['publish_enabled']=True
    image=graphics.render({'kind':'live-score','match':post['snapshot'][0],'checked_at':now.isoformat()},tmp_path/'score.jpg')
    post.update(image=str(image),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true');monkeypatch.setenv('GITHUB_REF_NAME','main')
    entry=policy.reserve(post,state,now);entry['run_key']='local-1';match_events.publication_state(state,entry,'reserved',now)
    storage.write(tmp_path/'cfg.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    return post,eid


def test_fb_pre_mutation_failure_safely_pending_with_backoff(cfg,tmp_path,monkeypatch):
    _,eid=prepare_send(cfg,tmp_path,monkeypatch)
    def fail():raise PublishError('Credential verification failed before POST')
    monkeypatch.setattr(cli,'PageFeed',fail)
    assert cli.main(['send','--kind','live','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path),'--publish','--checkpoint'])==1
    state=content.load(tmp_path/'checkpoint/state.json')
    assert state['posts'][0]['status']=='cancelled' and state['live_event_ledger']['events'][eid]['status']=='pending'
    assert state['live_event_ledger']['events'][eid]['retry_after']


def test_fb_ambiguous_failure_never_blindly_retries(cfg,tmp_path,monkeypatch):
    post,eid=prepare_send(cfg,tmp_path,monkeypatch)
    class Unknown:
        def send(self,post):raise PublishError('Ambiguous timeout after POST')
    monkeypatch.setattr(cli,'PageFeed',Unknown)
    args=['send','--kind','live','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path),'--publish','--checkpoint']
    assert cli.main(args)==1
    with pytest.raises(ValueError,match='ownership'):cli.main(args)
    state=content.load(tmp_path/'checkpoint/state.json')
    assert state['live_event_ledger']['events'][eid]['status']=='unknown'
    other={**post,'key':'another','topic':'another'}
    assert 'unresolved live' in policy.allowed(other,state,datetime.now(content.SAST)+timedelta(minutes=5),cfg)[1]


def test_acknowledged_post_id_survives_verify_failure(cfg,tmp_path,monkeypatch):
    _,eid=prepare_send(cfg,tmp_path,monkeypatch)
    class VerifyFailure:
        def send(self,post):return '123_456'
        def verify(self,*args):raise PublishError('Verification delayed')
    monkeypatch.setattr(cli,'PageFeed',VerifyFailure)
    assert cli.main(['send','--kind','live','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path),'--publish','--checkpoint'])==1
    state=content.load(tmp_path/'checkpoint/state.json')
    assert state['posts'][0]['post_id']=='123_456' and state['posts'][0]['status']=='unknown'
    assert state['live_event_ledger']['events'][eid]['status']=='unknown'


def test_disabling_monitor_cannot_fall_through_to_periodic_posts(cfg):
    cfg['event_monitor']['enabled']=False
    assert not cli.is_due('live',NOW,cfg)
    assert cli.build('live',ROOT,NOW,cfg,{'posts':[]},preview=True)[0] is None


def test_read_only_recovery_of_known_ack_never_sends_replacement(cfg,tmp_path,monkeypatch):
    post,eid=prepare_send(cfg,tmp_path,monkeypatch)
    state=content.load(tmp_path/'checkpoint/state.json');state['posts'][0].update(status='unknown',post_id='123_456')
    match_events.publication_state(state,state['posts'][0],'unknown',datetime.now(content.SAST))
    monkeypatch.setenv('GH_READ_TOKEN','synthetic-github-token')
    monkeypatch.setattr(storage,'restore',lambda *args:state)
    monkeypatch.setattr(cli,'build',lambda *args,**kwargs:(None,'offline recovery test'))
    calls=[]
    class Existing:
        def verify_hash(self,*args):calls.append(args)
        def send(self,*args):raise AssertionError('No replacement POST permitted')
    monkeypatch.setattr(cli,'PageFeed',Existing)
    assert cli.main(['prepare','--kind','live','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path),'--publish'])==0
    restored=content.load(tmp_path/'checkpoint/state.json')
    assert calls==[('123_456',post['caption_hash'])]
    assert restored['posts'][0]['status']=='published'
    assert restored['live_event_ledger']['events'][eid]['status']=='published'


def test_publish_enabled_false_blocks_even_requested_scheduled_publication(cfg,tmp_path,monkeypatch):
    cfg['event_monitor']['publish_enabled']=False
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true');monkeypatch.setenv('GITHUB_REF_NAME','main')
    monkeypatch.setenv('GH_READ_TOKEN','synthetic-github-token');monkeypatch.setenv('GITHUB_OUTPUT',str(tmp_path/'outputs'))
    monkeypatch.setenv('GITHUB_REPOSITORY','local/repo')
    prefixes=[]
    def restore(repo,branch,rid,prefix,*args):prefixes.append(prefix);return {'posts':[]}
    monkeypatch.setattr(storage,'restore',restore)
    monkeypatch.setattr(cli,'build',lambda *args,**kwargs:(None,'offline gated test'))
    def forbidden():raise AssertionError('Dry monitor must never contact Facebook')
    monkeypatch.setattr(cli,'PageFeed',forbidden)
    storage.write(tmp_path/'cfg.json',cfg)
    assert cli.main(['prepare','--kind','live','--publish','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path)])==0
    assert prefixes==[storage.namespace('local/repo','main',False)]
    assert 'should_publish=false' in (tmp_path/'outputs').read_text()


def test_empty_or_restricted_calendar_does_not_block_global_plan_permitted_live(cfg):
    api=Replay(NOW,[ProviderError('Calendar plan restricted'),[raw()]])
    state={'posts':[]};assert event_monitor.build(cfg,state,NOW,api)[0] is None
    assert len(api.calls)==2 and state['live_event_ledger']['matches']['1']


def test_more_than_twenty_changed_matches_are_one_consolidated_post(cfg):
    state=baseline(cfg,[raw(fid=i) for i in range(1,26)])
    now=NOW+timedelta(minutes=5)
    post,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(fid=i,score=(1,0),minute=55) for i in range(1,26)]]))
    assert len(post['snapshot'])==25 and len(post['event_ids'])==25


def test_previous_day_kickoff_is_monitored_after_sast_midnight():
    now=NOW.replace(hour=0,minute=20)+timedelta(days=1)
    value=raw(minute=50);value['fixture']['date']=(now-timedelta(minutes=65)).isoformat()
    assert match_events.normalise_observation(value,now)


def test_red_card_casing_enrichment_and_corrected_minute_do_not_duplicate():
    state={'posts':[]};observation(state,[raw()])
    red=event(kind='Card',detail='Red Card')
    observation(state,[raw(minute=55,events=[red])],NOW+timedelta(minutes=5))
    red['detail']='Red card';red['time']['elapsed']=55
    observation(state,[raw(minute=60,events=[red])],NOW+timedelta(minutes=10))
    assert len(state['live_event_ledger']['events'])==1


def test_red_card_without_name_then_later_identification_is_not_another_card():
    state={'posts':[]};observation(state,[raw()])
    red=event(kind='Card',detail='Red Card',player=None,pid=None)
    observation(state,[raw(minute=55,events=[red])],NOW+timedelta(minutes=5))
    red['player']={'id':33,'name':'Synthetic Identified Player'}
    observation(state,[raw(minute=60,events=[red])],NOW+timedelta(minutes=10))
    assert len(state['live_event_ledger']['events'])==1


def test_no_invented_goal_minute_when_only_score_known(cfg):
    state=baseline(cfg);now=NOW+timedelta(minutes=5)
    post,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(score=(1,0),minute=55)]]))
    assert 'Score updated' in post['caption'] and "55' | Goal" not in post['caption']
    assert "Status: Second half | 55'" in post['caption']


def test_bad_credentials_with_zero_header_do_not_enable_later_failover_when_auth_fallback_off(cfg,monkeypatch):
    cfg['event_monitor']['authentication_failover_permitted']=False
    keys(monkeypatch);allow_failover(cfg);state={}
    opener=Opener(Response(account()),Response([],0,{'token':'synthetic-private-primary'}))
    with pytest.raises(ProviderError):EventAPI(cfg,state,NOW,opener).get('fixtures')
    again=Opener()
    with pytest.raises(ProviderError,match='credential unavailable'):EventAPI(cfg,state,NOW+timedelta(minutes=5),again).get('fixtures')
    assert not again.calls and not state['event_api']['groups']['primary'].get('exhausted')


def test_pending_expiry_and_simulated_never_claim_facebook_publication(cfg):
    state=baseline(cfg);now=NOW+timedelta(minutes=5)
    post,_=event_monitor.build(cfg,state,now,Replay(now,[[raw(score=(1,0),minute=55)]]))
    match_events.publication_state(state,post,'simulated',now)
    assert state['live_event_ledger']['last_successful_publication'] is None
    for e in state['live_event_ledger']['events'].values():e['status']='pending'
    match_events.observe(state,[],(now+timedelta(hours=7)).isoformat(),now+timedelta(hours=7))
    assert all(e['status']=='expired' for e in state['live_event_ledger']['events'].values())


def test_state_size_guard_prevents_unrestorable_reservations(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'MAX_STATE_BYTES',100)
    with pytest.raises(storage.StateError,match='size bound'):storage.write(tmp_path/'state.json',{'too_large':'x'*101})
    assert not (tmp_path/'state.json').exists()


def test_event_send_gate_cannot_be_bypassed_by_different_cli_kind(cfg,tmp_path,monkeypatch):
    prepare_send(cfg,tmp_path,monkeypatch)
    cfg['event_monitor']['publish_enabled']=False;storage.write(tmp_path/'cfg.json',cfg)
    def forbidden():raise AssertionError('Must reject before Facebook credential requests')
    monkeypatch.setattr(cli,'PageFeed',forbidden)
    with pytest.raises(ValueError,match='publication gate changed'):
        cli.main(['send','--kind','results','--config',str(tmp_path/'cfg.json'),'--work',str(tmp_path),'--publish','--checkpoint'])


def test_three_confirmed_allocations_fail_over_only_on_documented_daily_exhaustion(cfg,monkeypatch):
    keys(monkeypatch);state={}
    opener=Opener(Response(account()),Response([],0,{'requests':'You have reached the request limit for the day'}),
                  Response(account()),HTTPError('https://example',429,'daily',{'x-ratelimit-requests-remaining':'0'},io.BytesIO()),
                  Response(account()),Response([{'verified_third_allocation':True}],98))
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'verified_third_allocation':True}]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-primary']*2+['synthetic-private-secondary']*2+['synthetic-private-third']*2
    groups=state['event_api']['groups']
    assert groups['primary']['exhausted'] and groups['backup-1']['exhausted']
    assert groups['primary']['requests']==100 and groups['backup-1']['requests']==100
    assert groups['backup-2']['requests']==2 and not groups['backup-2'].get('exhausted')
    assert 'synthetic-private' not in json.dumps(state)


def test_mapping_backups_does_not_reset_existing_primary_budget(cfg):
    state={'event_api':{'groups':{'primary':{'utc_date':'2026-10-30','requests':55,'remaining':45}},'slots':{}}}
    api=EventAPI(cfg,state,NOW,Opener())
    assert api.group('primary')['requests']==55 and api.group('primary')['remaining']==45
    assert api.group('backup-1')['requests']==0 and api.group('backup-2')['requests']==0
    assert api.group('primary')['requests']==55


def test_full_hundredth_request_is_used_then_next_poll_uses_renamed_backup(cfg,monkeypatch):
    keys(monkeypatch);state={};api=EventAPI(cfg,state,NOW,Opener())
    api.group('primary').update(requests=99,allocation=100,remaining=1,provider_used=99,plan_checked=api.day)
    api.state['slots']['API_FOOTBALL_KEY']={'revision':cfg['event_monitor']['credential_revision'],'plan_checked':api.day}
    opener=Opener(Response([{'last_primary_request':True}],0),Response(account()),Response([{'backup_request':True}],98))
    api.opener=opener
    assert api.get('fixtures')==[{'last_primary_request':True}]
    assert state['event_api']['groups']['primary']['requests']==100
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'backup_request':True}]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-primary','synthetic-private-secondary','synthetic-private-secondary']
    assert 'API_FOOTBALL_KEY_1' in state['event_api']['slots']


def test_local_failed_attempt_count_is_not_provider_quota_evidence(cfg,monkeypatch):
    keys(monkeypatch);state={};api=EventAPI(cfg,state,NOW,Opener())
    api.group('primary').update(requests=100,allocation=100,remaining=1,provider_used=99,plan_checked=api.day)
    with pytest.raises(ProviderError,match='local request ceiling'):api.get('fixtures')
    assert not api.opener.calls


def test_status_verified_exhaustion_switches_without_probing_fixtures_on_full_account(cfg,monkeypatch):
    keys(monkeypatch);used=account();used['requests']['current']=100
    opener=Opener(Response(used,0),Response(account()),Response([{'fresh':True}],98))
    state={};assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'fresh':True}]
    assert len(opener.calls)==3 and state['event_api']['groups']['primary']['exhausted']


def test_activation_uses_exact_renamed_slots_and_full_verified_limits(cfg):
    from facebook_feed.event_provider import SLOTS
    assert SLOTS==('API_FOOTBALL_KEY','API_FOOTBALL_KEY_1','API_FOOTBALL_KEY_2')
    assert cfg['event_monitor']['publish_enabled'] and cfg['event_monitor']['daily_request_budget']==100
    assert cfg['event_monitor']['daily_request_reserve']==0
    workflow=(ROOT/'.github/workflows/facebook-feed-run.yml').read_text()
    assert 'secrets.API_FOOTBALL_KEY_1' in workflow and 'secrets.API_FOOTBALL_KEY1' not in workflow
    assert 'secrets.API_FOOTBALL_KEY_2' in workflow and 'secrets.API_FOOTBALL_KEY2' not in workflow


def test_corrected_third_slot_reverifies_without_resetting_backup_usage(cfg,monkeypatch):
    keys(monkeypatch);state={};api=EventAPI(cfg,state,NOW,Opener())
    api.group('primary').update(exhausted=True,requests=100,remaining=0)
    api.group('backup-1').update(exhausted=True,requests=100,remaining=0)
    api.group('backup-2').update(requests=55,allocation=100,provider_used=55,remaining=45,plan_checked=api.day)
    used=account();used['requests']['current']=56
    opener=Opener(Response(used,44),Response([{'third_slot_verified':True}],43))
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'third_slot_verified':True}]
    assert len(opener.calls)==2
    assert all(r.get_header('X-apisports-key')=='synthetic-private-third' for r in opener.calls)
    assert state['event_api']['groups']['backup-2']['requests']==57
    assert state['event_api']['groups']['primary']['requests']==100
    assert state['event_api']['groups']['backup-1']['requests']==100
    assert state['event_api']['slots']['API_FOOTBALL_KEY_2']['plan_checked']==api.day


def test_primary_auth_rejection_immediately_uses_second_key_without_quota_poisoning(cfg,monkeypatch):
    keys(monkeypatch);state={}
    opener=Opener(Response([],0,{'token':'synthetic-private-primary'}),Response(account()),Response([{'second_verified':True}],98))
    api=EventAPI(cfg,state,NOW,opener)
    assert api.get('fixtures')==[{'second_verified':True}]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-primary']+['synthetic-private-secondary']*2
    assert api.active=='API_FOOTBALL_KEY_1' and state['event_api']['last_successful_slot']==api.active
    assert not state['event_api']['groups']['primary'].get('exhausted')
    assert state['event_api']['groups']['primary']['remaining'] is None
    assert state['event_api']['slots']['API_FOOTBALL_KEY']['failure_kind']=='authentication'
    assert 'synthetic-private' not in json.dumps(state)


def test_first_two_auth_rejections_immediately_use_third_key(cfg,monkeypatch):
    keys(monkeypatch);state={}
    opener=Opener(Response([],99,{'token':'rejected'}),Response([],99,{'key':'rejected'}),Response(account()),Response([{'third_verified':True}],98))
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'third_verified':True}]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-primary','synthetic-private-secondary']+['synthetic-private-third']*2
    assert state['event_api']['last_successful_slot']=='API_FOOTBALL_KEY_2'


def test_known_auth_rejection_skips_primary_during_cooldown(cfg,monkeypatch):
    keys(monkeypatch);state={}
    first=Opener(Response([],99,{'token':'rejected'}),Response(account()),Response([],98))
    EventAPI(cfg,state,NOW,first).get('fixtures')
    fresh=Response([{'still_second':True}],97);fresh.headers['Date']=format_datetime(NOW+timedelta(minutes=5))
    again=Opener(fresh)
    assert EventAPI(cfg,state,NOW+timedelta(minutes=5),again).get('fixtures')==[{'still_second':True}]
    assert len(again.calls)==1 and again.calls[0].get_header('X-apisports-key')=='synthetic-private-secondary'


def test_credential_failure_on_fixture_without_quota_header_can_fall_back(cfg,monkeypatch):
    keys(monkeypatch);failed=Response([],99,{'token':'rejected'});failed.headers.pop('x-ratelimit-requests-remaining')
    opener=Opener(Response(account()),failed,Response(account()),Response([{'verified':True}],98))
    assert EventAPI(cfg,{},NOW,opener).get('fixtures')==[{'verified':True}]


def test_http_401_auth_challenge_can_use_verified_backup(cfg,monkeypatch):
    keys(monkeypatch)
    opener=Opener(HTTPError('https://example',401,'unauthorised',{},io.BytesIO(b'authentication required')),Response(account()),Response([],98))
    assert EventAPI(cfg,{},NOW,opener).get('fixtures')==[]
    assert len(opener.calls)==3


@pytest.mark.parametrize('errors',[{'ip':'not allowed'},{'token':'account suspended'},{'token':'IP address not allowed'},{'token':'bad','parameters':'bad'},{'plan':'not covered'}])
def test_access_restrictions_plan_and_parameter_failures_never_switch_keys(cfg,monkeypatch,errors):
    keys(monkeypatch);opener=Opener(Response([],99,errors))
    with pytest.raises(ProviderError):EventAPI(cfg,{},NOW,opener).get('fixtures')
    assert len(opener.calls)==1


@pytest.mark.parametrize('code,body',[(403,b'forbidden'),(401,b'account suspended'),(401,b'IP address restriction')])
def test_http_restriction_never_switches_keys(cfg,monkeypatch,code,body):
    keys(monkeypatch);state={};opener=Opener(HTTPError('https://example',code,'rejected',{},io.BytesIO(body)))
    with pytest.raises(ProviderError):EventAPI(cfg,state,NOW,opener).get('fixtures')
    again=Opener()
    with pytest.raises(ProviderError):EventAPI(cfg,state,NOW+timedelta(minutes=5),again).get('fixtures')
    assert len(opener.calls)==1 and not again.calls


def test_all_credentials_rejected_preserves_previous_good_data(cfg,monkeypatch):
    from facebook_feed.event_provider import AuthenticationRejected
    keys(monkeypatch);state={'live_event_ledger':{'sentinel':'last confirmed data'}}
    opener=Opener(*(Response([],99,{'token':'synthetic-private-primary'}) for _ in range(3)))
    with pytest.raises(AuthenticationRejected) as caught:EventAPI(cfg,state,NOW,opener).get('fixtures')
    assert len(opener.calls)==3 and state['live_event_ledger']=={'sentinel':'last confirmed data'}
    assert all(not g.get('exhausted') for g in state['event_api']['groups'].values())
    assert 'synthetic-private' not in str(caught.value) and 'synthetic-private' not in json.dumps(state)


def test_auth_fallback_requires_existing_provider_permission(cfg,monkeypatch):
    keys(monkeypatch);cfg['event_monitor']['failover_permitted']=False
    opener=Opener(Response([],99,{'token':'rejected'}))
    with pytest.raises(ProviderError):EventAPI(cfg,{},NOW,opener).get('fixtures')
    assert len(opener.calls)==1


def test_policy_revision_reverifies_old_cooldown_without_resetting_usage(cfg,monkeypatch):
    keys(monkeypatch);state={};api=EventAPI(cfg,state,NOW,Opener())
    api.group('primary').update(requests=55,remaining=45,allocation=100,plan_checked=api.day)
    api.state['slots']['API_FOOTBALL_KEY']={'revision':'2','invalid_until':(NOW+timedelta(hours=6)).isoformat()}
    opener=Opener(Response([],45,{'token':'rejected'}),Response(account()),Response([],98))
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[]
    assert state['event_api']['groups']['primary']['requests']==56
    assert len(opener.calls)==3
