"""08:00 inclusive to midnight exclusive SAST, including event-ID send plans."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import pytest
from facebook_feed import cli,content,event_monitor,highlightly,policy,storage
from test_highlightly import cfg,activate
from test_event_monitor import NOW


@pytest.mark.parametrize('hour,minute,allowed',[(0,0,False),(0,20,False),(2,0,False),(7,59,False),(8,0,True),(23,59,True)])
def test_event_due_boundaries_in_sast(cfg,hour,minute,allowed):
    assert cli.is_due('live',NOW.replace(hour=hour,minute=minute),cfg) is allowed
    utc=NOW.replace(hour=hour,minute=minute).astimezone(timezone.utc)
    assert cli.is_due('live',utc,cfg) is allowed


@pytest.mark.parametrize('hour,minute',[(0,0),(7,59)])
def test_outside_window_no_provider_request_or_usage_history_change_even_preview(cfg,hour,minute):
    activate(cfg);now=NOW.replace(hour=hour,minute=minute)
    class NoAPI:
        def __getattr__(self,name):pytest.fail('No provider access outside coverage')
    state={'posts':[{'status':'unknown'}],'highlightly_api':{'requests':17},'event_api':{'groups':{'primary':{'requests':100}}}}
    before=deepcopy(state)
    assert not highlightly.poll(cfg,state,now,NoAPI())[0]
    assert not event_monitor.poll(cfg,state,now,NoAPI())[0]
    post,reason=cli.build('live',Path('.'),now,cfg,state,preview=True)
    assert post is None and 'outside 08:00' in reason and state==before


@pytest.mark.parametrize('cross_during_credentials',[False,True])
def test_event_id_does_not_bypass_midnight_send_guard(cfg,tmp_path,monkeypatch,cross_during_credentials):
    activate(cfg)
    before=NOW.replace(hour=23,minute=59,second=0,microsecond=0)
    midnight=(before+timedelta(days=1)).replace(hour=0,minute=0)
    class Clock(datetime):
        current=before if cross_during_credentials else midnight
        @classmethod
        def now(cls,tz=None):return cls.current
    monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('GITHUB_RUN_ID','window-test');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    image=tmp_path/'image.jpg';image.write_bytes(b'synthetic-immutable-image')
    post=content.candidate('live','new','new-topic','Factual synthetic score',event_ids=['event-1'],
                           snapshot=[{'source':'highlightly'}],image=str(image),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                           expires_at=(midnight+timedelta(minutes=3)).isoformat())
    state={'posts':[],'live_event_ledger':{'matches':{},'events':{'event-1':{'status':'reserved'}}}}
    entry=policy.reserve(post,state,before);entry['run_key']='window-test-1'
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[post])
    constructed=[]
    class Page:
        def __init__(self):
            constructed.append(True)
            if not cross_during_credentials:pytest.fail('No Page access for an already-closed window')
            Clock.current=midnight
        def send(self,*a):pytest.fail('No mutation after midnight, even with meaningful event IDs')
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(['send','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    saved=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert saved['posts'][0]['status']=='cancelled'
    assert saved['live_event_ledger']['events']['event-1']['status']=='pending'
    assert bool(constructed) is cross_during_credentials



def test_outside_window_prepare_does_not_reconcile_unknown_send_or_read_page(cfg,tmp_path,monkeypatch):
    activate(cfg);now=NOW.replace(hour=2,minute=0)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return now
    monkeypatch.setattr(cli,'datetime',Clock)
    monkeypatch.setenv('GITHUB_REF_NAME','main');monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true')
    monkeypatch.setenv('GH_READ_TOKEN','synthetic-placeholder-read');monkeypatch.setenv('GITHUB_REPOSITORY','synthetic/repo')
    prefix=storage.namespace('synthetic/repo','main',True)
    state={'schema':1,'namespace':prefix,'posts':[{'kind':'live','key':'keep','status':'unknown','post_id':'synthetic-id','caption_hash':'keep',
                                               'event_ids':['unresolved'],'at':(now-timedelta(hours=1)).isoformat()}]}
    monkeypatch.setattr(storage,'restore',lambda *a:deepcopy(state))
    monkeypatch.setattr(cli,'PageFeed',lambda *a:pytest.fail('No Page request/reconciliation outside coverage'))
    storage.write(tmp_path/'config.json',cfg)
    assert cli.main(['prepare','--kind','live','--publish','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])==0
    saved=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert saved['namespace']==prefix and saved['posts']==state['posts'] and 'highlightly_api' not in saved
