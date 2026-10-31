"""Scheduled factual football, isolated from live events and predictions.

Only documented /matches routes; list/detail agreement is a same-provider
cross-check, not independent-source verification. No fabricated missing samples.
"""
from datetime import datetime, timedelta
import re
from . import content
from .highlightly import Highlightly, pair
from .highlightly_watchlist import LEAGUES, league_key
from .provider import ProviderError

SLOTS=(('07:30','fixtures'),('08:30','results'),('10:00','psl'),('11:00','epl'),
       ('12:00','laliga'),('13:00','seriea'),('14:00','bundesliga'),('15:00','ligue1'),
       ('19:30','story'),('23:00','evening'))
TAGS={'psl':'#PSL #SouthAfricanFootball','epl':'#PremierLeague','laliga':'#LaLiga',
      'seriea':'#SerieA','bundesliga':'#Bundesliga','ligue1':'#Ligue1'}
FINAL={'Finished','Finished after extra time','Finished after penalties'}


def due(now):
    now=content.local(now)
    for clock,slot in SLOTS:
        target=now.replace(hour=int(clock[:2]),minute=int(clock[3:]),second=0,microsecond=0)
        # GitHub cron can arrive almost an hour late. Admit the current slot
        # until the next hour, never revive previous slots or a prior day's work.
        if timedelta(0)<=now-target<timedelta(minutes=60):return slot
    return None


def aware(value):
    stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Aware source timestamp required')
    return content.local(stamp)


def fixture(row):
    """Whitelist factual identity/score only; never persist predictions/news/logos."""
    try:
        league=league_key(row['league']['name'],row['country']['name'])
        if not league:return None
        for value in (row['id'],row['league']['id'],row['homeTeam']['id'],row['awayTeam']['id']):
            if type(value) is not int or not 0<value<2**63:raise ValueError()
        if row['homeTeam']['id']==row['awayTeam']['id']:raise ValueError()
        for side in ('homeTeam','awayTeam'):
            name=row[side]['name']
            if not isinstance(name,str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):raise ValueError()
        season=row['league'].get('season')
        if season is not None and (type(season) is not int or not 1900<=season<=2100):raise ValueError()
        score=pair(row['state'].get('score',{}).get('current'))
        status=row['state']['description']
        if not isinstance(status,str):raise ValueError()
        return {'id':row['id'],'league':league,'league_id':row['league']['id'],'season':season,
                'home':row['homeTeam']['name'],'away':row['awayTeam']['name'],
                'home_id':row['homeTeam']['id'],'away_id':row['awayTeam']['id'],
                'kickoff':aware(row['date']).isoformat(),'status':status,'score':score}
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ProviderError('Editorial fixture identity/score unverified; raw response omitted') from None


class Source(Highlightly):
    def catalog(self,params):
        rows=[];total=None;stamp=None
        for offset in range(0,self.cfg['max_pages_per_poll']*100,100):
            result=self.request('matches',dict(params,timezone='Africa/Johannesburg',limit=100,offset=offset))
            try:
                values=result['data'];p=result['pagination']
                if result['plan']['tier'] not in ('BASIC','FREE'):raise ValueError()
                count=p['totalCount']
                if type(count) is not int or not 0<=count<=1000:raise ValueError()
                if any(type(p[k]) is not int for k in ('limit','offset')) or p['offset']!=offset or p['limit']!=100:raise ValueError()
                if not isinstance(values,list) or len(values)!=min(100,max(0,count-offset)):raise ValueError()
                if total is not None and total!=count:raise ValueError()
                total=count;rows.extend(values);stamp=self.at if stamp is None else min(stamp,self.at)
                self.budget['plan_verified_at']=self.at
                if len(rows)>=count:break
            except (KeyError,TypeError,ValueError):
                raise ProviderError('Editorial pagination/Free plan unverified; no partial catalog') from None
        else:raise ProviderError('Editorial catalog exceeds safety bound')
        ids=[r.get('id') if isinstance(r,dict) else None for r in rows]
        if any(type(i) is not int or i<=0 for i in ids) or len(set(ids))!=len(ids):
            raise ProviderError('Editorial duplicate/invalid catalog identity')
        self.at=stamp
        return rows

    def raw_detail(self,mid):
        result=self.request(f'matches/{mid}')
        if not isinstance(result,list) or len(result)!=1 or not isinstance(result[0],dict) or result[0].get('id')!=mid:
            raise ProviderError('Editorial detail identity unverified')
        return result[0]


def cache(state,now):
    day=content.local(now).date().isoformat()
    book=state.setdefault('football_editorial',{})
    if book.get('day')!=day:
        book.clear();book.update(day=day,fixtures={},histories={},details={})
    return book


def day_rows(api,book,day,now,refresh=False):
    key=day.isoformat();saved=book['fixtures'].get(key)
    if not saved or refresh or now-aware(saved['at'])>timedelta(hours=12):
        # Complete day, then exact country+alias matching: querying a guessed
        # sponsor alias can silently misreport a league as having no fixtures.
        raw=api.catalog({'date':key})
        values=[m for r in raw if (m:=fixture(r)) is not None]
        if any(aware(m['kickoff']).date()!=day for m in values):
            raise ProviderError('Editorial date identity mismatch')
        saved={'at':api.at,'rows':values};book['fixtures'][key]=saved
    return saved['rows']


def checked_detail(api,book,m,now):
    saved=book['details'].get(str(m['id']))
    # Finals can be reused for this SAST day; upcoming details must be current.
    if saved and saved['row']['status'] in FINAL:
        other=saved['row']
    else:
        other=fixture(api.raw_detail(m['id']))
        if other is None:raise ProviderError('Detail outside approved leagues')
    if any(other[k]!=m[k] for k in ('id','league','league_id','season','home','away','home_id','away_id','kickoff','status','score')):
        raise ProviderError('List/detail conflict; statistics withheld')
    if other['status'] in FINAL and aware(other['kickoff'])>=now:raise ProviderError('Future final result rejected')
    book['details'][str(m['id'])]={'at':api.at,'row':other}
    return other


def sample(api,book,target,side,now):
    if target['season'] is None:raise ProviderError('League season missing; no mixed-period comparison')
    key=f"{target['league_id']}:{target['season']}"
    if key not in book['histories']:
        passes=[]
        for _ in range(2):
            rows=[fixture(r) for r in api.catalog({'leagueId':target['league_id'],'season':target['season']})]
            if any(m is None or (m['league_id'],m['season'],m['league'])!=(target['league_id'],target['season'],target['league']) for m in rows):
                raise ProviderError('History league/season mismatch')
            passes.append(rows)
        book['histories'][key]={'passes':passes,'checked_at':api.at}
    tid=target[side+'_id'];name=target[side]
    samples=[]
    for records in book['histories'][key]['passes']:
        rows=[m for m in records if m['status'] in FINAL and aware(m['kickoff'])<min(now,aware(target['kickoff']))
              and now-aware(m['kickoff'])<=timedelta(days=180) and tid in (m['home_id'],m['away_id'])]
        samples.append(sorted(rows,key=lambda m:(m['kickoff'],m['id']),reverse=True)[:5])
    if samples[0]!=samples[1]:raise ProviderError('Repeat-catalog sample conflict; statistics withheld')
    rows=samples[0]
    if len(rows)!=5:raise ProviderError('Five recent completed league matches unavailable; no card')
    if any(m['score'] is None for m in rows):
        raise ProviderError('Recent final score missing; sample cannot be backfilled')
    if any(m['status']!='Finished' for m in rows):
        raise ProviderError('Extra-time/shootout sample needs editorial scope review')
    verified=[]
    for index,m in enumerate(rows):
        # Cross-check every sample against a second complete catalog and the
        # newest match against its detail. No 60-detail/day requirement.
        if index==0:m=checked_detail(api,book,m,now)
        home=m['home_id']==tid
        if m['home' if home else 'away']!=name:raise ProviderError('Historical team name/identity conflict')
        gf,ga=m['score'] if home else reversed(m['score'])
        verified.append({'id':m['id'],'date':m['kickoff'],'gf':gf,'ga':ga})
    return {'matches':verified,'scored':sum(m['gf'] for m in verified),'conceded':sum(m['ga'] for m in verified),
            'wins':sum(m['gf']>m['ga'] for m in verified),'clean':sum(m['ga']==0 for m in verified),
            'draws':sum(m['gf']==m['ga'] for m in verified),'losses':sum(m['gf']<m['ga'] for m in verified),
            'unbeaten':sum(m['gf']>=m['ga'] for m in verified),'scored_in':sum(m['gf']>0 for m in verified)}


def hashtags(league=None,teams=()):
    tags=[TAGS[league]] if league else [TAGS[k] for k in LEAGUES]
    tags+=['#'+re.sub(r'[^A-Za-z0-9]','',name) for name in teams]
    return ' '.join(tags+['#Football','#MatchStats' if teams else '#FootballResults'])


def comparison(api,book,m,now):
    if m['status']!='Not started' or aware(m['kickoff'])<=now+timedelta(minutes=10):
        raise ProviderError('Featured match is not safely upcoming')
    checked_detail(api,book,m,now)
    home=sample(api,book,m,'home',now);away=sample(api,book,m,'away',now)
    rows=[('GOALS SCORED',home['scored'],away['scored']),('GOALS CONCEDED',home['conceded'],away['conceded']),
          ('GOALS PER GAME',f"{home['scored']/5:.2f}",f"{away['scored']/5:.2f}"),
          ('CONCEDED PER GAME',f"{home['conceded']/5:.2f}",f"{away['conceded']/5:.2f}"),
          ('CLEAN SHEETS',home['clean'],away['clean']),('WINS',home['wins'],away['wins']),
          ('DRAWS',home['draws'],away['draws']),('LOSSES',home['losses'],away['losses']),
          ('UNBEATEN MATCHES',home['unbeaten'],away['unbeaten']),('MATCHES SCORED IN',home['scored_in'],away['scored_in'])]
    # All three are bounded observed facts, not predictions or unsupported H2H claims.
    facts=[f"{m['home']}: {home['wins']} wins and {home['clean']} clean sheets in their last five league matches.",
           f"{m['away']}: {away['wins']} wins and {away['clean']} clean sheets in their last five league matches.",
           f"Goals scored/conceded over those samples: {m['home']} {home['scored']}/{home['conceded']}; {m['away']} {away['scored']}/{away['conceded']}."]
    dates=lambda s: f"{min(r['date'] for r in s['matches'])[:10]} to {max(r['date'] for r in s['matches'])[:10]}"
    caption=f"{m['home']} vs {m['away']} | {LEAGUES[m['league']][0]}\nKickoff: {aware(m['kickoff']):%d %b %Y, %H:%M} SAST\n\n"+'\n'.join('• '+f for f in facts)
    caption+=f"\n\nSample: last five completed matches in the same league/season, all venues.\n{m['home']}: {dates(home)}.\n{m['away']}: {dates(away)}.\n\nYour pick: {m['home']}, draw or {m['away']}? Comment below.\n\n"+hashtags(m['league'],(m['home'],m['away']))
    spec={'kind':'team-comparison','home':m['home'],'away':m['away'],'league':LEAGUES[m['league']][0],
          'country':LEAGUES[m['league']][1],'kickoff':m['kickoff'],'rows':rows,'period':'LAST 5 LEAGUE MATCHES • ALL VENUES',
          'checked_at':now.isoformat()}
    post=content.candidate('editorial',f"feature:{m['id']}",f"feature:{m['id']}",caption,graphic=spec,
                           fixture_ids=[m['id']],snapshot=[{'fixture':m,'home_sample':home,'away_sample':away}])
    post['expires_at']=min(now+timedelta(minutes=5),aware(m['kickoff'])-timedelta(minutes=5)).isoformat()
    return post


def build(cfg,state,now,api=None):
    settings=cfg.get('editorial',{})
    slot=due(now)
    if not settings.get('enabled') or not slot:return None,'editorial disabled or outside scheduled slot'
    if cfg.get('score_source')!='highlightly':return None,'editorial requires the approved Highlightly source'
    h=cfg['highlightly']
    if not h['rights_confirmed'] or not h['account_coverage_verified'] or h['verification_only']:
        return None,'Highlightly source approval required'
    # A completed attempt cannot select another fixture for the same daily slot.
    slotkey=f"editorial:{now.date()}:{slot}"
    if any(p.get('slot_key')==slotkey and p.get('status') not in ('cancelled','rejected') for p in state.get('posts',[])):
        return None,'daily editorial slot already attempted'
    if any(p.get('status') in ('reserved','unknown') for p in state.get('posts',[])):
        return None,'unresolved publication; inspect/reconcile before API preparation'
    api=api or Source(cfg,state,now);book=cache(state,now)
    try:
        if slot in LEAGUES:
            today=day_rows(api,book,now.date(),now)
            featured={p.get('topic') for p in state.get('posts',[]) if p.get('status') not in ('cancelled','rejected')}
            options=[m for m in today if m['league']==slot and m['status']=='Not started'
                     and aware(m['kickoff'])>now+timedelta(minutes=10) and f"feature:{m['id']}" not in featured]
            if not options:return None,'no distinct verified upcoming fixture for this slot'
            post=comparison(api,book,min(options,key=lambda m:(m['kickoff'],m['id'])),now)
        elif slot=='story':
            post=story(api,book,state,now)
            if post is None:return None,'no distinct completed match with verified incidents'
        else:
            day=now.date()-timedelta(days=1) if slot=='results' else now.date()
            rows=day_rows(api,book,day,now,refresh=slot in ('fixtures','evening'))
            final=slot!='fixtures'
            rows=[m for m in rows if (m['status'] in FINAL and m['score'] is not None and aware(m['kickoff'])<now) or not final]
            if slot=='evening':
                covered={i for p in state.get('posts',[]) if p.get('kind')=='editorial' and p.get('status') not in ('cancelled','rejected') for i in p.get('fixture_ids',[]) if p.get('topic','').startswith('results:')}
                rows=[m for m in rows if m['id'] not in covered]
            if not rows:return None,'no verified fixtures or new confirmed finals; no filler'
            title=f"{'Confirmed results' if final else 'Today’s fixtures'} | {day:%d %b %Y}"
            lines=[title]
            for league in LEAGUES:
                lines+=['',LEAGUES[league][0]]
                subset=sorted((m for m in rows if m['league']==league),key=lambda m:m['kickoff'])
                for m in subset:
                    value=f"{m['score'][0]}–{m['score'][1]} ({m['status']})" if final else f"{aware(m['kickoff']):%H:%M} SAST · {m['status']}"
                    lines.append(f"{m['home']} vs {m['away']} — {value}")
                if not subset:lines.append('No confirmed finals in this bulletin.' if final else 'No fixtures listed in the verified schedule.')
            lines+=['',hashtags() if final else hashtags().replace('#FootballResults','#FootballFixtures')]
            caption='\n'.join(lines)
            if len(caption)>12000:return None,'bulletin too long; editorial review required'
            post=content.candidate('editorial',slotkey,f"{'results' if final else 'fixtures'}:{day}:{slot}",caption,fixture_ids=[m['id'] for m in rows],snapshot=rows)
        post['slot_key']=slotkey
        return post,'verified scheduled editorial content'
    except ProviderError as error:
        return None,str(error)



def story(api,book,state,now):
    # Use yesterday's already-verified finals and fetch current incident details,
    # rather than paying for a fourth worldwide catalog scan. Date stays explicit.
    rows=day_rows(api,book,now.date()-timedelta(days=1),now)
    used={i for p in state.get('posts',[]) if p.get('status') not in ('cancelled','rejected') and
          (p.get('topic','').startswith('feature:') or p.get('topic','').startswith('story:')) for i in p.get('fixture_ids',[])}
    options=[m for m in rows if m['status'] in FINAL and m['score'] is not None and aware(m['kickoff'])<now and m['id'] not in used]
    if not options:return None
    m=max(options,key=lambda m:(m['kickoff'],m['id']))
    raw=api.raw_detail(m['id'])
    if fixture(raw)!=m:raise ProviderError('Recap list/detail conflict')
    events=raw.get('events')
    if not isinstance(events,list):return None
    goals=[];cards=[]
    for event in events:
        if not isinstance(event,dict):return None
        kind=event.get('type');clock=event.get('time')
        if kind not in ('Goal','Penalty','Red Card','Own Goal'):continue
        if kind=='Own Goal':return None  # Attribution must not be guessed.
        if not isinstance(clock,str) or not re.fullmatch(r'\d{1,3}(\+\d{1,2})?',clock):return None
        team_object=event.get('team')
        if not isinstance(team_object,dict):return None
        team=team_object.get('id')
        if type(team) is not int or team not in (m['home_id'],m['away_id']):return None
        item=(team,clock,kind)
        if item in goals+cards:return None
        (cards if kind=='Red Card' else goals).append(item)
    if [sum(g[0]==tid for g in goals) for tid in (m['home_id'],m['away_id'])]!=m['score']:return None
    facts=[]
    for tid,clock,kind in (goals+cards)[:3]:
        name=m['home'] if tid==m['home_id'] else m['away']
        facts.append(f"{clock}': {name} — {'red card' if kind=='Red Card' else 'goal'}.")
    if not facts:return None
    caption=f"{m['home']} {m['score'][0]}–{m['score'][1]} {m['away']} | {m['status']}\n{LEAGUES[m['league']][0]} · {aware(m['kickoff']):%d %b %Y}\n\n"+'\n'.join('• '+f for f in facts)
    caption+=f"\n\nSelected verified incidents, not a complete commentary.\nWhich moment stood out?\n\n"+hashtags(m['league'],(m['home'],m['away']))
    return content.candidate('editorial',f"story:{m['id']}",f"story:{m['id']}",caption,fixture_ids=[m['id']],snapshot=[m])
