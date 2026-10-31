"""Nine distinct pre-match packages, two factual cards from one verified sample."""
from datetime import timedelta
from . import content, editorial as e
from .provider import ProviderError

MATCH_SLOTS = tuple((f'{hour:02d}:00', f'match{hour-7:02d}') for hour in range(8,17))
SLOTS = (('07:30','fixtures'),) + MATCH_SLOTS


def due(now):
    now=content.local(now)
    for clock,slot in reversed(SLOTS):
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
    now=content.local(now);slot=due(now)
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
        # Earliest safe kickoff first; reserve the remaining places for leagues
        # not represented today when otherwise they would all be crowded out.
        counts={key:0 for key in e.LEAGUES}
        for p in counted:
            if p.get('kind')!='editorial' or not p.get('topic','').startswith('feature:'):continue
            if content.local(p['at']).date()!=now.date():continue
            for item in p.get('snapshot',[]):
                league=item.get('fixture',{}).get('league')
                if league in counts:counts[league]+=1
        unrepresented={m['league'] for m in options if counts[m['league']]==0}
        places_left=17-now.hour
        pool=[m for m in options if m['league'] in unrepresented] if len(unrepresented)>=places_left else options
        chosen=min(pool,key=lambda m:(m['kickoff'],counts[m['league']],m['id']))
        try:
            post=e.comparison(api,book,chosen,now)
        except ProviderError as error:
            # Do not keep choosing the same factually unusable fixture in all
            # nine slots. Transport/cooldown/quota failures remain retryable on
            # the SAME fixture; no second expensive candidate within one attempt.
            reason=str(error)
            if not any(word in reason for word in ('network/response','request rejected','daily budget','cooldown')):
                book.setdefault('package_unavailable',{})[str(chosen['id'])]='verified_sample_unavailable'
            raise
        post['graphics']=[post['graphic'],recent_spec(post)]
        post['slot_key']=slotkey
        return post,'verified two-picture match package'
    except ProviderError as error:
        return None,str(error)
