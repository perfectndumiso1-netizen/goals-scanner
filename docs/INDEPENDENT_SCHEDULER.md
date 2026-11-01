# Independent scheduling — Cloudflare timer

**Status: code prepared; NOT deployed or activated by this repository change.**
The November 1 investigation found missing GitHub scheduled executions. A manual
watchdog run recovered a verified text post; that does not repair GitHub cron or
wake the separate video workflow. Cloudflare must actually be configured below
before this timer provides any coverage. No Cloudflare account/deployment access
is available to the coding session. Existing GitHub schedules remain as a second
trigger, not as the claimed independent fallback.

## Phone setup checklist

Do not put any private key, token or password in chat, a repository file, a build
command, URL or screenshot. This setup uses a dedicated GitHub App, **not your
GitHub password, this session's credentials or a personal access token**.

### 1. Give the timer its own narrowly scoped GitHub identity

In GitHub's web settings (use **Desktop site** on your phone if needed):

1. **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. Choose a unique app name and use this repository's GitHub URL for Homepage.
   Turn off **Active** under Webhook; no callback, webhook, user OAuth flow or
   subscribed events are required. Make the app installable only on your account.
3. Under **Repository permissions**, grant **Actions: Read and write** only.
   Metadata read is implicit. Do not grant Contents write, Secrets, Administration,
   or any organization/account permissions.
4. Create the app, record its **App ID**, and generate a private key. Keep the
   downloaded PEM private; it is entered only into Cloudflare's encrypted secret.
5. **Install App → your account → Only select repositories → goals-scanner**.
   Record the installation ID from the installation page's URL (the number after
   `/settings/installations/`). Do not copy another installation's ID.

Actions write can dispatch other workflows in this one repository if the App key
is stolen; GitHub does not offer per-workflow dispatch permissions. The Worker
itself hard-codes only three workflow names and `main`. Its short-lived tokens
are explicitly scoped to this repository and Actions write, held only in memory.
This separate owner-approved app does not change or bypass Arena's denied
workflow-dispatch permission.

### 2. Deploy the Worker from GitHub in Cloudflare

After the tested change is merged:

1. Sign in to Cloudflare. **Workers & Pages → Create application → Import a
   repository / Connect Git**. Choose **Workers**, not a static Pages project.
2. Connect GitHub and select `perfectndumiso1-netizen/goals-scanner`, production
   branch **main**. Set the **root directory** to `automation/scheduler`.
3. Set **build command** to `npm ci && npm test`, **deploy command** to
   `npm run deploy`. Use Node **22 or newer** (for example the build environment
   variable `NODE_VERSION=22`). Name the Worker **goals-scanner-timer**.
4. Deploy. Wrangler reads `wrangler.jsonc`, provisions the SQLite-backed Durable
   Object and installs the `*/5 * * * *` UTC trigger. No public route/domain is
   needed; workers.dev and preview URLs are deliberately off.
5. In the deployed Worker's **Settings → Variables and Secrets**, add:

   | Name | Type | Value |
   |---|---|---|
   | `GITHUB_APP_ID` | Secret | Your recorded App ID |
   | `GITHUB_INSTALLATION_ID` | Secret | Your recorded installation ID |
   | `GITHUB_APP_PRIVATE_KEY` | Secret | Entire downloaded PEM, including BEGIN/END lines and real line breaks |
   | `ENABLE_SCHEDULER` | Secret | `true` — add **last**, when ready to allow real workflow dispatches |

   Use encrypted **Secret** for all four bindings so Git redeploys don't replace
   them with defaults. Missing bindings leave the deployed timer inert.
6. Under **Triggers / Cron Triggers**, confirm `*/5 * * * *` exists. Trigger
   changes can take several minutes to propagate; don't create a second timer or
   reset its Durable Object just because the first wake-up hasn't appeared yet.

Git integration labels may vary. If the account cannot deploy a Worker with the
SQLite Durable Object binding, stop and resolve that prerequisite; do not silently
substitute process memory or remove the admission guard. Review current Cloudflare
plan limits/pricing in the account before enabling; no paid plan was purchased or
free-tier entitlement verified by this change.

### 3. Prove that it actually works

1. Open **Worker → Observability → Logs** after a cron wake-up. Logs contain
   workflow names and safe operational outcomes, never keys, tokens, response
   bodies or signed URLs.
2. `workflow_active` / `recent_run` means GitHub already has a suitable run.
   `dispatch_cooldown` means a prior external attempt is still throttled.
   `dispatch_accepted_not_delivery` means GitHub accepted a dispatch — **not**
   that a video/post was delivered.
3. Confirm a matching `workflow_dispatch` run on GitHub's Actions page. Verify
   the actual per-lane acknowledgement/read-back and post/Reel ID separately.
   A Telegram receipt does not prove Facebook visibility.
4. Confirm a **second automatic cron wake-up**, the durable cooldown/active-run
   check, and the next due content window. Only then describe the independent
   timer as live and tested. Deliberately disabling GitHub schedules is not needed.
5. `app_authentication_failed_no_dispatch`, `run_inspection_failed_no_dispatch`
   or `dispatch_rejected` needs attention. Check App installation, permissions,
   IDs and key privately. A 403 is not a reason to broaden permissions, reset
   publication state or repeatedly resend a video.

To stop external dispatches, set the `ENABLE_SCHEDULER` secret to `false` and
confirm `disabled_or_unconfigured`. Removing the cron trigger also stops wake-ups.
Do not delete/reset Durable Object state to troubleshoot delivery uncertainty.
To revoke the identity, suspend/uninstall the dedicated GitHub App; rotating its
private key requires updating the Cloudflare secret and re-verifying wake-ups.

## Exact cadence and scope

The external clock ticks every five minutes, but it doesn't dispatch every target
every five minutes. It checks real GitHub runs and its own durable reservations:

| Target | Eligible SAST time | Minimum age since latest run / external attempt |
|---|---|---|
| `scan.yml` | All day | 25 minutes, and no active run |
| `facebook-roundup.yml` | 06:00–06:44 | 10 minutes, and no active run |
| `facebook-watchdog.yml` | 07:30–16:59 | 10 minutes, and no active run |

With a five-minute tick, the scan wakes approximately every 25–30 minutes when
GitHub cron is absent. It also refreshes the app and resumes the existing bounded
Facebook recovery queue, just as the normal scanner does. It never sets
`send_reel=true`: automatic videos remain in their current **05:00–07:19,
11:00–12:19 and 16:00–17:19 SAST** windows. Stale ticks aren't replayed. A missed
morning video outside its window still needs explicit guarded recovery.

Roundup dispatch uses `publish=true`, `preview=false`, `bootstrap=false`;
watchdog uses `publish=true`. No paused live/community/card/weekly lane is enabled.
No YouTube/Drive upload is enabled. Existing feed/scanner mutexes, source freshness,
real kickoff checks, quota/cooldown accounting, reservations, hashes, expiry,
read-back and unknown-send blocks remain authoritative. This timer never reads,
modifies or resets the delivery ledger, and never calls Facebook/provider APIs.
A durable pre-dispatch reservation throttles even ambiguous dispatch timeouts;
a later attempt first checks GitHub's actual runs again.

This removes dependency on **GitHub's cron clock**, not dependency on GitHub's
Actions runners/API. A GitHub outage, invalid publishing credentials, missing
verified picks, provider limits or platform rejection can still prevent delivery.
Cloudflare's own cron is also best-effort. No exact-minute or guaranteed-post
claim is made. Logs are available, but this change does **not** add an independent
email/SMS/Telegram alert service if both systems stop executing.

## Local validation / maintainer commands

```sh
cd automation/scheduler
npm ci
npm test
npm run check    # Bundle/config dry run + local workerd smoke test; does not deploy
```

Tests use mocked HTTP/storage plus generated in-memory RSA keys for both GitHub
PKCS#1 and PKCS#8 signing. The local smoke test also loads the actual bundle and SQLite Durable Object
in workerd, asserts the disabled state and public 404, and forbids outbound
network requests. No real credentials, provider requests, live publishing
or Cloudflare deployment are part of local tests. GitHub's existing Python-tests
workflow also runs the dependency-free timer tests on pull requests.
