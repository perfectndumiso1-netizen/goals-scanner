"""Opt-in score reader for exactly the app's published fixture IDs.

Uses the same public Livescore JSON endpoint as the Android app, not a paid plan
or a fallback that silently bypasses the existing API-FOOTBALL rights gates.
Facebook publication still requires separate app-source rights/coverage approval.
"""
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import re
from urllib.request import Request, build_opener
from urllib.error import HTTPError

from facebook_post import _NoRedirect
from .content import load, local, norm
from .provider import ProviderError

BASE = 'https://prod-public-api.livescore.com/v1/api/app/date/soccer'
# Match the existing Android Net.UA, without importing scanner runtime dependencies.
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0 Safari/537.36')
STATUSES = {'1H':'1H', '2H':'2H', 'NS':'NS', 'HT':'HT', 'FT':'FT', 'AET':'AET', 'AP':'PEN', 'PEN':'PEN',
            'Postp.':'PST', 'Canc.':'CANC', 'Aband.':'ABD', 'Susp.':'SUSP', 'Int.':'INT',
            'ET':'ET', 'BT':'BT', 'P':'P'}


def status(raw):
    raw = str(raw or '').strip()
    if raw in STATUSES:return STATUSES[raw]
    # The app's feed reports the live minute (including added time) instead of 1H/2H.
    minute = re.fullmatch(r"(\d{1,3})(?:\+(\d{1,2}))?'?", raw)
    if minute:
        value = int(minute[1])
        if 0 < value <= 120:return '1H' if value <= 45 else '2H' if value <= 90 else 'ET'
    return None


def goal(value):
    if isinstance(value, bool):return None
    if not isinstance(value, (str,int)) or not re.fullmatch(r'\d{1,2}',str(value)):return None
    return int(value)


class AppScores:
    def __init__(self, root, config, state, now, opener=None):
        self.root=root;self.config=config['app_scores'];self.state=state;self.now=now
        self.opener=opener or build_opener(_NoRedirect())

    def fixtures(self):
        if self.state.get('app_score_after') and self.now<local(self.state['app_score_after']):raise ProviderError('App score source cooldown active')
        publication=load(self.root/'latest.json', {})
        try:
            generated=local(publication['meta']['generated'])
            if not timedelta(minutes=-5)<=self.now-generated<=timedelta(hours=12):
                raise ProviderError('App publication stale; coverage cannot be established')
            rows=publication['fixtures']
            if not isinstance(rows,list):raise ValueError()
        except (KeyError,TypeError,ValueError):
            raise ProviderError('App fixture publication missing/malformed') from None
        coverage={};seen=set()
        for f in rows:
            try:
                ko=local(f['kickoff']);eid=str(f['livescore_id'])
                if not eid.isdecimal() or eid in seen or str(f.get('id',''))[:10]!=ko.date().isoformat():continue
                if not self.now-timedelta(hours=12)<=ko<=self.now+timedelta(hours=24):continue
                seen.add(eid);coverage[eid]=f
            except (KeyError,TypeError,ValueError):continue
        if not coverage:return [],self.now.isoformat()
        cache=self.state.get('app_score_cache')
        if cache:
            age=self.now-local(cache['fetched'])
            if timedelta(0)<=age<timedelta(minutes=self.config['poll_interval_minutes']):
                if age>timedelta(seconds=self.config['max_source_age_seconds']):
                    raise ProviderError('Awaiting next app-source poll; saved scores are not fresh enough to post')
                return [m for m in cache['matches'] if str(m['id']) in coverage and m['fixture_id']==coverage[str(m['id'])]['id'] and norm(m['home'])==norm(coverage[str(m['id'])]['home']) and norm(m['away'])==norm(coverage[str(m['id'])]['away'])],cache['fetched']
        days=sorted({local(f['kickoff']).date() for f in coverage.values()})[:2]
        matches=[];fetched=[];seen_events=set()
        for day in days:
            req=Request(f'{BASE}/{day:%Y%m%d}/2?MD=1',headers={'Accept':'application/json','User-Agent':UA,'Accept-Language':'en'})
            try:
                with self.opener.open(req,timeout=20) as response:
                    stamp=parsedate_to_datetime(response.headers.get('Date',''))
                    if stamp.tzinfo is None or abs((self.now-stamp).total_seconds())>self.config['max_source_age_seconds']:
                        raise ProviderError('App source HTTP timestamp missing/stale')
                    raw=response.read(8*1024*1024+1)
                    if len(raw)>8*1024*1024:raise ProviderError('App score response exceeds size bound')
                    data=json.loads(raw)
                if not isinstance(data.get('Stages'),list):raise ValueError()
            except HTTPError as error:
                if error.code in (429,503):
                    try:seconds=max(300,min(86400,int(error.headers.get('Retry-After','300'))))
                    except (TypeError,ValueError):seconds=300
                    self.state['app_score_after']=(self.now+timedelta(seconds=seconds)).isoformat()
                raise ProviderError(f'App score HTTP {error.code}; no score posted') from None
            except ProviderError:raise
            except Exception:raise ProviderError('App live-score request failed; no old or invented score substituted') from None
            fetched.append(stamp)
            for stage in data['Stages']:
                if not isinstance(stage,dict) or not isinstance(stage.get('Events'),list):continue
                for event in stage['Events']:
                    try:
                        eid=str(event['Eid']);f=coverage.get(eid)
                        if not f or eid in seen_events:continue
                        home,away=event['T1'][0]['Nm'],event['T2'][0]['Nm']
                        if norm(home)!=norm(f['home']) or norm(away)!=norm(f['away']):continue
                        ko=local(datetime.strptime(str(event['Esd']), '%Y%m%d%H%M%S').isoformat())
                        if abs((ko-local(f['kickoff'])).total_seconds())>1200 or ko.date()!=day:continue
                        phase=status(event.get('Eps'));hg,ag=goal(event.get('Tr1')),goal(event.get('Tr2'))
                        if phase is None or phase not in ('NS','PST','CANC') and (hg is None or ag is None):continue
                        if phase in ('NS','PST','CANC'):hg=ag=None
                        # Without an explicit penalty shootout result, never label a winner after penalties.
                        if phase=='PEN':continue
                        seen_events.add(eid)
                        matches.append(dict(id=eid,fixture_id=f['id'],home=f['home'],away=f['away'],
                            country=f.get('country',''),competition=f.get('competition') or f.get('league',''),
                            kickoff=local(f['kickoff']).isoformat(),status=phase,home_goals=hg,away_goals=ag,
                            penalties=None,elapsed=str(event.get('Eps',''))))
                    except (KeyError,TypeError,ValueError,IndexError):continue
        stamp=min(fetched).isoformat()
        self.state['app_score_cache']={'fetched':stamp,'matches':matches}
        return matches,stamp

    def coverage(self):
        matches,stamp=self.fixtures()
        return {'source':'app Livescore feed','fetched':stamp,'matched':len(matches),
                'fixture_ids':[m['fixture_id'] for m in matches],
                'rights_confirmed':self.config['rights_confirmed'],
                'coverage_verified':self.config['coverage_verified'],
                'note':'A read-only observation is not publication-rights clearance or an edit integration test.'}
