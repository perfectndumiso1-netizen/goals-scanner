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
STATS = {'Eid': 'x', 'Stat': [{'Tnb': 1, 'Pss': 61, 'Shon': 5, 'Shof': 4, 'Shbl': 2, 'Cos': 6, 'Fls': 9, 'Ofs': 1, 'Ycs': 1, 'Rcs': 0}, {'Tnb': 2, 'Pss': 39, 'Shon': 2, 'Shof': 3, 'Shbl': 1, 'Cos': 3, 'Fls': 12, 'Ofs': 2, 'Ycs': 3, 'Rcs': 0}]}
INCS = {'Incs': {'1': [{'Min': 12, 'IT': 36, 'Nm': 1, 'Fn': 'John', 'Ln': 'Smith', 'Sc': [1, 0]}, {'Min': 40, 'IT': 39, 'Nm': 2, 'Fn': 'Peter', 'Ln': 'Jones', 'Sc': [1, 1]}]}}
import base64, io
try:
    from PIL import Image, ImageDraw
    _im = Image.new('RGBA', (64, 64), (0, 0, 0, 0)); ImageDraw.Draw(_im).ellipse((4, 4, 60, 60), fill=(30, 77, 140, 255)); _b = io.BytesIO(); _im.save(_b, 'PNG'); PNG = _b.getvalue()
except Exception:
    PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')
LEAK = re.compile(r'github|perfectndumiso|goals-scanner|goals scanner|raw\.githubusercontent', re.I)

errors, shots = [], []
def shot(page, name):
    page.wait_for_timeout(150)
    path = f'/tmp/ui_{name}.png'
    try: page.screenshot(path=path, full_page=True)
    except Exception: page.screenshot(path=path, full_page=False)   # very tall pages exceed Chrome's capture limit
    shots.append(path)
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
        version: () => '1.1.0', dataUrl: () => 'https://data.test/data/app/latest.json', rawBase: () => 'https://data.test/', setPref: () => {}, setTheme: () => {},
        notificationsAllowed: () => true, requestNotifications: () => {}, refreshDone: () => {}, openUrl: (u) => { window.__opened = u; },
        notifyGoal: (eid, score, title, text) => window.__notified.push({eid, score, title, text}),
        notify: (ch, id, title, text, tab) => window.__notified.push({ch, id, title, text, tab}), setString: (k, v) => { window.__str = window.__str || {}; window.__str[k] = v; },
        checkUpdate: () => setTimeout(() => window.__updateInfo({version: '1.1.1', url: 'https://data.test/PlayReport.apk', notes: ''}), 200),
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
        elif 'lsm-static-prod.livescore.com' in url:
            route.fulfill(body=PNG, content_type='image/png')
        elif 'livescore.com' in url:
            route.fulfill(json=INCS if '/incidents/' in url else STATS if '/statistics/' in url else {} if '/lineups/' in url else live_json())
        else:
            errors.append('unexpected request: ' + url); route.abort()
    page.route(re.compile(r'^https?://'), handle)
    page.goto(WWW.as_uri())
    page.wait_for_selector('#view .card', timeout=10000)
    page.wait_for_timeout(800)

    # ---- home
    t = shot(page, 'home')
    for needle in ['Bets of the day', 'Safest bets', 'Next kick-offs']: assert needle in t, f'home missing {needle}'
    assert page.locator('#view .badge img').count() >= 4, 'badges rendered'
    assert page.locator('#view .whatsnew').count() == 1, "what's new card"
    page.click('#wn-close'); page.wait_for_timeout(150); assert page.locator('#view .whatsnew').count() == 0, "what's new dismissed"
    assert page.locator('#status-line').inner_text().startswith('Updated'), 'status line'
    # ---- bets segments
    page.click('#tabs button[data-tab=bets]'); page.wait_for_timeout(200)
    for seg in ['today', 'top', 'safest', 'goals', 'corners', 'cards', 'picks']:
        page.click(f'[data-bv={seg}]'); page.wait_for_timeout(150); t = shot(page, f'bets_{seg}')
        if seg == 'today': assert 'How the card is picked' in t and page.locator('#view .botd tr.tap').count() >= 1 and page.locator('#view .botd-sec').count() >= 2, 'grouped bets of the day card'
        if seg == 'top':
            assert page.locator('#view [data-board]').count() == 7 and page.locator('#view .tbl tr.tap').count() >= 5, 'top leagues board'
            page.click('[data-board=A]'); page.wait_for_timeout(150); t = shot(page, 'bets_top_away'); assert 'Away wins' in t
    page.click('[data-bv=goals]'); page.select_option('#f-hip', '0.8'); page.wait_for_timeout(150); shot(page, 'bets_goals_80')
    page.click('[data-bv=safest]'); page.click('[data-lg=major]'); page.wait_for_timeout(150); t = shot(page, 'bets_safest_major')
    page.click('[data-lg=all]'); page.wait_for_timeout(150); assert page.locator('#view .tbl tr.tap').count() >= 5, 'safest list'
    page.click('#guide-link'); page.wait_for_timeout(200); t = shot(page, 'guide'); assert 'Both teams to score' in t and 'Corners' in t, 'guide page'
    page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    # ---- live
    page.click('#tabs button[data-tab=live]'); page.wait_for_timeout(600); t = shot(page, 'live')
    assert "34'" in t and 'In play'.upper() in t.upper(), 'live tab shows no in-play match'
    page.click('[data-lv=all]'); page.wait_for_timeout(400); t = shot(page, 'live_all'); assert 'in play worldwide' in t and "34'" in t, 'all-in-play view'
    page.click('[data-lv=tracked]'); page.wait_for_timeout(150)
    # ---- matches
    page.click('#tabs button[data-tab=matches]'); page.wait_for_timeout(200); shot(page, 'matches')
    page.fill('#fx-search', DATA['fixtures'][0]['home'][:5]); page.wait_for_timeout(200); t = shot(page, 'matches_search')
    assert DATA['fixtures'][0]['home'] in t, 'search filter'
    page.fill('#fx-search', ''); page.wait_for_timeout(200)
    page.select_option('#fx-sort', 'O25'); page.wait_for_timeout(150); shot(page, 'matches_sort')
    page.select_option('#fx-sort', 'ko'); page.click('[data-mf=safe]'); page.wait_for_timeout(150); t = shot(page, 'matches_safe'); assert '🔒' in t or 'Safest' in t
    page.click('[data-mf=major]'); page.wait_for_timeout(150); shot(page, 'matches_major'); page.click('[data-mf=all]'); page.wait_for_timeout(150)
    assert page.locator('#view .hour-head').count() >= 2, 'hour headers in the time view'
    page.click('[data-mmode=comp]'); page.wait_for_timeout(200); t = shot(page, 'matches_comp')
    assert page.locator('#view .acc-head').count() >= 5, 'country accordions'
    page.click('#acc-all'); page.wait_for_timeout(300); shot(page, 'matches_comp_all')
    heads = page.locator('#view .acc-head'); heads.nth(0).click(); page.wait_for_timeout(150)
    page.click('[data-mmode=time]'); page.wait_for_timeout(150)
    page.click('#tabs button[data-tab=home]'); page.wait_for_timeout(100)
    page.click('#btn-search'); page.wait_for_timeout(200)
    assert page.evaluate('window.app.state.tab') == 'matches' and page.evaluate("document.activeElement && document.activeElement.id") == 'fx-search', 'search button focuses the search box'
    # ---- match page: the first priced match that has not kicked off yet (so the slip can be used)
    fid = page.evaluate("""(() => { const P = window.app.PR; const now = P.tzNow(); const f = P.state.data.fixtures.filter((x) => x.priced && x.data_ok && P.parseLocal(x.kickoff) > now).sort((a, b) => a.kickoff.localeCompare(b.kickoff))[0]; return f && f.id; })()""")
    assert fid, 'an upcoming priced fixture exists'
    page.evaluate(f'window.app.PR.openMatch({json.dumps(fid)})'); page.wait_for_timeout(700); t = shot(page, 'match_overview')
    assert 'expected goals' in t.lower() and 'over 2.5' in t.lower(), 'match overview'
    page.click('#fav-btn'); page.wait_for_timeout(200); assert page.locator('#fav-btn.on').count() == 1, 'favourite toggled on'
    assert 'favs' in (page.evaluate('window.__str || {}') or {}), 'favourites shared with the native side'
    for seg in ['trends', 'markets', 'stats', 'h2h', 'lineups']:
        page.click(f'[data-mv={seg}]'); page.wait_for_timeout(300); t = shot(page, f'match_{seg}')
        if seg == 'trends': assert 'Trends' in t and ('of 10' in t or 'of 5' in t or 'Not enough' in t or 'in the last' in t), 'trends segment'
        if seg == 'h2h': assert 'last 5' in t.lower(), 'h2h/form segment'
        if seg == 'lineups': assert 'line-ups' in t.lower(), 'lineups segment'
        if seg == 'markets':
            assert page.locator('#view .addsel').count() >= 3, 'add-to-slip buttons on markets'
            page.click('#view .addsel >> nth=0'); page.wait_for_timeout(200)
            assert page.locator('#slipbar.show').count() == 1, 'slip bar appears'
            assert page.locator('#view .addsel.on').count() == 1, 'selection marked as added'
            page.click('#view .addsel >> nth=1'); page.wait_for_timeout(200)   # same match -> replaces
            assert page.locator('#view .addsel.on').count() == 1, 'one selection per match'
    page.click('[data-mv=stats]'); page.wait_for_timeout(600); t = shot(page, 'match_stats2')
    assert 'this season' in t.lower() or 'not available' in t or 'Loading' in t, 'season block'
    # ---- bet slip: add a second match from the Bets tab, lock the ticket, check pages
    page.click('#tabs button[data-tab=bets]'); page.click('[data-bv=safest]'); page.wait_for_timeout(200)
    btns = page.locator('#view .addsel:not(.on)'); assert btns.count() >= 1, 'add buttons on safest bets'
    btns.nth(0).click(); page.wait_for_timeout(200)
    page.click('#slip-open'); page.wait_for_timeout(300); t = shot(page, 'slip')
    assert 'Total odds' in t and page.locator('#view .tbl tr').count() >= 2, 'slip page with two legs'
    page.fill('#slip-stake', '50'); page.wait_for_timeout(100)
    page.click('#slip-place'); page.wait_for_timeout(200)
    assert page.locator('#modal:not([hidden])').count() == 1, 'in-app confirm modal shown'
    shot(page, 'slip_confirm')
    page.click('#modal-ok'); page.wait_for_timeout(400); t = shot(page, 'today_after_ticket')
    assert page.evaluate('window.app.state.tab') == 'bets' and 'My tickets' in t and page.locator('#view [data-ticket]').count() >= 1, 'ticket appears under Bets > Today'
    assert page.locator('#slipbar.show').count() == 0, 'slip bar hidden after locking'
    page.click('#view [data-ticket] >> nth=0'); page.wait_for_timeout(300); t = shot(page, 'ticket')
    assert 'Ticket T' in t and any(k in t.lower() for k in ('pending', 'lost', 'won')), 'ticket page after locking'
    assert 'tickets' in (page.evaluate('window.__str || {}') or {}), 'tickets shared with the native side'
    page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    page.click('#btn-menu'); page.click('#menu [data-page=tickets]'); page.wait_for_timeout(200); t = shot(page, 'tickets')
    assert 'My tickets' in t and '1 ticket' in t, 'tickets list'
    page.click('#view [data-ticket]'); page.wait_for_timeout(200); assert 'Total odds' in shot(page, 'ticket2')
    while page.evaluate('window.app.back()'): page.wait_for_timeout(60)
    page.click('#tabs button[data-tab=matches]'); page.wait_for_timeout(200)
    page.click('#view .mrow.tap[data-fx] >> nth=0'); page.wait_for_timeout(600)
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
    page.click('#tabs button[data-tab=home]'); page.wait_for_timeout(200); t = shot(page, 'home2')
    assert 'Your matches' in t and 'Ndumiso Msani' in t, 'home shows favourites and the editor card'
    page.click('#tabs button[data-tab=matches]'); page.click('[data-mf=fav]'); page.wait_for_timeout(200); assert page.locator('#view .mrow').count() >= 1, 'favourites filter'
    page.click('[data-mf=all]'); page.wait_for_timeout(100)
    page.click('#tabs button[data-tab=days]'); page.wait_for_timeout(200); t = shot(page, 'days')
    assert page.locator('[data-day]').count() >= 1, 'days list'
    page.click('[data-day] >> nth=0'); page.wait_for_timeout(700); t = shot(page, 'day_results')
    assert 'Results' in t and 'Bets' in t, 'day page'
    page.click('[data-dv=bets]'); page.wait_for_timeout(200); shot(page, 'day_bets')
    # match page from a day row (only if present in current analysis)
    if page.locator('#view .tap[data-fx]').count():
        page.click('#view .tap[data-fx] >> nth=0'); page.wait_for_timeout(600); t = shot(page, 'day_to_match')
        assert 'Overview' in t, 'day row opens the match page'
        page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    page.evaluate('window.app.back()'); page.wait_for_timeout(100)
    # ---- menu pages
    page.click('#btn-menu'); page.wait_for_timeout(100); shot(page, 'menu')
    assert page.locator('#menu.open').count() == 1, 'menu opens'
    page.click('#menu [data-page=analysis]'); page.wait_for_timeout(800); t = shot(page, 'analysis')
    assert 'PlayReport' in t or 'Safest' in t or 'analysis' in t.lower(), 'analysis page'
    page.evaluate('window.app.back()')
    page.click('#btn-menu'); page.click('#menu [data-page=guide]'); page.wait_for_timeout(200); t = shot(page, 'guide_menu'); assert 'How the probabilities are made' in t
    page.evaluate('window.app.back()')
    page.click('#btn-menu'); page.click('#menu [data-page=performance]'); page.wait_for_timeout(200); t = shot(page, 'performance')
    assert 'Bets of the day' in t and 'Safest bets' in t and 'Parlay' not in t and 'Treble' not in t, 'performance'
    page.evaluate('window.app.back()')
    page.click('#btn-menu'); page.click('#menu [data-page=settings]'); page.wait_for_timeout(200); t = shot(page, 'settings')
    for sel in ['#s-goals', '#s-ht', '#s-ft', '#s-ko', '#s-bets', '#s-reports', '#s-live', '#s-tz', '#s-save', '#s-clear']: assert page.locator(sel).count() == 1, f'settings control {sel}'
    page.click('[data-th=dark]'); page.wait_for_timeout(200)
    assert page.evaluate("document.documentElement.dataset.theme") == 'dark', 'dark theme applied'
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(11, 15, 20)', 'dark background'
    shot(page, 'settings_dark')
    page.evaluate('window.app.back()'); page.evaluate("window.app.setTab('home')"); page.wait_for_timeout(300); shot(page, 'home_dark')
    page.click('#tabs button[data-tab=matches]'); page.wait_for_timeout(200); shot(page, 'matches_dark')
    page.click('#view .mrow.tap >> nth=0'); page.wait_for_timeout(400); shot(page, 'match_dark')
    while page.evaluate('window.app.back()'): page.wait_for_timeout(50)
    page.click('#btn-menu'); page.click('#menu [data-page=settings]'); page.wait_for_timeout(200)
    page.click('[data-th=light]'); page.wait_for_timeout(200)
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == 'rgb(242, 244, 248)', 'light background'
    page.click('[data-th=system]'); page.wait_for_timeout(100)
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
    goals = [n for n in notified if n.get('score')]
    assert goals and goals[-1]['score'] == '2-0', f'goal alert not fired: {notified}'
    notified = goals
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
