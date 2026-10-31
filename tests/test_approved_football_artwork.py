"""Approved templates, broad factual samples and offline crests. No API/Meta calls."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
import club_crests
import facebook_cover as cover
from facebook_feed import comparison_graphic,editorial
from test_football_editorial import cfg,Fake,NOW,raw

ROOT=Path(__file__).resolve().parents[1]


def test_every_bundled_crest_is_pinned_valid_and_no_svg_runtime():
    data=json.loads((club_crests.ROOT/'manifest.json').read_text())
    assert len(data['entries'])==129
    assert {e['country'] for e in data['entries']}=={'England','Spain','Germany','Italy','France','South Africa'}
    for e in data['entries']:
        p=club_crests.ROOT/e['file']
        assert p.suffix=='.png' and p.stat().st_size<512*1024
        assert hashlib.sha256(p.read_bytes()).hexdigest()==e['sha256']
        image=club_crests.read(e['name'],e['country'])
        assert image is not None and max(image.size)<=256 and image.mode=='RGBA'
        assert e['source'].startswith('https://api.github.com/repos/')


@pytest.mark.parametrize('name,country',[('Orlando Pirates','South Africa'),('Kaizer Chiefs','South Africa'),
    ('Arsenal','England'),('Chelsea','England'),('Athletic Club','Spain'),('Barcelona','Spain'),
    ('Bayern München','Germany'),('Inter','Italy'),('Milan','Italy'),('Paris Saint-Germain','France')])
def test_country_qualified_registered_clubs_have_real_crests(name,country):
    assert club_crests.read(name,country) is not None


@pytest.mark.parametrize('name,country',[('Arsenal','Brazil'),('Orlando City','South Africa'),
    ('Kaizer Chief','South Africa'),('Arsenal Women','England'),('Arsenal U21','England'),
    ('Arsenal',None),('Arsenal',''),('../Arsenal','Brazil'),('Made Up Club','England')])
def test_no_fuzzy_country_or_id_substitution(name,country):
    assert club_crests.read(name,country) is None


def test_tampered_or_oversized_crest_is_not_used(tmp_path,monkeypatch):
    (tmp_path/'bad.png').write_bytes(b'not an image')
    monkeypatch.setattr(club_crests,'ROOT',tmp_path)
    monkeypatch.setattr(club_crests,'registry',lambda:{('england','arsenal'):{'file':'bad.png','sha256':'0'*64}})
    assert club_crests.read('Arsenal','England') is None
    monkeypatch.setattr(club_crests,'registry',lambda:{('england','arsenal'):{'file':'../escape.png','sha256':'0'*64}})
    assert club_crests.read('Arsenal','England') is None


@pytest.mark.parametrize('bad',[None,True,False,'not priced','NaN','Infinity',float('inf'),float('nan'),0,-2,1,1001])
def test_cover_never_invents_or_accepts_invalid_combined_price(bad):
    with pytest.raises(ValueError):cover.cover_total([{'odds':bad}])


def test_cover_total_is_exact_filmed_set_not_fixed_example_or_input_metadata():
    picks=[{'odds':1.5},{'odds':'1.7'}]
    assert cover.cover_total(picks)=='2.55'
    picks.append({'odds':1.25})
    from video_card import combined_odds
    assert cover.cover_total(picks)==f'{combined_odds(picks):.2f}'=='3.19'
    assert cover.cover_total([{'odds':1.2,'combined_odds':2.55}])=='1.20'


def test_cover_is_approved_portrait_with_exact_names_total_and_real_badges(tmp_path,monkeypatch):
    picks=[{'home':'Arsenal','away':'Chelsea','country':'England','odds':1.5,'sel':'SECRET MARKET','p':.99},
           {'home':'Orlando Pirates','away':'Kaizer Chiefs','country':'South Africa','odds':1.7}]
    before=deepcopy(picks);texts=[];fn=ImageDraw.ImageDraw.text
    def capture(self,xy,text,*a,**kw):texts.append(str(text));return fn(self,xy,text,*a,**kw)
    monkeypatch.setattr(ImageDraw.ImageDraw,'text',capture)
    path=cover.render_matches(picks,tmp_path/'cover.jpg',now=datetime(2026,10,31))
    assert Image.open(path).size==(1080,1920) and picks==before
    visible=' '.join(texts)
    assert '2.55' in texts and 'Odds combined' in texts and 'MR 2 ODDS' in texts
    assert all(v in visible for p in picks for v in (p['home'],p['away']))
    assert not any(v in visible for v in ('SECRET MARKET','0.99','1.50','1.70','Source:','Checked','PREVIEW'))


@pytest.mark.parametrize('n',[1,5,8])
def test_cover_all_filmed_rows_fit_without_dropping_matches(tmp_path,n):
    picks=[{'home':f'Home {i}','away':f'Away {i}','odds':1.16} for i in range(n)]
    assert cover.render_matches(picks,tmp_path/f'{n}.jpg').is_file()


def test_broader_stats_are_derived_from_same_five_results_no_new_provider_calls(cfg):
    api=Fake()
    # Five same-league results: win, draw, loss, score draw, win.
    scores=['2 - 0','0 - 0','0 - 1','1 - 1','3 - 2']
    for index,score in enumerate(scores):
        r=api.hist['psl'][index*2];r['state']['score']['current']=score;api.details[r['id']]=deepcopy(r)
    post,reason=editorial.build(cfg,{},NOW,api)
    assert post,reason
    s=post['snapshot'][0]['home_sample']
    assert (s['wins'],s['draws'],s['losses'],s['unbeaten'],s['scored_in'],s['clean'])==(2,2,1,4,3,2)
    assert s['scored']==6 and s['conceded']==4 and len(s['matches'])==5
    labels={r[0]:r for r in post['graphic']['rows']}
    assert len(labels)==10 and labels['GOALS PER GAME'][1]=='1.20'
    assert labels['DRAWS'][1]==2 and labels['LOSSES'][1]==1
    assert labels['UNBEATEN MATCHES'][1]==4 and labels['MATCHES SCORED IN'][1]==3
    assert post['caption'].count('• ')==3 and post['graphic']['country']=='South Africa'
    assert len(api.calls)==6 # one day catalog, two history catalogs, three details
    assert not any('shots' in name.lower() or 'possession' in name.lower() for name in labels)


def test_away_result_orientation_for_broader_counts(cfg):
    api=Fake()
    for r in api.hist['psl']:
        r['homeTeam'],r['awayTeam']=r['awayTeam'],r['homeTeam']
        api.details[r['id']]=deepcopy(r)
    post,reason=editorial.build(cfg,{},NOW,api)
    assert post,reason
    s=post['snapshot'][0]['home_sample']
    assert (s['wins'],s['losses'],s['unbeaten'],s['scored_in'])==(0,5,0,0)
    assert (s['scored'],s['conceded'])==(0,10)


def test_broad_card_has_crests_but_no_source_or_check_label(cfg,tmp_path,monkeypatch):
    api=Fake();post,_=editorial.build(cfg,{},NOW,api);spec=post['graphic']
    spec.update(home='Orlando Pirates',away='Kaizer Chiefs')
    seen=[];original=comparison_graphic.paste
    def capture(canvas,name,country,center,size):
        result=original(canvas,name,country,center,size);seen.append((name,country,result));return result
    monkeypatch.setattr(comparison_graphic,'paste',capture)
    path=comparison_graphic.render(spec,tmp_path/'stats.jpg')
    assert Image.open(path).size==(1080,1350)
    assert seen==[('Orlando Pirates','South Africa',True),('Kaizer Chiefs','South Africa',True)]
    spec['rows']*=2
    with pytest.raises(ValueError):comparison_graphic.render(spec,path)



def test_empty_and_generator_prices_never_lose_filmed_selections():
    with pytest.raises(ValueError):cover.cover_total([])
    assert cover.cover_total(iter([{'odds':1.5},{'odds':1.7}]))=='2.55'
