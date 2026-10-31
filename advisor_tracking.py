"""Forward-only record of the selections actually visible in Bet Advisor.

First published price/probability is frozen, never replaced by a later winning line.
No historical backfill. Missing corner statistics stay pending under safe.settle_bets.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


def selections(payload):
    sf = payload.get('safe') or {}
    today = str((payload.get('meta') or {}).get('generated') or '')[:10]
    fixtures = {f['id']: f for f in payload.get('fixtures', [])}
    groups = (sf.get('today') or {}).get('groups') or []
    picks = [p for g in groups for p in (g.get('bets') or [])[:6]]
    if not picks:
        picks = list((sf.get('today') or {}).get('bets') or [])[:6]
    picks += [p for p in sf.get('bets', []) if str(p.get('kickoff', ''))[:10] == today][:5]
    for name in ('value', 'strong'):
        for p in (payload.get('groups') or {}).get(name, [])[:5]:
            f = fixtures.get(p.get('id'), {})
            picks.append({**f, **p, 'fixture': f.get('id'), 'kickoff': f.get('kickoff'),
                          'label': p.get('label') or p.get('sel')})
    unique = {}
    for p in picks:
        if not p.get('home') or not p.get('away') or not p.get('sel'):
            continue
        key = (str(p.get('kickoff') or '')[:10], p.get('country'), p['home'], p['away'], p['sel'])
        unique.setdefault(key, dict(p))
    return list(unique.values())


def update(book, picks, results, now):
    import pandas as pd
    import safe
    df = pd.DataFrame(book, columns=safe.SAFE_BET_COLS)
    existing = set(zip(df.match_date, df.country, df.home, df.away, df.sel))
    new = []
    for p in picks:
        day = str(p.get('kickoff') or '')[:10]
        key = (day, p.get('country', ''), p['home'], p['away'], p['sel'])
        if key in existing:
            continue
        try:
            ko = datetime.fromisoformat(str(p['kickoff']))
            reference = now.replace(tzinfo=ko.tzinfo) if ko.tzinfo is None or now.tzinfo is None else now
            if ko <= reference:
                continue  # never begin tracking a pick after kickoff
            odds, probability = float(p['odds']), float(p['p'])
            if not (odds >= 1.16 and 0 < probability < 1):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        existing.add(key)
        new.append({**p, 'match_date': day, 'status': 'pending', 'report_date': now.strftime('%Y-%m-%d'),
                    'run': now.isoformat(), 'kind': 'advisor', 'botd': '', 'score': '', 'settled_on': ''})
    if new:
        df = pd.concat([df, pd.DataFrame(new).reindex(columns=safe.SAFE_BET_COLS)], ignore_index=True)
    # Exact fixture date, not the legacy ledger's +/-3-day fuzzy match.
    if results is not None and not results.empty:
        results = results.copy()
        results['date'] = pd.to_datetime(results['date']).dt.tz_localize(None)
    frames = []
    for day, rows in df.groupby('match_date', sort=False):
        day_results = results
        if results is not None and not results.empty:
            day_results = results[results['date'].dt.strftime('%Y-%m-%d') == day]
        frames.append(safe.settle_bets(rows, day_results, now))
    if frames:
        df = pd.concat(frames, ignore_index=True)
    return json.loads(df.to_json(orient='records'))


def summary(book):
    def stats(rows):
        settled = [p for p in rows if p.get('status') in ('hit', 'miss')]
        wins = sum(p['status'] == 'hit' for p in settled)
        profit = sum(float(p['odds']) - 1 if p['status'] == 'hit' else -1 for p in settled)
        return {'tracked': len(rows), 'settled': len(settled), 'wins': wins, 'losses': len(settled)-wins,
                'pending': sum(p.get('status') == 'pending' for p in rows),
                'void': sum(p.get('status') == 'void' for p in rows),
                'hit_rate': wins/len(settled) if settled else None,
                'profit_units': round(profit, 3), 'roi': profit/len(settled) if settled else None}
    return {**stats(book), 'since': min((p['report_date'] for p in book), default=None),
            'markets': {sel: stats([p for p in book if p['sel'] == sel]) for sel in sorted({p['sel'] for p in book})},
            'recent': sorted(book, key=lambda p: (p.get('kickoff') or ''), reverse=True)[:30],
            'scope': 'Every published Advisor recommendation, high-confidence pick, edge and strong signal; first price frozen. Flat 1-unit singles; no backfill.'}


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return []


def video_results(book, history):
    """Recap the exact filmed lines/prices, not whatever later replaced them on the board."""
    index={}
    for p in book:
        key=(p.get('match_date'),p.get('home'),p.get('away'),p.get('sel'))
        index.setdefault(key,[]).append(p)
    out=[]
    for p in history:
        day=str(p.get('kickoff') or '')[:10]
        candidates=[r for r in index.get((day,p.get('home'),p.get('away'),p.get('sel')),[])
                    if not p.get('country') or r.get('country')==p['country']]
        # Conflicting/ambiguous ledger records are not permission to pick a win.
        if len(candidates)!=1:continue
        r=candidates[0]
        if r.get('status') in ('hit','miss','void'):
            out.append({**p,'result':r['status'],'score':r.get('score')})
    return out
