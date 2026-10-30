"""Offline cadence/photo contracts. Synthetic graphics are not match results or Page evidence."""
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib
from pathlib import Path
import pytest
import yaml
from PIL import Image
from facebook_feed import cli,content,graphics,policy,storage
from test_facebook_feed import NOW,raw_match
from facebook_feed.provider import normalize

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def match():
    return {**normalize(raw_match(),NOW),'fixture_id':'app-id','source':'api-football'}


def posted(cfg,now=NOW):
    p=policy.score_post([match()],{'posts':[]},now,cfg)
    state={'posts':[]};entry=policy.reserve(p,state,now);entry.update(status='published',post_id='123_456')
    return p,state


def test_new_production_cadence_and_photo_requirements(cfg):
    assert cfg['live_post_cooldown_minutes']==10 and cfg['live']['max_posts_per_day']==90
    assert cfg['live']['publish_every_poll'] and cfg['live']['image_required']
    assert not cfg['live']['edit_existing'] and cfg['provider']['daily_request_budget']==90
    p,state=posted(cfg)
    new=policy.score_post([match()],state,NOW+timedelta(minutes=10),cfg)
    assert new and new['key']!=p['key']  # Fresh unchanged HT observation still gets a timestamped picture.
    assert policy.allowed(new,state,NOW+timedelta(minutes=10),cfg)[0]
    assert policy.allowed(new,state,NOW+timedelta(minutes=9),cfg)[1]=='feed cooldown'
    assert not policy.allowed(p,state,NOW+timedelta(minutes=20),cfg)[0]


def test_legacy_published_post_cannot_block_for_old_sixty_minutes(cfg):
    p,state=posted(cfg)
    state['posts'][0]['key']='old-format-key'
    assert policy.allowed(policy.score_post([match()],state,NOW+timedelta(minutes=11),cfg),state,NOW+timedelta(minutes=11),cfg)[0]


def test_unknown_attempt_blocks_new_live_updates_even_with_new_bucket(cfg):
    p,state=posted(cfg);state['posts'][0]['status']='unknown'
    new=policy.score_post([match()],state,NOW+timedelta(minutes=20),cfg)
    assert 'unresolved live' in policy.allowed(new,state,NOW+timedelta(minutes=20),cfg)[1]


def test_all_final_scores_are_not_repeated_as_periodic_live(cfg):
    m={**match(),'status':'FT'}
    p=policy.score_post([m],{'posts':[]},NOW,cfg)
    state={'posts':[]};entry=policy.reserve(p,state,NOW);entry.update(status='published',post_id='123_456')
    assert policy.score_post([m],state,NOW+timedelta(minutes=10),cfg) is None


def test_photo_contains_one_exact_caption_match_and_renders_without_external_assets(tmp_path,cfg):
    a=match();b={**a,'id':'2','home':'Other Home','away':'Other Away'}
    post=policy.score_post([a,b],{'posts':[]},NOW,cfg)
    spec=post['graphic']
    assert spec['kind']=='live-score' and spec['match']['id']==a['id']
    assert spec['match']['home_goals']==1 and spec['match']['away_goals']==0
    path=graphics.render(spec,tmp_path/'score.jpg')
    assert Image.open(path).size==(1080,1350) and path.stat().st_size<8*1024*1024
    assert len(post['snapshot'])==2  # Text still covers all selected matches; image highlights exactly one.


def test_picture_long_names_fail_closed_not_truncated(tmp_path,cfg):
    p=policy.score_post([dict(match(),home='X'*500)],{'posts':[]},NOW,cfg)
    with pytest.raises(ValueError,match='fit|exceeds'):
        graphics.render(p['graphic'],tmp_path/'too-long.jpg')


def test_repeated_publication_history_fits_existing_restore_bound(cfg):
    state={'posts':[]}
    rows=[dict(match(),id=str(i),home='Home '+str(i),away='Away '+str(i)) for i in range(30)]
    for n in range(90):
        at=NOW.replace(hour=8,minute=0)+timedelta(minutes=10*n)
        p=policy.score_post(rows,state,at,cfg)
        p['fixture_ids']=['2026-10-30|'+('long-name-'*10)+str(i) for i in range(30)]
        entry=policy.reserve(p,state,at);entry.update(status='published',post_id='123_'+str(n))
        state['posts']=policy.history(state,at)
    assert len(state['posts'])==90 and len(state['posts'][-1]['snapshot'])==30
    import json
    assert len(json.dumps(state,indent=2).encode())<512*1024
    old=deepcopy(state['posts'][0]);old.update(status='unknown',snapshot=rows)
    state['posts'].insert(0,old)
    policy.history(state,NOW.replace(hour=23))
    assert state['posts'][0]['snapshot']==rows  # Never compact unresolved evidence.


def test_image_digest_is_reserved_and_tampering_stops_before_page_request(tmp_path,monkeypatch,cfg):
    now=datetime.now(content.SAST)
    p=policy.score_post([dict(match(),kickoff=(now-timedelta(hours=1)).isoformat())],{'posts':[]},now,cfg)
    p['expires_at']=(now+timedelta(minutes=3)).isoformat()
    image=tmp_path/'score.jpg';image.write_bytes(b'original')
    p.update(image=str(image),image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
    state={'posts':[]};entry=policy.reserve(p,state,now);entry['run_key']='1-1'
    assert entry['image_sha256']==p['image_sha256']
    storage.write(tmp_path/'config.json',cfg);storage.write(tmp_path/'checkpoint/state.json',state);storage.write(tmp_path/'plans.json',[p])
    image.write_bytes(b'changed')
    monkeypatch.setenv('FACEBOOK_FEED_PUBLISH','true');monkeypatch.setenv('GITHUB_RUN_ID','1');monkeypatch.setenv('GITHUB_RUN_ATTEMPT','1')
    monkeypatch.setattr(cli,'in_window',lambda *a:True)
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Page request before image validation'))
    with pytest.raises(ValueError,match='picture'):
        cli.main(['send','--publish','--checkpoint','--config',str(tmp_path/'config.json'),'--work',str(tmp_path)])


def test_photo_publisher_handoff_uses_existing_upload_lane(tmp_path,cfg):
    p=policy.score_post([match()],{'posts':[]},NOW,cfg)
    p['image']=str(graphics.render(p['graphic'],tmp_path/'live.jpg'))
    from facebook_feed.publisher import PageFeed
    client=object.__new__(PageFeed);client.page='123'
    calls=[]
    def call(method,path,**kwargs):
        calls.append((method,path,kwargs));return {'post_id':'123_456'}
    client.call=call
    assert client.send(p)=='123_456'
    assert calls[0][1]=='123/photos' and b'image/jpeg' in calls[0][2]['body']


def test_schedule_and_trusted_backend_fallback_share_existing_engine():
    workflow=yaml.safe_load((ROOT/'.github/workflows/facebook-live.yml').read_text())
    on=workflow.get('on',workflow.get(True))
    assert on['schedule'][0]['cron']=='3-59/10 6-21 * * *'
    assert on['workflow_run']['workflows']==['PlayReport scan (every 30 min)']
    job=workflow['jobs']['content']
    assert "head_branch == 'main'" in job['if'] and 'head_repository.full_name == github.repository' in job['if']
    assert 'conclusion' in job['if'] and job['uses']=='./.github/workflows/facebook-feed-run.yml'
    engine=(ROOT/'.github/workflows/facebook-feed-run.yml').read_text()
    assert "inputs.kind == 'live'" in engine and 'require-hashes' in engine


@pytest.mark.parametrize('field,value',[('max_posts_per_day',91),('image_required',False)])
def test_cadence_cannot_disable_required_photo_or_increase_approved_cap(tmp_path,cfg,field,value):
    cfg['live'][field]=value;storage.write(tmp_path/'config.json',cfg)
    with pytest.raises(ValueError):cli.config(tmp_path/'config.json')
