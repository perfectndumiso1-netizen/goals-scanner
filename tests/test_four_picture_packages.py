"""Offline four-card editorial contracts. Every club/result here is synthetic."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from facebook_feed import cli, editorial as e, graphics, policy, photo_package
from facebook_feed.editorial_leagues import league_key
from facebook_feed.highlightly_watchlist import LEAGUES as LIVE_LEAGUES
from facebook_feed.match_insights import history, priority, caption
from facebook_feed.publisher import PublishError
from test_nine_match_packages import Fake, NOW, raw, page_with_call, prepare

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():return cli.config(ROOT/'config/facebook-feed.json')


def test_four_cards_share_one_fixture_and_actual_evidence(cfg):
    post,reason=e.build(cfg,{},NOW,Fake());assert post,reason
    assert [g['kind'] for g in post['graphics']]==['team-comparison','recent-results','recent-h2h','venue-form']
    proof=post['snapshot'][0]
    assert post['graphics'][2]['meetings']==proof['h2h']
    assert post['graphics'][3]['home_results']==proof['venue_form']['home']
    assert post['graphics'][3]['away_results']==proof['venue_form']['away']
    assert all(r['venue']=='H' for r in proof['venue_form']['home'])
    assert all(r['venue']=='A' for r in proof['venue_form']['away'])
    assert len(post['fixture_ids'])==1 and post['caption'].count('• ')==3
    assert 'sample' not in post['caption'].lower() and 'Your pick' not in post['caption']
    assert 'Which market looks strongest' in post['caption']
    assert 'odds' not in proof['fixture'] and 'prediction' not in proof['fixture']


def test_all_four_cards_are_readable_branded_and_have_no_public_sample_labels(cfg,tmp_path,monkeypatch):
    post,_=e.build(cfg,{},NOW,Fake());texts=[]
    original=ImageDraw.ImageDraw.text
    def capture(self,xy,value,*a,**kw):texts.append(str(value));return original(self,xy,value,*a,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    for index,spec in enumerate(post['graphics']):
        texts.clear();out=graphics.render(spec,tmp_path/f'card-{index}.jpg')
        assert Image.open(out).size==(1080,1350)
        assert 'MR 2 ODDS' in texts
        assert not any('sample' in t.lower() or 'source:' in t.lower() or 'checked' in t.lower() for t in texts)
        if index==2:
            assert 'RECENT HEAD-TO-HEAD' in texts and '3–1' in texts
        if index==3:
            assert 'HOME & AWAY FORM' in texts
            assert any(t.endswith('· HOME') for t in texts) and any(t.endswith('· AWAY') for t in texts)


@pytest.mark.parametrize('country,name,key',[
    ('Japan','J1 League','japan'),('Netherlands','Eredivisie','eredivisie'),
    ('Norway','Eliteserien','norway'),('Belgium','Pro League','belgium'),
    ('Türkiye','Süper Lig','turkey'),('Czechia','First League','czechia'),
    ('United States','MLS','usa'),('South Korea','K League 1','korea'),
])
def test_broader_exact_country_league_scope_without_changing_live_or_models(country,name,key):
    assert league_key(name,country)==key
    assert set(LIVE_LEAGUES)=={'psl','laliga','epl','bundesliga','ligue1','seriea'}
    row=raw(league=key);row['country']['name']=country;row['league']['name']=name
    assert e.fixture(row)['league']==key


@pytest.mark.parametrize('country,name', [('Australia','A-League'),('England','Eredivisie'),('Brazil','Premier League')])
def test_unknown_or_wrong_country_identity_is_not_guessed(country,name):
    assert league_key(name,country) is None


def test_verified_clear_form_edge_in_smaller_league_beats_big_league_prestige(cfg):
    early=raw(1,'epl',NOW+timedelta(hours=3));later=raw(2,'japan',NOW+timedelta(hours=5))
    api=Fake(today=[early,later]);state={};book=e.cache(state,NOW)
    # Make EPL venue form equal; Japan keeps the stronger home-v-away contrast.
    for r in api.hist['epl']:
        if r['awayTeam']['id']==20:
            r['state']['score']['current']='0 - 2';api.details[r['id']]=deepcopy(r)
    for row in (early,later):
        target=e.fixture(row)
        for season in (2026,2025):history(api,book,target,season)
    assert priority(e.fixture(later),book,NOW)>priority(e.fixture(early),book,NOW)
    post,reason=e.build(cfg,state,NOW,api);assert post,reason
    assert post['fixture_ids']==[2]
    assert '#J1League' in post['caption']


def test_uncached_candidates_are_not_falsely_scored_as_favourites(cfg):
    api=Fake(today=[raw(1,'epl',NOW+timedelta(hours=5)),raw(2,'japan',NOW+timedelta(hours=3))])
    book=e.cache({},NOW)
    assert priority(e.fixture(api.today[0]),book,NOW)==(0,0,0)
    post,reason=e.build(cfg,{},NOW,api);assert post,reason
    assert post['fixture_ids']==[2]


@pytest.mark.parametrize('missing',['h2h','home','away','h2h_score','h2h_future','season_mismatch','duplicate'])
def test_missing_or_conflicting_extra_data_never_downgrades_to_two_pictures(cfg,missing):
    api=Fake();previous=api.previous_hist['psl'];current=api.hist['psl']
    if missing=='h2h':previous[:]=[r for r in previous if {r['homeTeam']['id'],r['awayTeam']['id']}!={10,20}]
    if missing=='home':
        for r in current:
            if r['homeTeam']['id']==10:r['homeTeam'],r['awayTeam']=r['awayTeam'],r['homeTeam'];api.details[r['id']]=deepcopy(r)
        previous[:]=[r for r in previous if r['homeTeam']['id']!=10]
    if missing=='away':
        current[:]=[r for r in current if r['awayTeam']['id']!=20]
        previous[:]=[r for r in previous if r['awayTeam']['id']!=20]
    meeting=next((r for r in previous if {r['homeTeam']['id'],r['awayTeam']['id']}=={10,20}),None)
    if missing=='h2h_score':meeting['state']['score']['current']=None
    if missing=='h2h_future':meeting['date']=(NOW+timedelta(hours=1)).isoformat()
    if missing=='season_mismatch':previous[0]['league']['season']=2024
    if missing=='duplicate':previous[0]['id']=current[0]['id']
    post,reason=e.build(cfg,{},NOW,api)
    assert post is None and reason


def test_caption_is_detailed_balanced_and_uses_singular_human_wording(cfg):
    post,_=e.build(cfg,{},NOW,Fake());proof=post['snapshot'][0]
    away=deepcopy(proof['away_sample'])
    for row,score in zip(away['matches'],[(1,0),(1,1),(0,1),(0,1),(0,1)]):row.update(gf=score[0],ga=score[1])
    text=caption(proof['fixture'],proof['home_sample'],away,proof)
    assert '1 win, 1 draw and 3 losses' in text
    assert 'look stronger' in text and 'weaker side' in text
    assert 'At home' in text and 'Away from home' in text
    assert 'Two or more goals' in text and 'latest league meeting' in text
    assert 'sample' not in text.lower() and 'who will win' not in text.lower()
    assert 'guaranteed' not in text.lower() and 'bookmaker' not in text.lower()


@pytest.mark.parametrize('bad',['future','score','identity','name','duplicate'])
def test_h2h_renderer_fails_closed(cfg,tmp_path,bad):
    post,_=e.build(cfg,{},NOW,Fake());spec=deepcopy(post['graphics'][2]);row=spec['meetings'][0]
    if bad=='future':row['date']=spec['checked_at']
    if bad=='score':row['score']=[True,1]
    if bad=='identity':row['away_id']=999
    if bad=='name':row['home']='Unverified club'
    if bad=='duplicate':spec['meetings'].append(deepcopy(row))
    with pytest.raises(ValueError):graphics.render(spec,tmp_path/'bad.jpg')


def test_venue_renderer_rejects_all_venue_form_disguised_as_home_only(cfg,tmp_path):
    post,_=e.build(cfg,{},NOW,Fake());spec=deepcopy(post['graphics'][3]);spec['home_results'][0]['venue']='A'
    with pytest.raises(ValueError):graphics.render(spec,tmp_path/'bad.jpg')


def test_actual_four_photo_protocol_then_one_feed_and_exact_readback(tmp_path):
    paths=[]
    for n in range(4):
        p=tmp_path/f'{n}.jpg';p.write_bytes(b'image'+bytes([n]));paths.append(str(p))
    calls=[];answers=iter([{'id':str(n)} for n in range(41,45)]+[{'id':'123_99'}])
    def call(*a,**kw):calls.append((a,kw));return next(answers)
    page=page_with_call(call);saved=[];ids=page.stage_package(paths,saved.append)
    assert len(saved)==4 and saved[-1]==['41','42','43','44']
    assert page.send_package({'caption':'Caption','images':paths},ids)=='123_99'
    assert len(calls)==5 and all(b'\r\nfalse\r\n' in c[1]['body'] for c in calls[:4])
    assert json.loads(calls[-1][0][2]['attached_media'])==[{'media_fbid':i} for i in ids]
    attachments=[{'target':{'id':i}} for i in ids]
    data={'id':'123_99','message':'Caption','is_published':True,'attachments':{'data':[{'subattachments':{'data':attachments}}]}}
    page.call=lambda *a,**kw:data
    assert page.verify_package_hash('123_99',hashlib.sha256(b'Caption').hexdigest(),ids)
    attachments.pop()
    with pytest.raises(PublishError):page.verify_package_hash('123_99',hashlib.sha256(b'Caption').hexdigest(),ids)


def test_partial_four_photo_ack_does_not_create_feed_or_reupload(cfg,tmp_path,monkeypatch):
    common=prepare(cfg,tmp_path,monkeypatch);calls=[]
    class Page:
        def stage_package(self,images,checkpoint):
            for i in ('41','42','43'):calls.append(i);checkpoint(list(calls))
            raise PublishError('fourth acknowledgement uncertain')
        def send_package(self,*a):pytest.fail('No feed mutation')
    monkeypatch.setattr(cli,'PageFeed',Page)
    assert cli.main(['stage',*common,'--checkpoint'])==1
    state=json.loads((tmp_path/'checkpoint/state.json').read_text())
    assert state['posts'][0]['media_ids']==['41','42','43']
    with pytest.raises(ValueError):cli.main(['stage',*common,'--checkpoint'])
    assert calls==['41','42','43']


def test_four_picture_reservation_cannot_be_downgraded_to_two(cfg,tmp_path,monkeypatch):
    common=prepare(cfg,tmp_path,monkeypatch)
    post=json.loads((tmp_path/'plans.json').read_text())[0]
    post['images']=post['images'][:2];post['image_sha256s']=post['image_sha256s'][:2]
    (tmp_path/'plans.json').write_text(json.dumps([post]))
    monkeypatch.setattr(cli,'PageFeed',lambda:pytest.fail('No Page contact'))
    with pytest.raises(ValueError):cli.main(['stage',*common,'--checkpoint'])


def test_complete_current_season_does_not_require_older_season_access(cfg):
    api=Fake()
    meeting=raw(1900,'psl',NOW-timedelta(days=45),10,20,'2 - 1','Finished')
    api.hist['psl'].append(meeting);api.details[1900]=deepcopy(meeting)
    original=api.catalog
    def catalog(params):
        if params.get('season')==2025:pytest.fail('No older-season request when current records suffice')
        return original(params)
    api.catalog=catalog
    post,reason=e.build(cfg,{},NOW,api);assert post,reason
    assert len(post['graphics'])==4
    assert post['snapshot'][0]['seasons']==[2026]
    assert 'the current league season' in post['caption']
    assert 'the last two league seasons' not in post['caption']
    assert all(params.get('season')!=2025 for kind,params in api.calls if kind=='catalog')
