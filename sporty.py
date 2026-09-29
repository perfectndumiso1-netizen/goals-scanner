"""Sportybet prices (public JSON used by the Sportybet web app). Display / payout information only —
these prices are never fed into the probability model. Fails soft: any error returns nothing and the
scanner falls back to the football-data.co.uk average prices."""
from __future__ import annotations

import difflib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import unicodedata
from datetime import datetime, timezone

import requests

log = logging.getLogger("sporty")

CC = os.getenv("SPORTY_CC", "za")            # country site: za, ng, gh, ke, ug, tz, zm
BASE = f"https://www.sportybet.com/api/{CC}/factsCenter"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
LIST_MARKETS = "1,10,18,29,19,20"            # 1X2, double chance, totals, BTTS, home/away team totals
TIMEOUT = 20
MAX_PAGES = 40

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json", "Accept-Language": "en"})

# Sportybet sits behind AWS WAF bot control. Python's HTTP/1.1 client gets a JavaScript challenge
# (HTTP 202, x-amzn-waf-action: challenge) from cloud IPs such as GitHub's runners, while curl over
# HTTP/2 is served normally from the same machine. So: curl first, requests as a fallback.
CURL = shutil.which("curl")
_TRANSPORT = {"mode": "curl" if CURL else "requests"}


def _fetch_curl(url: str) -> tuple[int, str]:
    cmd = [CURL, "-s", "--http2", "-m", str(TIMEOUT), "-A", UA, "-H", "Accept: application/json",
           "-H", "Accept-Language: en", "-w", "\n%{http_code}", url]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 10).stdout
    body, _, code = out.rpartition("\n")
    return int(code or 0), body


def _fetch_requests(url: str) -> tuple[int, str]:
    r = SESSION.get(url, timeout=TIMEOUT)
    return r.status_code, r.text


def _get(url: str) -> dict | None:
    try:
        if _TRANSPORT["mode"] == "curl":
            try:
                code, body = _fetch_curl(url)
            except (OSError, subprocess.SubprocessError, ValueError) as exc:
                log.warning("Sportybet curl failed (%s) - switching to requests", exc)
                _TRANSPORT["mode"] = "requests"
                code, body = _fetch_requests(url)
        else:
            code, body = _fetch_requests(url)
        if code == 202 and _TRANSPORT["mode"] == "requests" and CURL:
            # WAF challenge on the plain client: retry once through curl and stay there
            _TRANSPORT["mode"] = "curl"
            code, body = _fetch_curl(url)
        if code != 200:
            log.warning("Sportybet HTTP %s for %s", code, url[:120])
            return None
        d = json.loads(body)
        if d.get("bizCode") not in (10000, None):
            log.warning("Sportybet bizCode %s: %s", d.get("bizCode"), str(d.get("message"))[:100])
            return None
        return d.get("data") or {}
    except (requests.RequestException, ValueError, subprocess.SubprocessError, OSError) as exc:
        log.warning("Sportybet request failed: %s", exc)
        return None


def _f(x) -> float | None:
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_markets(markets: list) -> dict:
    """Normalise Sportybet market objects into a small dict of prices."""
    out: dict = {}
    for m in markets or []:
        mid = str(m.get("id"))
        spec = m.get("specifier") or ""
        outs = {o.get("desc", ""): _f(o.get("odds")) for o in m.get("outcomes", []) if o.get("isActive", 1) == 1}
        if not outs or m.get("status", 0) not in (0, None):
            continue
        line = None
        mt = re.search(r"total=([\d.]+)", spec)
        if mt:
            line = float(mt.group(1))
        if mid == "1":
            out["1X2"] = (outs.get("Home"), outs.get("Draw"), outs.get("Away"))
        elif mid == "10":
            out["DC"] = {"1X": outs.get("Home or Draw"), "12": outs.get("Home or Away"), "X2": outs.get("Draw or Away")}
        elif mid == "29":
            out["BTTS"] = (outs.get("Yes"), outs.get("No"))
        elif mid in ("18", "19", "20", "166", "900300", "900301", "177", "139", "900304", "900305") and line is not None:
            key = {"18": "OU", "19": "TGH", "20": "TGA", "166": "CORN", "900300": "CORNH", "900301": "CORNA",
                   "177": "CORN1H", "139": "CARDS", "900304": "CARDSH", "900305": "CARDSA"}[mid]
            over = next((v for k, v in outs.items() if k.startswith("Over")), None)
            under = next((v for k, v in outs.items() if k.startswith("Under")), None)
            if over or under:
                out.setdefault(key, {})[line] = (over, under)
    return out


def fetch_upcoming(hours_ahead: float = 48) -> list[dict]:
    """All upcoming football events with the main markets. ~20 requests, ~20 s."""
    t0 = time.time()
    events: list[dict] = []
    horizon = time.time() + hours_ahead * 3600
    for page in range(1, MAX_PAGES + 1):
        data = _get(f"{BASE}/pcUpcomingEvents?sportId=sr%3Asport%3A1&marketId={LIST_MARKETS.replace(',', '%2C')}"
                    f"&pageSize=100&pageNum={page}&option=1")
        if data is None:
            if page == 1:
                return []
            break
        tours = data.get("tournaments") or []
        n = 0
        for t in tours:
            for e in t.get("events", []):
                n += 1
                ko = e.get("estimateStartTime")
                if not ko or ko / 1000 > horizon:
                    continue
                events.append({
                    "id": e.get("eventId"), "ko": datetime.fromtimestamp(ko / 1000, tz=timezone.utc),
                    "country": t.get("categoryName") or e.get("sport", {}).get("category", {}).get("name", ""),
                    "tournament": t.get("name", ""), "home": e.get("homeTeamName", ""), "away": e.get("awayTeamName", ""),
                    "markets": _parse_markets(e.get("markets")),
                })
        if n == 0:
            break
    log.info("Sportybet (%s): %d upcoming events within %.0fh in %.1fs", CC, len(events), hours_ahead, time.time() - t0)
    return events


def fetch_event_markets(event_id: str) -> dict:
    """Full market list for one event (corners, cards, team totals ...)."""
    data = _get(f"{BASE}/event?eventId={event_id}&productId=3")
    if not data:
        return {}
    return _parse_markets(data.get("markets"))


def _slug(s) -> str:
    """Path segment of a Sportybet name (their router uses lowercase with symbols as underscores)."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def event_url(ev: dict | None) -> str | None:
    """Public Sportybet page of one event — the 'open in Sportybet' deep link (no login needed to view).

    Route format (from the Sportybet web router): /sport/:sportKey/:categoryName/:tournamentName/:homeVsAway?/:eventId/
    """
    if not ev or not ev.get("id"):
        return None
    cat = _slug(ev.get("country") or "football")
    tour = _slug(ev.get("tournament") or "football")
    home_vs_away = f"{_slug(ev.get('home'))}_v_{_slug(ev.get('away'))}" if ev.get("home") and ev.get("away") else ""
    return (f"https://www.sportybet.com/{CC}/sport/sr:sport:1/{cat}/{tour}/{home_vs_away}/{ev['id']}/")


def share_url(code: str) -> str:
    """Sportybet booking-code share link: opens in the Sportybet app/site and loads the slip."""
    c = re.sub(r"[^A-Za-z0-9]", "", str(code or ""))
    return f"https://www.sportybet.com/{CC}/?shareCode={c}" if c else None


# ----------------------------------------------------------------------------- matching to football-data fixtures
STOP = set("fc afc cf sc ac as us ss ssc calcio club de cd ud sd rcd fk sk bk if ff ik sv vfb vfl tsg fsv spvgg "
           "1 04 05 1899 1900 1904 1909 1910 the and of ca cs csd cfr kf ks nk hk gks mks rks lks zks sp spa".split())
SHORT = {"utd": "united", "rvs": "rovers", "ath": "athletic", "wed": "wednesday"}
# tokens that mark reserve / youth / women sides: never the same club as the first team
RESERVE = {"b", "ii", "2", "u19", "u21", "u23", "women", "w", "reserves", "youth"}
# same-stem clubs that are different teams (football-data short name vs the other club)
NEVER = {("dundee", "dundee united"), ("celta vigo", "celta fortuna")}
SUFFIX = {"united", "city", "rovers", "wanderers", "town", "county", "athletic", "wednesday", "albion", "forest"}

# football-data.co.uk short names -> long names as bookmakers list them
ALIAS = {
    "man united": "manchester united", "man city": "manchester city", "nott'm forest": "nottingham forest",
    "sheffield weds": "sheffield wednesday", "peterboro": "peterborough", "middlesboro": "middlesbrough",
    "wolves": "wolverhampton wanderers", "spurs": "tottenham hotspur", "qpr": "queens park rangers",
    "milton keynes dons": "mk dons", "bristol rvs": "bristol rovers", "inverness c": "inverness ct",
    "inter": "inter milano", "ath madrid": "atletico madrid", "ath bilbao": "athletic bilbao",
    "sociedad": "real sociedad", "espanol": "espanyol", "betis": "real betis", "vallecano": "rayo vallecano",
    "celta": "celta vigo", "celta b": "celta fortuna", "sociedad b": "real sociedad b", "barcelona b": "barcelona atletic",
    "sp gijon": "sporting gijon", "sp lisbon": "sporting cp", "guimaraes": "vitoria guimaraes",
    "ein frankfurt": "eintracht frankfurt", "m'gladbach": "borussia monchengladbach", "leverkusen": "bayer leverkusen",
    "dortmund": "borussia dortmund", "hertha": "hertha berlin", "st pauli": "st. pauli", "fc koln": "1. fc koln",
    "paris sg": "paris saint-germain", "st etienne": "saint-etienne", "marseille": "olympique marseille",
    "lyon": "olympique lyonnais", "psv eindhoven": "psv", "for sittard": "fortuna sittard", "nijmegen": "nec nijmegen",
    "hearts": "heart of midlothian", "st johnstone": "st. johnstone", "st mirren": "st. mirren",
    "waregem": "zulte waregem", "st truiden": "sint-truiden", "club brugge": "club brugge kv",
    "standard": "standard liege", "buyuksehyr": "istanbul basaksehir", "ad alcorcon": "alcorcon",
    "atl. san luis": "atletico san luis", "unam pumas": "pumas unam", "boston utd": "boston united",
    "fylde": "afc fylde", "st. louis city": "saint louis city", "ajax": "ajax amsterdam",
    "ferencvaros": "ferencvarosi tc", "brann": "sk brann", "bodo/glimt": "bodo/glimt",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    s = ALIAS.get(s, s)
    s = s.replace("&", " and ").replace("-", " ").replace("'", "").replace(".", " ").replace("/", " ")
    toks = [SHORT.get(t, t) for t in re.split(r"[^a-z0-9]+", s) if t and t not in STOP]
    return " ".join(toks) or s




def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if a == b:
        return 1.0
    if (a, b) in NEVER or (b, a) in NEVER:
        return 0.0
    ta, tb = set(a.split()), set(b.split())
    if (ta & RESERVE) != (tb & RESERVE):
        return 0.0
    if ta and tb and (ta <= tb or tb <= ta):
        return 0.9
    la, lb = a.split()[-1], b.split()[-1]
    if la != lb and la in SUFFIX and lb in SUFFIX:      # Manchester United vs Manchester City
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_fixtures(fixtures, events: list[dict], min_sim: float = 0.72, tol_min: int = 20) -> dict:
    """Map fixture index -> Sportybet event, using kick-off time (±tol) and both team names."""
    out = {}
    if fixtures is None or fixtures.empty or not events:
        return out
    by_time = sorted(events, key=lambda e: e["ko"])
    kos = [e["ko"].timestamp() for e in by_time]
    import bisect
    for idx, f in fixtures.iterrows():
        ko = f["kickoff"].timestamp()
        lo = bisect.bisect_left(kos, ko - tol_min * 60)
        hi = bisect.bisect_right(kos, ko + tol_min * 60)
        best, bs = None, 0.0
        for e in by_time[lo:hi]:
            s = min(similarity(f["home"], e["home"]), similarity(f["away"], e["away"]))
            if s > bs:
                bs, best = s, e
        if best is not None and bs >= min_sim:
            out[idx] = best
    log.info("Sportybet: matched %d of %d fixtures", len(out), len(fixtures))
    return out


if __name__ == "__main__":  # quick manual check
    logging.basicConfig(level=logging.INFO)
    evs = fetch_upcoming(24)
    print(len(evs), "events")
    for e in evs[:5]:
        print(e["ko"], e["country"], e["tournament"], e["home"], "v", e["away"], json.dumps(e["markets"])[:200])
