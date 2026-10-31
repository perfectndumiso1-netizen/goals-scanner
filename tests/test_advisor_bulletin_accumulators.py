"""Production morning routing, real-edition boundaries and brand, entirely offline."""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image,ImageChops,ImageDraw
import pytest
import yaml
import advisor_tracking
import scanner
import video_accumulators as accumulators
from facebook_feed import cli,content,editorial,storage,watchdog,policy
from facebook_feed import advisor_predictions as predictions

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,31,7,30,tzinfo=content.SAST)
DAY='2026-10-30'


@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def pick(i=0,**kw):
    return dict(home=f'Home {i}',away=f'Away {i}',country='England',kickoff=f'{DAY} 20:00',
                sel='O15',label='Over 1.5 goals',odds=1.2,p=.8,**kw)


def source(root,now=NOW,picks=None):
    root.mkdir(parents=True,exist_ok=True)
    if picks is None:
        picks=[{**pick(i),'sel':sel,'kickoff':now.replace(hour=15+i).isoformat()} for i,sel in enumerate(('H','D','A','O15'))]
    data={'meta':{'generated':now.isoformat()},'safe':{'today':{'bets':picks}},'fixtures':[]}
    storage.write(root/'latest.json',data);return root


def test_production_schedule_separates_results_predictions_and_nine_matches(cfg):
    assert cfg['authorized_kinds']==['editorial','results']
    assert dict(editorial.schedule(cfg))['07:30']=='predictions'
    assert cli.is_due('results',NOW.replace(hour=6,minute=0),cfg)
    assert cli.is_due('results',NOW.replace(hour=6,minute=44,second=59),cfg)
    assert not cli.is_due('results',NOW.replace(hour=6,minute=45),cfg)
    assert not cli.is_due('results',NOW,cfg)
    assert not cli.is_due('results',NOW.replace(hour=8,minute=0),cfg)
    assert editorial.due(NOW,cfg)=='predictions'
    assert all(not cli.is_due(k,NOW,cfg) for k in ('live','community','card','weekly','roundup'))
    assert cfg['highlightly']['daily_request_budget']==100 and cfg['editorial']['match_posts_per_day']==9


def test_all_visible_advisor_1x2_are_copied_not_shortlist_or_football_provider(cfg,tmp_path,monkeypatch):
    root=source(tmp_path/'app');calls=[]
    monkeypatch.setattr(editorial,'Source',lambda *a:pytest.fail('No Highlightly reads for predictions'))
    cfg['highlightly']['rights_confirmed']=False
    post,reason=cli.build('editorial',root,NOW,cfg,{})
    assert post,reason
    assert predictions.is_post(post) and len(post['snapshot'])==3
    assert all(x['source']==predictions.SOURCE for x in post['snapshot'])
    assert post['caption'].startswith('1X2 PREDICTIONS OF THE DAY')
    assert all(t in post['caption'] for t in ('1 — Home 0 to win','X — Draw','2 — Away 2 to win','@ 1.20','18+'))
    assert 'Over 1.5' not in post['caption'] and 'Home 3' not in post['caption']
    assert all(t not in post['caption'] for t in ('PlayReport','MR 2 ODDS','Highlightly','Source:','checked'))
    assert content.local(post['expires_at'])==NOW+timedelta(minutes=5)


def test_visible_sections_dedupes_only_same_selection_never_silently_caps_report(cfg,tmp_path):
    picks=[{**pick(i),'sel':'H','kickoff':NOW.replace(hour=20).isoformat()} for i in range(6)]
    root=source(tmp_path/'app',picks=picks)
    data=content.load(root/'latest.json');data['safe']['today']['groups']=[{'bets':picks}]
    data['groups']={'value':[{'id':'f1','sel':'A','p':.6,'odds':2.0}], 'strong':[]}
    data['fixtures']=[dict(id='f1',home='Extra Home',away='Extra Away',country='England',kickoff=NOW.replace(hour=20).isoformat())]
    data['shortlist']={'primary':[dict(picks[0],home='Not on Advisor')]}
    storage.write(root/'latest.json',data)
    post,_=predictions.build(root,NOW,cfg,{})
    assert len(post['snapshot'])==7 and 'Extra Home' in post['caption']
    assert 'Not on Advisor' not in post['caption']


@pytest.mark.parametrize('change',['missing','stale','yesterday','future','invalid_price','missing_price','invalid_probability','bool_price','bad_name'])
def test_invalid_advisor_data_never_falls_back_to_fixtures_or_partial_picks(cfg,tmp_path,change):
    root=source(tmp_path/'app');data=content.load(root/'latest.json')
    if change=='missing':(root/'latest.json').unlink()
    else:
        if change=='stale':data['meta']['generated']=(NOW-timedelta(hours=13)).isoformat()
        if change=='yesterday':data['meta']['generated']=(NOW-timedelta(hours=8)).isoformat()
        if change=='future':data['meta']['generated']=(NOW+timedelta(minutes=6)).isoformat()
        if change=='invalid_price':data['safe']['today']['bets'][0]['odds']=float('nan')
        if change=='missing_price':data['safe']['today']['bets'][0].pop('odds')
        if change=='invalid_probability':data['safe']['today']['bets'][0]['p']=1.0
        if change=='bool_price':data['safe']['today']['bets'][0]['odds']=True
        if change=='bad_name':data['safe']['today']['bets'][0]['home']='bad\nname'
        storage.write(root/'latest.json',data)
    assert predictions.build(root,NOW,cfg,{})[0] is None


def test_already_started_and_insufficient_lead_picks_are_not_predicted(cfg,tmp_path):
    root=source(tmp_path/'app',picks=[{**pick(),'sel':'H','kickoff':(NOW+timedelta(minutes=10)).isoformat()}])
    assert predictions.build(root,NOW,cfg,{})==(None,'No safely upcoming 1X2 selections on Bet Advisor; no filler')


def test_direct_factual_builder_cannot_turn_highlightly_into_betting_content(cfg,monkeypatch):
    monkeypatch.setattr(editorial,'Source',lambda *a:pytest.fail('No factual data may support betting'))
    assert editorial.build(cfg,{},NOW)[0] is None


def test_prediction_admission_cannot_debit_or_be_blocked_by_factual_quota(cfg):
    before={'utc_date':NOW.astimezone(__import__('datetime').timezone.utc).date().isoformat(), 'requests':100,'remaining':0,'after':(NOW+timedelta(days=1)).isoformat()}
    s={'posts':[],'highlightly_api':deepcopy(before)}
    watchdog.book(s,NOW,editorial.schedule(cfg))
    assert watchdog.assess(s,NOW,'123-1')[0]
    key=watchdog.current_slot(s,NOW)[0];row=s['editorial_delivery']['slots'][key]
    assert row['quota_hold']['amount']==0 and row['attempts']==1
    watchdog.release_quota_hold(s,row)
    assert s['highlightly_api']==before
    # The ordinary match slot still cannot bypass the same hard limit/cooldown.
    assert not watchdog.assess(s,NOW.replace(hour=8,minute=0),'124-1')[0]


def test_prediction_dedupe_and_unknown_guards_stay(cfg,tmp_path):
    post,_=predictions.build(source(tmp_path/'app'),NOW,cfg,{})
    s={'posts':[]};policy.reserve(post,s,NOW)['status']='unknown'
    assert not policy.allowed(post,s,NOW+timedelta(minutes=50),cfg)[0]


@pytest.mark.parametrize('states,expected,returned',[
    (['hit']*5,'WON',Decimal('2.48832')),
    (['hit']*4+['void'],'WON',Decimal('2.0736')),
    (['void']*5,'VOID',Decimal(1)),
    (['hit']*4+['pending'],'PENDING',None),
    (['hit']*3+['pending','miss'],'LOST',Decimal(0)),
    (['void']*4+['miss'],'LOST',Decimal(0)),
])
def test_each_video_is_one_accumulator_not_sum_of_singles(states,expected,returned):
    result=accumulators.settle([{**pick(i),'result':s} for i,s in enumerate(states)])
    assert result['status']==expected and result['return_units']==returned
    assert result['original_odds']==Decimal('2.48832')
    assert result['profit_units']==(None if returned is None else returned-1)


@pytest.mark.parametrize('bad',[None,True,0,'NaN','Infinity','wrong',1.15])
def test_missing_original_odds_never_invent_payout(bad):
    result=accumulators.settle([dict(pick(),odds=bad,result='hit')])
    assert result['status']=='WON' and result['return_units'] is None and result['original_odds'] is None


def test_editions_are_append_only_and_have_independent_hashes():
    p=[pick(i) for i in range(5)];book=accumulators.record({},DAY,'morning',p,'recorded')
    book=accumulators.record(book,DAY,'noon',[pick(i+5) for i in range(5)],'later')
    assert accumulators.record(book,DAY,'morning',p,'retry')==book
    with pytest.raises(ValueError,match='overwritten'):
        accumulators.record(book,DAY,'morning',[dict(x,odds=1.5) for x in p],'later')
    groups,unassigned=accumulators.groups({'briefing_editions':book},DAY)
    assert [g[0] for g in groups]==['morning','noon'] and not unassigned
    book[DAY]['morning']['picks'][0]['odds']=1.9
    with pytest.raises(ValueError,match='integrity'):accumulators.groups({'briefing_editions':book},DAY)


def result_source(root):
    source(root,now=NOW.replace(hour=6,minute=0))
    morning=[pick(i) for i in range(5)];noon=[pick(i+5) for i in range(5)]
    book=accumulators.record({},DAY,'morning',morning,'morning ack')
    book=accumulators.record(book,DAY,'noon',noon,'noon ack')
    storage.write(root/'telegram_state.json',{'briefing_editions':book,'briefing_history':{DAY:morning+noon}})
    ledger=[dict(p,match_date=DAY,status='hit',score='2-1',odds=9) for p in morning+noon]
    ledger[3]['status']='void';ledger[5]['status']='miss';ledger[6]['status']='pending'
    storage.write(root.parent/'advisor_ledger.json',ledger)
    return root


def test_one_morning_post_has_two_separate_accumulators_original_prices_and_all_losses(cfg,tmp_path):
    root=result_source(tmp_path/'data/app')
    post=content.morning_results(root,NOW,cfg);caption=post['caption']
    assert 'MORNING VIDEO — SEPARATE ACCUMULATOR: WON' in caption
    assert 'NOON VIDEO — SEPARATE ACCUMULATOR: LOST' in caption
    assert 'Original combined odds: 2.49' in caption and 'Void-adjusted combined odds: 2.07' in caption
    assert 'return 2.07 · profit +1.07 units' in caption
    assert 'return 0.00 · profit -1.00 units' in caption
    assert caption.count(' @ 1.20')==10 and '@ 9.00' not in caption
    assert all(f'Home {i} v Away {i}' in caption for i in range(10))
    assert 'PENDING' in caption and 'VOID' in caption and 'OLDER VIDEO' not in caption
    assert len(post['snapshot'])==2 and post['key']==f'video-results:{DAY}'
    assert all(word not in caption for word in ('PLAYREPORT','MR 2 ODDS','Source:','checked','Latest app publication'))


def test_legacy_grouping_is_disclosed_never_guessed_or_merged_into_one_accumulator(cfg,tmp_path):
    root=result_source(tmp_path/'data/app');state=content.load(root/'telegram_state.json');state.pop('briefing_editions')
    storage.write(root/'telegram_state.json',state)
    post=content.morning_results(root,NOW,cfg)
    assert 'OLDER VIDEO GROUPING UNAVAILABLE' in post['caption']
    assert 'Original combined odds:' not in post['caption'] and 'SEPARATE ACCUMULATOR:' not in post['caption']
    assert post['snapshot'][0]['edition']=='unassigned_legacy' and len(post['snapshot'][0]['picks'])==10


def test_midnight_keeps_exact_previous_video_editions_without_resetting_slots(monkeypatch,tmp_path):
    state={'day':DAY,'briefing_editions':accumulators.record({},DAY,'morning',[pick(i) for i in range(5)],'ack'),
           'briefing_history':{DAY:[pick(i) for i in range(5)]},'briefing_slots':{DAY:['morning']}}
    storage.write(tmp_path/'app/telegram_state.json',state);monkeypatch.setattr(scanner,'DATA_DIR',tmp_path)
    _,next_state=scanner._telegram_state(NOW)
    assert next_state['briefing_editions']==state['briefing_editions'] and next_state['briefing_history'][DAY]


def test_country_or_ambiguous_settlement_cannot_be_replaced_by_a_win():
    p=pick();entry=dict(p,match_date=DAY,status='hit',score='2-1')
    assert advisor_tracking.video_results([dict(entry,country='France')],[p])==[]
    assert advisor_tracking.video_results([entry,dict(entry,status='miss')],[p])==[]


def test_recap_is_one_daily_post_and_never_collides_with_prediction_gap(cfg,tmp_path):
    root=result_source(tmp_path/'data/app');at=NOW.replace(hour=6,minute=0)
    post=content.morning_results(root,at,cfg);s={'posts':[]}
    assert policy.allowed(post,s,at,cfg)[0]
    policy.reserve(post,s,at)['status']='published'
    assert not policy.allowed(dict(post,key='other',topic='other'),s,at+timedelta(minutes=20),cfg)[0]
    prediction,_=predictions.build(root,NOW,cfg,{})
    assert policy.allowed(prediction,s,NOW,cfg)[0]


def test_recap_unknown_reconciles_positively_without_any_resend():
    s={'posts':[{'kind':'results','status':'unknown','post_id':'123_4','caption_hash':'hash'}]};calls=[]
    class Page:
        def verify_hash(self,*args):calls.append(args)
    watchdog.reconcile_known(s,NOW,Page)
    assert s['posts'][0]['status']=='published' and calls==[('123_4','hash')]


def test_results_schedule_and_read_only_published_advisor_checkout():
    wf=yaml.safe_load((ROOT/'.github/workflows/facebook-roundup.yml').read_text())
    on=wf.get('on',wf.get(True))
    assert on['schedule']==[{'cron':'0 4 * * *'},{'cron':'20 4 * * *'}]
    wf=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    step=next(s for s in wf['jobs']['feed']['steps'] if 'Read published Bet Advisor' in s['name'])
    assert step['with']['ref']=='data' and step['with']['sparse-checkout'].strip()=='data/app/latest.json'
    assert step['if']=="inputs.kind == 'editorial'"


def test_feed_readers_do_not_require_pandas_or_a_provider_dependency():
    code="import sys; import advisor_tracking, video_accumulators; from facebook_feed import advisor_predictions; assert 'pandas' not in sys.modules; assert 'safe' not in sys.modules"
    subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)


def test_logo_uses_owner_selected_asset_without_touching_any_statistics():
    from football_artwork import brand
    before=Image.new('RGBA',(1080,1350),'#06141d');after=before.copy()
    brand(after,ImageDraw.Draw(after))
    assert ImageChops.difference(before.convert('RGB'),after.convert('RGB')).getbbox()
    assert ImageChops.difference(before.convert('RGB').crop((0,139,1080,1350)),after.convert('RGB').crop((0,139,1080,1350))).getbbox() is None
    for name in ('facebook_cover.py','facebook_feed/comparison_graphic.py','facebook_feed/recent_results_graphic.py','facebook_feed/stadium_graphic.py','facebook_feed/score_graphic.py','facebook_feed/graphics.py'):
        text=(ROOT/name).read_text()
        assert 'PLAYREPORT' not in text and 'brand(' in text


@pytest.mark.parametrize('portrait_changes_card',[False,True])
def test_saved_editions_follow_actual_render_not_candidate_pool(monkeypatch,tmp_path,portrait_changes_card):
    from types import SimpleNamespace
    at=NOW.replace(hour=5,minute=0);today=at.date().isoformat()
    picks=[dict(pick(i),kickoff=f'{today} 20:00') for i in range(6)]
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','fake');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','fake')
    monkeypatch.delenv('FORCE_DAILY_REEL',raising=False);monkeypatch.setenv('TMPDIR',str(tmp_path))
    monkeypatch.setattr(scanner,'ROOT',tmp_path)
    assets=tmp_path/'assets/reel';assets.mkdir(parents=True);(assets/'logo.png').write_bytes(b'placeholder')
    app=tmp_path/'latest.json';storage.write(app,{'meta':{'generated':at.isoformat()},'fixtures':[]})
    monkeypatch.setattr(scanner,'APP_FILE',app)
    state={};monkeypatch.setattr(scanner,'_telegram_state',lambda now:(tmp_path/'state.json',state))
    monkeypatch.setattr(advisor_tracking,'selections',lambda data:picks)
    monkeypatch.setattr(scanner,'yt_mod',None);monkeypatch.setattr(scanner,'drive_mod',None)
    def render(card,path,**kw):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'video')
        actual=deepcopy(card[:5])
        if kw.get('aspect')=='9:16' and portrait_changes_card:actual[0]['odds']=1.5
        storage.write(kw['work']/'build_meta.json',{'picks':actual})
    monkeypatch.setattr(scanner,'reel_mod',SimpleNamespace(build=render,video_picks=lambda *a,**k:(picks,[])))
    sent=[]
    monkeypatch.setattr(scanner,'send_telegram_video',lambda path,caption,**kw:(sent.append(kw['facebook_path']) or True))
    scanner.maybe_send_daily_reel({},at)
    assert len(state['briefing_history'][today])==5
    assert state['briefing_editions'][today]['morning']['picks']==picks[:5]
    assert sent[0].exists() is not portrait_changes_card


def test_prediction_cli_can_publish_from_advisor_when_factual_source_not_approved(cfg,tmp_path,monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(cli,'datetime',Clock)
    for k,v in {'GITHUB_REF_NAME':'main','GITHUB_REPOSITORY':'owner/repo','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','FACEBOOK_FEED_PUBLISH':'true','GH_READ_TOKEN':'placeholder'}.items():monkeypatch.setenv(k,v)
    cfg['highlightly'].update(rights_confirmed=False,account_coverage_verified=False)
    root=source(tmp_path/'app');work=tmp_path/'work';config=tmp_path/'config.json';storage.write(config,cfg)
    s={'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[]}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(s))
    monkeypatch.setattr(editorial,'Source',lambda *a:pytest.fail('No provider API calls'))
    args=['--kind','editorial','--publish','--source',str(root),'--work',str(work),'--config',str(config)]
    assert cli.main(['prepare',*args])==0
    plans=content.load(work/'plans.json');assert len(plans)==1 and predictions.is_post(plans[0])
    sent=[]
    class Page:
        def send(self,post):sent.append(post);return '123_4'
        def verify(self,*a):return True
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(['send',*args,'--checkpoint'])==0
    assert len(sent)==1 and content.load(work/'checkpoint/state.json')['posts'][0]['status']=='published'


def test_prediction_and_results_completion_triggers_keep_watchdog_subscription_valid():
    post=yaml.safe_load((ROOT/'.github/workflows/facebook-editorial.yml').read_text())
    watch=yaml.safe_load((ROOT/'.github/workflows/facebook-watchdog.yml').read_text())
    on=watch.get('on',watch.get(True))
    assert post['name'] in on['workflow_run']['workflows']
    assert 'Facebook morning video results' in on['workflow_run']['workflows']


def test_duplicate_leg_cannot_be_five_fictitious_accumulator_legs():
    with pytest.raises(ValueError,match='repeat'):
        accumulators.record({},DAY,'morning',[pick()]*5,'ack')


def test_production_watchdog_admits_predictions_without_factual_approval_or_quota(cfg,tmp_path,monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(watchdog,'datetime',Clock)
    monkeypatch.setattr(cli,'config',lambda path:cfg)
    cfg['highlightly'].update(rights_confirmed=False,account_coverage_verified=False)
    for k,v in {'GITHUB_REF_NAME':'main','GITHUB_REPOSITORY':'owner/repo','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','FACEBOOK_FEED_PUBLISH':'true','WATCHDOG_REQUEST_PUBLISH':'true','GH_READ_TOKEN':'placeholder','GITHUB_OUTPUT':str(tmp_path/'outputs')}.items():monkeypatch.setenv(k,v)
    s={'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[],
       'highlightly_api':{'utc_date':NOW.astimezone(__import__('datetime').timezone.utc).date().isoformat(),'requests':100,'remaining':0}}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(s))
    monkeypatch.setattr(watchdog,'PageFeed',lambda:object())
    assert watchdog.main(['assess','--work',str(tmp_path)])==0
    assert 'allow_prepare=true' in (tmp_path/'outputs').read_text()
    checkpoint=content.load(tmp_path/'checkpoint/state.json')
    assert checkpoint['highlightly_api']==s['highlightly_api']
