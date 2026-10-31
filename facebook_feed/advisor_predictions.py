"""07:30 1X2 bulletin copied ONLY from the already-published Bet Advisor.

No Highlightly import, fixture lookup, provider API call or model recomputation.
"""
from datetime import timedelta
import math
from pathlib import Path
from . import content

SOURCE='published-bet-advisor'


def is_post(post):
    rows=post.get('snapshot')
    return (post.get('kind')=='editorial' and post.get('topic','').startswith('advisor-1x2:')
            and post.get('slot_key','').endswith(':predictions') and isinstance(rows,list)
            and bool(rows) and all(isinstance(r,dict) and r.get('source')==SOURCE for r in rows))


def build(root,now,cfg,state):
    from advisor_tracking import selections
    source=content.load(Path(root)/'latest.json',{})
    try:
        generated=content.local(source['meta']['generated'])
        if generated.date()!=now.date() or not timedelta(minutes=-5)<=now-generated<=timedelta(hours=cfg['max_source_age_hours']):
            return None,'Bet Advisor publication unavailable or stale; no predictions'
        pool=selections(source)
    except (KeyError,TypeError,ValueError):
        return None,'Bet Advisor publication unavailable or stale; no predictions'
    rows=[]
    for p in pool:
        if p.get('sel') not in ('H','D','A'):continue
        try:
            kickoff=content.local(p['kickoff'])
            if kickoff.date()!=now.date() or kickoff<=now+timedelta(minutes=10):continue
            odds,prob=float(p['odds']),float(p['p'])
            if isinstance(p['odds'],bool) or isinstance(p['p'],bool) or not math.isfinite(odds) or not math.isfinite(prob) or not 1.16<=odds<1000 or not 0<prob<1:
                return None,'Published Advisor 1X2 data invalid; no partial bulletin'
            if any(not isinstance(p.get(k),str) or not p[k].strip() or any(ord(c)<32 for c in p[k]) for k in ('home','away')):
                raise ValueError()
            rows.append({**{k:p[k] for k in ('home','away','sel','odds','p')},'country':p.get('country',''),
                         'kickoff':kickoff.isoformat(),'source':SOURCE,'publication_at':generated.isoformat()})
        except (KeyError,TypeError,ValueError,OverflowError):
            return None,'Published Advisor 1X2 data invalid; no partial bulletin'
    if not rows:return None,'No safely upcoming 1X2 selections on Bet Advisor; no filler'
    rows.sort(key=lambda p:(p['kickoff'],p['home'],p['away'],p['sel']))
    lines=["1X2 PREDICTIONS OF THE DAY",f'{now:%d %B %Y}','']
    for p in rows:
        selection={'H':f"1 — {p['home']} to win",'D':'X — Draw','A':f"2 — {p['away']} to win"}[p['sel']]
        lines += [f"{p['home']} vs {p['away']}",
                  f"{content.local(p['kickoff']):%H:%M} SAST · {selection} @ {float(p['odds']):.2f}",'']
    lines+=['1 = home win · X = draw · 2 = away win',
            '18+ · Predictions, not guarantees. Bet responsibly.','#FootballPredictions #1X2']
    caption='\n'.join(lines)
    if len(caption)>12000:return None,'Advisor bulletin too long; no selections silently omitted'
    key=f'editorial:{now.date()}:predictions'
    post=content.candidate('editorial',key,f'advisor-1x2:{now.date()}',caption,snapshot=rows,
                           fixture_ids=[],slot_key=key)
    post['expires_at']=min(now+timedelta(minutes=5),*(content.local(p['kickoff'])-timedelta(minutes=10) for p in rows)).isoformat()
    return post,'published Bet Advisor 1X2 selections; no football-data API calls'
