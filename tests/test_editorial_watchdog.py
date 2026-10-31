"""Offline failure injection: watchdog cannot fabricate delivery or blindly resend."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
import yaml
from facebook_feed import watchdog as w, cli, storage
from facebook_feed.publisher import PageFeed, PublishError
from test_football_editorial import NOW, Fake, cfg

ROOT=Path(__file__).resolve().parents[1]
KEY=f'editorial:{NOW.date()}:psl'


def state():return {'schema':1,'namespace':storage.namespace('owner/repo','main',True),'posts':[]}


def row(s):return s['editorial_delivery']['slots'][KEY]


def attempt(s,at=NOW,run='1-1'):
    assert w.assess(s,at,run)[0]
    w.release_quota_hold(s,s['editorial_delivery']['slots'][w.slot_at(at)[0]])


def entry(status='unknown',**kw):
    return dict(kind='editorial',slot_key=KEY,key='fixture:1',at=NOW.isoformat(),status=status,caption_hash=hashlib.sha256(b'Caption').hexdigest(),**kw)


def test_attempt_is_checkpointable_before_any_provider_work_and_only_current_slot():
    s=state();assert w.assess(s,NOW,'1-1')==(True,'admitted')
    assert row(s)['attempts']==1 and row(s)['quota_hold']['released'] is False
    assert s['highlightly_api']['requests']==33 and not s['posts']
    assert w.assess(s,NOW+timedelta(minutes=5),'2-1')==(False,'retry_backoff')
    assert w.assess(s,NOW.replace(hour=16),'3-1')==(False,'outside_slot')


def test_temporary_source_retry_backoff_and_cap_survive_state_roundtrips():
    s=state()
    for index,minute in enumerate((0,10,30)):
        at=NOW+timedelta(minutes=minute);attempt(s,at,str(index))
        s['highlightly_api']['requests']+=1
        w.record(s,at,[{'status':'skipped','reason':next(iter(w.TRANSIENT))}])
        assert row(s)['attempts']==index+1
        s=json.loads(json.dumps(s))
    report=w.audit(s,NOW+timedelta(minutes=31))
    assert report['incidents'][0]['diagnosis']=='bounded_retries_exhausted'
    assert not w.assess(s,NOW+timedelta(minutes=50),'4')[0]
    assert s['highlightly_api']['requests']==3


def test_crash_holds_are_not_reclaimed_by_a_later_run_or_reset():
    s=state()
    for i,minute in enumerate((0,10,30)):
        assert w.assess(s,NOW+timedelta(minutes=minute),str(i))[0]
        # Hard kill before a final checkpoint: conservative allowance stays spent.
    assert s['highlightly_api']['requests']==99
    assert not w.assess(s,NOW+timedelta(minutes=50),'4')[0]
    assert s['highlightly_api']['requests']==99


def test_100th_allowed_no_101st_and_unused_hold_release_is_single_use():
    s=state();s['highlightly_api']={'utc_date':NOW.date().isoformat(),'requests':99,'remaining':1}
    assert w.assess(s,NOW,'1')[0]
    assert s['highlightly_api']['requests']==100 and row(s)['quota_hold']['amount']==1
    w.release_quota_hold(s,row(s));assert s['highlightly_api']['requests']==99
    with pytest.raises(storage.StateError):w.release_quota_hold(s,row(s))
    s['highlightly_api']['requests']+=1
    w.record(s,NOW,[{'status':'skipped','reason':next(iter(w.TRANSIENT))}])
    assert w.assess(s,NOW+timedelta(minutes=10),'2')==(False,'shared_quota_exhausted')
    assert s['highlightly_api']['requests']==100


def test_real_utc_rollover_only_and_cooldown_preserved():
    s=state();s['highlightly_api']={'utc_date':(NOW-timedelta(days=1)).date().isoformat(),'requests':100,'remaining':0}
    assert w.assess(s,NOW,'1')[0]
    assert s['highlightly_api']['requests']==33
    s=state();s['highlightly_api']={'utc_date':NOW.date().isoformat(),'requests':12,'after':(NOW+timedelta(hours=6)).isoformat()}
    assert w.assess(s,NOW,'1')==(False,'provider_cooldown')
    assert s['highlightly_api']['requests']==12 and row(s)['attempts']==0


@pytest.mark.parametrize('reason',list(w.SAFE_SKIPS))
def test_missing_verified_content_is_a_terminal_skip_not_filler_or_alert(reason):
    s=state();attempt(s);w.record(s,NOW,[{'status':'skipped','reason':reason}])
    assert row(s)['status']=='skipped'
    assert not w.assess(s,NOW+timedelta(minutes=20),'2')[0]
    assert not w.audit(s,NOW+timedelta(minutes=61))['incidents']


def test_unknown_validation_failure_is_not_retried_or_exposed():
    s=state();attempt(s);w.record(s,NOW,[{'status':'skipped','reason':'raw token=do-not-copy'}])
    report=w.audit(s,NOW)
    assert report['incidents'][0]['diagnosis']=='preparation_blocked'
    assert 'do-not-copy' not in json.dumps(report)


@pytest.mark.parametrize('status',['reserved','unknown','published'])
def test_existing_attempt_never_creates_a_new_candidate(status):
    s=state();s['posts']=[entry(status)]
    assert not w.assess(s,NOW,'1')[0]
    assert row(s)['attempts']==0 and not s.get('highlightly_api')
    assert row(s)['status']==('delivered' if status=='published' else 'verifying')


def test_positive_known_id_verifies_without_creation():
    s=state();s['posts']=[entry(post_id='123_45')];calls=[]
    class P:
        def verify_hash(self,i,h):calls.append((i,h))
        def send(self,*a):pytest.fail('No mutation during recovery')
    w.reconcile_known(s,NOW,P)
    assert s['posts'][0]['status']=='published' and len(calls)==1
    assert not w.assess(s,NOW,'1')[0] and row(s)['status']=='delivered'


def test_lost_ack_positive_discovery_has_separate_hash_readback():
    s=state();s['posts']=[entry()];calls=[]
    class P:
        def find_reserved(self,e):calls.append('find');return '123_45'
        def verify_hash(self,i,h):calls.append('verify')
    w.reconcile_known(s,NOW,P)
    assert calls==['find','verify'] and s['posts'][0]['post_id']=='123_45'


@pytest.mark.parametrize('missing_id',[True,False])
def test_empty_feed_or_failed_readback_never_proves_absence_and_checks_are_bounded(missing_id):
    s=state();s['posts']=[entry(**({} if missing_id else {'post_id':'123_45'}))];calls=[]
    class P:
        def find_reserved(self,e):calls.append('find');return None
        def verify_hash(self,*a):calls.append('verify');raise PublishError('unavailable')
    for minute in (0,1,10,11,30,50):w.reconcile_known(s,NOW+timedelta(minutes=minute),P)
    assert len(calls)==3 and s['posts'][0]['status']=='unknown'
    assert s['posts'][0]['delivery_check']['attempts']==3
    assert w.audit(s,NOW+timedelta(minutes=50))['incidents']
    assert not w.assess(s,NOW+timedelta(minutes=50),'new')[0]


def test_reconcile_graph_failure_is_bounded_and_never_cancels_unknown():
    s=state();s['posts']=[entry() for _ in range(5)];calls=[]
    def fail():calls.append(1);raise PublishError('Access denied')
    w.reconcile_known(s,NOW,fail)
    assert len(calls)==3 and all(p['status']=='unknown' for p in s['posts'])


def test_unresolved_other_slot_blocks_then_positive_reconciliation_allows_current_slot():
    s=state();s['posts']=[entry(slot_key_other='unused')];s['posts'][0]['slot_key']='earlier'
    assert not w.assess(s,NOW,'1')[0]
    s['posts'][0]['status']='published';s['posts'][0]['at']=(NOW-timedelta(hours=1)).isoformat()
    assert w.assess(s,NOW+timedelta(minutes=10),'2')[0]


def test_success_is_acknowledged_only_from_published_ledger_not_green_preparation():
    s=state();attempt(s);w.record(s,NOW,[{'status':'reserved'}])
    s['posts']=[entry('reserved')]
    assert w.audit(s,NOW)['counts']['delivered']==0
    s['posts'][0]['status']='published'
    assert w.audit(s,NOW)['counts']['delivered']==1


@pytest.mark.parametrize('failure,status',[('preflight_temporary','waiting'),('expired_before_mutation','waiting'),('facebook_preflight_blocked','needs_attention')])
def test_only_explicit_before_mutation_cancellation_is_retryable(failure,status):
    s=state();attempt(s);w.record(s,NOW,[{'status':'reserved'}])
    s['posts']=[entry('cancelled',delivery_failure=failure)]
    report=w.audit(s,NOW,pipeline_ok=False)
    assert row(s)['status']==status
    assert bool(report['incidents'])==(status=='needs_attention')


def test_missed_triggers_and_midnight_are_detected_without_backfill():
    s=state();w.sync(s,NOW.replace(hour=23))
    next_day=NOW.replace(hour=23)+timedelta(hours=1,minutes=13)
    report=w.audit(s,next_day)
    assert any(i['diagnosis']=='slot_expired_without_delivery' for i in report['incidents'])
    assert w.assess(s,next_day,'new')==(False,'outside_slot')


def test_first_deployment_does_not_invent_failures_for_unmonitored_morning():
    s=state();at=NOW.replace(hour=16)
    assert not w.audit(s,at)['incidents']
    assert not s['editorial_delivery']['slots']


def test_pipeline_failure_alerts_without_claiming_any_facebook_delivery():
    s=state();report=w.audit(s,NOW,pipeline_ok=False)
    assert report['incidents'][-1]['diagnosis']=='workflow_step_failed' and report['counts']['delivered']==0


def publisher(rows):
    p=PageFeed.__new__(PageFeed);p.page='123';calls=[]
    p.call=lambda method,path,fields:(calls.append((method,path,fields)) or {'data':rows})
    return p,calls


def feed_row(**changes):
    return dict(id='123_45',message='Caption',is_published=True,created_time=NOW.isoformat(),**changes)


def test_discovery_is_bounded_get_and_exact_hash_page_time():
    p,calls=publisher([feed_row()]);assert p.find_reserved(entry())=='123_45'
    assert calls[0][0]=='GET' and calls[0][1]=='123/feed' and calls[0][2]['limit']==100
    for change in ({'id':'999_45'},{'message':'Different'},{'is_published':False},{'created_time':(NOW+timedelta(days=1)).isoformat()}):
        value=feed_row();value.update(change);p,_=publisher([value]);assert p.find_reserved(entry()) is None
    p,_=publisher([feed_row(),feed_row()]);assert p.find_reserved(entry()) is None
    p,_=publisher([]);assert p.find_reserved(entry()) is None


class Response(io.BytesIO):
    def __init__(self,value):super().__init__(json.dumps(value).encode())


@pytest.fixture
def alerts_env(monkeypatch):
    monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GITHUB_RUN_ID','12345')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','123:synthetic');monkeypatch.setenv('TELEGRAM_CHAT_ID','456')
    monkeypatch.setenv('GH_READ_TOKEN','synthetic-github')
    return {'incidents':[{'slot':KEY,'diagnosis':'bounded_retries_exhausted','attempts':3}]}


def test_telegram_alert_dedup_and_no_github_credential_forwarding(alerts_env):
    s=state();w.book(s,NOW);calls=[]
    def open(req,timeout):calls.append(req);return Response({'ok':True})
    assert w.notify(alerts_env,s,SimpleNamespace(open=open))=='telegram'
    assert w.notify(alerts_env,s,SimpleNamespace(open=open))=='already_alerted'
    assert len(calls)==1 and calls[0].get_header('Authorization') is None
    assert b'synthetic-github' not in calls[0].data


def test_no_alert_on_legitimate_skip(alerts_env):
    assert w.notify({'incidents':[]},opener=SimpleNamespace(open=lambda *a,**k:pytest.fail('No notification')))=='not_needed'


def test_telegram_failure_uses_one_github_issue_and_no_token_in_body(alerts_env):
    calls=[]
    def open(req,timeout):
        calls.append(req)
        if 'api.telegram.org' in req.full_url:raise OSError('DO NOT LOG SECRET URL')
        return Response([] if req.get_method()=='GET' else {'number':7})
    assert w.notify(alerts_env,state(),SimpleNamespace(open=open))=='github_issue'
    assert [c.get_method() for c in calls]==['POST','GET','POST']
    assert calls[1].get_header('Authorization')=='Bearer synthetic-github'
    assert b'synthetic' not in calls[2].data and b'bounded_retries_exhausted' in calls[2].data


def test_issue_fallback_is_deduplicated_even_without_durable_alert_state(alerts_env,monkeypatch):
    monkeypatch.delenv('TELEGRAM_BOT_TOKEN');captured=[]
    def first(req,timeout):
        if req.get_method()=='GET':return Response([])
        captured.append(json.loads(req.data));return Response({'number':9})
    assert w.notify(alerts_env,opener=SimpleNamespace(open=first))=='github_issue'
    def second(req,timeout):
        assert req.get_method()=='GET'
        return Response([dict(captured[0],number=9)])
    assert w.notify(alerts_env,opener=SimpleNamespace(open=second))=='github_issue'


def test_notification_failure_is_reported_not_pretended_delivered(alerts_env):
    def fail(*a,**k):raise OSError('secret not for logs')
    assert w.notify(alerts_env,opener=SimpleNamespace(open=fail))=='failed'


def env_main(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW
    monkeypatch.setattr(w,'datetime',Clock);monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setattr(w,'PageFeed',lambda:SimpleNamespace())
    for k,v in {'GITHUB_REF_NAME':'main','GITHUB_REPOSITORY':'owner/repo','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','WATCHDOG_REQUEST_PUBLISH':'true','FACEBOOK_FEED_PUBLISH':'true','GH_READ_TOKEN':'synthetic'}.items():monkeypatch.setenv(k,v)


def test_assess_missing_ledger_never_bootstraps_and_audit_alerts(tmp_path,monkeypatch,capsys):
    env_main(monkeypatch);monkeypatch.setattr(storage,'restore',lambda *a:None)
    assert w.main(['assess','--work',str(tmp_path)])==1
    assert not (tmp_path/'checkpoint/state.json').exists()
    monkeypatch.setattr(w,'notify',lambda report,*a,**k:'failed')
    assert w.main(['audit','--work',str(tmp_path)])==1
    assert 'synthetic' not in capsys.readouterr().out
    assert json.loads((tmp_path/'watchdog-report.json').read_text())['notification']=='failed'


def test_branch_and_read_only_gates_do_not_restore_or_use_credentials(tmp_path,monkeypatch):
    env_main(monkeypatch);monkeypatch.setenv('GITHUB_REF_NAME','arena/test')
    monkeypatch.setattr(storage,'restore',lambda *a:pytest.fail('No branch restore'))
    assert w.main(['assess','--work',str(tmp_path)])==0
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('WATCHDOG_REQUEST_PUBLISH','false')
    assert w.main(['assess','--work',str(tmp_path)])==0


def test_durable_admission_then_exact_cli_prepare_releases_only_its_hold(tmp_path,monkeypatch,cfg):
    env_main(monkeypatch);s=state()
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(s))
    monkeypatch.setattr(w,'reconcile_known',lambda *a:None)
    assert w.main(['assess','--work',str(tmp_path)])==0
    saved=json.loads((tmp_path/'checkpoint/state.json').read_text());assert saved['highlightly_api']['requests']>0
    from facebook_feed import editorial
    real=editorial.build
    monkeypatch.setattr(editorial,'build',lambda cfg,state,now:real(cfg,state,now,Fake()))
    storage.write(tmp_path/'config.json',cfg)
    # Restore must not overwrite the admitted state a second time.
    monkeypatch.setattr(storage,'restore',lambda *a:pytest.fail('No duplicate restore'))
    assert cli.main(['prepare','--kind','editorial','--publish','--watchdog-checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    final=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert row(final)['attempts']==1 and row(final)['quota_hold']['released'] is True
    assert final['posts'][0]['status']=='reserved' and final['posts'][0]['run_key']=='123-1'


@pytest.mark.parametrize('tamper',['owner','allowed','namespace','expired','phase'])
def test_invalid_admission_cannot_access_provider(tmp_path,monkeypatch,cfg,tamper):
    env_main(monkeypatch);s=state();assert w.assess(s,NOW,'123-1')[0]
    admission={'run_key':'123-1','allowed':True}
    if tamper=='owner':admission['run_key']='other'
    if tamper=='allowed':admission['allowed']=False
    if tamper=='namespace':s['namespace']='wrong'
    if tamper=='expired':s['editorial_delivery']['slots'][KEY]['status']='delivered'
    storage.write(tmp_path/'checkpoint/state.json',s);storage.write(tmp_path/'watchdog-admission.json',admission);storage.write(tmp_path/'config.json',cfg)
    monkeypatch.setattr(cli,'build',lambda *a,**k:pytest.fail('No provider preparation'))
    phase='preview' if tamper=='phase' else 'prepare'
    with pytest.raises(storage.StateError):cli.main([phase,'--kind','editorial','--publish','--watchdog-checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])


def test_workflow_admission_before_prepare_and_reservation_before_send_shared_mutex():
    doc=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    steps=doc['jobs']['feed']['steps'];names=[s.get('id') for s in steps]
    assert names.index('assess')<names.index('admission')<names.index('prepare')<names.index('reserve')<names.index('send')<names.index('health')
    assert 'steps.admission.conclusion' in next(s['if'] for s in steps if s.get('id')=='prepare')
    assert 'steps.reserve.conclusion' in next(s['if'] for s in steps if s.get('id')=='send')
    assert doc['concurrency']['cancel-in-progress'] is False
    assert doc['permissions']=={'contents':'read','actions':'read'}
    monitor=yaml.safe_load((ROOT/'.github/workflows/facebook-watchdog.yml').read_text());on=monitor.get('on',monitor.get(True))
    assert on['schedule']==[{'cron':'13,33,53 * * * *'}]
    assert on['workflow_run']['branches']==['main']
    assert monitor['jobs']['monitor']['with']['bootstrap'] is False
    assert monitor['jobs']['alert']['permissions']=={'contents':'read','issues':'write'}
    assert 'secrets.' not in json.dumps(monitor['jobs']['alert'])
    assert monitor['jobs']['alert']['steps'][0]['with']['ref']=='main'


@pytest.mark.parametrize('failure,retryable', [('identity',True),('identity',False),('send',True),('verify',True)])
def test_cli_recovery_never_retries_after_mutation_started(tmp_path,monkeypatch,cfg,failure,retryable):
    from facebook_feed import editorial,policy
    env_main(monkeypatch)
    post,_=editorial.build(cfg,{},NOW,Fake())
    post.pop('graphic',None);post['expires_at']=(NOW+timedelta(minutes=4)).isoformat()
    s=state();attempt(s);w.record(s,NOW,[{'status':'reserved'}])
    saved=policy.reserve(post,s,NOW);saved['run_key']='123-1'
    storage.write(tmp_path/'checkpoint/state.json',s);storage.write(tmp_path/'plans.json',[post]);storage.write(tmp_path/'config.json',cfg)
    calls=[]
    class Page:
        def __init__(self):
            if failure=='identity':raise PublishError('identity unavailable',retryable=retryable)
        def send(self,post):
            calls.append('POST')
            if failure=='send':raise PublishError('outcome uncertain',retryable=True)
            return '123_45'
        def verify(self,*args):raise PublishError('read-back unavailable',retryable=True)
    monkeypatch.setattr(cli,'PageFeed',Page)
    args=['send','--kind','editorial','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)]
    assert cli.main(args)==1
    s=json.loads((tmp_path/'checkpoint/state.json').read_text())
    if failure=='identity':
        assert not calls and s['posts'][0]['status']=='cancelled'
        w.audit(s,NOW,False)
        assert row(s)['status']==('waiting' if retryable else 'needs_attention')
    else:
        assert calls==['POST'] and s['posts'][0]['status']=='unknown'
        with pytest.raises(ValueError,match='ownership'):cli.main(args)
        assert calls==['POST']


@pytest.mark.parametrize('temporary',[True,False])
def test_broken_page_credentials_stop_before_spending_provider_allowance(tmp_path,monkeypatch,temporary):
    env_main(monkeypatch);monkeypatch.setattr(storage,'restore',lambda *a:state())
    monkeypatch.setattr(w,'reconcile_known',lambda *a:None)
    def fail():raise PublishError('do not expose raw credential details',retryable=temporary)
    monkeypatch.setattr(w,'PageFeed',fail)
    assert w.main(['assess','--work',str(tmp_path)])==0
    s=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert s['highlightly_api']['requests']==0
    assert row(s)['status']==('waiting' if temporary else 'needs_attention')
    assert json.loads((tmp_path/'watchdog-admission.json').read_text())['allowed'] is False


@pytest.mark.parametrize('method,status,code,expected', [('GET',503,0,True),('GET',429,4,True),('GET',401,190,False),('POST',503,0,False),('POST',429,4,False)])
def test_http_classification_never_labels_a_post_safe_to_retry(method,status,code,expected):
    p=PageFeed.__new__(PageFeed);p.page='123';p.token='synthetic';p.credentials=['synthetic']
    def fail(req,timeout):raise HTTPError(req.full_url,status,'failure',{},io.BytesIO(json.dumps({'error':{'code':code,'message':'synthetic https://private.invalid'}}).encode()))
    p.opener=SimpleNamespace(open=fail)
    with pytest.raises(PublishError) as caught:p.call(method,'123/feed',{})
    assert caught.value.retryable is expected
    assert 'synthetic' not in str(caught.value) and 'private.invalid' not in str(caught.value)


def test_provider_access_quota_and_rate_limit_are_not_blindly_retried():
    for failure,expected in [('authentication_rejected','needs_attention'),('access_restriction','needs_attention'),('rate_or_quota_rejection','waiting')]:
        s=state();attempt(s)
        s['highlightly_api'].update(last_failure=failure,after=(NOW+timedelta(minutes=10)).isoformat())
        w.record(s,NOW,[{'status':'skipped','reason':'Highlightly request rejected; details omitted, no provider/key switching'}])
        assert row(s)['status']==expected
    s=state();attempt(s)
    w.record(s,NOW,[{'status':'skipped','reason':'Highlightly daily budget unavailable; cached data retained'}])
    assert row(s)['status']=='skipped' and row(s)['diagnosis']=='shared_quota_exhausted'


def test_only_new_diagnosis_alerts_not_every_downstream_missed_slot(alerts_env):
    s=state();w.book(s,NOW);calls=[]
    def open(req,timeout):calls.append(req);return Response({'ok':True})
    assert w.notify(alerts_env,s,SimpleNamespace(open=open))=='telegram'
    changed=deepcopy(alerts_env);changed['incidents'].append(dict(changed['incidents'][0],slot=KEY+'other'))
    assert w.notify(changed,s,SimpleNamespace(open=open))=='already_alerted'
    changed['incidents'][0]['diagnosis']='facebook_access_blocked'
    assert w.notify(changed,s,SimpleNamespace(open=open))=='telegram'
    assert len(calls)==2


def test_failed_final_checkpoint_cannot_hide_behind_a_healthy_earlier_audit():
    doc=yaml.safe_load((ROOT/'.github/workflows/facebook-feed-run.yml').read_text())
    assert "steps.final.conclusion != 'success'" in doc['jobs']['feed']['outputs']['watchdog_alert']
    assert any(s.get('id')=='final' and 'always()' in s['if'] for s in doc['jobs']['feed']['steps'])
