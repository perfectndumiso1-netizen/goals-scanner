"""Owner-approved independent account selection; disabled account stays untouched."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from facebook_feed import cli,diagnostics
from facebook_feed.event_provider import EventAPI
from facebook_feed.provider import ProviderError
from test_event_monitor import NOW,Response,Opener,account,keys

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def cfg():
    cfg=cli.config(ROOT/'config/facebook-feed.json')
    cfg['score_source']='api-football'
    for name in ('API_FOOTBALL_KEY_1','API_FOOTBALL_KEY_2'):cfg['event_monitor']['key_slots'][name]['authorised']=True
    return cfg


def test_historical_approved_selection_keeps_disabled_original_and_groups(cfg):
    slots=cfg['event_monitor']['key_slots']
    assert slots['API_FOOTBALL_KEY']['authorised'] is False
    assert slots['API_FOOTBALL_KEY_1']['authorised'] and slots['API_FOOTBALL_KEY_2']['authorised']
    assert slots['API_FOOTBALL_KEY']['quota_group']=='primary'
    assert slots['API_FOOTBALL_KEY_1']['quota_group']=='backup-1'
    assert slots['API_FOOTBALL_KEY_2']['quota_group']=='backup-2'
    assert cfg['event_monitor']['publish_enabled'] and cfg['event_monitor']['daily_request_budget']==100


def test_normal_requests_use_approved_second_slot_and_preserve_disabled_history(cfg,monkeypatch):
    keys(monkeypatch)
    state={'event_api':{'groups':{'primary':{'utc_date':'2026-10-30','requests':17,'remaining':83}},'slots':{}},'posts':[{'status':'unknown','key':'keep'}]}
    old=deepcopy(state);opener=Opener(Response(account()),Response([{'verified':True}],98))
    assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[{'verified':True}]
    assert all(r.get_header('X-apisports-key')=='synthetic-private-secondary' for r in opener.calls)
    assert state['event_api']['groups']['primary']==old['event_api']['groups']['primary']
    assert state['posts']==old['posts']
    assert state['event_api']['last_successful_slot']=='API_FOOTBALL_KEY_1'


@pytest.mark.parametrize('error',[{'requests':'You have reached the request limit for the day'},{'token':'rejected'}])
def test_approved_secondary_can_fail_over_to_approved_third(cfg,monkeypatch,error):
    keys(monkeypatch);opener=Opener(Response([],0,error),Response(account()),Response([],98))
    state={};assert EventAPI(cfg,state,NOW,opener).get('fixtures')==[]
    assert [r.get_header('X-apisports-key') for r in opener.calls]==['synthetic-private-secondary']+['synthetic-private-third']*2
    assert 'primary' not in state['event_api']['groups']
    assert state['event_api']['last_successful_slot']=='API_FOOTBALL_KEY_2'


def test_new_restriction_on_approved_account_is_not_bypassed(cfg,monkeypatch):
    keys(monkeypatch);opener=Opener(Response([],99,{'access':'account suspended'}))
    with pytest.raises(ProviderError):EventAPI(cfg,{},NOW,opener).get('fixtures')
    assert len(opener.calls)==1 and opener.calls[0].get_header('X-apisports-key')=='synthetic-private-secondary'


def test_status_verification_makes_exactly_one_status_request(cfg,monkeypatch):
    keys(monkeypatch);opener=Opener(Response(account()))
    api=EventAPI(cfg,{},NOW,opener)
    assert api.get('status')==account()
    assert len(opener.calls)==1 and opener.calls[0].full_url.endswith('/status')
    assert api.active=='API_FOOTBALL_KEY_1'


def test_diagnostic_verifies_both_approved_accounts_without_fixture_or_page_calls(cfg,monkeypatch):
    keys(monkeypatch);state={'posts':[{'status':'unknown'}]}
    real_api=EventAPI;openers=[]
    def api_factory(probe,state,now):
        opener=Opener(Response(account()));openers.append(opener)
        return real_api(probe,state,now,opener)
    monkeypatch.setattr(diagnostics,'EventAPI',api_factory)
    report=diagnostics.diagnose_accounts(cfg,state,NOW)
    assert report['outcome']=='verified_read_only' and report['facebook_requests']==0
    assert report['successful_slots']==['API_FOOTBALL_KEY_1','API_FOOTBALL_KEY_2']
    assert report['slots'][0]['outcome']=='disabled' and not report['slots'][0]['http_attempted']
    assert [o.calls[0].get_header('X-apisports-key') for o in openers]==['synthetic-private-secondary','synthetic-private-third']
    assert all(len(o.calls)==1 and o.calls[0].full_url.endswith('/status') for o in openers)
    assert 'primary' not in state['event_api']['groups'] and state['posts']==[{'status':'unknown'}]
    assert 'synthetic-private' not in json.dumps(report)


def test_diagnostic_stops_if_an_approved_account_returns_a_new_access_restriction(cfg,monkeypatch):
    keys(monkeypatch);opener=Opener(Response([],99,{'access':'account suspended'}))
    monkeypatch.setattr(diagnostics,'EventAPI',lambda probe,state,now:EventAPI(probe,state,now,opener))
    report=diagnostics.diagnose_accounts(cfg,{},NOW)
    assert report['reason']=='account_suspended' and report['outcome']=='blocked'
    assert report['slots'][2]['reason']=='previous_policy_stop' and not report['slots'][2]['http_attempted']
    assert len(opener.calls)==1


def test_missing_preferred_approved_key_can_use_remaining_approved_slot(cfg,monkeypatch):
    keys(monkeypatch);monkeypatch.delenv('API_FOOTBALL_KEY_1')
    opener=Opener(Response(account()),Response([],98))
    assert EventAPI(cfg,{},NOW,opener).get('fixtures')==[]
    assert all(r.get_header('X-apisports-key')=='synthetic-private-third' for r in opener.calls)


def test_final_permitted_status_response_is_valid_and_no_101st_call(cfg,monkeypatch):
    keys(monkeypatch);cfg['event_monitor']['key_slots']['API_FOOTBALL_KEY_2']['authorised']=False
    state={'event_api':{'groups':{'backup-1':{'utc_date':'2026-10-30','requests':99,'remaining':1,'allocation':100,'plan_checked':'2026-10-30'}},'slots':{'API_FOOTBALL_KEY_1':{'revision':'3','plan_checked':'2026-10-30'}}}}
    response=account();response['requests']['current']=100
    opener=Opener(Response(response,0));api=EventAPI(cfg,state,NOW,opener)
    assert api.get('status')==response
    assert state['event_api']['groups']['backup-1']['requests']==100
    with pytest.raises(ProviderError):api.get('status')
    assert len(opener.calls)==1


def test_status_audit_respects_known_local_reserve(cfg,monkeypatch):
    keys(monkeypatch);cfg['event_monitor']['daily_request_reserve']=10
    state={'event_api':{'groups':{'backup-1':{'utc_date':'2026-10-30','requests':90,'remaining':10,'allocation':100}},'slots':{}}}
    opener=Opener();api=EventAPI(cfg,state,NOW,opener)
    with pytest.raises(ProviderError):api.get('status')
    assert opener.calls==[] and api.diagnostics[-1]['category']=='local_request_ceiling'


@pytest.mark.parametrize('error,expected',[({'token':'rejected'},'partially_verified'),({'requests':'You have reached the request limit for the day'},'partially_verified')])
def test_account_audit_continues_only_after_allowed_failures(cfg,monkeypatch,error,expected):
    keys(monkeypatch);responses=[Response([],0,error),Response(account())];openers=[]
    def factory(probe,state,now):
        opener=Opener(responses.pop(0));openers.append(opener)
        return EventAPI(probe,state,now,opener)
    monkeypatch.setattr(diagnostics,'EventAPI',factory)
    report=diagnostics.diagnose_accounts(cfg,{},NOW)
    assert report['outcome']==expected and report['successful_slots']==['API_FOOTBALL_KEY_2']
    assert all(len(o.calls)==1 and o.calls[0].full_url.endswith('/status') for o in openers)


def test_current_production_excludes_all_owner_confirmed_suspended_accounts():
    cfg=cli.config(ROOT/"config/facebook-feed.json")
    assert cfg["score_source"]=="highlightly"
    assert all(not slot["authorised"] for slot in cfg["event_monitor"]["key_slots"].values())
    assert not cfg["highlightly"]["verification_only"] and cli.scores_approved(cfg)
