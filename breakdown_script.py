"""Natural, spoken-first narration for the daily match breakdown.

The old templates read the data back ("1.44 scored and 1.11 conceded per game, with over 1.5 goals in 84% of those
games"). This module writes what a knowledgeable friend would actually say: rounded numbers, football scores, varied
sentence shapes and no stat soup. Nothing here invents a fact: every sentence is built from a field in the match
dossier (or from sourced extras supplied by the caller), and unknown data simply produces no sentence.

Data-integrity rule: the same match can sit twice in a team's history when two result feeds spell a club differently
("Heerenveen" / "SC Heerenveen"). Every count used here is taken from de-duplicated matches, and streak claims that the
dossier computed upstream are not used for a team whose history shows repeats.
"""
from __future__ import annotations

import re

import spoken as sp

# ---------------------------------------------------------------------------- data access (de-duplicated)

def distinct(rows, keys=("date", "venue", "gf", "ga")) -> list[dict]:
    seen, out = set(), []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        k = tuple(r.get(x) for x in keys)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _team_block(dos: dict, side: str) -> dict:
    return ((dos.get("teams") or {}).get(side)) or {}


def _norm(x) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x or "").lower())


def _numeric_rows(dos: dict, side: str) -> list[dict]:
    return [m for m in (_team_block(dos, side).get("last5") or [])
            if isinstance(m, dict) and isinstance(m.get("gf"), (int, float)) and isinstance(m.get("ga"), (int, float))]


def last_results(dos: dict, side: str) -> list[dict]:
    """Newest-first distinct results. League games only when there are at least three of them, otherwise all we have."""
    rows = distinct(_numeric_rows(dos, side))
    same = [m for m in rows if _norm(m.get("league")) == _norm(dos.get("league"))]
    return same if len(same) >= 3 else rows


def is_league_form(dos: dict, side: str) -> bool:
    """True when every result in the form list is from the fixture's own league (so "league games" is the truth)."""
    rows = last_results(dos, side)
    return bool(rows) and all(_norm(m.get("league")) == _norm(dos.get("league")) for m in rows)


_FATIGUE = re.compile(r"last match (\d{4}-\d{2}-\d{2}), (\d+) day\(s\) before kick-off; (\d+) match\(es\) in the last 7 days "
                      r"\(last (\d+)-(\d+) v (.+?) · (.+?)\)")
_EUROPE = re.compile(r"champions league|europa league|conference league", re.I)
_CUP = re.compile(r"cup|pokal|copa|coupe|coppa|trophy|beker|cupen|supercopa|super cup", re.I)


def last_game(dos: dict, side: str) -> dict | None:
    """The team's most recent match of any competition, from the fatigue facts (the form list leaves European games out)."""
    for f in ((dos.get("context") or {}).get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "fatigue" and not f.get("stale") and f.get("subject") == dos.get(side):
            m = _FATIGUE.search(str(f.get("text") or ""))
            if m:
                c1, c2 = m.group(6).strip(), m.group(7).strip()
                comp = c1 if _EUROPE.search(c1) else c2 if _CUP.search(c2) else c1 if _CUP.search(c1) else ""
                return {"date": m.group(1), "days": int(m.group(2)), "gf": int(m.group(4)), "ga": int(m.group(5)),
                        "comp": comp, "european": bool(_EUROPE.search(c1)), "cup": bool(comp) and not _EUROPE.search(c1)}
    return None


def incomplete(dos: dict, side: str) -> bool:
    """True when the team has played a non-league match since its newest form-list result (a European or cup night)."""
    g, rows = last_game(dos, side), last_results(dos, side)
    return bool(g and g["comp"] and rows and g["date"] > str(rows[0].get("date") or ""))


def suspect_history(dos: dict, side: str) -> bool:
    """True when this team's results show repeated matches (or a history long enough to be double counted)."""
    t = _team_block(dos, side)
    raw = [m for m in (t.get("last5") or []) if isinstance(m, dict)]
    repeated = len(distinct(raw)) < len(raw)
    return repeated or int(t.get("n") or 0) >= 55


def meetings(dos: dict) -> list[dict]:
    rows = [m for m in (dos.get("h2h") or []) if isinstance(m, dict) and isinstance(m.get("hg"), (int, float))
            and isinstance(m.get("ag"), (int, float))]
    return distinct(rows, keys=("date", "hg", "ag"))


def _letters(rows: list[dict]) -> str:
    return "".join("W" if m["gf"] > m["ga"] else "D" if m["gf"] == m["ga"] else "L" for m in rows)


def _lead(letters: str, pred) -> int:
    k = 0
    for c in letters:
        if not pred(c):
            break
        k += 1
    return k


# ---------------------------------------------------------------------------- names, places, markets

def league_name(league) -> str:
    return sp.league_name(league)


def place(dos: dict, ch: sp.Chooser) -> str:
    """"Germany's Bundesliga" / "the Bundesliga in Germany"."""
    return sp.competition(dos.get("country"), dos.get("league"), ch)


def spoken_market(best: dict, dos: dict) -> str:
    """The pick as it is said: "Deportivo to score at least once", "over one and a half goals"."""
    return sp.market_phrase(best.get("label"), dos.get("home"), dos.get("away"))


def pick_side(best: dict, dos: dict) -> str | None:
    m = re.match(r"^(.+?)\s+over\s+(?:0|1)\.5\s+goals$", str(best.get("label") or "").strip(), re.I)
    if not m:
        return None
    who = m.group(1).strip().lower()
    for side in ("home", "away"):
        if who == str(dos.get(side) or "").strip().lower():
            return side
    return None


# ---------------------------------------------------------------------------- results and form

def result_phrase(m: dict, ch: sp.Chooser) -> str:
    """Past-tense clause: "beat Elversberg one-nil at home", "lost three-one at PSG", "drew two-all at Monaco"."""
    opp = sp.team(m.get("opp") or "their opponents")
    gf, ga = int(m["gf"]), int(m["ga"])
    home = m.get("venue") == "H"
    sc = sp.score(gf, ga)
    margin = abs(gf - ga)
    if gf > ga:
        if home:
            opts = [f"hammered {opp} {sc} at home", f"thrashed {opp} {sc} at home"] if margin >= 3 else \
                   [f"beat {opp} {sc} at home", f"saw off {opp} {sc} at home", f"got past {opp} {sc} at home"]
        else:
            opts = [f"hammered {opp} {sc} away from home"] if margin >= 3 else \
                   [f"won {sc} away at {opp}", f"won {sc} at {opp}"]
    elif gf == ga:
        opts = [f"drew {sc} at home to {opp}", f"were held {sc} at home by {opp}"] if home else \
               [f"drew {sc} away at {opp}", f"were held {sc} at {opp}"]
    else:
        if home:
            opts = [f"were hammered {sc} at home by {opp}", f"were well beaten {sc} at home by {opp}"] if margin >= 3 else \
                   [f"lost {sc} at home to {opp}", f"were beaten {sc} at home by {opp}"]
        else:
            opts = [f"were hammered {sc} at {opp}"] if margin >= 3 else [f"lost {sc} at {opp}", f"went down {sc} at {opp}"]
    return ch.pick("result", opts)


def _art(word: str) -> str:
    w = word.lower()
    return "an" if w[:1] in "aeiou" and not w.startswith(("one", "uni", "use")) else "a"


def latest_noun(m: dict) -> str:
    opp = sp.team(m.get("opp") or "their opponents")
    sc = sp.score(int(m["gf"]), int(m["ga"]))
    home = m.get("venue") == "H"
    kind = "win" if m["gf"] > m["ga"] else "draw" if m["gf"] == m["ga"] else "defeat"
    return f"{_art(sc)} {sc} {kind} {'at home to' if home else 'away at'} {opp}"


def form_unit(name: str, rows: list[dict], ch: sp.Chooser, *, prefix: str = "", league: bool = True, short: bool = False) -> str | None:
    """One or two sentences on how a side has been getting on, from at least three distinct results.

    Everything is scoped to "league games" when the list is league-only, because a European or cup night may sit
    between two league results and "last time out" would then be wrong."""
    n = len(rows)
    if n < 3:
        return None
    T = sp.team(name)
    G = "league games" if league else "games"
    lt = _letters(rows)
    wins, losses = lt.count("W"), lt.count("L")
    win_run, loss_run = _lead(lt, lambda c: c == "W"), _lead(lt, lambda c: c == "L")
    unbeaten, winless = _lead(lt, lambda c: c != "L"), _lead(lt, lambda c: c != "W")
    last = rows[0]
    margin = abs(last["gf"] - last["ga"])
    run_form = False
    w = sp.words
    if win_run >= 3:
        lead = ch.pick("form:win3", [f"{T} have won their last {w(win_run)} {G}", f"{T} are on a run of {w(win_run)} straight {'league ' if league else ''}wins"])
        run_form = True
    elif win_run == 2:
        lead = ch.pick("form:win2", [f"{T} have won their last two {G}", f"{T} come in off the back of two {'league ' if league else ''}wins"])
        run_form = True
    elif unbeaten >= 4:
        lead = ch.pick("form:unb", [f"{T} are unbeaten in their last {w(unbeaten)} {G}", f"{T} haven't lost in {w(unbeaten)} {G}"])
        run_form = True
    elif loss_run >= 3:
        lead = ch.pick("form:loss3", [f"{T} have lost their last {w(loss_run)} {G}", f"{T} are on a run of {w(loss_run)} {'league ' if league else ''}defeats"])
        run_form = True
    elif loss_run == 2:
        lead = ch.pick("form:loss2", [f"{T} have lost their last two {G}", f"{T} come in on the back of two {'league ' if league else ''}defeats"])
        run_form = True
    elif winless >= 3:
        lead = ch.pick("form:winless", [f"{T} haven't won in their last {w(winless)} {G}", f"{T} are winless in {w(winless)} {G}"])
        run_form = True
    elif wins == 0:
        lead = f"{T} haven't won any of their last {w(n)} {G}"
    elif wins == n - 1 and losses == 0:
        lead = f"{T} haven't lost in their last {w(n)} {G}"
    else:
        lead = ch.pick("form:mixed", [f"{T} have {sp.count_word(wins, 'win')} from their last {w(n)} {G}",
                                       f"{T} have had a mixed run, with {sp.count_word(wins, 'win')} from their last {w(n)} {G}"])
    if short:
        text = lead + "."
    elif run_form and margin < 3:
        text = lead + ch.pick("form:tail_run", [f", the latest being {latest_noun(last)}", f", most recently {latest_noun(last)}"]) + "."
    elif league:
        tail = ch.pick("form:tail", [f", and in their last league game they {result_phrase(last, ch)}", f". In their last league game they {result_phrase(last, ch)}",
                                      f", and their last league game was {latest_noun(last)}"])
        text = f"{lead}{tail}."
    else:
        text = lead + "."
    return (prefix + " " + text) if prefix else text


def venue_unit(name: str, t: dict, where: str, ch: sp.Chooser) -> str | None:
    gf, ga = t.get("venue_gf"), t.get("venue_ga")
    if not isinstance(gf, (int, float)) or not isinstance(ga, (int, float)):
        return None
    pg = lambda x: sp.per_game(x, ch)  # noqa: E731
    place = "At home" if where == "home" else ch.pick("away_place", ["On the road", "Away from home"])
    if gf >= 1.5 and ga >= 1.5:
        return f"{place}, it's goals at both ends: they score {pg(gf)} a game and concede {pg(ga)}."
    if gf < 1.0 and ga >= 1.5:
        return f"{place} it's been tough going: they score {pg(gf)} a game and concede {pg(ga)}."
    if gf >= 1.9 and ga < 1.2:
        return f"{place}, they've been very good: {pg(gf)} scored a game and just {pg(ga)} conceded."
    if ga >= 1.7:
        return f"{place}, they've been letting in {pg(ga)} a game, and scoring {pg(gf)}."
    return ch.pick("venue", [f"{place}, they score {pg(gf)} a game and let in {pg(ga)}.",
                              f"{place}, it's {pg(gf)} scored and {pg(ga)} conceded a game."])


def trend_unit(dos: dict, side: str, ch: sp.Chooser) -> str | None:
    """A long streak straight from the dossier's trend list, only for a team whose history is clean and complete."""
    if suspect_history(dos, side) or incomplete(dos, side):
        return None
    T = sp.team(dos.get(side))
    tr = ((dos.get("trends") or {}).get(side)) or {}
    best = None
    for x in (tr.get("all") or []):
        t = str((x or {}).get("t") or "")
        m = re.search(r"scored in (\d+) consecutive matches", t)
        if m and int(m.group(1)) >= 6:
            best = max(best or (0, ""), (int(m.group(1)), f"{T} have scored in {sp.words(int(m.group(1)))} games in a row."))
        m = re.search(r"unbeaten in the last (\d+)", t)
        if m and int(m.group(1)) >= 6:
            best = max(best or (0, ""), (int(m.group(1)), f"{T} are unbeaten in their last {sp.words(int(m.group(1)))}."))
    return best[1] if best else None


# ---------------------------------------------------------------------------- slide A

_FIRST = ("First up, {p}.", "We start with {p}.", "Let's kick off with {p}.")
_MID = ("Next, {p}.", "Moving on to {p}.", "Then it's {p}.", "Now, {p}.", "After that, {p}.")
_LAST = ("And last up, {p}.", "Last one: {p}.", "And we finish with {p}.")
_HOST = ("host", "welcome", "are at home to")


def opener_unit(dos: dict, idx: int, total: int, ch: sp.Chooser, rot: int = 0) -> str:
    h, a = sp.team(dos.get("home")), sp.team(dos.get("away"))
    pool = _FIRST if idx == 1 else _LAST if idx == total else _MID
    lead = pool[(idx + rot) % len(pool)].format(p=place(dos, ch))
    ko = sp.kickoff(str(dos.get("kickoff") or "")[11:16])
    return f"{lead} {h} {ch.pick('host', _HOST)} {a} {ko}.".replace("  ", " ").replace(" .", ".")


def _positions(table: dict | None) -> dict:
    out = {}
    for side in ("home", "away"):
        m = re.match(r"^\s*(\d+)(?:st|nd|rd|th)\b", str((table or {}).get(side) or ""))
        if m:
            out[side] = int(m.group(1))
    return out


def _lead_only(name: str, rows: list[dict], league: bool) -> str | None:
    """The lead clause of a form sentence with no randomness consumed (used as the short wording)."""
    return form_unit(name, rows, sp.Chooser(0), league=league, short=True)


def a_units(dos: dict, idx: int, total: int, ch: sp.Chooser, table: dict | None = None, rot: int = 0) -> list[tuple]:
    h, a = dos.get("home"), dos.get("away")
    th, ta = _team_block(dos, "home"), _team_block(dos, "away")
    pos = _positions(table)
    items: list[tuple] = [(0, opener_unit(dos, idx, total, ch, rot))]
    anchors: list[int] = []
    rows_h, rows_a = last_results(dos, "home"), last_results(dos, "away")
    lg_h, lg_a = is_league_form(dos, "home"), is_league_form(dos, "away")
    fh = form_unit(h, rows_h, ch, league=lg_h)
    if fh:
        items.append((1.1, fh, (), _lead_only(h, rows_h, lg_h)))
        anchors.append(len(items) - 1)
    vh = venue_unit(h, th, "home", ch)
    if vh:
        items.append((2, vh))
        anchors.append(len(items) - 1)
    fa = form_unit(a, rows_a, ch, league=lg_a)
    if fa:
        link = ch.pick("meanwhile", ["Meanwhile,", "As for the visitors,", "On the other side,"])
        items.append((1.2, f"§{link}§ {fa}", tuple(anchors), (lambda t: f"§{link}§ {t}" if t else None)(_lead_only(a, rows_a, lg_a))))
    va = venue_unit(a, ta, "away", ch)
    if va:
        items.append((2.1, va))
    if "home" in pos and "away" in pos:
        gap = abs(pos["home"] - pos["away"])
        H, A = sp.team(h), sp.team(a)
        if gap >= 6:
            forms = [f"In the table, {H} are {sp.ordinal(pos['home'])} and {A} are {sp.ordinal(pos['away'])}."]
            if min(pos.values()) <= 3:
                forms.append(f"It's {sp.ordinal(min(pos.values()))} against {sp.ordinal(max(pos.values()))} in the table: {H} are {sp.ordinal(pos['home'])}, {A} {sp.ordinal(pos['away'])}.")
            items.insert(1, (1, ch.pick("gap", forms)))
            items = [(it[0], it[1], tuple(x + 1 if x >= 1 else x for x in (it[2] if len(it) > 2 and it[2] else ())), it[3] if len(it) > 3 else None) for it in items]
        else:
            items.append((3, f"{H} are {sp.ordinal(pos['home'])} in the table and {A} {sp.ordinal(pos['away'])}."))
    else:
        for side, nm in (("home", h), ("away", a)):
            if side in pos:
                items.append((3, f"{sp.team(nm)} are {sp.ordinal(pos[side])} in the table."))
    tr = trend_unit(dos, "away", ch) or trend_unit(dos, "home", ch)
    if tr:
        items.append((3, tr))
    return items


# ---------------------------------------------------------------------------- slide B

def _result_sentence(r: dict) -> str:
    h, a = sp.team(r.get("home")), sp.team(r.get("away"))
    hg, ag = int(r["hg"]), int(r["ag"])
    if hg > ag:
        return f"{h} beat {a} {sp.score(hg, ag)}"
    if ag > hg:
        return f"{a} won {sp.score(hg, ag)} at {h}"
    return f"it finished {sp.score(hg, ag)}"


def h2h_units(dos: dict, ch: sp.Chooser) -> list[tuple[float, str]]:
    """Head to head as two units: the latest meeting (matters more) and the average (nice to have)."""
    rows = meetings(dos)
    if not rows:
        return []
    r0, when = rows[0], sp.month_year(rows[0].get("date")) or "recently"
    if len(rows) == 1:
        return [(1.4, ch.pick("h2h1", [f"They last met in {when}, and {_result_sentence(r0)}.",
                                       f"The last time these two met was {when}: {_result_sentence(r0)}."]))]
    n = len(rows)
    goals = [int(r["hg"]) + int(r["ag"]) for r in rows]
    avg = sum(goals) / n
    both = sum(1 for r in rows if int(r["hg"]) > 0 and int(r["ag"]) > 0)
    tail = ""
    if both == n and n >= 2:
        tail = ", and both teams scored every time"
    elif both >= max(2, n - 1) and n >= 4:
        tail = f", and both teams scored in {sp.words(both)} of them"
    head = ch.pick("h2h", [f"Their last {sp.words(n)} meetings have averaged {sp.per_game(avg, ch)} goals{tail}.",
                            f"When these two meet there are goals: {sp.per_game(avg, ch)} a game across the last {sp.words(n)}{tail}."
                            if avg >= 2.5 else f"Their last {sp.words(n)} meetings have averaged {sp.per_game(avg, ch)} goals{tail}."])
    recent = f"The most recent was in {when}: {_result_sentence(r0)}."
    return [(2.0, head), (1.4, recent)]


def h2h_unit(dos: dict, ch: sp.Chooser) -> str | None:
    """Both h2h sentences together (used where one string is wanted)."""
    return " ".join(t for _, t in h2h_units(dos, ch)[::-1] if True) or None


def _clean_headline(title: str) -> str:
    t = sp.ascii_fold(re.sub(r"\s+", " ", str(title or "")).strip().strip("\"'“”‘’"))
    return t.replace(": ", ", ").replace(" - ", ", ").rstrip(".!?")


def _source_name(src: str) -> str:
    s = str(src or "").strip()
    low = s.lower()
    if low.startswith("bbc"):
        return "the BBC"
    if low in ("guardian", "the guardian"):
        return "the Guardian"
    return s or "the press"


def news_from_headlines(dos: dict, ch: sp.Chooser, headlines: list[dict]) -> list[str]:
    out = []
    for h in headlines[:2]:
        src = _source_name(h.get("_src") or h.get("source"))
        out.append(ch.pick("news", [f"The latest from {src}: {_clean_headline(h['text'])}.",
                                     f"{sp.cap(src)} has this headline: {_clean_headline(h['text'])}."]))
    return out


def _is(names: list[str]) -> str:
    return "is" if len(names) == 1 else "are"


def _team_news(T: str, c: dict, ch: sp.Chooser) -> tuple[str, str]:
    """(main sentence without a final stop, optional second sentence about returners)."""
    out, doubt, susp, back = (list(c.get(k) or []) for k in ("out", "doubt", "susp", "back"))
    if out:
        s = f"{T} {ch.pick('without', ['will be without', 'are missing', 'are without'])} {sp.names(out)}"
        if susp:
            s += f", and {sp.names(susp)} {_is(susp)} suspended"
    elif susp:
        s = f"{T} will be without the suspended {sp.names(susp)}"
    elif doubt:
        s = f"{T} have {sp.names(doubt)} doubtful"
        doubt = []
    else:
        s = f"{T} {ch.pick('clear', ['have no new injury worries', 'come through with no fresh injury concerns'])}"
    if doubt:
        s += f", with {sp.names(doubt)} doubtful"
    return s, (f"{sp.names(back)} {_is(back)} back in the squad." if back else "")


def card_speech(cards: list[dict], dos: dict, ch: sp.Chooser) -> list[str]:
    """Team news as sentences. Structured cards ({team, out[], doubt[], susp[], back[], source}) are written out in
    plain speech with one mention of the source; cards that already carry a `spoken` line are used as they are."""
    structured = [c for c in cards if any(c.get(k) for k in ("out", "doubt", "susp", "back", "clear"))]
    if not structured:
        return [c["spoken"] for c in cards if c.get("spoken")]
    src = next((c.get("source") for c in structured if c.get("source")), "")
    src_name = _source_name(str(src).split("·")[0].strip()) if src else ""
    mains, extras = [], []
    for c in structured[:2]:
        main, extra = _team_news(sp.team(c.get("team") or ""), c, ch)
        mains.append(main)
        if extra:
            extras.append(extra)
    body = mains[0] + (f", while {mains[1]}" if len(mains) > 1 else "")
    if src_name:
        body = ch.pick("srcintro", [f"According to {src_name}, {body}", f"On the team news, {src_name} says {body}"])
    return [body + "."] + extras


def midweek_unit(dos: dict, side: str, ch: sp.Chooser, other_days: int | None = None) -> str | None:
    """"Dortmund come into this off a one-nil Champions League win on Wednesday" - from the team's most recent match."""
    from datetime import datetime
    g = last_game(dos, side)
    if not g or not g["comp"] or g["days"] > 5:
        return None
    T = sp.team(dos.get(side))
    kind = "win" if g["gf"] > g["ga"] else "draw" if g["gf"] == g["ga"] else "defeat"
    sc = sp.score(g["gf"], g["ga"])
    art = _art(sc)
    comp = sp.ascii_fold(g["comp"]).strip()
    comp = re.sub(r"\s*:.*$", "", comp)
    try:
        day = datetime.strptime(g["date"], "%Y-%m-%d").strftime("%A")
    except ValueError:
        day = ""
    base = ch.pick("mid", [f"{T} come into this off {art} {sc} {comp} {kind}" + (f" on {day}" if day else ""),
                            f"{T} played in the {comp} on {day}, {art} {sc} {kind}" if day else f"{T} played in the {comp}, {art} {sc} {kind}"])
    extra = ""
    if g["days"] <= 4:
        extra = f", just {sp.words(g['days'])} days ago"
        if other_days and other_days >= g["days"] + 2:
            extra += f", while {sp.team(dos.get('away' if side == 'home' else 'home'))} have had {sp.words(other_days)}"
    return base + extra + "."


def rest_unit(dos: dict, rest: tuple, ch: sp.Chooser) -> str | None:
    """Only when it is worth saying: a short turnaround for one side or both, or a comfortable week for both."""
    rh, ra = rest
    if not (rh and ra):
        return None
    rh, ra = int(rh), int(ra)
    H, A = sp.team(dos.get("home")), sp.team(dos.get("away"))
    if rh >= 6 and ra >= 6:
        return "Both sides have had a good week to recover."
    if rh <= 3 and ra <= 3:
        return f"Both sides are on a quick turnaround, with just {sp.words(max(rh, ra))} days since their last game."
    if min(rh, ra) <= 4 and abs(rh - ra) >= 2:
        short, ds, other, do = (H, rh, A, ra) if rh < ra else (A, ra, H, rh)
        return f"{short} have had just {sp.words(ds)} days since their last game, {other} {sp.words(do)}."
    return None


def weather_unit(raw: tuple[str, str] | None, dos: dict, ch: sp.Chooser) -> str | None:
    for f in ((dos.get("context") or {}).get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "weather" and not f.get("stale"):
            m = re.search(r"(-?\d+)\s*°C,\s*rain\s*([\d.]+)\s*mm/h,\s*wind\s*(\d+)\s*km/h", str(f.get("text") or ""))
            if not m:
                continue
            temp, rain, wind = int(m.group(1)), float(m.group(2)), int(m.group(3))
            deg = f"{sp.words(abs(temp))} degrees" + (" below" if temp < 0 else "")
            bits = ["there's some rain around" if rain >= 0.3 else "it should stay dry"]
            if wind >= 30:
                bits.append("it's quite windy")
            return ch.pick("wx", [f"Weather-wise, {' and '.join(bits)}, around {deg}.", f"At kick-off it's about {deg}, and {' and '.join(bits)}."])
    return None


def referee_unit(dos: dict, ch: sp.Chooser) -> str | None:
    for f in ((dos.get("context") or {}).get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "referee" and not str(f.get("text") or "").startswith("N/A"):
            m = re.match(r"^Referee\s+(.+?):\s*([\d.]+)\s*cards/game", str(f.get("text") or ""))
            if m:
                return f"The referee is {sp.ascii_fold(m.group(1))}, who averages {sp.per_game(float(m.group(2)), ch)} cards a game."
    return None


_NO_NEWS = ("There's no confirmed team news yet, and line-ups usually land about an hour before kick-off.",
            "Team news is still to come. Line-ups normally arrive around an hour before kick-off.",
            "Nothing confirmed on team news yet. Line-ups tend to drop about an hour before kick-off.")


def b_units(dos: dict, cards: list[dict], ch: sp.Chooser, *, headlines: list[dict] | None = None, rest: tuple = (None, None),
            facts: list[dict] | None = None) -> list[tuple[float, str]]:
    items: list[tuple[float, str]] = []
    hu = h2h_units(dos, ch)
    if hu:
        items += hu
    else:
        items.append((2.0, ch.pick("noh2h", ["These two haven't met in our recent records.",
                                             "There's no recent history between these two to go on."])))
    news = card_speech(cards, dos, ch) if cards else (news_from_headlines(dos, ch, headlines) if headlines else [])
    if news:
        items += [(1.0 + 0.01 * k, s) for k, s in enumerate(news[:3])]
    else:
        items.append((2.6, ch.pick("nonews", _NO_NEWS)))      # says nothing new, so it never crowds out a real detail
    notes = []
    for side, other in (("home", "away"), ("away", "home")):
        g_other = last_game(dos, other)
        note = midweek_unit(dos, side, ch, g_other["days"] if g_other else None)
        if note:
            notes.append(note)
    if notes:
        items += [(1.2, n) for n in notes[:2]]
    else:
        ru = rest_unit(dos, rest, ch)
        if ru:
            items.append((2.3, ru))
    for f in (facts or [])[:2]:
        t = str((f or {}).get("spoken") or "")
        if t:
            items.append((2.1, t))
    wu = weather_unit(None, dos, ch)
    if wu:
        items.append((3, wu))
    rf = referee_unit(dos, ch)
    if rf:
        items.append((3, rf))
    return items


# ---------------------------------------------------------------------------- slide V

def _count(rows: list[dict], pred, last: int = 5) -> tuple[int, int]:
    rs = rows[:last]
    return sum(1 for m in rs if pred(m)), len(rs)


def reasons(dos: dict, best: dict, ch: sp.Chooser, extra_reasons: list | None = None) -> tuple[list[str], list[str]]:
    """(up to two spoken reasons, up to two short on-screen bullets). Data-backed, never repeating a point."""
    label = str(best.get("label") or "")
    th, ta = _team_block(dos, "home"), _team_block(dos, "away")
    lh, la = last_results(dos, "home"), last_results(dos, "away")
    side = pick_side(best, dos)
    pieces: list[tuple[float, str, str, str]] = []     # strength, spoken, bullet, topic
    for x in (extra_reasons or []):
        pieces.append((float(x.get("s", 6)), x["spoken"], x.get("bullet") or x["spoken"], x.get("topic", "extra")))
    if side:
        me, opp = ("home", "away") if side == "home" else ("away", "home")
        l_me, l_opp = (lh, la) if side == "home" else (la, lh)
        t_me, t_opp = (th, ta) if side == "home" else (ta, th)
        me_n, opp_n = sp.team(dos.get(me)), sp.team(dos.get(opp))
        k, n = _count(l_me, lambda m: m["gf"] > 0)
        gm = " league games" if is_league_form(dos, me) else ""
        if n >= 4 and k >= n - 1 and k >= 3:
            pieces.append((k + 0.5, f"{me_n} have scored in {sp.of_last(k, n)}{gm}", f"{me_n} scored in {k} of last {n}", "me_score"))
        if not suspect_history(dos, me) and not incomplete(dos, me):
            for x in (((dos.get("trends") or {}).get(me) or {}).get("all") or []):
                m = re.search(r"scored in (\d+) consecutive matches", str((x or {}).get("t") or ""))
                if m and int(m.group(1)) >= 8:
                    N = int(m.group(1))
                    pieces.append((9, f"{me_n} have scored in {sp.words(N)} matches in a row", f"{me_n} scored in {N} matches in a row", "me_score"))
        vg = t_me.get("venue_gf")
        if isinstance(vg, (int, float)) and vg >= 1.4:
            where = "at home" if side == "home" else "away from home"
            pieces.append((4.5, f"{me_n} are scoring {sp.per_game(vg, ch)} a game {where}", f"{vg:.1f} goals a game {where}", "me_venue"))
        k2, n2 = _count(l_opp, lambda m: m["ga"] > 0)
        gm2 = " league games" if is_league_form(dos, opp) else ""
        if n2 >= 4 and k2 >= n2 - 1 and k2 >= 3:
            pieces.append((k2 - 0.1, f"{opp_n} have conceded in {sp.of_last(k2, n2)}{gm2}", f"{opp_n} conceded in {k2} of last {n2}", "opp_concede"))
        og = t_opp.get("venue_ga")
        if isinstance(og, (int, float)) and og >= 1.5:
            where = "away from home" if side == "home" else "at home"
            pieces.append((4.0, f"{opp_n} are letting in {sp.per_game(og, ch)} a game {where}", f"{og:.1f} conceded a game {where}", "opp_venue"))
    else:
        o15, o25 = re.search(r"over\s*1\.5", label, re.I), re.search(r"over\s*2\.5", label, re.I)
        key = "venue_o15" if o15 else "venue_o25" if o25 else None
        line = "one and a half" if o15 else "two and a half"
        H, A = sp.team(dos.get("home")), sp.team(dos.get("away"))
        if key and isinstance(th.get(key), (int, float)) and isinstance(ta.get(key), (int, float)):
            rh, ra = sp.rate(th[key]), sp.rate(ta[key])
            both = (f"over {line} has landed in {rh} of both {sp.possessive(H)} home games and {sp.possessive(A)} away games" if rh == ra
                    else f"over {line} has landed in {rh} of {sp.possessive(H)} home games and {ra} of {sp.possessive(A)} away games")
            pieces.append((6, both,
                           f"Over {'1.5' if o15 else '2.5'}: {round(100 * th[key])}% at home · {round(100 * ta[key])}% away", "rate"))
        need = 2 if o15 else 3
        ms = meetings(dos)
        if len(ms) >= 3 and all(int(r["hg"]) + int(r["ag"]) >= need for r in ms):
            pieces.append((5.5, f"every one of their last {sp.words(len(ms))} meetings had {sp.words(need)} goals or more",
                           f"Last {len(ms)} meetings: {need}+ goals every time", "h2h"))
        for sd, nm, rows in (("home", H, lh), ("away", A, la)):
            k, n = _count(rows, lambda m: m["gf"] + m["ga"] >= need)
            if n >= 4 and k >= n - 1:
                lg = "league games" if is_league_form(dos, sd) else "games"
                pieces.append((4.5 + k / 10, f"{sp.possessive(nm)} {lg} have gone over {line} in {sp.of_last(k, n)}",
                               f"{nm}: {k} of last {n} went over {'1.5' if o15 else '2.5'}", f"trend_{sd}"))
        gf, ga = th.get("venue_gf"), ta.get("venue_ga")
        if isinstance(gf, (int, float)) and isinstance(ga, (int, float)) and gf >= 1.4 and ga >= 1.4:
            pieces.append((4.2, f"{H} score {sp.per_game(gf, ch)} a game at home and {A} concede {sp.per_game(ga, ch)} away",
                           f"{gf:.1f} scored at home · {ga:.1f} conceded away", "pair"))
    pieces.sort(key=lambda p: -p[0])
    top, seen = [], set()
    for pc in pieces:
        if pc[3] not in seen and len(top) < 2:
            top.append(pc)
            seen.add(pc[3])
    if not top:
        return ["The numbers from both sides point the same way"], ["Form and venue numbers agree"]
    return [p[1] for p in top], [p[2] for p in top]


def _they(first: str, second: str) -> str:
    """If both reasons are about the same team, the second one says "they" instead of repeating the name."""
    m = re.match(r"^(.+?) (have|are|haven't|aren't) ", first)
    if m and second.startswith(m.group(1) + " "):
        rest = second[len(m.group(1)) + 1:]
        rest = re.sub(r"^have ", "they've ", rest)
        rest = re.sub(r"^are ", "they're ", rest)
        return rest if rest.startswith("they") else "they " + rest
    return second


def v_units(dos: dict, ch: sp.Chooser, extra_reasons: list | None = None, idx: int = 1, rot: int = 0) -> tuple[list[tuple[int, str]], list[str]]:
    best = dos.get("_best_market") or {}
    odds = best.get("odds")
    od = f"{float(odds):.2f}" if isinstance(odds, (int, float)) else "N/A"
    mk = spoken_market(best, dos)
    leads = (f"So, my pick for this one: {mk}, at {od}.", f"My pick here is {mk}, at {od}.",
             f"I'm going with {mk}, at {od}.", f"The one I like here: {mk}, at {od}.")
    lead = leads[(idx + rot) % len(leads)]
    spoken, bullets = reasons(dos, best, ch, extra_reasons)
    items: list[tuple[float, str]] = [(0, lead), (1, sp.cap(spoken[0]) + ".")]
    if len(spoken) > 1:
        link = ch.pick("link", ["On top of that,", "Plus,", "And"])
        second = _they(spoken[0], spoken[1])
        items.append((2, f"{link} {second}."))
    return items, bullets


# ---------------------------------------------------------------------------- intro / closer

_WHEN = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


def country_run(matches: list[dict]) -> str:
    seen: dict[str, int] = {}
    for m in matches:
        c = sp.country(m.get("country"))
        if c:
            seen[c] = seen.get(c, 0) + 1
    return sp.join_list([f"{c} twice" if k == 2 else c for c, k in seen.items()])


def intro_text(matches: list[dict], day_label: str, ch: sp.Chooser) -> str:
    n = len(matches)
    evening = sp.all_evening(str(m.get("kickoff") or "")[11:16] for m in matches)
    dp = "tonight" if evening else "today"
    num = _WHEN.get(n, str(n))
    greet = ch.pick("greet", ["Hello and welcome back to Mr 2 Odds.", "Hi everyone, and welcome back to Mr 2 Odds.", "Welcome back to Mr 2 Odds."])
    head = ch.pick("head", [f"It's {day_label}, and I've got {num} games lined up for you {dp}.",
                             f"It's {day_label}, and there are {num} games to get through {dp}."])
    trip = ch.pick("trip", [f"We're heading to {country_run(matches)}.", f"We'll be visiting {country_run(matches)}."])
    plan = ch.pick("plan", ["For each one, I'll take you through how both sides have been playing, the head to head and the team news, and then I'll tell you what I'd go for.",
                             "For every game we'll look at the form, the history between the teams and who's missing, and then I'll give you my pick."])
    small = ("Before we start, the small print. This is statistical information, not betting advice. "
             "It's eighteen plus only, so please bet responsibly. "
             "Never bet money you can't afford to lose, and remember, there's no such thing as a sure bet.")
    go = ch.pick("go", ["Right then, let's get into it.", "Okay, let's get going.", "So, let's get started."])
    return f"{greet} {head} {trip} {plan} All kick-off times are South African time. {small} {go}"


def closer_text(matches: list[dict], ch: sp.Chooser) -> str:
    n = len(matches)
    evening = sp.all_evening(str(m.get("kickoff") or "")[11:16] for m in matches)
    dp = "tonight" if evening else "today"
    num = _WHEN.get(n, str(n))
    ask = ch.pick("ask", ["If you enjoyed this, give it a like, share it with a mate, and subscribe so you don't miss tomorrow's games.",
                          "If this was useful, give it a like, send it to a mate, and subscribe so you catch tomorrow's games."])
    return (f"And that's the lot for {dp}. All {num} picks are on your screen now, so grab a screenshot if you want them. {ask} "
            "One last reminder: this is statistical information, not betting advice. "
            "Eighteen plus only, please bet responsibly, and never bet more than you can afford to lose. "
            "Mr 2 Odds. All rights reserved.")


# ---------------------------------------------------------------------------- assembly

def assemble(items: list[tuple], budget: int) -> str:
    """items = [(priority, text[, anchors[, short]])] in reading order. Lower priority numbers matter more.

    Priority 0 is always kept; the rest are added by importance while they fit the character budget, and the result is
    read back in the original order. `short` is a tighter wording tried when the full sentence does not fit.
    A text that starts with "§link§" gets that link word ("Meanwhile,") only when one of its `anchors` (indices of the
    sentences it leans on) was kept; otherwise it simply starts with the team name.
    """
    n = len(items)
    parts = [(it[0], it[1], tuple(it[2]) if len(it) > 2 and it[2] else (), it[3] if len(it) > 3 else None) for it in items]
    chosen: dict[int, str] = {}
    used = 0

    def render(i: int, text: str) -> str:
        m = re.match(r"^§(.*?)§\s*(.*)$", text, re.S)
        if not m:
            return text
        anchored = any(a in chosen for a in parts[i][2])
        return f"{m.group(1)} {m.group(2)}" if anchored else m.group(2)

    for i, (p, text, _, _) in enumerate(parts):
        if p == 0:
            chosen[i] = text
            used += len(render(i, text)) + 1
    for i in sorted((i for i, (p, *_rest) in enumerate(parts) if p != 0), key=lambda i: (parts[i][0], i)):
        _, text, _, short = parts[i]
        for cand in (text, short):
            if cand and used + len(render(i, cand)) + 1 <= budget:
                chosen[i] = cand
                used += len(render(i, cand)) + 1
                break
    return " ".join(render(i, chosen[i]) for i in sorted(chosen))
