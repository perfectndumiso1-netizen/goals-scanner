"""Prepare/checkpoint/send CLI. Publishing requires three explicit gates and a saved reservation."""
import argparse
from datetime import datetime,timedelta
import hashlib
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from . import content,policy,storage,match_events,event_monitor
from .graphics import render
from .provider import APIFootball,ProviderError
from .app_scores import AppScores
from .live_window import in_window, eligible_kickoff, app_candidates, match_app_coverage, outstanding_candidates
from .publisher import PageFeed,PublishError

KINDS=('community','card','weekly','live','roundup','results','preflight')


def uses_events(cfg):
    return 'event_monitor' in cfg and cfg['event_monitor'].get('mode','events')=='events'


def config(path):
    data=content.load(path)
    if data.get('version')!=1 or data.get('timezone')!='Africa/Johannesburg':
        raise ValueError('Unsupported feed configuration')
    if any(type(value) is not bool for value in (data['enabled'],data['dry_run'],data['live']['enabled'],data['live']['edit_existing'],data['provider']['rights_confirmed'],data['provider']['account_coverage_verified'])):
        raise ValueError('Safety switches must be JSON booleans, not strings')
    if data['provider']['name']!='api-football' or not 8<=data['topic_history_days']<=90:
        raise ValueError('Unsupported provider/history window')
    for key in ('min_feed_interval_minutes','live_post_cooldown_minutes','edit_cooldown_minutes'):
        if not isinstance(data.get(key),int) or data[key]<1:
            raise ValueError('Posting intervals must be positive')
    if not 0<=data['live']['max_posts_per_day']<=(90 if data['live'].get('publish_every_poll') is True else 3) or not 1<=data['live']['max_matches']<=30:
        raise ValueError('Live posting cap exceeds approved maximum')
    for flag in ('publish_every_poll','image_required'):
        if flag in data['live'] and type(data['live'][flag]) is not bool:raise ValueError('Live switches must be booleans')
    if data['live'].get('graphic_style','classic') not in ('classic','stadium'):raise ValueError('Unsupported live picture style')
    if type(data['live'].get('crests_enabled',False)) is not bool:raise ValueError('Crest switch must be a boolean')
    if data['live'].get('publish_every_poll') and data['live'].get('image_required') is not True:raise ValueError('Periodic live updates require a score picture')
    if data['live'].get('publish_every_poll') and data['live_post_cooldown_minutes']<10:raise ValueError('Live publication interval cannot be below ten minutes')
    if data['provider']['poll_interval_minutes']<10 or not 1<=data['provider']['daily_request_budget']<=90:
        raise ValueError('Free-plan polling/request budget is unsafe')
    settings=data['provider']
    if type(settings.get('statistics_enabled',False)) is not bool or any(type(settings.get(k,0)) is not int or not 0<=settings.get(k,0)<=limit for k,limit in (('statistics_daily_request_budget',6),('statistics_max_matches_per_update',2))):
        raise ValueError('Unsafe optional statistics budget')
    if 'app_coverage_only' in data['live'] and type(data['live']['app_coverage_only']) is not bool:
        raise ValueError('App coverage restriction must be a boolean')
    window=data['live'].get('coverage_window')
    if 'coverage_window' in data['live']:
        if window!={'start':'08:00','end':'24:00'}:raise ValueError('Live coverage must remain 08:00 to midnight SAST')
    if data.get('score_source', 'api-football') not in ('api-football', 'app', 'highlightly'):raise ValueError('Unsupported score source')
    if 'authorized_kinds' in data and (not isinstance(data['authorized_kinds'],list) or any(k not in KINDS for k in data['authorized_kinds'])):raise ValueError('Invalid authorized kinds')
    if data.get('score_source')=='app':
        app=data.get('app_scores',{})
        if any(type(app.get(k)) is not bool for k in ('rights_confirmed','coverage_verified')):raise ValueError('App source approvals must be booleans')
        if not 30<=app.get('max_source_age_seconds',0)<=300 or app.get('poll_interval_minutes',0)<5:raise ValueError('Unsafe app score freshness/poll interval')
    for key in ('community_time','weekly_time','card_time','roundup_time'):
        datetime.strptime(data[key],'%H:%M')
    datetime.strptime(data.get('results_time','08:00'),'%H:%M')
    event=data.get('event_monitor')
    if event is not None:
        from .event_provider import SLOTS
        if event.get('mode','events') not in ('events','legacy'):raise ValueError('Unsupported live monitoring mode')
        if any(type(event.get(k)) is not bool for k in ('enabled','publish_enabled','failover_permitted')):raise ValueError('Event safety switches must be booleans')
        if type(event.get('authentication_failover_permitted',False)) is not bool:raise ValueError('Authentication failover switch must be a boolean')
        if type(event.get('daily_request_budget')) is not int or not 1<=event['daily_request_budget']<=100:raise ValueError('Unsafe event account budget')
        reserve=event.get('daily_request_reserve',10)
        if type(reserve) is not int or not 0<=reserve<event['daily_request_budget']:raise ValueError('Unsafe event account reserve')
        if type(event.get('max_source_age_seconds')) is not int or not 30<=event['max_source_age_seconds']<=180:raise ValueError('Unsafe event freshness')
        if not isinstance(event.get('credential_revision'),str) or not event['credential_revision']:raise ValueError('Credential revision required')
        if not isinstance(event.get('permission_reference'),str):raise ValueError('Failover permission reference must be text')
        if set(event.get('key_slots',{}))!=set(SLOTS):raise ValueError('Invalid API key slots')
        for slot in event['key_slots'].values():
            if type(slot.get('authorised')) is not bool or not isinstance(slot.get('quota_group'),str) or not slot['quota_group']:raise ValueError('Invalid authorised account allocation')
        if uses_events(data) and event['enabled'] and (not data['live'].get('image_required') or data.get('score_source','api-football') not in ('api-football','highlightly')):raise ValueError('Event monitoring requires the authorised API source and match picture')
        if event['failover_permitted'] and not event['permission_reference'].strip():raise ValueError('Documented provider failover permission required')
    if data.get('score_source')=='highlightly':
        h=data.get('highlightly',{})
        if not uses_events(data):raise ValueError('Highlightly is for factual live events only')
        if any(type(h.get(k)) is not bool for k in ('verification_only','rights_confirmed','account_coverage_verified')):raise ValueError('Highlightly approval switches must be booleans')
        if type(h.get('daily_request_budget')) is not int or not 1<=h['daily_request_budget']<=100:raise ValueError('Unsafe Highlightly budget')
        for k,lo,hi in (('poll_interval_minutes',20,60),('max_pages_per_poll',1,10),('max_details_per_poll',0,5)):
            if type(h.get(k)) is not int or not lo<=h[k]<=hi:raise ValueError('Unsafe Highlightly polling bounds')
    return data


def source_freshness(cfg):
    if cfg.get('score_source')=='highlightly':return cfg['event_monitor']['max_source_age_seconds']
    return cfg['app_scores']['max_source_age_seconds'] if cfg.get('score_source')=='app' else cfg['provider']['max_fetch_age_seconds']


def scores_approved(cfg):
    if cfg.get('score_source')=='highlightly':
        h=cfg['highlightly']
        return h['rights_confirmed'] and h['account_coverage_verified'] and not h['verification_only']
    if cfg.get('score_source')=='app':
        return cfg['app_scores']['rights_confirmed'] and cfg['app_scores']['coverage_verified']
    return cfg['provider']['rights_confirmed'] and cfg['provider']['account_coverage_verified']


def is_due(kind,now,cfg):
    if kind=='preflight':return False
    if kind not in cfg.get('authorized_kinds',KINDS):return False
    if kind=='live':return cfg['live']['enabled'] and (cfg['event_monitor']['enabled'] if uses_events(cfg) else in_window(now,cfg))
    if kind=='card' and now.weekday() not in cfg['card_days']:return False
    if kind=='weekly' and now.weekday()!=cfg['weekly_day']:return False
    key={'community':'community_time','weekly':'weekly_time','card':'card_time','roundup':'roundup_time','results':'results_time'}[kind]
    when=cfg.get(key,'08:00')
    target=now.replace(hour=int(when[:2]),minute=int(when[3:]),second=0,microsecond=0)
    return timedelta(0)<=now-target<timedelta(hours=2)


def build(kind,root,now,cfg,state,preview=False):
    if not preview and not is_due(kind,now,cfg):return None,'not due'
    if kind=='live' and uses_events(cfg):
        if not cfg['event_monitor']['enabled'] or not cfg['live']['enabled']:return None,'event monitoring disabled'
        try:return event_monitor.build(cfg,state,now)
        except ProviderError as error:return None,str(error)
    if kind=='results':return content.morning_results(root,now,cfg),'exact filmed history + verified app ledger'
    items=[] if kind in ('live','roundup','preflight') else content.verified_fixtures(root,now,cfg)
    if kind in ('community','card'):
        covered={key for p in policy.history(state,now,cfg['topic_history_days']) if p.get('kind') in ('community','card') and p.get('status') not in ('cancelled','rejected') for key in p.get('fixture_ids',[])}
        items=[item for item in items if item['fixture']['id'] not in covered]
    if kind=='community':
        return content.community(items,content.load(Path(root).parents[0]/'advisor_ledger.json',[]),now,policy.history(state,now)),'editorial evidence'
    if kind=='card':return content.match_card(items,now),'card evidence'
    if kind=='weekly':return content.weekly(items,root,now),'weekly evidence'
    if kind in ('live','roundup','preflight'):
        if not preview and not cfg['live']['enabled']:return None,'live scores disabled pending verification'
        try:
            # Preview may bypass calendar timing for editorial content, never overnight score safety.
            if kind!='preflight' and not in_window(now,cfg):return None,'outside 08:00–24:00 SAST score coverage'
            if not preview and not cfg['live']['edit_existing']:
                sent=[p for p in state.get('posts',[]) if p.get('kind') in ('live','roundup') and
                      p.get('status') not in ('cancelled','rejected') and p.get('operation')!='edit' and content.local(p['at']).date()==now.date()]
                if len(sent)>=cfg['live']['max_posts_per_day']:return None,'daily score post cap reached; conserving API allowance'
            coverage=None
            if kind!='preflight' and cfg['live'].get('app_coverage_only'):
                coverage=outstanding_candidates(app_candidates(root,now,cfg),state,cfg.get('score_source','api-football'))
                if not coverage:return None,'no eligible app-covered match in progress window; no API request'
            provider=AppScores(Path(root),cfg,state,now) if cfg.get('score_source')=='app' else APIFootball(cfg,state,now)
            if kind=='preflight':return None,json.dumps(provider.coverage(),sort_keys=True)
            matches,fetched=provider.fixtures(coverage=coverage) if coverage is not None and cfg.get('score_source')!='app' else provider.fixtures()
            if now-content.local(fetched)>timedelta(seconds=source_freshness(cfg)):
                return None,'cached scores are too old to publish'
            if coverage is not None:matches=match_app_coverage(matches,coverage)
            if cfg['live'].get('coverage_window'):matches=[m for m in matches if eligible_kickoff(m['kickoff'],now,cfg)]
            # Prevent a frozen in-play minute/status from being treated as a fresh observation forever.
            seen=state.setdefault('score_observations',{})
            valid=[]
            for match in matches:
                fingerprint=json.dumps([match['status'],match.get('elapsed'),match['home_goals'],match['away_goals']],sort_keys=True)
                observation_key=cfg.get('score_source','api-football')+':'+str(match['id'])
                match['source']=cfg.get('score_source','api-football')
                prior=seen.get(observation_key)
                if prior and prior['fingerprint']==fingerprint:
                    if match['status'] in ('1H','2H','HT','ET','BT','P') and now-content.local(prior['since'])>timedelta(minutes=35):
                        continue
                else:seen[observation_key]={'fingerprint':fingerprint,'since':now.isoformat()}
                valid.append(match)
            selected=policy.selected_matches(valid,cfg,[item['fixture'] for item in items])
            post=policy.score_post(selected,state,now,cfg,roundup=kind=='roundup')
            if post and cfg.get('score_source')!='app' and policy.allowed(post,state,now,cfg)[0]:
                enriched=provider.enrich_statistics(selected)
                post=policy.score_post(enriched,state,now,cfg,roundup=kind=='roundup')
            if post:
                timestamps=[content.local(fetched)]+[content.local(m['statistics_at']) for m in post['snapshot'] if m.get('statistics_at')]
                if post.get('graphic',{}).get('kind')=='live-score':post['graphic']['checked_at']=content.local(fetched).isoformat()
                post['expires_at']=(min(timestamps)+timedelta(seconds=source_freshness(cfg))).isoformat()
                post['caption']=post['caption'].replace(f'checked {now:%d %b %H:%M}',f'checked {content.local(fetched):%d %b %H:%M}')
                if cfg.get('score_source')=='app' or cfg['live'].get('app_coverage_only'):
                    post['fixture_ids']=[m['fixture_id'] for m in selected if m.get('fixture_id')]
                if cfg.get('score_source')=='app':
                    post['caption']=post['caption'].replace('Source: API-FOOTBALL / API-SPORTS.', 'Source: the same Livescore feed used by the Mr 2 Odds app; app-covered fixture IDs only.')
                post['caption_hash']=hashlib.sha256(post['caption'].encode()).hexdigest()
            return post,('selected verified provider snapshots' if post else 'no new final or verified in-play score observation')
        except ProviderError as error:return None,str(error)
    return None,'no useful verified candidate'


def output(name,value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as target:target.write(f'{name}={value}\n')


def reconcile(args,cfg,now,work):
    """Operator recovery only: verify an existing post, or explicitly acknowledge inspected absence."""
    if not args.reservation_key or bool(args.post_id)==bool(args.cancel_reservation):
        raise ValueError('Choose one existing post ID or cancellation for an exact reservation key')
    if args.cancel_reservation and not args.confirm_page_inspection:
        raise ValueError('Cancellation requires confirmed manual Page inspection; never guess absence')
    repo=os.environ.get('GITHUB_REPOSITORY','local/repo');branch=os.environ.get('GITHUB_REF_NAME','local')
    token=os.environ.get('GH_READ_TOKEN')
    if not token:raise storage.StateError('Recovery requires authenticated durable-state restoration')
    prefix=storage.namespace(repo,branch,True);output('prefix',prefix)
    state=storage.restore(repo,branch,os.environ.get('GITHUB_REPOSITORY_ID',''),prefix,token,work)
    if state is None:raise storage.StateError('No live ledger to reconcile; refusing bootstrap/reset')
    entries=[entry for entry in state['posts'] if entry['key']==args.reservation_key and entry.get('status') in ('reserved','unknown')]
    if len(entries)!=1:raise ValueError('Expected exactly one unresolved reservation')
    entry=entries[0]
    if args.post_id:
        PageFeed().verify_hash(args.post_id,entry['caption_hash'])
        entry.update(status='published',post_id=args.post_id)
    else:entry.update(status='cancelled',resolution='Operator confirmed Page inspection and absence')
    match_events.publication_state(state,entry,'published' if args.post_id else 'pending',now)
    entry['reconciled_at']=now.isoformat();entry.pop('error',None)
    storage.write(work/'checkpoint/state.json',state)
    print('::notice::Reservation reconciled. No Facebook creation/edit request was made.')
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('prepare','send','preview','reconcile'))
    parser.add_argument('--kind',choices=KINDS+('all',),default='community')
    parser.add_argument('--config',default='config/facebook-feed.json')
    parser.add_argument('--source',default='tmp/feed-source/data/app')
    parser.add_argument('--work',default='tmp/facebook-feed')
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--bootstrap',action='store_true')
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--checkpoint',action='store_true',help='Workflow confirms durable reservation artifact was saved')
    parser.add_argument('--reservation-key')
    parser.add_argument('--post-id')
    parser.add_argument('--cancel-reservation',action='store_true')
    parser.add_argument('--confirm-page-inspection',action='store_true')
    args=parser.parse_args(argv)
    cfg=config(args.config);now=datetime.now(ZoneInfo(cfg['timezone']))
    work=Path(args.work);work.mkdir(parents=True,exist_ok=True)
    statepath=work/'checkpoint'/'state.json';manifest=work/'plans.json'
    if args.phase=='reconcile':return reconcile(args,cfg,now,work)
    requested=args.publish and os.getenv('FACEBOOK_FEED_PUBLISH','').lower()=='true'
    source_blocked=(args.phase=='prepare' and args.kind in ('live','roundup') and not args.preview and not scores_approved(cfg))
    publish=requested and cfg['enabled'] and not cfg['dry_run'] and args.phase!='preview' and not source_blocked
    event_mode=uses_events(cfg) and args.kind in ('live','all')
    if event_mode:
        publish=publish and cfg['event_monitor']['enabled'] and cfg['event_monitor']['publish_enabled'] and os.getenv('GITHUB_REF_NAME','local')=='main'
    if args.phase=='send':
        if not publish or not args.checkpoint:
            raise ValueError('Publish gates/checkpoint confirmation absent; nothing sent')
        state=content.load(statepath);plans=content.load(manifest,[])
        run_key=os.getenv('GITHUB_RUN_ID','local')+'-'+os.getenv('GITHUB_RUN_ATTEMPT','1')
        publisher=None;failed=False
        for post in plans:
            if post.get('event_ids') and (not uses_events(cfg) or not cfg['event_monitor']['enabled'] or not cfg['event_monitor']['publish_enabled'] or os.getenv('GITHUB_REF_NAME','local')!='main'):
                raise ValueError('Live-event publication gate changed; nothing sent')
            entries=[p for p in state['posts'] if p['key']==post['key'] and p.get('run_key')==run_key]
            if len(entries)!=1 or entries[0]['status']!='reserved':
                raise ValueError('Reservation ownership mismatch; no retry')
            entry=entries[0]
            score_content=post['kind'] in ('live','roundup')
            source_changed=score_content and any(m.get('source')!=cfg.get('score_source','api-football') for m in post.get('snapshot',[]))
            if post['kind'] not in cfg.get('authorized_kinds',KINDS) or score_content and (not cfg['live']['enabled'] or not scores_approved(cfg) or source_changed):
                entry['status']='cancelled';entry['error']='Content/source authorisation changed before sending';match_events.publication_state(state,entry,'pending',now);storage.write(statepath,state);continue
            if hashlib.sha256(post['caption'].encode()).hexdigest()!=entry['caption_hash'] or any(entry.get(k)!=post.get(k) for k in ('kind','topic','fixture_ids','operation','target_id','snapshot','image_sha256','event_ids')):
                raise ValueError('Prepared content does not match its durable reservation')
            if datetime.now(content.SAST)>=content.local(post['expires_at']) or post['kind'] in ('live','roundup') and not (post.get('event_ids') or in_window(datetime.now(content.SAST),cfg)):
                entry['status']='cancelled';entry['error']='Prepared content expired before sending';match_events.publication_state(state,entry,'pending',now);storage.write(statepath,state);continue
            if post['kind']=='live' and cfg['live'].get('image_required'):
                image=Path(post.get('image') or '')
                if not image.is_file() or not post.get('image_sha256') or hashlib.sha256(image.read_bytes()).hexdigest()!=entry.get('image_sha256'):
                    raise ValueError('Live-score picture missing or changed; nothing sent')
            entry['status']='unknown';match_events.publication_state(state,entry,'unknown',now);storage.write(statepath,state)
            mutation_started=False
            try:
                if publisher is None:publisher=PageFeed()
                if datetime.now(content.SAST)>=content.local(post['expires_at']) or post['kind'] in ('live','roundup') and not (post.get('event_ids') or in_window(datetime.now(content.SAST),cfg)):
                    entry['status']='cancelled';entry['error']='Content expired during credential verification; no mutation sent';match_events.publication_state(state,entry,'pending',now);continue
                mutation_started=True
                identity=publisher.send(post)
                entry['post_id']=identity;storage.write(statepath,state)
                publisher.verify(identity,post['caption'])
                entry['status']='published'
                match_events.publication_state(state,entry,'published',datetime.now(content.SAST))
                print(f'::notice::Facebook {post["kind"]} confirmed: https://www.facebook.com/{identity}')
            except PublishError as error:
                if post.get('event_ids') and not mutation_started:
                    entry['status']='cancelled';match_events.publication_state(state,entry,'pending',now)
                    for eid in post['event_ids']:
                        match_events.ledger(state)['events'][eid]['retry_after']=(now+timedelta(minutes=15)).isoformat()
                entry['error']=str(error);failed=True
                print('::error::Feed publication not confirmed; reservation retained. '+str(error).replace('%','%25').replace('\n',' '))
            finally:storage.write(statepath,state)
        return 1 if failed else 0
    branch=os.getenv('GITHUB_REF_NAME','local');repo=os.getenv('GITHUB_REPOSITORY','local/repo')
    prefix=storage.namespace(repo,branch,publish);output('prefix',prefix)
    state=None
    if args.phase!='preview' and os.getenv('GH_READ_TOKEN'):
        state=storage.restore(repo,branch,os.getenv('GITHUB_REPOSITORY_ID',''),prefix,os.environ['GH_READ_TOKEN'],work)
    output('restored','true' if state is not None else 'false')
    if state is None:
        if publish and not args.bootstrap:
            raise storage.StateError('No durable live feed ledger. Explicit first-run bootstrap/Page inspection required.')
        state={'schema':1,'namespace':prefix,'posts':[]}
    state['posts']=policy.history(state,now,cfg['topic_history_days'])
    if 'score_observations' in state:
        state['score_observations']={k:v for k,v in state['score_observations'].items() if now-content.local(v['since'])<timedelta(hours=6)}
    if publish and event_mode:
        for entry in state['posts']:
            if entry.get('event_ids') and entry.get('status')=='unknown' and entry.get('post_id'):
                try:
                    PageFeed().verify_hash(entry['post_id'],entry['caption_hash'])
                    entry['status']='published';match_events.publication_state(state,entry,'published',now)
                except PublishError:pass  # Never send a replacement for an ambiguous attempt.
    plans=[];report=[]
    kinds=KINDS if args.kind=='all' else (args.kind,)
    for kind in kinds:
        if source_blocked:
            report.append({'kind':kind,'status':'blocked','reason':'score-source rights/coverage approval pending; no Facebook request'});continue
        if publish and kind not in cfg.get('authorized_kinds',KINDS):
            report.append({'kind':kind,'status':'blocked','reason':'content type not authorised; unrelated feeds remain paused'});continue
        post,reason=build(kind,Path(args.source),now,cfg,state,preview=args.preview or args.phase=='preview')
        if not post:
            report.append({'kind':kind,'status':'skipped','reason':reason});continue
        if publish and kind in ('live','roundup') and not (cfg['live']['enabled'] and scores_approved(cfg)):
            report.append({'kind':kind,'status':'blocked','reason':'live rights/account coverage not approved'});continue
        ok,why=policy.allowed(post,state,now,cfg)
        if not ok:
            report.append({'kind':kind,'status':'skipped','reason':why});continue
        expiry=min(now+timedelta(minutes=5),content.local(post.get('expires_at',(now+timedelta(minutes=5)).isoformat())))
        if kind not in ('live','roundup','results') and post.get('fixture_ids'):
            source=content.load(Path(args.source)/'latest.json',{})
            for fixture in source.get('fixtures',[]):
                if fixture.get('id') in post['fixture_ids']:
                    expiry=min(expiry,content.local(fixture['kickoff']))
        post['expires_at']=expiry.isoformat()
        if post.get('graphic'):
            try:
                if post['graphic'].get('style')=='stadium' and cfg['live'].get('crests_enabled'):
                    from .crest_cache import prepare as prepare_crests
                    prepare_crests(post['graphic'],work/'crests')
                post['image']=str(render(post['graphic'],work/f'{kind}.jpg'))
                if kind=='live':post['image_sha256']=hashlib.sha256(Path(post['image']).read_bytes()).hexdigest()
            except ValueError as error:
                report.append({'kind':kind,'status':'skipped','reason':str(error)});continue
        (work/f'{kind}.txt').write_text(post['caption'],encoding='utf-8')
        entry=policy.reserve(post,state if args.phase!='preview' else {'posts':[]},now)
        entry['run_key']=os.getenv('GITHUB_RUN_ID','local')+'-'+os.getenv('GITHUB_RUN_ATTEMPT','1')
        if post.get('event_ids') and args.phase!='preview':
            # Simulated entries dedupe the dry-run namespace, never consume production events.
            match_events.publication_state(state,entry,'reserved' if publish else 'simulated',now)
        if not publish:entry['status']='simulated'
        plans.append(post);report.append({'kind':kind,'status':'reserved' if publish else 'dry_run','key':post['key']})
    storage.write(manifest,plans);storage.write(work/'report.json',report);storage.write(statepath,state)
    output('should_publish','true' if publish and plans else 'false')
    print('::notice::Facebook feed '+('LIVE PLAN' if publish else 'DRY RUN — no Facebook requests')+': '+json.dumps(report,separators=(',',':')))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as target:
            target.write('## Facebook feed '+('plan' if publish else 'dry run')+'\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,storage.StateError) as error:
        print('::error::'+str(error));raise SystemExit(1)
