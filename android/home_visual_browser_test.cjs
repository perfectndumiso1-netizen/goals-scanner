/* Optional real-browser UI regression. No production npm dependencies.
 * npm install --prefix tmp/visual-test-tools playwright-core @sparticuz/chromium
 * Save a read-only published latest.json to tmp/visual-fixtures/latest.json first.
 * Screenshots and downloaded snapshots stay ignored in tmp/. Test-only synthetic selections
 * below never enter production data, app assets, or a published analysis.
 */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..'), dir = path.join(root, 'tmp/visual-fixtures');
const modules = process.env.ANDROID_TEST_MODULES || path.join(root, 'tmp/visual-test-tools/node_modules');
const { chromium: browserType } = require(path.join(modules, 'playwright-core'));
const latest = JSON.parse(fs.readFileSync(path.join(dir, 'latest.json')));
const app = 'https://appassets.androidplatform.net/assets/www/';
(async () => {
  const { default: chromium } = await import(path.join(modules, '@sparticuz/chromium/build/index.js'));
  const { inflate } = await import(path.join(modules, '@sparticuz/chromium/build/lambdafs.js'));
  await inflate(path.join(modules, '@sparticuz/chromium/bin/al2023.tar.br'));
  process.env.LD_LIBRARY_PATH = '/tmp/al2023/lib:' + (process.env.LD_LIBRARY_PATH || '');
  const browser = await browserType.launch({ executablePath: await chromium.executablePath(), args: chromium.args.filter((a) => !['--single-process', '--no-zygote'].includes(a)), headless: true });
  const results = { layouts: [], errors: [] };
  try {
    const context = await browser.newContext({ viewport: { width: 412, height: 915 } });
    const page = await context.newPage();
    page.on('pageerror', (e) => results.errors.push(e.message));
    await page.clock.install({ time: new Date(latest.meta.generated.replace(' ', 'T') + '+02:00') });
    await context.route('**/*', async (route) => {
      const u = route.request().url();
      if (u.startsWith(app)) {
        const filename = new URL(u).pathname.split('/').pop();
        const file = path.join(root, 'android/app/src/main/assets/www', filename);
        if (!fs.existsSync(file)) return route.abort();
        return route.fulfill({ body: fs.readFileSync(file), contentType: filename.endsWith('.js') ? 'application/javascript' : filename.endsWith('.css') ? 'text/css' : filename.endsWith('.html') ? 'text/html' : 'image/png' });
      }
      if (u.includes('/data/app/latest.json')) return route.fulfill({ json: latest, headers: { 'Access-Control-Allow-Origin': '*', ETag: 'visual-test' } });
      if (u.includes('/date/soccer/')) return route.fulfill({ json: { Stages: [] }, headers: { 'Access-Control-Allow-Origin': '*' } });
      return route.fulfill({ status: 404, body: 'Unavailable in isolated UI test', headers: { 'Access-Control-Allow-Origin': '*' } });
    });
    await page.goto(app + 'index.html');
    await page.locator('.home-launchpad').waitFor();
    assert.equal(await page.locator('.home-quick').count(), 3);
    for (const theme of ['dark', 'light']) for (const width of [320, 412, 768]) {
      await page.setViewportSize({ width, height: 915 });
      await page.evaluate((theme) => { PR.settings.theme = theme; PR.applyTheme(); }, theme);
      const heroBackground = await page.locator('.home-stadium').evaluate((e) => getComputedStyle(e).backgroundImage);
      assert(heroBackground.includes('13, 37, 49') && heroBackground.includes('16, 79, 72'), `unreadable hero background in ${theme}: ${heroBackground}`);
      const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth, cards: [...document.querySelectorAll('.home-quick')].map((e) => { const r = e.getBoundingClientRect(); return { top: r.top, right: r.right, height: r.height }; }) }));
      if (layout.scroll > width + 1) console.log(await page.evaluate(() => [...document.querySelectorAll('#view *')].map(e=>({tag:e.tagName, cls:e.className, right:e.getBoundingClientRect().right, width:e.getBoundingClientRect().width})).filter(e=>e.right>innerWidth+1).slice(0,20)));
      assert(layout.scroll <= width + 1, `page overflow ${theme}/${width}: ${layout.scroll}`);
      assert(layout.cards.every((r) => r.top >= 64 && r.top < 400 && r.right <= width && r.height >= 44));
      results.layouts.push({ theme, width, overflow: false });
      await page.screenshot({ path: path.join(dir, `home-${theme}-${width}.png`) });
    }
    await page.setViewportSize({ width: 412, height: 915 });
    await page.locator('[data-page-go="advisor"]').click();
    assert.equal(await page.evaluate(() => PR.state.stack.at(-1).type), 'advisor');
    await page.locator('.advisor-hero').waitFor();
    await page.evaluate(() => PR.back());
    await page.locator('.home-launchpad').waitFor();
    results.advisor_navigation = 'passed';
    // Controlled boundary data in this isolated page only. Exercise the actual core/indexer/policy.
    await page.evaluate(() => {
      const d = PR.state.data, today = PR.ymd(PR.tzNow());
      const f = d.fixtures[0];
      const make = (key, p, odds = 1.2, date = today) => ({ ...f, id: date + '|Test|' + key, home: key, away: 'UI test only', date, kickoff: date + ' 23:30', d: null, livescore_id: null,
        sels: [{ sel: 'O15', p, p_sb: p, odds, label: 'Over 1.5 goals' }] });
      d.fixtures = [make('Boundary 80', .80), make('Above 81', .81), make('Rounded 79', .79999), make('Below 78', .78), make('Cheap 85', .85, 1.15), make('Other date', .85, 1.2, '2000-01-01')];
      d._byId = Object.fromEntries(d.fixtures.map((f) => [f.id, f]));
      d.tracked = []; d.safe = { bets: [], today: { bets: [] } }; d.meta.fixtures = d.fixtures.length;
      // Make sure the unrelated original 78% panel cannot leak into the 80%-only collection.
      d.strong_markets = { bets: [{ ...d.fixtures[3], sel: 'O15', p: .78, odds: 1.2, label: 'Below 80 panel', family: 'o15' }] };
      PR.settings.leagues = 'all'; PR.state.homeTab = 'all'; PR.render();
    });
    await page.locator('[data-home-open="eighty"]').click();
    const labels = await page.locator('.home-selection-table tr[data-fx]').allTextContents();
    assert.equal(labels.length, 2, labels.join('\n'));
    assert(labels.some((s) => s.includes('Boundary 80')) && labels.some((s) => s.includes('Above 81')));
    assert(!await page.locator('#view').textContent().then((s) => s.includes('Below 80 panel')));
    assert.equal(await page.locator('[data-ht="eighty"]').getAttribute('aria-pressed'), 'true');
    await page.locator('#home-sort').selectOption('odds_a');
    assert.equal(await page.locator('.home-selection-table tr[data-fx]').count(), 2);
    await page.locator('[data-hmk="goals"]').click();
    assert.equal(await page.locator('.home-selection-table tr[data-fx]').count(), 2);
    results.exact_80_filter_sort_market = 'passed';
    await page.locator('.home-selection-table tr[data-fx]').first().locator('td').nth(1).locator('.b').click();
    assert.equal(await page.evaluate(() => PR.state.stack.at(-1).type), 'match');
    await page.evaluate(() => PR.back());
    assert.equal(await page.evaluate(() => PR.state.homeTab), 'eighty');
    results.match_detail_and_back = 'passed';
    await page.locator('[data-home-open="all"]').click();
    assert.equal(await page.locator('.home-selection-table tr[data-fx]').count(), 4);
    results.daily_navigation = 'passed';
    // Empty and offline cached UI: no fallback to a lower bar, no new dependencies.
    await context.setOffline(true);
    await page.evaluate(() => { PR.state.data.fixtures = PR.state.data.fixtures.filter((f) => f.home.includes('Below 78')); PR.state.homeTab = 'all'; PR.render(); });
    await page.locator('[data-home-open="eighty"]').click();
    assert.equal(await page.locator('.home-selection-table tr[data-fx]').count(), 0);
    assert((await page.locator('#view').textContent()).includes('threshold is never lowered'));
    assert.equal(await page.locator('.home-quick').count(), 3);
    results.empty_offline_collection = 'passed';
    assert.deepEqual(results.errors, []);
    results.status = 'passed';
    fs.writeFileSync(path.join(dir, 'visual-results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
    await context.close();
  } finally { await browser.close(); }
})().catch((e) => { console.error(e); process.exitCode = 1; });
