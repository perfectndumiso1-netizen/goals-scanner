/* Dependency-free tests of the production Home collection functions. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/app/src/main/assets/www/views.js', 'utf8');
const today = '2026-10-30';
function setup(buttons = []) {
  const PR = { $: () => null, $$: (selector) => selector === '[data-matchday]' ? buttons : [], views: {}, live: {}, state: { data: {}, homeTab: 'all' }, settings: { leagues: 'all' },
    tzNow: () => new Date(today + 'T12:00:00'), ymd: () => today,
    SEL_FLOOR: { O25: 0.55, H: 0.55 }, selGroup: (sel) => sel.startsWith('C') ? 'corners' : 'goals',
    isDropped: (sel) => sel.startsWith('U'), isOutlier: (s) => !!s.outlier,
    icon: () => '', esc: (s) => String(s).replace(/</g, '&lt;') };
  // Export lexical functions ONLY inside this test VM; the shipped app has no test-only API.
  vm.runInNewContext(source.replace('})(window.PR);', 'PR.testHome = { homeCollections, homeLaunchpad, matchdayFixtures, matchdayStats, openMatchday, wireCommon }; })(window.PR);'), { window: { PR }, console });
  return PR;
}
const sel = (p, odds = 1.2, key = 'O15') => ({ p, odds, sel: key });
const fixture = (id, sels, extra = {}) => ({ id, date: today, major: true, sels, ...extra });
const rows = (PR, fixtures) => PR.testHome.homeCollections({ fixtures });

test('80% collection uses exact published probability, not rounding or market implied', () => {
  const PR = setup();
  const c = rows(PR, [fixture('below', [sel(.79999)]), fixture('boundary', [sel(.8)]), fixture('above', [sel(.801)]),
    fixture('market-only', [{ ...sel(.79), p_sb: .9 }])]);
  assert.deepEqual(Array.from(c.eighty, (r) => r.f.id), ['boundary', 'above']);
  assert.equal(c.all.length, 4); // Other collections retain their old bars.
});
test('filter before choosing strongest market: a sub-80 winner cannot hide an 80 line', () => {
  const PR = setup();
  const c = rows(PR, [fixture('same', [sel(.799, 1.2, 'COVER'), sel(.8)])]);
  assert.equal(c.all[0].s.sel, 'COVER');
  assert.equal(c.eighty[0].s.sel, 'O15');
});
test('one qualifying market per match; highest existing strength wins', () => {
  const c = rows(setup(), [fixture('same', [sel(.8), sel(.85), sel(.82)])]);
  assert.equal(c.eighty.length, 1); assert.equal(c.eighty[0].s.p, .85);
});
test('preserves today, league scope, odds floor, dropped market and outlier gates', () => {
  const PR = setup(); PR.settings.leagues = 'major';
  const c = rows(PR, [fixture('good', [sel(.8, 1.16)]), fixture('cheap', [sel(.9, 1.15)]),
    fixture('unpriced', [sel(.9, null)]), fixture('yesterday', [sel(.9)], { date: '2026-10-29' }),
    fixture('tomorrow', [sel(.9)], { date: '2026-10-31' }), fixture('minor', [sel(.9)], { major: false }),
    fixture('blocked', [sel(.9, 1.2, 'U15')]), fixture('outlier', [{ ...sel(.9), outlier: true }])]);
  assert.deepEqual(Array.from(c.eighty, (r) => r.f.id), ['good']);
});
test('malformed and non-finite probabilities never enter 80% collection', () => {
  const c = rows(setup(), [fixture('bad', [sel(null), sel(NaN), sel(Infinity), sel(1), sel(-1), sel('0.85')])]);
  assert.equal(c.eighty.length, 0);
});
test('empty publication stays empty, no lower threshold or fabricated picks', () => {
  assert.equal(rows(setup(), []).eighty.length, 0);
  assert.equal(rows(setup(), [fixture('below', [sel(.79)])]).eighty.length, 0);
});
test('home collections do not mutate fixture or selection data', () => {
  const fixtures = [fixture('same', [sel(.8), sel(.85)])];
  const before = JSON.stringify(fixtures); rows(setup(), fixtures);
  assert.equal(JSON.stringify(fixtures), before);
});
test('all three shortcuts always exist, including empty states, with correct destinations', () => {
  const PR = setup(); const html = PR.testHome.homeLaunchpad(rows(PR, []));
  for (const text of ['Bet Advisor', 'Bets of the Day', '80%+ Markets', 'data-page-go="advisor"', 'data-home-open="all"', 'data-home-open="eighty"', '0 qualifying today']) assert(html.includes(text), text);
});


test('matchday picture has four semantic, labelled buttons even when counts are zero', () => {
  const PR = setup(); const html = PR.testHome.matchdayStats([], [], 0);
  assert.equal((html.match(/<button type="button"/g) || []).length, 4);
  for (const key of ['fixtures', 'analysed', 'signals', 'live']) assert(html.includes(`data-matchday="${key}"`));
  assert.equal((html.match(/aria-label=/g) || []).length, 4);
  assert(!html.includes('disabled')); assert(html.includes('View all analysed matches today'));
});
test('analysed drill-down uses the same today/data_ok predicate as the Home counter', () => {
  const PR = setup();
  const fixtures = [fixture('analysed', [], { data_ok: true }), fixture('unanalysed', [], { data_ok: false }),
    fixture('tomorrow', [], { date: '2026-10-31', data_ok: true }), fixture('yesterday', [], { date: '2026-10-29', data_ok: true })];
  assert.deepEqual(Array.from(PR.testHome.matchdayFixtures(fixtures, true), f => f.id), ['analysed']);
  assert.deepEqual(Array.from(PR.testHome.matchdayFixtures(fixtures, false), f => f.id), ['analysed', 'unanalysed']);
  assert(PR.testHome.matchdayStats(PR.testHome.matchdayFixtures(fixtures, false), [], 0).includes('<b>1</b><span>Analysed</span>'));
});
test('wired buttons clear stale searches and open full today/analysed lists in kickoff order', () => {
  const buttons = ['fixtures', 'analysed'].map(key => ({ dataset: { matchday: key } }));
  const PR = setup(buttons); const destinations = []; PR.setTab = tab => destinations.push(tab);
  PR.testHome.wireCommon();
  for (const [i, button] of buttons.entries()) {
    Object.assign(PR.state, { search: 'old hidden query', matchFilter: 'fav', sort: 'O25', matchesView: 'comp' });
    let stopped = false; button.onclick({ stopPropagation() { stopped = true; } });
    assert(stopped); assert.equal(PR.state.search, ''); assert.equal(PR.state.matchFilter, i ? 'analysed' : 'today');
    assert.equal(PR.state.sort, 'ko'); assert.equal(PR.state.matchesView, 'time');
  }
  assert.deepEqual(destinations, ['matches', 'matches']);
});
test('signals opens existing high-probability list with today and all markets selected', () => {
  const PR = setup(); let destination; PR.setTab = tab => { destination = tab; };
  Object.assign(PR.state, { betsView: 'corners', betGroup: 'corners', safestAll: true });
  PR.testHome.openMatchday('signals');
  assert.equal(destination, 'bets'); assert.equal(PR.state.betsView, 'safest');
  assert.equal(PR.state.betGroup, 'all'); assert.equal(PR.state.safestAll, false);
});
test('live opens worldwide live when loaded, including zero, otherwise tracked view', () => {
  const PR = setup(); PR.setTab = tab => assert.equal(tab, 'live');
  PR.state.liveAll = null; PR.testHome.openMatchday('live'); assert.equal(PR.state.liveView, 'tracked');
  PR.state.liveAll = []; PR.testHome.openMatchday('live'); assert.equal(PR.state.liveView, 'all');
  PR.state.liveAll = [{ eid: '123' }]; PR.testHome.openMatchday('live'); assert.equal(PR.state.liveView, 'all');
});
test('empty analysed collection stays empty and shortcut navigation never changes published data', () => {
  const PR = setup(); PR.setTab = () => {};
  PR.state.data = { fixtures: [fixture('not ready', [sel(.8)], { data_ok: false })], safe: { bets: [] } };
  const before = JSON.stringify(PR.state.data);
  assert.equal(PR.testHome.matchdayFixtures(PR.state.data.fixtures, true).length, 0);
  for (const key of ['fixtures', 'analysed', 'signals', 'live', 'unknown']) PR.testHome.openMatchday(key);
  assert.equal(JSON.stringify(PR.state.data), before);
});
