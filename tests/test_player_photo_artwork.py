"""Real club-kit library, exact derby identity and non-overlapping offline artwork."""
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw
import player_photos as photos
from football_derbies import label
from facebook_feed import comparison_graphic
import facebook_cover

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def review_day(monkeypatch):
    original = photos.review_date
    monkeypatch.setattr(photos, 'review_date', lambda value=None: original(value) if value is not None else date(2026, 10, 31))


@pytest.mark.parametrize('team,player', [('Orlando Pirates','Evidence Makgopa'), ('Kaizer Chiefs','Wandile Duba')])
def test_reviewed_real_club_kit_portraits_are_hash_pinned(team,player):
    photo, name = photos.read(team, 'South Africa', on='2026-11-01T15:00:00+02:00')
    assert name == player and photo.mode == 'RGBA' and max(photo.size) <= 800
    entries = json.loads((photos.ROOT/'manifest.json').read_text())['entries']
    entry = next(e for e in entries if e['player'] == player)
    assert hashlib.sha256((photos.ROOT/entry['file']).read_bytes()).hexdigest() == entry['sha256']
    assert entry['source_page'].startswith('https://') and entry['club_kit_verified'] is True
    assert entry['rights_status'].startswith('Not established')  # Owner approval is not a licence.


@pytest.mark.parametrize('team,country', [('Orlando Pirates','England'),('Orlando City','South Africa'),
    ('Kaizer Chief','South Africa'),('Orlando Pirates Women','South Africa'),('Kaizer Chiefs U21','South Africa'),
    ('Arsenal','England'),('Kaizer Chiefs',None)])
def test_no_wrong_club_country_age_group_or_unreviewed_substitute(team,country):
    assert photos.read(team,country) is None


@pytest.mark.parametrize('day', ['2026-10-30','2026-12-01','2028-01-01','bad date',42])
def test_fixture_outside_review_window_falls_back(day):
    assert photos.read('Orlando Pirates','South Africa',on=day) is None


def test_historical_fixture_cannot_revive_expired_association(monkeypatch):
    original=photos.review_date
    monkeypatch.setattr(photos,'review_date',lambda value=None: date(2026,12,1) if value is None else original(value))
    assert photos.read('Orlando Pirates','South Africa',on='2026-11-01') is None


@pytest.fixture
def manifest(tmp_path,monkeypatch):
    data=json.loads((photos.ROOT/'manifest.json').read_text())
    for e in data['entries']:(tmp_path/e['file']).write_bytes((photos.ROOT/e['file']).read_bytes())
    monkeypatch.setattr(photos,'ROOT',tmp_path)
    def save():(tmp_path/'manifest.json').write_text(json.dumps(data))
    save()
    return data,save,tmp_path


@pytest.mark.parametrize('change',[{'club_kit_verified':False},{'owner_requested_use':False},
    {'sha256':'0'*64},{'file':'../escape.png'},{'player':''},{'valid_through':'2026-10-30'}])
def test_unsafe_national_kit_unapproved_tampered_or_stale_asset_omitted(manifest,change):
    data,save,_=manifest;data['entries'][0].update(change);save()
    assert photos.read('Orlando Pirates','South Africa') is None


def test_duplicate_identity_corrupt_missing_manifest_and_symlink_fall_back(manifest):
    data,save,root=manifest
    data['entries'].append(deepcopy(data['entries'][0]));save()
    assert photos.read('Orlando Pirates','South Africa') is None
    data['entries'].pop();save()
    file=root/data['entries'][0]['file'];file.unlink();file.symlink_to(ROOT/'assets/player-photos/evidence-makgopa.png')
    assert photos.read('Orlando Pirates','South Africa') is None
    file.unlink();file.write_bytes(b'corrupt')
    data['entries'][0]['sha256']=hashlib.sha256(b'corrupt').hexdigest();save()
    assert photos.read('Orlando Pirates','South Africa') is None
    (root/'manifest.json').write_text('bad json')
    assert photos.read('Orlando Pirates','South Africa') is None
    (root/'manifest.json').unlink()
    assert photos.read('Orlando Pirates','South Africa') is None


@pytest.mark.parametrize('home,away,country,name',[
    ('Orlando Pirates','Kaizer Chiefs','South Africa','Soweto Derby'),
    ('Arsenal','Tottenham Hotspur','England','North London Derby'),
    ('Manchester United','Manchester City','England','Manchester Derby'),
    ('Liverpool','Everton','England','Merseyside Derby'),
    ('Real Madrid','Atlético Madrid','Spain','Madrid Derby'),
    ('Inter','Milan','Italy','Milan Derby'),('Roma','Lazio','Italy','Rome Derby'),
    ('Arsenal','Chelsea','England',None),('Barcelona','Real Madrid','Spain',None),
    ('Orlando Pirates','Kaizer Chiefs','England',None),('Kaizer Chiefs','Kaizer Chiefs','South Africa',None),
])
def test_derbies_are_exact_symmetric_not_every_big_match(home,away,country,name):
    assert label(home,away,country)==name
    assert label(away,home,country)==name


def test_paste_changes_only_reserved_box_and_keeps_aspect_ratio():
    canvas=Image.new('RGB',(200,200),'white');before=canvas.copy()
    photos.paste(canvas,(Image.new('RGBA',(80,160),'red'),'Test'),(30,20,130,120))
    assert ImageChops.difference(before,canvas).getbbox()==(30,20,130,120)
    assert canvas.getpixel((80,70))==(255,0,0) and canvas.getpixel((31,70))!=(255,0,0)


def spec():
    return dict(home='Orlando Pirates',away='Kaizer Chiefs',country='South Africa',league='Betway Premiership',
        kickoff='2026-10-31T15:30:00+02:00',period='LAST 5 · SAME LEAGUE / SEASON · ALL VENUES',
        rows=[(f'ROW {i}',i,i+1) for i in range(10)])


def test_stats_photos_do_not_change_stats_kickoff_or_readability(tmp_path,monkeypatch):
    visible=[];original=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*args,**kw):visible.append(str(text));return original(self,xy,text,*args,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    data=spec();before=deepcopy(data)
    with_photos=comparison_graphic.render(data,tmp_path/'with.jpg')
    assert data==before
    assert {'Evidence Makgopa','Wandile Duba','SOWETO DERBY'} <= set(visible)
    assert not any('Source:' in t or 'Checked' in t or 'licensed' in t.lower() for t in visible)
    monkeypatch.setattr(photos,'read',lambda *a,**kw:None)
    without=comparison_graphic.render(data,tmp_path/'without.jpg')
    # All numeric rows and sample/kickoff remain pixel-identical, not overlaid.
    assert ImageChops.difference(Image.open(with_photos).crop((0,480,1080,1350)),
        Image.open(without).crop((0,480,1080,1350))).getbbox() is None


@pytest.mark.parametrize('count',[1,5,8])
def test_cover_exact_film_odds_matches_and_photo_density(tmp_path,monkeypatch,count):
    picks=[dict(home='Orlando Pirates',away='Kaizer Chiefs',country='South Africa',odds=1.5)]
    picks += [dict(home=f'Home {i}',away=f'Away {i}',odds=1.2) for i in range(count-1)]
    before=deepcopy(picks);calls=[];original=photos.paste
    def paste(*args):calls.append(args[2]);return original(*args)
    monkeypatch.setattr(photos,'paste',paste)
    path=facebook_cover.render_matches(picks,tmp_path/f'cover-{count}.jpg',now=datetime(2026,10,31))
    assert Image.open(path).size==(1080,1920) and picks==before
    assert len(calls)==(2 if count<=5 else 0)
    assert all(598<box[1]<box[3]<1000 for box in calls)


@pytest.mark.parametrize('aspect,size',[('9:16',(1080,1920)),('16:9',(1920,1080))])
def test_video_overview_keeps_photos_in_club_area_and_prices_unchanged(tmp_path,monkeypatch,aspect,size):
    import shortlist_reel as reel
    pick=dict(home='Orlando Pirates',away='Kaizer Chiefs',country='South Africa',league='Premiership',
        kickoff='2026-10-31T15:30:00+02:00',p=.8,odds=1.5,label='Over 1.5 goals',sel='O15')
    before=deepcopy(pick);boxes=[];original=photos.paste
    def paste(*args):boxes.append(args[2]);return original(*args)
    monkeypatch.setattr(photos,'paste',paste)
    path=tmp_path/'slide.jpg'
    reel.render_pick_overview(pick,1,5,ROOT/'assets/reel/bg_stadium.jpg',
        ROOT/'assets/club-crests/south-africa-orlandopirates.png',
        ROOT/'assets/club-crests/south-africa-kaizerchiefs.png',path,aspect=aspect,chart=[])
    assert pick==before and Image.open(path).size==size and len(boxes)==2
    assert max(b[3] for b in boxes)<(420 if aspect=='9:16' else 350)


def test_all_other_video_declarations_remain_pinned_to_pre_photo_implementation():
    import ast
    source=(ROOT/'shortlist_reel.py').read_text()
    protected=json.loads((ROOT/'tests/fixtures/player-photo-video-invariants.json').read_text())
    declarations={n.name:ast.get_source_segment(source,n) for n in ast.parse(source).body
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n.name!='render_pick_overview'}
    assert set(declarations)==set(protected)
    for name,body in declarations.items():
        assert hashlib.sha256(body.encode()).hexdigest()==protected[name],name


def test_review_boundary_uses_sast_even_when_fixture_is_utc():
    assert photos.read('Orlando Pirates','South Africa',on='2026-11-30T21:59:59Z') is not None
    assert photos.read('Orlando Pirates','South Africa',on='2026-11-30T22:00:00Z') is None
