"""Offline Highlightly fixtures only; no live credentials, provider or Page calls."""
from copy import deepcopy
from datetime import timedelta
from email.utils import format_datetime
import io
import json
from pathlib import Path
from urllib.error import HTTPError
import pytest
from facebook_feed import cli,highlightly,diagnostics,storage,event_monitor,crest_cache,match_events
from facebook_feed.provider import ProviderError
from test_event_monitor import NOW,Opener

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def cfg():
    cfg=cli.config(ROOT/'config/facebook-feed.json')
    # Historical live replay, independently of the paused production config.
    cfg['live']['enabled']=True
    cfg['event_monitor'].update(enabled=True,publish_enabled=True)
    cfg['authorized_kinds']=['live','results']
    # Explicit staging regression fixture; current production activation is tested separately.
    cfg['highlightly'].update(verification_only=True,account_coverage_verified=False,monitor_mode='all')
    return cfg


def row(mid=1,status='Second half',score='1 - 0',clock=65,events=None):
    return {'id':mid,'date':(NOW-timedelta(minutes=80)).isoformat(),
            'homeTeam':{'id':10,'name':'Synthetic Home'},'awayTeam':{'id':20,'name':'Synthetic Away'},
            'league':{'id':90,'name':'Synthetic League'},'country':{'name':'Synthetic Country'},
            'state':{'description':status,'clock':clock,'score':{'current':score}},'events':events or []}


def envelope(rows=None,total=None,offset=0,tier='BASIC'):
    rows=[row()] if rows is None else rows
    return {'data':rows,'pagination':{'limit':100,'offset':offset,'totalCount':len(rows) if total is None else total},'plan':{'tier':tier,'message':'PRIVATE provider details'}}


class Response:
    def __init__(self,value=None,remaining=99,limit=100,stamp=NOW):
        self.value=envelope() if value is None else value
        self.headers={'Date':format_datetime(stamp),'x-ratelimit-requests-limit':str(limit),'x-ratelimit-requests-remaining':str(remaining)}
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):return json.dumps(self.value).encode()


def api(cfg,monkeypatch,*responses,state=None,now=NOW):
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-highlightly')
    opener=Opener(*(responses or [Response(),Response([row()],98)]))
    return highlightly.Highlightly(cfg,{} if state is None else state,now,opener),opener


def test_staging_gate_blocks_reads_and_suspended_accounts_stay_disabled(cfg,monkeypatch):
    assert cfg['score_source']=='highlightly' and not cli.scores_approved(cfg)
    assert all(not s['authorised'] for s in cfg['event_monitor']['key_slots'].values())
    client,opener=api(cfg,monkeypatch)
    assert not event_monitor.poll(cfg,{},NOW,client)[0] and opener.calls==[]


def test_direct_auth_fixed_host_plan_and_safe_report(cfg,monkeypatch):
    state={'posts':[{'status':'unknown','post_id':'keep'}],'event_api':{'groups':{'primary':{'requests':17}}},'live_event_ledger':{'keep':'unchanged'}}
    before=deepcopy(state);client,opener=api(cfg,monkeypatch,state=state)
    report=highlightly.diagnose(cfg,state,NOW,client)
    assert report['outcome']=='verified_read_only' and report['facebook_requests']==0
    assert report['http_attempted'] and report['usable_observations']==1
    assert report['allocation']==100 and report['requests']==2 and report['match_detail_verified'] and report['ready_for_activation']
    request=opener.calls[0]
    assert request.full_url.startswith('https://soccer.highlightly.net/matches?')
    assert request.get_header('X-rapidapi-key')=='synthetic-private-highlightly'
    assert request.get_header('X-apisports-key') is None
    assert all(state[k]==before[k] for k in before)
    assert 'PRIVATE' not in json.dumps(report) and 'synthetic-private' not in json.dumps(report)
    assert not cli.scores_approved(cfg)  # No automatic enable/reset from a diagnostic.


def test_missing_key_makes_no_request(cfg,monkeypatch):
    monkeypatch.delenv('HIGHLIGHTLY_API_KEY',raising=False)
    client=highlightly.Highlightly(cfg,{},NOW,Opener())
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['reason']=='not_configured' and not report['http_attempted']


def test_final_permitted_response_valid_no_101st(cfg,monkeypatch):
    state={'highlightly_api':{'utc_date':'2026-10-30','requests':99,'remaining':1}}
    client,opener=api(cfg,monkeypatch,Response(remaining=0),state=state)
    client.page()
    assert client.budget['requests']==100
    with pytest.raises(ProviderError):client.page()
    assert len(opener.calls)==1


def test_external_usage_and_utc_reset_do_not_reset_other_provider_or_unknown_sends(cfg,monkeypatch):
    state={'posts':[{'status':'unknown'}],'event_api':{'groups':{'primary':{'requests':100}}}}
    client,_=api(cfg,monkeypatch,Response(remaining=4),state=state)
    client.page();assert client.budget['requests']==96
    tomorrow=highlightly.Highlightly(cfg,state,NOW+timedelta(days=1),Opener())
    assert tomorrow.budget['requests']==0
    assert state['event_api']['groups']['primary']['requests']==100 and state['posts']==[{'status':'unknown'}]


@pytest.mark.parametrize('code',[401,403,429,500,503])
def test_http_errors_are_counted_redacted_and_not_rotated(cfg,monkeypatch,code):
    error=HTTPError('https://soccer.highlightly.net/matches',code,'PRIVATE',{'Retry-After':'600'},io.BytesIO(b'PRIVATE synthetic-private-highlightly'))
    client,opener=api(cfg,monkeypatch,error)
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['outcome']=='blocked' and report['requests']==1 and report['facebook_requests']==0
    assert 'PRIVATE' not in json.dumps(report) and 'synthetic-private' not in json.dumps(report)
    with pytest.raises(ProviderError):client.page()
    assert len(opener.calls)==1
    if code==429:assert client.budget['remaining'] is None


def test_auth_cooldown_survives_utc_rollover(cfg,monkeypatch):
    state={'highlightly_api':{'utc_date':'2026-10-29','requests':40,'remaining':60,'after':(NOW+timedelta(hours=2)).isoformat()}}
    client,opener=api(cfg,monkeypatch,state=state)
    with pytest.raises(ProviderError):client.page()
    assert opener.calls==[] and client.budget['requests']==0


@pytest.mark.parametrize('response',[
    Response(stamp=NOW-timedelta(minutes=10)),Response(limit=7500),
    Response(remaining=-1),Response(value={'errors':{'token':'PRIVATE'}}),
    Response(value=envelope(tier='PRO')),
    Response(value={'data':[],'pagination':{'totalCount':100,'offset':0,'limit':100},'plan':{'tier':'BASIC'}}),
])
def test_bad_freshness_quota_plan_error_and_incomplete_page_block(cfg,monkeypatch,response):
    client,opener=api(cfg,monkeypatch,response)
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['outcome']=='blocked' and report['requests']>=1 and len(opener.calls)==1
    assert 'PRIVATE' not in json.dumps(report)


def test_complete_pagination_and_full_diagnostic_verification(cfg,monkeypatch):
    first=[row(i) for i in range(1,101)];last=[row(101)]
    client,opener=api(cfg,monkeypatch,Response(envelope(first,101)),Response(envelope(last,101,100),98))
    assert len(client.matches())==101 and len(opener.calls)==2
    assert 'offset=100' in opener.calls[1].full_url
    client,_=api(cfg,monkeypatch,Response(envelope(first,101)),Response(envelope(last,101,100),98),Response([row()],97))
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['coverage']=='complete_day' and report['total_rows']==101 and report['pages_read']==2
    assert report['match_detail_verified'] and report['ready_for_activation']


@pytest.mark.parametrize('failure',['bound','duplicate','changed_total','quota'])
def test_partial_matchdays_never_advance_baseline(cfg,monkeypatch,failure):
    cfg['highlightly']['verification_only']=False
    first=[row(i) for i in range(1,101)]
    responses=[Response(envelope(first,101),0 if failure=='quota' else 99)]
    if failure=='bound':cfg['highlightly']['max_pages_per_poll']=1
    else:responses.append(Response(envelope([row(1 if failure=='duplicate' else 101)],102 if failure=='changed_total' else 101,100),98))
    state={'live_event_ledger':{'version':1,'matches':{},'events':{}},'posts':[{'status':'unknown'}]}
    before=deepcopy(state['live_event_ledger']);client,_=api(cfg,monkeypatch,*responses,state=state)
    with pytest.raises(ProviderError):highlightly.poll(cfg,state,NOW,client)
    assert state['live_event_ledger']==before and state['posts']==[{'status':'unknown'}]


def test_namespace_unknowns_missing_scores_and_no_guessed_halftime():
    m=highlightly.observation(row(),NOW)
    assert m['id']=='highlightly:1' and m['source']=='highlightly'
    assert m['home_goals']==1 and m['halftime'] is None and m['fulltime'] is None
    assert highlightly.observation(row(status='Unknown'),NOW) is None
    assert highlightly.observation(row(score=None),NOW) is None
    with pytest.raises(ProviderError):highlightly.observation(row(score='unknown'),NOW)


def test_verified_events_only_and_penalties_separate():
    events=[{'type':kind,'time':'65','team':{'id':10},'player':'Synthetic Player','playerId':9} for kind in ('Goal','Missed Penalty','VAR Goal Cancelled','Red Card')]
    value=row(events=events);value['state']['score']['penalties']='4 - 3'
    m=highlightly.observation(value,NOW)
    assert {e['kind'] for e in m['events']}=={'goal','red_card'}
    assert len(m['events'])==2 and m['penalties']==[4,3] and m['home_goals']==1


def test_direct_client_refuses_arbitrary_routes_and_cross_provider_detail_ids(cfg,monkeypatch):
    client,opener=api(cfg,monkeypatch)
    for route in ('status','odds','predictions','highlights','matches/1?x=bad','https://evil.invalid'):
        with pytest.raises(ProviderError):client.request(route)
    for key in ('1','api-football:1','highlightly:../1'):
        with pytest.raises(ProviderError):client.detail(key)
    assert opener.calls==[]


def test_baseline_minute_only_then_consolidated_real_change_after_explicit_activation(cfg,monkeypatch):
    cfg['highlightly']['verification_only']=False;cfg['highlightly']['account_coverage_verified']=True
    state={'posts':[]};cfg['highlightly']['max_details_per_poll']=0
    client,_=api(cfg,monkeypatch,Response(envelope([row()])),state=state)
    assert event_monitor.build(cfg,state,NOW,client)[0] is None
    later=NOW+timedelta(minutes=20)
    client,_=api(cfg,monkeypatch,Response(envelope([row(clock=85)]),98,stamp=later),state=state,now=later)
    assert event_monitor.build(cfg,state,later,client)[0] is None
    later+=timedelta(minutes=20)
    client,_=api(cfg,monkeypatch,Response(envelope([row(score='2 - 0',clock=90)]),97,stamp=later),state=state,now=later)
    post,_=event_monitor.build(cfg,state,later,client)
    assert post and '2–0' in post['caption'] and post['snapshot'][0]['source']=='highlightly'


def test_no_api_sports_crest_lookup_for_highlightly_ids(monkeypatch,tmp_path):
    monkeypatch.setattr(crest_cache,'fetch_crest',lambda *a:pytest.fail('Cross-provider crest fetch'))
    spec={'match':highlightly.observation(row(),NOW)}
    assert crest_cache.prepare(spec,tmp_path)['crests']=={}


def test_diagnostic_main_selected_provider_preserves_durable_state(cfg,monkeypatch,tmp_path):
    monkeypatch.setattr(cli,'PageFeed',lambda *a,**kw:pytest.fail('Diagnostic must not contact Facebook'))
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GH_READ_TOKEN','synthetic-placeholder-read')
    monkeypatch.setenv('GITHUB_REPOSITORY','synthetic/repo');monkeypatch.setenv('GITHUB_REPOSITORY_ID','123')
    monkeypatch.setattr(diagnostics,'config',lambda _:cfg)
    state={'schema':1,'posts':[{'status':'unknown'}],'event_api':{'groups':{'primary':{'requests':100}}}}
    monkeypatch.setattr(storage,'restore',lambda *a:state)
    real=highlightly.diagnose
    def fake(cfg,state,now):
        client,_=api(cfg,monkeypatch,Response(stamp=now),state=state,now=now)
        return real(cfg,state,now,client)
    monkeypatch.setattr(highlightly,'diagnose',fake)
    assert diagnostics.main()==0
    saved=json.loads((tmp_path/'tmp/facebook-feed/checkpoint/state.json').read_text())
    report=json.loads((tmp_path/'tmp/facebook-feed/api-diagnostic.json').read_text())
    assert report['mode']=='read_only_highlightly_diagnostic' and report['facebook_requests']==0
    assert saved['posts']==state['posts'] and saved['event_api']==state['event_api'] and saved['highlightly_api']['requests']==1


def activate(cfg):
    cfg['highlightly'].update(verification_only=False,account_coverage_verified=True)


def test_detail_refresh_confirms_disappearing_fixture_not_its_absence(cfg,monkeypatch):
    activate(cfg);state={'posts':[]}
    initial=row();m=highlightly.observation(initial,NOW)
    match_events.observe(state,[m],NOW.isoformat(),NOW)
    later=NOW+timedelta(minutes=20)
    final=row(status='Finished',clock=90)
    client,opener=api(cfg,monkeypatch,Response(envelope([]),98,stamp=later),Response([final],97,stamp=later),state=state,now=later)
    post,_=event_monitor.build(cfg,state,later,client)
    assert post and 'Full-time' in post['caption']
    assert opener.calls[1].full_url=='https://soccer.highlightly.net/matches/1'


def test_details_confirm_red_and_goal_without_repeating_baseline(cfg,monkeypatch):
    activate(cfg);state={'posts':[]}
    client,_=api(cfg,monkeypatch,Response(envelope()),Response([row()],98),state=state)
    assert event_monitor.build(cfg,state,NOW,client)[0] is None
    later=NOW+timedelta(minutes=20)
    detail=row(score='2 - 0',clock=85,events=[{'type':'Goal','time':'85','team':{'id':10},'player':'Synthetic Scorer','playerId':11},
                                           {'type':'Red Card','time':'85','team':{'id':20},'player':'Synthetic Defender','playerId':22}])
    client,_=api(cfg,monkeypatch,Response(envelope([row(score='2 - 0',clock=85)]),97,stamp=later),Response([detail],96,stamp=later),state=state,now=later)
    post,_=event_monitor.build(cfg,state,later,client)
    assert post and 'Synthetic Scorer' in post['caption'] and 'Red card — Synthetic Defender' in post['caption']
    assert len(post['event_ids'])==2


def test_other_provider_id_pending_history_and_unknown_send_are_never_relabelled(cfg,monkeypatch):
    activate(cfg);cfg['highlightly']['max_details_per_poll']=0
    old=highlightly.observation(row(),NOW);old.update(id='1',source='api-football')
    state={'posts':[{'status':'unknown','key':'keep'}]}
    match_events.observe(state,[old],NOW.isoformat(),NOW)
    state['live_event_ledger']['events']['old']={'id':'old','fixture_id':'1','change':{'kind':'score_update'},'status':'pending','detected_at':NOW.isoformat()}
    before=deepcopy(state)
    client,_=api(cfg,monkeypatch,state=state)
    post,_=event_monitor.build(cfg,state,NOW,client)
    assert post is None and state['posts']==before['posts']
    assert state['live_event_ledger']['matches']['1']==before['live_event_ledger']['matches']['1']
    assert state['live_event_ledger']['events']['old']==before['live_event_ledger']['events']['old']
    assert 'highlightly:1' in state['live_event_ledger']['matches']


def test_detail_wrong_team_blocks_all_observations(cfg,monkeypatch):
    activate(cfg);state={'posts':[]};detail=row();detail['homeTeam']['id']=99
    client,_=api(cfg,monkeypatch,Response(),Response([detail],98),state=state)
    with pytest.raises(ProviderError):highlightly.poll(cfg,state,NOW,client)
    assert not state['live_event_ledger']['matches']


@pytest.mark.parametrize('field,value',[('verification_only','false'),('daily_request_budget',101),('max_pages_per_poll',11),('max_details_per_poll',50),('poll_interval_minutes',5)])
def test_config_bounds_fail_closed(cfg,tmp_path,field,value):
    cfg['highlightly'][field]=value
    path=tmp_path/'config.json';path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):cli.config(path)


def test_retry_after_is_honoured_and_details_require_verified_plan(cfg,monkeypatch):
    client,opener=api(cfg,monkeypatch)
    with pytest.raises(ProviderError):client.request('matches/1')
    assert opener.calls==[]
    error=HTTPError('https://soccer.highlightly.net/matches',429,'PRIVATE',{'Retry-After':'3600'},io.BytesIO())
    client,_=api(cfg,monkeypatch,error)
    with pytest.raises(ProviderError):client.page()
    assert client.budget['after']==(NOW+timedelta(hours=1)).isoformat()


def test_empty_day_is_verified_empty_not_fabricated_matches(cfg,monkeypatch):
    client,_=api(cfg,monkeypatch,Response(envelope([])))
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['outcome']=='verified_read_only' and report['list_rows']==0 and report['usable_observations']==0
    assert not cli.scores_approved(cfg)



def test_existing_unknown_send_guard_blocks_new_provider_post(cfg):
    from facebook_feed import content,policy
    activate(cfg)
    old=content.candidate('live','old','old-topic','Old factual caption',snapshot=[{'id':'1','source':'api-football'}])
    state={'posts':[]};entry=policy.reserve(old,state,NOW-timedelta(hours=1));entry['status']='unknown'
    new=content.candidate('live','new','new-topic','New factual caption',snapshot=[highlightly.observation(row(),NOW)],event_ids=['new-event'])
    allowed,reason=policy.allowed(new,state,NOW,cfg)
    assert not allowed and 'unresolved live publication' in reason and entry['status']=='unknown'


def test_full_diagnostic_verifies_all_284_rows_and_one_detail_without_event_changes(cfg,monkeypatch):
    state={'posts':[{'status':'unknown'}],'live_event_ledger':{'sentinel':'untouched'},'event_api':{'primary':'untouched'}}
    before=deepcopy(state)
    pages=[Response(envelope([row(i) for i in range(1,101)],284),99),
           Response(envelope([row(i) for i in range(101,201)],284,100),98),
           Response(envelope([row(i) for i in range(201,285)],284,200),97),Response([row()],96)]
    client,opener=api(cfg,monkeypatch,*pages,state=state)
    report=highlightly.diagnose(cfg,state,NOW,client)
    assert report['outcome']=='verified_read_only' and report['ready_for_activation']
    assert report['total_rows']==284 and report['pages_read']==3 and report['match_detail_verified']
    assert len(opener.calls)==4 and report['requests']==4 and report['remaining']==96
    assert report['facebook_requests']==0 and all(state[k]==before[k] for k in before)
    assert not cli.scores_approved(cfg)


@pytest.mark.parametrize('case',['quota','missing_events','wrong_team','partial_pages','network'])
def test_failed_full_diagnostic_never_reports_ready_or_advances_state(cfg,monkeypatch,case):
    state={'posts':[{'status':'unknown'}],'live_event_ledger':{'sentinel':'untouched'}}
    before=deepcopy(state)
    detail=row()
    if case=='missing_events':detail.pop('events')
    if case=='wrong_team':detail['homeTeam']['name']='Wrong identity'
    if case=='partial_pages':
        cfg['highlightly']['max_pages_per_poll']=1
        responses=[Response(envelope([row(i) for i in range(1,101)],101))]
    else:
        responses=[Response(remaining=0 if case=='quota' else 99),OSError('PRIVATE synthetic-private-highlightly') if case=='network' else Response([detail],98)]
    client,opener=api(cfg,monkeypatch,*responses,state=state)
    report=highlightly.diagnose(cfg,state,NOW,client)
    assert report['outcome']=='blocked' and not report['ready_for_activation'] and not report['match_detail_verified']
    assert report['facebook_requests']==0 and all(state[k]==before[k] for k in before)
    assert len(opener.calls)==(1 if case in ('quota','partial_pages') else 2)
    assert 'PRIVATE' not in json.dumps(report) and 'synthetic-private' not in json.dumps(report)


def test_verified_empty_list_is_not_ready_for_activation_without_detail_sample(cfg,monkeypatch):
    client,opener=api(cfg,monkeypatch,Response(envelope([])))
    report=highlightly.diagnose(cfg,{},NOW,client)
    assert report['outcome']=='verified_read_only' and report['coverage']=='complete_day'
    assert not report['ready_for_activation'] and not report['match_detail_verified'] and len(opener.calls)==1


def test_verified_production_config_is_activated_with_all_existing_limits():
    current=cli.config(ROOT/'config/facebook-feed.json')
    assert current['score_source']=='highlightly' and cli.scores_approved(current)
    assert current['highlightly']['verification_only'] is False
    assert current['highlightly']['account_coverage_verified'] is True
    assert '41164360718' in current['highlightly']['verification_reference']
    assert current['highlightly']['daily_request_budget']==100
    assert current['highlightly']['poll_interval_minutes']==20
    assert current['highlightly']['max_pages_per_poll']==10 and current['highlightly']['max_details_per_poll']==2
    assert current['live']['coverage_window']=={'start':'08:00','end':'24:00'}
    assert all(not s['authorised'] for s in current['event_monitor']['key_slots'].values())
    assert current['event_monitor']['credential_revision']=='3'
    assert not cli.is_due('live',NOW.replace(hour=7,minute=59),current)
    assert not cli.is_due('live',NOW.replace(hour=8,minute=0),current)  # Owner paused live coverage.
    assert not cli.is_due('live',NOW.replace(hour=0,minute=0),current)


@pytest.mark.parametrize('field,value',[('verification_only',True),('account_coverage_verified',False),('rights_confirmed',False)])
def test_activated_config_still_requires_all_source_approval_gates(field,value):
    current=cli.config(ROOT/'config/facebook-feed.json')
    current['highlightly'][field]=value
    assert not cli.scores_approved(current)


def test_activated_production_still_baselines_before_any_new_meaningful_event(monkeypatch):
    current=cli.config(ROOT/'config/facebook-feed.json')
    current['highlightly']['monitor_mode']='all'  # Legacy full-list replay; selected production mode has separate tests.
    state={'posts':[],'event_api':{'groups':{'primary':{'requests':17}}}}
    old=deepcopy(state['event_api'])
    client,opener=api(current,monkeypatch,state=state)
    assert event_monitor.build(current,state,NOW,client)[0] is None
    assert len(opener.calls)==2 and state['event_api']==old
    later=NOW+timedelta(minutes=20)
    changed=row(score='2 - 0',clock=85)
    client,opener=api(current,monkeypatch,Response(envelope([changed]),97,stamp=later),Response([changed],96,stamp=later),state=state,now=later)
    post,_=event_monitor.build(current,state,later,client)
    assert post and post['event_ids'] and post['snapshot'][0]['id']=='highlightly:1'
    assert state['event_api']==old and '2–0' in post['caption']
