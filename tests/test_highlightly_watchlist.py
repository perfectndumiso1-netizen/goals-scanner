"""Synthetic selected-league schedules only; never real provider/Page requests."""
from copy import deepcopy
from datetime import timedelta,timezone
import json
from pathlib import Path
import pytest
from facebook_feed import cli,highlightly,event_monitor,match_events,storage
from facebook_feed.highlightly_watchlist import LEAGUES,choose,league_key,metadata,poll,summary
from facebook_feed.provider import ProviderError
from test_event_monitor import NOW,Opener
from test_highlightly import Response,envelope,row

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def cfg():
    value=cli.config(ROOT/'config/facebook-feed.json')
    value['live']['enabled']=True
    value['event_monitor'].update(enabled=True,publish_enabled=True)
    value['authorized_kinds']=['live','results']
    return value


def game(mid=1,league='psl',at=None,status='Second half',score='1 - 0',clock=65):
    value=row(mid,status,score,clock)
    label,country,aliases=LEAGUES[league]
    value.update(league={'id':100+list(LEAGUES).index(league),'name':aliases[0]},country={'name':country})
    value['homeTeam'].update(id=mid*100+10,name=f'Synthetic Home {mid}')
    value['awayTeam'].update(id=mid*100+20,name=f'Synthetic Away {mid}')
    if at:value['date']=at.isoformat()
    return value


class FakeAPI:
    def __init__(self,rows,now=NOW,details=None):
        self.rows=rows;self.now=now;self.at=now.isoformat();self.calls=[]
        self.budget={'requests':0,'remaining':100,'plan_verified_at':None}
        self.details={f'highlightly:{r["id"]}':r for r in rows} if details is None else details
    def matches(self):
        self.calls.append('catalog');self.budget['requests']+=1;self.budget['remaining']-=1
        if isinstance(self.rows,Exception):raise self.rows
        self.budget['plan_verified_at']=self.at
        return deepcopy(self.rows)
    def detail(self,key):
        self.calls.append(key);self.budget['requests']+=1;self.budget['remaining']-=1
        value=self.details[key]
        if isinstance(value,Exception):raise value
        return highlightly.observation(deepcopy(value),self.now)


@pytest.mark.parametrize('key',list(LEAGUES))
def test_all_six_exact_country_scoped_leagues(key):
    m=metadata(game(league=key,at=NOW+timedelta(hours=1),status='Not started',score=None,clock=None),NOW)
    assert m and m['league']==key and m['id']=='highlightly:1'
    assert 'score' not in m and 'events' not in m and 'status' not in m


@pytest.mark.parametrize('name,country',[
    ('Bundesliga','Austria'),('Premier League','South Africa'),('Serie A','Brazil'),
    ('Ligue 2','France'),('Premier League 2','England'),('Premier League Women','England'),
    ('LaLiga 2','Spain'),('FA Cup','England'),('Champions League','Europe'),
])
def test_near_names_other_countries_cups_and_lower_divisions_are_excluded(name,country):
    assert league_key(name,country) is None


def test_aliases_and_accents_are_exact_not_substrings():
    assert league_key('Primera División','Spain')=='laliga'
    assert league_key('Betway Premiership','South Africa')=='psl'
    assert league_key('Ligue 1 McDonald’s','France')=='ligue1'
    assert league_key('2. Bundesliga','Germany') is None


def test_future_schedule_retained_when_live_normalizer_cannot_use_it():
    value=game(at=NOW+timedelta(hours=2),status='Not started',score=None,clock=None)
    assert highlightly.observation(value,NOW) is None
    assert metadata(value,NOW)['kickoff']==(NOW+timedelta(hours=2)).isoformat()


@pytest.mark.parametrize('change', ['wrong_day','before_08','finished','unknown','very_old'])
def test_ineligible_calendar_entries(change):
    value=game()
    if change=='wrong_day':value['date']=(NOW+timedelta(days=1)).isoformat()
    if change=='before_08':value['date']=NOW.replace(hour=7).isoformat()
    if change=='finished':value['state']['description']='Finished'
    if change=='unknown':value['state']['description']='Unknown'
    if change=='very_old':value['date']=(NOW-timedelta(hours=7)).isoformat()
    assert metadata(value,NOW) is None


def test_psl_representation_daily_cap_and_foreign_rotation():
    candidates=[metadata(game(i+1,key),NOW) for i,key in enumerate(LEAGUES)]
    roster=choose(candidates,{},NOW)
    assert len(roster)==5 and 'psl' in {m['league'] for m in roster.values()}
    assert len({m['league'] for m in roster.values()})==5
    assert choose(list(reversed(candidates)),{},NOW)==roster
    tomorrow=choose(candidates,{},NOW+timedelta(days=1))
    assert {m['league'] for m in tomorrow.values()}!={m['league'] for m in roster.values()}
    finished={k:dict(v,confirmed_status='FT') for k,v in roster.items()}
    assert choose(candidates,finished,NOW)==finished  # Never recycle the five daily slots.


def test_choose_prefers_staggered_options_within_a_league():
    psl=metadata(game(1,'psl',at=NOW),NOW)
    same=metadata(game(2,'epl',at=NOW),NOW)
    staggered=metadata(game(3,'epl',at=NOW+timedelta(hours=3),status='Not started'),NOW)
    roster=choose([psl,same,staggered],{},NOW,2)
    assert set(roster)=={'highlightly:1','highlightly:3'}


def test_cached_schedule_and_targeted_details_replace_repeated_full_downloads(cfg):
    state={'posts':[]};api=FakeAPI([game()])
    assert poll(cfg,state,NOW,api)[0]
    assert api.calls==['catalog','highlightly:1']
    before=deepcopy(state['highlightly_watchlist']['selected'])
    later=NOW+timedelta(minutes=20);api.now=later;api.at=later.isoformat()
    api.details['highlightly:1']['state']['clock']=85
    assert poll(cfg,state,later,api)[0]
    assert api.calls==['catalog','highlightly:1','highlightly:1']
    assert len(state['highlightly_watchlist']['selected'])==1
    assert state['highlightly_watchlist']['selected']['highlightly:1']['id']==before['highlightly:1']['id']
    assert not state['live_event_ledger']['events']


def test_selection_baselines_then_only_fresh_selected_changes_post(cfg):
    state={'posts':[]};api=FakeAPI([game()])
    assert event_monitor.build(cfg,state,NOW,api)[0] is None
    later=NOW+timedelta(minutes=20);api.now=later;api.at=later.isoformat()
    api.details['highlightly:1']['state'].update(clock=85,score={'current':'2 - 0'})
    post,_=event_monitor.build(cfg,state,later,api)
    assert post and 'SELECTED MATCH UPDATES' in post['caption'] and '2–0' in post['caption']
    assert all(m['id'] in state['highlightly_watchlist']['selected'] for m in post['snapshot'])


def test_future_kickoffs_need_no_detail_reads(cfg):
    api=FakeAPI([game(at=NOW+timedelta(hours=2),status='Not started',score=None,clock=None)])
    state={};assert not poll(cfg,state,NOW,api)[0]
    assert api.calls==['catalog'] and len(state['highlightly_watchlist']['selected'])==1


def test_fair_rotation_updates_every_due_target_before_revisiting(cfg):
    api=FakeAPI([game(i+1,key) for i,key in enumerate(LEAGUES)])
    state={};poll(cfg,state,NOW,api)
    for n in (1,2):
        api.now=NOW+timedelta(minutes=n*20);api.at=api.now.isoformat()
        poll(cfg,state,api.now,api)
    targets=[c for c in api.calls if c!='catalog']
    assert len(set(targets[:5]))==5 and len(targets)==6
    assert len(state['highlightly_watchlist']['selected'])==5


def test_partial_catalog_failure_keeps_prior_roster_and_unknown_history(cfg):
    state={'posts':[{'status':'unknown'}],'event_api':{'primary':'untouched'}}
    start=NOW.replace(hour=10)
    api=FakeAPI([game(at=start-timedelta(minutes=80))],start);poll(cfg,state,start,api)
    old=deepcopy(state['highlightly_watchlist']['selected'])
    api.rows=ProviderError('synthetic failure');api.now=start+timedelta(hours=8);api.at=api.now.isoformat()
    assert not poll(cfg,state,api.now,api)[0]
    assert state['highlightly_watchlist']['selected']==old
    assert state['posts']==[{'status':'unknown'}] and state['event_api']=={'primary':'untouched'}


def test_new_access_or_network_failure_stops_rest_of_cycle(cfg):
    api=FakeAPI([game(1),game(2,'epl')])
    api.details['highlightly:1']=ProviderError('synthetic access failure')
    state={};poll(cfg,state,NOW,api)
    assert api.calls==['catalog','highlightly:1']
    assert state['highlightly_watchlist']['selected']['highlightly:1']['problem']=='detail_failed_or_identity_unverified'


def test_mismatch_never_enters_ledger(cfg):
    api=FakeAPI([game()]);wrong=game();wrong['homeTeam']['id']=999
    api.details['highlightly:1']=wrong
    state={};assert not poll(cfg,state,NOW,api)[0]
    assert not state.get('live_event_ledger',{}).get('matches')


def test_ns_retiming_before_live_allowed_but_live_identity_not_changed(cfg):
    now=NOW.replace(hour=8,minute=0)
    value=game(at=now+timedelta(hours=1),status='Not started',score=None,clock=None)
    api=FakeAPI([value],now);state={};poll(cfg,state,now,api)
    api.now=now+timedelta(hours=8);api.at=api.now.isoformat()
    api.rows[0]['date']=(api.now+timedelta(hours=1)).isoformat()
    poll(cfg,state,api.now,api)
    assert state['highlightly_watchlist']['selected']['highlightly:1']['kickoff']==(api.now+timedelta(hours=1)).isoformat()


def test_unconfirmed_timed_out_target_is_unresolved_not_finished(cfg):
    start=NOW.replace(hour=14)
    api=FakeAPI([game(at=start-timedelta(minutes=80))],start);state={};poll(cfg,state,start,api)
    api.now=start+timedelta(hours=5);api.at=api.now.isoformat()
    before=len(api.calls);poll(cfg,state,api.now,api)
    assert state['highlightly_watchlist']['selected']['highlightly:1']['problem']=='tracking_window_exceeded_unresolved'
    # No more calls after the tracking bound, and still no inferred final.
    assert len(api.calls)==before
    assert state['highlightly_watchlist']['selected']['highlightly:1']['confirmed_status']=='2H'


def test_budget_zero_and_daily_setting_change_never_reset_or_read(cfg):
    api=FakeAPI([game()]);state={};poll(cfg,state,NOW,api)
    api.now=NOW+timedelta(minutes=20);api.at=api.now.isoformat();api.budget.update(requests=100,remaining=0)
    before=list(api.calls);assert not poll(cfg,state,api.now,api)[0]
    assert api.calls==before and api.budget['requests']==100
    cfg['highlightly']['watchlist']['max_matches']=4
    with pytest.raises(ProviderError):poll(cfg,state,api.now,api)


def test_real_transport_first_catalog_then_only_one_detail_next_poll(cfg,monkeypatch):
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-highlightly')
    values=[game()]+[row(i) for i in range(2,102)]
    opener=Opener(Response(envelope(values[:100],101)),Response(envelope(values[100:],101,100),98),Response([game()],97))
    state={};api=highlightly.Highlightly(cfg,state,NOW,opener)
    assert poll(cfg,state,NOW,api)[0] and len(opener.calls)==3
    later=NOW+timedelta(minutes=20)
    next_opener=Opener(Response([game(clock=85)],96,stamp=later))
    next_api=highlightly.Highlightly(cfg,state,later,next_opener)
    assert poll(cfg,state,later,next_api)[0]
    assert len(next_opener.calls)==1 and next_opener.calls[0].full_url.endswith('/matches/1')
    assert state['highlightly_api']['requests']==4


@pytest.mark.parametrize('field,value',[('max_matches',6),('catalog_refresh_hours',1),('max_catalog_attempts_per_day',3),('leagues',['psl'])])
def test_config_limits_and_exact_approved_scope(cfg,tmp_path,field,value):
    cfg['highlightly']['watchlist'][field]=value
    path=tmp_path/'config.json';storage.write(path,cfg)
    with pytest.raises(ValueError):cli.config(path)


def test_preview_summary_has_no_cached_scores_or_account_details(cfg):
    api=FakeAPI([game()]);state={};poll(cfg,state,NOW,api)
    text=json.dumps(summary(state['highlightly_watchlist']))
    assert 'Synthetic Home 1' in text and 'South Africa' in text
    assert 'home_goals' not in text and 'subscription' not in text and 'api_key' not in text


def test_no_unapproved_league_fallback_when_there_are_no_eligible_matches(cfg):
    api=FakeAPI([row()]);state={}
    assert not poll(cfg,state,NOW,api)[0]
    assert api.calls==['catalog'] and state['highlightly_watchlist']['selected']=={}
    assert summary(state['highlightly_watchlist'])['scope']=='selected_matches_only'


def test_explicit_postponement_with_new_kickoff_is_not_a_team_identity_change(cfg):
    state={};api=FakeAPI([game()]);poll(cfg,state,NOW,api)
    later=NOW+timedelta(minutes=20);api.now=later;api.at=later.isoformat()
    api.details['highlightly:1']['state']['description']='Postponed'
    api.details['highlightly:1']['date']=(NOW+timedelta(days=1)).isoformat()
    post,_=event_monitor.build(cfg,state,later,api)
    assert post and 'Postponed' in post['caption']
    assert state['highlightly_watchlist']['selected']['highlightly:1']['confirmed_status']=='PST'


def test_stalled_clock_cannot_be_reported_as_an_accepted_fresh_live_observation(cfg):
    state={};api=FakeAPI([game()]);poll(cfg,state,NOW,api)
    for minutes in (20,40):
        api.now=NOW+timedelta(minutes=minutes);api.at=api.now.isoformat()
        result=poll(cfg,state,api.now,api)
    assert not result[0]
    assert state['highlightly_watchlist']['selected']['highlightly:1']['problem']=='observation_regression_or_stall_rejected'


def test_daily_rollover_does_not_delete_old_event_or_unknown_send_history(cfg):
    start=NOW.replace(hour=10);api=FakeAPI([game(at=start-timedelta(minutes=80))],start)
    state={'posts':[{'status':'unknown'}],'event_api':{'keep':True}}
    poll(cfg,state,start,api)
    old=deepcopy(state['live_event_ledger']['matches'])
    tomorrow=start+timedelta(days=1);api.now=tomorrow;api.at=tomorrow.isoformat();api.rows=[]
    poll(cfg,state,tomorrow,api)
    assert state['posts']==[{'status':'unknown'}] and state['event_api']=={'keep':True}
    assert state['live_event_ledger']['matches']==old and state['highlightly_watchlist']['previous_day']['matches']


def test_catalog_attempts_bounded_even_on_repeated_failure(cfg):
    start=NOW.replace(hour=8);api=FakeAPI(ProviderError('synthetic failure'),start,details={});state={}
    for hours in (0,1,2,3):
        api.now=start+timedelta(hours=hours);api.at=api.now.isoformat()
        poll(cfg,state,api.now,api)
    assert api.calls==['catalog','catalog'] and state['highlightly_watchlist']['catalog_attempts']==2


def test_live_retiming_or_changed_competition_is_not_silently_accepted(cfg):
    state={};api=FakeAPI([game()]);poll(cfg,state,NOW,api)
    later=NOW+timedelta(minutes=20);api.now=later;api.at=later.isoformat()
    api.details['highlightly:1']['date']=(NOW-timedelta(minutes=70)).isoformat()
    assert not poll(cfg,state,later,api)[0]
    assert state['highlightly_watchlist']['selected']['highlightly:1']['problem']=='detail_failed_or_identity_unverified'


def test_old_global_pending_events_cannot_leak_into_selected_bulletin(cfg):
    state={'posts':[]};outside=highlightly.observation(row(99),NOW)
    match_events.observe(state,[outside],NOW.isoformat(),NOW)
    state['live_event_ledger']['events']['old-global']={'id':'old-global','fixture_id':outside['id'],'status':'pending','detected_at':NOW.isoformat(),'change':{'kind':'score_update'}}
    api=FakeAPI([game()]);assert event_monitor.build(cfg,state,NOW,api)[0] is None
    assert state['live_event_ledger']['events']['old-global']['status']=='pending'


def test_send_cancels_old_unselected_reservation_before_page_access(cfg,tmp_path,monkeypatch):
    from datetime import datetime
    from facebook_feed import content,policy
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GITHUB_RUN_ID','watch-test');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setattr(cli,'PageFeed',lambda *a:pytest.fail('No Page access for unselected historical reservation'))
    post=content.candidate('live','old-global','old-global','Synthetic old global caption',event_ids=['e'],snapshot=[highlightly.observation(game(99),NOW)],expires_at=(NOW+timedelta(minutes=3)).isoformat())
    state={'posts':[],'highlightly_watchlist':{'day':NOW.date().isoformat(),'selected':{'highlightly:1':metadata(game(),NOW)}},'live_event_ledger':{'matches':{},'events':{'e':{'status':'reserved'}}}}
    entry=policy.reserve(post,state,NOW);entry['run_key']='watch-test-1'
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    assert cli.main(['send','--kind','live','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    saved=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert saved['posts'][0]['status']=='cancelled' and saved['live_event_ledger']['events']['e']['status']=='pending'


def test_100th_detail_response_valid_and_no_101st_request(cfg,monkeypatch):
    api=FakeAPI([game(1),game(2,'epl')]);state={};poll(cfg,state,NOW,api)
    later=NOW+timedelta(minutes=20)
    state['highlightly_api']={'utc_date':later.astimezone(timezone.utc).date().isoformat(),'requests':99,'remaining':1,'plan_verified_at':NOW.isoformat()}
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-highlightly')
    opener=Opener(Response([game(clock=85,score='2 - 0')],0,stamp=later))
    actual=highlightly.Highlightly(cfg,state,later,opener)
    post,_=event_monitor.build(cfg,state,later,actual)
    assert post and len(opener.calls)==1 and state['highlightly_api']['requests']==100



def test_switch_from_global_to_selected_baselines_without_erasing_old_pending(cfg):
    state={'posts':[]}
    prior=highlightly.observation(game(score='0 - 0'),NOW)
    match_events.observe(state,[prior],(NOW-timedelta(minutes=1)).isoformat(),NOW)
    state['live_event_ledger']['events']['old']={'id':'old','fixture_id':'highlightly:1','status':'pending','detected_at':(NOW-timedelta(minutes=1)).isoformat(),'change':{'kind':'score_update'}}
    api=FakeAPI([game()])
    assert event_monitor.build(cfg,state,NOW,api)[0] is None
    assert state['live_event_ledger']['events']['old']['status']=='pending'
    created=[e for k,e in state['live_event_ledger']['events'].items() if k!='old']
    assert created and all(e['status']=='expired' and e['reason']=='selected_roster_baseline' for e in created)
    later=NOW+timedelta(minutes=20);api.now=later;api.at=later.isoformat()
    api.details['highlightly:1']['state'].update(clock=85,score={'current':'2 - 0'})
    post,_=event_monitor.build(cfg,state,later,api)
    assert post and 'old' not in post['event_ids'] and len(post['event_ids'])==1


def test_selected_diagnostic_previews_roster_without_committing_cache_or_events(cfg,monkeypatch):
    values=[game(),game(2,'epl',at=NOW+timedelta(hours=1),status='Not started',score=None,clock=None)]
    state={'posts':[{'status':'unknown'}],'live_event_ledger':{'sentinel':'untouched'}}
    monkeypatch.setenv('HIGHLIGHTLY_API_KEY','synthetic-private-highlightly')
    opener=Opener(Response(envelope(values)),Response([game()],98))
    api=highlightly.Highlightly(cfg,state,NOW,opener)
    report=highlightly.diagnose(cfg,state,NOW,api)
    assert report['ready_for_activation'] and report['facebook_requests']==0
    assert len(report['selection_preview']['matches'])==2
    assert report['selection_preview']['scope']=='selected_matches_only'
    assert 'highlightly_watchlist' not in state and state['live_event_ledger']=={'sentinel':'untouched'}
    assert state['posts']==[{'status':'unknown'}] and len(opener.calls)==2


def test_prepare_surfaces_safe_roster_in_phone_summary_and_public_artifact(cfg,tmp_path,monkeypatch):
    from datetime import datetime
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GH_READ_TOKEN','synthetic-placeholder-read')
    monkeypatch.setenv('GITHUB_STEP_SUMMARY',str(tmp_path/'summary.md'))
    state={'posts':[],'highlightly_watchlist':{'day':NOW.date().isoformat(),'selected':{'highlightly:1':metadata(game(),NOW)},'status':'selected'}}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(state))
    monkeypatch.setattr(cli,'build',lambda *a,**kw:(None,'offline summary test'))
    monkeypatch.setattr(cli,'PageFeed',lambda *a:pytest.fail('No Page request'))
    storage.write(tmp_path/'config.json',cfg)
    assert cli.main(['prepare','--kind','live','--preview','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    text=(tmp_path/'live-watchlist.json').read_text()
    assert 'Synthetic Home 1' in text and 'selected_matches_only' in text
    assert 'Selected live watchlist' in (tmp_path/'summary.md').read_text()
    assert 'home_goals' not in text
