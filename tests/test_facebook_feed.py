"""Offline contract tests. Synthetic replay fixtures are not evidence of a live provider test."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from email.utils import format_datetime
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import zipfile
import pytest
import yaml

from facebook_feed import content,policy,provider,publisher,storage,cli,graphics

NOW=datetime(2026,10,29,12,15,tzinfo=content.SAST)
ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def recent(venue=None):
    return [dict(date=(NOW-timedelta(days=i+2)).date().isoformat(),venue=venue or ('H' if i%2 else 'A'),
                 opp=f'Opponent {i}',gf=2,ga=i%2,league='Test League') for i in range(5)]


def source(tmp_path,count=4):
    root=tmp_path/'data/app';(root/'fx').mkdir(parents=True);(root/'days').mkdir()
    fixtures=[]
    for i in range(count):
        key=f'{i:012x}';fixture=dict(id=f'match-{i}',d=key,home=f'Home {i}',away=f'Away {i}',
            kickoff=(NOW+timedelta(hours=8,days=i%2)).isoformat(),date=NOW.date().isoformat(),time_known=True,
            country='England',league='Test League',competition='England · Test League')
        fixtures.append(fixture)
        detail={**fixture,'generated':NOW.isoformat(),'teams':{
            'home':{'last5':recent(),'venue_last5':recent('H')},'away':{'last5':recent(),'venue_last5':recent('A')}},'h2h':[]}
        (root/'fx'/f'{key}.json').write_text(json.dumps(detail))
    payload={'meta':{'generated':NOW.isoformat()},'fixtures':fixtures}
    (root/'latest.json').write_text(json.dumps(payload))
    (root/'days'/f'{NOW.date()}.json').write_text(json.dumps({'updated':NOW.isoformat(),'fixtures':fixtures}))
    return root


def test_sample_counts_scores_not_rates_or_estimates():
    result=content.sample(recent(),NOW)
    assert result['n']==5 and result['scored']==10 and result['conceded']==2
    assert result['form']=='WWWWW' and result['scope']=='Test League'


@pytest.mark.parametrize('field,value',[('gf',None),('gf',True),('gf',-1),('gf',1.2),('ga','not-known'),
    ('league','Friendly'),('league','Club Friendlies'),('league',None),('opp',None),('league',''),('date','bad'),('date','2026-10-30'),('date','2024-01-01'),('venue','unknown')])
def test_invalid_samples_never_invent_missing_data(field,value):
    rows=recent();rows[0][field]=value
    assert content.sample(rows,NOW) is None


def test_duplicate_recent_results_and_thin_venue_sample_fail_closed():
    rows=recent();rows[4]=rows[0]
    assert content.sample(rows,NOW) is None
    assert content.sample(recent()[:4],NOW) is None
    assert content.sample(recent('A'),NOW,'H') is None


def test_mixed_competition_scope_is_not_called_league_only():
    rows=recent();rows[0]['league']='Competitive Cup'
    assert content.sample(rows,NOW)['scope']=='mixed competitive competitions'


def test_actual_detail_identity_and_freshness_required(tmp_path,cfg):
    root=source(tmp_path)
    assert len(content.verified_fixtures(root,NOW,cfg))==4
    assert content.verified_fixtures(root,NOW+timedelta(hours=13),cfg)==[]
    path=root/'fx/000000000000.json';d=json.loads(path.read_text());d['home']='Another Club';path.write_text(json.dumps(d))
    assert len(content.verified_fixtures(root,NOW,cfg))==3


def test_match_card_requires_venue_evidence_and_produces_original_mobile_graphic(tmp_path,cfg):
    root=source(tmp_path);items=content.verified_fixtures(root,NOW,cfg)
    post=content.match_card(items,NOW)
    assert 'INTERESTING STATS MATCH CARD' in post['caption'] and 'Last 5 recorded competitive' in post['caption']
    assert 'model estimate' not in post['caption']
    path=graphics.render(post['graphic'],tmp_path/'card.jpg')
    from PIL import Image
    assert Image.open(path).size==(1080,1350)
    for item in items:item['hv']=None
    assert content.match_card(items,NOW) is None


def test_weekly_uses_actual_next_seven_days_and_needs_three_teams(tmp_path,cfg):
    root=source(tmp_path);items=content.verified_fixtures(root,NOW,cfg)
    post=content.weekly(items,root,NOW)
    assert 3<=len(post['teams'])<=5 and 'TEAMS TO WATCH THIS WEEK' in post['caption']
    assert all(NOW<content.local(f['kickoff'])<NOW+timedelta(days=7) for t in post['teams'] for f in t['fixtures'])
    assert content.weekly(items[:1],root,NOW) is None
    graphics.render(post['graphic'],tmp_path/'weekly.jpg')


def test_honest_prediction_review_includes_losses_and_pending(tmp_path,cfg):
    book=[{'kind':'advisor','match_date':'2026-10-28','status':status,'country':'England','home':f'H{i}','away':'A','sel':'O15'}
          for i,status in enumerate(['miss','miss','pending','void'])]
    result=content.community([],book,NOW,[])
    assert '0 won, 2 lost' in result['caption'] and '1 pending' in result['caption'] and '0.0%' in result['caption']
    assert content.community([],[],NOW,[]) is None


def post(kind='community',key='one',**kw):
    return content.candidate(kind,key,key,'Caption '+key,**kw)


def test_durable_reservation_blocks_unknown_retry_and_topic_repeat(cfg):
    state={'posts':[]};p=post();entry=policy.reserve(p,state,NOW)
    assert not policy.allowed(p,state,NOW+timedelta(hours=3),cfg)[0]
    entry['status']='unknown'
    assert not policy.allowed(p,state,NOW+timedelta(hours=3),cfg)[0]
    another=post(key='two');another['topic']=p['topic']
    assert not policy.allowed(another,state,NOW+timedelta(hours=3),cfg)[0]


def test_cooldown_ordinary_cap_and_live_cap_are_shared(cfg):
    state={'posts':[]};policy.reserve(post(),state,NOW)
    assert policy.allowed(post('card',key='two'),state,NOW+timedelta(minutes=119),cfg)[1]=='feed cooldown'
    assert policy.allowed(post('card',key='two'),state,NOW+timedelta(hours=2),cfg)[0]
    policy.reserve(post('card',key='two'),state,NOW+timedelta(hours=2))
    assert policy.allowed(post('weekly',key='three'),state,NOW+timedelta(hours=3),cfg)[1]=='daily post cap'
    for i in range(3):policy.reserve(post('live',f'live-{i}'),state,NOW-timedelta(hours=i+1))
    assert policy.allowed(post('roundup','roundup'),state,NOW+timedelta(hours=5),cfg)[1]=='daily post cap'


def test_reel_quiet_windows_and_timezone_rollover(cfg):
    assert not policy.allowed(post(),{'posts':[]},NOW.replace(hour=8,minute=15),cfg)[0]
    assert content.local('2026-10-29T23:00:00Z').date().isoformat()=='2026-10-30'
    assert cli.is_due('community',NOW,cfg)


def match(**kw):
    return dict(id='1',home='Arsenal',away='Tottenham',competition='Premier League',country='England',
        kickoff=NOW.replace(hour=12,minute=0).isoformat(),status='1H',elapsed=15,home_goals=0,away_goals=0,penalties=None,**kw)


def test_match_selection_is_not_every_fixture(cfg):
    good=match();ordinary={**good,'id':'2','home':'Other','away':'Another'}
    assert policy.selected_matches([good,ordinary],cfg)==[good]
    cfg['live']['competitions']=[]
    assert policy.selected_matches([good],cfg)==[]


def test_minutes_or_single_goal_do_not_create_every_goal_notifications():
    a=match();assert not policy.significant(a,{**a,'elapsed':30})
    assert not policy.significant(a,{**a,'home_goals':1})
    assert policy.significant(a,{**a,'status':'HT'})
    assert policy.significant(a,{**a,'home_goals':2})
    assert policy.significant({**a,'home_goals':1},{**a,'home_goals':1,'away_goals':2})


def test_score_centre_edit_and_final_roundup_deduplicate(cfg):
    a=match();p=policy.score_post([a],{'posts':[]},NOW,cfg)
    state={'posts':[]};entry=policy.reserve(p,state,NOW-timedelta(hours=2));entry.update(status='published',post_id='123_456')
    assert policy.score_post([{**a,'elapsed':30}],state,NOW,cfg) is None
    cfg['live']['edit_existing']=True
    update=policy.score_post([{**a,'status':'HT'}],state,NOW,cfg)
    assert update['operation']=='edit' and update['target_id']=='123_456'
    finals=[{**a,'status':'FT','home_goals':1},{**a,'id':'2','status':'FT','home':'H2','away':'A2','away_goals':2}]
    roundup=policy.score_post(finals,state,NOW,cfg,roundup=True)
    assert roundup and 'RESULTS ROUNDUP' in roundup['caption']
    e=policy.reserve(roundup,state,NOW);e.update(status='published')
    assert policy.score_post(finals,state,NOW,cfg,roundup=True) is None


def raw_match():
    return {'fixture':{'id':123,'date':(NOW-timedelta(hours=1)).isoformat(),'status':{'short':'HT','elapsed':45}},
            'teams':{'home':{'name':'Arsenal'},'away':{'name':'Tottenham'}},'league':{'name':'Premier League','country':'England'},
            'goals':{'home':1,'away':0},'score':{}}


def test_provider_normalizes_real_scores_without_turning_null_into_zero():
    data=raw_match();assert provider.normalize(data,NOW)['home_goals']==1
    data['goals']['home']=None;assert provider.normalize(data,NOW) is None
    data['fixture']['status']['short']='NS';assert provider.normalize(data,NOW)['home_goals'] is None
    data['fixture']['status']['short']='UNKNOWN';assert provider.normalize(data,NOW) is None


class Response(io.BytesIO):
    def __init__(self,data,headers=None):super().__init__(json.dumps(data).encode());self.headers=headers or {}


def test_provider_free_plan_budget_cache_and_header_only_auth(monkeypatch,cfg):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic')
    requests=[]
    values=[{'response':{'subscription':{'plan':'Free','active':True},'requests':{'current':1}}},
            {'response':[raw_match()],'paging':{'total':1}}]
    def open(request,**kw):
        requests.append(request);assert 'synthetic' not in request.full_url
        return Response(values.pop(0),{'Date':format_datetime(NOW.astimezone(timezone.utc))})
    state={};p=provider.APIFootball(cfg,state,NOW,opener=SimpleNamespace(open=open))
    matches,_=p.fixtures();assert len(matches)==1 and len(requests)==2
    assert p.fixtures()[0]==matches and len(requests)==2
    p.budget['requests']=90
    with pytest.raises(provider.ProviderError,match='budget'):p.get('fixtures')


@pytest.mark.parametrize('mode',['stale','errors','paid','network','paginated'])
def test_provider_failure_modes_skip_instead_of_fabricating(monkeypatch,cfg,mode):
    monkeypatch.setenv('API_FOOTBALL_KEY','synthetic')
    def open(request,**kw):
        if mode=='network':raise OSError('private detail')
        result={'response':{'subscription':{'plan':'Pro' if mode=='paid' else 'Free','active':True}}}
        if mode=='errors':result['errors']={'plan':'unsupported'}
        if mode=='paginated':result['paging']={'total':2}
        date=NOW-timedelta(days=1) if mode=='stale' else NOW
        return Response(result,{'Date':format_datetime(date.astimezone(timezone.utc))})
    p=provider.APIFootball(cfg,{},NOW,opener=SimpleNamespace(open=open))
    with pytest.raises(provider.ProviderError):p.fixtures()


def test_graph_creation_confirmation_and_page_identity_resolution(monkeypatch):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic-user')
    values=[{'id':'999'},{'access_token':'synthetic-page'},{'id':'123'},{'id':'123_456'}, {'id':'123_456','message':'Hello','is_published':True}];requests=[]
    def open(req,**kw):requests.append(req);return Response(values.pop(0))
    client=publisher.PageFeed(SimpleNamespace(open=open))
    identity=client.send({'caption':'Hello'})
    assert identity=='123_456' and client.verify(identity,'Hello')
    assert all('synthetic-' not in r.full_url for r in requests)
    assert requests[3].get_header('Authorization')=='Bearer synthetic-page'
    assert 'synthetic-page' not in client.redact('Error synthetic-page synthetic-user')


def test_graph_edit_is_a_single_post_update_and_wrong_page_is_blocked(monkeypatch):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic')
    values=[{'id':'123'},{'success':True}];requests=[]
    def open(req,**kw):requests.append(req);return Response(values.pop(0))
    client=publisher.PageFeed(SimpleNamespace(open=open))
    assert client.send({'operation':'edit','target_id':'123_456','caption':'HT'})=='123_456'
    assert requests[-1].full_url.endswith('/123_456')
    with pytest.raises(publisher.PublishError):client.send({'operation':'edit','target_id':'999_456','caption':'Bad'})


def test_graph_ambiguous_response_is_not_retried(monkeypatch):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic')
    count=[]
    def open(req,**kw):
        count.append(req)
        if len(count)==1:return Response({'id':'123'})
        raise OSError('unknown accepted outcome')
    client=publisher.PageFeed(SimpleNamespace(open=open))
    with pytest.raises(publisher.PublishError,match='ambiguous'):client.send({'caption':'Hello'})
    assert len(count)==2


def test_photo_uses_feed_photo_endpoint_not_reels(monkeypatch,tmp_path):
    monkeypatch.setenv('FACEBOOK_PAGE_ID','123');monkeypatch.setenv('FACEBOOK_PAGE_ACCESS_TOKEN','synthetic')
    image=tmp_path/'original.jpg';image.write_bytes(b'JPEG')
    requests=[];values=[{'id':'123'},{'id':'789','post_id':'123_789'}]
    def open(req,**kw):requests.append(req);return Response(values.pop(0))
    client=publisher.PageFeed(SimpleNamespace(open=open));assert client.send({'caption':'Stats','image':str(image)})=='123_789'
    assert requests[-1].full_url.endswith('/123/photos') and b'JPEG' in requests[-1].data


def test_dry_run_never_instantiates_page_publisher(monkeypatch,tmp_path,cfg):
    root=source(tmp_path)
    # Build outside scheduler using actual clock override only for this synthetic unit test.
    import facebook_feed.cli as runner
    monkeypatch.setattr(runner,'PageFeed',lambda:pytest.fail('dry run attempted Meta access'))
    monkeypatch.setattr(runner,'build',lambda *a,**kw:(post(), 'unit fixture'))
    monkeypatch.delenv('GH_READ_TOKEN',raising=False)
    assert runner.main(['preview','--kind','community','--source',str(root),'--work',str(tmp_path/'out')])==0
    state=json.loads((tmp_path/'out/checkpoint/state.json').read_text())
    assert not state['posts']


def test_send_is_blocked_without_publish_switches(tmp_path):
    with pytest.raises(ValueError,match='gates'):cli.main(['send','--work',str(tmp_path)])


def test_dry_and_live_state_namespaces_do_not_share_reservations():
    assert storage.namespace('repo/name','main',False)!=storage.namespace('repo/name','main',True)
    assert storage.namespace('repo/name','main',False)!=storage.namespace('repo/name','branch',False)


def test_storage_network_failure_never_becomes_an_empty_ledger(monkeypatch,tmp_path):
    monkeypatch.setattr(storage,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**kw:(_ for _ in ()).throw(OSError('private'))))
    with pytest.raises(storage.StateError,match='blocked'):storage.restore('a/b','main','1','prefix','synthetic',tmp_path)


def test_state_restores_reserved_checkpoint_and_ignores_foreign_branch(monkeypatch,tmp_path):
    prefix=storage.namespace('a/b','main',True)
    artifacts=[{'name':prefix+'1-reserved','expired':False,'created_at':'2026-10-29','id':1,
                'workflow_run':{'head_branch':'main','head_repository_id':1}},
               {'name':prefix+'2-final','expired':False,'created_at':'2026-10-30','id':2,
                'workflow_run':{'head_branch':'other','head_repository_id':1}}]
    monkeypatch.setattr(storage,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**kw:Response({'artifacts':artifacts,'total_count':2})))
    state={'schema':1,'namespace':prefix,'posts':[{'key':'reserved-key','status':'reserved'}]}
    def download(repo,endpoint,path,token):
        assert '/1/' in endpoint
        with zipfile.ZipFile(path,'w') as archive:archive.writestr('state.json',json.dumps(state))
    monkeypatch.setattr(storage,'github_download',download)
    assert storage.restore('a/b','main','1',prefix,'synthetic',tmp_path)==state


def test_new_workflows_keep_independent_state_and_score_safety_gates(cfg):
    assert type(cfg['enabled']) is bool and type(cfg['dry_run']) is bool
    assert not cfg['live']['enabled'] and not cfg['live']['edit_existing']
    assert not cfg['provider']['rights_confirmed'] and not cfg['provider']['account_coverage_verified']
    text=(ROOT/'.github/workflows/facebook-feed-run.yml').read_text()
    assert 'group: facebook-feed-' in text and 'git push' not in text and 'goals-scan' not in text.split('concurrency:',1)[1]
    assert text.index('Save durable reservation')<text.index('Publish or edit only')
    for kind,cron in [('community','15 10 * * *'),('weekly','15 8 * * 1'),('card','15 16 * * 2,4,6'),('live','7,27,47 * * * *')]:
        workflow=yaml.safe_load((ROOT/f'.github/workflows/facebook-{kind}.yml').read_text())
        on=workflow.get('on',workflow.get(True))
        assert on['schedule'][0]['cron']==cron


def test_config_cannot_silently_increase_live_cap_or_free_quota(tmp_path,cfg):
    cfg['live']['max_posts_per_day']=4;p=tmp_path/'config.json';p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError,match='cap'):cli.config(p)
