// Exercise the actual Wrangler bundle in workerd, not just Node mocks. No real
// credentials, external GitHub request, workflow dispatch or deployment occurs.
const assert = require('node:assert/strict');
const path = require('node:path');
const { Miniflare, convertV4MiniflareOptions } = require('miniflare');
const config = require('node:fs').readFileSync(path.join(__dirname, 'wrangler.jsonc'), 'utf8');
const compatibilityDate = JSON.parse(config).compatibility_date;

(async () => {
  const mf = new Miniflare(convertV4MiniflareOptions({
    modules: true,
    scriptPath: path.resolve(__dirname, '../../tmp/scheduler-bundle/worker.js'),
    compatibilityDate,
    durableObjects: { SCHEDULER: { className: 'Scheduler', useSQLite: true } },
    // Forbid accidental live network access even if a future edit adds config.
    outboundService: () => { throw new Error('Live network forbidden in smoke test'); },
  }));
  try {
    assert.equal((await mf.dispatchFetch('http://timer.invalid/', { method: 'POST' })).status, 404);
    const namespace = await mf.getDurableObjectNamespace('SCHEDULER');
    const object = namespace.get(namespace.idFromName('main-timer'));
    const response = await object.fetch('http://internal.invalid/tick', {
      method: 'POST', body: JSON.stringify({ scheduledTime: Date.now() }),
    });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).outcomes[0].result, 'disabled_or_unconfigured');
    console.log('PASS: real Workers bundle loads SQLite Durable Object; unconfigured timer is inert; public route is 404.');
  } finally { await mf.dispose(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
