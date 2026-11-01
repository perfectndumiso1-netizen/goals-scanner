"""Offline evidence, missed-window detection and at-most-once alert safety."""
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import video_delivery_health as health


def now(hour=5, minute=0, day=2):
    return datetime(2026, 11, day, hour, minute, tzinfo=health.SAST)


def ledger(tmp_path):
    path = tmp_path / 'video_delivery.json'
    health.save(path, health.load(path, now(4)))
    return path


def test_legacy_one_lane_markers_are_not_imported_as_channel_confirmations(tmp_path):
    path = ledger(tmp_path)
    (tmp_path/'telegram_state.json').write_text(json.dumps({'briefing_slots':{'2026-11-02':['morning']}}))
    assert health.plan(path, 'run:1', now(7,20)) == ['2026-11-02:morning']
    row = health.load(path)['days']['2026-11-02']['morning']
    assert all(v['status']=='pending' for v in row['lanes'].values())


@pytest.mark.parametrize('hour,minute,expected', [(4,59,[]),(5,0,[]),(7,19,[]),
    (7,20,['morning']),(12,20,['morning','noon']),(17,20,['morning','noon','evening'])])
def test_deadlines_detect_wholly_missed_jobs_without_ever_uploading(tmp_path,hour,minute,expected):
    path = ledger(tmp_path)
    assert health.plan(path, 'run:1', now(hour,minute)) == [f'2026-11-02:{e}' for e in expected]


def test_activation_does_not_spam_historical_windows_but_monitors_current_window(tmp_path):
    path = tmp_path/'health.json'
    assert health.plan(path,'run:1',now(20))==[]
    assert health.load(path)['days']=={}
    # Start mid-window; the current edition's approaching deadline is monitored.
    other = tmp_path/'other.json'
    health.plan(other,'run:1',now(12,0))
    assert health.plan(other,'run:2',now(12,20))==['2026-11-02:noon']


def test_previous_day_missed_window_is_detected_after_midnight(tmp_path):
    path = ledger(tmp_path)
    result = health.plan(path,'run:1',now(0,1,day=3))
    assert result==[f'2026-11-02:{e}' for e in ('morning','noon','evening')]


def test_telegram_success_never_confirms_facebook_and_alert_is_deduplicated(tmp_path):
    path = ledger(tmp_path)
    health.record_lane(path,'2026-11-02','morning','telegram','confirmed','123',now(5,5))
    health.record_lane(path,'2026-11-02','morning','facebook','unconfirmed',now=now(5,5))
    assert health.plan(path,'run:1',now(5,6))==['2026-11-02:morning']
    assert health.plan(path,'run:2',now(5,7))==[]
    messages=[]
    def send(text):
        # This reservation must already be unknown on disk BEFORE the POST.
        assert health.load(path)['days']['2026-11-02']['morning']['alert']['status']=='unknown'
        messages.append(text)
        return True
    assert health.notify(path,'run:1',now(5,7),send)=={'alerts_confirmed':1,'alerts_unconfirmed':0}
    assert 'telegram: confirmed' in messages[0] and 'facebook: unconfirmed' in messages[0]
    assert health.notify(path,'run:1',now(5,8),lambda _:pytest.fail('duplicate alert'))['alerts_confirmed']==0
    assert health.plan(path,'run:3',now(7,21))==[]


def test_alert_requires_matching_checkpoint_owner_not_another_run_or_attempt(tmp_path):
    path=ledger(tmp_path);health.plan(path,'100:1',now(7,20))
    for run_key in ('100:2','101:1'):
        assert health.notify(path,run_key,now(7,21),lambda _:pytest.fail('wrong owner'))['alerts_confirmed']==0


def test_network_timeout_preserves_unknown_alert_and_does_not_leak_or_retry(tmp_path,capsys):
    path=ledger(tmp_path);health.plan(path,'run:1',now(7,20))
    def fail(_):raise TimeoutError('dummy-private-token-in-url')
    assert health.notify(path,'run:1',now(7,21),fail)['alerts_unconfirmed']==1
    assert health.notify(path,'run:1',now(7,22),lambda _:pytest.fail('ambiguous resend'))['alerts_confirmed']==0
    assert health.plan(path,'run:2',now(8))==[]
    assert 'dummy-private' not in capsys.readouterr().out


def test_confirmed_lanes_are_monotonic_and_require_reel_identity(tmp_path):
    path=ledger(tmp_path)
    with pytest.raises(ValueError):health.record_lane(path,'2026-11-02','morning','facebook','confirmed',now=now())
    health.record_lane(path,'2026-11-02','morning','facebook','confirmed','987',now())
    health.record_lane(path,'2026-11-02','morning','facebook','unconfirmed',now=now())
    with pytest.raises(ValueError):health.record_lane(path,'2026-11-02','morning','facebook','confirmed','988',now())
    health.record_lane(path,'2026-11-02','morning','telegram','confirmed','123',now())
    assert health.plan(path,'run:1',now(7,20))==[]
    assert health.load(path)['days']['2026-11-02']['morning']['health']=='confirmed_both_channels'


def test_alert_reservation_is_not_sent_after_delivery_was_reconciled(tmp_path):
    path=ledger(tmp_path);health.plan(path,'run:1',now(7,20))
    for lane in ('telegram','facebook'):
        health.record_lane(path,'2026-11-02','morning',lane,'confirmed','123',now())
    assert health.notify(path,'run:1',now(7,21),lambda _:pytest.fail('obsolete warning'))['alerts_confirmed']==0


def test_crashed_upload_gets_grace_but_is_not_mistaken_for_confirmation(tmp_path):
    path=ledger(tmp_path)
    health.record_lane(path,'2026-11-02','morning','facebook','attempting',now=now(5))
    assert health.plan(path,'run:1',now(5,9))==[]
    assert health.plan(path,'run:2',now(5,10))==['2026-11-02:morning']


def test_blocked_quality_gate_alerts_without_padding_or_media_retries(tmp_path):
    path=ledger(tmp_path)
    health.record_outcome(path,'2026-11-02','noon','blocked',now(11))
    assert '2026-11-02:noon' in health.plan(path,'run:1',now(11,1))


@pytest.mark.parametrize('payload',[{'version':99,'days':{}}, {'version':1,'since':'bad','days':{}},
    {'version':1,'since':now().isoformat(),'days':{'2026-11-02':{'morning':{'lanes':{'facebook':{'status':'confirmed'}}}}}}])
def test_corruption_fails_closed_without_reset(tmp_path,payload):
    path=tmp_path/'ledger.json';text=json.dumps(payload);path.write_text(text)
    with pytest.raises((ValueError,KeyError)):health.plan(path,'run:1',now(7,20))
    assert path.read_text()==text


def test_context_metadata_is_scoped_and_never_contains_credentials(tmp_path):
    path=ledger(tmp_path)
    assert health.identity()=={}
    with health.edition_context(path,'2026-11-02','morning'):
        assert health.identity()=={'edition':'morning','edition_date':'2026-11-02'}
        health.observe('telegram','confirmed','123')
    assert health.identity()=={}
    assert health.load(path)['days']['2026-11-02']['morning']['lanes']['telegram']['receipt_id']=='123'


@pytest.mark.parametrize('ack,status', [({'ok':True,'result':{'message_id':123}},'confirmed'),
    ({'ok':False},'unconfirmed'), ({'ok':True,'result':{}},'unconfirmed')])
def test_native_sender_records_channels_separately_without_changing_media_cleanup(monkeypatch,tmp_path,ack,status):
    import scanner
    path=ledger(tmp_path);landscape=tmp_path/'landscape.mp4';landscape.write_bytes(b'video')
    portrait=tmp_path/'portrait.mp4';portrait.write_bytes(b'portrait')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','dummy-test');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    monkeypatch.setattr(scanner.facebook_mod,'requested',lambda:True)
    monkeypatch.setattr(scanner.facebook_mod,'publish',lambda *a:scanner.facebook_mod.UploadResult('failed'))
    monkeypatch.setattr(scanner.SESSION,'post',lambda *a,**kw:SimpleNamespace(status_code=200,json=lambda:ack))
    with health.edition_context(path,'2026-11-02','morning'):
        assert scanner.send_telegram_video(landscape,'caption',width=1920,height=1080,facebook_path=portrait)
    row=health.load(path)['days']['2026-11-02']['morning']['lanes']
    assert row['telegram']['status']==status and row['facebook']['status']=='unconfirmed'
    assert landscape.exists() and portrait.exists()  # Failed Facebook retains originals.


def test_alert_transport_uses_headers_no_redirects_and_explicit_telegram_ack(monkeypatch):
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','dummy-test');monkeypatch.setenv('TELEGRAM_CHAT_ID','123')
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return b'{"ok":true}'
    def open(request,**kwargs):calls.append(request);return Response()
    monkeypatch.setattr(health,'build_opener',lambda handler:SimpleNamespace(open=open))
    assert health.send_alert('status only')
    assert json.loads(calls[0].data)=={'chat_id':'123','text':'status only'}
    assert health.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid') is None


def test_workflow_checkpoints_before_notify_and_persists_even_after_failure():
    text=Path('.github/workflows/recover-morning.yml').read_text()
    assert 'health:' in text and 'needs.route.outputs.mode' in text
    assert text.index('video_delivery_health plan') < text.index('id: checkpoint') < text.index('video_delivery_health notify')
    assert "steps.checkpoint.outcome == 'success'" in text
    health_job=text[text.index('\n  health:'):]
    assert health_job.index('Checkpoint reservations BEFORE') < health_job.index('video_delivery_health notify')
    assert 'Persist alert receipts even after a timeout' in health_job
    assert 'FACEBOOK_PAGE_ACCESS_TOKEN' not in health_job
    scan=Path('.github/workflows/scan.yml').read_text()
    assert "- name: Publish state\n        if: always() && steps.restore.outcome == 'success'" in scan


def test_scanner_checkpoint_change_preserves_schedule_model_and_force_gates():
    # The single workflow SHA pin is refreshed only for restore-step ID and
    # always-checkpoint semantics. Scheduling, model env and manual force stay locked.
    text=Path('.github/workflows/scan.yml').read_text()
    assert '- cron: "*/30 * * * *"' in text
    assert 'RUN_HOURS: "7,12,17"' in text
    assert 'COVER_DAYS: "60"' in text and 'APP_WINDOW_HOURS: "24"' in text
    assert "FORCE_DAILY_REEL: ${{ github.event.inputs.send_reel || 'false' }}" in text
    assert 'group: goals-scan' in text and 'cancel-in-progress: false' in text
    assert 'FACEBOOK_AUTOMATION: "1"' in text and 'YT_UPLOAD: "0"' in text
    assert text.count('id: restore')==1


def test_fabricated_confirmation_without_evidence_or_id_fails_closed(tmp_path):
    path=ledger(tmp_path)
    data=health.load(path)
    row=health.entry(data,'2026-11-02','morning')
    row['lanes']['facebook']={'status':'confirmed'}
    health.save(path,data)
    with pytest.raises(ValueError):health.plan(path,'run:1',now(7,20))


def test_observation_corruption_is_not_reset_or_used_to_claim_delivery(tmp_path,capsys):
    path=tmp_path/'health.json';path.write_text('{"version":999}')
    with health.edition_context(path,'2026-11-02','morning'):
        health.observe('facebook','confirmed','987')
    assert path.read_text()=='{"version":999}'
    assert 'could not be saved' in capsys.readouterr().out
