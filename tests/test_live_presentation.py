"""Synthetic screenshot-style fixtures, not real match results or search-volume evidence."""
from datetime import timedelta
import pytest
from facebook_feed import cli, policy, provider
from facebook_feed.live_presentation import caption, hashtags
from test_facebook_feed import NOW, raw_match


def match(**changes):
    return dict(id='1',home='Home',away='Away',home_goals=3,away_goals=1,status='2H',elapsed=75,
                competition='Division 2',country='Egypt',kickoff=(NOW-timedelta(minutes=100)).isoformat(),
                fixture_id='app-1',source='api-football',halftime=[1,0],fulltime=None,
                statistics={'corners':[4,2],'yellow_cards':[1,0],'red_cards':[0,0],
                            'possession':[60,40],'saves':[2,3]},statistics_at=NOW.isoformat(),**changes)


def test_exact_title_clean_grouped_scoreboard():
    a=match();b={**a,'id':'2','home':'Other Home'};c={**a,'id':'3','country':'Thailand','competition':'Premier League'}
    text=caption([a,b,c])
    assert text.startswith('Live Matches SAST\n\n🇪🇬 Egypt ◆ Division 2\n')
    assert text.count('🇪🇬 Egypt ◆ Division 2')==1
    assert '🇹🇭 Thailand ◆ Premier League' in text
    assert '🔴 75′ | Home 3–1 Away' in text
    assert '↳ 1st half: 1–0 | 2nd half: 2–1' in text
    assert '🚩 Corners 4–2  🟨 Yellow 1–0' in text and '🧤 Saves 2–3' in text
    for unwanted in ('MR 2 ODDS','Mr 2 Odds','PlayReport','Source:','API-FOOTBALL','Which','Periodic','checked','Match stats'):
        assert unwanted not in text
    assert '#EgyptDivision2' in text and '#ThailandPremierLeague' in text


def test_only_posted_leagues_and_at_most_ten_unique_relevant_tags():
    rows=[{**match(),'country':'Country','competition':f'League {i}'} for i in range(20)]
    tags=hashtags(rows)
    assert len(tags)==10 and len(set(t.lower() for t in tags))==10
    assert tags[-3:]==['#LiveScores','#Football','#FootballStats']
    assert '#PremierLeague' not in tags
    assert hashtags([{**match(),'country':'England','competition':'Premier League'}])[0]=='#PremierLeague'
    assert len(set(hashtags([{**match(),'country':'World','competition':'Football'}])))==len(hashtags([{**match(),'country':'World','competition':'Football'}]))


def test_missing_or_malformed_data_never_creates_placeholders_or_fake_halves():
    a=match();a.update(halftime=None,statistics={})
    text=caption([a])
    assert '1st half' not in text and 'Corners' not in text and '0–0' not in text
    a.update(halftime=[4,0],statistics={'corners':[None,2],'possession':[70,70]})
    text=caption([a])
    assert '1st half' not in text and 'Possession' not in text and 'Corners' not in text


@pytest.mark.parametrize('status',['ET','AET','P','PEN'])
def test_extra_time_never_mislabeled_as_second_half(status):
    a=match();a.update(status=status,fulltime=None)
    assert '1st half: 1–0' in caption([a]) and '2nd half' not in caption([a])
    a['fulltime']=[2,1]
    assert '2nd half: 1–1' in caption([a])


def test_halftime_and_stoppage_time_display_without_fabricating_minutes():
    a=match();a.update(status='HT')
    assert '⏸ HT |' in caption([a]) and '2nd half' not in caption([a])
    a.update(status='2H',elapsed=90,added_time=5)
    assert '90+5′' in caption([a])
    a['elapsed']=95
    assert '95′' in caption([a]) and '95+5' not in caption([a])
    a['elapsed']=None
    assert '🔴 2H |' in caption([a]) and 'None' not in caption([a])


def test_optional_score_breakdown_and_saves_use_same_fixture_responses():
    raw=raw_match();raw['score']={'halftime':{'home':1,'away':0},'fulltime':{'home':1,'away':0}}
    raw['fixture']['status']['extra']=2
    m=provider.normalize(raw,NOW)
    assert m['halftime']==[1,0] and m['fulltime']==[1,0] and m['added_time']==2
    raw['score']['halftime']['home']=True
    assert provider.normalize(raw,NOW)['halftime'] is None
    raw['score']['halftime']['home']=99
    assert provider.normalize(raw,NOW)['halftime'] is None
    from test_live_score_stats import stats
    raw['teams']['home']['id']=10;raw['teams']['away']['id']=20
    rows=stats()
    rows[0]['statistics'].append({'type':'Goalkeeper Saves','value':0})
    rows[1]['statistics'].append({'type':'Goalkeeper Saves','value':2})
    assert provider.normalize_statistics(rows,provider.normalize(raw,NOW))['saves']==[0,2]


def test_clock_and_format_changes_do_not_repost_or_enable_edits():
    cfg=cli.config('config/facebook-feed.json')
    cfg['live'].update(publish_every_poll=False,image_required=False)  # Original change-only contract remains selectable.
    a=match();post=policy.score_post([a],{'posts':[]},NOW,cfg)
    state={'posts':[]};entry=policy.reserve(post,state,NOW);entry.update(status='published',post_id='1_2')
    a['elapsed']=76
    assert policy.score_post([a],state,NOW+timedelta(minutes=10),cfg) is None
    # Already-posted old-format snapshots still stop identical scores being reposted for styling.
    for m in entry['snapshot']:
        m.pop('halftime',None);m.pop('fulltime',None)
    assert policy.score_post([a],state,NOW+timedelta(minutes=10),cfg) is None
    assert not cfg['live']['edit_existing']
