/* Optional real Chromium integration/benchmark harness. No production npm dependencies.
 * npm install --prefix tmp/android-test-tools playwright-core @sparticuz/chromium
 * Requires temporary latest.json and leagues-index.json in ANDROID_CACHE_FIXTURES (see docs).
 */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const modules = process.env.ANDROID_TEST_MODULES || path.join(root, 'tmp/android-test-tools/node_modules');
const { chromium: browserType } = require(path.join(modules, 'playwright-core'));
const dir = process.env.ANDROID_CACHE_FIXTURES || path.join(root, 'tmp/android-fixtures');
const latest = JSON.parse(fs.readFileSync(path.join(dir, 'latest.json')));
const index = JSON.parse(fs.readFileSync(path.join(dir, 'leagues-index.json')));
const optional = (file) => fs.existsSync(path.join(dir, file)) ? JSON.parse(fs.readFileSync(path.join(dir, file))) : null;
const detail = optional('detail.json'), teams = optional('teams.json'), league = optional('league.json'), day = optional('day.json');
const www = path.join(root, 'android/app/src/main/assets/www');
const prefix = 'https://raw.githubusercontent.com/perfectndumiso1-netizen/goals-scanner/data/';
const app = 'https://appassets.androidplatform.net/assets/www/';
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const { default: chromium } = await import(path.join(modules, '@sparticuz/chromium/build/index.js'));
  const { inflate } = await import(path.join(modules, '@sparticuz/chromium/build/lambdafs.js'));
  await inflate(path.join(modules, '@sparticuz/chromium/bin/al2023.tar.br'));
  process.env.LD_LIBRARY_PATH = '/tmp/al2023/lib:' + (process.env.LD_LIBRARY_PATH || '');
  const browser = await browserType.launch({ executablePath: await chromium.executablePath(), args: chromium.args.filter((arg) => !['--single-process', '--no-zygote'].includes(arg)), headless: true });
  const results = {};
  async function session(baseline = false) {
    const context = await browser.newContext({ viewport: { width: 412, height: 915 } });
    const page = await context.newPage(), errors = [], requests = [];
    let delay = 0, mode = 'normal', revision = false;
    page.on('pageerror', (e) => errors.push(e.message));
    await context.route('**/*', async (route) => {
      const u = route.request().url();
      if (u.startsWith(app)) {
        const filename = new URL(u).pathname.split('/').pop();
        try {
          const relative = 'android/app/src/main/assets/www/' + filename;
          const bytes = baseline ? execFileSync('git', ['show', (process.env.ANDROID_CACHE_BASELINE || '49196874736afdcb980438bae465d0721e9937c3') + ':' + relative], { cwd: root, stdio: ['ignore', 'pipe', 'ignore'] }) : fs.readFileSync(path.join(www, filename));
          return route.fulfill({ body: bytes, contentType: filename.endsWith('.js') ? 'application/javascript' : filename.endsWith('.css') ? 'text/css' : filename.endsWith('.html') ? 'text/html' : 'image/png' });
        } catch (_) { return route.abort(); }
      }
      if (u.startsWith(prefix)) {
        const resource = new URL(u).pathname.split('/data/')[1]; requests.push({ resource, headers: route.request().headers() });
        if (delay) await pause(delay);
        if (mode === 'failure') return route.abort('internetdisconnected');
        if (mode === '304' && route.request().headers()['if-none-match'] === 'one') return route.fulfill({ status: 304, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag', ETag: 'one' } });
        let j;
        if (resource === 'data/app/latest.json') j = revision ? Object.assign({}, latest, { cache_test_revision: 2 }) : latest;
        else if (resource === 'data/app/leagues/index.json') j = index;
        else if (resource === 'data/app/leagues/fixtures.json') j = { generated: index.generated, count: 0, fixtures: [] };
        else if (detail && resource.endsWith('/fx/' + latest.fixtures[0].d + '.json')) j = detail;
        else if (teams && resource.endsWith('/teams/' + teams.div.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '') + '.json')) j = teams;
        else if (league && resource.endsWith('/leagues/' + index.leagues[0].slug)) j = league;
        else if (day && resource.endsWith('/days/' + day.date + '.json')) j = day;
        else if (resource.includes('/fx/')) {
          const f = latest.fixtures.find((x) => resource.includes(x.d));
          j = f ? Object.assign({}, f, { teams: { home: {}, away: {} }, h2h: [], trends: {} }) : {};
        } else if (/days\/\d/.test(resource)) j = { date: resource.match(/\d{4}-\d\d-\d\d/)[0], fixtures: [] };
        else if (resource.includes('teams-index')) j = { generated: latest.meta.generated, teams: [] };
        else j = { placeholder: 'test-only' };
        return route.fulfill({ json: j, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Expose-Headers': 'ETag', ETag: 'one' } });
      }
      if (u.includes('prod-public-api.livescore.com')) return route.fulfill({ json: { Stages: [] }, headers: { 'Access-Control-Allow-Origin': '*' } });
      return route.abort();
    });
    await page.goto(app + 'index.html');
    await page.waitForFunction(() => window.PR && PR.state.data && PR.state.data.fixtures.length);
    await page.evaluate(() => { PR.prefetchDetails = () => {}; });
    await page.waitForTimeout(200);
    return { context, page, errors, requests, control(v) { if ('delay' in v) delay = v.delay; if ('mode' in v) mode = v.mode; if ('revision' in v) revision = v.revision; } };
  }
  try {
    // Before/after comparison of a genuinely network-first path in the prior application.
    for (const baseline of [true, false]) {
      const s = await session(baseline);
      await s.page.evaluate(({ index, prefix }) => {
        localStorage.setItem('pr_d:leag/idx', JSON.stringify({ t: 1, s: index.generated, d: index }));
      }, { index, prefix });
      s.control({ delay: 2000 });
      const timing = await s.page.evaluate(async () => { const start = performance.now(); await PR.leaguesApi.loadIndex(false); return performance.now() - start; });
      results[baseline ? 'before_cached_league_ms' : 'after_cached_league_ms'] = Math.round(timing);
      assert.equal(s.errors.length, 0, s.errors.join('\n'));
      await s.context.close();
    }
    assert(results.after_cached_league_ms < 500);
    assert(results.before_cached_league_ms >= 1800);
    const s = await session();
    // Reopen with real persistent IndexedDB and a two-second network delay.
    s.control({ delay: 2000 });
    const reopenedAt = Date.now(); await s.page.reload();
    await s.page.waitForFunction(() => window.PR && PR.state.data && PR.state.data.fixtures.length);
    results.cached_reopen_ms = Date.now() - reopenedAt;
    await s.page.evaluate(() => { PR.prefetchDetails = () => {}; });
    assert(results.cached_reopen_ms < 1500);
    const before = s.requests.filter((r) => r.resource === 'data/app/latest.json').length;
    await s.page.evaluate(async () => { for (let i = 0; i < 5; i++) { PR.setTab('matches'); PR.setTab('bets'); PR.setTab('home'); await PR.loadData(false); } });
    assert.equal(s.requests.filter((r) => r.resource === 'data/app/latest.json').length, before);
    // Unchanged revalidation should not replace the screen DOM.
    s.control({ delay: 0, mode: '304' });
    await s.page.waitForTimeout(2300); // Let any deliberately delayed initial day fetch settle.
    const content = await s.page.evaluate(() => { window.__oldCard = document.querySelector('#view .card'); return !!window.__oldCard; });
    await s.page.evaluate(() => PR.loadData(true)); await s.page.waitForTimeout(250);
    if (content) assert(await s.page.evaluate(() => document.querySelector('#view .card') === window.__oldCard));
    const conditional = s.requests.filter((r) => r.resource === 'data/app/latest.json').at(-1);
    assert.equal(conditional.headers['if-none-match'], 'one');
    // Updated publication propagates without reopening the screen.
    s.control({ mode: 'normal', revision: true });
    await s.page.evaluate(() => PR.loadData(true));
    await s.page.waitForFunction(() => PR.state.data.cache_test_revision === 2);
    if (detail && teams && league && day) {
      await s.page.evaluate(async ({ teams, day, slug }) => {
        const f = PR.state.data.fixtures[0];
        await PR.loadDetail(f.id, f.d); await PR.loadTeams(teams.div); await PR.loadDay(day.date); await PR.leaguesApi.loadDetail(slug);
      }, { teams, day, slug: index.leagues[0].slug });
    }
    await s.context.setOffline(true);
    const offlineCount = s.requests.length;
    await s.page.evaluate(() => PR.loadData(true));
    assert((await s.page.locator('#data-status').innerText()).includes('Offline'));
    assert.equal(s.requests.length, offlineCount);
    if (detail && teams && league && day) {
      // Drop only RAM mirrors: prove an offline screen can restore the persisted records.
      const restored = await s.page.evaluate(async ({ div, date, slug }) => {
        const f = PR.state.data.fixtures[0]; PR.state.details = {}; PR.state.teams = {}; PR.state.days = {};
        const x = await PR.loadDetail(f.id, f.d), t = await PR.loadTeams(div), d = await PR.loadDay(date), l = await PR.leaguesApi.loadDetail(slug);
        return { id: x.id, teams: Object.keys(t.teams).length, date: d.date, key: l.key };
      }, { div: teams.div, date: day.date, slug: index.leagues[0].slug });
      assert.equal(restored.id, detail.id); assert.equal(restored.teams, Object.keys(teams.teams).length);
      assert.equal(restored.date, day.date); assert.equal(restored.key, league.key);
      assert.equal(s.requests.length, offlineCount); results.offline_details_teams_day_standings = 'passed';
    }
    // Identity checks: another match/date, duplicate fixtures, wrong league cannot replace cache.
    assert(await s.page.evaluate(({ prefix }) => {
      const j = structuredClone(PR.state.data);
      j.fixtures.push(j.fixtures[0]);
      return !PR.validResource(prefix + 'data/app/latest.json', j) &&
        !PR.validResource(prefix + 'data/app/days/2026-10-30.json', { date: '2026-10-29', fixtures: [] }) &&
        !PR.validResource(prefix + 'data/app/fx/000000000000.json', { id: 'different match', home: 'A', away: 'B' });
    }, { prefix }));
    await s.context.setOffline(false); await s.page.waitForTimeout(300);
    assert.equal(s.errors.length, 0, s.errors.join('\n'));
    results.errors = s.errors;
    results.repeated_navigation_additional_latest_requests = 0;
    results.status = 'passed';
    await s.page.screenshot({ path: path.join(root, 'tmp/android-fixtures/cache-screen.png'), fullPage: true });
    await s.context.close();
    console.log(JSON.stringify(results, null, 2));
    fs.writeFileSync(path.join(root, 'tmp/android-fixtures/browser-results.json'), JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
