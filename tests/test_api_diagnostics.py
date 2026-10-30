"""Safe diagnostic replay: never real keys, API calls, Page calls or raw responses."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
import yaml
from facebook_feed import diagnostics,publisher,storage
from facebook_feed.event_provider import EventAPI,rejection_category,safe_error_fields
from test_event_monitor import NOW,Response,Opener,account,keys,cfg

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('errors,category,fields',[
    ({'token':'Your account has been suspended; synthetic-private-primary'},'account_suspended',['token']),
    ({'token':'Your account is blocked'},'account_access_restriction',['token']),
    ({'token':'IP address is not allowed'},'ip_access_restriction',['token']),
    ({'ip':'synthetic-private-primary'},'ip_access_restriction',['ip']),
    ({'token':'bad','parameters':'bad'},'mixed_authentication_rejection',['parameters','token']),
    ({'token':'bad','synthetic-private-primary':'private details'},'mixed_authentication_rejection',['other','token']),
    ({'token':'bad'},'authentication_rejected',['token']),
    ({'subscription':'bad'},'plan_or_coverage_rejection',['subscription']),
    ({'requests':'bad'},'rate_or_quota_rejection',['requests']),
    ({'timezone':'bad'},'parameter_rejection',['timezone']),
    ('synthetic-private-primary','unclassified_provider_rejection',['unstructured']),
])
def test_categories_and_field_names_never_echo_provider_values_or_unknown_fields(errors,category,fields):
    assert rejection_category(errors)==category
    assert safe_error_fields(errors)==fields
    assert 'synthetic-private' not in json.dumps([rejection_category(errors),safe_error_fields(errors)])


def test_diagnostic_identifies_slot_and_restriction_without_trying_other_accounts(cfg,monkeypatch):
    keys(monkeypatch);state={'posts':[{'status':'unknown','post_id':'123_456'}],'live_event_ledger':{'sentinel':'unchanged'}}
    before=deepcopy(state)
    opener=Opener(Response([],99,{'token':'Your account is suspended: synthetic-private-primary'}))
    api=EventAPI(cfg,state,NOW,opener);report=diagnostics.diagnose(cfg,state,NOW,api)
    assert report['outcome']=='blocked' and report['facebook_requests']==0
    assert report['reason']=='account_suspended'
    assert report['slots'][0]['http_attempted'] and not report['slots'][1]['http_attempted'] and not report['slots'][2]['http_attempted']
    rejection=next(e for e in report['events'] if e['category']=='account_suspended')
    assert rejection['slot']=='API_FOOTBALL_KEY' and rejection['endpoint']=='status'
    assert rejection['authentication_fallback_eligible'] is False
    assert state['posts']==before['posts'] and state['live_event_ledger']==before['live_event_ledger']
    assert state['event_api']['groups']['primary']['requests']==1
    assert 'synthetic-private' not in json.dumps(report) and len(opener.calls)==1


def test_diagnostic_proves_second_slot_was_used_after_first_auth_rejection(cfg,monkeypatch):
    keys(monkeypatch);state={}
    opener=Opener(Response([],99,{'token':'synthetic-private-primary'}),Response(account()),Response([],98))
    report=diagnostics.diagnose(cfg,state,NOW,EventAPI(cfg,state,NOW,opener))
    assert report['outcome']=='verified_read_only' and report['successful_slot']=='API_FOOTBALL_KEY_1'
    assert report['verified_fixture_count']==0 and report['facebook_requests']==0
    assert report['slots'][0]['http_attempted'] and report['slots'][1]['http_attempted']
    assert not report['slots'][2]['http_attempted']
    assert any(e['category']=='authentication_fallback' for e in report['events'])
    assert 'synthetic-private' not in json.dumps(report)


def test_all_rejected_and_missing_credentials_are_explicit(cfg,monkeypatch):
    keys(monkeypatch);api=EventAPI(cfg,{},NOW,Opener(*(Response([],99,{'token':'rejected'}) for _ in range(3))))
    report=diagnostics.diagnose(cfg,{},NOW,api)
    assert report['reason']=='authentication_unavailable' and all(s['http_attempted'] for s in report['slots'])
    for slot in api.keys:monkeypatch.delenv(slot)
    empty=diagnostics.diagnose(cfg,{},NOW,EventAPI(cfg,{},NOW,Opener()))
    assert not any(s['configured'] for s in empty['slots']) and empty['facebook_requests']==0


def test_diagnostic_main_preserves_production_history_and_saves_quota_even_when_blocked(cfg,tmp_path,monkeypatch,capsys):
    keys(monkeypatch);monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GH_READ_TOKEN','synthetic-gh-token')
    monkeypatch.setenv('GITHUB_OUTPUT',str(tmp_path/'outputs'))
    monkeypatch.setenv('GITHUB_STEP_SUMMARY',str(tmp_path/'summary'))
    state={'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[{'status':'unknown','key':'old'}]}
    monkeypatch.setattr(diagnostics,'config',lambda path:cfg)
    monkeypatch.setattr(storage,'restore',lambda *args:state)
    opener=Opener(Response([],99,{'token':'account suspended synthetic-private-primary'}))
    monkeypatch.setattr(diagnostics,'EventAPI',lambda cfg,state,now:EventAPI(cfg,state,NOW,opener))
    def forbidden(*args,**kwargs):raise AssertionError('No Facebook requests permitted')
    monkeypatch.setattr(publisher,'PageFeed',forbidden)
    assert diagnostics.main()==0
    saved=json.loads((tmp_path/'tmp/facebook-feed/checkpoint/state.json').read_text())
    assert saved['posts']==[{'status':'unknown','key':'old'}]
    assert saved['event_api']['groups']['primary']['requests']==1
    report=json.loads((tmp_path/'tmp/facebook-feed/api-diagnostic.json').read_text())
    assert report['reason']=='account_suspended' and report['facebook_requests']==0
    text=capsys.readouterr().out+(tmp_path/'summary').read_text()
    assert 'synthetic-private' not in text and 'synthetic-gh-token' not in text
    assert 'should_publish=true' not in (tmp_path/'outputs').read_text()


def test_diagnostic_refuses_missing_ledger_or_wrong_branch_without_probing(cfg,tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.setenv('GITHUB_REF_NAME','other')
    with pytest.raises(storage.StateError):diagnostics.main()
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GH_READ_TOKEN','synthetic')
    monkeypatch.setattr(diagnostics,'config',lambda path:cfg);monkeypatch.setattr(storage,'restore',lambda *args:None)
    def forbidden(*args):raise AssertionError('No request before ledger restoration')
    monkeypatch.setattr(diagnostics,'EventAPI',forbidden)
    with pytest.raises(storage.StateError,match='bootstrap/reset'):diagnostics.main()


def test_workflow_diagnostic_is_explicit_and_cannot_prepare_a_post():
    caller=yaml.safe_load((ROOT/'.github/workflows/facebook-live.yml').read_text())
    trigger=caller.get('on',caller.get(True))
    assert trigger['workflow_dispatch']['inputs']['diagnostic']['default'] is False
    assert trigger['schedule'][0]['cron']=='*/5 * * * *'
    assert 'inputs.diagnostic' in caller['jobs']['content']['with']['diagnostic']
    engine=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    steps=engine['jobs']['feed']['steps'];diagnostic=next(s for s in steps if s.get('id')=='diagnostic')
    assert diagnostic['if']=='inputs.diagnostic'
    assert set(diagnostic['env'])=={'GH_READ_TOKEN','API_FOOTBALL_KEY','API_FOOTBALL_KEY_1','API_FOOTBALL_KEY_2','HIGHLIGHTLY_API_KEY'}
    prepare=next(s for s in steps if s.get('id')=='prepare')
    assert '!inputs.diagnostic' in prepare['if']
    send=next(s for s in steps if s['name'].startswith('Publish or edit'))
    assert "steps.prepare.outputs.should_publish == 'true'" in send['if']
    final=next(s for s in steps if s['name']=='Save final ledger including ambiguous failures')
    assert "steps.diagnostic.conclusion == 'success'" in final['if']
    assert 'steps.diagnostic.outputs.prefix' in final['with']['name']
