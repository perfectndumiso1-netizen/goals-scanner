"""Headless smoke test for the bundled PlayReport UI (run locally; not part of the app).
Stubs the native bridge, the published data files (latest.json, days/, teams/, reports/) and Livescore;
walks every tab, segment and page; screenshots to /tmp/ui_*.png; fails on console errors, missing
elements or any backend identifier leaking into the rendered UI.
Usage: DATA_ROOT=/tmp/gs-test python3 ui_test.py   (needs playwright + chromium)"""
import json, os, re, sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
WWW = ROOT / 'app/src/main/assets/www/index.html'
DATA_ROOT = pathlib.Path(os.environ.get('DATA_ROOT', ROOT.parent))
DATA = json.load(open(DATA_ROOT / 'data/app/latest.json'))
BASE = 'https://data.test/'

tracked = [f for f in DATA['fixtures'] if f['id'] in set(DATA['tracked']) and f.get('livescore_id')]
live_calls = {'n': 0}
def live_json():
    live_calls['n'] += 1
    evs = []
    for i, f in enumerate(tracked[:6]):
        hg, ag, st = (1, 0, "34'") if i == 0 else ((2, 1, 'FT') if i == 1 else (0, 0, 'NS'))
        if i == 0 and live_calls['n'] > 1: hg = 2
        evs.append({'Eid': str(f['livescore_id']), 'Eps': st, 'Tr1': str(hg), 'Tr2': str(ag), 'T1': [{'Nm': f['home']}], 'T2': [{'Nm': f['away']}]})
    return {'Stages': [{'Snm': 'x', 'Cnm': 'y', 'Events': evs}]}
INCS = {'Incs': {'1': [{'Min': 12, 'IT': 36, 'Nm': 1, 'Fn': 'John', 'Ln': 'Smith', 'Sc': [1, 0]}, {'Min': 40, 'IT': 39, 'Nm': 2, 'Fn': 'Peter', 'Ln': 'Jones', 'Sc': [1, 1]}]}}
LEAK = re.compile(r'github|perfectndumiso|goals-scanner|goals scanner|raw\.githubusercontent', re.I)

errors, shots = [], []
def shot(page, name):
    page.wait_for_timeout(150)
    path = f'/tmp/ui_{name}.png'; page.screenshot(path=path, full_page=True); shots.append(path)
    txt = page.inner_text('body')
    m = LEAK.search(txt)
    if m: errors.append(f'LEAK on {name}: …{txt[max(0, m.start()-40):m.end()+40]}…')
    return txt

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 412, 'height': 915}, device_scale_factor=2)
    page = ctx.new_page()
    page.on('console', lambda m: errors.append('console: ' + m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e)))
    page.add_init_script("""
      window.__notified = [];
      window.Android = {
        version: () => '1.0.3', dataUrl: () => 'https://data.test/data/app/latest.json', rawBase: () => 'https://data.test/',
        notificationsAllowed: () => true, requestNotifications: () => {}, refreshDone: () => {}, openUrl: (u) => { window.__opened = u; },
        notifyGoal: (eid, score, title, text) => window.__notified.push({eid, score, title, text}),
        checkUpdate: () => setTimeout(() => window.__updateInfo({version: '1.0.4', url: 'https://data.test/PlayReport.apk', notes: ''}), 200),
        installUpdate: (u) => { window.__installed = u; setTimeout(() => window.__updateProgress('downloading'), 50); },
      };
    """)
    def handle(route):
        url = route.request.url
        if url.startswith(BASE):
            rel = url[len(BASE):].split('?')[0]
            f = DATA_ROOT / rel
            if f.exists(): route.fulfill(body=f.read_bytes(), content_type='application/json' if rel.endswith('.json') else 'text/plain; charset=utf-8')
            else: route.fulfill(status=404, body='missing')
        elif 'livescore.com' in url:
            route.fulfill(json=INCS if '/incidents/' in url else live_json())
        else:
            errors.append('unexpected request: ' + url); route.abort()
    page.route(re.compile(r'^https?://'), handle)
    page.goto(WWW.as_uri())
    page.wait_for_selector('#view .card', timeout=10000)
    page.wait_for_timeout(800)

    # ---- home
    t = shot(page, 'home')
    for needle in ['Safest trebles', 'Safest bets', 'Next kick-offs']: assert needle in t, f'home missing {needle}'
    assert page.locator('#status-line').inner_text().startswith('Analysis'), 'status line'
    # ---- bets segments
    page.click('#tabs button[data-tab=bets]'); page.wait_for_timeout(200)
    for seg in ['safest', 'trebles', 'high', 'parlays', 'picks']:
        page.click(f'[data-bv={seg}]'); page.wait_for_timeout(150); shot(page, f'bets_{seg}')
    page.click('[data-bv=high]'); page.select_option('#f-hip', '0.8'); page.wait_for_timeout(150); shot(page, 'bets_high_80')
    page.click('[data-bv=safest]'); page.select_option('#f-minodds', '1.5'); page.wait_for_timeout(150); shot(page, 'bets_safest_150')
    # ---- live
    page.click('#tabs button[data-tab=live]'); page.wait_for_timeout(600); t = shot(page, 'live')
    assert "34'" in t and 'In play'.upper() in t.upper(), 'live tab shows no in-play match'
    page.click('[data-lv=trebles]'); page.wait_for_timeout(150); t = shot(page, 'live_trebles'); assert 'Treble 1' in t
    page.click('[data-lv=parlays]'); page.wait_for_timeout(150); shot(page, 'live_parlays')
    page.click('[data-lv=matches]'); page.wait_for_timeout(150)
    # ---- matches
    page.click('#tabs button[data-tab=matches]'); page.wait_for_timeout(200); shot(page, 'matches')
    page.fill('#fx-search', DATA['fixtures'][0]['home'][:5]); page.wait_for_timeout(200); t = shot(page, 'matches_search')
    assert DATA['fixtures'][0]['home'] in t, 'search filter'
    page.fill('#fx-search', ''); page.wait_for_timeout(200)
    page.select_option('#fx-sort', 'O25'); page.wait_for_timeout(150); shot(page, 'matches_sort')
    # ---- match page from matches list
    page.click('#view .list-item.tap[data-fx] >> nth=0'); page.wait_for_timeout(500); t = shot(page, 'match_overview')
    assert 'expected goals' in t.lower() and 'over 2.5' in t.lower(), 'match overview'
    for seg in ['markets', 'stats', 'h2h']:
        page.click(f'[data-mv={seg}]'); page.wait_for_timeout(300); t = shot(page, f'match_{seg}')
    page.click('[data-mv=stats]'); page.wait_for_timeout(600); t = shot(page, 'match_stats2')
    assert 'this season' in t.lower() or 'not available' in t or 'Loading' in t, 'season block'
    # ---- team page via team link
    page.click('#view a.team >> nth=0'); page.wait_for_timeout(600); t = shot(page, 'team_overview')
    assert 'Season splits' in t or 'No season data' in t, 'team page'
    if 'Season splits' in t:
        page.click('[data-tv=matches]'); page.wait_for_timeout(200); shot(page, 'team_matches')
        page.click('[data-tv=table]'); page.wait_for_timeout(200); t = shot(page, 'team_table'); assert 'pts' in t.lower(), 'team table'
        # click another team in the table -> pushes a second team page
        page.click('#view .tbl.table a.team >> nth=3'); page.wait_for_timeout(300); shot(page, 'team_other')
        assert page.evaluate('window.app.state.stack.length') == 3, 'team->team push'
    # back navigation through the stack
    while page.evaluate('window.app.back()'): page.wait_for_timeout(80)
    assert page.evaluate('window.app.state.tab') == 'home', 'back returns to home'
    # ---- days
    page.click('#tabs button[data-tab=days]'); page.wait_for_timeout(200); t = shot(page, 'days')
    assert page.locator('[data-day]').count() >= 1, 'days list'
    page.click('[data-day] >> nth=0'); page.wait_for_timeout(700); t = shot(page, 'day_results')
    assert 'Results' in t and 'Bets' in t, 'day page'
    page.click('[data-dv=bets]'); page.wait_for_timeout(200); shot(page, 'day_bets')
    # match page from a day row (only if present in current analysis)
    if page.locator('#view .tap[data-fx]').count():
        page.click('#view .tap[data-fx] >> nth=0'); page.wait_for_timeout(300); shot(page, 'day_to_match')
        page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    # ---- menu pages
    page.click('#btn-menu'); page.wait_for_timeout(100); shot(page, 'menu')
    assert page.locator('#menu.open').count() == 1, 'menu opens'
    page.click('#menu [data-page=analysis]'); page.wait_for_timeout(800); t = shot(page, 'analysis')
    assert 'PlayReport' in t or 'Safest' in t or 'analysis' in t.lower(), 'analysis page'
    page.click('[data-ak=dossier]'); page.wait_for_timeout(800); shot(page, 'dossier')
    page.evaluate('window.app.back()')
    page.click('#btn-menu'); page.click('#menu [data-page=performance]'); page.wait_for_timeout(200); t = shot(page, 'performance')
    assert 'Safest trebles' in t and 'Parlays' in t, 'performance'
    page.evaluate('window.app.back()')
    page.click('#btn-menu'); page.click('#menu [data-page=settings]'); page.wait_for_timeout(200); t = shot(page, 'settings')
    for sel in ['#s-goals', '#s-live', '#s-tz', '#s-save', '#s-clear']: assert page.locator(sel).count() == 1, f'settings control {sel}'
    assert 'WhatsApp' in t and 'msanindumiso@gmail.com' in t, 'contact card'
    # update flow
    page.wait_for_timeout(4200)  # boot checkUpdate fires after 4 s
    assert page.locator('#banner .update').count() == 1, 'update banner'
    shot(page, 'update_banner')
    page.click('#b-update'); page.wait_for_timeout(200)
    assert page.evaluate('window.__installed') == 'https://data.test/PlayReport.apk', 'install url'
    page.click('#s-save'); page.wait_for_timeout(200)
    # ---- Android back from home returns false (lets the activity finish)
    while page.evaluate('window.app.back()'): page.wait_for_timeout(50)
    assert page.evaluate('window.app.state.tab') == 'home' and page.evaluate('window.app.back()') is False, 'back chain'
    # ---- goal alert: second live poll moves 1-0 -> 2-0
    page.click('#tabs button[data-tab=live]'); page.wait_for_timeout(200)
    page.evaluate('window.app.PR.live.refresh(true)'); page.wait_for_timeout(600)
    notified = page.evaluate('window.__notified')
    assert notified and notified[-1]['score'] == '2-0', f'goal alert not fired: {notified}'
    shot(page, 'live_after_goal')
    # external link routing
    page.click('#btn-menu'); page.click('#menu [data-contact]'); page.wait_for_timeout(100)
    assert page.evaluate('window.__opened') == 'https://wa.me/27738212664', 'whatsapp link'
    # notification tab extra path
    page.evaluate("window.app.setTab('today')"); assert page.evaluate('window.app.state.tab') == 'home'
    b.close()

print('\n'.join(shots))
if errors:
    print('ERRORS:'); print('\n'.join(errors)); sys.exit(1)
print('OK — no console errors, no leaks; goal alert:', notified[-1]['title'], '|', notified[-1]['text'])
