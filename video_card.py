"""Deterministic, price-bounded Bet Advisor video cards. Never invent a selection."""
from __future__ import annotations
import math
import re

MIN_MATCHES, MAX_MATCHES = 5, 8
MIN_ODDS, TARGET_ODDS, MAX_ODDS = 2.00, 2.50, 3.30
MARKET = re.compile(r'^(O15|O25|C[HA]?O\d+)$')


def match_key(p):
    def club(s):
        s = re.sub(r'[^a-z0-9]+', ' ', str(s or '').lower())
        return re.sub(r'\b(fc|cf|sc|ac|afc|club)\b', '', s).strip()
    return tuple(sorted((club(p.get('home')), club(p.get('away')))))


def eligible(p):
    try:
        prob, odds = float(p['p']), float(p['odds'])
        floor = .55 if p.get('sel') == 'O25' else .65
        return bool(MARKET.fullmatch(str(p.get('sel', '')))) and floor <= prob < 1 and 1.16 <= odds <= MAX_ODDS
    except (ValueError, TypeError, KeyError):
        return False


def combined_odds(picks):
    return math.prod(float(p['odds']) for p in picks)


def choose(picks, *, allow_fallback=True):
    """Bounded beam search, one market per fixture; try O15/corners before O25.

    Odds are only a composition constraint after eligibility, not a probability adjustment.
    An infeasible card is empty, never padded or allowed outside the price range.
    """
    valid = [dict(p) for p in picks if eligible(p)]
    for fallback in ([False, True] if allow_fallback else [False]):
        groups = {}
        for p in valid:
            if p['sel'] == 'O25' and not fallback:
                continue
            groups.setdefault(match_key(p), {})[p['sel']] = p
        states = {0: [(1.0, 1.0, [])]}
        for key in sorted(groups):
            next_states = {n: list(rows) for n, rows in states.items()}
            for n, rows in states.items():
                if n >= MAX_MATCHES:
                    continue
                for odds, probability, card in rows:
                    for p in groups[key].values():
                        product = odds * float(p['odds'])
                        if product <= MAX_ODDS + 1e-9:
                            next_states.setdefault(n + 1, []).append((product, probability * float(p['p']), card + [p]))
            # Keep a diverse price frontier per count; highest probability in each 0.001 price bucket.
            states = {}
            for n, rows in next_states.items():
                buckets = {}
                for row in rows:
                    b = round(row[0] * 1000)
                    if b not in buckets or row[1] > buckets[b][1]:
                        buckets[b] = row
                states[n] = list(buckets.values())
        feasible = [r for n, rows in states.items() if n >= MIN_MATCHES for r in rows
                    if MIN_ODDS <= r[0] <= MAX_ODDS]
        if feasible:
            # Total corners preferred over team corners when target and quality tie.
            return min(feasible, key=lambda r: (abs(r[0] - TARGET_ODDS), -r[1],
                       -sum(str(p['sel']).startswith('CO') for p in r[2])))[2]
    return []
