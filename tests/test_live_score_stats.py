"""Synthetic offline contracts, not evidence of account coverage/rights or Page publication."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from facebook_feed import cli, content, policy, provider, storage
from facebook_feed.live_window import in_window, eligible_kickoff, app_candidates, match_app_coverage
from test_facebook_feed import NOW, Response, raw_match

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    cfg=cli.config(ROOT / 'config/facebook-feed.json')
    # Historical live replay, independently of the paused production config.
    cfg['live']['enabled']=True
    cfg['event_monitor'].update(enabled=True,publish_enabled=True)
    cfg['authorized_kinds']=['live','results']
    cfg['score_source']='api-football'
    cfg['event_monitor']['mode']='legacy'  # Legacy adapter regression fixture.
    cfg['live'].update(max_posts_per_day=3,publish_every_poll=False,image_required=False)
    cfg['live_post_cooldown_minutes']=60
    return cfg


def raw():
    value = raw_match()
    value['teams']['home']['id'] = 10
    value['teams']['away']['id'] = 20
    return value


def stats():
    return [dict(team={'id': identifier, 'name': name}, statistics=[
        {'type': 'Corner Kicks', 'value': corners}, {'type': 'Yellow Cards', 'value': 1},
        {'type': 'Red Cards', 'value': 0}, {'type': 'Ball Possession', 'value': possession},
        {'type': 'Shots on Goal', 'value': 2}, {'type': 'Total Shots', 'value': 5},
        {'type': 'Fouls', 'value': 4}, {'type': 'Offsides', 'value': None},
    ]) for identifier, name, corners, possession in [(10, 'Arsenal', 4, '60%'), (20, 'Tottenham', 2, '40%')]]


def publication(tmp_path, kickoff=None):
    fixture = dict(id='app-original-id', home='Arsenal', away='Tottenham', time_known=True,
                   kickoff=(kickoff or NOW-timedelta(hours=1)).isoformat())
    storage.write(tmp_path/'latest.json', {'meta': {'generated': NOW.isoformat()}, 'fixtures': [fixture]})
    return fixture


def client(cfg, monkeypatch, responses=None, state=None, now=NOW):
    monkeypatch.setenv('API_FOOTBALL_KEY', 'synthetic-test-only')
    calls=[]
    responses=list(responses if responses is not None else [stats()])
    day=now.astimezone(timezone.utc).date().isoformat()
    state=state if state is not None else {'provider': {'utc_date': day, 'requests': 2, 'plan_checked': day}}
    def open(req, **kwargs):
        calls.append(req)
        value=responses.pop(0)
        if isinstance(value, Exception):raise value
        return Response({'response': value}, {'Date': format_datetime(now.astimezone(timezone.utc))})
    return provider.APIFootball(cfg,state,now,opener=SimpleNamespace(open=open)), calls


def test_production_config_limits_and_approvals(cfg):
    assert cfg['score_source']=='api-football'
    assert cfg['provider']['poll_interval_minutes']==10
    assert cfg['provider']['daily_request_budget']==90
    assert cfg['provider']['statistics_daily_request_budget']==6
    assert cfg['provider']['statistics_max_matches_per_update']==2
    assert cfg['live']['app_coverage_only']
    assert cfg['live']['coverage_window']=={'start':'08:00','end':'24:00'}
    assert cli.scores_approved(cfg) and not cfg['live']['edit_existing']
    assert not cfg['app_scores']['rights_confirmed'] and not cfg['app_scores']['coverage_verified']
    assert set(cfg['authorized_kinds'])=={'live','results'}


@pytest.mark.parametrize('hour,minute,expected',[(0,0,False),(7,59,False),(8,0,True),(23,59,True)])
def test_window_and_delayed_run_safety(cfg,hour,minute,expected):
    now=NOW.replace(hour=hour,minute=minute)
    assert in_window(now,cfg)==expected
    assert in_window(now.astimezone(timezone.utc),cfg)==expected
    assert cli.is_due('live',now,cfg)==expected


@pytest.mark.parametrize('hour,minute,expected',[(0,0,False),(7,59,False),(8,0,True),(23,59,True)])
def test_overnight_kickoffs_excluded_entirely(cfg,hour,minute,expected):
    assert eligible_kickoff(NOW.replace(hour=hour,minute=minute),NOW,cfg)==expected
    assert not eligible_kickoff(NOW-timedelta(days=1),NOW,cfg)


def test_coverage_is_fresh_exact_and_only_current_candidates(tmp_path,cfg):
    fixture=publication(tmp_path)
    assert app_candidates(tmp_path,NOW,cfg)==[fixture]
    match=provider.normalize(raw(),NOW)
    assert match_app_coverage([match],[fixture])[0]['fixture_id']=='app-original-id'
    assert not match_app_coverage([match,dict(match,id='124')],[fixture])
    assert not match_app_coverage([match],[fixture,fixture])
    assert not match_app_coverage([dict(match,home='Other')],[fixture])
    assert not match_app_coverage([dict(match,kickoff=(NOW-timedelta(minutes=59)).isoformat())],[fixture])
    assert not match_app_coverage([dict(match,home=match['away'],away=match['home'])],[fixture])
    publication(tmp_path,NOW.replace(hour=7))
    assert app_candidates(tmp_path,NOW,cfg)==[]
    publication(tmp_path,NOW+timedelta(hours=1))
    assert app_candidates(tmp_path,NOW,cfg)==[]
    with pytest.raises(provider.ProviderError,match='coverage'):
        app_candidates(tmp_path,NOW+timedelta(days=1),cfg)


@pytest.mark.parametrize('case',['overnight','no-match','overnight-kickoff'])
def test_preview_cannot_spend_requests_outside_coverage(tmp_path,monkeypatch,cfg,case):
    publication(tmp_path,NOW.replace(hour=7) if case=='overnight-kickoff' else NOW+timedelta(hours=1))
    monkeypatch.setattr(cli,'APIFootball',lambda *a:pytest.fail('No provider call allowed'))
    now=NOW.replace(hour=7) if case=='overnight' else NOW
    assert cli.build('live',tmp_path,now,cfg,{},preview=True)[0] is None


def test_normalized_stats_preserve_zero_and_never_invent_missing():
    match=provider.normalize(raw(),NOW)
    parsed=provider.normalize_statistics(stats(),match)
    assert parsed['corners']==[4,2] and parsed['red_cards']==[0,0]
    assert parsed['possession']==[60,40]
    assert 'offsides' not in parsed
    bad=stats();bad[0]['statistics'][0]['value']=None
    assert 'corners' not in provider.normalize_statistics(bad,match)


@pytest.mark.parametrize('value',[None,True,-1,'unknown','4.5',float('nan'),{'value':2}])
def test_invalid_count_is_omitted_not_coerced(value):
    rows=stats();rows[0]['statistics'][0]['value']=value
    assert 'corners' not in provider.normalize_statistics(rows,provider.normalize(raw(),NOW))


@pytest.mark.parametrize('value',['140%','NaN%','60','-2%','20%',None,True])
def test_invalid_or_inconsistent_possession_is_omitted(value):
    rows=stats();rows[0]['statistics'][3]['value']=value
    assert 'possession' not in provider.normalize_statistics(rows,provider.normalize(raw(),NOW))


def test_stats_require_exact_unique_team_identity_and_metrics():
    match=provider.normalize(raw(),NOW)
    for rows in [None,[],[{}], [{'team':[]},{}], [stats()[0],stats()[0]]]:
        assert provider.normalize_statistics(rows,match)=={}
    rows=stats();rows[0]['team']['name']='Other'
    assert provider.normalize_statistics(rows,match)=={}
    rows=stats();rows[0]['statistics'].append({'type':'Corner Kicks','value':99})
    assert 'corners' not in provider.normalize_statistics(rows,match)
    rows=stats();rows[0]['statistics'].append({'type':[],'value':'bad'})
    assert provider.normalize_statistics(rows,match)['corners']==[4,2]


def test_stats_are_optional_cached_and_counted_inside_shared_budget(cfg,monkeypatch):
    api,calls=client(cfg,monkeypatch)
    match=provider.normalize(raw(),NOW)
    enriched=api.enrich_statistics([match])[0]
    assert enriched['statistics']['corners']==[4,2]
    assert api.budget['requests']==3 and api.budget['statistics_requests']==1
    assert calls[0].full_url.endswith('fixtures/statistics?fixture=123')
    assert 'synthetic-test-only' not in calls[0].full_url
    assert api.enrich_statistics([match])[0]['statistics']==enriched['statistics']
    assert len(calls)==1
    api.now=NOW+timedelta(minutes=6);api.budget['statistics_requests']=6
    assert 'statistics' not in api.enrich_statistics([enriched])[0]  # no stale input/cache reuse
    assert len(calls)==1


@pytest.mark.parametrize('requests,stats_requests',[(88,0),(90,0),(2,6)])
def test_auxiliary_requests_never_consume_reserve(cfg,monkeypatch,requests,stats_requests):
    api,calls=client(cfg,monkeypatch)
    api.budget.update(requests=requests,statistics_requests=stats_requests)
    assert 'statistics' not in api.enrich_statistics([provider.normalize(raw(),NOW)])[0]
    assert not calls


def test_at_most_two_stats_calls_per_post(cfg,monkeypatch):
    api,calls=client(cfg,monkeypatch,[stats(),stats()])
    matches=[dict(provider.normalize(raw(),NOW),id=str(i)) for i in range(4)]
    assert sum('statistics' in m for m in api.enrich_statistics(matches))==2
    assert len(calls)==2


def test_provider_error_on_stats_keeps_score_without_fabricated_fields(cfg,monkeypatch):
    error=HTTPError('https://example.invalid',503,'unavailable',{'Retry-After':'1200'},None)
    api,calls=client(cfg,monkeypatch,[error])
    match=provider.normalize(raw(),NOW)
    result=api.enrich_statistics([match])[0]
    assert result['home_goals']==1 and 'statistics' not in result
    assert api.budget['statistics_requests']==1 and len(calls)==1
    assert content.local(api.budget['retry_after'])==NOW+timedelta(minutes=20)


def test_failed_fixture_attempt_waits_ten_minutes_and_never_posts_old_cache(cfg,monkeypatch):
    api,calls=client(cfg,monkeypatch,[OSError('private network details')])
    with pytest.raises(provider.ProviderError):api.fixtures()
    with pytest.raises(provider.ProviderError,match='poll'):api.fixtures()
    assert len(calls)==1


def test_fixture_cache_contains_only_verified_app_coverage(cfg,monkeypatch,tmp_path):
    fixture=publication(tmp_path)
    unrelated=raw();unrelated['fixture']['id']=456;unrelated['teams']['home']['name']='Other'
    api,calls=client(cfg,monkeypatch,[[raw(),unrelated]])
    matches,_=api.fixtures(coverage=[fixture])
    assert len(matches)==1 and matches[0]['fixture_id']==fixture['id']
    assert api.budget['cache']['matches']==matches
    assert not api.fixtures(coverage=[dict(fixture,home='Changed')])[0]
    assert len(calls)==1


def test_emoji_caption_stats_and_no_stats_only_spam(cfg):
    match=dict(provider.normalize(raw(),NOW),fixture_id='app-id',source='api-football',
               statistics=provider.normalize_statistics(stats(),provider.normalize(raw(),NOW)),statistics_at=NOW.isoformat())
    post=policy.score_post([match],{'posts':[]},NOW,cfg)
    assert post['caption'].startswith('Live Matches SAST\n') and '⏸ HT | Arsenal 1–0 Tottenham' in post['caption']
    for line in ['🚩 Corners 4–2','🟨 Yellow 1–1','🟥 Red 0–0',
                 '📊 Possession 60%–40%','🎯 On target 2–2','🥅 Shots 5–5','⚠️ Fouls 4–4']:
        assert line in post['caption']
    assert '🚫 Offsides' not in post['caption']
    state={'posts':[]};entry=policy.reserve(post,state,NOW);entry.update(status='published',post_id='123_456')
    changed=deepcopy(match);changed['statistics']['corners']=[5,2]
    assert policy.score_post([changed],state,NOW+timedelta(minutes=10),cfg) is None
    assert policy.score_post([dict(changed,home_goals=2)],state,NOW+timedelta(minutes=10),cfg)
    assert '📈 Match stats' not in policy.score_post([dict(match,statistics={})],{'posts':[]},NOW,cfg)['caption']


def test_build_enriches_matched_scores_and_preserves_app_fixture_ids(tmp_path,monkeypatch,cfg):
    publication(tmp_path)
    match=provider.normalize(raw(),NOW)
    calls=[]
    def enrich(matches):
        calls.append(matches)
        return [dict(m,statistics={'corners':[4,2]},statistics_at=NOW.isoformat()) for m in matches]
    monkeypatch.setattr(cli,'APIFootball',lambda *a:SimpleNamespace(
        fixtures=lambda **kw:([match],NOW.isoformat()),enrich_statistics=enrich))
    post,_=cli.build('live',tmp_path,NOW,cfg,{'posts':[]},preview=True)
    assert post['fixture_ids']==['app-original-id'] and '🚩 Corners 4–2' in post['caption']
    assert len(calls)==1
    # Unchanged type caps/cooldowns stop optional spend too.
    state={'posts':[]};entry=policy.reserve(post,state,NOW);entry.update(status='published',post_id='1_2')
    match['home_goals']=2
    cli.build('live',tmp_path,NOW,cfg,state,preview=True)
    assert len(calls)==1


def test_midnight_send_cancels_before_any_page_request(tmp_path,monkeypatch,cfg):
    cfg['provider']['rights_confirmed']=cfg['provider']['account_coverage_verified']=True
    now=datetime.now(content.SAST)
    post=content.candidate('live','key','topic','verified',expires_at=(now+timedelta(minutes=5)).isoformat())
    state={'posts':[]};entry=policy.reserve(post,state,now);entry['run_key']='1-1'
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    monkeypatch.setenv('GITHUB_RUN_ID','1');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setattr(cli,'in_window',lambda *a:False)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No overnight Page request'))
    assert cli.main(['send','--kind','live','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    assert content.load(tmp_path/'checkpoint/state.json')['posts'][0]['status']=='cancelled'


@pytest.mark.parametrize('minutes',[-6,3])
def test_stale_or_future_http_statistics_are_not_presented_as_current(cfg,monkeypatch,minutes):
    api,calls=client(cfg,monkeypatch)
    api.opener=SimpleNamespace(open=lambda *a,**k:Response({'response':stats()},
        {'Date':format_datetime((NOW+timedelta(minutes=minutes)).astimezone(timezone.utc))}))
    assert 'statistics' not in api.enrich_statistics([provider.normalize(raw(),NOW)])[0]


def test_unsafe_optional_budgets_and_empty_window_fail_closed(tmp_path,cfg):
    for section,key,value in [('provider','statistics_daily_request_budget',7),
                              ('provider','statistics_max_matches_per_update',3),
                              ('provider','statistics_enabled','true'),
                              ('provider','poll_interval_minutes',9),
                              ('live','coverage_window',{})]:
        altered=deepcopy(cfg);altered[section][key]=value
        storage.write(tmp_path/'config.json',altered)
        with pytest.raises(ValueError):cli.config(tmp_path/'config.json')


def test_source_change_before_send_cannot_borrow_another_provider_approval(tmp_path,monkeypatch,cfg):
    cfg['provider']['rights_confirmed']=cfg['provider']['account_coverage_verified']=True
    now=datetime.now(content.SAST)
    post=content.candidate('live','key','topic','old source',snapshot=[{'source':'app'}],
                           expires_at=(now+timedelta(minutes=5)).isoformat())
    state={'posts':[]};entry=policy.reserve(post,state,now);entry['run_key']='1-1'
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    monkeypatch.setenv('GITHUB_RUN_ID','1');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('Changed source must not reach Page'))
    assert cli.main(['send','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    assert content.load(tmp_path/'checkpoint/state.json')['posts'][0]['status']=='cancelled'


def test_reported_terminal_fixture_and_daily_cap_stop_unnecessary_polling(tmp_path,monkeypatch,cfg):
    publication(tmp_path)
    monkeypatch.setattr(cli,'APIFootball',lambda *a:pytest.fail('No unnecessary provider request'))
    match=dict(provider.normalize(raw(),NOW),status='FT',source='api-football')
    state={'posts':[{'kind':'live','status':'published','at':NOW.isoformat(),'snapshot':[match]}]}
    assert cli.build('live',tmp_path,NOW,cfg,state)[0] is None
    state={'posts':[{'kind':'live','status':'published','at':NOW.isoformat()} for _ in range(3)]}
    assert cli.build('live',tmp_path,NOW,cfg,state)[0] is None


@pytest.mark.parametrize('approval',['rights_confirmed','account_coverage_verified'])
def test_revoking_either_approval_blocks_scheduled_publishing(tmp_path,monkeypatch,cfg,approval):
    cfg['provider'][approval]=False
    assert not cli.scores_approved(cfg)
    storage.write(tmp_path/'config.json',cfg)
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setattr(cli,'build',lambda *a,**k:pytest.fail('Revoked approval must block before API or Page access'))
    assert cli.main(['prepare','--kind','live','--publish','--config',str(tmp_path/'config.json'),
                     '--work',str(tmp_path/'work')])==0
    assert content.load(tmp_path/'work/report.json')[0]['status']=='blocked'
