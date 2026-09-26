"""Headless smoke test for the bundled PlayReport UI (run locally; not part of the app).
Stubs the data feed, Livescore and the report files; screenshots every tab; checks that no GitHub
identifiers leak into the rendered UI and that no console errors occur.
Usage: python3 ui_test.py  (needs playwright + chromium; screenshots go to /tmp/ui_*.png)"""
import json, os, re, sys, time, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
WWW = ROOT / 'app/src/main/assets/www/index.html'
REPO = ROOT.parent
DATA = json.load(open(REPO / 'data/app/latest.json'))
REPORT = open(REPO / 'reports' / (DATA['history']['reports'][0] + '.md'), encoding='utf-8').read()
DOSSIER = open(REPO / 'reports' / (DATA['history']['reports'][0] + '-parlays.md'), encoding='utf-8').read()

# fake live: first tracked fixture with an id is 1-0 at 34', later 2-0
tracked = [f for f in DATA['fixtures'] if f['id'] in set(DATA['tracked']) and f.get('livescore_id')]
live_calls = {'n': 0}
def live_json():
    live_calls['n'] += 1
    evs = []
    for i, f in enumerate(tracked[:6]):
        hg, ag, st = (1, 0, "34'") if i == 0 else (0, 0, 'NS')
        if i == 0 and live_calls['n'] > 1: hg = 2
        evs.append({'Eid': str(f['livescore_id']), 'Eps': st, 'Tr1': str(hg), 'Tr2': str(ag), 'T1': [{'Nm': f['home']}], 'T2': [{'Nm': f['away']}]})
    return {'Stages': [{'Snm': 'x', 'Cnm': 'y', 'Events': evs}]}
INCS = {'Incs': {'1': [{'Min': 12, 'IT': 36, 'Nm': 1, 'Fn': 'John', 'Ln': 'Smith', 'Sc': [1, 0]}, {'Min': 40, 'IT': 36, 'Nm': 1, 'Fn': 'Peter', 'Ln': 'Jones', 'Sc': [2, 0]}]}}

notified = []
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 412, 'height': 915}, device_scale_factor=2)
    page = ctx.new_page()
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    # native bridge stub
    page.add_init_script("""
      window.__notified = [];
      window.Android = {
        fetch: null, version: () => '1.0.2', dataUrl: () => 'https://data.test/latest.json', rawBase: () => 'https://data.test/',
        notificationsAllowed: () => true, requestNotifications: () => {}, refreshDone: () => {}, openUrl: (u) => { window.__opened = u; },
        notifyGoal: (eid, score, title, text) => window.__notified.push({eid, score, title, text}),
        checkUpdate: () => setTimeout(() => window.__updateInfo({version: '1.0.3', url: 'https://data.test/PlayReport.apk', notes: ''}), 200),
        installUpdate: (u) => { window.__installed = u; setTimeout(() => window.__updateProgress('downloading'), 50); },
      };
      delete window.Android.fetch;  // let the page use window.fetch (intercepted below)
    """)
    def handle(route):
        url = route.request.url
        if 'latest.json' in url: route.fulfill(json=DATA)
        elif '/date/soccer/' in url: route.fulfill(json=live_json())
        elif '/incidents/' in url: route.fulfill(json=INCS)
        elif url.endswith('-parlays.md') or '-parlays.md?' in url: route.fulfill(body=DOSSIER, content_type='text/markdown')
        elif '.md' in url: route.fulfill(body=REPORT, content_type='text/markdown')
        else: route.fulfill(status=404, body='')
    page.route(re.compile(r'^https?://'), handle)
    page.goto(WWW.as_uri())
    page.wait_for_function("window.app && window.app.state.data")
    time.sleep(0.5)
    page.screenshot(path='/tmp/ui_today.png', full_page=False)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); time.sleep(0.2)
    page.screenshot(path='/tmp/ui_today_bottom.png')
    for tab in ['live', 'fixtures', 'analysis', 'ledger']:
        page.click(f'#tabs button[data-tab={tab}]'); time.sleep(0.8)
        if tab == 'analysis':
            page.wait_for_function("window.app.state.reportMd.length > 100")
            time.sleep(0.3)
        page.screenshot(path=f'/tmp/ui_{tab}.png')
    # dossier toggle
    page.click('#tabs button[data-tab=analysis]'); page.wait_for_function("window.app.state.reportMd.length > 100")
    page.click('.seg button[data-kind=dossier]'); page.wait_for_function("window.app.state.reportKind==='dossier' && window.app.state.reportMd.length > 100"); time.sleep(0.3)
    page.screenshot(path='/tmp/ui_dossier.png')
    # live goal detection: second poll -> 2-0 -> notifyGoal
    page.click('#tabs button[data-tab=live]'); time.sleep(0.5)
    page.evaluate("window.app.state.lastLive = 0"); page.click('#live-refresh'); time.sleep(1.0)
    notified = page.evaluate("window.__notified")
    # settings + update banner
    page.click('#btn-settings'); time.sleep(0.5)
    page.screenshot(path='/tmp/ui_settings.png')
    banner = page.inner_text('#banner')
    page.click('#b-update'); time.sleep(0.3)
    installed = page.evaluate("window.__installed")
    # detail
    page.evaluate("window.app.back()"); page.click('#tabs button[data-tab=fixtures]'); time.sleep(0.3)
    page.click('.list-item.tap'); time.sleep(0.5); page.screenshot(path='/tmp/ui_detail.png')
    # contact click goes through native.openUrl
    page.evaluate("window.app.back()"); page.click('#tabs button[data-tab=today]'); time.sleep(0.3)
    page.click('a.btn.wa'); opened = page.evaluate("window.__opened")
    # leak check: full text of every view
    leaks = []
    for tab in ['today', 'live', 'fixtures', 'analysis', 'ledger']:
        page.click(f'#tabs button[data-tab={tab}]'); time.sleep(0.6)
        if tab == 'analysis': page.wait_for_function("window.app.state.reportMd.length > 100")
        txt = page.inner_text('body') + ' ' + page.inner_html('#view')
        for pat in ['github', 'perfectndumiso', 'Goals Scanner', 'goals-scanner']:
            if pat.lower() in txt.lower(): leaks.append((tab, pat))
    page.click('#btn-settings'); time.sleep(0.3)
    txt = page.inner_text('body') + page.inner_html('#view')
    for pat in ['github', 'perfectndumiso', 'Goals Scanner', 'goals-scanner']:
        if pat.lower() in txt.lower(): leaks.append(('settings', pat))
    b.close()

print('goal notifications:', notified)
print('banner:', banner.replace('\n', ' | '))
print('install url:', installed)
print('whatsapp opened:', opened)
print('leaks:', leaks)
print('console errors:', errors)
ok = notified and 'Jones' in notified[0]['text'] and installed and 'wa.me/27738212664' in (opened or '') and not leaks and not errors
print('RESULT', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
