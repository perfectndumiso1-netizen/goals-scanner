/* Run: node --test android/cache_test.cjs — no npm dependencies. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('./app/src/main/assets/www/resource-cache.js');
const base = 'https://raw.githubusercontent.com/owner/repo/data/data/app/';
const url = base + 'latest.json';
const body = (n = 1, generated = '2026-10-30 12:00') => JSON.stringify({ meta: { generated }, fixtures: [{ id: 'match', n }] });
const tick = () => new Promise((r) => setImmediate(r));
function fixture(fetcher) {
  const rows = new Map(), negative = new Map(); let time = Date.UTC(2026, 9, 30, 12), connected = true;
  const calls = [], puts = [], touches = [], events = [];
  const store = {
    async get(k) { return rows.has(k) ? structuredClone(rows.get(k)) : negative.get(k) || null; },
    async put(k, e) { puts.push(k); rows.set(k, structuredClone(e)); },
    async touch(k, t, headers) { touches.push(k); if (!rows.has(k)) throw Error('evicted'); Object.assign(rows.get(k), { checkedAt: t, etag: headers?.etag || rows.get(k).etag }); },
    async clear() { rows.clear(); negative.clear(); },
    async failure(k, v) { if (v) negative.set(k, { retryAt: v.until, errorCode: v.code, failureCount: v.count }); else negative.delete(k); }
  };
  const options = { store, now: () => time, online: () => connected, validate: (_, d) => Array.isArray(d.fixtures), sleep: async () => {},
    fetch: async (u, headers) => { calls.push({ u, headers }); return fetcher(u, headers); } };
  const make = () => { const cache = create(options); cache.subscribe((e) => events.push(e)); return cache; };
  return { cache: make(), make, store, rows, calls, puts, touches, events, advance: (ms) => { time += ms; }, offline: () => { connected = false; }, online: () => { connected = true; } };
}

test('first install downloads once; reopen reads persisted data without network', async () => {
  const f = fixture(() => ({ code: 200, body: body(), etag: 'one' }));
  assert.equal((await f.cache.get(url)).fixtures[0].n, 1);
  assert.equal((await f.make().get(url)).fixtures[0].n, 1);
  assert.equal(f.calls.length, 1); assert.equal(f.puts.length, 1);
});

test('expired cache renders before a slow request finishes; changed data notifies automatically', async () => {
  let release;
  const f = fixture(() => ({ code: 200, body: body(), etag: 'one' }));
  await f.cache.get(url); f.advance(6 * 60000);
  f.cache = create({ store: f.store, now: () => 2000000, validate: (_, d) => !!d.fixtures,
    fetch: () => new Promise((r) => { release = r; }) });
  const updates = []; f.cache.subscribe((e) => updates.push(e));
  const start = performance.now(); const old = await f.cache.get(url); assert(performance.now() - start < 100);
  assert.equal(old.fixtures[0].n, 1); await tick();
  release({ code: 200, body: body(2), etag: 'two' }); await tick(); await tick();
  assert.equal((await f.cache.get(url)).fixtures[0].n, 2);
  assert.equal(updates.filter((e) => e.type === 'changed').length, 1);
});

test('ETag/304 touches metadata only and returns the identical parsed object', async () => {
  let code = 200;
  const f = fixture(() => ({ code, body: code === 200 ? body() : '', etag: 'one' }));
  const first = await f.cache.get(url); code = 304; f.advance(6 * 60000);
  assert.equal(await f.cache.get(url), first); await tick(); await tick();
  assert.equal(f.calls[1].headers.etag, 'one'); assert.equal(f.puts.length, 1); assert.equal(f.touches.length, 1);
  assert.equal(f.events.filter((e) => e.type === 'changed').length, 1);
});

test('identical 200 without validator support is not rewritten or rerendered', async () => {
  const f = fixture(() => ({ code: 200, body: body() }));
  const first = await f.cache.get(url); f.advance(6 * 60000);
  await f.cache.get(url); await tick(); await tick();
  assert.equal(await f.cache.get(url), first); assert.equal(f.puts.length, 1);
  assert.equal(f.events.filter((e) => e.type === 'changed').length, 1);
});

test('one flight for simultaneous identical requests; cache-busters share identity', async () => {
  const f = fixture(() => ({ code: 200, body: body() }));
  const all = await Promise.all(Array.from({ length: 30 }, (_, i) => f.cache.get(url + '?t=' + i)));
  assert.equal(f.calls.length, 1); assert(all.every((d) => d === all[0]));
  assert.notEqual(f.cache.key(url + '?MD=1'), f.cache.key(url + '?MD=2'));
});

test('no cache + offline fails once locally without a request; reconnect fetches', async () => {
  const f = fixture(() => ({ code: 200, body: body() })); f.offline();
  await assert.rejects(f.cache.get(url)); await assert.rejects(f.cache.get(url)); assert.equal(f.calls.length, 0);
  f.online(); f.cache.reconnect(); await tick(); await tick();
  assert.equal((await f.cache.get(url)).fixtures[0].n, 1);
});

test('offline retains useful fixtures; restoring connectivity updates them', async () => {
  let n = 1; const f = fixture(() => ({ code: 200, body: body(n) }));
  await f.cache.get(url); f.advance(6 * 60000); f.offline();
  n = 2; assert.equal((await f.cache.get(url)).fixtures[0].n, 1); assert(f.cache.status(url).offline);
  assert.equal(f.calls.length, 1); f.online(); f.cache.reconnect(); await tick(); await tick();
  assert.equal((await f.cache.get(url)).fixtures[0].n, 2);
});

for (const response of ['<html>failure</html>', '{}', '{"fixtures":[]}', body(2, '2026-10-29 12:00')]) {
  test('invalid, empty or older response preserves valid snapshot: ' + response.slice(0, 30), async () => {
    let value = body(); const f = fixture(() => ({ code: 200, body: value }));
    await f.cache.get(url); value = response; f.advance(6 * 60000);
    await f.cache.get(url); await tick(); await tick();
    assert.equal((await f.cache.get(url)).fixtures[0].n, 1); assert.equal(f.puts.length, 1);
  });
}

test('5xx retries once then backs off; manual refresh cannot bypass cooldown', async () => {
  const f = fixture(() => ({ code: 503, body: '' }));
  await assert.rejects(f.cache.get(url)); assert.equal(f.calls.length, 2);
  await assert.rejects(f.cache.get(url, { force: true })); assert.equal(f.calls.length, 2);
});

test('429 Retry-After survives reconnect and a repository restart', async () => {
  const f = fixture(() => ({ code: 429, retryAfter: 3600000 }));
  await assert.rejects(f.cache.get(url)); await tick();
  f.cache.reconnect(); await assert.rejects(f.make().get(url)); assert.equal(f.calls.length, 1);
});

test('a total outage does not erase previous data or cause endless requests', async () => {
  let code = 200; const f = fixture(() => ({ code, body: code === 200 ? body() : '' }));
  await f.cache.get(url); f.advance(6 * 60000); code = 0;
  await f.cache.get(url); await tick(); await tick();
  for (let i = 0; i < 20; i++) await f.cache.get(url, { force: true });
  assert.equal(f.calls.length, 3); assert.equal(f.rows.size, 1);
});

test('queue limits different resources to two concurrent reads', async () => {
  let active = 0, maximum = 0;
  const f = fixture(async () => { active++; maximum = Math.max(maximum, active); await tick(); active--; return { code: 200, body: body() }; });
  await Promise.all(Array.from({ length: 25 }, (_, i) => f.cache.get(base + 'fx/' + i + '.json')));
  assert.equal(maximum, 2);
});

test('failure to save does not hide downloaded data; unchanged retry repairs persistence', async () => {
  const f = fixture(() => ({ code: 200, body: body() }));
  const put = f.store.put; f.store.put = async () => { throw Error('disk full'); };
  assert.equal((await f.cache.get(url)).fixtures[0].n, 1); assert(!f.cache.status(url).persisted);
  f.store.put = put; f.advance(6 * 60000); await f.cache.get(url); await tick(); await tick();
  assert(f.cache.status(url).persisted); assert.equal(f.rows.size, 1);
});

test('304 after database eviction restores payload rather than losing offline support', async () => {
  let code = 200; const f = fixture(() => ({ code, body: body() }));
  await f.cache.get(url); f.rows.clear(); code = 304; f.advance(6 * 60000);
  await f.cache.get(url); await tick(); await tick(); assert.equal(f.rows.size, 1);
});

test('late response after clear cannot restore erased data', async () => {
  let release; const f = fixture(() => new Promise((r) => { release = r; }));
  const pending = f.cache.get(url).catch(() => null); await tick(); await f.cache.clear();
  release({ code: 200, body: body() }); await pending; assert.equal(f.rows.size, 0);
});

test('freshness varies by resource and publication invalidates on-demand predictions', async () => {
  const f = fixture(() => ({ code: 200, body: body() }));
  assert(f.cache.ttl(base + 'days/2020-01-01.json') > f.cache.ttl(url));
  assert(f.cache.ttl(base + 'teams/one.json') > f.cache.ttl(url));
  const detail = base + 'fx/key.json'; await f.cache.get(detail); f.advance(1);
  f.cache.invalidate(base + 'fx/'); assert(f.cache.status(detail).stale);
});

test('legacy seed never overwrites a newer durable snapshot', async () => {
  const f = fixture(() => ({ code: 200, body: body(2) })); await f.cache.get(url);
  await f.make().seed(url, JSON.parse(body(1)), 1); assert.equal((await f.make().get(url)).fixtures[0].n, 2);
});


test('a different caller cannot bypass its identity check by joining an existing flight', async () => {
  const f = fixture(() => ({ code: 200, body: body() }));
  const good = f.cache.get(url, { validate: (d) => d.fixtures[0].n === 1 });
  const bad = f.cache.get(url, { validate: (d) => d.fixtures[0].n === 99 });
  assert.equal((await good).fixtures[0].n, 1); await assert.rejects(bad); assert.equal(f.calls.length, 1);
});

test('a rate-limited origin does not drain a whole queued batch of requests', async () => {
  const f = fixture(async () => { await tick(); return { code: 429, retryAfter: 3600000 }; });
  await Promise.allSettled(Array.from({ length: 20 }, (_, i) => f.cache.get(base + 'fx/' + i + '.json')));
  assert(f.calls.length <= 2);
});

test('identical HTTP 200 reuses parsed data rather than parsing it again', async () => {
  const f = fixture(() => ({ code: 200, body: body() })); await f.cache.get(url); f.advance(6 * 60000);
  const parse = JSON.parse; let count = 0;
  JSON.parse = (...args) => { count++; return parse(...args); };
  try { await f.cache.get(url); await tick(); await tick(); assert.equal(count, 0); }
  finally { JSON.parse = parse; }
});


test('legacy cache remains usable even when the new database cannot be written', async () => {
  const f = fixture(() => { throw Error('should be offline'); }); f.offline();
  f.store.put = async () => { throw Error('disk full'); };
  await f.cache.seed(url, JSON.parse(body()), 1);
  assert.equal((await f.cache.get(url)).fixtures[0].n, 1); assert.equal(f.calls.length, 0);
});

test('a background worker snapshot is adopted without downloading it again', async () => {
  const f = fixture(() => ({ code: 200, body: body() })); await f.cache.get(url);
  await f.store.put(url, { body: body(2), checkedAt: Date.UTC(2026, 9, 30, 12), updatedAt: 1000, etag: 'two' });
  await f.cache.pullShared(url);
  assert.equal((await f.cache.get(url)).fixtures[0].n, 2); assert.equal(f.calls.length, 1);
});
