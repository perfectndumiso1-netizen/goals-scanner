"""Outcome-based editorial supervisor. No blind resends, ledger resets or quota bypass.

assess -> durable admission artifact -> existing prepare/reserve/send -> audit
All phases share the feed workflow mutex and production artifact namespace.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.request import Request, build_opener

from . import content, storage
from .editorial import SLOTS, due
from .publisher import PageFeed, PublishError
from facebook_post import _NoRedirect

MAX_ATTEMPTS = 3
BACKOFF = (10, 20, 40)
SAFE_SKIPS = {
    'no distinct verified upcoming fixture for this slot',
    'No safely upcoming 1X2 selections on Bet Advisor; no filler',
    'no distinct completed match with verified incidents',
    'no verified fixtures or new confirmed finals; no filler',
    'Five recent completed league matches unavailable; no card',
    'Recent final score missing; sample cannot be backfilled',
    'Extra-time/shootout sample needs editorial scope review',
    'Featured match is not safely upcoming',
}
TRANSIENT = {'Highlightly network/response validation failed; details omitted',
             'Bet Advisor publication unavailable or stale; no predictions'}


def slot_at(now, slots=None):
    now=content.local(now)
    for clock,slot in reversed(slots or SLOTS):
        start=now.replace(hour=int(clock[:2]),minute=int(clock[3:]),second=0,microsecond=0)
        if timedelta(0)<=now-start<timedelta(hours=1):return f'editorial:{start.date()}:{slot}',start
    return None


def current_slot(state,now):
    return slot_at(now,state.get('editorial_delivery',{}).get('schedule'))


def book(state, now, slots=None):
    journal = state.setdefault('editorial_delivery', {'version': 1, 'since': (slot_at(now,slots) or ('', now))[1].isoformat(), 'slots': {}})
    if journal.get('version') != 1 or not isinstance(journal.get('slots'), dict):
        raise storage.StateError('Watchdog journal invalid; no reset or publishing allowed')
    if slots is not None and journal.get('schedule') != [list(p) for p in slots]:
        # Migrate monitoring metadata only; NEVER reset posts, ambiguous sends,
        # quota, retries or publication evidence when a timetable changes.
        journal['schedule']=[list(p) for p in slots]
        journal['since']=(slot_at(now,slots) or ('',now))[1].isoformat()
    # Only monitoring summaries expire. Publication history and unknowns never reset.
    cutoff = now - timedelta(days=7)
    journal['slots'] = {k: v for k, v in journal['slots'].items() if content.local(v['start']) >= cutoff}
    return journal


def sync(state, now):
    journal = book(state, now)
    # Positively reconciled old-timetable reservations must stop alerting even
    # after schedule migration (publication history itself is never reset).
    for key,row in journal['slots'].items():
        if any(p.get('slot_key')==key and p.get('kind')=='editorial' and p.get('status')=='published' for p in state['posts']):
            row.update(status='delivered',diagnosis='facebook_verified')
    for day in (now - timedelta(days=1), now):
        for clock, name in journal.get('schedule',SLOTS):
            start = day.replace(hour=int(clock[:2]), minute=int(clock[3:]), second=0, microsecond=0)
            if not content.local(journal['since']) <= start <= now:
                continue
            key = f'editorial:{start.date()}:{name}'
            row = journal['slots'].setdefault(key, {'start': start.isoformat(), 'attempts': 0, 'status': 'pending'})
            entries = [p for p in state['posts'] if p.get('kind') == 'editorial' and p.get('slot_key') == key]
            if any(p.get('status') == 'published' for p in entries):
                row.update(status='delivered', diagnosis='facebook_verified')
            elif any(p.get('status') in ('reserved', 'unknown') for p in entries):
                unresolved = [p for p in entries if p.get('status') in ('reserved', 'unknown')]
                exhausted = any(p.get('delivery_check', {}).get('attempts', 0) >= MAX_ATTEMPTS for p in unresolved)
                if exhausted or now >= start + timedelta(hours=1):
                    row.update(status='needs_attention', diagnosis='ambiguous_publication_no_resend')
                else:
                    row.update(status='verifying', diagnosis='verification_pending_no_resend')
            elif now >= start + timedelta(hours=1) and row['status'] not in ('delivered', 'skipped', 'needs_attention'):
                row.update(status='needs_attention', diagnosis='slot_expired_without_delivery')
    for row in journal['slots'].values():
        if (row.get('diagnosis') == 'unresolved_publication_no_resend' and
            now < content.local(row['start']) + timedelta(hours=1) and
            not any(p.get('status') in ('reserved', 'unknown') for p in state['posts'])):
            row.update(status='pending', diagnosis='prior_publication_reconciled')
    return journal


def reconcile_known(state, now, factory=PageFeed):
    """Positive read-back only. Empty/missing/partial feed results NEVER prove absence."""
    publisher = None
    checked = 0
    for entry in state['posts']:
        if entry.get('kind') not in ('editorial','results') or entry.get('status') not in ('unknown', 'reserved'):
            continue
        check = entry.setdefault('delivery_check', {'attempts': 0})
        if check['attempts'] >= MAX_ATTEMPTS or check.get('next_at') and now < content.local(check['next_at']):
            continue
        if checked >= MAX_ATTEMPTS:
            break
        checked += 1
        check['attempts'] += 1
        check['next_at'] = (now + timedelta(minutes=BACKOFF[check['attempts'] - 1])).isoformat()
        try:
            publisher = publisher or factory()
            identity = entry.get('post_id') or publisher.find_reserved(entry)
            if not identity:
                continue
            if entry.get('image_sha256s'):
                publisher.verify_package_hash(identity,entry['caption_hash'],entry.get('media_ids'))
            else:
                publisher.verify_hash(identity, entry['caption_hash'])
            entry.update(status='published', post_id=identity, reconciled_at=now.isoformat())
            entry.pop('error', None)
        except PublishError:
            pass  # Never cancel, replace or claim that a post was absent.


def assess(state, now, run_key, *, max_pages=10, daily_budget=100):
    journal = sync(state, now)
    current = current_slot(state,now)
    if current is None:
        return False, 'outside_slot'
    key, start = current
    row = journal['slots'][key]
    if row['status'] in ('delivered', 'skipped', 'needs_attention', 'verifying'):
        return False, row.get('diagnosis', row['status'])
    if any(p.get('status') in ('reserved', 'unknown') for p in state['posts']):
        row.update(status='needs_attention', diagnosis='unresolved_publication_no_resend')
        return False, row['diagnosis']
    counted = [p for p in state['posts'] if p.get('status') not in ('cancelled', 'rejected')]
    if counted and now < max(content.local(p['at']) for p in counted) + timedelta(minutes=45):
        return False, 'feed_spacing_wait'
    if row.get('next_at') and now < content.local(row['next_at']):
        return False, 'retry_backoff'
    if row['attempts'] >= MAX_ATTEMPTS:
        row.update(status='needs_attention', diagnosis='bounded_retries_exhausted')
        return False, row['diagnosis']
    if key.endswith(':predictions'):
        # This slot only reads the published Advisor JSON, never Highlightly.
        row['attempts']+=1
        row.update(status='preparing',diagnosis='admitted',run_key=run_key,
                   quota_hold={'amount':0,'source':'published-bet-advisor','released':False},
                   next_at=(now+timedelta(minutes=BACKOFF[row['attempts']-1])).isoformat())
        return True,'admitted'
    budget = state.get('highlightly_api', {})
    # Transport is still the authority for UTC rollover and the hard 100 cap.
    # Do not reinterpret yesterday's count as today's exhaustion.
    if budget.get('utc_date') == now.astimezone(timezone.utc).date().isoformat() and (budget.get('requests', 0) >= 100 or budget.get('remaining') == 0):
        row.update(status='skipped', diagnosis='shared_quota_exhausted')
        return False, row['diagnosis']
    if budget.get('after') and now < content.local(budget['after']):
        row.update(status='waiting', diagnosis='provider_cooldown', next_at=budget['after'])
        return False, row['diagnosis']
    # Debit a worst-case preparation allowance in the durable admission. If
    # prepare is killed after a provider request, this conservative debit stays
    # spent. A normal, checkpointed preparation releases the UNUSED hold locally
    # before using the unchanged transport's actual/header-based accounting.
    day = now.astimezone(timezone.utc).date().isoformat()
    budget = state.setdefault('highlightly_api', {})
    if budget.get('utc_date') != day:
        cooldown = budget.get('after')
        budget.clear(); budget.update(utc_date=day, requests=0, remaining=None)
        if cooldown:
            budget['after'] = cooldown
    available = min(daily_budget - budget.get('requests', 0),
                    budget.get('remaining') if budget.get('remaining') is not None else daily_budget)
    if available <= 0:
        row.update(status='skipped', diagnosis='shared_quota_exhausted')
        return False, row['diagnosis']
    hold = min(3 * max_pages + 3, available)
    budget['requests'] += hold
    row['quota_hold'] = {'utc_date': day, 'amount': hold, 'released': False}
    row['attempts'] += 1
    row.update(status='preparing', diagnosis='admitted', run_key=run_key,
               next_at=(now + timedelta(minutes=BACKOFF[row['attempts'] - 1])).isoformat())
    return True, 'admitted'


def release_quota_hold(state, row):
    """In-memory release for THIS admitted prepare, never an older failed run.

    The pre-prepare durable artifact still includes the entire hold. If this
    process dies, no provider request spent in it is erased from accounting.
    """
    hold = row.get('quota_hold', {})
    budget = state.get('highlightly_api', {})
    amount = hold.get('amount')
    if type(amount) is int and amount==0 and hold.get('source')=='published-bet-advisor' and hold.get('released') is False:
        hold['released']=True;return
    if (hold.get('released') is not False or type(amount) is not int or not 1 <= amount <= 33 or
        hold.get('utc_date') != budget.get('utc_date') or budget.get('requests', 0) < amount):
        raise storage.StateError('Invalid watchdog quota hold; no provider request allowed')
    budget['requests'] -= amount
    hold['released'] = True


def record(state, now, report):
    current = current_slot(state,now)
    if not current:
        return
    row = book(state, now)['slots'].get(current[0])
    if not row or row['status'] != 'preparing':
        return
    result = report[0] if len(report) == 1 else {}
    reason = result.get('reason', '')
    if result.get('status') == 'reserved':
        row.update(status='reserved', diagnosis='awaiting_facebook_confirmation')
    elif reason in SAFE_SKIPS:
        row.update(status='skipped', diagnosis='verified_content_unavailable')
    elif reason in TRANSIENT:
        row.update(status='waiting', diagnosis='temporary_source_failure')
    elif reason == 'Highlightly daily budget unavailable; cached data retained' or state.get('highlightly_api', {}).get('remaining') == 0:
        row.update(status='skipped', diagnosis='shared_quota_exhausted')
    elif reason == 'Highlightly request rejected; details omitted, no provider/key switching':
        budget = state.get('highlightly_api', {})
        if budget.get('last_failure') in ('authentication_rejected', 'access_restriction'):
            row.update(status='needs_attention', diagnosis='provider_access_blocked')
        elif budget.get('last_failure') == 'rate_or_quota_rejection':
            row.update(status='waiting', diagnosis='provider_cooldown')
            if budget.get('after'):
                row['next_at'] = max(content.local(row['next_at']), content.local(budget['after'])).isoformat()
        else:
            row.update(status='needs_attention', diagnosis='provider_request_blocked')
    else:
        row.update(status='needs_attention', diagnosis='preparation_blocked')


def audit(state, now, pipeline_ok=True):
    journal = book(state, now)
    for key, row in journal['slots'].items():
        entries = [p for p in state['posts'] if p.get('slot_key') == key and p.get('kind') == 'editorial']
        if entries and all(p.get('status') in ('cancelled', 'rejected') for p in entries) and row['status'] == 'reserved':
            # Only explicit local preflight/expiry cancellations can be rebuilt.
            last = entries[-1]
            if last.get('delivery_failure') in ('preflight_temporary', 'expired_before_mutation', 'unpublished_staging_incomplete'):
                row.update(status='waiting', diagnosis=last['delivery_failure'])
            else:
                row.update(status='needs_attention', diagnosis='facebook_preflight_blocked')
    journal = sync(state, now)
    for row in journal['slots'].values():
        if row['status'] in ('waiting', 'preparing') and row['attempts'] >= MAX_ATTEMPTS:
            row.update(status='needs_attention', diagnosis='bounded_retries_exhausted')
    incidents = [{'slot': k, 'diagnosis': v['diagnosis'], 'attempts': v['attempts']}
                 for k, v in journal['slots'].items() if v['status'] == 'needs_attention']
    current = current_slot(state,now)
    active = journal['slots'].get(current[0], {}) if current else {}
    retry_expected = active.get('status') in ('waiting', 'verifying') and active.get('attempts', 0) < MAX_ATTEMPTS
    if not pipeline_ok and not retry_expected:
        incidents.append({'slot': f'pipeline:{now.date()}', 'diagnosis': 'workflow_step_failed', 'attempts': 0})
    return {'checked_at': now.isoformat(), 'incidents': incidents, 'counts': {
        s: sum(r['status'] == s for r in journal['slots'].values())
        for s in ('delivered', 'skipped', 'waiting', 'pending', 'preparing', 'reserved', 'verifying', 'needs_attention')}}


def json_request(opener, url, payload=None, token=None):
    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    raw = None if payload is None else json.dumps(payload).encode()
    if raw is not None:
        headers['Content-Type'] = 'application/json'
    with opener.open(Request(url, data=raw, headers=headers), timeout=25) as response:
        value = json.loads(response.read(1024 * 1024))
    return value


def notify(report, state=None, opener=None, *, allow_github=True):
    """Only fixed diagnosis enums, counts and run URLs leave the runner. No raw errors."""
    if not report['incidents']:
        return 'not_needed'
    # Same root cause gets one notification per SAST day, not one for each
    # downstream missed slot. New diagnoses still produce a fresh alert.
    day = report.get('checked_at', datetime.now(content.SAST).isoformat())[:10]
    digest = hashlib.sha256(json.dumps({'day': day, 'diagnoses': sorted({i['diagnosis'] for i in report['incidents']})}, sort_keys=True).encode()).hexdigest()
    alerts = (state or {}).get('editorial_delivery', {}).setdefault('alerts', {})
    if digest in alerts:
        return 'already_alerted'
    repo = os.getenv('GITHUB_REPOSITORY', '')
    run = os.getenv('GITHUB_RUN_ID', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or not run.isdigit():
        return 'unavailable'
    text = 'Facebook posting needs attention.\n' + '\n'.join(
        f"{i['slot']}: {i['diagnosis']} (attempts {i['attempts']})" for i in report['incidents'])
    text += f'\nNo blind resend was performed.\nhttps://github.com/{repo}/actions/runs/{run}'
    opener = opener or build_opener(_NoRedirect())
    bot, chat = os.getenv('TELEGRAM_BOT_TOKEN', ''), os.getenv('TELEGRAM_CHAT_ID', '')
    delivered = None
    if re.fullmatch(r'\d+:[A-Za-z0-9_-]+', bot) and chat:
        try:
            result = json_request(opener, f'https://api.telegram.org/bot{bot}/sendMessage',
                                  {'chat_id': chat, 'text': text[:3900], 'disable_web_page_preview': True})
            if result.get('ok') is True:
                delivered = 'telegram'
        except Exception:
            pass  # Never log the request URL (contains a credential).
    if delivered is None and allow_github and os.getenv('GH_READ_TOKEN'):
        try:
            base = f'https://api.github.com/repos/{repo}/issues'
            token = os.environ['GH_READ_TOKEN']
            marker = '<!-- facebook-delivery-watchdog -->'
            issues = json_request(opener, base + '?state=open&per_page=100', token=token)
            if not isinstance(issues, list):
                return 'failed'
            existing = next((i for i in issues if not i.get('pull_request') and marker in (i.get('body') or '')), None)
            if existing is None and len(issues) >= 100:
                return 'failed'  # Partial index cannot prove there is no existing alert issue.
            report_marker = '<!-- facebook-watchdog-report:' + digest + ' -->'
            body = marker + '\n' + report_marker + '\n' + text + '\n\n@' + repo.split('/')[0]
            if existing and report_marker in (existing.get('body') or ''):
                return 'github_issue'
            if existing:
                # Only update the exact issue returned by GitHub, never invent an ID.
                number = existing['number']
                if type(number) is not int or number <= 0:
                    return 'failed'
                request = Request(base + f'/{number}', data=json.dumps({'body': body}).encode(), method='PATCH',
                                  headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
                with opener.open(request, timeout=25) as response:
                    result = json.loads(response.read(1024 * 1024))
            else:
                result = json_request(opener, base, {'title': '[Posting watchdog] Facebook delivery needs attention', 'body': body}, token)
            if type(result.get('number')) is int:
                delivered = 'github_issue'
        except Exception:
            pass
    if delivered:
        alerts[digest] = delivered
        # Bound notification metadata only, never publication/unknown evidence.
        while len(alerts) > 64:
            del alerts[next(iter(alerts))]
        return delivered
    return 'failed'


def main(argv=None):
    from .cli import config, output, scores_approved, editorial_source_approved
    from .editorial import schedule
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('assess', 'audit', 'alert'))
    parser.add_argument('--work', default='tmp/facebook-feed')
    args = parser.parse_args(argv)
    work = Path(args.work); path = work / 'checkpoint/state.json'
    now = datetime.now(content.SAST)
    cfg = config('config/facebook-feed.json')
    repo, branch = os.getenv('GITHUB_REPOSITORY', ''), os.getenv('GITHUB_REF_NAME', '')
    run_key = os.getenv('GITHUB_RUN_ID', '') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    if branch != 'main' or os.getenv('WATCHDOG_REQUEST_PUBLISH') != 'true':
        output('allow_prepare', 'false')
        return 0
    state = None
    try:
        if args.phase == 'alert':
            # Runs in a separate least-privilege issue-notification job. No Page
            # or provider secrets, no publication state writes or mutation.
            report = {'checked_at': now.isoformat(), 'incidents': [{'slot': f'pipeline:{now.date()}', 'diagnosis': 'watchdog_pipeline_requires_attention', 'attempts': 0}]}
            supplied = os.getenv('WATCHDOG_HEALTH', '')
            try:
                health = json.loads(supplied)
                safe = []
                for item in health['incidents'][:100]:
                    if (re.fullmatch(r'(?:editorial:\d{4}-\d{2}-\d{2}:[a-z]+|pipeline(?::\d{4}-\d{2}-\d{2})?|configuration)', item['slot']) and
                        re.fullmatch(r'[a-z_]{1,70}', item['diagnosis']) and type(item['attempts']) is int and 0 <= item['attempts'] <= MAX_ATTEMPTS):
                        safe.append({k: item[k] for k in ('slot', 'diagnosis', 'attempts')})
                if safe:
                    report['incidents'] = safe
            except (ValueError, KeyError, TypeError):
                pass
            result = notify(report)
            print('::notice::Watchdog fallback notification: ' + result)
            return 0 if result in ('github_issue', 'telegram', 'already_alerted') else 1
        if args.phase == 'assess':
            prefix = storage.namespace(repo, branch, True); output('prefix', prefix)
            state = storage.restore(repo, branch, os.getenv('GITHUB_REPOSITORY_ID', ''), prefix, os.environ['GH_READ_TOKEN'], work)
            if state is None:
                raise storage.StateError('No durable ledger; watchdog never bootstraps')
            output('restored', 'true')
            book(state,now,schedule(cfg))
            enabled = cfg['enabled'] and not cfg['dry_run'] and cfg.get('editorial', {}).get('enabled') and 'editorial' in cfg.get('authorized_kinds', []) and editorial_source_approved(cfg,now) and os.getenv('FACEBOOK_FEED_PUBLISH', '').lower() == 'true'
            if enabled:
                reconcile_known(state, now)
                allowed, reason = assess(state, now, run_key, max_pages=cfg['highlightly']['max_pages_per_poll'], daily_budget=cfg['highlightly']['daily_request_budget'])
                if allowed:
                    try:
                        PageFeed()  # Credential identity GET only, never creation.
                    except PublishError as error:
                        current = current_slot(state,now)
                        row = book(state, now)['slots'][current[0]]
                        release_quota_hold(state, row)  # Positive proof: no provider request made.
                        row.update(status='waiting' if error.retryable else 'needs_attention',
                                   diagnosis='facebook_preflight_temporary' if error.retryable else 'facebook_access_blocked')
                        allowed, reason = False, row['diagnosis']
            else:
                allowed, reason = False, 'publication_gates_disabled'
            storage.write(path, state)
            storage.write(work / 'watchdog-admission.json', {'run_key': run_key, 'allowed': allowed})
            output('allow_prepare', str(allowed).lower())
            print('::notice::Editorial watchdog admission: ' + reason)
            return 0
        state = content.load(path) if path.exists() else None
        if state is None:
            report = {'checked_at': now.isoformat(), 'incidents': [{'slot': 'pipeline', 'diagnosis': 'durable_state_or_admission_unavailable', 'attempts': 0}], 'counts': {}}
        else:
            report = audit(state, now, os.getenv('WATCHDOG_PIPELINE_OK') == 'true')
            if os.getenv('FACEBOOK_FEED_PUBLISH', '').lower() != 'true' or not cfg['enabled'] or cfg['dry_run'] or not editorial_source_approved(cfg,now) or not cfg.get('editorial', {}).get('enabled') or 'editorial' not in cfg.get('authorized_kinds', []):
                report['incidents'].append({'slot': 'configuration', 'diagnosis': 'publication_gates_disabled', 'attempts': 0})
        result = notify(report, state, allow_github=False)
        report['notification'] = result
        output('health_report', json.dumps(report, separators=(',', ':')))
        output('alert_fallback', 'true' if report['incidents'] and result not in ('telegram', 'already_alerted') else 'false')
        storage.write(work / 'watchdog-report.json', report)
        if state is not None:
            storage.write(path, state)
        print('::notice::Editorial delivery health: ' + json.dumps(report, separators=(',', ':')))
        if os.getenv('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as target:
                target.write('## Facebook delivery watchdog\n```json\n' + json.dumps(report, indent=2) + '\n```\n')
        return 1 if report['incidents'] else 0
    except Exception:
        # No raw network/config exception, credential, Graph message or signed URL.
        print('::error::Watchdog could not establish safe delivery state; no publishing or reset allowed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
