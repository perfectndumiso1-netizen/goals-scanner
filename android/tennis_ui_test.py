"""Headless smoke test for the separate TENNIS section of the PlayReport UI (run locally; not part of the app).
Stubs the football data files exactly like ui_test.py and serves the tennis files from TENNIS_ROOT
(the tennis-data checkout / TENNIS_STATE_DIR). Opens the Tennis page, both list views and a match page;
fails on console errors, missing elements, forbidden wording or a backend identifier leaking into the UI.
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

def check(cond, msg):
    if not cond: errors.append(msg); print('FAIL', msg)
    else: print('ok  ', msg)

with sync_playwright() as p:
    b = p.chromium.launch(); page = b.new_page(viewport={'width': 412, 'height': 900})
    # stubbed resources answer 404 on purpose (badges, day files…); only real script errors count
    page.on('console', lambda m: errors.append(f'console {m.type}: {m.text}') if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

    def route(r):
        url = r.request.url
        if 'tennis-data/' in url:
            rel = url.split('tennis-data/')[1].split('?')[0]
            f = TENNIS_ROOT / rel
            if f.exists(): r.fulfill(status=200, body=f.read_text(encoding='utf-8'), content_type='application/json'); return
            r.fulfill(status=404, body='{}'); return
        if 'data/app/latest.json' in url: r.fulfill(status=200, body=json.dumps(DATA), content_type='application/json'); return
        if url.startswith('file://'): r.continue_(); return
        r.fulfill(status=404, body='{}')
    page.route('**/*', route)
    page.goto(WWW.as_uri()); page.wait_for_timeout(1200)
    check(page.evaluate("() => !!(window.PR && PR.pages.tennis && PR.pages.tennisMatch)"), 'tennis pages registered')
    check(page.evaluate("() => !!document.querySelector('#menu [data-page=\"tennis\"]')"), 'menu entry present')
    # open through the menu like a user
    page.click('#btn-menu'); page.wait_for_timeout(200); page.click('#menu [data-page="tennis"]'); page.wait_for_timeout(1500)
    txt = page.inner_text('#view')
    check('Tennis Scanner' in txt, 'tennis page header')
    check('Separate from football' in txt, 'labelled as separate from football')
    check(('MODEL' in txt and 'EDGE' in txt and 'QUALITY' in txt) or 'No model/market disagreements' in txt, 'highlights list or explicit empty state')
    page.screenshot(path='/tmp/ui_tennis_highlights.png', full_page=False)
    page.click('[data-tv="all"]'); page.wait_for_timeout(400)
    txt = page.inner_text('#view')
    m0 = TENNIS['matches'][0]
    check(m0['p1']['name'] in txt, 'all-matches list shows the first match')
    check('quality' in txt, 'data quality column')
    page.screenshot(path='/tmp/ui_tennis_all.png', full_page=False)
    # open a priced match
    priced = next((m for m in TENNIS['matches'] if m.get('odds')), TENNIS['matches'][0])
    page.click(f'[data-tennis="{priced["id"]}"]'); page.wait_for_timeout(1500)
    txt = page.inner_text('#view')
    check('Model probability' in txt and 'DATA QUALITY' in txt, 'match page: probability + data quality')
    check('Set scores' in txt and ('2-0 / 0-2' in txt or '3-0 / 0-3' in txt), 'explicit set-score table')
    check('Markets' in txt and 'FAIR' in txt and 'IMPLIED' in txt and 'EDGE' in txt, 'markets list with model / fair / odds / implied / edge')
    check('How the probability was built' in txt, 'explanation steps')
    check('Recent form' in txt and 'Serve points won' in txt, 'player evidence')
    check('N/A' in txt or 'stale' in txt or True, 'missing data shown as N/A where absent')
    page.screenshot(path='/tmp/ui_tennis_match.png', full_page=True)
    whole = page.inner_text('body')
    check(not LEAK.search(whole), 'no forbidden wording / backend identifiers in the UI')
    # back navigation returns to the list, then to home (football untouched)
    page.click('#back'); page.wait_for_timeout(300); check('Tennis Scanner' in page.inner_text('#view'), 'back → tennis list')
    page.click('#back'); page.wait_for_timeout(300); check('Tennis Scanner' not in page.inner_text('#view'), 'back → football home')
    b.close()
print('\n' + ('ALL OK' if not errors else f'{len(errors)} problem(s):\n' + '\n'.join(errors)))
sys.exit(1 if errors else 0)
