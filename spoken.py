"""Spoken-English helpers: numbers, scores, times and lists the way a presenter actually says them.

Pure functions with no I/O. Everything the narration says aloud goes through here, so the voice never reads a
stats table ("1.44 scored and 1.11 conceded") and the same script reads naturally in any voice.

Rules of thumb baked in:
  - Small counts are words ("four of their last five"), scores are football scores ("three-two", "two-all").
  - Per-game rates and percentages are rounded to what a person would say ("nearly two a game",
    "better than four in five") and never to two decimals.
  - Only betting odds keep digits ("1.24"), because that is how odds are spoken.
"""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from typing import Iterable, Sequence

_ONES = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth",
        10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
        16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth"}


def words(n) -> str:
    """0-999 as words ("twenty-two"); anything else is returned as digits."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n < 0:
        return "minus " + words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + (f"-{_ONES[o]}" if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{_ONES[h]} hundred" + (f" and {words(r)}" if r else "")
    return str(n)


def ordinal(n) -> str:
    """1 -> first ... 99 -> ninety-ninth."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n in _ORD:
        return _ORD[n]
    if 20 < n < 100:
        t, o = divmod(n, 10)
        return (_TENS[t][:-1] + "ieth") if o == 0 else f"{_TENS[t]}-{_ORD[o]}"
    return f"{n}th"


_FOLD = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L",
                       "œ": "oe", "Œ": "OE", "ð": "d", "þ": "th", "ı": "i"})


def ascii_fold(text) -> str:
    """Accents removed so a text-to-speech voice never trips on them (Casadó -> Casado)."""
    s = str(text or "").translate(_FOLD)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


# --------------------------------------------------------------------------- names

_SAY_MAP = {
    "Deportivo A Coruna": "Deportivo La Coruna", "Borussia M'gladbach": "Gladbach", "Borussia Monchengladbach": "Gladbach",
    "Wolverhampton Wanderers": "Wolves", "Turkiye": "Turkey", "FC Cologne": "Cologne", "1. FC Koln": "Cologne",
    "Willem II": "Willem Two", "Minnesota United": "Minnesota", "Atletico MG": "Atletico Mineiro",
    "Eintracht Frankfurt": "Frankfurt", "Borussia Dortmund": "Dortmund", "RB Leipzig": "Leipzig", "AS Monaco": "Monaco",
    "AC Milan": "Milan", "Paris Saint-Germain": "PSG", "Paris SG": "PSG", "PSV Eindhoven": "PSV", "Charlton Athletic": "Charlton",
    "Bolton Wanderers": "Bolton", "Bayern Munich": "Bayern", "Manchester United": "Man United", "Manchester City": "Man City",
    "Tottenham Hotspur": "Spurs", "Newcastle United": "Newcastle", "West Ham United": "West Ham", "Leeds United": "Leeds",
    "Brighton & Hove Albion": "Brighton", "West Bromwich Albion": "West Brom", "Atletico Madrid": "Atletico Madrid",
}
_COUNTRY = {"Netherlands": "Holland", "USA": "America", "Turkiye": "Turkey", "United States": "America",
            "Korea Republic": "South Korea"}


def team(name) -> str:
    """How a presenter says a club name: no FC/SC, abbreviations expanded, accents folded."""
    n = str(name or "").strip()
    n = _SAY_MAP.get(n, n)
    n = re.sub(r"^(1\.\s*)?(FC|SC|SV|AFC|CF)\s+", "", n)
    n = _SAY_MAP.get(n, n)
    n = n.replace("/", " ")
    n = re.sub(r"\s+(BK|FK|IF|SK|IK|FF|AIK|BoIS|SC)$", "", n)          # Scandinavian club suffixes are never said aloud
    n = re.sub(r"\s+0?\d{2}$", "", n)                                   # "Sarpsborg 08", "Schalke 04", "Mainz 05"
    n = re.sub(r"(?<=[bdgklmnprstv])oe(?=\b|\s)", "o", n)                 # Bodoe -> Bodo, Tromsoe -> Tromso
    n = re.sub(r"\bLillestroem\b", "Lillestrom", n)
    n = re.sub(r"\bUtd\b\.?", "United", n)
    n = re.sub(r"\bSt\.?\s*(?=[A-Z])", "Saint ", n)
    n = re.sub(r"\bTurkiye\b", "Turkey", n)
    return ascii_fold(n).strip()


def country(name) -> str:
    n = str(name or "").strip()
    return _COUNTRY.get(n, n)


def possessive(name: str) -> str:
    n = str(name or "")
    return f"{n}'" if n.endswith("s") else f"{n}'s"


# --------------------------------------------------------------------------- numbers

def score(a, b) -> str:
    """A result as football people say it: three-two, two-nil, one-all, nil-nil (winner's goals first)."""
    a, b = int(a), int(b)
    if a == b:
        return "nil-nil" if a == 0 else f"{words(a)}-all"
    hi, lo = max(a, b), min(a, b)
    return f"{words(hi)}-{'nil' if lo == 0 else words(lo)}"


_PER_GAME = (
    (0.45, ("well under one",)),
    (0.80, ("under one", "less than one")),
    (0.95, ("just under one", "a shade under one")),
    (1.10, ("about one", "roughly one")),
    (1.30, ("just over one", "a touch over one")),
    (1.40, ("one and a bit",)),
    (1.60, ("about one and a half", "one and a half")),
    (1.70, ("a touch over one and a half",)),
    (1.90, ("getting on for two", "nearly two")),
    (2.10, ("about two", "around two")),
    (2.30, ("just over two", "a touch over two")),
    (2.40, ("well over two",)),
    (2.60, ("two and a half", "about two and a half")),
    (2.90, ("nearly three", "getting on for three")),
    (3.10, ("about three",)),
    (3.40, ("over three",)),
    (3.60, ("three and a half",)),
    (3.90, ("nearly four",)),
    (4.10, ("about four",)),
    (4.40, ("over four",)),
    (4.60, ("four and a half",)),
    (4.90, ("nearly five",)),
    (5.10, ("about five",)),
    (99.0, ("over five",)),
)


def per_game(x, ch: "Chooser | None" = None) -> str:
    """A goals-per-game average as words: 1.75 -> "nearly two". Completes "... a game"."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return ""
    for top, opts in _PER_GAME:
        if v < top:
            return ch.pick("pg:" + opts[0], opts) if ch else opts[0]
    return "over five"


_RATES = (
    (0.97, "almost every one"), (0.90, "nine in ten"), (0.82, "better than four in five"), (0.76, "about four in five"),
    (0.70, "about three in four"), (0.62, "roughly two in three"), (0.55, "more than half"), (0.45, "about half"),
    (0.30, "roughly a third"), (0.0, "a handful"),
)


def rate(p) -> str:
    """A share between 0 and 1 as a spoken fraction: 0.84 -> "better than four in five"."""
    try:
        v = float(p)
    except (TypeError, ValueError):
        return ""
    for lo, text in _RATES:
        if v >= lo:
            return text
    return "a handful"


def of_last(k: int, n: int) -> str:
    """"all of their last five", "four of their last five", "every one of their last ten"."""
    k, n = int(k), int(n)
    if n >= 6 and k == n:
        return f"every one of their last {words(n)}"
    if k == n:
        return f"all of their last {words(n)}"
    return f"{words(k)} of their last {words(n)}"


def count_word(n: int, single: str, plural: str | None = None) -> str:
    plural = plural or single + "s"
    return f"{words(n)} {single if int(n) == 1 else plural}"


def half_line(text: str) -> str:
    """Betting lines in words: "1.5" -> "one and a half", "9.5" -> "nine and a half", "0.5" -> "nought point five"."""
    def sub(m: re.Match) -> str:
        n = int(m.group(1))
        return "nought point five" if n == 0 else f"{words(n)} and a half"
    return re.sub(r"\b(\d{1,2})\.5\b", sub, str(text or ""))


# --------------------------------------------------------------------------- time

def _hm(hhmm) -> tuple[int, int] | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(hhmm or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def clock(hhmm) -> str:
    """"20:45" -> "quarter to nine", "21:00" -> "nine o'clock"."""
    t = _hm(hhmm)
    if not t:
        return ""
    h, m = t
    h12 = h % 12 or 12
    nxt = (h + 1) % 12 or 12
    if h == 0 and m == 0:
        return "midnight"
    table = {0: f"{words(h12)} o'clock", 5: f"five past {words(h12)}", 10: f"ten past {words(h12)}",
             15: f"quarter past {words(h12)}", 20: f"twenty past {words(h12)}", 25: f"twenty-five past {words(h12)}",
             30: f"half past {words(h12)}", 35: f"twenty-five to {words(nxt)}", 40: f"twenty to {words(nxt)}",
             45: f"quarter to {words(nxt)}", 50: f"ten to {words(nxt)}", 55: f"five to {words(nxt)}"}
    return table.get(m, f"{words(h12)} {'oh ' + words(m) if m < 10 else words(m)}")


def daypart(hhmm) -> str:
    t = _hm(hhmm)
    if not t:
        return ""
    h = t[0]
    if h < 5:
        return "in the early hours"
    if h < 12:
        return "this morning"
    if h < 17:
        return "this afternoon"
    return "tonight"


def kickoff(hhmm, *, with_daypart: bool = True) -> str:
    """"at quarter to nine tonight", "at half past three this afternoon", "at nine tonight"."""
    t = _hm(hhmm)
    if not t:
        return ""
    h, m = t
    dp = daypart(hhmm) if with_daypart else ""
    if m == 0 and dp:
        return f"at {words(h % 12 or 12)} {dp}"
    return f"at {clock(hhmm)}" + (f" {dp}" if dp else "")


def all_evening(kickoffs: Iterable[str]) -> bool:
    hs = [t[0] for t in (_hm(k) for k in kickoffs) if t]
    return bool(hs) and min(hs) >= 17


# --------------------------------------------------------------------------- lists

def join_list(items: Sequence[str], conj: str = "and") -> str:
    items = [str(i) for i in items if str(i).strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {conj} " + items[-1]


def names(items: Sequence[str], limit: int = 3) -> str:
    """"Aubameyang, Casado and Eddahchouri" - or "A, B, C and two others" when the list is long."""
    items = [ascii_fold(i).strip() for i in items if str(i).strip()]
    if len(items) <= limit:
        return join_list(items)
    extra = len(items) - limit
    return join_list(items[:limit] + [f"{words(extra)} other{'s' if extra != 1 else ''}"])


def cap(text: str) -> str:
    t = str(text or "")
    return t[:1].upper() + t[1:]


def month_year(date_str) -> str:
    from datetime import datetime
    try:
        return datetime.strptime(str(date_str)[:10], "%Y-%m-%d").strftime("%B %Y")
    except ValueError:
        return ""


# --------------------------------------------------------------------------- variety

def seed_for(*parts) -> int:
    """A stable integer from any parts, so a given day's script is reproducible but changes from day to day."""
    return int(hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12], 16)


class Chooser:
    """Seeded variety: picks a phrase variant and never repeats the same one twice in a row for a key."""

    def __init__(self, seed=0):
        self.rnd = random.Random(seed)
        self._last: dict[str, str] = {}

    def pick(self, key: str, options: Sequence[str]) -> str:
        opts = [o for o in options if o != self._last.get(key)] or list(options)
        choice = self.rnd.choice(opts)
        self._last[key] = choice
        return choice

    def chance(self, p: float) -> bool:
        return self.rnd.random() < p


# --------------------------------------------------------------------------- competitions and markets

_THE_LEAGUES = {"bundesliga", "second bundesliga", "eredivisie", "championship", "premier league", "primeira liga", "super lig",
                "premiership", "eliteserien", "allsvenskan", "superliga", "super league", "pro league", "league one",
                "league two", "eerste divisie", "segunda division", "scottish premiership"}
_COMPETITION = re.compile(r"champions league|europa league|conference league|nations league|world cup|\bcup\b|copa|euro\b", re.I)


def league_name(league) -> str:
    """League as said aloud: accents folded, digits in words ("Ligue 1" -> "Ligue One", "2. Bundesliga" -> "second Bundesliga")."""
    from shortlist_reel import spoken_text
    name = ascii_fold(spoken_text(str(league or "").strip()))
    name = re.sub(r"\b(\d)\.\s*(Bundesliga|Liga)\b", lambda m: f"{ordinal(int(m.group(1)))} {m.group(2)}", name)
    return re.sub(r"\b(\d)\b", lambda m: cap(words(int(m.group(1)))), name)


def the_league(league: str) -> str:
    return "the " if league.lower() in _THE_LEAGUES else ""


def competition(country_name, league, ch: "Chooser | None" = None) -> str:
    """"Germany's Bundesliga" / "the Bundesliga in Germany" / "the Europa League, league stage"."""
    c, lg = country(country_name), league_name(league)
    if not c or c.lower() == lg.lower():
        return f"{the_league(lg)}{lg}"
    if _COMPETITION.search(c):                      # the "country" of a European tie is the competition itself
        stage = f", {lg.lower()}" if lg else ""
        return f"{'' if c.lower().startswith('the ') else 'the '}{c}{stage}"
    forms = [f"{possessive(c)} {lg}", f"{the_league(lg)}{lg} in {c}"]
    return ch.pick("place", forms) if ch else forms[0]


_TEAM_OVER = re.compile(r"^(.+?)\s+over\s+(0|1)\.5\s+goals$", re.I)


def market_phrase(label, home=None, away=None) -> str:
    """A betting label as the presenter says it: "Deportivo to score at least once", "over one and a half goals"."""
    from shortlist_reel import spoken_text
    lab = str(label or "the selection").strip()
    m = _TEAM_OVER.match(lab)
    if m:
        who = m.group(1).strip().lower()
        for nm in (home, away):
            if nm and who == str(nm).strip().lower():
                return f"{team(nm)} to score at least once" if m.group(2) == "0" else f"{team(nm)} to score two or more"
    low = lab.lower()
    if re.search(r"both teams to score|btts", low) and "no" not in low.split():
        return "both teams to score"
    return half_line(ascii_fold(spoken_text(lab))).replace("Over ", "over ", 1)
