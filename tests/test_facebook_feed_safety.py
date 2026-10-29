"""Failure/retry and evidence regressions for the isolated feed engine."""
from datetime import datetime,timedelta
import hashlib
import json
import os
from pathlib import Path
import pytest
from facebook_feed import cli,content,policy,provider,publisher,storage
from test_facebook_feed import NOW,ROOT,source,post,raw_match,Response
from types import SimpleNamespace
from email.utils import format_datetime
from datetime import timezone


@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def prepared(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true');monkeypatch.setenv('GITHUB_RUN_ID','999');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    cfg['enabled']=True;cfg['dry_run']=False
    configuration=tmp_path/'config.json';storage.write(configuration,cfg)
    now=datetime.now(content.SAST);p=post();p['expires_at']=(now+timedelta(minutes=5)).isoformat()
    state={'schema':1,'posts':[]};entry=policy.reserve(p,state,now);entry['run_key']='999-1'
    storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[p])
    return ['send','--publish','--checkpoint','--config',str(configuration),'--work',str(tmp_path)]


@pytest.mark.parametrize('failure',['send','verify'])
def test_ambiguous_mutation_survives_restart_without_automatic_resend(tmp_path,monkeypatch,cfg,failure):
    args=prepared(tmp_path,monkeypatch,cfg);calls=[]
    class Page:
        def send(self,plan):
            calls.append('send')
            if failure=='send':raise publisher.PublishError('ambiguous')
            return '123_456'
        def verify(self,*a):raise publisher.PublishError('not yet confirmed')
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(args)==1
    entry=json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]
    assert entry['status']=='unknown'
    if failure=='verify':assert entry['post_id']=='123_456'
    with pytest.raises(ValueError,match='ownership'):cli.main(args)
    assert calls==['send']


def test_expired_plan_is_cancelled_without_any_meta_request(tmp_path,monkeypatch,cfg):
    args=prepared(tmp_path,monkeypatch,cfg)
    plans=json.loads((tmp_path/'plans.json').read_text());plans[0]['expires_at']=(datetime.now(content.SAST)-timedelta(seconds=1)).isoformat()
    storage.write(tmp_path/'plans.json',plans)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('expired plan contacted Facebook'))
    assert cli.main(args)==0
    assert json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]['status']=='cancelled'


def test_caption_cannot_change_after_durable_reservation(tmp_path,monkeypatch,cfg):
    args=prepared(tmp_path,monkeypatch,cfg);plans=json.loads((tmp_path/'plans.json').read_text());plans[0]['caption']='Different content'
    storage.write(tmp_path/'plans.json',plans)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('changed plan contacted Facebook'))
    with pytest.raises(ValueError,match='does not match'):cli.main(args)


def test_unresolved_reservations_do_not_disappear_with_history_retention(cfg):
    state={'posts':[]};entry=policy.reserve(post(),state,NOW-timedelta(days=90));entry['status']='unknown'
    assert policy.history(state,NOW,28)==[entry]
    assert not policy.allowed(post(),state,NOW,cfg)[0]


def test_daily_community_and_weekly_feature_limits_cannot_be_bypassed_by_different_keys(cfg):
    state={'posts':[]};policy.reserve(post(),state,NOW-timedelta(hours=3))
    assert policy.allowed(post(key='different-key'),state,NOW,cfg)[1]=='daily community cap'
    policy.reserve(post('weekly','week-1'),state,NOW-timedelta(days=1))
    assert policy.allowed(post('weekly','week-2'),state,NOW,cfg)[1]=='weekly feature cap'


def test_weekly_excludes_conflicting_rescheduled_pair_dates(tmp_path,cfg):
    root=source(tmp_path,count=2)
    assert content.weekly(content.verified_fixtures(root,NOW,cfg),root,NOW)
    path=root/'days'/f'{NOW.date()}.json';day=json.loads(path.read_text());conflict=dict(day['fixtures'][0])
    conflict.update(id='rescheduled-id',kickoff=(NOW+timedelta(days=2)).isoformat());day['fixtures'].append(conflict);path.write_text(json.dumps(day))
    assert content.weekly(content.verified_fixtures(root,NOW,cfg),root,NOW) is None


def test_next_seven_days_includes_partial_eighth_calendar_day(tmp_path,cfg):
    root=source(tmp_path,count=2);items=content.verified_fixtures(root,NOW,cfg);extra=dict(items[0]['fixture'])
    extra.update(id='day-seven-fixture',away='New opponent',kickoff=(NOW+timedelta(days=7,hours=-1)).isoformat())
    date=content.local(extra['kickoff']).date().isoformat();storage.write(root/'days'/f'{date}.json',{'updated':NOW.isoformat(),'fixtures':[extra]})
    result=content.weekly(items,root,NOW)
    assert any(f['id']=='day-seven-fixture' for t in result['teams'] for f in t['fixtures'])


def test_editorial_competition_filter_and_cross_feature_fixture_history(tmp_path,cfg):
    root=source(tmp_path)
    first=content.verified_fixtures(root,NOW,cfg)[0]['fixture']['id'];state={'posts':[]}
    policy.reserve(content.candidate('community','prior','topic','Prior',fixture_ids=[first]),state,NOW-timedelta(hours=3))
    candidate,_=cli.build('card',root,NOW,cfg,state,preview=True)
    assert candidate['fixture_ids']!=[first]
    cfg['editorial_competitions']=[{'country':'South Africa','names':['Premiership']}]
    assert content.verified_fixtures(root,NOW,cfg)==[]


def test_free_plan_is_verified_before_coverage_catalog(monkeypatch,cfg):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic');calls=[]
    def open(req,**kw):
        calls.append(req.full_url)
        return Response({'response':{'subscription':{'plan':'Pro','active':True}}},{'Date':format_datetime(NOW.astimezone(timezone.utc))})
    client=provider.APIFootball(cfg,{},NOW,opener=SimpleNamespace(open=open))
    with pytest.raises(provider.ProviderError,match='Free'):client.coverage()
    assert len(calls)==1 and calls[0].endswith('/status')


def test_actual_account_header_usage_caps_shared_key_across_namespaces(monkeypatch,cfg):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic');calls=[]
    def open(req,**kw):
        calls.append(req.full_url)
        return Response({'response':{'subscription':{'plan':'Free','active':True},'requests':{'current':90}}},
            {'Date':format_datetime(NOW.astimezone(timezone.utc)),'x-ratelimit-requests-remaining':'10'})
    client=provider.APIFootball(cfg,{},NOW,opener=SimpleNamespace(open=open))
    with pytest.raises(provider.ProviderError,match='budget'):client.fixtures()
    assert len(calls)==1


def test_stale_cache_is_not_reused_just_because_poll_interval_is_twenty_minutes(monkeypatch,cfg):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic');calls=[]
    state={'provider':{'utc_date':NOW.astimezone(timezone.utc).date().isoformat(),'requests':1,'plan_checked':NOW.astimezone(timezone.utc).date().isoformat(),
        'cache':{'at':(NOW-timedelta(minutes=19)).isoformat(),'matches':[]}}}
    def open(req,**kw):
        calls.append(req.full_url)
        return Response({'response':[raw_match()]},{'Date':format_datetime(NOW.astimezone(timezone.utc))})
    client=provider.APIFootball(cfg,state,NOW,opener=SimpleNamespace(open=open))
    assert client.fixtures()[0] and len(calls)==1


def test_impossible_elapsed_status_and_frozen_match_age_are_rejected():
    value=raw_match();value['fixture']['date']=(NOW-timedelta(hours=5)).isoformat()
    assert provider.normalize(value,NOW) is None
    value=raw_match();value['fixture']['status'].update(short='1H',elapsed=80)
    assert provider.normalize(value,NOW) is None


def test_h2h_excludes_unknown_and_friendly_competitions():
    row={'date':'2026-10-25','home':'H','away':'A','hg':1,'ag':0,'league':'Friendly'}
    assert not content.h2h_rows({'home':'H','away':'A','h2h':[row]},NOW)
    row['league']='League';assert len(content.h2h_rows({'home':'H','away':'A','h2h':[row]},NOW))==1


def test_graph_http_failure_redacts_reflected_credential(monkeypatch):
    from urllib.error import HTTPError
    import io
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic-sensitive')
    count=[]
    def open(req,**kw):
        count.append(req)
        if len(count)==1:return Response({'id':'123'})
        body=json.dumps({'error':{'code':190,'message':'Credential synthetic-sensitive at https://example.invalid/?token=synthetic-sensitive'}}).encode()
        raise HTTPError(req.full_url,401,'rejected',{},io.BytesIO(body))
    client=publisher.PageFeed(SimpleNamespace(open=open))
    with pytest.raises(publisher.PublishError) as error:client.send({'caption':'Hello'})
    assert 'synthetic-sensitive' not in str(error.value) and 'example.invalid' not in str(error.value)


def test_existing_reel_schedule_renderer_publisher_and_music_are_byte_identical_to_audit_baseline():
    # Hash-pinned at the audited base, not regenerated by the implementation or CI.
    baseline=json.loads((ROOT/'tests/fixtures/facebook-feed-reel-invariants.json').read_text())
    for name,digest in baseline.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name


def test_frozen_in_play_snapshot_is_suppressed_even_when_http_fetch_is_new(tmp_path,monkeypatch,cfg):
    from test_facebook_feed import match
    m=match();fingerprint=json.dumps([m['status'],m['elapsed'],m['home_goals'],m['away_goals']],sort_keys=True)
    state={'posts':[],'score_observations':{m['id']:{'fingerprint':fingerprint,'since':(NOW-timedelta(minutes=40)).isoformat()}}}
    monkeypatch.setattr(cli,'APIFootball',lambda *a:SimpleNamespace(fixtures=lambda:([m],NOW.isoformat())))
    assert cli.build('live',tmp_path,NOW,cfg,state,preview=True)[0] is None


def test_safety_switches_reject_truthy_false_strings(tmp_path,cfg):
    cfg['enabled']='false';storage.write(tmp_path/'config.json',cfg)
    with pytest.raises(ValueError,match='booleans'):cli.config(tmp_path/'config.json')


def test_operator_recovery_verifies_existing_post_without_creating_one(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('GH_READ_TOKEN','synthetic');state={'posts':[]};entry=policy.reserve(post(),state,NOW);entry['status']='unknown'
    monkeypatch.setattr(storage,'restore',lambda *a:state)
    calls=[]
    monkeypatch.setattr(cli,'PageFeed',lambda:SimpleNamespace(verify_hash=lambda identity,digest:calls.append((identity,digest))))
    assert cli.main(['reconcile','--reservation-key','one','--post-id','123_456','--work',str(tmp_path)])==0
    assert calls==[('123_456',entry['caption_hash'])] and entry['status']=='published'
    assert json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]['post_id']=='123_456'


def test_operator_cancellation_requires_explicit_inspected_absence(tmp_path,monkeypatch,cfg):
    monkeypatch.setenv('GH_READ_TOKEN','synthetic');state={'posts':[]};entry=policy.reserve(post(),state,NOW);entry['status']='unknown'
    monkeypatch.setattr(storage,'restore',lambda *a:state)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('cancellation contacted Meta'))
    args=['reconcile','--reservation-key','one','--cancel-reservation','--work',str(tmp_path)]
    with pytest.raises(ValueError,match='inspection'):cli.main(args)
    assert cli.main(args+['--confirm-page-inspection'])==0 and entry['status']=='cancelled'
