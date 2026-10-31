"""Exact video-edition manifests and accumulator settlement, without model/API calls.

Never infer video boundaries from the legacy merged daily history. Historical
unassigned selections can be disclosed, but are never called a single accumulator.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json

SLOTS=('morning','noon','evening')
FIELDS=('home','away','country','kickoff','sel','label','odds','p','p_sb')


def record(book,day,slot,picks,at):
    if slot not in SLOTS or not isinstance(picks,list) or not 5<=len(picks)<=8:
        raise ValueError('Exact video edition requires five to eight filmed picks')
    kept=[{k:p[k] for k in FIELDS if k in p} for p in picks]
    for p in kept:
        if not all(isinstance(p.get(k),str) and p[k].strip() for k in ('home','away','sel','kickoff')):
            raise ValueError('Filmed edition identity/date missing')
        price(p.get('odds'))
    if len({tuple(p.get(k) for k in ('home','away','country','kickoff')) for p in kept})!=len(kept):
        raise ValueError('A video accumulator cannot repeat a fixture')
    digest=hashlib.sha256(json.dumps(kept,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    out=deepcopy(book or {});editions=out.setdefault(day,{})
    if slot in editions:
        if editions[slot].get('sha256')!=digest:raise ValueError('Recorded video edition cannot be overwritten')
        return out
    editions[slot]={'id':f'{day}:{slot}','recorded_at':at,'sha256':digest,'picks':kept}
    return out


def price(value):
    try:
        if isinstance(value,bool):raise ValueError()
        p=Decimal(str(value))
        if not p.is_finite() or not Decimal('1.16')<=p<=1000:raise ValueError()
        return p
    except (InvalidOperation,TypeError,ValueError):
        raise ValueError('Original filmed price missing or invalid') from None


def settle(picks):
    """Flat one-unit accumulator; a void leg is 1.00, never a missing-score win."""
    states=[p.get('result','pending') for p in picks]
    if not states:raise ValueError('Empty accumulator')
    status=('LOST' if 'miss' in states else 'PENDING' if any(s not in ('hit','void') for s in states)
            else 'VOID' if all(s=='void' for s in states) else 'WON')
    original=Decimal(1);effective=Decimal(1)
    try:
        for p in picks:
            odds=price(p.get('odds'));original*=odds
            if p.get('result')!='void':effective*=odds
    except ValueError:original=effective=None
    returned=(Decimal(0) if status=='LOST' else Decimal(1) if status=='VOID' else effective if status=='WON' else None)
    return {'status':status,'original_odds':original,'settled_odds':effective,
            'return_units':returned,'profit_units':None if returned is None else returned-1}


def groups(state,day):
    """Return recorded editions and unassigned legacy legs, never guess a split."""
    records=(state.get('briefing_editions') or {}).get(day,{})
    editions=[];assigned=set()
    def key(p):return tuple(p.get(k) for k in ('home','away','sel','kickoff','country'))
    for slot in SLOTS:
        item=records.get(slot)
        if not isinstance(item,dict) or item.get('id')!=f'{day}:{slot}':continue
        picks=item.get('picks')
        if not isinstance(picks,list) or not 5<=len(picks)<=8:continue
        digest=hashlib.sha256(json.dumps(picks,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=item.get('sha256'):raise ValueError('Video edition integrity mismatch')
        editions.append((slot,picks));assigned.update(key(p) for p in picks)
    unique={}
    for p in (state.get('briefing_history') or {}).get(day,[]):
        if isinstance(p,dict) and all(isinstance(p.get(k),str) and p[k].strip() for k in ('home','away','sel','kickoff')) and key(p) not in assigned:
            unique.setdefault(key(p),p)
    return editions,list(unique.values())
