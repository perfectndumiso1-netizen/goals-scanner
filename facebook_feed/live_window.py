"""Local coverage boundaries and strict matching to the existing app publication."""
from datetime import timedelta
from pathlib import Path
from .content import load, local, norm
from .provider import ProviderError


def in_window(now, config):
    now = local(now)
    window = config['live'].get('coverage_window')
    if not window:
        return True
    current = now.strftime('%H:%M')
    return window['start'] <= current < window['end']


def eligible_kickoff(kickoff, now, config):
    kickoff = local(kickoff)
    return kickoff.date() == local(now).date() and in_window(kickoff, config)


def app_candidates(root, now, config):
    """No speculative polling: fresh app fixtures, local kickoff >=08:00, <=4.5h old.

    The bounded age permits extra time/penalties without indefinitely polling an old fixture.
    Actual NS/finished state is decided by the provider, never inferred from kickoff alone.
    """
    publication = load(Path(root) / 'latest.json', {})
    try:
        generated = local(publication['meta']['generated'])
        if not timedelta(minutes=-5) <= now-generated <= timedelta(hours=config['max_source_age_hours']):
            raise ValueError()
        fixtures = publication['fixtures']
        if not isinstance(fixtures, list):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ProviderError('Fresh app coverage publication unavailable; no speculative polling') from None
    candidates = []
    for f in fixtures:
        try:
            kickoff = local(f['kickoff'])
            if (not f.get('id') or not norm(f['home']) or not norm(f['away']) or
                    f.get('time_known') is False or not eligible_kickoff(kickoff, now, config)):
                continue
            if timedelta(0) <= now-kickoff <= timedelta(minutes=270):
                candidates.append(f)
        except (KeyError, TypeError, ValueError):
            continue
    return candidates


def match_app_coverage(matches, fixtures):
    """No fuzzy club aliases, reversed sides, ambiguous duplicates or date-only matching."""
    matched = []
    used = set()
    for m in matches:
        candidates = [f for f in fixtures if norm(f['home']) == norm(m['home']) and
                      norm(f['away']) == norm(m['away']) and local(f['kickoff']) == local(m['kickoff'])]
        if len(candidates) != 1 or candidates[0]['id'] in used:
            continue
        # Multiple provider fixtures for the same app match are ambiguous, even with identical names.
        if sum(norm(other['home']) == norm(m['home']) and norm(other['away']) == norm(m['away']) and
               local(other['kickoff']) == local(m['kickoff']) for other in matches) != 1:
            continue
        used.add(candidates[0]['id'])
        matched.append({**m, 'fixture_id': candidates[0]['id']})
    return matched


def outstanding_candidates(fixtures, state, source):
    """Don't spend another call on an already published terminal fixture."""
    done={(norm(m['home']),norm(m['away']),local(m['kickoff']))
          for post in state.get('posts',[]) if post.get('kind')=='live' and post.get('status')=='published'
          for m in post.get('snapshot',[]) if m.get('source')==source and
          m.get('status') in ('FT','AET','PEN')}
    return [f for f in fixtures if (norm(f['home']),norm(f['away']),local(f['kickoff'])) not in done]
