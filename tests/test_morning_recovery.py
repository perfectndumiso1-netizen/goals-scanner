from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
import recover_morning as recovery
import scanner


@pytest.mark.parametrize('hour,minute,expected', [(0,0,None),(7,59,None),(8,0,'morning'),
    (9,25,'morning'),(12,0,'morning'),(15,59,'morning'),(16,0,'evening'),(19,15,'evening'),(23,59,'evening')])
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
