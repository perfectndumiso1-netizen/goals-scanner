/* Dependency-free tests of the production Home collection functions. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(__dirname + '/app/src/main/assets/www/views.js', 'utf8');
const today = '2026-10-30';
function setup() {
  const PR = { views: {}, live: {}, state: { data: {}, homeTab: 'all' }, settings: { leagues: 'all' },
    tzNow: () => new Date(today + 'T12:00:00'), ymd: () => today,
    SEL_FLOOR: { O25: 0.55, H: 0.55 }, selGroup: (sel) => sel.startsWith('C') ? 'corners' : 'goals',
    isDropped: (sel) => sel.startsWith('U'), isOutlier: (s) => !!s.outlier,
    icon: () => '', esc: (s) => String(s).replace(/</g, '&lt;') };
  // Export lexical functions ONLY inside this test VM; the shipped app has no test-only API.
  vm.runInNewContext(source.replace('})(window.PR);', 'PR.testHome = { homeCollections, homeLaunchpad }; })(window.PR);'), { window: { PR }, console });
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
