"""Nine distinct pre-match packages, four factual cards from verified match histories."""
from datetime import timedelta
from . import content, editorial as e
from .provider import ProviderError

MATCH_SLOTS = tuple((f'{hour:02d}:00', f'match{hour-7:02d}') for hour in range(8,17))
SLOTS = (('07:30','fixtures'),) + MATCH_SLOTS


def schedule(cfg=None):
    morning='predictions' if (cfg or {}).get('editorial',{}).get('morning_bulletin')=='advisor_1x2' else 'fixtures'
    return (('07:30',morning),)+MATCH_SLOTS


def due(now,cfg=None):
    now=content.local(now)
    for clock,slot in reversed(schedule(cfg)):
        start=now.replace(hour=int(clock[:2]),minute=int(clock[3:]),second=0,microsecond=0)
        if timedelta(0)<=now-start<timedelta(hours=1):return slot
    return None


def recent_spec(post):
    evidence=post['snapshot'][0]
    m=evidence['fixture']
    return {'kind':'recent-results','home':m['home'],'away':m['away'],
            'country':e.LEAGUES[m['league']][1],'league':e.LEAGUES[m['league']][0],
            'kickoff':m['kickoff'], 'period':'LAST 5 LEAGUE MATCHES · ALL VENUES',
            'home_results':evidence['home_sample']['matches'],
            'away_results':evidence['away_sample']['matches']}


def build(cfg,state,now,api=None):
    now=content.local(now);slot=due(now,cfg)
    if slot=='predictions':
        return None,'Advisor predictions require the published Advisor source; no Highlightly fallback'
    if slot=='fixtures':
        legacy=dict(cfg,editorial=dict(cfg['editorial'],package_mode=False))
        return e.build(legacy,state,now,api)
    h=cfg['highlightly']
    if not cfg['editorial']['enabled'] or not slot:return None,'editorial disabled or outside scheduled slot'
    if cfg.get('score_source')!='highlightly' or not h['rights_confirmed'] or not h['account_coverage_verified'] or h['verification_only']:
        return None,'Highlightly source approval required'
    slotkey=f'editorial:{now.date()}:{slot}'
    if any(p.get('slot_key')==slotkey and p.get('status') not in ('cancelled','rejected') for p in state.get('posts',[])):
        return None,'daily editorial slot already attempted'
    if any(p.get('status') in ('reserved','unknown') for p in state.get('posts',[])):
        return None,'unresolved publication; inspect/reconcile before API preparation'
    api=api or e.Source(cfg,state,now);book=e.cache(state,now)
    try:
        today=e.day_rows(api,book,now.date(),now)
        counted=[p for p in state.get('posts',[]) if p.get('status') not in ('cancelled','rejected')]
        used={p.get('topic') for p in counted}
        options=[m for m in today if m['league'] in e.LEAGUES and m['status']=='Not started'
                 and e.aware(m['kickoff'])>now+timedelta(minutes=10) and f"feature:{m['id']}" not in used
                 and str(m['id']) not in book.get('package_unavailable',{})]
        if not options:return None,'no distinct verified upcoming fixture for this slot'
        # Prefer complete, repeat-verified context and a clear form contrast.
        # Cold candidates tie on safe kickoff, NOT league prestige/coverage quotas.
        from .match_insights import priority
        chosen=min(options,key=lambda m:(tuple(-v for v in priority(m,book,now)),m['kickoff'],m['id']))
        try:
            post=e.comparison(api,book,chosen,now,with_context=True)
        except ProviderError as error:
            # Do not keep choosing the same factually unusable fixture in all
            # nine slots. Transport/cooldown/quota failures remain retryable on
            # the SAME fixture; no second expensive candidate within one attempt.
            reason=str(error)
            if not any(word in reason for word in ('network/response','request rejected','daily budget','cooldown')):
                book.setdefault('package_unavailable',{})[str(chosen['id'])]='verified_sample_unavailable'
            raise
        evidence=post['snapshot'][0]
        context=dict(home=chosen['home'],away=chosen['away'],home_id=chosen['home_id'],away_id=chosen['away_id'],
                     country=e.LEAGUES[chosen['league']][1],league=e.LEAGUES[chosen['league']][0],
                     kickoff=chosen['kickoff'],checked_at=now.isoformat(),seasons=evidence['seasons'])
        post['graphics']=[post['graphic'],recent_spec(post),
            dict(context,kind='recent-h2h',meetings=evidence['h2h']),
            dict(context,kind='venue-form',period='LAST 5 HOME / LAST 5 AWAY · LEAGUE RESULTS',
                 home_results=evidence['venue_form']['home'],away_results=evidence['venue_form']['away'])]
        post['slot_key']=slotkey
        return post,'verified four-picture match package'
    except ProviderError as error:
        return None,str(error)
