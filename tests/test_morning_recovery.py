from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
import recover_morning as recovery
import scanner


@pytest.mark.parametrize('hour,minute,expected', [(0,0,None),(4,59,None),(5,0,'morning'),
    (7,19,'morning'),(7,20,None),(10,59,None),(11,0,'noon'),(12,19,'noon'),(12,20,None),
    (15,59,None),(16,0,'evening'),(17,19,'evening'),(17,20,None),(23,59,None)])

def test_delayed_scheduler_has_a_due_slot(hour,minute,expected):
    assert scanner._reel_slot(datetime(2026,10,29,hour,minute)) == expected


def test_utc_date_rollover_does_not_catch_up_yesterday():
    assert scanner._reel_slot(datetime(2026,10,29,22,1,tzinfo=timezone.utc)) is None


@pytest.fixture
def configured(monkeypatch,tmp_path):
    state = {}
    app=tmp_path/'latest.json'
    app.write_text(json.dumps({'meta':{'generated':'2026-10-29 09:26'}}))
    monkeypatch.setattr(scanner,'APP_FILE',app)
    monkeypatch.setattr(scanner,'_telegram_state',lambda now:(tmp_path/'state.json',state))
    monkeypatch.setattr(recovery.advisor_tracking,'selections',lambda payload:[{'home':'Home','away':'Away'}]*6)
    monkeypatch.setattr(scanner,'reel_mod',SimpleNamespace(video_picks=lambda *a,**kw:([{}]*5,[])))
    monkeypatch.setattr(scanner,'yt_mod',None)
    monkeypatch.setattr(scanner,'drive_mod',None)
    monkeypatch.setattr(scanner,'send_telegram_video',lambda *a,**kw:True)
    monkeypatch.setenv('VIDEO_RECOVERY_REPORT',str(tmp_path/'report.json'))
    monkeypatch.delenv('GITHUB_STEP_SUMMARY',raising=False)
    monkeypatch.setenv('FORCE_DAILY_REEL','false')
    monkeypatch.setenv('DAILY_REEL_EDITION','auto')
    return state,app,tmp_path/'report.json'


def test_recovery_keeps_gate_and_forces_morning_without_resetting_history(monkeypatch,configured):
    state,_,report=configured
    state['briefing_history']={'2026-10-28':[{'home':'Yesterday','away':'Opponent'}]}
    def deliver(payload,now):
        assert recovery.os.environ['FORCE_DAILY_REEL']=='true'
        assert recovery.os.environ['DAILY_REEL_EDITION']=='morning'
        assert '2026-10-28' in state['briefing_history']
        scanner.send_telegram_video('video','caption')
        state['briefing_slots']={'2026-10-29':['morning']}
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',deliver)
    assert recovery.run(datetime(2026,10,29,17,tzinfo=recovery.SAST))==1  # stale source fails closed
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==0
    result=json.loads(report.read_text())
    assert result['status']=='delivered' and result['deliveries']['telegram']['delivered']
    assert recovery.os.environ['FORCE_DAILY_REEL']=='false'
    assert recovery.os.environ['DAILY_REEL_EDITION']=='auto'


def test_existing_slot_is_not_cleared_to_force_a_duplicate(monkeypatch,configured):
    state,_,report=configured
    state['briefing_slots']={'2026-10-29':['morning']}
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('duplicate'))
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==0
    assert json.loads(report.read_text())['status']=='already_delivered'


def test_fewer_than_five_fails_without_publishing_or_marking_sent(monkeypatch,configured):
    state,_,report=configured
    monkeypatch.setattr(scanner.reel_mod,'video_picks',lambda *a,**kw:([],[{'reasons':['no recent H2H']}]))
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('quality gate bypassed'))
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==1
    result=json.loads(report.read_text())
    assert result['status']=='blocked' and result['dropped'][0]['reasons']==['no recent H2H']
    assert not state.get('briefing_slots')


def test_success_is_not_assumed_when_renderer_or_all_deliveries_fail(monkeypatch,configured):
    _,_,report=configured
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:None)
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==1
    assert json.loads(report.read_text())['status']=='not_delivered'


def test_yesterdays_source_cannot_be_relabelled_as_today(monkeypatch,configured):
    _,app,report=configured
    app.write_text(json.dumps({'meta':{'generated':'2026-10-28 22:00'}}))
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('stale source'))
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==1
    assert json.loads(report.read_text())['status']=='blocked'


def test_force_environment_restored_if_delivery_raises(monkeypatch,configured):
    def fail(*a):
        raise RuntimeError('render broke')
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',fail)
    with pytest.raises(RuntimeError,match='render broke'):
        recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))
    assert recovery.os.environ['FORCE_DAILY_REEL']=='false'
    assert recovery.os.environ['DAILY_REEL_EDITION']=='auto'


def test_refresh_h2h_only_adds_real_past_meetings_for_exact_clubs(monkeypatch,tmp_path):
    import shortlist_reel,reel_verify,worldfeed
    now=datetime(2026,10,29,10,tzinfo=recovery.SAST)
    pick={'home':'Kalmar FF','away':'GAIS','country':'Sweden','kickoff':'2026-10-29 20:00'}
    app=tmp_path/'latest.json';app.write_text('{}');(tmp_path/'fx').mkdir()
    path=tmp_path/'fx'/(shortlist_reel._fx_key(pick)+'.json')
    detail={**pick,'div':'LS:sweden/allsvenskan','h2h':[{'date':'2026-05-30','home':'GAIS','away':'Kalmar FF','hg':3,'ag':0}],
            'p':{'O15':.81},'odds':{'over25':1.7}}
    path.write_text(json.dumps(detail))
    monkeypatch.setattr(scanner,'APP_FILE',app)
    monkeypatch.setattr(scanner,'LS_DIR',tmp_path/'ls')
    monkeypatch.setattr(reel_verify,'stats_problems',lambda *a,**kw:['only 1 head-to-head meeting(s) with a score'])
    records={'one':['202605301500','1','GAIS','2','Kalmar FF',3,0,None,None],
             'duplicate':['202605301500','1','GAIS','2','Kalmar FF',3,0,None,None],
             'two':['202408011500','2','Kalmar FF','1','GAIS',1,2,None,None],
             'wrong-club':['202409011500','2','Kalmar United','1','GAIS',2,2,None,None],
             'future':['202710291500','2','Kalmar FF','1','GAIS',2,2,None,None],
             'unplayed':['202510291500','2','Kalmar FF','1','GAIS',None,None,None,None]}
    class Archive:
        def __init__(self,root):pass
        def backfill(self,wanted,now,**kw):return {'added':1,'requests':1}
        def save(self):pass
        def load(self,stage):return {'events':records,'league':'Allsvenskan'}
    monkeypatch.setattr(worldfeed,'Archive',Archive)
    report=recovery.refresh_h2h([pick],now)
    updated=json.loads(path.read_text())
    assert report['refreshed_fixtures']==1 and len(updated['h2h'])==2
    assert updated['h2h_meta']['n']==2
    assert updated['p']==detail['p'] and updated['odds']==detail['odds']
    assert {row['source_event_id'] for row in updated['h2h']}=={'duplicate','two'}


@pytest.mark.parametrize('hour,expected', [(5,'morning'),(11,'noon'),(16,'evening')])
def test_automatic_editions_do_not_force_or_resend(monkeypatch,configured,hour,expected):
    state,app,report=configured
    app.write_text(json.dumps({'meta':{'generated':f'2026-10-29 {hour:02}:00'}}))
    def deliver(payload,now):
        assert recovery.os.environ['FORCE_DAILY_REEL']=='false'
        assert recovery.os.environ['DAILY_REEL_EDITION']==expected
        assert scanner._reel_slot(now)==expected
        scanner.send_telegram_video('video','caption')
        state['briefing_slots']={'2026-10-29':[expected]}
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',deliver)
    now=datetime(2026,10,29,hour,5,tzinfo=recovery.SAST)
    assert recovery.run(now,edition='auto')==0
    assert json.loads(report.read_text())['edition']==expected
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('duplicate edition'))
    assert recovery.run(now,edition='auto')==0
    assert json.loads(report.read_text())['status']=='already_delivered'


def test_auto_after_window_does_not_inspect_source_or_publish(monkeypatch,configured):
    _,app,report=configured;app.unlink()
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('outside window'))
    assert recovery.run(datetime(2026,10,29,18,tzinfo=recovery.SAST),edition='auto')==0
    assert json.loads(report.read_text())['status']=='outside_window'


def test_window_expiring_during_preparation_does_not_force_upload(monkeypatch,configured):
    _,app,report=configured
    app.write_text(json.dumps({'meta':{'generated':'2026-10-29 11:00'}}))
    times=iter([datetime(2026,10,29,12,19,tzinfo=recovery.SAST),datetime(2026,10,29,12,20,tzinfo=recovery.SAST)])
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('window expired'))
    assert recovery.run(edition='auto',clock=lambda:next(times))==0
    assert json.loads(report.read_text())['status']=='window_expired'
    assert recovery.os.environ['FORCE_DAILY_REEL']=='false'


def test_telegram_only_success_is_partial_when_facebook_requested(monkeypatch,configured):
    state,_,report=configured
    monkeypatch.setattr(scanner.facebook_mod,'requested',lambda:True)
    def deliver(payload,now):
        scanner.facebook_mod.publish('portrait','caption')
        scanner.send_telegram_video('landscape','caption')
        state['briefing_slots']={'2026-10-29':['morning']}
    monkeypatch.setattr(scanner.facebook_mod,'publish',lambda *a:scanner.facebook_mod.UploadResult('failed'))
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',deliver)
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==1
    data=json.loads(report.read_text())
    assert data['status']=='partially_delivered' and data['unconfirmed_lanes']==['facebook']
    assert data['deliveries']['telegram']['delivered']
    assert state['briefing_slots']['2026-10-29']==['morning']
    monkeypatch.setattr(scanner,'maybe_send_daily_reel',lambda *a:pytest.fail('Telegram must not replay'))
    assert recovery.run(datetime(2026,10,29,10,tzinfo=recovery.SAST))==0


def test_recovery_workflow_uses_same_bounded_facebook_lane_and_saves_queue_first():
    from pathlib import Path
    text=Path('.github/workflows/recover-morning.yml').read_text()
    assert 'FACEBOOK_AUTOMATION: "1"' in text
    assert 'actions: read' in text
    assert 'group: goals-scan' in text and 'cancel-in-progress: false' in text
    assert 'inputs.edition' in text and "== 'schedule' && 'auto'" in text
    assert text.index('facebook_recovery_queue.py recover') < text.index('python recover_morning.py')
    assert text.index('id: recovery') < text.index('facebook_recovery_queue.py register') < text.index('git -C state add -A')
    assert 'if: always() && steps.recovery.outputs.artifact-id' in text
