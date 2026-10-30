"""Read-only live API diagnostics using the production quota ledger, never Facebook.

Run only in the existing isolated main-branch Actions engine. Report closed safe
categories and configured slot names, never responses, credentials or account PII.
"""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path

from . import content,storage
from .cli import config,output
from .event_provider import EventAPI,SLOTS,AuthenticationRejected,QuotaExceeded
from .provider import ProviderError


def diagnose(cfg,state,now,api=None,endpoint='fixtures'):
    api=api or EventAPI(cfg,state,now)
    outcome='blocked';count=None;reason='provider_policy_or_validation'
    try:
        # Exercise the SAME plan checks, failover order, quota/cooldown policy and
        # global read endpoint as production. No override of access restrictions.
        rows=api.get(endpoint,{'live':'all','timezone':'Africa/Johannesburg'} if endpoint=='fixtures' else None)
        if endpoint=='status' and isinstance(rows,dict):outcome='verified_read_only';reason='verified_account_status'
        elif endpoint=='fixtures' and isinstance(rows,list):outcome='verified_read_only';count=len(rows);reason='verified_response'
        else:reason='invalid_provider_response'
    except AuthenticationRejected:reason='authentication_unavailable'
    except QuotaExceeded:reason='quota_unavailable'
    except ProviderError:
        if api.diagnostics:reason=api.diagnostics[-1]['category']
    except Exception:
        # Unexpected provider schema must not dump response/account details or lose
        # already-counted attempts; this is a diagnostic failure, not permission to post.
        reason='unexpected_provider_response_shape'
    return {'mode':'read_only_api_diagnostic','outcome':outcome,'reason':reason,
            'facebook_requests':0,'checked_at':now.isoformat(),'verified_fixture_count':count,
            'successful_slot':api.active,
            'slots':[{'slot':slot,'configured':bool(api.keys[slot]),
                      'authorised':cfg['event_monitor']['key_slots'][slot]['authorised'],
                      'http_attempted':any(e['slot']==slot and e['category']=='request_started' for e in api.diagnostics)} for slot in SLOTS],
            'events':list(api.diagnostics)}


def diagnose_accounts(cfg,state,now):
    """One status request per configured approved account, no match or Page calls.

    A new access restriction still stops the audit; it is not a licence to bypass
    suspensions. Existing permitted authentication/quota fallback remains honoured.
    """
    slots=[];events=[];successful=[];stop=None
    for slot in SLOTS:
        authorised=cfg['event_monitor']['key_slots'][slot]['authorised']
        row={'slot':slot,'configured':bool(os.getenv(slot,'').strip()),'authorised':authorised,'http_attempted':False}
        if not authorised:row.update(outcome='disabled',reason='not_authorised_for_selection')
        elif stop:row.update(outcome='not_attempted',reason='previous_policy_stop')
        elif not row['configured']:row.update(outcome='not_attempted',reason='not_configured')
        else:
            probe=deepcopy(cfg)
            for name,settings in probe['event_monitor']['key_slots'].items():settings['authorised']=name==slot
            api=EventAPI(probe,state,now)
            report=diagnose(probe,state,now,api,endpoint='status')
            events.extend(report['events'])
            row.update(outcome=report['outcome'],reason=report['reason'],
                       http_attempted=any(e['category']=='request_started' for e in report['events']))
            if report['outcome']=='verified_read_only':
                successful.append(slot)
                budget=state['event_api']['groups'][cfg['event_monitor']['key_slots'][slot]['quota_group']]
                row.update(daily_limit=budget['allocation'],provider_used=budget.get('provider_used'),remaining=budget.get('remaining'))
            else:
                permitted=cfg['event_monitor']['failover_permitted'] and bool(cfg['event_monitor']['permission_reference'])
                allowed=report['reason']=='quota_unavailable' or (report['reason']=='authentication_unavailable' and cfg['event_monitor'].get('authentication_failover_permitted',False))
                if not permitted or not allowed:stop=report['reason']
        slots.append(row)
    approved=[row for row in slots if row['authorised']]
    outcome='verified_read_only' if approved and all(row['outcome']=='verified_read_only' for row in approved) else 'partially_verified' if successful else 'blocked'
    return {'mode':'read_only_approved_accounts_diagnostic','outcome':outcome,
            'reason':stop or ('verified_account_status' if outcome=='verified_read_only' else 'some_accounts_unavailable'),
            'facebook_requests':0,'checked_at':now.isoformat(),'successful_slots':successful,
            'slots':slots,'events':events}


def main():
    if os.getenv('GITHUB_REF_NAME')!='main':raise storage.StateError('API diagnostic must run on main; no alternate production ledger')
    token=os.getenv('GH_READ_TOKEN')
    if not token:raise storage.StateError('Authenticated production quota restoration is required')
    cfg=config('config/facebook-feed.json');now=datetime.now(content.SAST)
    work=Path('tmp/facebook-feed');work.mkdir(parents=True,exist_ok=True)
    repo=os.environ['GITHUB_REPOSITORY'];prefix=storage.namespace(repo,'main',True)
    state=storage.restore(repo,'main',os.getenv('GITHUB_REPOSITORY_ID',''),prefix,token,work)
    if state is None:raise storage.StateError('No existing production quota ledger; refusing diagnostic bootstrap/reset')
    output('prefix',prefix)
    report=diagnose_accounts(cfg,state,now)
    # Keep usage/cooldowns durable without changing matches, posts or pending events.
    storage.write(work/'checkpoint/state.json',state)
    storage.write(work/'api-diagnostic.json',report)
    print('::notice::API DIAGNOSTIC — NO FACEBOOK REQUESTS: '+json.dumps(report,separators=(',',':')))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as target:
            target.write('## Read-only live API diagnostic\n\nNo Facebook requests. No credential values or raw provider responses.\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,storage.StateError):
        print('::error::Cannot safely restore/run API diagnostic; no ledger reset or Facebook request')
        raise SystemExit(1)
