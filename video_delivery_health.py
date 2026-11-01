"""Per-channel evidence and durable, deduplicated video failure alerts.

Observer only: never renders, uploads, retries media, clears slots or infers a
Facebook acknowledgement from Telegram, a workflow result or legacy history.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo

from video_schedule import WINDOWS

SAST = ZoneInfo('Africa/Johannesburg')
EDITIONS = {name for name, _, _ in WINDOWS}
LANES = {'telegram', 'facebook'}
STATUSES = {'pending', 'attempting', 'unconfirmed', 'not_configured', 'confirmed'}
RESULTS = {'blocked', 'not_delivered', 'partially_delivered', 'delivered', 'already_delivered',
           'window_expired', 'outside_window'}
_CONTEXT = ContextVar('video_health_context', default=None)


def local(now=None):
    now = now or datetime.now(SAST)
    return now.replace(tzinfo=SAST) if now.tzinfo is None else now.astimezone(SAST)


def load(path, now=None):
    path = Path(path)
    if not path.exists():
        return {'version': 1, 'since': local(now).isoformat(), 'days': {}}
    data = json.loads(path.read_text())
    if data.get('version') != 1 or not isinstance(data.get('days'), dict):
        raise ValueError('Invalid video health ledger; refusing reset')
    local(datetime.fromisoformat(data['since']))
    for day, editions in data['days'].items():
        if datetime.fromisoformat(day).date().isoformat() != day or not isinstance(editions, dict):
            raise ValueError('Invalid video health date')
        for edition, row in editions.items():
            if edition not in EDITIONS or not isinstance(row, dict):
                raise ValueError('Invalid video health edition')
            if set(row.get('lanes', {})) != LANES or any(
                    item.get('status') not in STATUSES for item in row['lanes'].values()):
                raise ValueError('Invalid video health lanes')
            if 'alert' in row:
                alert = row['alert']
                if (not isinstance(alert, dict) or alert.get('status') not in
                        {'reserved', 'unknown', 'confirmed', 'resolved_before_send'} or
                        not isinstance(alert.get('run_key'), str) or not alert['run_key']):
                    raise ValueError('Invalid video alert reservation')
                local(datetime.fromisoformat(alert['reserved_at']))
            for lane, item in row['lanes'].items():
                expected = 'publishing_complete' if lane == 'facebook' else 'sendVideo_acknowledged'
                if item['status'] == 'confirmed' and (not re.fullmatch(r'[1-9]\d*', str(item.get('receipt_id', ''))) or item.get('evidence') != expected):
                    raise ValueError('Invalid channel confirmation evidence')
    return data


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def entry(data, day, edition):
    if edition not in EDITIONS or datetime.fromisoformat(day).date().isoformat() != day:
        raise ValueError('Invalid edition identity')
    return data['days'].setdefault(day, {}).setdefault(edition, {
        'lanes': {lane: {'status': 'pending'} for lane in sorted(LANES)}})


def record_lane(path, day, edition, lane, status, receipt_id=None, now=None):
    if lane not in LANES or status not in STATUSES:
        raise ValueError('Invalid channel evidence')
    if receipt_id is not None and not re.fullmatch(r'[1-9]\d*', str(receipt_id)):
        raise ValueError('Invalid public receipt ID')
    if status == 'confirmed' and receipt_id is None:
        raise ValueError('Channel confirmation requires an acknowledgement ID')
    data = load(path, now)
    item = entry(data, day, edition)['lanes'][lane]
    if item['status'] == 'confirmed':
        if receipt_id and item.get('receipt_id') and str(receipt_id) != item['receipt_id']:
            raise ValueError('Confirmed delivery identity cannot be overwritten')
        return
    item.update(status=status, checked_at=local(now).isoformat())
    if receipt_id is not None:
        item['receipt_id'] = str(receipt_id)
    if status == 'confirmed':
        item['evidence'] = 'publishing_complete' if lane == 'facebook' else 'sendVideo_acknowledged'
    save(path, data)


def record_outcome(path, day, edition, result, now=None):
    if edition not in EDITIONS or result not in RESULTS:
        return
    data = load(path, now)
    row = entry(data, day, edition)
    row.update(last_result=result, checked_at=local(now).isoformat())
    save(path, data)


@contextmanager
def edition_context(path, day, edition):
    token = _CONTEXT.set((Path(path), day, edition))
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def identity():
    value = _CONTEXT.get()
    return {'edition': value[2], 'edition_date': value[1]} if value else {}


def observe(lane, status, receipt_id=None):
    value = _CONTEXT.get()
    if value:
        try:
            record_lane(*value, lane, status, receipt_id)
        except Exception:
            # Never expose raw exceptions/paths/credentials or reset corrupted state.
            print('::error::Video channel evidence could not be saved; no delivery confirmation inferred.')


def plan(path, run_key, now=None):
    """Reserve at most one incident per edition BEFORE the workflow pushes state.

    Begin monitoring at activation (including a window already in progress), not
    historical missed editions. A later tick covers a wholly missed window even
    if no renderer ran. Legacy briefing_slots are deliberately not imported.
    """
    now = local(now)
    data = load(path, now)
    since = local(datetime.fromisoformat(data['since']))
    planned = []
    for day in (now.date() - timedelta(days=1), now.date()):
        for edition, start, end in WINDOWS:
            beginning = datetime.combine(day, datetime.min.time(), SAST) + timedelta(minutes=start)
            deadline = beginning.replace(hour=0, minute=0) + timedelta(minutes=end)
            if now < beginning or deadline < since:
                continue
            row = entry(data, day.isoformat(), edition)
            confirmed = all(v['status'] == 'confirmed' for v in row['lanes'].values())
            if confirmed:
                row['health'] = 'confirmed_both_channels'
                continue
            bad_result = row.get('last_result') in {'blocked', 'not_delivered', 'partially_delivered'}
            old_attempt = any(v['status'] in {'unconfirmed', 'not_configured'} or
                (v['status'] == 'attempting' and now - local(datetime.fromisoformat(v['checked_at'])) >= timedelta(minutes=10))
                for v in row['lanes'].values())
            if not (now >= deadline or bad_result or old_attempt):
                row['health'] = 'waiting'
                continue
            row['health'] = 'needs_attention'
            # A reserved/unknown alert from another run is NEVER blindly resent.
            if 'alert' not in row:
                row['alert'] = {'status': 'reserved', 'run_key': run_key, 'reserved_at': now.isoformat()}
                planned.append(f'{day}:{edition}')
    cutoff = (now.date() - timedelta(days=7)).isoformat()
    data['days'] = {day: value for day, value in data['days'].items() if day >= cutoff}
    save(path, data)
    return planned


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send_alert(text):
    """No retries after an ambiguous send, no credential-bearing exception output."""
    token, chat = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return False
    request = Request(f'https://api.telegram.org/bot{token}/sendMessage',
        data=json.dumps({'chat_id': chat, 'text': text}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        payload = json.loads(response.read(65536))
    return payload.get('ok') is True


def notify(path, run_key, now=None, sender=send_alert):
    """Workflow MUST checkpoint plan() to data branch before invoking this."""
    data = load(path, now)
    sent = 0
    for day, editions in sorted(data['days'].items()):
        for edition, row in editions.items():
            alert = row.get('alert', {})
            if alert.get('status') != 'reserved' or alert.get('run_key') != run_key:
                continue
            if all(item['status'] == 'confirmed' for item in row['lanes'].values()):
                alert['status'] = 'resolved_before_send'
                save(path, data)
                continue
            # Persist before network. A timeout may have delivered the message.
            alert['status'] = 'unknown'
            save(path, data)
            labels = ', '.join(f'{lane}: {item["status"]}' for lane, item in sorted(row['lanes'].items()))
            reason = {'blocked': 'Source/selection checks blocked this edition.',
                      'not_delivered': 'No successful edition delivery was recorded.',
                      'partially_delivered': 'A requested channel is still unconfirmed.'}.get(
                          row.get('last_result'), 'The deadline passed or a delivery attempt remained unconfirmed.')
            message = (f'⚠️ Video delivery needs attention — {day} {edition} (SAST).\n'
                       f'{labels}.\n'
                       f'{reason} '
                       'Confirmed channels will not be resent. Facebook recovery uses saved sessions only.')
            try:
                acknowledged = sender(message)
            except Exception:
                acknowledged = False  # Never serialize an exception or credential URL.
            if acknowledged:
                alert.update(status='confirmed', confirmed_at=local(now).isoformat())
                sent += 1
            save(path, data)
    # Keep a transport failure visible on later audits, not just the sending run.
    uncertain = sum(1 for editions in data['days'].values() for row in editions.values()
                    if row.get('health') == 'needs_attention' and
                    row.get('alert', {}).get('status') in {'reserved', 'unknown'})
    return {'alerts_confirmed': sent, 'alerts_unconfirmed': uncertain}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'notify'])
    parser.add_argument('--directory', default='state/data/app')
    args = parser.parse_args()
    path = Path(args.directory) / 'video_delivery.json'
    run_key = os.environ['GITHUB_RUN_ID'] + ':' + os.getenv('GITHUB_RUN_ATTEMPT', '1')
    try:
        result = plan(path, run_key) if args.action == 'plan' else notify(path, run_key)
        print('::notice::Video delivery health: ' + json.dumps(result))
        if os.getenv('GITHUB_STEP_SUMMARY'):
            data = load(path)
            lines = ['## Video delivery tracker', '| Date / edition | Telegram | Facebook |', '|---|---|---|']
            for day, editions in sorted(data['days'].items()):
                for edition, row in editions.items():
                    labels = []
                    for lane in ('telegram', 'facebook'):
                        item = row['lanes'][lane]
                        receipt = item.get('receipt_id', '')
                        # Never render unvalidated arbitrary data in a summary.
                        receipt = receipt if re.fullmatch(r'[1-9]\d*', str(receipt)) else ''
                        labels.append(item['status'] + (' (ID ' + receipt + ')' if receipt else ''))
                    lines.append(f'| {day} / {edition} | {labels[0]} | {labels[1]} |')
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
                summary.write('\n'.join(lines) + '\n')
        if isinstance(result, dict) and result['alerts_unconfirmed']:
            return 1
        return 0
    except Exception:
        print('::error::Video delivery health unavailable; state preserved, no reset or blind resend.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
