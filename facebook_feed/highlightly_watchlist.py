"""Bounded, persistent selected-league schedule metadata and fair detail polling.

Catalog scores are NEVER published from this cache. Only fresh, identity-checked
provider details enter the existing event ledger. No account/namespace resets.
"""
from datetime import timedelta
import hashlib
import json
import math
import unicodedata
from .content import local
from .match_events import ACTIVE, TERMINAL, ledger, observe
from .provider import ProviderError

# Country + exact normalised competition aliases, never a substring/odds ranking.
LEAGUES={
    'psl':('South African PSL','South Africa',('Premier Soccer League','Premier Division','Premiership','PSL','Betway Premiership','DStv Premiership')),
    'laliga':('LaLiga','Spain',('LaLiga','La Liga','Primera Division','LaLiga EA Sports')),
    'epl':('EPL','England',('Premier League','English Premier League','EPL')),
    'bundesliga':('Bundesliga','Germany',('Bundesliga','1. Bundesliga')),
    'ligue1':('Ligue 1','France',('Ligue 1','Ligue 1 McDonalds',"Ligue 1 McDonald's")),
    'seriea':('Serie A','Italy',('Serie A','Serie A Enilive')),
}


def normal(value):
    if not isinstance(value,str):return ''
    return ''.join(c for c in unicodedata.normalize('NFKD',value).casefold() if c.isalnum())


def league_key(name,country):
    return next((key for key,(_,nation,aliases) in LEAGUES.items()
                 if normal(country)==normal(nation) and normal(name) in {normal(v) for v in aliases}),None)


def metadata(row,now):
    """Only bounded schedule identity; retains future kickoffs, excludes scores."""
    try:
        key=league_key(row['league']['name'],row['country']['name'])
        if key is None:return None
        mid=row['id'];home=row['homeTeam'];away=row['awayTeam']
        if type(mid) is not int or not 1<=mid<=2**63-1:raise ValueError()
        if any(type(t['id']) is not int or not 1<=t['id']<=2**63-1 for t in (home,away)):raise ValueError()
        if home['id']==away['id']:raise ValueError()
        for value in (home['name'],away['name']):
            if not isinstance(value,str) or not value.strip() or len(value)>200 or any(ord(c)<32 for c in value):raise ValueError()
        kickoff=local(row['date'])
        if kickoff.date()!=local(now).date() or not 8<=kickoff.hour<24:return None
        phase=row['state']['description']
        from .highlightly import STATES
        status=STATES.get(phase)
        if status not in ACTIVE|{'NS'}:return None
        if now-kickoff>timedelta(hours=6):return None
        return {'id':f'highlightly:{mid}','league':key,'competition':row['league']['name'],
                'country':row['country']['name'],'home':home['name'],'away':away['name'],
                'home_team_id':home['id'],'away_team_id':away['id'],'kickoff':kickoff.isoformat()}
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ProviderError('Selected-league catalog identity/schema unverified; no replacement committed') from None


def choose(candidates,existing,now,limit=5):
    """One PSL first if available, rotating European priority, fewer overlaps first.

    Existing slots are never recycled during a SAST day, even after FT/cancellation.
    This prevents a 'five slots' cap from silently becoming unlimited daily games.
    """
    selected={k:dict(v) for k,v in existing.items()}
    if len(selected)>=limit:return selected
    other=[key for key in LEAGUES if key!='psl']
    shift=local(now).date().toordinal()%len(other)
    order=['psl']+other[shift:]+other[:shift]
    pools={key:[] for key in order}
    for m in candidates:
        if m['id'] not in selected:pools[m['league']].append(m)
    def preference(m):
        start=local(m['kickoff']);end=start+timedelta(minutes=140)
        overlap=sum(start<local(v['kickoff'])+timedelta(minutes=140) and local(v['kickoff'])<end for v in selected.values())
        return overlap,abs((start-now).total_seconds()),m['kickoff'],m['id']
    # Prioritise representation across leagues before taking another from one league.
    represented={m['league'] for m in selected.values()}
    while len(selected)<limit:
        progress=False
        for key in sorted(order,key=lambda k:k in represented):
            if not pools[key]:continue
            value=min(pools[key],key=preference);pools[key].remove(value)
            selected[value['id']]=dict(value);represented.add(key);progress=True
            if len(selected)>=limit:break
        if not progress:break
    return selected


def signature(settings):
    return hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def summary(book):
    return {'scope':'selected_matches_only','day':book.get('day'),
            'selection_policy':'PSL first when eligible; rotating European league priority; prefer staggered kickoffs',
            'last_observed_at':book.get('last_observed_at'),
            'catalog_at':book.get('catalog_at'),'catalog_attempts':book.get('catalog_attempts',0),
            'eligible_catalog_matches':book.get('eligible_count',0),'status':book.get('status','not_started'),
            'catalog_problem':book.get('catalog_problem'),
            'matches':[{k:v for k,v in row.items() if k in ('id','league','competition','country','home','away','kickoff','last_attempt','confirmed_status','problem')}
                       for row in book.get('selected',{}).values()]}


def poll(cfg,state,now,api=None):
    from .highlightly import Highlightly
    from .live_window import in_window
    if not in_window(now,cfg):return False,'outside 08:00–24:00 SAST score coverage'
    if cfg['highlightly']['verification_only']:return False,'Highlightly staging gate active; no selected-match reads'
    settings=cfg['highlightly']['watchlist'];day=local(now).date().isoformat()
    book=state.setdefault('highlightly_watchlist',{})
    if book.get('day')!=day:
        prior=summary(book) if book else None
        book.clear();book.update(day=day,signature=signature(settings),selected={},catalog_attempts=0,status='awaiting_catalog')
        if prior:book['previous_day']=prior  # One bounded roster only; event/post history is elsewhere and untouched.
    if book.get('signature')!=signature(settings):
        raise ProviderError('Watchlist settings changed during the day; existing roster retained for operator review')
    if book.get('next_poll') and now<local(book['next_poll']):return False,'awaiting selected-match polling interval'
    book['next_poll']=(now+timedelta(minutes=cfg['highlightly']['poll_interval_minutes'])).isoformat()
    api=api or Highlightly(cfg,state,now)
    if api.budget.get('after') and now<local(api.budget['after']):return False,'Highlightly account cooldown; roster/history retained'
    if api.budget.get('remaining')==0 or api.budget['requests']>=cfg['highlightly']['daily_request_budget']:
        book['status']='quota_unavailable';return False,'Highlightly quota unavailable; no terminal state inferred'
    catalog_due=not book.get('catalog_at') or now-local(book['catalog_at'])>=timedelta(hours=settings['catalog_refresh_hours'])
    plan_missing=not api.budget.get('plan_verified_at')
    retry_due=not book.get('catalog_retry_after') or now>=local(book['catalog_retry_after'])
    if (catalog_due or plan_missing) and retry_due and book['catalog_attempts']<settings['max_catalog_attempts_per_day']:
        # An optional rediscovery must not consume the final few detail requests.
        available=min(cfg['highlightly']['daily_request_budget']-api.budget['requests'],api.budget.get('remaining') if api.budget.get('remaining') is not None else 100)
        estimated=book.get('catalog_pages',cfg['highlightly']['max_pages_per_poll'])
        if not book.get('catalog_at') or plan_missing or available>=estimated+1:
            book['catalog_attempts']+=1
            try:
                rows=api.matches()
                candidates=[m for row in rows if (m:=metadata(row,now)) is not None]
                if len(candidates)>200:raise ProviderError('Selected-league catalog bound exceeded')
                updated={k:dict(v) for k,v in book['selected'].items()}
                by_id={m['id']:m for m in candidates}
                for key,old in updated.items():
                    new=by_id.get(key)
                    if new and all(old[k]==new[k] for k in ('home_team_id','away_team_id','home','away','league')):
                        # Re-time only before any confirmed live observation of this target.
                        if old.get('confirmed_status') in (None,'NS'):old['kickoff']=new['kickoff']
                selected=choose(candidates,updated,now,settings['max_matches'])
                book.update(selected=selected,catalog_at=api.at,catalog_pages=max(1,math.ceil(len(rows)/100)),eligible_count=len(candidates),status='selected')
                book.pop('catalog_retry_after',None);book.pop('catalog_problem',None)
            except ProviderError:
                book['catalog_retry_after']=(now+timedelta(hours=1)).isoformat()
                book['catalog_problem']='catalog_refresh_failed_prior_roster_retained'
                book['status']='degraded_catalog'
                return False,'Selected-match catalog unavailable; prior roster retained, no score inferred'
    if not api.budget.get('plan_verified_at'):
        return False,'Fresh Highlightly Free-plan verification unavailable; no detail reads'
    due=[]
    for row in book['selected'].values():
        if row.get('confirmed_status') in TERMINAL:continue
        kickoff=local(row['kickoff'])
        if now<kickoff:continue
        if now-kickoff>timedelta(hours=6):
            row['problem']='tracking_window_exceeded_unresolved';continue
        if row.get('last_attempt') and now-local(row['last_attempt'])<timedelta(minutes=cfg['highlightly']['poll_interval_minutes']):continue
        due.append(row)
    due.sort(key=lambda r:(r.get('last_attempt',''),r['kickoff'],r['id']))
    fresh=0;detail_failed=False
    for row in due[:cfg['highlightly']['max_details_per_poll']]:
        row['last_attempt']=now.isoformat()
        try:
            m=api.detail(row['id'])
            if m is None:
                row['problem']='detail_unusable_state_or_score';continue
            if any(m.get(k)!=row.get(k) for k in ('id','home_team_id','away_team_id','home','away')) or (m['kickoff']!=row['kickoff'] and m['status'] not in ('PST','CANC')) or league_key(m.get('competition'),m.get('country'))!=row['league']:
                raise ProviderError('Selected detail identity/competition mismatch')
            if not -30<=(now-local(api.at)).total_seconds()<=cfg['event_monitor']['max_source_age_seconds']:
                raise ProviderError('Selected observation expired')
            first_sample=not row.get('baseline_at')
            prior_events=set(ledger(state)['events']) if first_sample else set()
            observe(state,[m],api.at,now)
            accepted=ledger(state)['matches'].get(row['id'])
            if not accepted or accepted['observed_at']!=api.at:
                row['problem']='observation_regression_or_stall_rejected'
                continue
            if first_sample:
                row['baseline_at']=api.at
                # Preserve old pending/unknown evidence; suppress only events just
                # created by crossing from the old global snapshot into this roster.
                for eid in set(ledger(state)['events'])-prior_events:
                    e=ledger(state)['events'][eid]
                    if e['fixture_id']==row['id']:
                        e['status']='expired';e['reason']='selected_roster_baseline'
            row['kickoff']=m['kickoff']
            row['confirmed_status']=m['status'];row.pop('problem',None);fresh+=1
        except ProviderError:
            row['problem']='detail_failed_or_identity_unverified'
            book['status']='degraded_detail';detail_failed=True
            break  # No further calls after a new provider/network/access failure.
    if fresh:book['last_observed_at']=now.isoformat()
    if fresh and not detail_failed:book['status']='observed_selected_matches'
    return bool(fresh),f'Selected coverage only: {len(book["selected"])} daily matches; {fresh} fresh detail observations; no missing/final scores inferred'
