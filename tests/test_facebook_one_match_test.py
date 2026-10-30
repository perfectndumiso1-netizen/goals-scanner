"""The isolated reach test may send one factual picture, never a replacement Reel."""
from datetime import datetime,timedelta
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import facebook_one_match_test as one
from facebook_feed.content import SAST
from facebook_feed.storage import write
import facebook_post as fb

NOW=datetime(2026,10,30,13,0,tzinfo=SAST)


def request():return dict(request_id='one-test',date='2026-10-30',expires_at='2026-10-30T20:00:00+02:00',fixture_id='one-match',cover={})


def item():
    def stats(form,gf,ga):return dict(form=form,scored=gf,conceded=ga,scored_in=3,wins=2,start='2026-09-20',end='2026-10-27')
    return dict(fixture=dict(id='one-match',home='Home',away='Away',kickoff='2026-10-30 22:00',country='Spain'),home=stats('WWDLL',10,3),away=stats('LLWWD',4,9))


@pytest.mark.parametrize('now',[NOW-timedelta(days=1),NOW+timedelta(days=1),NOW.replace(hour=21)])
def test_one_picture_authorisation_expires(now):
    with pytest.raises(ValueError):one.validate(request(),now)


def test_picture_uses_observed_counts_and_discloses_sample_not_forecast(tmp_path,monkeypatch):
    drawn=[]
    from PIL import Image,ImageDraw
    original=ImageDraw.ImageDraw.text
    def text(self,xy,content,*args,**kw):drawn.append(content);return original(self,xy,content,*args,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',text)
    post=one.build(item(),NOW,tmp_path/'picture.jpg')
    assert Image.open(post['image']).size==(1080,1350)
    assert 'Goals scored: 10 | 4' in drawn and 'Goals conceded: 3 | 9' in drawn
    assert 'sample windows differ' in post['caption']
    assert all(word not in ' '.join(drawn) for word in ('PlayReport','MR 2 ODDS','probability','Over 1.5'))


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    work=tmp_path/'work';work.mkdir()
    monkeypatch.setattr(one,'WORK',work)
    monkeypatch.setattr(one,'validate',lambda *args:None)
    post=one.build(item(),NOW,work/'picture.jpg')
    row=dict(status='reserved',caption_hash=post['caption_hash'],image_hash=post['image_hash'])
    write(work/'checkpoint/state.json',dict(schema=1,namespace='test-',posts=[row]))
    write(work/'plan.json',dict(request=request(),post=post,cover=None))
    return work


def test_photo_is_sent_once_and_known_id_saved_before_readback(prepared,monkeypatch):
    calls=[]
    class Page:
        def send(self,post):calls.append('POST');return '123_456'
        def verify(self,*a):
            state=json.loads((prepared/'checkpoint/state.json').read_text())
            assert state['posts'][0]['post_id']=='123_456'
            calls.append('GET')
    monkeypatch.setattr(one,'PageFeed',Page)
    monkeypatch.setattr(fb,'publish',lambda *a:pytest.fail('No new Reel allowed'))
    one.send()
    assert calls==['POST','GET']
    assert json.loads((prepared/'checkpoint/state.json').read_text())['posts'][0]['status']=='verified'
    with pytest.raises(ValueError):one.send()
    assert calls==['POST','GET']


def test_ambiguous_photo_send_is_never_retried(prepared,monkeypatch):
    calls=[]
    def send(post):calls.append('POST');raise OSError('private-network-details')
    monkeypatch.setattr(one,'PageFeed',lambda:SimpleNamespace(send=send))
    with pytest.raises(SystemExit):one.send()
    assert calls==['POST']
    assert json.loads((prepared/'checkpoint/state.json').read_text())['posts'][0]['status']=='unknown'
    with pytest.raises(ValueError):one.send()
    assert calls==['POST']


def test_existing_reservation_blocks_another_picture(tmp_path,monkeypatch):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setattr(one,'WORK',tmp_path)
    monkeypatch.setattr(one,'validate',lambda *a:None)
    for key in ('GITHUB_REPOSITORY','GITHUB_REF_NAME','GITHUB_REPOSITORY_ID','GH_READ_TOKEN'):monkeypatch.setenv(key,'synthetic')
    monkeypatch.setenv('GITHUB_REF_NAME','main')
    monkeypatch.setattr(one,'restore',lambda *a:dict(schema=1,namespace='test-',posts=[dict(status='reserved')]))
    monkeypatch.setattr(one,'verified_fixtures',lambda *a:pytest.fail('Already reserved; no new content'))
    monkeypatch.setattr(one,'outputs',lambda prefix,send:pytest.fail('Must not send') if send else None)
    one.prepare()
    assert json.loads((tmp_path/'checkpoint/state.json').read_text())['posts'][0]['status']=='reserved'


def test_one_off_workflow_cannot_start_from_push_or_unpause_general_feed():
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/facebook-one-match-test.yml').read_text())
    assert list(workflow.get('on',workflow.get(True)))==['workflow_dispatch']
    steps=workflow['jobs']['test']['steps']
    reserve=next(i for i,s in enumerate(steps) if s.get('id')=='reserve')
    send=next(i for i,s in enumerate(steps) if 'facebook_one_match_test.py send' in s.get('run',''))
    assert reserve<send and "steps.reserve.conclusion == 'success'" in steps[send]['if']
    config=json.loads((root/'config/facebook-feed.json').read_text())
    assert set(config['authorized_kinds'])=={'results','live'}
    assert not config['app_scores']['rights_confirmed'] and not config['app_scores']['coverage_verified']
    assert not config['live']['edit_existing']


def test_authorised_automation_keeps_scanner_cron_and_three_edition_rules():
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/scan.yml').read_text())
    events=workflow.get('on',workflow.get(True))
    assert events['schedule']==[{'cron':'*/30 * * * *'}]
    assert workflow['concurrency']=={'group':'goals-scan','cancel-in-progress':False}
    assert workflow['jobs']['scan']['env']['RUN_HOURS']=='7,12,17'
    assert workflow['jobs']['scan']['env']['FACEBOOK_AUTOMATION']=='1'
    scanner=(root/'scanner.py').read_text()
    assert 'hour >= 16' in scanner or 'now.hour < 16' in scanner
