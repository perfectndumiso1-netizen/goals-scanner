// This timer can only wake the existing main-branch workflows. It has no Facebook,
// provider or Telegram credentials and must never decide whether a post was sent.
export const REPOSITORY = 'perfectndumiso1-netizen/goals-scanner';
const MINUTE = 60_000;
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'pending', 'requested']);
const BASE = `https://api.github.com/repos/${REPOSITORY}/actions/workflows/`;

export function targetsAt(now) {
  const date = new Date(now);
  if (!Number.isFinite(date.getTime())) throw new Error('invalid_clock');
  const minute = date.getUTCHours() * 60 + date.getUTCMinutes();
  const targets = [];
  // Queue video work before a heavyweight scan. Both use the existing goals-scan
  // mutex and edition markers; auto is never a forced catch-up outside a window.
  const videoDue = [[180, 320], [540, 620], [840, 920]].some(([start, end]) => minute >= start && minute < end);
  // Out-of-window health-only runs detect a completely missed edition. They
  // cannot render, upload, force catch-up or change media delivery reservations.
  targets.push({ workflow: 'recover-morning.yml', interval: (videoDue ? 10 : 15) * MINUTE,
    inputs: { edition: videoDue ? 'auto' : 'health' } });
  targets.push({ workflow: 'scan.yml', interval: 25 * MINUTE, inputs: { send_reel: false } });
  // SAST = UTC+2. The publisher, not this timer, enforces each actual content slot.
  if (minute >= 330 && minute < 900) {
    targets.push({ workflow: 'facebook-watchdog.yml', interval: 10 * MINUTE, inputs: { publish: true } });
  }
  if (minute >= 240 && minute < 285) {
    targets.push({ workflow: 'facebook-roundup.yml', interval: 10 * MINUTE,
      inputs: { publish: true, preview: false, bootstrap: false } });
  }
  return targets;
}

export function inspectRuns(payload, now, interval) {
  if (!payload || !Array.isArray(payload.workflow_runs)) throw new Error('invalid_run_list');
  let latest = -Infinity;
  let active = false;
  for (const run of payload.workflow_runs) {
    const created = Date.parse(run.created_at);
    if (run.head_branch !== 'main' || !Number.isFinite(created) || created > now + MINUTE ||
        !['completed', ...ACTIVE].includes(run.status)) throw new Error('invalid_run_list');
    latest = Math.max(latest, created);
    active ||= ACTIVE.has(run.status);
  }
  if (active) return 'workflow_active';
  if (now - latest < interval) return 'recent_run';
  return null;
}

async function github(workflow, suffix, token, fetcher, body) {
  // Workers supports only follow/manual, not redirect:error. Never follow a
  // redirect with credentials; callers reject every non-exact success status.
  // No user-controlled URL, exception text, response body or token in logs.
  const response = await fetcher(BASE + workflow + suffix, {
    method: body ? 'POST' : 'GET',
    redirect: 'manual',
    signal: AbortSignal.timeout(8_000),
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'goals-scanner-independent-timer',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  return response;
}

function der(tag, bytes) {
  const length = bytes.length;
  const size = length < 128 ? [length] : length < 256 ? [0x81, length] : [0x82, length >> 8, length & 255];
  return new Uint8Array([tag, ...size, ...bytes]);
}

const base64url = bytes => btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');

// Only errors created here carry diagnostic metadata. Never serialize an
// upstream exception, cause, response body, JWT, ID, URL or secret value.
const AUTH_FAILURES = new WeakMap();
function authFailure(stage, reason, status) {
  const error = new Error('Timer authentication failed');
  AUTH_FAILURES.set(error, {
    auth_stage: stage, auth_reason: reason,
    ...(Number.isInteger(status) && status >= 100 && status <= 599 ? { http_status: status } : {}),
  });
  return error;
}

export async function installationToken(env, fetcher, now, cryptography = globalThis.crypto) {
  if (!/^[1-9][0-9]*$/.test(env.GITHUB_APP_ID)) {
    throw authFailure('configuration', 'app_id_not_positive_integer');
  }
  if (!/^[1-9][0-9]*$/.test(env.GITHUB_INSTALLATION_ID)) {
    throw authFailure('configuration', 'installation_id_not_positive_integer');
  }
  const pem = env.GITHUB_APP_PRIVATE_KEY;
  if (typeof pem !== 'string' || !/^-----BEGIN (RSA )?PRIVATE KEY-----/.test(pem.trim())) {
    throw authFailure('pem_decode', 'private_key_header_invalid');
  }
  let bytes;
  try {
    bytes = Uint8Array.from(atob(pem.replace(/-----[^-]+-----/g, '').replace(/\s/g, '')), c => c.charCodeAt(0));
    if (pem.includes('BEGIN RSA PRIVATE KEY')) {
      // GitHub downloads PKCS#1; Web Crypto imports PKCS#8. Wrap the original
      // bytes locally, without a conversion service or writing a key to disk.
      const rsaAlgorithm = [0x30, 0x0d, 0x06, 0x09, 0x2a, 0x86, 0x48, 0x86, 0xf7, 0x0d, 0x01, 0x01, 0x01, 0x05, 0x00];
      bytes = der(0x30, new Uint8Array([0x02, 0x01, 0x00, ...rsaAlgorithm, ...der(0x04, bytes)]));
    }
  } catch {
    throw authFailure('pem_decode', 'private_key_base64_invalid');
  }
  let key;
  try {
    key = await cryptography.subtle.importKey('pkcs8', bytes,
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['sign']);
  } catch {
    throw authFailure('key_import', 'private_key_import_failed');
  }
  let jwt;
  try {
    const encode = data => base64url(new TextEncoder().encode(JSON.stringify(data)));
    const seconds = Math.floor(now / 1000);
    const unsigned = encode({ alg: 'RS256', typ: 'JWT' }) + '.' +
      encode({ iat: seconds - 60, exp: seconds + 8 * 60, iss: env.GITHUB_APP_ID });
    const signature = await cryptography.subtle.sign('RSASSA-PKCS1-v1_5', key, new TextEncoder().encode(unsigned));
    jwt = `${unsigned}.${base64url(new Uint8Array(signature))}`;
  } catch {
    throw authFailure('jwt_sign', 'jwt_signing_failed');
  }
  let response;
  try {
    response = await fetcher(`https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`, {
      method: 'POST', redirect: 'manual', signal: AbortSignal.timeout(8_000),
      headers: { Authorization: `Bearer ${jwt}`,
        Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'goals-scanner-independent-timer', 'Content-Type': 'application/json' },
      body: JSON.stringify({ repositories: ['goals-scanner'], permissions: { actions: 'write' } }),
    });
  } catch {
    throw authFailure('installation_token_request', 'network_or_timeout');
  }
  if (response.status !== 201) {
    throw authFailure('installation_token_http', 'github_rejected_token_request', response.status);
  }
  let body;
  try { body = await response.json(); }
  catch { throw authFailure('installation_token_response', 'response_not_json', 201); }
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw authFailure('installation_token_response', 'response_schema_invalid', 201);
  }
  if (typeof body.token !== 'string' || !body.token) {
    throw authFailure('installation_token_response', 'token_missing', 201);
  }
  if (body.permissions?.actions !== 'write') {
    throw authFailure('installation_token_response', 'actions_write_not_granted', 201);
  }
  if (!(Date.parse(body.expires_at) > now + MINUTE)) {
    throw authFailure('installation_token_response', 'token_expiry_invalid', 201);
  }
  return body.token; // Short-lived; never persisted in Durable Object storage or logs.
}

export async function tick({ storage, env, now = Date.now(), scheduledTime = now,
                             fetcher = fetch, authenticate = installationToken, log = console.log }) {
  const report = { checked_at: new Date(now).toISOString(), outcomes: [] };
  const emit = (workflow, result, status) => {
    report.outcomes.push({ workflow, result, ...(status ? { http_status: status } : {}) });
  };
  if (env.ENABLE_SCHEDULER !== 'true' || !env.GITHUB_APP_ID || !env.GITHUB_INSTALLATION_ID || !env.GITHUB_APP_PRIVATE_KEY) {
    emit('timer', 'disabled_or_unconfigured');
  } else if (!Number.isFinite(scheduledTime) || now - scheduledTime > 2 * MINUTE || scheduledTime > now + MINUTE) {
    // Never replay an old tick or force a missed video after its actual window.
    emit('timer', 'stale_tick');
  } else {
    const acquired = await storage.transaction(async transaction => {
      if ((await transaction.get('lease_until') || 0) > now) return false;
      await transaction.put('lease_until', now + 3 * MINUTE);
      return true;
    });
    if (!acquired) {
      emit('timer', 'tick_already_running');
    } else {
      try {
        let token;
        try { token = await authenticate(env, fetcher, now); }
        catch (error) {
          report.outcomes.push({ workflow: 'timer', result: 'app_authentication_failed_no_dispatch',
            ...(AUTH_FAILURES.get(error) || { auth_stage: 'unknown', auth_reason: 'unexpected_error' }) });
          log(JSON.stringify(report));
          return report;
        }
        for (const target of targetsAt(now)) {
          const key = `attempt:${target.workflow}`;
          try {
            const previous = await storage.get(key);
            if (previous && now - previous.at < target.interval) {
              emit(target.workflow, 'dispatch_cooldown');
              continue;
            }
            const response = await github(target.workflow, '/runs?branch=main&per_page=100', token, fetcher);
            if (response.status !== 200) {
              emit(target.workflow, 'run_inspection_failed_no_dispatch', response.status);
              continue;
            }
            let reason;
            try { reason = inspectRuns(await response.json(), now, target.interval); }
            catch { emit(target.workflow, 'invalid_run_list_no_dispatch'); continue; }
            if (reason) { emit(target.workflow, reason); continue; }
            // Durable reservation BEFORE the network mutation. A timeout, crash or
            // ambiguous response cannot cause an immediate duplicate dispatch.
            await storage.put(key, { at: now, outcome: 'dispatch_unknown' });
            const dispatched = await github(target.workflow, '/dispatches', token, fetcher,
              { ref: 'main', inputs: target.inputs });
            const result = dispatched.status === 204 ? 'dispatch_accepted_not_delivery' : 'dispatch_rejected';
            await storage.put(key, { at: now, outcome: result });
            emit(target.workflow, result, dispatched.status);
          } catch {
            emit(target.workflow, 'request_failed_no_immediate_retry');
          }
        }
      } finally {
        await storage.delete('lease_until');
      }
    }
  }
  log(JSON.stringify(report));
  return report;
}
