from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
import pytest
import advisor_tracking as tracking
import video_card as card
import reel_verify
import shortlist_reel as reel
import scanner

NOW = datetime(2026,10,28,8)


def pick(i=0, **kw):
    return {'home':f'Home {i}', 'away':f'Away {i}', 'country':'England', 'kickoff':'2026-10-28 20:00',
            'sel':'O15', 'label':'Over 1.5 goals', 'p':.83, 'odds':1.20, **kw}


def test_five_matches_near_target():
    chosen = card.choose([pick(i) for i in range(12)])
    assert len(chosen) == 5
    assert card.combined_odds(chosen) == pytest.approx(1.2**5)
    assert len({card.match_key(p) for p in chosen}) == 5


@pytest.mark.parametrize('sel', ['O15','CO85','CHO35','CAO35'])
def test_preferred_markets(sel):
    chosen = card.choose([pick(i,sel=sel) for i in range(5)])
    assert len(chosen) == 5 and {p['sel'] for p in chosen} == {sel}


def test_over25_only_used_as_fallback_and_can_be_55_percent():
    pool = [pick(i) for i in range(5)] + [pick(6, sel='O25',p=.55)]
    assert all(p['sel'] != 'O25' for p in card.choose(pool))
    pool = pool[:4]+pool[-1:]
    chosen = card.choose(pool)
    assert len(chosen)==5 and any(p['sel']=='O25' for p in chosen)
    assert card.choose(pool,allow_fallback=False) == []


@pytest.mark.parametrize('pool', [[pick(i) for i in range(4)], [pick(i,odds=1.5) for i in range(6)],
                                 [pick(i,odds=None) for i in range(6)], [pick(i,odds=1.15) for i in range(6)]])
def test_no_padding_and_no_out_of_range_card(pool):
    assert card.choose(pool)==[]


@pytest.mark.parametrize('sel',['U25','CU85','KO35','BTTS','H','HO05'])
def test_banned_market(sel):
    assert not card.eligible(pick(sel=sel))


def test_alternate_lines_do_not_repeat_matches():
    pool=[pick(i) for i in range(5)]+[pick(i,sel='CO85',p=.9) for i in range(5)]
    chosen=card.choose(pool)
    assert len(chosen)==len({card.match_key(p) for p in chosen})==5
    assert {p['sel'] for p in chosen}=={'CO85'}


def test_slots_are_sast_not_machine_timezone():
    assert scanner._reel_slot(datetime(2026,10,28,6,tzinfo=timezone.utc))=='morning'
    assert scanner._reel_slot(datetime(2026,10,28,14,tzinfo=timezone.utc))=='evening'
    for hour in range(24):
        assert (scanner._reel_slot(datetime(2026,10,28,hour)) is not None)==(hour in (8,16))


def test_tracking_freezes_first_published_price_and_probability():
    book=tracking.update([], [pick()],pd.DataFrame(),NOW)
    changed=tracking.update(book,[pick(odds=1.5,p=.9)],pd.DataFrame(),NOW)
    assert len(changed)==1
    assert changed[0]['odds']==1.2 and changed[0]['p']==.83
    assert tracking.summary(changed)['pending']==1
    assert tracking.summary(changed)['hit_rate'] is None


def test_no_post_kickoff_or_historical_backfill():
    assert tracking.update([], [pick(kickoff='2026-10-27 20:00')],pd.DataFrame(),NOW)==[]


def test_settlement_win_loss_and_missing_corner_stats():
    book=tracking.update([], [pick(0),pick(1),pick(2,sel='CO85')],pd.DataFrame(),NOW)
    results=pd.DataFrame([{'date':'2026-10-28','country':'England','home':f'Home {i}','away':f'Away {i}',
                           'hg':2 if i==0 else 0,'ag':0} for i in range(3)])
    settled=tracking.update(book,[],results,datetime(2026,10,29,8))
    s=tracking.summary(settled)
    assert (s['wins'],s['losses'],s['pending'])==(1,1,1)
    assert s['profit_units']==pytest.approx(-.8)
    assert s['roi']==pytest.approx(-.4)
    assert s['hit_rate']==.5


def test_same_match_different_advisor_lines_tracked_separately():
    book=tracking.update([], [pick(),pick(sel='CO85')],pd.DataFrame(),NOW)
    assert len(book)==2 and set(tracking.summary(book)['markets'])=={'O15','CO85'}


def test_advisor_pool_is_exact_visible_sections():
    payload={'meta':{'generated':'2026-10-28 08:00'},'safe':{'today':{'groups':[{'bets':[pick(i) for i in range(9)]}]},
             'bets':[pick(0),pick(10)]},'shortlist':{'primary':[pick(99)]}}
    chosen=tracking.selections(payload)
    assert len(chosen)==7 and all(p['home']!='Home 99' for p in chosen)


def test_missing_details_fail_closed(tmp_path):
    assert reel.video_picks([pick(i) for i in range(6)],fx_dir=tmp_path/'missing',now=NOW)[0]==[]


def test_no_future_or_stale_stats_and_corners_need_actual_samples():
    from tests.test_reel_gate import detail, PICK, NOW as gate_now
    d=detail()
    p={**PICK,'sel':'CO85'}
    assert any('corner' in reason for reason in reel_verify.stats_problems(p,d,now=gate_now))
    d['corners']={'n':[10,10],'home':5,'away':4}
    assert reel_verify.stats_problems(p,d,now=gate_now)==[]


def test_video_recap_keeps_filmed_price():
    p=pick()
    book=[{**p,'match_date':'2026-10-28','status':'hit','score':'2-1','odds':1.4}]
    recap=tracking.video_results(book,[p])
    assert recap[0]['odds']==1.2 and recap[0]['result']=='hit'


def test_apk_release_verifies_signature_upgrade_and_version():
    wf=Path('.github/workflows/build-app.yml').read_text()
    for text in ('1.6.84','apksigner','zipalign','adb install -r','previous-signature','--min-sdk-version 26'):
        assert text in wf
    assert Path('assets/reel/logo.png').read_bytes()==Path('android/app/src/main/assets/www/logo.png').read_bytes()
