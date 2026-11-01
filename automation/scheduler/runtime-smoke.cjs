// Exercise the actual Wrangler bundle in workerd, not just Node mocks. No real
// credentials, external GitHub request, workflow dispatch or deployment occurs.
const assert = require('node:assert/strict');
const path = require('node:path');
const { generateKeyPairSync, verify } = require('node:crypto');
const { Miniflare, convertV4MiniflareOptions } = require('miniflare');
const config = require('node:fs').readFileSync(path.join(__dirname, 'wrangler.jsonc'), 'utf8');
const compatibilityDate = JSON.parse(config).compatibility_date;

(async () => {
  const mf = new Miniflare(convertV4MiniflareOptions({
    modules: true,
    modulesRoot: path.resolve(__dirname, '../..'),
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

  // Exercise real Workers Web Crypto with fresh synthetic keys and an in-process
  // fake GitHub endpoint. This detects runtime-specific import/signing failures
  // that Node-only mocks cannot. No production key or external network is used.
  const keys = generateKeyPairSync('rsa', { modulusLength: 2048 });
  for (const [type, status] of [['pkcs1', 401], ['pkcs8', 401], ['pkcs1', 302], ['pkcs1', 201]]) {
    let tokenRequests = 0;
    let mockStage = 'not_called';
    const runtime = new Miniflare(convertV4MiniflareOptions({
      modules: true, modulesRoot: path.resolve(__dirname, '../..'),
      scriptPath: path.resolve(__dirname, '../../tmp/scheduler-bundle/worker.js'), compatibilityDate,
      durableObjects: { SCHEDULER: { className: 'Scheduler', useSQLite: true } },
      bindings: { ENABLE_SCHEDULER: 'true', GITHUB_APP_ID: '123', GITHUB_INSTALLATION_ID: '456',
        GITHUB_APP_PRIVATE_KEY: keys.privateKey.export({ type, format: 'pem' }) },
      outboundService: async request => {
        mockStage = 'outbound_entered';
        const url = new URL(request.url);
        mockStage = 'origin_check';
        assert.equal(url.origin, 'https://api.github.com');
        mockStage = 'path_check';
        if (url.pathname === '/app/installations/456/access_tokens') {
          mockStage = 'method_check';
          assert.equal(request.method, 'POST');
          mockStage = 'body_check';
          assert.deepEqual(await request.json(), { repositories: ['goals-scanner'], permissions: { actions: 'write' } });
          mockStage = 'signature_check';
          const [header, body, signature] = request.headers.get('Authorization').slice(7).split('.');
          assert.ok(verify('RSA-SHA256', Buffer.from(header + '.' + body), keys.publicKey, Buffer.from(signature, 'base64url')));
          tokenRequests++;
          return status === 201 ? Response.json({ token: 'dummy-test-installation-token',
            permissions: { actions: 'write' }, expires_at: new Date(Date.now() + 3_600_000).toISOString() }, { status }) :
            new Response('dummy-private-response-must-not-be-logged', { status,
              headers: status === 302 ? { Location: 'https://redirect.invalid/credential-trap' } : {} });
        }
        assert.equal(status, 201);
        assert.equal(request.method, 'GET', 'no workflow dispatch permitted in smoke test');
        assert.ok(url.pathname.startsWith('/repos/perfectndumiso1-netizen/goals-scanner/actions/workflows/'));
        assert.ok(url.pathname.endsWith('/runs'));
        assert.equal(request.headers.get('Authorization'), 'Bearer dummy-test-installation-token');
        return Response.json({ workflow_runs: [{ head_branch: 'main', status: 'completed',
          created_at: new Date().toISOString() }] });
      },
    }));
    try {
      const namespace = await runtime.getDurableObjectNamespace('SCHEDULER');
      const object = namespace.get(namespace.idFromName('main-timer'));
      const response = await object.fetch('http://internal.invalid/tick', {
        method: 'POST', body: JSON.stringify({ scheduledTime: Date.now() }),
      });
      const report = await response.json();
      assert.equal(tokenRequests, 1, `mock stage: ${mockStage}`);
      if (status !== 201) {
        assert.deepEqual(report.outcomes, [{ workflow: 'timer', result: 'app_authentication_failed_no_dispatch',
          auth_stage: 'installation_token_http', auth_reason: 'github_rejected_token_request', http_status: status }]);
      } else {
        assert.ok(report.outcomes.length > 0);
        assert.ok(report.outcomes.every(row => row.result === 'recent_run'));
      }
      console.log(`PASS: workerd ${type} import/sign + mock GitHub HTTP ${status}; no real dispatch.`);
    } finally { await runtime.dispose(); }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
