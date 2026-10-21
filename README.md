# ⚽ PlayReport

Automatic football analysis that runs **every 30 minutes** on GitHub Actions and publishes to the PlayReport
Android app and Telegram — no servers, no API keys, and it runs while your phone is in your pocket.

* **Coverage** — every competition on the public live feed, worldwide (including women's and youth leagues),
  priced by Sportybet South Africa; the 22 main European leagues additionally get corners, cards and referee models.
* **Data-first model** — every probability comes from football data only (goals, form, venue, league baseline →
  Dixon-Coles score matrix); bookmaker prices are a *separate comparison layer* (implied %, difference, EV, market xG)
  and never feed the model. Every statistic carries its sample size (Very small 1–4 … Very strong 40+), every match
  has a transparent data-quality assessment, the raw matches used, extreme results flagged and the model's own
  numbers ("why 1.35 goals?") in the app's **Data** tab and in `python audit.py HOME AWAY`. Missing data is N/A, never 0.
* **Goals shortlists** — Over 1.5, Over 2.5, Both Teams To Score, from the backtested and calibrated model.
* **High-probability selections** — singles with model probability ≥ 70 % (**Over 2.5 and BTTS from 55 %**), priced by
  Sportybet, in the Over-goals / BTTS / corners / bookings markets — no team goals, no double chance, no unders
  (2026-10-17, see *Market policy* below). New ones are announced immediately (Telegram + app). Nothing is ever
  labelled "safe" or "guaranteed".
* **⭐ Bets of the day** — grouped card built on Over 1.5, Over 2.5, BTTS and bookings; 1X2 / BTTS / Over 2.5 only with strong supporting form; one market per match; graded separately.
* **Trends, head-to-head and home/away form** on every match page; live scores, line-ups and match statistics for
  every match in play; squad values (Transfermarkt) for the main leagues.
* **Live research & context** (Phase A: collected and shown, **not yet weighted**) — for the fixtures inside the
  published window the scanner also records attributed current information: confirmed line-ups from the live feed
  when they are published, reported team news (outlet, link and publication time, availability signals flagged but
  never "verified"), scheduling/fatigue from our own archive, the competition format, and Open-Meteo weather for
  genuinely severe conditions only. Each match shows **base probability → context → final probability** with a
  research-quality grade (HIGH/MEDIUM/LOW/INSUFFICIENT), the reasons, the sources and any unresolved conflict;
  missing information is N/A and normal weather is no adjustment by rule. With the shipped configuration the
  published probability is *identical* to the statistical model — see `docs/RESEARCH.md`.
* **Bet slip & tickets** in the app — build a multiple from priced selections, lock it, and PlayReport grades it from
  the scores and match statistics (private record on the phone).
* **Results archive** — every finished match on the live feed is kept with half-time score, corners, cards, shots and
  possession (`data/ls/` on the data branch), feeding the corners / cards models for every league over time.
* **Checked before publishing** — every run exports the app data to a staging directory and `verify.py` checks it
  (format, probabilities, prices, selection rules, day-card sections, detail files, evidence layer, no market
  contamination of model probabilities, ledger integrity) before it is
  promoted; a failed check keeps the previous publication and reports the problem on Telegram.
* **Season backfill** — up to two earlier seasons of every covered competition are archived from Livescore once,
  so head-to-head, form and league pages are complete outside football-data's leagues.
* **Delivery** — full report (Markdown + PDF) at 07:00 / 12:00 / 17:00 SAST on Telegram; three shortlist videos a
  day (05:00–07:19, 11:00–12:19, 16:00–17:19 SAST) in 16:9 and 9:16, no voice, one music bed
  (`assets/reel/under_the_stadium_lights.mp3`), each slide holding for as long as its own words take to read — the
  first video of the day opens with every result from every video of the day before, then today's matches one at a
  time with the reason for each; files
  are deleted after a successful send; app data on the `data` branch (`data/app/latest.json`, per-match files,
  60-day history); a weekly performance digest on Mondays.

The code lives on `main`; all generated state (reports, ledgers, app data, the Livescore archive) lives on the
orphan `data` branch, which is force-pushed by every run so the history stays small.

Statistical information, not betting advice. 18+.

## 🎾 Tennis Scanner (separate module)

`tennis/` is an independent package built beside the football scanner — own data (`data/tennis/`, `data/app/tennis/`
on the orphan `tennis-data` branch), own model, tracker (`data/tennis/tracker.csv`), reports (`reports/tennis/`),
workflow (`.github/workflows/tennis-scan.yml`, four runs a day) and tests (`tennis/tests/`). It imports nothing from
the football model code; the only shared piece is the generic Markdown → PDF helper. See `docs/TENNIS_AUDIT.md`
(architecture, sources, limitations) and `tennis/BACKTEST_RESULTS.md` (walk-forward validation and calibration).

* **Coverage** — ATP / WTA main tours and ATP/WTA Challengers, singles only (no ITF, team events or doubles).
* **Data** — Jeff Sackmann's historical match files (tennisabstract.com, CC BY-NC-SA 4.0, June 2026 snapshot via the
  Aneeshers archive mirror; 288,040 matches 2005–2026) for ratings, form, serve/return statistics; Livescore for
  results after the snapshot (no statistics — serve/return traits from the archive are marked stale when old);
  Sportybet prices as a *comparison layer only*. Anything missing is N/A, never zero.
* **Model** — Elo (overall + surface blend, sample-size K schedule) → set probability → explicit best-of-3 / best-of-5
  match probability (2-0 / 2-1 / 3-0 / 3-1 / 3-2 each way) → Markov point/game chain for total games, player games
  and game handicap. Parameters chosen on 2012–2018, evaluated on 2019–2026 (walk-forward, no look-ahead).
* **Output** — per match: MODEL PROBABILITY, FAIR ODDS, BOOKMAKER ODDS, MARKET IMPLIED, EDGE and DATA QUALITY
  (a 14-check score of the evidence, not a win probability). Reports at 08:00 / 18:00 SAST on Telegram labelled
  "🎾 TENNIS SCANNER". No parlays, no tennis + football combinations.
* **Selections of the day** — one preferred market per match (`tennis/markets.py::select`): the highest model
  probability ≥ 60 % among Sportybet-priced markets (price ≥ 1.30) whose margin-free implied probability is ≥ 45 %
  (the market must not contradict the pick), data quality ≥ 60, both players ≥ 30 rated matches, no low-confidence
  game data, model − market ≤ 20 pp. **Strong** = model ≥ 70 % and market ≥ 50 %. Ranked by probability, never by
  edge. Grouped by market (Match winner / Total games / Player games / Game handicap) in `latest.json`
  (`selections`, `sections`, `strong`), the reports and Telegram.
* **Tracker** — `data/tennis/tracker.csv` grades four groups separately (`kind` = day / strong / highlight /
  favourite): hit rate vs average model probability and flat-stake units at the recorded price. Day files
  `data/app/tennis/days/<day>.json` keep every analysed match with its result and settlement; `days/index.json` lists them.
* **App** — sport switch (⚽ Football | 🎾 Tennis) at the top of every tab in `tennis.js`; the football views are
  wrapped, not modified. Tennis Home / Bets / Live / Matches / Days and a match page with Overview / Markets /
  Stats / Data (sample labels, last 10 matches with raw scores, H2H context only, quality checks, identity, inputs).
  Smoke test: `android/tennis_ui_test.py`.

### Model diet: every league the archive has enough data on (2026-10-11, widened 2026-10-17)
Fixture intake is filtered before analysis (`scanner.league_allowed` / `scanner.fixture_allowed`). A competition is in when it is on the **curated list** (big-5 + second tiers, the strong top flights, Brazil, Argentina, MLS, Liga MX, the big African leagues, UEFA Champions / Europa / Conference League), is one of the **22 football-data main divisions**, or passes the **archive rule** (`scanner.data_rich_from_facts`, computed once per run from `data/ls/stages` via `coverage.stage_facts`, ≈ 2 s): a league-shaped table (8–45 clubs), the registry's `eligible` flag, a median of at least 15 archived finished matches per club, a result inside the model's 400-day window, and match statistics on ≥ 50 % of the recent window — or, for a national league whose provider publishes no statistics (Ghana, Kenya, Tunisia, Algeria …), a table that is not a regional / amateur tier (`AMATEUR_TIER_RE`: Oberliga, Serie D, RFEF and "Group x" splits, Norwegian 3. divisjon …). On the 2026-10-17 archive that is **165 stages (was 36)**, including the **Chinese Super League and League One**, K League 1/2, the Saudi Pro League, the Indian Super League, UAE, Qatar, Thailand, Brazil Série B, USL, England League 1/2, the Scottish divisions, 3. Liga, Eerste Divisie, Liga Portugal 2 and Turkey's 1. Lig. As the stats collector fills more competitions they qualify automatically.
Hard blocks beat every rule: **Australia** (explicit user rule 2026-10-11), women, youth/reserve (incl. "Premier League 2"), friendlies, all domestic cups, internationals, qualifiers and play-offs. The 2026-10-17 pass also anchored the English patterns (`Northern Premier League`, step 4, used to slip through `premier league$`). Competitions that are in only through the archive rule are analysed `DIET_EXTRA_DAYS` (14) ahead — the app lists ten days of fixtures, so the far end of the 60-day window would only cost scan time (curated leagues and main divisions keep the full horizon). Depth gate: a fixture where either team has fewer than `MIN_TEAM_MATCHES` (8) recent matches with data is skipped entirely. Every app surface inherits the filter (shortlist, selections, bets of the day, accas, the Leagues browser, fixtures list and search); history collection stays wide so cup/international results still feed team form. Levers: `MODEL_DIET`, `MIN_TEAM_MATCHES`, `DIET_EXTRA_DAYS`, `DIET_MIN_PER_TEAM`, `DIET_STATS_PCT`, `SEED_STAGES`.

### Japan is back (2026-10-21)
The 2026-10-11 ban on Japan is reversed at the user's request: **J1 and J2 League are on the curated list**
(`DIET_ALLOW`), so they are analysed whenever they play, and any deeper Japanese division (J3 …) comes in through the
archive rule like every other league — the Livescore archive already carries `japan/j-league`, `japan/j-league-2` and
`japan/j-league-3`, and all three are now seeded (`SEED_STAGES`) so their history keeps updating. `japan` and
`\bj[123]\b` are out of `DIET_BLOCK_RE`; the Emperor's Cup, the League Cup and the WE League stay out through the cup /
women's blocks, and **Australia stays banned**. Tests: `tests/test_diet.py` (Japan allowed, Japanese cups blocked,
Australia still blocked).

### Market policy (2026-10-17)
`policy.py` is the one place that decides which selections the model may recommend; `safe.selections()` asks it for every candidate, so the shortlist, high-probability selections, bets of the day, accas, the match pages and the app boards all inherit it (the app repeats the rule client-side so a payload published before a change cannot show a dropped market). **Dropped:** double chance (1X/12/X2) and **every under** — total goals, no-BTTS, team unders, corner and card unders (the old pattern missed team-level corner/card unders, which is how `CAU55` / `KHU25` reached bets of the day). **Focus:** Over 1.5, Over 2.5, BTTS and bookings; 1X2 and corner overs stay on (not asked to go). **Over 2.5 and BTTS start from a 55 % model probability** (`policy.SEL_MIN_P`, in the shortlist bars, bets of the day, the high-probability list and the app boards); every other market keeps its bar (goals lines 70 %, corners & bookings 65 %, 1X2 60 %). Old codes still label and settle, so bets placed earlier keep grading. **Lanes:** one selection per match stays the rule, but "the best candidate wins the match" gave Over 1.5 — always the likeliest of Over 1.5 / Over 2.5 / BTTS — 286 of 303 matches on the 2026-10-17 slate (and 40 of 40 high-probability slots), so Over 2.5 could never appear whatever its floor. Both the **shortlist** and the **high-probability selections** now work like the bets-of-the-day card: each market claims its own best matches in turn (shortlist: Over 2.5, BTTS, bookings, corners, 1X2, then Over 1.5 and the other goals lines, 10 each; selections: bookings 6, corners 4, Over 2.5 10, BTTS 10, then Over 1.5 up to 50 in total), and Over 1.5 takes what is left. Nothing is padded, a match cut from one lane can still be claimed by a later one, and the board is still shown by probability. Levers: `SHORTLIST_LANES=0` / `SAFE_LANES=0` restore the old single-ranking behaviour. Other levers: `MODEL_MARKETS=all` (or `unders,team,dc`) restores a dropped family, `MODEL_DROP=corners,result` switches those two off, `POLICY_MIN_P_O25` / `POLICY_MIN_P_BTTS` move the 55 % (not `MIN_P_O25` / `MIN_P_BTTS`: scan.yml already uses those, at 0.60, for the older Goals-shortlist star thresholds).

### Settlement: team corners and team cards were graded backwards (2026-10-21)
Reported as "I'm losing more bets than before". The picks were not the problem — the grader was. `safe.settle` read
the *side* letter as the *direction*, so a code like `CHO35` ("home team over 3.5 corners") was graded as a
**match-under** (`total corners < 3.5`) and came back as a loss almost every time; `KAO15` / `KHU25` (team cards) had
the same fault, and a statistic the feed never published could also be turned into a loss. On the published data
branch that mis-graded **63 wins as losses** (34 of them still inside the last 60 days). `settle` now parses one shape
— family (`C` corners / `K` cards / none goals), optional side (`H`/`A`), direction (`O`/`U`), line in tenths — and
grades a team market on *that team's* number and a total on the match total, returning `None` (pending → void) when
the statistic is missing. A new `safe.regrade_settled` re-checks settled corner/card rows against the archive and is
called by `settle_bets` and `shortlist.settle`, so the record repairs itself on the next scan; goals, BTTS and 1X2
rows were always right and are never touched. `tools/regrade_ledgers.py --state state [--write]` does the same
offline. Tests: `tests/test_settle_markets.py` (every code the policy can emit must be gradable, plus a repair test).

Model check on the same archive, 788 settled bets re-graded: actual 79.7 % vs the model's 80.4 % — calibrated in
every probability band (<70 %: 70 % actual vs 65 % predicted … 85 %+: 87 % vs 89 %), so the recent dip is variance
plus the false losses, not a broken model. What did change on 2026-10-17 is volume and mix: the lanes added corners,
bookings and 1X2, and the app now announces 20–110 picks on a busy day (45 on 2026-10-20) instead of a dozen.

### Strong markets for the day, total corners, and no accumulators (2026-10-21)
Three user rules in one pass. **Strong markets.** The home page now opens with one section, *Strong markets for the
day*: model probability **≥ 75 %**, a real Sportybet price of **≥ 1.16**, and only **Over 1.5 total goals, team goals,
corners and bookings**. `policy.is_strong_market()` is the definition, `appdata.strong_markets_payload()` filters,
caps and orders the list, and the payload key is `strong_markets` (`min_p`, `min_odds`, `date`, `bets`). Team-corner
lines used to crowd out the totals, so the section caps each family (`STRONG_CAPS`: total corners 8, total bookings
6, Over 1.5 10, team goals 6, team corners 3, team bookings 3), shows at most two markets per match, and orders by
probability. Nothing else may appear there — no Over 2.5, BTTS, 1X2 or unders. **Total corners.** Two things hid the
match-total corner market: the count model only priced 8.5 and above while team lines started at 3.5 (so an average
10-corner match could never show 75 %+ on a total), and the board gave the whole corner family one lane of four
slots, which the three team lines took. `markets.CORNERS["lines_total"]` is now `(7.5 … 12.5)` — same distribution,
same calibration, wider lines — and both boards split `corners` / `corners_team` and `cards` / `cards_team` into separate lanes — totals first —
so the totals always get their slots: `safe.safe_lane()`/`SAFE_LANE_CAP` (bookings 4 + 2, corners 4 + 2) and
`shortlist.lane_of()`/`LANE_ORDER`/`LANE_CAP` (10 per total lane, 5 per team lane). **No
accumulators.** Accas are retired everywhere: no build in `scanner.py`, no acca page, home card, menu entry or slip
button in the app, no acca or combine slide in the videos, no acca block in `verify.py` and no acca line in
`safe.summary()`. `accas.py` stays only to settle the historical `data/accas.csv` / `data/accas_doubles.csv` rows.
**Videos** carry Over 1.5 total goals, team goals, corners and bookings only (`shortlist_reel.REEL_MARKET_RE`);
BTTS, Over 2.5 and 1X2 picks are out, and the in-app briefing player uses the same filter. Tests:
`tests/test_strong_markets.py`.

### Videos: no voice at all — one music bed, a full recap first, and no repeated read-out (2026-10-21)
The user retired the AI narration: **every video now carries one track and nothing else.**
`assets/reel/under_the_stadium_lights.mp3` is the permanent soundtrack — not a library, not a rotation. `music.bed()`
loops it to the video's exact length, fades in 1.5 s, fades out 2.5 s, normalises to −18 LUFS and hands it to
`music.mux()`; the picture is copied, never re-encoded. Both the shortlist reel (`shortlist_reel.build` /
`build_both`) and the match breakdown (`match_breakdown.render`) use it, so 16:9 and 9:16 are silent apart from the
same track. A missing track raises instead of publishing a mute video, and the workflow no longer installs espeak-ng,
edge-tts or Piper. **Slide timing.** With nothing spoken, a slide lasts as long as its own words take to read:
`music.reading_seconds(text)` counts words at the old narration pace (2.6 words/s, `REEL_READ_WPS` to tune), clamped
to 2.6–40 s per slide, then `reel.hold_seconds` / `frame_hold` keep the old shape (intro ≥ `INTRO_MIN`, `TAIL` after
every slide, whole frames). **The pick slides are timed by what is on them, not by words** (`reel.stage_seconds`,
5–11 s: a few tenths of a second per chart bar or evidence line, never less than the stage's floor), so the screen
changes every few seconds instead of holding one card. The
breakdown no longer speeds anything up (`MAX_TEMPO` is gone): when the script would run past `MAX_SECONDS` it drops
trailing matches down to `MIN_MATCHES`. **Recap.** The first video of the day (morning, or a manual `FORCE_DAILY_REEL`)
covers *every* selection from *all* of yesterday's videos — the history is merged per day across morning, noon and
evening — paged `RECAP_ROWS` (9) at a time, headed `YESTERDAY'S CARD · EVERY VIDEO · PART n OF m`. It is the record
plus the standout win and the one that got away, never match by match; later pages get one line each. The noon and
evening videos carry no recap (`recap=False`). **No repetition.** Each match appears once, as the three
slides described in the next section (pick + market chart, evidence, record) — and the video ends on the closer,
with no combine or acca slide at all. The list keeps the board's own order — one selection per match, 65 %+, and only Over 1.5 / team
goals / corners / bookings. Levers: `REEL_MIN_P` (0.65), `MAX_PICKS` (12), `RECAP_ROWS`, `MAX_RECAP`,
`REEL_READ_WPS`. Retired with the voice: `voice_polish.py`, `scripts/setup_voice.sh`, the `EDGE_TTS_*` / `PIPER_*` /
`ESPEAK_*` env vars and the workflow's "Prepare neural narration voice" step.

### Each match is three short slides: the pick, the evidence, the record (2026-10-21)
With no voice to explain a selection, the screen has to. Every match now gets up to three slides, all drawn from the
same numbers the app shows (`reel_insights.py`, reading `data/app/fx/<key>.json` and `data/app/leagues/*`):

* **THE PICK** — the clubs, their form, the kick-off, the selection and its SportyBet price, and a horizontal bar
  chart of *every market the video covers for that match*, highest model probability first. The featured market is
  the green bar; because `reel.reel_picks` now features the strongest allowed market per match, it is also the
  tallest bar. The axis is labelled 50 %–100 % rather than 0–100 %: every market in a video is 65 %+ by rule, so a
  zero-based axis would draw six identical bars and hide the differences. The pick is always on its own chart even
  when the fixture detail is missing.
* **WHY IT'S HERE** — each club's league position, points, games played and last-five pills, its home/away scoring
  and conceding rates, then the reasons (`reel_insights.reasons`: model probability, projected goals, the base rate,
  the table position, the edge in points) and this fixture's own trend lines.
* **THE RECORD** — head to head with scores and W/D/L plus the aggregate line, and both clubs' last five results.

Cards are laid out with `reel._fill_slots`, which spreads their contents over the card (capped, so a two-line card
is centred rather than dragged apart) and sizes the fonts from the space available — no more content pooled in the
top third of a card. A slide with nothing to show is **skipped, never left empty** (`reel_insights.slide_plan`).
Portrait stacks each chart bar's label above its bar, because a 9:16 frame cannot fit a market name beside one.
Tests: `tests/test_reel_insights.py`.

### Google Drive handoff: Drive → Zapier → YouTube (2026-10-21)
`drive_handoff.py` is the third lane and the one the user chose to publish through: the finished **16:9** video is
copied into a Drive folder, and a free two-step Zapier Zap (Drive *New File in Folder* → YouTube *Upload Video*)
publishes it. It uses a **service account** (`GDRIVE_SA_JSON`, the whole JSON key) and `GDRIVE_FOLDER_ID`, with
`DRIVE_HANDOFF=1` as the master switch — without both secrets it reports "not configured" and the scan behaves
exactly as before. Share the Drive folder with the service account's `client_email` as **Editor**, then:

```bash
export GDRIVE_SA_JSON="$(cat service-account.json)"
export GDRIVE_FOLDER_ID='...'
python drive_handoff.py info      # account, folder, and whether it may add files
python drive_handoff.py check     # dry run: a 2 KB stand-in through the whole path
python drive_handoff.py upload /tmp/briefing-16x9.mp4
```

Notes that drove the design. **No crypto dependency:** the hashed `requirements.txt` has none, so the RS256 JWT is
signed with plain integer maths from the standard library (`drive_handoff.sign_rs256`, PKCS#1 v1.5 + SHA-256) —
tested against a hand-built key. **Resumable upload**, because Google's multipart endpoint stops at 5 MB and a video
is bigger. **The title has no extension** and the mime type is `video/mp4`, which is what makes the Zapier→YouTube
step publish a playable video rather than a file. Zapier's free plan has no third step, so nothing moves or deletes
the Drive file afterwards: the folder is the permanent receipt log, and the ~100 MB file ceiling is why the videos
stay small. Telegram gets one line either way — `📤 YouTube handoff: <file> → PlayReport/YouTube`, or a warning if it
failed — and a Drive failure never stops the Telegram send. Tests: `tests/test_drive_handoff.py`.

### YouTube auto-poster: probe first, then two videos a day (2026-10-21)
`youtube_post.py` is the second delivery lane, next to Telegram. It uses the YouTube Data API over plain `requests`
(no extra pip dependency) and is **inert until it is configured**: without `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and
`YT_REFRESH_TOKEN` it reports "not configured" and the scan behaves exactly as before.

**What goes up.** By default the morning shortlist in 16:9 (`YT_SLOTS=morning`) and the daily match breakdown
(`YT_UPLOAD_BREAKDOWN=1`) — two uploads a day, not six, because daily near-identical uploads are what YouTube's
inauthentic-content policy targets. The 9:16 reel stays Telegram/TikTok: it runs past three minutes and is not a
Short. Widen with `YT_SLOTS=morning,noon,evening`. `YT_UPLOAD=1` is the master switch, `YT_PRIVACY` the default
visibility (public / unlisted / private). Metadata is written next to each mp4 as `<video>.mp4.json`
(`youtube_post.write_meta`) so the text can be inspected without re-rendering: no bookmaker names, no links, always
the 18+ "statistical information, not betting advice" line, sports category, not made for kids.

**Setting the three secrets.** Google Cloud → new project → enable **YouTube Data API v3** → OAuth consent screen
(external, add your own account as a test user) → Credentials → **OAuth client ID → Desktop app**. Then, on your own
machine:

```bash
export YT_CLIENT_ID='...apps.googleusercontent.com'
export YT_CLIENT_SECRET='...'
python scripts/yt_auth.py          # opens the consent screen, prints YT_REFRESH_TOKEN
python youtube_post.py info        # channel, subscriber count, granted scopes
python youtube_post.py probe       # ← the important one
```

`scripts/yt_auth.py` catches the redirect on `http://127.0.0.1:8765/` and asks for the `youtube` scope (upload, read
status, update, delete — the probe deletes its own clip), with `access_type=offline` so it gets a refresh token.
Sign in with the account that owns the channel. `--manual` is for a machine with no browser.

**Why the probe comes before the poster.** A Google Cloud project created after 28 July 2020 that has not passed
YouTube's compliance audit cannot publish: `videos.insert` succeeds, the video is pinned **private**, and that state
cannot be appealed or changed by hand — Google's own help page says the video has to be re-uploaded through an
audited client or the YouTube site. `probe` uploads a three-second black clip as *unlisted*, reads back the privacy
YouTube actually gave it, then deletes it, and prints one of:

* `OK — uploads can publish` → the project is fine, nothing else to do;
* `LOCKED — the API project is not audited` → either finish the audit
  (https://support.google.com/youtube/contact/yt_api_form), or post through the YouTube site by hand, or use a
  verified third-party uploader (Zapier/Make/Buffer run on their own audited projects).

While an audit is pending, set `YT_PRIVACY=unlisted` or `private` so nothing misleading reaches the channel; nothing
uploaded can earn or count before it is public, and private uploads never count toward the Partner Program.

**Commission realities, recorded here so nobody is surprised later.** Auto-posting is not penalised — the API is
just a delivery method — but the channel still needs 1,000 subscribers plus 4,000 public watch hours (or 10M Shorts
views) and doubles to 8,000 hours on 1 February 2027 for new applicants. Betting content is age-restricted and
usually earns *limited* ads, and since March 2025 no uncertified gambling service may be linked, shown or mentioned.
So YouTube is distribution for the app and Telegram; treat ad revenue as a bonus, never the plan. The one music
track must also be free of Content ID claims: upload one video unlisted and check Studio's Copyright column before
letting the poster publish.

### Briefing videos go to Telegram, then the file is deleted (2026-10-13)
Shortlist briefing videos are sent with `send_telegram_video` (same `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` as the text picks). After a successful send the local file is unlinked. They are never committed, never published on the `data` branch, and never uploaded to Drive. Pass `PLAYREPORT_BRIEFING_VIDEO` on a report run to send one. The sound is the committed music track, looped to the picture (`music.bed`); nothing is synthesised in the workflow any more.

### Sportybet names no longer mix matches + shortlist briefing (2026-10-13)
`attach_prices` looked up Sportybet events by `zip(todays.index, rows)`. The depth gate drops thin fixtures from `rows` but not from `todays`, so every later event slid onto the wrong match — `home_long` then painted the bookmaker name (Kaizer Chiefs on Bristol City) across the app. Lookup is now by fixture identity; `event_fits` refuses a name that is not the same club; matching is exclusive; carried cache events are dropped when they do not fit. The client ignores `home_long` / Sportybet deep-links that fail the same check, so an already-published file stops lying on update. Shortlist tab: **Tonight's briefing** — a silent video-style player (same slide timing, no phone TTS) and a download (WebM when the WebView can record, otherwise a self-contained HTML briefing).

### Wrong-match fix, new sounds, corner & booking prices, focused trends (2026-10-13)
Four user-commissioned changes. **Wrong-match bug**: the client now verifies identity at every layer — a detail file must carry the tapped fixture's id AND its team names before it is rendered (`loadDetail`, `matchPage`), day-archive fallbacks are pinned by country (same-name pairs in two countries can never cross), and the on-phone cache moved to a fresh namespace (`pr_d:`) with a one-time sweep of the legacy `pr_c:*` entries, so data poisoned by pre-1.6.57 builds is gone on update. `tools/app_click_identity.mjs` boots the real app in jsdom against the live publication, taps every surface and asserts the right match opens — including poisoned-cache scenarios. **Notification sounds**: the whole `res/raw/pr_*.wav` family was re-synthesised (numpy additive synthesis, soft attack, exponential decay) to match each channel's meaning, and the channel ids were bumped to `_v4` (Android freezes a channel's sound at creation; old channels are deleted). **Corners & bookings prices**: `LIST_MARKETS` now includes Sportybet's total-corners (166) and bookings (139) markets — probed: the list endpoint carries both, so every priced fixture gets the ladders with no extra requests; `selections()` prices total corner/card lines from the list feed (per-event full list still wins) and adds team corner/card selections (`CH/CA/KH/KA` + O/U + line); `_sb_from_sels` rebuilds them across fetch outages; labels updated server- and client-side. **Trends**: non-Trends surfaces (match Overview) show only the 3 strongest trends by the strength score `s`; the Trends tabs keep everything.

### UEFA competitions + predicted line-ups (2026-10-12)
Two user-commissioned upgrades. **UEFA in**: `league_allowed` now admits the UEFA Champions League, Europa League and Conference League (allow entries: `^uefa$|^europe$` × `champions league|…`, plus the real Livescore shape `^champions league$|^europa league$|^conference league$` — the competition IS the country); the block regex keeps `qualif*|play-offs`, so UCL/UEL/UECL qualifiers and play-off rounds never enter. Intake seeds carry the probed-real stage keys `champions-league/league-stage,europa-league/league-stage,conference-league/league-stage` (all HTTP 200; the `uefa/*` slugs are 410); the Leagues tab derives from the index, so the app needs no client change. **Predicted line-ups**: all third-party prediction sources are bot-walled from server IPs, so the app grows its own — `research/lineups.XiArchive` harvests every confirmed XI the research layer already collects into `data/research/xi_archive.json` (eid-deduped, index capped 20k). A club with ≥3 archived XIs gets a projection (`XiArchive.projection`): formation by recency-weighted vote over the last 8 (0.75^i), starters ranked by weighted starts filled per position group (4-2-3-1 folds mid to n2+n3), bench from last-6 subs. `scanner.py` attaches projections to app rows before the shortlist pass; `appdata` publishes `lineup_proj`; `pages.js lineupsBlock` renders both XIs labelled **"Predicted by PlayReport … a projection, never official"** whenever the official XI is absent, and the official XI replaces it on publication. Projections never feed the model.

### Deep analysis + Telegram picks (2026-10-11)
### Calibration, safer doubles & the honest record (2026-10-11)
`calibration.py` learns a per-market-group isotonic map from the settled shortlist ledger and validates it OUT-OF-TIME (21-day holdout, Brier); it goes live per market group only where it beats the raw model. Live maps set `p_cal` on every pick and the honest composite on accas; the Performance page shows the curve, the per-market table and predicted-vs-actual bands. A second acca family — **safer doubles** (exactly 2 legs at ~2.00, same gates, never sharing a match with the 3.00 builds) — is tracked in its own ledger (`data/accas_doubles.csv`) with its own verification contract. `backtest/research_backtest.py` is the Phase-B evidence run: reconstructable research factors (rest, congestion, form gap) are tested against model residuals on the settled ledger; a factor earns a weight only on a monotone, well-sampled signal (2026-10-11 run: none — weights stay 0, see `backtest/RESEARCH_RESULTS.md`). The app notifies when the shortlist publishes (one push per run, `counts_shortlist` in the publication meta).

### Deep analysis + Telegram picks (2026-10-11) (`shortlist.match_article`) built only from its own MatchRow data — last-five form chips, a model-vs-bar-vs-market probability bar, goals per match, venue splits, head-to-head, and a verdict line; anything missing renders as N/A. The diet also filters the app-wide Leagues browser/fixtures index (`leagues.build(..., allow=league_allowed)`), so no off-diet competition appears anywhere. `scanner.telegram_shortlist()` pushes the day's primary picks (strongest market per match) to Telegram once per pick per day (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, deduped via `data/app/telegram_state.json`).

### High-conviction shortlist (`shortlist.py`)
A strict filter over the day's board: hard gates (data checks, verified price, odds band 1.15–1.90, per-market probability bar, believable model/market gap) and soft gates (data quality, confidence, warnings, research conflicts, carried prices). EV and edge are displayed but never gate (user rule 2026-10-11) — value hunting lives on the Positive EV tab. At most 7 matches, one selection each; otherwise **NO QUALIFYING SELECTIONS**. Read-only: it never changes a probability. Every decision is logged to `data/shortlist.csv` before kick-off and settled for walk-forward evaluation. Levers: `SHORTLIST_MIN_ODDS`, `SHORTLIST_MAX`.

### Sequences tab & selection rules
User betting sequences (07–12, 12–16, 16–20, 20–00 SAST) get their own tab: the day's shortlist split into windows — the same gates, one strongest market per match across all markets, Sportybet price and model probability.
