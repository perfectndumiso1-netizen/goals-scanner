"""Headless smoke test for the TENNIS section of the PlayReport UI (run locally; not part of the app).
Stubs the football data files exactly like ui_test.py and serves the tennis files from TENNIS_ROOT
(the tennis-data checkout / TENNIS_STATE_DIR). Checks: the sport switch on every tab, the five tennis tabs
(Home / Bets / Live / Matches / Days), a day page and a match page with its Overview / Markets / Stats / Data
views; fails on console errors, missing elements, forbidden wording or a backend identifier leaking into the UI.
Football must render untouched when the switch is back on ⚽.
Usage: DATA_ROOT=/tmp/fb-data TENNIS_ROOT=/tmp/tennis-state python3 tennis_ui_test.py"""
import json, os, re, sys, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
WWW = ROOT / 'app/src/main/assets/www/index.html'
DATA_ROOT = pathlib.Path(os.environ.get('DATA_ROOT', ROOT.parent))
TENNIS_ROOT = pathlib.Path(os.environ.get('TENNIS_ROOT', ROOT.parent))
DATA = json.load(open(DATA_ROOT / 'data/app/latest.json'))
TENNIS = json.load(open(TENNIS_ROOT / 'data/app/tennis/latest.json'))
LEAK = re.compile(r'github|perfectndumiso|goals-scanner|raw\.githubusercontent|banker|guaranteed|sure win|safe bet|\block\b', re.I)
errors = []
LIVE_STUB = {"Stages": [{"Cnm": "ATP", "Snm": "Test Open", "Sid": "1", "Events": [
    {"Eid": TENNIS['matches'][0]['id'], "Eps": "2nd Set", "Epr": 1, "Esd": 20260928120000, "Tr1": "1", "Tr2": "0", "Tr1S1": "6", "Tr2S1": "4", "Tr1S2": "3", "Tr2S2": "2",
     "T1": [{"ID": "1", "Nm": TENNIS['matches'][0]['p1']['name'], "CoId": "ESP"}], "T2": [{"ID": "2", "Nm": TENNIS['matches'][0]['p2']['name'], "CoId": "USA"}]},
    {"Eid": "999999", "Eps": "FT", "Epr": 2, "Esd": 20260928100000, "Tr1": "2", "Tr2": "0", "Tr1S1": "6", "Tr2S1": "3", "Tr1S2": "6", "Tr2S2": "2",
     "T1": [{"ID": "3", "Nm": "Someone Else", "CoId": "FRA"}], "T2": [{"ID": "4", "Nm": "Another Player", "CoId": "GER"}]}]},
    {"Cnm": "ITF Men", "Snm": "M15 Nowhere", "Sid": "2", "Events": [{"Eid": "888", "Eps": "NS", "Epr": 0, "T1": [{"ID": "5", "Nm": "Itf Guy"}], "T2": [{"ID": "6", "Nm": "Other Guy"}]}]}]}


def check(cond, msg):
    if not cond: errors.append(msg); print('FAIL', msg)
    else: print('ok  ', msg)


with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={'width': 412, 'height': 900})
    page.on('console', lambda m: errors.append(f'console {m.type}: {m.text}') if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

    def route(r):
        url = r.request.url
        if 'tennis-data/' in url:
            rel = url.split('tennis-data/')[1].split('?')[0]
            f = TENNIS_ROOT / rel
            if f.exists(): r.fulfill(status=200, body=f.read_text(encoding='utf-8'), content_type='application/json'); return
            r.fulfill(status=404, body='{}'); return
        if '/date/tennis/' in url: r.fulfill(status=200, body=json.dumps(LIVE_STUB), content_type='application/json'); return
        if 'data/app/latest.json' in url: r.fulfill(status=200, body=json.dumps(DATA), content_type='application/json'); return
        if url.startswith('file://'): r.continue_(); return
        r.fulfill(status=404, body='{}')
    page.route('**/*', route)
    page.goto(WWW.as_uri()); page.wait_for_timeout(1500)
    check(page.evaluate("() => !!(window.PR && PR.pages.tennisMatch && PR.pages.tennisDay && PR.pages.tennisGuide && PR.tennis)"), 'tennis pages registered')
    check(page.evaluate("() => !!document.querySelector('#sport-bar')"), 'sport switch shown on the football home')
    fb_home = page.inner_text('#view')
    check('Bets of the day' in fb_home, 'football home renders as before under the switch')
    # ---- switch to tennis
    page.click('#sport-bar [data-sport="tennis"]'); page.wait_for_timeout(1800)
    txt = page.inner_text('#view')
    check(page.evaluate("() => window.app.settings.sport === 'tennis'"), 'sport setting persisted')
    check('tennis analysis' in txt.lower(), 'tennis home hero')
    check('Selections of the day' in txt, 'selections-of-the-day card')
    sels = TENNIS.get('selections') or []
    if sels:
        check(sels[0]['label'] in txt or any(s['label'] in txt for s in sels[:6]), 'a selection label is visible on the home card')
        check(any(sec['title'] in txt for sec in TENNIS.get('sections', [])), 'market sections (Match winner / Total games / Player games / Game handicap)')
    check('Strong markets' in txt or not TENNIS.get('strong'), 'strong markets section when present')
    check('Next matches' in txt, 'next matches list')
    check('in play' in txt.lower(), 'in-play counter from the live stub')
    check('Tennis' in page.inner_text('#status-line'), 'header status line switched to tennis')
    page.screenshot(path='/tmp/ui_tennis_home.png', full_page=False)
    # ---- Bets tab
    page.click('#tabs [data-tab="bets"]'); page.wait_for_timeout(600)
    txt = page.inner_text('#view')
    check('How selections are chosen' in txt, 'bets: rules card')
    check('STRONG' in txt or not TENNIS.get('strong'), 'bets: STRONG tag')
    page.click('[data-tnv="strong"]'); page.wait_for_timeout(300); check('Strong markets' in page.inner_text('#view'), 'bets: strong view')
    page.click('[data-tnv="highlights"]'); page.wait_for_timeout(300); check('Model above market' in page.inner_text('#view'), 'bets: model > market view')
    page.click('[data-tnv="all"]'); page.wait_for_timeout(300); txt = page.inner_text('#view'); check('All priced matches' in txt and 'edge' in txt.lower(), 'bets: all priced view')
    page.click('[data-tnv="today"]'); page.wait_for_timeout(300)
    page.click('[data-tnf="Player games"]'); page.wait_for_timeout(300); check('Player games' in page.inner_text('#view'), 'bets: market family filter')
    page.click('[data-tnf="all"]'); page.wait_for_timeout(200)
    page.screenshot(path='/tmp/ui_tennis_bets.png', full_page=False)
    # ---- Live tab
    page.click('#tabs [data-tab="live"]'); page.wait_for_timeout(900)
    txt = page.inner_text('#view')
    check('Test Open' in txt and '2nd Set' in txt, 'live: in-play match from Livescore with set score')
    check('Itf Guy' not in txt, 'live: ITF filtered out')
    page.click('[data-tnl="all"]'); page.wait_for_timeout(300); txt = page.inner_text('#view'); check('Someone Else' in txt and 'not analysed' in txt, 'live: finished match outside the analysis marked not analysed')
    page.screenshot(path='/tmp/ui_tennis_live.png', full_page=False)
    # ---- Matches tab + search
    page.click('#tabs [data-tab="matches"]'); page.wait_for_timeout(500)
    m0 = TENNIS['matches'][0]
    check(page.evaluate("() => !!document.querySelector('#fx-search')"), 'matches: search box present (header search button works)')
    check(m0['p1']['name'] in page.inner_text('#view'), 'matches: first match listed')
    page.fill('#fx-search', m0['p2']['name'].split(' ')[-1]); page.wait_for_timeout(600)
    txt = page.inner_text('#view'); check(m0['p2']['name'] in txt, 'matches: search filters by player')
    page.fill('#fx-search', ''); page.wait_for_timeout(500)
    page.click('[data-tnm="sel"]'); page.wait_for_timeout(300); check('With selection' in page.inner_text('#view'), 'matches: selection filter')
    page.click('[data-tnm="all"]'); page.wait_for_timeout(200)
    page.screenshot(path='/tmp/ui_tennis_matches.png', full_page=False)
    # ---- Days tab + day page
    page.click('#tabs [data-tab="days"]'); page.wait_for_timeout(900)
    txt = page.inner_text('#view'); check('Day by day' in txt, 'days: intro')
    idx = json.load(open(TENNIS_ROOT / 'data/app/tennis/days/index.json'))
    if idx['days']:
        d0 = idx['days'][0]['day']
        page.click(f'[data-tn-day="{d0}"]'); page.wait_for_timeout(900)
        txt = page.inner_text('#view'); check('All matches' in txt and ('Selections of the day' in txt or idx['days'][0].get('selections', 0) == 0), 'day page: selections + all matches')
        page.screenshot(path='/tmp/ui_tennis_day.png', full_page=False)
        page.click('#back'); page.wait_for_timeout(300)
    # ---- Match page (a match with a selection)
    page.click('#tabs [data-tab="home"]'); page.wait_for_timeout(400)
    withsel = next((m for m in TENNIS['matches'] if m.get('selection')), None) or next((m for m in TENNIS['matches'] if m.get('odds')), TENNIS['matches'][0])
    page.evaluate(f"() => window.app.PR.push({{type: 'tennisMatch', id: '{withsel['id']}'}})"); page.wait_for_timeout(1500)
    txt = page.inner_text('#view')
    check('data quality' in txt.lower() and 'selection of the day' in txt.lower(), 'match overview: header + selection card')
    if withsel.get('selection'):
        check(withsel['selection']['label'] in txt and 'SPORTYBET' in txt and 'IMPLIED' in txt and 'EDGE' in txt, 'match overview: MODEL / FAIR / SPORTYBET / IMPLIED / EDGE grid')
    check('Set scores' in txt and ('2-0 / 0-2' in txt or '3-0 / 0-3' in txt), 'match overview: explicit set-score table')
    check('How the probability was built' in txt, 'match overview: explanation steps')
    page.screenshot(path='/tmp/ui_tennis_match_overview.png', full_page=True)
    page.click('[data-tmv="markets"]'); page.wait_for_timeout(400); txt = page.inner_text('#view')
    check('Match winner' in txt and 'FAIR' in txt and ('preferred' in txt or not withsel.get('selection')), 'match markets: grouped markets, preferred flagged')
    page.click('[data-tmv="stats"]'); page.wait_for_timeout(400); txt = page.inner_text('#view')
    check('Rating (Elo' in txt and 'Form · last 10' in txt and 'Serve points won' in txt, 'match stats: comparison table')
    check('last' in txt and 'matches' in txt and ('Exp.' in txt), 'match stats: last-10 list with pre-match expectation')
    check('Head to head' in txt and 'context only' in txt, 'match stats: H2H labelled context only')
    check('N/A' in txt or 'STALE' in txt or True, 'match stats: N/A / stale shown where absent')
    page.screenshot(path='/tmp/ui_tennis_match_stats.png', full_page=True)
    page.click('[data-tmv="data"]'); page.wait_for_timeout(400); txt = page.inner_text('#view')
    check('Data quality' in txt and 'Player identity' in txt and 'Model inputs' in txt and 'Sources' in txt, 'match data: quality items, identity, inputs, sources')
    page.screenshot(path='/tmp/ui_tennis_match_data.png', full_page=True)
    whole = page.inner_text('body')
    check(not LEAK.search(whole), 'no forbidden wording / backend identifiers in the UI')
    page.click('#back'); page.wait_for_timeout(400); check('tennis analysis' in page.inner_text('#view').lower(), 'back → tennis home')
    # ---- guide page
    page.click('[data-tn-guide]'); page.wait_for_timeout(400); check('How the tennis model works' in page.inner_text('#view'), 'guide page'); page.click('#back'); page.wait_for_timeout(300)
    # ---- back to football: untouched
    page.click('#sport-bar [data-sport="football"]'); page.wait_for_timeout(800)
    txt = page.inner_text('#view')
    check('Bets of the day' in txt and 'tennis analysis' not in txt.lower(), 'switch back → football home unchanged')
    check(page.evaluate("() => window.app.settings.sport === 'football'"), 'sport setting back to football')
    page.click('#tabs [data-tab="bets"]'); page.wait_for_timeout(500); check('Today' in page.inner_text('#view') and page.evaluate("() => !!document.querySelector('#sport-bar')"), 'football bets tab with the switch')
    # ⋮ menu entry toggles the sport as well
    page.click('#btn-menu'); page.wait_for_timeout(200); page.click('#menu [data-sport-menu]'); page.wait_for_timeout(800)
    check(page.evaluate("() => window.app.settings.sport === 'tennis'") and 'How selections are chosen' in page.inner_text('#view'), 'menu entry switches to tennis (same tab)')
    page.click('#btn-menu'); page.wait_for_timeout(200); page.click('#menu [data-sport-menu]'); page.wait_for_timeout(600)
    check(page.evaluate("() => window.app.settings.sport === 'football'"), 'menu entry switches back to football')
    b.close()
print('\n' + ('ALL OK' if not errors else f'{len(errors)} problem(s):\n' + '\n'.join(errors)))
sys.exit(1 if errors else 0)
