import test from 'node:test';
import { webcrypto } from 'node:crypto';
globalThis.crypto ??= webcrypto;
import assert from 'node:assert/strict';
import worker, { Scheduler } from './worker.mjs';
import { targetsAt, inspectRuns, tick, REPOSITORY, installationToken } from './core.mjs';

const minute = 60_000;
const at = clock => Date.parse(`2026-11-01T${clock}:00Z`);
const dummyCredential = 'dummy-test-credential';
const env = { ENABLE_SCHEDULER: 'true', GITHUB_APP_ID: '123', GITHUB_INSTALLATION_ID: '456', GITHUB_APP_PRIVATE_KEY: 'dummy-test-key' };
const run = (created = at('01:00'), status = 'completed') =>
  ({ head_branch: 'main', created_at: new Date(created).toISOString(), status });
function store() {
  const map = new Map();
  return { map, async get(k) { return map.get(k); }, async put(k, v) { map.set(k, v); },
    async delete(k) { map.delete(k); }, async transaction(fn) { return fn(this); } };
}
function harness(options = {}) {
  const calls = [], logs = [], storage = options.storage || store();
  const fetcher = async (url, init) => {
    calls.push({ url, ...init });
    if (options.fetcher) return options.fetcher(url, init);
    return init.method === 'POST' ? new Response(null, { status: 204 }) :
      Response.json({ workflow_runs: options.runs || [] });
  };
  return { calls, logs, storage,
    go: (overrides = {}) => tick({ env, storage, fetcher, authenticate: async () => dummyCredential, log: line => logs.push(line), now: at('05:55'), ...overrides }) };
}

for (const [clock, workflows] of [
  ['03:59', ['recover-morning.yml', 'scan.yml']], ['04:00', ['recover-morning.yml', 'scan.yml', 'facebook-roundup.yml']],
  ['04:44', ['recover-morning.yml', 'scan.yml', 'facebook-roundup.yml']], ['04:45', ['recover-morning.yml', 'scan.yml']],
  ['05:29', ['scan.yml']], ['05:30', ['scan.yml', 'facebook-watchdog.yml']],
  ['14:59', ['recover-morning.yml', 'scan.yml', 'facebook-watchdog.yml']], ['15:00', ['recover-morning.yml', 'scan.yml']],
  ['23:59', ['scan.yml']],
]) test(`UTC/SAST boundaries at ${clock}`, () => {
  assert.deepEqual(targetsAt(at(clock)).map(t => t.workflow), workflows);
});

test('no enabled flag or no credential means no network', async () => {
  for (const config of [{}, { ...env, ENABLE_SCHEDULER: 'false' }, { ENABLE_SCHEDULER: 'true' }]) {
    const h = harness();
    assert.equal((await h.go({ env: config })).outcomes[0].result, 'disabled_or_unconfigured');
    assert.equal(h.calls.length, 0);
  }
});

test('late and future cron events cannot replay past windows', async () => {
  for (const scheduledTime of [at('05:50'), at('06:00'), NaN]) {
    const h = harness();
    assert.equal((await h.go({ scheduledTime })).outcomes[0].result, 'stale_tick');
    assert.equal(h.calls.length, 0);
  }
});

for (const status of ['queued', 'in_progress', 'waiting', 'pending', 'requested']) {
  test(`an existing ${status} workflow blocks dispatch`, async () => {
    const h = harness({ runs: [run(at('01:00'), status)] });
    assert.ok((await h.go()).outcomes.every(row => row.result === 'workflow_active'));
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
  });
}

test('recent successes AND failures prevent storm retries; stale completed runs can wake', () => {
  assert.equal(inspectRuns({ workflow_runs: [run(at('05:50'))] }, at('05:55'), 25 * minute), 'recent_run');
  assert.equal(inspectRuns({ workflow_runs: [run(at('01:00'))] }, at('05:55'), 25 * minute), null);
});

test('fixed repository/main and safe inputs; acceptance is never called publication', async () => {
  const h = harness();
  const report = await h.go();
  assert.ok(report.outcomes.every(o => o.result === 'dispatch_accepted_not_delivery'));
  const posts = h.calls.filter(c => c.method === 'POST');
  assert.equal(posts.length, 2);
  for (const call of h.calls) {
    assert.ok(call.url.startsWith(`https://api.github.com/repos/${REPOSITORY}/actions/workflows/`));
    assert.equal(call.redirect, 'manual');
    assert.equal(call.headers.Authorization, `Bearer ${dummyCredential}`);
  }
  assert.deepEqual(JSON.parse(posts[0].body), { ref: 'main', inputs: { send_reel: false } });
  assert.deepEqual(JSON.parse(posts[1].body), { ref: 'main', inputs: { publish: true } });
  assert.ok(!h.logs.join('').includes(dummyCredential));
});

test('results use normal gates, never preview/bootstrap/forced recovery', async () => {
  const h = harness();
  await h.go({ now: at('04:00') });
  const body = JSON.parse(h.calls.find(c => c.method === 'POST' && c.url.includes('roundup')).body);
  assert.deepEqual(body, { ref: 'main', inputs: { publish: true, preview: false, bootstrap: false } });
  const video = h.calls.find(c => c.method === 'POST' && c.url.includes('recover-morning'));
  assert.deepEqual(JSON.parse(video.body), { ref: 'main', inputs: { edition: 'auto' } });
});

for (const status of [301, 401, 403, 404, 429, 500]) {
  test(`HTTP ${status} run inspection fails closed without a dispatch`, async () => {
    const h = harness({ fetcher: async () => new Response('sensitive response body', { status }) });
    assert.ok((await h.go()).outcomes.every(o => o.result === 'run_inspection_failed_no_dispatch'));
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
    assert.ok(!h.logs.join('').includes('sensitive response body'));
  });
}

for (const payload of [{}, { workflow_runs: null }, { workflow_runs: [null] },
  { workflow_runs: [{ ...run(), head_branch: 'untrusted' }] },
  { workflow_runs: [{ ...run(), created_at: 'bad' }] },
  { workflow_runs: [run(at('06:00'))] }, { workflow_runs: [run(at('01:00'), 'unexpected')] }]) {
  test(`invalid run payload fails closed ${JSON.stringify(payload)}`, async () => {
    const h = harness({ fetcher: async () => Response.json(payload) });
    assert.ok((await h.go()).outcomes.every(o => o.result === 'invalid_run_list_no_dispatch'));
    assert.equal(h.calls.filter(c => c.method === 'POST').length, 0);
  });
}

test('durable cooldown works across cold invocations, and active lease prevents overlap', async () => {
  const storage = store();
  await harness({ storage }).go();
  const h = harness({ storage });
  assert.ok((await h.go({ now: at('06:00') })).outcomes.every(o => o.result === 'dispatch_cooldown'));
  assert.equal(h.calls.length, 0);
  await storage.put('lease_until', at('06:03'));
  assert.equal((await h.go({ now: at('06:01') })).outcomes[0].result, 'tick_already_running');
  assert.equal(await storage.get('lease_until'), at('06:03'));
});

test('reserve before dispatch, preserve ambiguity on timeout, no immediate retry or raw errors', async () => {
  const storage = store();
  const h = harness({ storage, fetcher: async (url, init) => {
    if (init.method === 'GET') return Response.json({ workflow_runs: [] });
    const key = 'attempt:' + url.split('/').at(-2);
    assert.equal((await storage.get(key)).outcome, 'dispatch_unknown');
    throw new Error('sensitive credential and signed URL');
  } });
  assert.ok((await h.go()).outcomes.every(o => o.result === 'request_failed_no_immediate_retry'));
  assert.equal(await storage.get('lease_until'), undefined);
  const again = harness({ storage });
  assert.ok((await again.go({ now: at('06:00') })).outcomes.every(o => o.result === 'dispatch_cooldown'));
  assert.equal(again.calls.length, 0);
  assert.ok(!h.logs.join('').includes('sensitive'));
});

test('rejected mutation is not a delivery and is also durably throttled', async () => {
  const h = harness({ fetcher: async (url, init) => init.method === 'GET' ?
    Response.json({ workflow_runs: [] }) : new Response(null, { status: 403 }) });
  assert.ok((await h.go()).outcomes.every(o => o.result === 'dispatch_rejected' && o.http_status === 403));
  assert.ok((await h.go()).outcomes.every(o => o.result === 'dispatch_cooldown'));
});

test('a failed target does not prevent independent targets being checked', async () => {
  const h = harness({ fetcher: async (url, init) => {
    if (url.includes('/scan.yml/')) throw new Error('private error');
    return init.method === 'GET' ? Response.json({ workflow_runs: [] }) : new Response(null, { status: 204 });
  } });
  assert.deepEqual((await h.go()).outcomes.map(o => o.result),
    ['request_failed_no_immediate_retry', 'dispatch_accepted_not_delivery']);
});

test('public HTTP requests cannot trigger workflows', async () => {
  assert.equal((await worker.fetch(new Request('https://public.invalid/', { method: 'POST' }))).status, 404);
});

test('scheduled handler uses fixed durable identity; missing config is inert inside object', async () => {
  const calls = [], waiting = [];
  const response = { ok: true };
  const binding = {
    idFromName(name) { assert.equal(name, 'main-timer'); return 'fixed-id'; },
    get(id) { assert.equal(id, 'fixed-id'); return { async fetch(...args) { calls.push(args); return response; } }; },
  };
  await worker.scheduled({ scheduledTime: at('05:55') }, { SCHEDULER: binding }, { waitUntil(p) { waiting.push(p); } });
  await Promise.all(waiting);
  assert.deepEqual(JSON.parse(calls[0][1].body), { scheduledTime: at('05:55') });
  const obj = new Scheduler({ storage: store() }, {});
  assert.equal((await obj.fetch(new Request('https://internal.invalid'))).status, 404);
});


test('GitHub App signs short-lived JWT and requests only this repository/Actions write', async () => {
  const { generateKeyPairSync, createPublicKey, verify } = await import('node:crypto');
  const keys = generateKeyPairSync('rsa', { modulusLength: 2048 });
  for (const type of ['pkcs1', 'pkcs8']) {
    const config = { ...env, GITHUB_APP_PRIVATE_KEY: keys.privateKey.export({ type, format: 'pem' }) };
    const token = await installationToken(config, async (url, init) => {
      assert.equal(url, 'https://api.github.com/app/installations/456/access_tokens');
      assert.equal(init.redirect, 'manual');
      assert.deepEqual(JSON.parse(init.body), { repositories: ['goals-scanner'], permissions: { actions: 'write' } });
      const jwt = init.headers.Authorization.slice(7);
      const [header, body, signature] = jwt.split('.');
      assert.deepEqual(JSON.parse(Buffer.from(header, 'base64url')), { alg: 'RS256', typ: 'JWT' });
      const claims = JSON.parse(Buffer.from(body, 'base64url'));
      assert.equal(claims.iss, '123');
      assert.equal(claims.exp - claims.iat, 9 * 60);
      assert.ok(verify('RSA-SHA256', Buffer.from(header + '.' + body),
        createPublicKey(config.GITHUB_APP_PRIVATE_KEY), Buffer.from(signature, 'base64url')));
      return Response.json({ token: dummyCredential, permissions: { actions: 'write' },
        expires_at: new Date(at('06:55')).toISOString() }, { status: 201 });
    }, at('05:55'));
    assert.equal(token, dummyCredential);
  }
});

test('App authentication failure produces no dispatch and no secret logs', async () => {
  const h = harness();
  const report = await h.go({ authenticate: async () => { throw new Error('private-key material'); } });
  assert.equal(report.outcomes[0].result, 'app_authentication_failed_no_dispatch');
  assert.equal(h.calls.length, 0);
  assert.ok(!h.logs.join('').includes('private-key material'));
  assert.equal(await h.storage.get('lease_until'), undefined);
});

test('malformed App configuration never contacts another host or installation', async () => {
  for (const config of [{ ...env, GITHUB_APP_ID: 'https://evil.invalid' },
    { ...env, GITHUB_INSTALLATION_ID: '../other' }, env]) {
    await assert.rejects(installationToken(config, () => assert.fail('network forbidden'), at('05:55')));
  }
});

test('App token endpoint denial, missing grant and expired token fail closed', async () => {
  const { generateKeyPairSync } = await import('node:crypto');
  const keys = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const config = { ...env, GITHUB_APP_PRIVATE_KEY: keys.privateKey.export({ type: 'pkcs8', format: 'pem' }) };
  for (const response of [new Response('private body', { status: 403 }),
    Response.json({ token: dummyCredential, permissions: {}, expires_at: new Date(at('06:55')).toISOString() }, { status: 201 }),
    Response.json({ token: dummyCredential, permissions: { actions: 'write' }, expires_at: new Date(at('05:54')).toISOString() }, { status: 201 }),
    Response.json({ permissions: { actions: 'write' }, expires_at: new Date(at('06:55')).toISOString() }, { status: 201 })]) {
    await assert.rejects(installationToken(config, async () => response, at('05:55')));
  }
});

test('overlapping ticks share atomic admission, not process-local locks', async () => {
  const storage = store();
  let serial = Promise.resolve();
  storage.transaction = fn => {
    const pending = serial.then(() => fn(storage));
    serial = pending.catch(() => {});
    return pending;
  };
  let entered, release;
  const reached = new Promise(resolve => { entered = resolve; });
  const gate = new Promise(resolve => { release = resolve; });
  const one = harness({ storage });
  const first = one.go({ authenticate: async () => { entered(); await gate; return dummyCredential; } });
  await reached;
  const two = harness({ storage });
  assert.equal((await two.go()).outcomes[0].result, 'tick_already_running');
  assert.equal(two.calls.length, 0);
  release();
  await first;
});

// Synthetic keys only. No production keys/tokens are stored in these fixtures.
const { generateKeyPairSync: diagnosticKeyPair } = await import('node:crypto');
const diagnosticKeys = diagnosticKeyPair('rsa', { modulusLength: 2048 });
const diagnosticEnv = { ...env,
  GITHUB_APP_PRIVATE_KEY: diagnosticKeys.privateKey.export({ type: 'pkcs1', format: 'pem' }) };
const privateError = () => Object.assign(new Error('dummy-private-upstream-message'), {
  auth_stage: 'dummy-sensitive-stage', http_status: 'dummy-sensitive-status',
  response: { body: 'dummy-sensitive-response' }, cause: 'dummy-private-cause',
});
async function expectAuthDiagnosis({ config = diagnosticEnv, fetcher, cryptography,
                                     stage, reason, status, calls = 0 }) {
  const h = harness({ fetcher: fetcher || (() => assert.fail('network forbidden')) });
  const report = await h.go({ env: config,
    authenticate: (e, f, n) => installationToken(e, f, n, cryptography) });
  assert.deepEqual(report.outcomes, [{ workflow: 'timer', result: 'app_authentication_failed_no_dispatch',
    auth_stage: stage, auth_reason: reason, ...(status ? { http_status: status } : {}) }]);
  assert.equal(h.calls.length, calls);
  assert.ok(h.calls.every(c => c.url.includes('/app/installations/') && !c.url.includes('/dispatches')));
  assert.equal(h.storage.map.size, 0, 'no auth data or dispatch reservations persisted on failure');
  assert.equal(h.logs.length, 1);
  assert.deepEqual(JSON.parse(h.logs[0]), report);
  for (const sensitive of [diagnosticEnv.GITHUB_APP_PRIVATE_KEY, dummyCredential,
    'dummy-private-upstream-message', 'dummy-sensitive', 'dummy-private-cause',
    'BEGIN RSA PRIVATE KEY', 'Authorization', 'Bearer', '/access_tokens']) {
    assert.ok(!h.logs[0].includes(sensitive), 'only allowlisted metadata may be logged');
  }
}

for (const [name, value, reason] of [
  ['GITHUB_APP_ID', 'dummy-client-id', 'app_id_not_positive_integer'],
  ['GITHUB_APP_ID', '123 ', 'app_id_not_positive_integer'],
  ['GITHUB_INSTALLATION_ID', 'https://github.com/settings/installations/456', 'installation_id_not_positive_integer'],
  ['GITHUB_INSTALLATION_ID', '0', 'installation_id_not_positive_integer'],
]) test(`diagnose configuration: ${name} ${reason} ${value}`, async () => {
  await expectAuthDiagnosis({ config: { ...diagnosticEnv, [name]: value }, stage: 'configuration', reason });
});

test('diagnose fingerprint/header, base64 and DER failures separately without exposing key bytes', async () => {
  for (const [pem, stage, reason] of [
    ['SHA256:dummy-fingerprint', 'pem_decode', 'private_key_header_invalid'],
    ['-----BEGIN RSA PRIVATE KEY-----\n%%%%\n-----END RSA PRIVATE KEY-----', 'pem_decode', 'private_key_base64_invalid'], // dummy invalid-base64 fixture, not a credential
    ['-----BEGIN PRIVATE KEY-----\nYWJj\n-----END PRIVATE KEY-----', 'key_import', 'private_key_import_failed'], // dummy three-byte DER fixture, not a credential
  ]) await expectAuthDiagnosis({ config: { ...diagnosticEnv, GITHUB_APP_PRIVATE_KEY: pem }, stage, reason });
});

test('diagnose key import and JWT signing exceptions without trusting upstream error fields', async () => {
  await expectAuthDiagnosis({ stage: 'key_import', reason: 'private_key_import_failed',
    cryptography: { subtle: { importKey: async () => { throw privateError(); } } } });
  await expectAuthDiagnosis({ stage: 'jwt_sign', reason: 'jwt_signing_failed',
    cryptography: { subtle: { importKey: async () => ({}), sign: async () => { throw privateError(); } } } });
});

test('diagnose network/timeout before any token response; do not expose exception text', async () => {
  await expectAuthDiagnosis({ stage: 'installation_token_request', reason: 'network_or_timeout', calls: 1,
    fetcher: async () => { throw privateError(); } });
});

for (const status of [301, 401, 403, 404, 422, 429, 500]) {
  test(`diagnose installation token HTTP ${status}, never read or print its body`, async () => {
    await expectAuthDiagnosis({ stage: 'installation_token_http', reason: 'github_rejected_token_request', status, calls: 1,
      fetcher: async () => ({ status, json() { assert.fail('error response body must not be read'); } }) });
  });
}

test('diagnose JSON response parse failure separately', async () => {
  await expectAuthDiagnosis({ stage: 'installation_token_response', reason: 'response_not_json', status: 201, calls: 1,
    fetcher: async () => ({ status: 201, json: async () => { throw privateError(); } }) });
});

for (const [body, reason] of [
  [null, 'response_schema_invalid'], [[], 'response_schema_invalid'], ['dummy-sensitive', 'response_schema_invalid'],
  [{ token: '' }, 'token_missing'], [{ token: dummyCredential, permissions: { actions: 'read' } }, 'actions_write_not_granted'],
  [{ token: dummyCredential, permissions: { actions: 'write' }, expires_at: 'bad' }, 'token_expiry_invalid'],
  [{ token: dummyCredential, permissions: { actions: 'write' }, expires_at: new Date(at('05:54')).toISOString() }, 'token_expiry_invalid'],
]) test(`diagnose installation token response: ${reason} ${JSON.stringify(body)}`, async () => {
  await expectAuthDiagnosis({ stage: 'installation_token_response', reason, status: 201, calls: 1,
    fetcher: async () => Response.json(body, { status: 201 }) });
});

test('unrecognized errors cannot inject diagnostic fields or secrets into report', async () => {
  const h = harness();
  const report = await h.go({ authenticate: async () => { throw privateError(); } });
  assert.deepEqual(report.outcomes, [{ workflow: 'timer', result: 'app_authentication_failed_no_dispatch',
    auth_stage: 'unknown', auth_reason: 'unexpected_error' }]);
  assert.ok(!h.logs.join('').includes('dummy-private'));
  assert.ok(!h.logs.join('').includes('dummy-sensitive'));
});

test('whitespace and collapsed PEM line breaks are not themselves authentication failures', async () => {
  for (const pem of [diagnosticEnv.GITHUB_APP_PRIVATE_KEY.replaceAll('\n', ''),
    ' \n' + diagnosticEnv.GITHUB_APP_PRIVATE_KEY.replaceAll('\n', '\r\n\r\n') + '\n ']) {
    const token = await installationToken({ ...diagnosticEnv, GITHUB_APP_PRIVATE_KEY: pem }, async () =>
      Response.json({ token: dummyCredential, permissions: { actions: 'write' },
        expires_at: new Date(at('06:55')).toISOString() }, { status: 201 }), at('05:55'));
    assert.equal(token, dummyCredential);
  }
});


for (const [clock, due] of [['02:59',false],['03:00',true],['05:19',true],['05:20',false],
  ['08:59',false],['09:00',true],['10:19',true],['10:20',false],
  ['13:59',false],['14:00',true],['15:19',true],['15:20',false]]) {
  test(`video-only window at UTC ${clock}: ${due}`, () => {
    const targets = targetsAt(at(clock));
    assert.equal(targets.some(t => t.workflow === 'recover-morning.yml'), due);
    if (due) {
      assert.equal(targets[0].workflow, 'recover-morning.yml');
      assert.deepEqual(targets[0].inputs, { edition: 'auto' });
      assert.equal(targets[0].interval, 10 * minute);
    }
  });
}
